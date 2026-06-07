"""
PDF 题库解析器 — 从题目PDF和答案PDF中提取结构化题目数据。

支持的题型：
  - 选择题（单选/多选）：自动识别 A/B/C/D 选项
  - 填空题：识别填空标记
  - 解答题/计算题/证明题：完整提取大题内容

使用方式：
  parser = PDFQuestionParser()
  result = await parser.parse(question_pdf_path, answer_pdf_path)
  # result.questions: List[ParsedQuestion]
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pdfplumber

logger = logging.getLogger(__name__)


# ============================================================
# 数据模型
# ============================================================

@dataclass
class ParsedQuestion:
    """解析出的单道题目"""
    number: int                    # 题号 (1, 2, 3...)
    content: str                   # 题目正文
    question_type: str             # 选择题/填空题/解答题/计算题/证明题
    options: List[str] = field(default_factory=list)   # 选项 ["A.xxx", "B.xxx", ...]
    answer: str = ""               # 答案（从答案PDF提取）
    analysis: str = ""             # 解析（从答案PDF提取）
    raw_text: str = ""             # 原始文本（用于调试）
    sub_questions: List[Dict] = field(default_factory=list)  # 子题（如(1)(2)(3)）


@dataclass
class ParseResult:
    """解析结果"""
    success: bool = False
    total_questions: int = 0
    questions: List[ParsedQuestion] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


# ============================================================
# 正则模式
# ============================================================

# 题号匹配：1.  2.  （1）（2）  ①②③ 等
QUESTION_NUMBER_PATTERN = re.compile(
    r'^(?:'
    r'(?:\d+)[\.\、\s]'              # "1." "2、" "3 "
    r'|(?:\(\d+\))'                  # "(1)" "(2)"
    r'|[①②③④⑤⑥⑦⑧⑨⑩]'            # 圈数字
    r')',
    re.MULTILINE
)

# 选项匹配：A. xxx  B. xxx  或 (A) xxx
OPTION_PATTERN = re.compile(
    r'^([A-Fa-f])[\.\、\)]\s*(.+)$',
    re.MULTILINE
)

# 题型关键词检测
TYPE_KEYWORDS = {
    '选择题': ['选择题', '单选题', '多选题', '选择'],
    '填空题': ['填空题', '填空'],
    '解答题': ['解答题', '解答'],
    '计算题': ['计算题', '计算', '求', '求解'],
    '证明题': ['证明题', '证明', '求证'],
    '作图题': ['作图题', '作图'],
}

# 大题标题（如"一、选择题"、"二、填空题"）
SECTION_HEADER_PATTERN = re.compile(
    r'^(?:[一二三四五六七八九十]+[\.\、\s]|'
    r'[第\d]+[大题部分][\.\、\s]|'
    r'(?:选择|填空|解答|计算|证明|作图)[题]?[\s\(])',
    re.MULTILINE
)

# 答案中的常见格式：
# "1. A" / "1.A" / "(1) xxx" / "1. 答案：xxx"
ANSWER_LINE_PATTERN = re.compile(
    r'^(\d+)[\.\)\s]\s*(.+)$',
    re.MULTILINE
)

SUB_ANSWER_PATTERN = re.compile(
    r'[（(](\d+)[)）]\s*[:：]?\s*(.+)',
    re.MULTILINE
)


class PDFQuestionParser:
    """
    PDF 题库解析器
    
    功能：
      1. 从题目 PDF 提取每道题的内容、选项、题型
      2. 从答案 PDF 提取对应答案和解析
      3. 合并为结构化的 ParsedQuestion 列表
    """

    def __init__(
        self,
        auto_detect_category: bool = True,
        default_difficulty: int = 3,
        default_category: str = "未分类",
    ):
        self.auto_detect_category = auto_detect_category
        self.default_difficulty = default_difficulty
        self.default_category = default_category

    async def parse(
        self,
        question_pdf_path: str,
        answer_pdf_path: Optional[str] = None,
    ) -> ParseResult:
        """
        主解析入口
        
        Args:
            question_pdf_path: 题目 PDF 文件路径
            answer_pdf_path: 答案 PDF 文件路径（可选，没有则答案留空）
        
        Returns:
            ParseResult 包含所有解析出的题目
        """
        result = ParseResult()
        
        # 验证文件存在
        if not Path(question_pdf_path).exists():
            result.errors.append(f"题目PDF不存在: {question_pdf_path}")
            return result
        if answer_pdf_path and not Path(answer_pdf_path).exists():
            result.warnings.append(f"答案PDF不存在: {answer_pdf_path}，将跳过答案提取")
            answer_pdf_path = None

        # 步骤1：解析题目PDF
        logger.info(f"开始解析题目PDF: {question_pdf_path}")
        try:
            questions = await self._parse_question_pdf(question_pdf_path)
        except Exception as e:
            result.errors.append(f"题目PDF解析失败: {str(e)}")
            logger.error(f"题目PDF解析失败: {e}", exc_info=True)
            return result

        if not questions:
            result.errors.append("未从题目PDF中解析出任何题目")
            return result

        result.questions = questions
        result.total_questions = len(questions)
        logger.info(f"从题目PDF解析出 {len(questions)} 道题")

        # 步骤2：解析答案PDF并合并
        if answer_pdf_path:
            logger.info(f"开始解析答案PDF: {answer_pdf_path}")
            try:
                answers = await self._parse_answer_pdf(answer_pdf_path)
                await self._merge_answers(questions, answers)
                logger.info("答案合并完成")
            except Exception as e:
                result.warnings.append(f"答案PDF解析失败（题目已导入但无答案）: {str(e)}")
                logger.warning(f"答案PDF解析失败: {e}", exc_info=True)

        result.success = True
        return result

    async def _parse_question_pdf(self, pdf_path: str) -> List[ParsedQuestion]:
        """解析题目PDF，提取所有题目。优先使用 PyMuPDF (fitz)，回退到 pdfplumber"""
        questions: List[ParsedQuestion] = []
        
        # 策略1：PyMuPDF (fitz) — 对数学公式 PDF 提取效果更好
        try:
            import fitz  # PyMuPDF
            full_text = self._extract_with_fitz(pdf_path)
            if full_text and len(full_text.strip()) > 50:
                logger.info(f"PyMuPDF 提取成功，文本长度: {len(full_text)}")
                questions = self._split_into_questions(full_text)
                if questions:
                    return questions
        except ImportError:
            logger.info("PyMuPDF 未安装，回退到 pdfplumber")
        except Exception as e:
            logger.warning(f"PyMuPDF 提取失败: {e}，回退到 pdfplumber")
        
        # 策略2：pdfplumber（回退）
        logger.info("使用 pdfplumber 提取文本")
        full_text = self._extract_with_pdfplumber(pdf_path)
        questions = self._split_into_questions(full_text)
        
        return questions

    def _extract_with_fitz(self, pdf_path: str) -> str:
        """用 PyMuPDF (fitz) 提取 PDF 文本，对数学公式支持更好"""
        import fitz
        doc = fitz.open(pdf_path)
        all_pages_text = []
        
        for page_num, page in enumerate(doc):
            # 使用 text 参数提取，保留原始布局信息
            text = page.get_text("text")
            if text and text.strip():
                # 清理 fitz 常见的提取伪影
                text = self._clean_extracted_text(text)
                all_pages_text.append((page_num + 1, text))
        
        doc.close()
        
        # 合并全文
        full_text = ""
        for page_num, text in all_pages_text:
            full_text += f"\n--- PAGE_{page_num} ---\n{text}"
        
        return full_text

    def _extract_with_pdfplumber(self, pdf_path: str) -> str:
        """用 pdfplumber 提取 PDF 文本（回退方案）"""
        all_pages_text = []
        
        with pdfplumber.open(pdf_path) as pdf:
            for page_num, page in enumerate(pdf.pages):
                text = page.extract_text() or ""
                if text.strip():
                    text = self._clean_extracted_text(text)
                    all_pages_text.append((page_num + 1, text))
                
                # 表格
                tables = page.extract_tables()
                for table in tables or []:
                    table_text = "\n".join([
                        " | ".join(str(cell) or "" for cell in row)
                        for row in table
                    ])
                    if table_text.strip():
                        all_pages_text.append((page_num + 1, f"[TABLE]{table_text}[/TABLE]"))
        
        full_text = ""
        for page_num, text in all_pages_text:
            full_text += f"\n--- PAGE_{page_num} ---\n{text}"
        
        return full_text

    @staticmethod
    def _clean_extracted_text(text: str) -> str:
        """
        清理 PDF 提取的原始文本。
        去除常见伪影：乱码字符、多余空白、页眉页脚等
        """
        import re
        
        # 替换常见的 Unicode 乱码字符为可读替代
        replacements = {
            '\ufffd': '',           # REPLACEMENT CHARACTER
            '\u200b': '',           # ZERO WIDTH SPACE
            '\u200c': '',           # NON-JOINER
            '\u00a0': ' ',          # NO-BREAK SPACE → 普通空格
            '\ufeff': '',           # BOM
        }
        for old, new in replacements.items():
            text = text.replace(old, new)
        
        # 去除纯控制字符（保留换行和制表符）
        text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
        
        # 合并过多连续空行（超过2个变成2个）
        text = re.sub(r'\n{3,}', '\n\n', text)
        
        # 合并行内多个空格为单个
        text = re.sub(r' {3,}', '  ', text)
        
        return text.strip()

    def _split_into_questions(self, full_text: str) -> List[ParsedQuestion]:
        """
        将全文分割为独立的题目。
        
        核心策略：
          1. 先按大题节（一、二、三...）分组
          2. 在每个节内按题号分割
          3. 识别选项和子题
          4. 推断题型
        """
        questions: List[ParsedQuestion] = []
        
        # 清理文本
        text = full_text.replace('\r\n', '\n').replace('\r', '\n')
        
        # 分割成行
        lines = text.split('\n')
        
        current_section_type = "解答题"  # 默认类型
        current_q_number = 0
        current_content_lines: List[str] = []
        current_options: List[Tuple[str, str]] = []  # (letter, text)
        sub_questions: List[Dict] = []
        
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            
            # 跳过空行和页码标记
            if not line or line.startswith('--- PAGE_'):
                i += 1
                continue
            
            # 检测是否是大题节标题
            section_type = self._detect_section_type(line)
            if section_type:
                # 先保存之前的题目
                if current_content_lines:
                    q = self._build_question_from_buffer(
                        current_q_number, current_content_lines,
                        current_options, current_section_type, sub_questions
                    )
                    if q:
                        questions.append(q)
                    current_content_lines = []
                    current_options = []
                    sub_questions = []
                
                current_section_type = section_type
                i += 1
                continue
            
            # 检测是否是新题目的开始
            q_num = self._detect_question_number(line)
            if q_num is not None and q_num > 0:
                # 先保存之前的题目
                if current_content_lines:
                    q = self._build_question_from_buffer(
                        current_q_number, current_content_lines,
                        current_options, current_section_type, sub_questions
                    )
                    if q:
                        questions.append(q)
                    current_content_lines = []
                    current_options = []
                    sub_questions = []
                
                current_q_number = q_num
                # 把当前行作为第一行内容（去掉题号前缀）
                clean_line = self._strip_question_prefix(line, q_num)
                if clean_line:
                    current_content_lines.append(clean_line)
                i += 1
                continue
            
            # 检测是否是选项
            option_match = OPTION_PATTERN.match(line)
            if option_match and current_q_number > 0:
                opt_letter = option_match.group(1).upper()
                opt_text = option_match.group(2).strip()
                current_options.append((opt_letter, opt_text))
                i += 1
                continue
            
            # 检测是否是子题 (1) (2) (3) 或 （1）（2）（3）
            sub_match = re.match(r'^[（(](\d+)[)）]', line)
            if sub_match and current_q_number > 0:
                sub_num = int(sub_match.group(1))
                sub_text = line[sub_match.end():].strip()
                sub_questions.append({
                    "number": sub_num,
                    "content": sub_text,
                })
                i += 1
                continue
            
            # 普通内容行 → 归入当前题目
            if current_q_number > 0:
                current_content_lines.append(line)
            
            i += 1
        
        # 不要遗漏最后一道题
        if current_content_lines:
            q = self._build_question_from_buffer(
                current_q_number, current_content_lines,
                current_options, current_section_type, sub_questions
            )
            if q:
                questions.append(q)

        return questions

    def _build_question_from_buffer(
        self,
        number: int,
        content_lines: List[str],
        options: List[Tuple[str, str]],
        section_type: str,
        sub_questions: List[Dict],
    ) -> Optional[ParsedQuestion]:
        """从缓冲区构建 ParsedQuestion 对象"""
        if number <= 0 or not content_lines:
            return None
        
        # 合并内容
        content = "\n".join(content_lines).strip()
        
        # 去掉表格标记
        content = re.sub(r'\[TABLE\](.*?)\[/TABLE\]', r'\1', content, flags=re.DOTALL)
        
        # 去掉多余空白
        content = re.sub(r'\n{3,}', '\n\n', content)
        
        # 如果有选项，推断为选择题
        if options:
            qtype = "选择题"
            opt_list = [f"{letter}.{text}" for letter, text in options]
        else:
            qtype = self._infer_question_type(content, section_type)
            opt_list = []
        
        return ParsedQuestion(
            number=number,
            content=content,
            question_type=qtype,
            options=opt_list,
            raw_text=content,
            sub_questions=sub_questions,
        )

    def _detect_section_type(self, line: str) -> Optional[str]:
        """检测是否是大题节标题，返回题型或None"""
        line_lower = line.lower().strip()
        for qtype, keywords in TYPE_KEYWORDS.items():
            for kw in keywords:
                if kw in line_lower and len(line) < 30:
                    return qtype
        return None

    def _detect_question_number(self, line: str) -> Optional[int]:
        """检测行首的题号，返回数字或None"""
        stripped = line.strip()
        
        # 匹配 "1." "2." "3、" 等
        m = re.match(r'^(\d+)[\.\、\s]', stripped)
        if m:
            return int(m.group(1))
        
        # 匹配 "(1)" "(2)" 但排除选项
        m = re.match(r'^\((\d+)\)\s', stripped)
        if m and len(stripped) > 5:  # 不是短选项
            return int(m.group(1))
        
        # 匹配圈数字
        circle_map = {'①':1,'②':2,'③':3,'④':4,'⑤':5,'⑥':6,'⑦':7,'⑧':8,'⑨':9,'⑩':10}
        if stripped[0] in circle_map:
            return circle_map[stripped[0]]
        
        return None

    def _strip_question_prefix(self, line: str, num: int) -> str:
        """去掉行首的题号前缀"""
        # 去掉 "1. " "2、" "3 " 等
        cleaned = re.sub(r'^\d+[\.\、\s]+', '', line).strip()
        # 去掉 "(1)" 前缀
        cleaned = re.sub(r'^\(\d+\)\s*', '', cleaned).strip()
        return cleaned

    def _infer_question_type(self, content: str, section_type: str) -> str:
        """根据内容和所在节推断题型"""
        # 如果已有明确的节的类型（非默认），直接使用
        if section_type and section_type not in ("解答题", ""):
            return section_type
        
        # 根据内容特征判断（仅在未明确分类时）
        if '_____' in content or '___' in content or '（  ）' in content or '(    )' in content:
            return "填空题"
        if '求证' in content or '证明' in content:
            return "证明题"
        # "求"和"计算"只有在非解答题节下才判定为计算题
        if ('计算' in content) and section_type != "解答题":
            return "计算题"
        if '解' in content:
            return "解答题"
        
        return section_type or "解答题"

    async def _parse_answer_pdf(self, pdf_path: str) -> Dict[int, Dict[str, str]]:
        """
        解析答案PDF，返回 {题号: {"answer": ..., "analysis": ...}}
        """
        answers: Dict[int, Dict[str, str]] = {}
        
        with pdfplumber.open(pdf_path) as pdf:
            full_text = ""
            for page in pdf.pages:
                text = page.extract_text() or ""
                if text.strip():
                    full_text += text + "\n"
        
        # 策略1：逐行匹配 "1. xxx" 格式
        for match in ANSWER_LINE_PATTERN.finditer(full_text):
            qnum = int(match.group(1))
            ans_text = match.group(2).strip()
            if qnum not in answers:
                answers[qnum] = {"answer": ans_text}
            else:
                # 已有则追加到分析
                existing = answers[qnum].get("answer", "")
                answers[qnum]["analysis"] = ans_text
        
        # 策略2：匹配子题答案 "(1) xxx"
        for match in SUB_ANSWER_PATTERN.finditer(full_text):
            sub_num = int(match.group(1))
            sub_ans = match.group(2).strip()
            # 找到最近的父题号
            parent_qnum = self._find_parent_question_for_sub(match.start(), full_text)
            if parent_qnum is not None:
                if parent_qnum not in answers:
                    answers[parent_qnum] = {"answer": "", "sub_answers": {}}
                if "sub_answers" not in answers[parent_qnum]:
                    answers[parent_qnum]["sub_answers"] = {}
                answers[parent_qnum]["sub_answers"][str(sub_num)] = sub_ans
        
        return answers

    def _find_parent_question_for_sub(
        self, pos: int, text: str
    ) -> Optional[int]:
        """找到子题答案对应的父题号"""
        # 向前搜索最近的主题号
        before = text[:pos]
        matches = list(re.finditer(r'^(\d+)[\.\)]', before, re.MULTILINE))
        if matches:
            return int(matches[-1].group(1))
        return None

    async def _merge_answers(
        self,
        questions: List[ParsedQuestion],
        answers: Dict[int, Dict[str, str]],
    ) -> None:
        """将答案合并到题目上"""
        for q in questions:
            if q.number in answers:
                ans_data = answers[q.number]
                q.answer = ans_data.get("answer", "")
                q.analysis = ans_data.get("analysis", "")
                
                # 处理子题答案
                if "sub_answers" in ans_data and q.sub_questions:
                    for sq in q.sub_questions:
                        sub_num_str = str(sq["number"])
                        if sub_num_str in ans_data["sub_answers"]:
                            sq["answer"] = ans_data["sub_answers"][sub_num_str]

    # ============================================================
    # 导出工具方法
    # ============================================================

    def to_import_dicts(
        self,
        parse_result: ParseResult,
        category: str = "",
        source_name: str = "",
    ) -> List[Dict[str, Any]]:
        """
        将 ParseResult 转换为 QuestionImporter 可接受的字典列表。
        
        Args:
            parse_result: 解析结果
            category: 手动指定的分类（留空则自动检测）
            source_name: 来源名称（用于 source 字段）
        
        Returns:
            符合数据库 schema 的字典列表
        """
        dicts = []
        base_id = f"PDF_{uuid.uuid4().hex[:6].upper()}"
        
        for idx, q in enumerate(parse_result.questions):
            qid = f"{base_id}_{q.number:03d}"
            
            # 构建选项 JSON
            options_json = json.dumps(q.options, ensure_ascii=False) if q.options else "[]"
            
            # 构建知识点（从内容简单推断）
            kps = self._extract_knowledge_points(q.content, category)
            
            entry = {
                "id": qid,
                "content": q.content,
                "question_type": q.question_type,
                "options": options_json,
                "answer": q.answer or "待补充",
                "analysis": q.analysis,
                "category": category or self.default_category,
                "sub_categories": "",
                "knowledge_points": json.dumps(kps, ensure_ascii=False),
                "difficulty": self.default_difficulty,
                "estimated_time": self._estimate_time(q.question_type),
                "source": source_name or "PDF导入",
            }
            dicts.append(entry)
        
        return dicts

    @staticmethod
    def _extract_knowledge_points(content: str, category: str) -> List[str]:
        """从题目内容中粗略提取知识点关键词"""
        points = [category] if category else []
        
        # 数学常见关键词
        keywords_map = {
            "导数": ["导数", "f'(x)", "f''(x)", "切线", "单调性", "极值", "最值"],
            "积分": ["积分", "∫", "定积分", "不定积分", "面积"],
            "极限": ["极限", "lim", "趋近于", "无穷"],
            "三角函数": ["sin", "cos", "tan", "三角", "正弦", "余弦", "正切"],
            "数列": ["数列", "等差", "等比", "a_n", "通项"],
            "不等式": ["不等式", "≤", "≥", "<", ">"],
            "集合": ["集合", "∩", "∪", "补集", "交集", "并集"],
            "函数": ["函数", "f(x)", "定义域", "值域"],
            "概率": ["概率", "P(", "随机", "期望", "方差"],
            "立体几何": ["体积", "表面积", "垂直", "平行", "空间"],
            "解析几何": ["椭圆", "双曲线", "抛物线", "圆", "直线", "曲线"],
        }
        
        for kp, keywords in keywords_map.items():
            for kw in keywords:
                if kw in content and kp not in points:
                    points.append(kp)
                    break
        
        return points or ["未分类"]

    @staticmethod
    def _estimate_time(question_type: str) -> int:
        """根据题型估算答题时间（分钟）"""
        time_map = {
            "选择题": 2,
            "填空题": 3,
            "计算题": 5,
            "证明题": 7,
            "解答题": 8,
            "作图题": 5,
        }
        return time_map.get(question_type, 3)
