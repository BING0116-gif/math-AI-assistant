"""DocumentParser adapter — 正式 PDF 解析边界。

生产业务只依赖 `DocumentParser.parse(file_path, mode) -> ParsedDocument`，
不直接 import MinerU Python API。MinerU 通过 subprocess 调用独立 dedicated venv CLI。

模式：
- quick  : PyMuPDF 文本提取（电子 PDF / 调试），页码可靠。
- mineru : 数学增强模式；MinerU 输出 Markdown/LaTeX，页码映射不确定时显式标记。

安全边界：
- 参数一律 list，shell=False，不拼 shell command 字符串；
- 设置 timeout；捕获 exit code；stdout/stderr 长度控制；
- 使用独立临时输出目录；不信任原始 filename；错误结束后清理临时目录；
- 所有错误转为稳定 application error（Exception 带稳定 code）。
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional

from app.config.settings import settings

logger = logging.getLogger(__name__)

# 稳定错误码
PARSER_UNAVAILABLE = "PARSER_UNAVAILABLE"
INVALID_PDF = "INVALID_PDF"
PARSE_FAILED = "PARSE_FAILED"

# 支持的 parser 模式
MODE_MINERU = "mineru"
MODE_QUICK = "quick"
MODE_AUTO = "auto"
MODE_LAYOUT_WORKER = "layout_worker"
SUPPORTED_MODES = (MODE_MINERU, MODE_QUICK, MODE_AUTO, MODE_LAYOUT_WORKER)

# subprocess 输出长度上限（防止大输出撑爆内存）
_MAX_STREAM_CHARS = 20000


class ContentParseError(Exception):
    """稳定 application error，携带稳定 code。"""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class ParserCancelled(Exception):
    """解析过程被上层任务取消。"""


@dataclass
class ParsedPage:
    page: Optional[int] = None
    text: str = ""


# 块类型：MinerU type 映射为稳定枚举
BLOCK_KIND_TEXT = "text"
BLOCK_KIND_HEADER = "header"
BLOCK_KIND_PAGE_NUMBER = "page_number"
BLOCK_KIND_EQUATION = "equation"
_KNOWN_BLOCK_TYPES = {BLOCK_KIND_TEXT, BLOCK_KIND_HEADER, BLOCK_KIND_PAGE_NUMBER, BLOCK_KIND_EQUATION}


@dataclass
class PageBlock:
    """单个结构化块：保留真实页码 + 类型 + 文本，供 section-aware splitter 消费。

    page 使用 1-based（MinerU page_idx 为 0-based）+1 得到。
    """
    text: str = ""
    page: Optional[int] = None
    kind: str = BLOCK_KIND_TEXT
    text_level: Optional[int] = None
    bbox: Optional[list] = None
    confidence: Optional[float] = None


@dataclass
class ParsedDocument:
    parser_name: str
    parser_version: str
    markdown: str = ""
    pages: List[ParsedPage] = field(default_factory=list)
    # 顺文档序的块列表（真实页码）；无可靠页码时为空列表
    blocks: List[PageBlock] = field(default_factory=list)
    # MinerU 页码映射不确定时置 True，candidate 据此标记 source_page=null + warning
    page_mapping_uncertain: bool = False


def _parsed_document_from_worker(payload: object) -> ParsedDocument:
    """将 sidecar JSON 收敛为内部模型，拒绝不完整/不可信结构。"""
    if not isinstance(payload, dict):
        raise ContentParseError(PARSE_FAILED, "layout-worker 返回格式无效")
    parser_name = str(payload.get("parser_name") or MODE_LAYOUT_WORKER)
    parser_version = str(payload.get("parser_version") or "unknown")
    pages: List[ParsedPage] = []
    for item in payload.get("pages") or []:
        if not isinstance(item, dict):
            continue
        pages.append(ParsedPage(page=item.get("page"), text=str(item.get("text") or "")))
    blocks: List[PageBlock] = []
    for item in payload.get("blocks") or []:
        if not isinstance(item, dict) or not str(item.get("text") or "").strip():
            continue
        bbox = item.get("bbox")
        if bbox is not None and (not isinstance(bbox, list) or len(bbox) != 4):
            bbox = None
        blocks.append(PageBlock(
            text=str(item.get("text") or ""),
            page=item.get("page"),
            kind=str(item.get("kind") or BLOCK_KIND_TEXT),
            text_level=item.get("text_level"),
            bbox=bbox,
            confidence=float(item["confidence"]) if item.get("confidence") is not None else None,
        ))
    markdown = str(payload.get("markdown") or "")
    if not markdown and pages:
        markdown = "\n\n".join(page.text for page in pages)
    if not markdown and not blocks:
        raise ContentParseError(PARSE_FAILED, "layout-worker 输出为空")
    return ParsedDocument(
        parser_name=parser_name,
        parser_version=parser_version,
        markdown=markdown,
        pages=pages,
        blocks=blocks,
        page_mapping_uncertain=bool(payload.get("page_mapping_uncertain", False)),
    )


def _repage_worker_payload(payload: object, page_number: int) -> Dict[str, object]:
    """把单页 worker 输出绑定到原 PDF 的真实 1-based 页码。"""
    if not isinstance(payload, dict):
        raise ContentParseError(PARSE_FAILED, "layout-worker 返回格式无效")
    repaged = dict(payload)
    pages = []
    for item in payload.get("pages") or []:
        if not isinstance(item, dict):
            continue
        page = dict(item)
        page["page"] = page_number
        pages.append(page)
    blocks = []
    for item in payload.get("blocks") or []:
        if not isinstance(item, dict):
            continue
        block = dict(item)
        block["page"] = page_number
        blocks.append(block)
    repaged["pages"] = pages
    repaged["blocks"] = blocks
    return repaged


def _merge_worker_payloads(payloads: List[Dict[str, object]]) -> Dict[str, object]:
    """合并按页 worker 输出，保持页面/块顺序并保留解析元数据。"""
    if not payloads:
        raise ContentParseError(PARSE_FAILED, "layout-worker 输出为空")
    pages = []
    blocks = []
    markdown_parts = []
    for payload in payloads:
        pages.extend(payload.get("pages") or [])
        blocks.extend(payload.get("blocks") or [])
        markdown = str(payload.get("markdown") or "").strip()
        if markdown:
            markdown_parts.append(markdown)
    return {
        "parser_name": str(payloads[0].get("parser_name") or MODE_LAYOUT_WORKER),
        "parser_version": str(payloads[0].get("parser_version") or "unknown"),
        "markdown": "\n\n".join(markdown_parts),
        "pages": pages,
        "blocks": blocks,
        "page_mapping_uncertain": any(bool(p.get("page_mapping_uncertain")) for p in payloads),
    }


class DocumentParser:
    """解析 PDF -> ParsedDocument。"""

    def __init__(self, executable: Optional[str] = None):
        self._executable = executable if executable is not None else settings.MINERU_EXECUTABLE

    # ── 对外统一入口 ──
    def parse(
        self,
        file_path: str | Path,
        mode: str = MODE_QUICK,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> ParsedDocument:
        if mode not in SUPPORTED_MODES:
            raise ContentParseError(PARSE_FAILED, f"未知解析模式: {mode}")
        if mode == MODE_MINERU:
            return self._parse_mineru(file_path)
        if mode == MODE_LAYOUT_WORKER:
            return self._parse_layout_worker(file_path, progress_callback=progress_callback)
        return self._parse_quick(file_path)

    def layout_worker_available(self) -> bool:
        """只做轻量探活；sidecar 不可达时绝不阻塞主解析链路。"""
        base_url = (settings.LAYOUT_WORKER_URL or "").strip().rstrip("/")
        if not base_url:
            return False
        try:
            import httpx
            response = httpx.get(f"{base_url}/health", timeout=min(5.0, float(settings.LAYOUT_WORKER_TIMEOUT_SECONDS)))
            return response.status_code == 200 and response.json().get("status") == "ready"
        except Exception:  # noqa: BLE001
            logger.info("layout-worker 探活失败，自动路由将跳过 sidecar", exc_info=True)
            return False

    # ── quick：PyMuPDF ──
    def _parse_quick(self, file_path: str | Path) -> ParsedDocument:
        import fitz  # PyMuPDF（主 venv 轻量依赖）

        path = Path(file_path)
        if not path.exists() or not path.is_file():
            raise ContentParseError(INVALID_PDF, "文件不存在")
        try:
            doc = fitz.open(path)
        except Exception as e:  # noqa: BLE001
            raise ContentParseError(INVALID_PDF, f"无法打开 PDF: {e}")
        try:
            if doc.page_count <= 0:
                raise ContentParseError(INVALID_PDF, "PDF 无有效页面")
            pages: List[ParsedPage] = []
            blocks: List[PageBlock] = []
            for i in range(doc.page_count):
                page = doc[i]
                text = page.get_text("text", sort=True) or ""
                page_no = i + 1
                pages.append(ParsedPage(page=page_no, text=text))
                # 保留文本块 bbox，后续遇到字体映射异常时可精确显示原题图。
                # 只用 get_text("text") 会丢掉位置，导致审核页只能展示整页缩略图。
                page_blocks = page.get_text("blocks", sort=True) or []
                if page_blocks:
                    for item in page_blocks:
                        block_text = str(item[4] or "") if len(item) > 4 else ""
                        if block_text.strip():
                            bbox = list(item[:4]) if len(item) >= 4 else None
                            for line in block_text.splitlines():
                                if line.strip():
                                    blocks.append(PageBlock(text=line, page=page_no, kind=BLOCK_KIND_TEXT, bbox=bbox))
                else:
                    # 极少数 PDF 没有 block 元数据，保留原有逐行降级路径。
                    for line in text.splitlines():
                        if (line or "").strip():
                            blocks.append(PageBlock(text=line, page=page_no, kind=BLOCK_KIND_TEXT))
            markdown = "\n\n".join(p.text for p in pages)
            return ParsedDocument(
                parser_name=MODE_QUICK,
                parser_version="PyMuPDF",
                markdown=markdown,
                pages=pages,
                blocks=blocks,
                page_mapping_uncertain=False,
            )
        finally:
            doc.close()

    def _parse_layout_worker(
        self,
        file_path: str | Path,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> ParsedDocument:
        """调用独立版面解析 worker，按页提交以提供可恢复进度。"""
        base_url = (settings.LAYOUT_WORKER_URL or "").strip().rstrip("/")
        if not base_url:
            raise ContentParseError(PARSER_UNAVAILABLE, "layout-worker 未配置")
        path = Path(file_path)
        if not path.exists() or not path.is_file():
            raise ContentParseError(INVALID_PDF, "文件不存在")
        try:
            import fitz
            import httpx

            source = fitz.open(path)
            try:
                if source.page_count <= 0:
                    raise ContentParseError(INVALID_PDF, "PDF 无有效页面")
                total_pages = source.page_count
                if not settings.LAYOUT_WORKER_PAGEWISE:
                    with path.open("rb") as handle:
                        response = httpx.post(
                            f"{base_url}/v1/parse",
                            files={"file": (path.name, handle, "application/pdf")},
                            timeout=float(settings.LAYOUT_WORKER_TIMEOUT_SECONDS),
                        )
                    if response.status_code != 200:
                        raise ContentParseError(
                            PARSE_FAILED,
                            f"layout-worker 返回 {response.status_code}: {response.text[-1000:]}",
                        )
                    if progress_callback is not None:
                        progress_callback(total_pages, total_pages)
                    return _parsed_document_from_worker(response.json())
                payloads: List[Dict[str, object]] = []
                with tempfile.TemporaryDirectory(prefix="layout_pages_") as page_dir:
                    for page_index in range(total_pages):
                        page_number = page_index + 1
                        page_path = Path(page_dir) / f"page-{page_number}.pdf"
                        single_page = fitz.open()
                        try:
                            single_page.insert_pdf(source, from_page=page_index, to_page=page_index)
                            single_page.save(page_path)
                        finally:
                            single_page.close()

                        with page_path.open("rb") as handle:
                            response = httpx.post(
                                f"{base_url}/v1/parse",
                                files={"file": (page_path.name, handle, "application/pdf")},
                                timeout=float(settings.LAYOUT_WORKER_TIMEOUT_SECONDS),
                            )
                        if response.status_code != 200:
                            raise ContentParseError(
                                PARSE_FAILED,
                                f"layout-worker 第 {page_number} 页返回 {response.status_code}: {response.text[-1000:]}",
                            )
                        payloads.append(_repage_worker_payload(response.json(), page_number))
                        if progress_callback is not None:
                            progress_callback(page_number, total_pages)
                return _parsed_document_from_worker(_merge_worker_payloads(payloads))
            finally:
                source.close()
        except (ContentParseError, ParserCancelled):
            raise
        except Exception as exc:  # noqa: BLE001
            raise ContentParseError(PARSER_UNAVAILABLE, f"layout-worker 不可用: {exc}")

    # ── mineru：subprocess 调用独立 CLI ──
    def _parse_mineru(self, file_path: str | Path) -> ParsedDocument:
        executable = self._mineru_executable()
        if executable is None:
            raise ContentParseError(
                PARSER_UNAVAILABLE,
                "MinerU 不可用：未配置 MINERU_EXECUTABLE 或 executable 不存在",
            )

        path = Path(file_path)
        if not path.exists() or not path.is_file():
            raise ContentParseError(INVALID_PDF, "文件不存在")

        # 独立临时输出目录（每次调用唯一）
        temp_root = Path(tempfile.mkdtemp(prefix="mineru_out_"))
        try:
            # 使用随机输出子目录，避免跨并发互相覆盖
            out_dir = temp_root / "out"
            out_dir.mkdir(parents=True, exist_ok=True)

            cmd = [
                executable,
                "-p", str(path.resolve()),
                "-o", str(out_dir),
                "-b", "pipeline",
            ]
            logger.info("调用 MinerU: %s", " ".join(f'"{c}"' if " " in c else c for c in cmd[1:]))

            # Windows 上 MinerU 会派生子进程（本地 fast-api server）并让其继承
            # stdout/stderr 管道句柄，导致 capture_output 的 communicate() 在
            # 主进程退出后永远等不到 EOF 而卡死。因此改为重定向到临时文件，
            # 避免管道句柄被后代进程持有，超时后按进程树清理。
            stdout_log = temp_root / "mineru_stdout.log"
            stderr_log = temp_root / "mineru_stderr.log"
            creationflags = (
                subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            )
            proc: Optional[subprocess.Popen] = None
            try:
                # 显式构造 subprocess env：继承 os.environ，并确保模型源稳定传递，
                # 使 dedicated venv 命中用户级 ModelScope 缓存，避免误触发下载。
                env = dict(os.environ)
                env.setdefault("MINERU_MODEL_SOURCE", settings.MINERU_MODEL_SOURCE)
                with open(stdout_log, "wb", buffering=0) as so, open(
                    stderr_log, "wb", buffering=0
                ) as se:
                    proc = subprocess.Popen(
                        cmd,
                        shell=False,
                        cwd=str(temp_root),
                        stdin=subprocess.DEVNULL,
                        stdout=so,
                        stderr=se,
                        env=env,
                        creationflags=creationflags,
                    )
                    try:
                        proc.wait(timeout=settings.CONTENT_PARSER_TIMEOUT_SECONDS)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        _kill_process_tree(proc.pid)
                        raise ContentParseError(
                            PARSE_FAILED,
                            f"MinerU 解析超时（>{settings.CONTENT_PARSER_TIMEOUT_SECONDS}s）",
                        )
            except OSError as e:
                raise ContentParseError(PARSER_UNAVAILABLE, f"MinerU 无法启动: {e}")

            def _read_log(p: Path) -> str:
                try:
                    return p.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    return ""

            if proc.returncode != 0:
                raise ContentParseError(
                    PARSE_FAILED,
                    "MinerU 解析失败\nSTDOUT:\n"
                    + _read_log(stdout_log)[-_MAX_STREAM_CHARS:]
                    + "\nSTDERR:\n"
                    + _read_log(stderr_log)[-_MAX_STREAM_CHARS:],
                )

            md_files = sorted(out_dir.rglob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
            if not md_files:
                raise ContentParseError(PARSE_FAILED, "MinerU 已运行，但没有生成 Markdown 文件")
            md_path = md_files[0]
            markdown = md_path.read_text(encoding="utf-8", errors="replace")
            if not markdown.strip():
                raise ContentParseError(PARSE_FAILED, "MinerU 输出为空")

            # 使用 MinerU 结构化产物 *_content_list.json 做可靠页码映射。
            # 每个 block 提供真实 page_idx / type / text_level / bbox；
            # 若产物缺失（旧版/异常），回退 markdown + page_mapping_uncertain=True。
            blocks, page_mapping_uncertain = _load_mineru_content_blocks(out_dir)

            return ParsedDocument(
                parser_name=MODE_MINERU,
                parser_version=self._mineru_version(executable),
                markdown=markdown,
                blocks=blocks,
                page_mapping_uncertain=page_mapping_uncertain,
            )
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)

    # ── helpers ──
    def _mineru_executable(self) -> Optional[str]:
        exe = (self._executable or "").strip()
        if not exe:
            return None
        if not os.path.exists(exe):
            return None
        return exe

    @staticmethod
    def _mineru_version(executable: str) -> str:
        try:
            proc = subprocess.run(
                [executable, "--version"],
                shell=False,
                capture_output=True,
                text=True,
                timeout=30,
            )
            out = (proc.stdout or "").strip().splitlines()
            return out[0] if out else "unknown"
        except Exception:  # noqa: BLE001
            return "unknown"


def _load_mineru_content_blocks(out_dir: Path):
    """从 MinerU 产物 *_content_list.json 读取页级块列表。

    返回 (blocks, page_mapping_uncertain)。
    - 找到并解析成功：blocks 带真实 1-based 页码，uncertain=False。
    - 找不到/解析失败：blocks 为空，uncertain=True（调用方回退到整篇 markdown + 不确定页码）。
    """
    try:
        files = list(out_dir.rglob("*_content_list.json"))
        if not files:
            return [], True
        path = sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)[0]
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:  # noqa: BLE001
        logger.warning("MinerU content_list 解析失败，回退页面不确定", exc_info=True)
        return [], True

    if not isinstance(data, list):
        return [], True

    blocks: List[PageBlock] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        text = (item.get("text") or "")
        text = text.replace("\n", "\n").strip("\n")
        kind_raw = item.get("type") or BLOCK_KIND_TEXT
        kind = kind_raw if kind_raw in _KNOWN_BLOCK_TYPES else BLOCK_KIND_TEXT
        page_idx = item.get("page_idx")
        page = (int(page_idx) + 1) if isinstance(page_idx, int) else None
        level = item.get("text_level")
        blocks.append(
            PageBlock(
                text=text,
                page=page,
                kind=kind,
                text_level=int(level) if isinstance(level, int) else None,
                bbox=item.get("bbox"),
            )
        )
    return blocks, False


def _kill_process_tree(pid: int) -> None:
    """终止指定 PID 及其后代进程（Windows 用 taskkill /T；否则 kill）。"""
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(pid)],
            shell=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    else:
        try:
            import signal

            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass


def validate_pdf_upload(content: bytes, original_filename: str) -> None:
    """上传安全边界检查（§13）。

    - .pdf 扩展名
    - PDF magic / header（%PDF-）
    - 文件大小上限
    - 页数上限（读取 header 后按 'obj' 个数粗略估算，或由调用方用 PyMuPDF 精确校验）
    """
    name = (original_filename or "").strip()
    if not name.lower().endswith(".pdf"):
        raise ContentParseError(INVALID_PDF, "仅支持 .pdf 文件")
    if not content:
        raise ContentParseError(INVALID_PDF, "文件内容为空")
    if len(content) > settings.CONTENT_MAX_UPLOAD_BYTES:
        raise ContentParseError(
            INVALID_PDF,
            f"文件超过大小上限 {settings.CONTENT_MAX_UPLOAD_BYTES // (1024 * 1024)}MB",
        )
    # PDF magic：文件头应包含 %PDF-
    if content[:1024].find(b"%PDF-") == -1:
        raise ContentParseError(INVALID_PDF, "文件不是有效的 PDF（缺少 PDF 头）")


def validate_pdf_page_count(file_path: str | Path) -> int:
    """用 PyMuPDF 精确校验页数上限，返回页数；超限抛稳定错误。"""
    import fitz

    doc = fitz.open(str(file_path))
    try:
        count = doc.page_count
        if count > settings.CONTENT_MAX_PAGES:
            raise ContentParseError(
                PARSE_FAILED,
                f"PDF 页数 {count} 超过上限 {settings.CONTENT_MAX_PAGES}",
            )
        return count
    finally:
        doc.close()
