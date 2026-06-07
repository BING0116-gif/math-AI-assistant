"""直接运行VL导入第二章"""
import asyncio
import sys
import os

# 设置控制台编码（不替换stdout对象）
if sys.platform == 'win32':
    os.environ.setdefault('PYTHONIOENCODING', 'utf-8')

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.vl_import import vl_extract_and_import

BASE = r"C:\Users\HUAWEI\Desktop\高数题＋答案pdf"

async def main():
    print("=" * 60)
    print("视觉模型 PDF 导入 - 第二章 导数与微分")
    print("=" * 60)
    
    result = await vl_extract_and_import(
        question_pdf=os.path.join(BASE, "第二章自测题2010-1-20.pdf"),
        answer_pdf=os.path.join(BASE, "第二章导数与微分自测题A答案与提示.pdf"),
        category="导数",
        source="高数-第二章-VL",
        max_pages=50,
        preview_only=False,
    )
    
    print(f"\n{'='*60}")
    print(f"最终结果: 成功={result.get('success', 0)}, 失败={result.get('failed', 0)}")
    print(f"{'='*60}")

if __name__ == "__main__":
    asyncio.run(main())
