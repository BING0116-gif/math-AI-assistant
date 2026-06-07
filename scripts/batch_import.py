"""
批量题库导入工具 — 从多个 Excel/CSV 文件导入题目。

用法:
  # 导入单个文件
  python scripts/batch_import.py data/my_questions.xlsx

  # 导入整个目录下的所有 xlsx/csv 文件
  python scripts/batch_import.py data/chapters/

  # 清理之前导入的乱码 PDF 数据
  python scripts/batch_import.py --cleanup-pdf "高数自测题"
"""

import asyncio
import argparse
import glob
import os
import sys
import io

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.data.database import init_db, close_db, get_db_session
from app.data.models import Question
from app.services.question_importer import QuestionImporter
from app.services.vector_store import get_vector_store
from sqlalchemy import text


async def cleanup_pdf_data(source_keyword: str):
    """清理指定来源的 PDF 导入数据（通常是乱码数据）"""
    await init_db()
    
    async with get_db_session() as db:
        # 查找匹配的记录
        result = await db.execute(
            text(f"SELECT id, source, substr(content, 40) as content_preview FROM questions WHERE source LIKE '%{source_keyword}%'")
        )
        rows = result.fetchall()
        
        if not rows:
            print(f"未找到来源包含 '{source_keyword}' 的记录")
            return
        
        print(f"找到 {len(rows)} 条待清理记录:")
        for row in rows:
            print(f"  ID={row[0]} | src={row[1]} | {row[2]}")
        
        # 删除数据库记录
        count = 0
        for row in rows:
            qid = row[0]
            obj = await db.get(Question, qid)
            if obj:
                await db.delete(obj)
                count += 1
        
        await db.commit()
        print(f"\n已从数据库删除 {count} 条记录")
    
    # 同时从向量库中删除对应文档
    try:
        vs = await get_vector_store()
        deleted = 0
        for row in rows:
            qid = row[0]
            try:
                await vs.client.get_or_create_collection("math_questions").delete(where={"id": qid})
                deleted += 1
            except Exception:
                pass
        print(f"已从向量库删除 {deleted} 个文档")
    except Exception as e:
        print(f"向量库清理跳过: {e}")
    
    await close_db()
    print("\n清理完成!")


async def batch_import(file_path: str, category: str = "", default_difficulty: int = 3):
    """批量导入单个文件或目录"""
    await init_db()
    vs = await get_vector_store()
    importer = QuestionImporter(vector_store=vs)
    
    total_success = 0
    total_failed = 0
    
    if os.path.isdir(file_path):
        # 目录模式：导入所有 xlsx/csv 文件
        files = sorted(glob.glob(os.path.join(file_path, "*.xlsx")))
        files += sorted(glob.glob(os.path.join(file_path, "*.csv")))
        
        if not files:
            print(f"目录 {file_path} 中没有找到 .xlsx 或 .csv 文件")
            return
        
        print(f"在目录 {file_path} 中发现 {len(files)} 个文件:\n")
        
        for fpath in files:
            fname = os.path.basename(fpath)
            print(f"{'='*50}")
            print(f"导入: {fname}")
            
            if fpath.endswith('.xlsx'):
                result = await importer.import_from_excel(fpath)
            else:
                result = await importer.import_from_csv(fpath)
            
            print(f"  结果: 成功={result.success}, 失败={result.failed}")
            if result.errors:
                for err in result.errors[:3]:
                    print(f"  错误: {err}")
            
            total_success += result.success
            total_failed += result.failed
    
    elif os.path.isfile(file_path):
        # 单文件模式
        fname = os.path.basename(file_path)
        print(f"导入: {fname}")
        
        if file_path.endswith('.xlsx'):
            result = await importer.import_from_excel(file_path)
        elif file_path.endswith('.csv'):
            result = await importer.import_from_csv(file_path)
        else:
            print(f"不支持的文件格式: {fname} (仅支持 .xlsx 和 .csv)")
            return
        
        print(f"\n结果: 总计={result.total}, 成功={result.success}, 失败={result.failed}")
        if result.errors:
            print("\n错误详情:")
            for err in result.errors[:10]:
                print(f"  - {err}")
        
        total_success = result.success
        total_failed = result.failed
        
        if result.imported_ids:
            print(f"\n已导入ID (前5个):")
            for qid in result.imported_ids[:5]:
                print(f"  {qid}")
    else:
        print(f"路径不存在: {file_path}")
        return
    
    # 最终统计
    print(f"\n{'='*50}")
    print(f"批量导入完成! 总成功: {total_success}, 总失败: {total_failed}")
    
    # 显示最终统计
    try:
        stats = await vs.get_collection_stats()
        print(f"向量库: {stats.get('total_documents', '?')} 文档")
    except Exception:
        pass
    
    await close_db()


async def main():
    parser = argparse.ArgumentParser(description="批量题库导入/清理工具")
    parser.add_argument("path", nargs="?", help="Excel/CSV 文件或目录路径")
    parser.add_argument("--category", "-c", default="", help="默认分类")
    parser.add_argument("--difficulty", "-d", type=int, default=3, choices=[1,2,3,4,5])
    parser.add_argument("--cleanup-pdf", nargs="?", const="PDF", help="清理 PDF 来源的乱码数据（可指定关键词）")
    
    args = parser.parse_args()
    
    if args.cleanup_pdf is not None:
        await cleanup_pdf_data(args.cleanup_pdf or "PDF")
    elif args.path:
        await batch_import(args.path, args.category, args.difficulty)
    else:
        parser.print_help()
        print("\n示例:")
        print("  python scripts/batch_import.py data/template_import_questions.csv")
        print("  python scripts/batch_import.py data/chapters/")
        print("  python scripts/batch_import.py --cleanup-pdf")


if __name__ == "__main__":
    asyncio.run(main())
