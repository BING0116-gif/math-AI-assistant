"""
PDF 题库导入脚本 — 从题目PDF和答案PDF导入到系统。

用法:
  # 基本用法（只有题目PDF）
  python scripts/import_pdf.py questions.pdf

  # 题目 + 答案
  python scripts/import_pdf.py questions.pdf answers.pdf

  # 指定分类和难度
  python scripts/import_pdf.py questions.pdf answers.pdf --category "高考数学" --difficulty 3

  # 只预览不导入
  python scripts/import_pdf.py questions.pdf --preview
"""

import asyncio
import argparse
import sys
import os
import io

# Fix Windows console encoding for Unicode math symbols
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.data.database import init_db, close_db
from app.services.question_importer import QuestionImporter
from app.services.vector_store import get_vector_store
from app.services.pdf_question_parser import PDFQuestionParser


async def main():
    parser = argparse.ArgumentParser(description="从PDF导入题库")
    parser.add_argument("question_pdf", help="题目PDF文件路径")
    parser.add_argument("answer_pdf", nargs="?", default=None, help="答案PDF文件路径（可选）")
    parser.add_argument("--category", "-c", default="", help="题目分类（如：导数、积分、高考数学）")
    parser.add_argument("--source", "-s", default="", help="来源名称（如：2024高考真题）")
    parser.add_argument("--difficulty", "-d", type=int, default=3, choices=[1,2,3,4,5],
                        help="默认难度 (1-5, 默认3)")
    parser.add_argument("--preview", "-p", action="store_true", help="只预览解析结果，不导入")

    args = parser.parse_args()

    # 验证文件
    if not os.path.exists(args.question_pdf):
        print(f"[错误] 题目PDF不存在: {args.question_pdf}")
        sys.exit(1)
    if args.answer_pdf and not os.path.exists(args.answer_pdf):
        print(f"[警告] 答案PDF不存在: {args.answer_pdf}，将跳过答案提取")
        args.answer_pdf = None

    print("=" * 60)
    print("PDF 题库导入工具")
    print("=" * 60)
    print(f"题目PDF: {args.question_pdf}")
    if args.answer_pdf:
        print(f"答案PDF: {args.answer_pdf}")
    print(f"分类:   {args.category or '(自动检测)'}")
    print(f"难度:   {args.difficulty}")
    print()

    # 步骤1: 解析PDF
    print("[1/3] 正在解析PDF...")
    pdf_parser = PDFQuestionParser(
        default_difficulty=args.difficulty,
        default_category=args.category or "未分类",
    )
    parse_result = await pdf_parser.parse(
        question_pdf_path=args.question_pdf,
        answer_pdf_path=args.answer_pdf,
    )

    if not parse_result.success:
        print(f"\n[错误] PDF解析失败:")
        for err in parse_result.errors:
            print(f"  - {err}")
        sys.exit(1)

    print(f"  解析成功! 共 {parse_result.total_questions} 道题")
    
    for w in parse_result.warnings:
        print(f"  [警告] {w}")

    # 显示预览
    print(f"\n{'='*60}")
    print(f"题目预览 (前{min(5, len(parse_result.questions))}道):")
    print(f"{'='*60}")

    for idx, q in enumerate(parse_result.questions[:5]):
        print(f"\n--- 第{q.number}题 [{q.question_type}] ---")
        content_preview = q.content[:100] + ("..." if len(q.content) > 100 else "")
        print(f"  内容: {content_preview}")
        if q.options:
            print(f"  选项: {' | '.join(q.options)}")
        if q.answer:
            ans_preview = q.answer[:80] + ("..." if len(q.answer) > 80 else "")
            print(f"  答案: {ans_preview}")
        else:
            print(f"  答案: (待补充)")
        
        # 子题信息
        if q.sub_questions:
            print(f"  子题: {len(q.sub_questions)} 个")

    if len(parse_result.questions) > 5:
        print(f"\n  ... 还有 {len(parse_result.questions)-5} 道题")

    if args.preview:
        print(f"\n[预览模式] 不执行导入。如需导入请去掉 --preview 参数")
        return

    # 步骤2: 初始化数据库和向量库
    print(f"\n[2/3] 正在初始化数据库和向量库...")
    await init_db()
    vs = await get_vector_store()
    importer = QuestionImporter(vector_store=vs)
    print("  数据库就绪 ✓")
    print("  向量库就绪 ✓")

    # 步骤3: 转换并导入
    print(f"\n[3/3] 正在导入到数据库和向量库...")
    import_dicts = pdf_parser.to_import_dicts(
        parse_result,
        category=args.category,
        source_name=args.source,
    )
    
    result = await importer.import_from_dict_list(import_dicts)
    
    print()
    print("=" * 60)
    print("导入完成!")
    print("=" * 60)
    print(f"  总计:     {result.total} 题")
    print(f"  成功:     {result.success} 题")
    print(f"  失败:     {result.failed} 题")
    
    if result.errors:
        print(f"\n  错误详情 (最多显示10条):")
        for err in result.errors[:10]:
            print(f"    ✗ {err}")
    
    if result.success > 0:
        print(f"\n  已导入的题目ID (前5个):")
        for qid in result.imported_ids[:5]:
            print(f"    ✓ {qid}")
        if len(result.imported_ids) > 5:
            print(f"    ... 共 {len(result.imported_ids)} 个")
        
        # 更新向量库统计
        try:
            stats = await vs.get_collection_stats()
            print(f"\n  向量库当前状态: {stats.get('total_documents', '?')} 文档, "
                  f"{stats.get('total_categories', '?')} 分类")
        except Exception as e:
            print(f"  向量库统计获取失败: {e}")

    await close_db()


if __name__ == "__main__":
    asyncio.run(main())
