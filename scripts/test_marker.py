"""测试 Marker 对数学PDF的提取效果"""
import sys
import os
import io

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

pdf_path = r"C:\Users\HUAWEI\Desktop\高数题＋答案pdf\第二章自测题2010-1-20.pdf"

print("=" * 60)
print("Marker PDF -> Markdown 提取测试")
print("=" * 60)
print(f"文件: {os.path.basename(pdf_path)}")
print()

try:
    from marker.converters.pdf import PdfConverter
    from marker.output import text_from_rendered
    
    converter = PdfConverter()
    rendered = converter(pdf_path)
    text, _, images = text_from_rendered(rendered)
    
    print(f"提取成功! 文本长度: {len(text)} 字符")
    print(f"图片数量: {len(images)}")
    print()
    print("--- 前1500字符预览 ---")
    print(text[:1500])
    
except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()
