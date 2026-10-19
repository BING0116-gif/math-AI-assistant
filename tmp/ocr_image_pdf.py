import asyncio, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services.vision_pdf_parser import VisionPDFParser

PDF = r"C:\Users\HUAWEI\Desktop\高数题＋答案pdf\4e068e81320b-cb.pdf"

async def main():
    parser = VisionPDFParser()
    pages = parser.pdf_to_images(PDF, dpi=150)
    all_questions, errors = [], []
    for page_num, image in pages:
        try:
            result = await asyncio.wait_for(parser.extract_from_image(image, page_num=page_num, category_hint="高等数学一"), timeout=25)
            all_questions.extend(result.questions); errors.extend(result.errors)
            print('page', page_num, 'questions', len(result.questions), flush=True)
        except Exception as exc:
            errors.append(f'page {page_num}: {exc}')
    payload = {"questions": [q.__dict__ for q in all_questions], "errors": errors}
    Path('tmp/ocr_image_pdf.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf8')
    print('questions', len(all_questions), 'errors', errors, flush=True)

asyncio.run(main())
