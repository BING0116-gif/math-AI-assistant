"""
视觉模型 PDF 题库批量导入工具 — 用千问VL"看"PDF提取数学题目并导入系统。

用法:
  # 导入单个章节
  python scripts/vl_import.py "第二章自测题2010-1-20.pdf" "第二章答案.pdf" --category "导数"

  # 批量导入整个目录（自动匹配题目和答案PDF）
  python scripts/vl_import.py "高数题＋答案pdf/" --batch

  # 预览模式（只显示提取结果，不导入）
  python scripts/vl_import.py "第二章自测题2010-1-20.pdf" --preview

  # 指定最大页数和并发数
  python scripts/vl_import.py "第二章.pdf" --pages 20 --concurrent 3
"""

import asyncio
import argparse
import glob
import json
import logging
import os
import re
import sys

if sys.platform == 'win32':
    os.environ.setdefault('PYTHONIOENCODING', 'utf-8')

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.data.database import init_db, close_db, get_db_session
from app.data.models import Question
from app.services.question_importer import QuestionImporter
from app.services.vector_store import get_vector_store
from app.services.vision_pdf_parser import VisionPDFParser, VLExtractedQuestion, VLExtractionResult
from app.config.settings import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)


# 章节名称映射（从文件名推断分类）
CHAPTER_MAP = {
    "第一章": "函数与极限",
    "第二章": "导数与微分",
    "第三章": "中值定理与导数的应用",
    "第四章": "不定积分",
    "第五章": "定积分",
    "第六章": "多元函数",
    "第七章": "无穷级数",
    "第八章": "微分方程",
}


def infer_category_from_filename(filename: str) -> str:
    """从文件名推断章节分类"""
    for key, category in CHAPTER_MAP.items():
        if key in filename:
            return category
    return ""


def find_answer_pdf(question_pdf: str, directory: str) -> str:
    """在目录中查找对应的答案PDF"""
    qname = os.path.splitext(os.path.basename(question_pdf))[0]
    
    # 尝试多种匹配模式
    patterns = [
        f"*{qname}*答案*",
        f"*{qname}*提示*",
        f"*{qname.split('第')[0] if '第' in qname else qname[:4]}*答案*",  # 用章节号匹配
    ]
    
    for pattern in patterns:
        matches = sorted(glob.glob(os.path.join(directory, pattern + ".pdf")))
        if matches:
            # 排除自身
            for m in matches:
                if os.path.basename(m) != os.path.basename(question_pdf):
                    return m
    
    return ""


async def vl_extract_and_import(
    question_pdf: str,
    answer_pdf: str = "",
    category: str = "",
    source: str = "",
    max_pages: int = 50,
    preview_only: bool = False,
) -> dict:
    """
    完整流程：VL提取 → 结构化 → 导入数据库+向量库
    """
    if not category:
        category = infer_category_from_filename(question_pdf)
    if not source:
        source = os.path.splitext(os.path.basename(question_pdf))[0]
    
    print(f"\n{'='*60}")
    print(f"处理: {os.path.basename(question_pdf)}")
    print(f"分类: {category or '(自动)'}")
    print(f"答案: {os.path.basename(answer_pdf) if answer_pdf else '(无)'}")
    print(f"{'='*60}")
    
    # Step 1: VL 提取
    parser = VisionPDFParser(
        api_key=settings.LLM_API_KEY,
        api_base=settings.LLM_API_BASE,
    )
    
    result = await parser.extract_from_pdf(
        pdf_path=question_pdf,
        answer_pdf_path=answer_pdf if answer_pdf else None,
        category=category,
        max_pages=max_pages,
    )
    
    print(f"\n提取结果: {result.success} 道题成功, {result.failed} 个错误")
    
    if preview_only:
        print("\n--- 预览 (前10道) ---")
        for i, q in enumerate(result.questions[:10]):
            print(f"\n[{i+1}] [{q.question_type}] ID={q.id}")
            print(f"    {q.content[:150]}...")
            if q.options:
                print(f"    选项: {json.dumps(q.options, ensure_ascii=False)}")
            if q.answer:
                print(f"    答案: {q.answer}")
        return {"success": result.success, "questions": result.questions}
    
    if result.success == 0:
        print("没有提取到有效题目，跳过导入")
        return {"success": 0, "errors": result.errors}
    
    # Step 2: 转换为导入格式并入库
    await init_db()
    vs = await get_vector_store()
    importer = QuestionImporter(vector_store=vs)
    
    # 将 VL 提取的题目转为 importer 能接受的格式
    import_data = []
    for q in result.questions:
        item = {
            "id": q.id,
            "content": q.content,
            "question_type": q.question_type,
            "options": json.dumps(q.options, ensure_ascii=False) if q.options else "[]",
            "answer": q.answer,
            "analysis": q.analysis,
            "category": q.category or category,
            "sub_categories": "",
            "knowledge_points": json.dumps(q.knowledge_points, ensure_ascii=False),
            "difficulty": q.difficulty,
            "estimated_time": _estimate_time(q.question_type),
            "source": source,
            "version": "1.0",
            "tags": "vl-imported",
        }
        import_data.append(item)
    
    # 批量导入
    from app.services.question_importer import ImportResult
    
    try:
        import_result = await importer.import_from_dict_list(
            questions=import_data,
        )
        
        print(f"\n导入完成!")
        print(f"  总计: {len(import_data)}")
        print(f"  成功: {import_result.success}")
        print(f"  失败: {import_result.failed}")
        
        if import_result.errors:
            for err in import_result.errors[:5]:
                print(f"  错误: {err}")
        
        # 显示向量库状态
        try:
            stats = await vs.get_collection_stats()
            print(f"  向量库总计: {stats.get('total_documents', '?')} 文档")
        except Exception:
            pass
        
        await close_db()
        
        return {
            "success": import_result.success,
            "failed": import_result.failed,
            "extracted": result.success,
            "ids": import_result.imported_ids,
        }
        
    except Exception as e:
        logger.error(f"导入失败: {e}", exc_info=True)
        await close_db()
        return {"success": 0, "failed": len(import_data), "error": str(e)}


def _estimate_time(qtype: str) -> int:
    """根据题型估算答题时间(分钟)"""
    times = {
        "选择题": 2,
        "填空题": 3,
        "解答题": 7,
        "计算题": 8,
        "证明题": 10,
        "作图题": 5,
    }
    return times.get(qtype, 5)


async def batch_import_directory(directory: str, max_pages: int = 50):
    """
    批量导入目录下所有PDF。
    自动匹配题目PDF和答案PDF。
    """
    # 找出所有PDF
    all_pdfs = sorted(glob.glob(os.path.join(directory, "*.pdf")))
    
    if not all_pdfs:
        print(f"目录中没有找到PDF文件: {directory}")
        return
    
    print(f"在目录中发现 {len(all_pdfs)} 个PDF文件:")
    for p in all_pdfs:
        print(f"  - {os.path.basename(p)}")
    
    # 分类：题目PDF vs 答案PDF
    question_pdfs = []
    for pdf in all_pdfs:
        name = os.path.basename(pdf).lower()
        # 答案PDF通常包含这些关键词
        is_answer = any(kw in name for kw in ["答案", "提示", "answer", "key"])
        if not is_answer:
            question_pdfs.append(pdf)
    
    print(f"\n识别为题目PDF: {len(question_pdfs)} 个")
    
    # 逐个处理
    total_success = 0
    total_failed = 0
    
    for qpdf in question_pdfs:
        apdf = find_answer_pdf(qpdf, directory)
        
        result = await vl_extract_and_import(
            question_pdf=qpdf,
            answer_pdf=apdf,
            max_pages=max_pages,
        )
        
        total_success += result.get("success", 0)
        total_failed += result.get("failed", 0)
        
        # API限速：每章之间等待几秒
        await asyncio.sleep(2)
    
    print(f"\n{'='*60}")
    print(f"批量导入完成! 总成功: {total_success}, 总失败: {total_failed}")
    print(f"{'='*60}")


async def main():
    parser = argparse.ArgumentParser(
        description="视觉模型 PDF 题库导入工具 — 千问VL识别数学公式",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 导入单章（预览）
  python scripts/vl_import.py "第二章.pdf" --preview
  
  # 导入单章（正式）
  python scripts/vl_import.py "第二章.pdf" "第二章答案.pdf" -c 导数
  
  # 批量导入整个目录
  python scripts/vl_import.py "./高数题/" --batch
""",
    )
    
    parser.add_argument("path", help="题目PDF文件或包含PDF的目录路径")
    parser.add_argument("--answers", "-a", default="", help="答案PDF路径")
    parser.add_argument("--category", "-c", default="", help="默认分类（不指定则从文件名推断）")
    parser.add_argument("--source", "-s", default="", help="来源标记")
    parser.add_argument("--pages", "-p", type=int, default=50, help="每个PDF最大处理页数")
    parser.add_argument("--preview", action="store_true", help="只预览，不导入数据库")
    parser.add_argument("--batch", "-b", action="store_true", help="批量模式：处理目录下所有PDF")
    
    args = parser.parse_args()
    
    if not os.path.exists(args.path):
        print(f"路径不存在: {args.path}")
        return
    
    if args.batch and os.path.isdir(args.path):
        await batch_import_directory(args.path, max_pages=args.pages)
    elif os.path.isfile(args.path):
        await vl_extract_and_import(
            question_pdf=args.path,
            answer_pdf=args.answers,
            category=args.category,
            source=args.source,
            max_pages=args.pages,
            preview_only=args.preview,
        )
    else:
        parser.print_help()


if __name__ == "__main__":
    asyncio.run(main())
