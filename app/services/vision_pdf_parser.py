"""
视觉模型驱动的 PDF 题目提取器 — 用千问VL"看"PDF图片来识别数学公式。

原理：
  PDF页面 → 转成PNG图片 → 发给千问VL(视觉模型) → AI识别题目+公式+选项+答案

优势：
  - 不依赖字体编码，任何数学公式都能"看到"
  - 复杂排版、手写体、扫描件都行
  - 利用已有的千问API，无需额外ML库
"""

import base64
import io
import json
import logging
import os
import re
import sys
import tempfile
from dataclasses import dataclass, field, asdict
from typing import List, Optional

if sys.platform == 'win32':
    # Fix Windows console encoding for Unicode output
    import _locale
    try:
        _locale._default_locale = lambda: ('zh_CN', 'utf8')
    except Exception:
        pass

# Use fitz/PyMuPDF for PDF→image conversion (already installed)
import fitz  # PyMuPDF
from app.config.settings import settings

logger = logging.getLogger(__name__)


@dataclass
class VLExtractedQuestion:
    """视觉模型提取的单道题"""
    id: str = ""
    content: str = ""
    question_type: str = "text"
    options: List[str] = field(default_factory=list)
    answer: str = ""
    analysis: str = ""
    category: str = ""  # 从文件名或内容推断
    difficulty: int = 3
    knowledge_points: List[str] = field(default_factory=list)
    source_page: int = 0


@dataclass
class VLExtractionResult:
    """整页/整个PDF的提取结果"""
    questions: List[VLExtractedQuestion] = field(default_factory=list)
    raw_text: str = ""  # 原始文本（用于调试）
    errors: List[str] = field(default_factory=list)

    @property
    def success(self) -> int:
        return len([q for q in self.questions if q.content and len(q.content) > 5])

    @property
    def failed(self) -> int:
        return len(self.errors)


class VisionPDFParser:
    """
    用视觉大模型(VL)解析含数学公式的PDF。
    
    核心思路：把PDF每页转成图片，让AI"看"图片来提取结构化题目。
    """

    # 提取提示词 — 让VL模型输出结构化JSON
    EXTRACTION_PROMPT = r"""你是一个专业的数学试卷OCR助手。请仔细阅读这张数学试卷的图片，提取出所有题目。

要求：
1. 识别每一道完整的题目（包括选择题、填空题、解答题、计算题、证明题等）
2. 完整保留所有数学公式和符号（用LaTeX格式表示，如 $f'(x)$、$\int_0^1$、$\lim_{x\to 0}$ 等）
3. 如果有选项(A/B/C/D)，完整记录每个选项的内容
4. 如果能看出答案（如选择题的勾选、填空题的答案），也一并记录

输出格式（严格JSON数组）：
[
  {
    "content": "题目完整内容（含公式）",
    "type": "选择题|填空题|解答题|计算题|证明题",
    "options": ["A选项内容", "B选项内容", ...],
    "answer": "答案",
    "analysis": "解题思路（如果能从图中看出）"
  },
  ...
]

注意：
- 公式用 $...$ 包裹（行内）或 $$...$$ 包裹（独立成行）
- 大题包含多个小问时，每个小问作为独立一道题
- 只输出JSON，不要其他文字
- 如果这一页没有题目，返回空数组 []
"""

    def __init__(self, api_key: str = "", api_base: str = "", model: str = ""):
        from openai import AsyncOpenAI
        
        self.api_key = api_key or settings.LLM_API_KEY
        self.api_base = api_base or "https://dashscope.aliyuncs.com/compatible-mode/v1"
        self.model = model or "qwen-vl-max"  # 千问视觉模型
        
        self.client = AsyncOpenAI(
            api_key=self.api_key,
            base_url=self.api_base,
        )
        
        logger.info(f"VisionPDFParser 初始化完成 | model={self.model}")

    def pdf_to_images(self, pdf_path: str, dpi: int = 200) -> List[tuple]:
        """
        将PDF每一页转换为PNG图片。
        返回: [(page_num, image_bytes), ...]
        """
        doc = fitz.open(pdf_path)
        pages = []
        
        for page_num in range(len(doc)):
            page = doc[page_num]
            # 设置DPI，越高越清晰但越大
            mat = fitz.Matrix(dpi / 72, dpi / 72)
            pix = page.get_pixmap(matrix=mat)
            
            img_data = pix.tobytes("png")
            pages.append((page_num + 1, img_data))
            
            size_kb = len(img_data) / 1024
            logger.debug(f"Page {page_num + 1}: {pix.width}x{pix.height}, {size_kb:.0f}KB")
        
        doc.close()
        logger.info(f"PDF转图完成: {len(pages)} 页")
        return pages

    async def extract_from_image(
        self,
        image_bytes: bytes,
        page_num: int = 0,
        category_hint: str = "",
    ) -> VLExtractionResult:
        """
        发送单页图片到视觉模型，提取题目。
        """
        img_b64 = base64.b64encode(image_bytes).decode('utf-8')
        
        # 构建用户消息（带图片）
        user_content = [
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/png;base64,{img_b64}",
                    "detail": "high",  # 高细节模式，对公式识别更准
                },
            },
            {
                "type": "text",
                "text": self.EXTRACTION_PROMPT,
            },
        ]
        
        # 如果有分类提示，加到prompt里
        if category_hint:
            user_content[1]["text"] = (
                f"这份试卷属于【{category_hint}】章节。\n\n" + 
                self.EXTRACTION_PROMPT
            )
        
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "你是专业的数学试卷OCR和题目提取专家。"},
                    {"role": "user", "content": user_content},
                ],
                max_tokens=4096,
                temperature=0.1,  # 低温度确保稳定输出
            )
            
            raw_text = response.choices[0].message.content or ""
            
            # 解析JSON
            questions = self._parse_vl_response(raw_text, category_hint, page_num)
            
            return VLExtractionResult(
                questions=questions,
                raw_text=raw_text,
            )
            
        except Exception as e:
            logger.error(f"VL模型调用失败 (page {page_num}): {e}")
            return VLExtractionResult(
                errors=[f"第{page_num}页VL调用失败: {str(e)}"],
            )

    async def extract_from_pdf(
        self,
        pdf_path: str,
        answer_pdf_path: Optional[str] = None,
        category: str = "",
        max_pages: int = 50,
    ) -> VLExtractionResult:
        """
        完整流程：PDF → 图片 → VL模型 → 结构化题目列表。
        
        Args:
            pdf_path: 题目PDF路径
            answer_pdf_path: 答案PDF路径（可选，用于补充答案）
            category: 默认分类
            max_pages: 最大处理页数
            
        Returns:
            所有提取到的题目
        """
        all_result = VLExtractionResult()
        
        # Step 1: PDF → 图片
        logger.info(f"开始处理PDF: {pdf_path}")
        pages = self.pdf_to_images(pdf_path)
        
        if not pages:
            all_result.errors.append("PDF无法转换为图片（可能为空或损坏）")
            return all_result
        
        # 限制页数
        pages = pages[:max_pages]
        
        # Step 2: 逐页发送给VL模型
        for page_num, image_bytes in pages:
            logger.info(f"正在分析第 {page_num}/{len(pages)} 页...")
            
            result = await self.extract_from_image(
                image_bytes=image_bytes,
                page_num=page_num,
                category_hint=category,
            )
            
            all_result.questions.extend(result.questions)
            all_result.errors.extend(result.errors)
            
            if result.questions:
                logger.info(f"  第{page_num}页: 提取到 {result.success} 道题")
        
        # Step 3: 如果有答案PDF，尝试匹配答案
        if answer_pdf_path and os.path.exists(answer_pdf_path):
            logger.info("开始匹配答案PDF...")
            await self._match_answers(all_result, answer_pdf_path)
        
        # 分配唯一ID
        file_prefix = self._make_id_prefix(pdf_path)
        for i, q in enumerate(all_result.questions):
            if not q.id:
                q.id = f"{file_prefix}_{i+1:03d}"
            if not q.category and category:
                q.category = category
        
        logger.info(
            f"PDF提取完成! 总计={len(all_result.questions)}, "
            f"成功={all_result.success}, 失败={all_result.failed}"
        )
        
        return all_result

    async def _match_answers(
        self,
        result: VLExtractionResult,
        answer_pdf_path: str,
    ):
        """从答案PDF中提取答案并匹配到对应题目"""
        pages = self.pdf_to_images(answer_pdf_path)
        
        for page_num, image_bytes in pages[:10]:  # 答案通常不超过10页
            img_b64 = base64.b64encode(image_bytes).decode('utf-8')
            
            try:
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {
                            "role": "system",
                            "content": "你是数学答案提取专家。从这张答案图片中提取所有答案。",
                        },
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:image/png;base64,{img_b64}",
                                        "detail": "high",
                                    },
                                },
                                {
                                    "type": "text",
                                    "text": """请提取这张答案页中的所有答案。输出JSON数组：
[
  {"question_number": "第1题", "answer": "..."},
  {"question_number": "第2题", "answer": "..."}
]
只输出JSON。""",
                                },
                            ],
                        },
                    ],
                    max_tokens=2048,
                    temperature=0.1,
                )
                
                raw = response.choices[0].message.content or ""
                
                # 尝试匹配到已有题目
                answers = self._safe_json_parse(raw)
                if isinstance(answers, list):
                    for ans_item in answers:
                        q_num = str(ans_item.get("question_number", ""))
                        ans_val = str(ans_item.get("answer", ""))
                        
                        # 模糊匹配到已有题目
                        for q in result.questions:
                            if q_num in q.content or q_num.replace("第", "").replace("题", "") in q.content:
                                if not q.answer:
                                    q.answer = ans_val
                                break
                
            except Exception as e:
                logger.warning(f"答案匹配失败 (page {page_num}): {e}")

    @staticmethod
    def _parse_vl_response(raw_text: str, category: str, page: int) -> List[VLExtractedQuestion]:
        """解析VL模型的JSON响应为结构化题目列表"""
        questions = []
        
        # 尝试直接解析JSON
        data = VisionPDFParser._safe_json_parse(raw_text)
        
        if isinstance(data, list):
            for item in data:
                if not isinstance(item, dict):
                    continue
                    
                q = VLExtractedQuestion()
                q.content = item.get("content", "")
                q.question_type = item.get("type", "text")
                q.options = item.get("options", [])
                q.answer = item.get("answer", "")
                q.analysis = item.get("analysis", "")
                q.source_page = page
                q.category = category
                
                # 过滤无效题目
                if q.content and len(q.content.strip()) > 5:
                    questions.append(q)
                    
        elif isinstance(data, dict):
            # 单个对象包装为数组
            q = VLExtractedQuestion(
                content=data.get("content", ""),
                question_type=data.get("type", "text"),
                options=data.get("options", []),
                answer=data.get("answer", ""),
                analysis=data.get("analysis", ""),
                source_page=page,
                category=category,
            )
            if q.content and len(q.content.strip()) > 5:
                questions.append(q)
        else:
            # JSON解析失败，尝试从原始文本中手动提取
            questions = VisionPDFParser._fallback_extract(raw_text, category, page)
        
        return questions

    @staticmethod
    def _fallback_extract(text: str, category: str, page: int) -> List[VLExtractedQuestion]:
        """当JSON解析失败时，从纯文本中粗略提取题目"""
        questions = []
        
        # 按常见分隔符分割
        parts = re.split(r'(?=\d+[\.、\s]|(?:第?\d+[\.、\s]?)?(?:题|问))', text)
        
        for part in parts:
            part = part.strip()
            if len(part) < 10:
                continue
            
            # 简单判断是否像一道题
            has_math = bool(re.search(r'[=+\-×÷∫∑∏√∂∞≤≥≠≈]', part))
            has_question_mark = any(m in part for m in ['？', '?', '求', '计算', '证明', '解'])
            
            if has_math or has_question_mark:
                questions.append(VLExtractedQuestion(
                    content=part[:500],  # 截断过长内容
                    question_type="text",
                    source_page=page,
                    category=category,
                ))
        
        return questions

    @staticmethod
    def _safe_json_parse(text: str):
        """安全解析JSON，处理各种格式问题"""
        if not text:
            return None
        
        # 清理markdown代码块标记
        text = text.strip()
        if text.startswith('```'):
            lines = text.split('\n')
            text = '\n'.join(lines[1:] if lines[0].startswith('```') else lines)
            if text.endswith('```'):
                text = text[:-3].strip()
        
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        
        # 尝试找到JSON数组部分
        start = text.find('[')
        end = text.rfind(']')
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                pass
        
        # 尝试找JSON对象
        start = text.find('{')
        end = text.rfind('}')
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                pass
        
        return None

    @staticmethod
    def _make_id_prefix(pdf_path: str) -> str:
        """从文件名生成ID前缀"""
        name = os.path.splitext(os.path.basename(pdf_path))[0]
        # 取前几个字符作为前缀
        clean = re.sub(r'[^\w\u4e00-\u9fff]', '', name)[:6]
        return clean or "Q"


# ==================== 命令行测试 ====================

async def main():
    """命令行测试入口"""
    import argparse
    
    parser = argparse.ArgumentParser(description="视觉模型PDF题目提取器")
    parser.add_argument("pdf", help="题目PDF路径")
    parser.add_argument("--answers", "-a", help="答案PDF路径（可选）")
    parser.add_argument("--category", "-c", default="", help="默认分类")
    parser.add_argument("--pages", "-p", type=int, default=10, help="最大处理页数")
    parser.add_argument("--preview", action="store_help", help="只预览不导入")
    
    args = parser.parse_args()
    
    if not os.path.exists(args.pdf):
        print(f"文件不存在: {args.pdf}")
        return
    
    # 从环境变量读取API配置
    from app.config.settings import settings
    
    parser_obj = VisionPDFParser(
        api_key=settings.LLM_API_KEY,
        api_base=settings.LLM_API_BASE,
    )
    
    print("=" * 60)
    print("视觉模型 PDF 题目提取器 (Vision-PDF Parser)")
    print("=" * 60)
    print(f"题目文件: {os.path.basename(args.pdf)}")
    print(f"答案文件: {args.answers or '(无)'}")
    print(f"分类: {args.category or '(自动推断)'}")
    print(f"最大页数: {args.pages}")
    print(f"模型: {parser_obj.model}")
    print()
    
    result = await parser_obj.extract_from_pdf(
        pdf_path=args.pdf,
        answer_pdf_path=args.answers,
        category=args.category,
        max_pages=args.pages,
    )
    
    # 输出结果
    print("\n" + "=" * 60)
    print(f"提取完成! 成功={result.success} 题, 失败={result.failed}")
    print("=" * 60)
    
    for i, q in enumerate(result.questions):
        print(f"\n--- 第{i+1}题 [第{q.source_page}页] [{q.question_type}] ---")
        print(f"ID: {q.id}")
        print(f"内容: {q.content[:200]}{'...' if len(q.content)>200 else ''}")
        if q.options:
            print(f"选项: {json.dumps(q.options, ensure_ascii=False)}")
        if q.answer:
            print(f"答案: {q.answer}")
        if q.analysis:
            print(f"解析: {q.analysis[:100]}...")
    
    if result.errors:
        print(f"\n错误:")
        for err in result.errors[:5]:
            print(f"  - {err}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
