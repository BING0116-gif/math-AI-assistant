"""对比 pdfplumber vs PyMuPDF 对数学PDF的提取效果"""
import sys
import os
import io

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

sys.path.insert(0, '.')

pdf_path = r"C:\Users\HUAWEI\Desktop\高数题＋答案pdf\第二章自测题2010-1-20.pdf"

print("=" * 60)
print("PDF 文本提取对比: pdfplumber vs PyMuPDF")
print("=" * 60)
print(f"文件: {os.path.basename(pdf_path)}")
print()

# --- pdfplumber ---
print("--- pdfplumber 提取 (前500字符) ---")
try:
    import pdfplumber
    with pdfplumber.open(pdf_path) as pdf:
        text_plumber = ""
        for page in pdf.pages[:2]:
            t = page.extract_text() or ""
            if t.strip():
                text_plumber += t + "\n"
        print(text_plumber[:500])
except Exception as e:
    print(f"ERROR: {e}")

print()
print("=" * 60)

# --- PyMuPDF (fitz) ---
print("\n--- PyMuPDF (fitz) 提取 (前500字符) ---")
try:
    import fitz
    doc = fitz.open(pdf_path)
    text_fitz = ""
    for page in doc[:2]:
        t = page.get_text("text") or ""
        if t.strip():
            text_fitz += t + "\n"
    doc.close()
    print(text_fitz[:500])
except Exception as e:
    print(f"ERROR: {e}")
