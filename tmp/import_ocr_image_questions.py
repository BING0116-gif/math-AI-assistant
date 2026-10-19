from __future__ import annotations
import asyncio, hashlib, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.data.database import init_db, close_db
from app.services.question_importer import QuestionImporter

async def main():
    data=json.loads(Path('tmp/ocr_image_pdf.json').read_text(encoding='utf8'))
    rows=[]
    for i,q in enumerate(data.get('questions',[]),1):
        content=str(q.get('content','')).strip()
        if len(content)<12: continue
        h=hashlib.sha256(f'4e068e81320b-cb.pdf:{i}:{content}'.encode()).hexdigest()[:19]
        kind=str(q.get('question_type') or q.get('type') or '综合题')
        if kind in {'choice','选择题'}: kind='选择题'
        elif kind in {'fill','填空题'}: kind='填空题'
        elif kind in {'proof','证明题'}: kind='证明题'
        else: kind='计算题'
        analysis=q.get('analysis') or '扫描试卷经视觉识别，完整解法需依据原图人工复核。建议按定义域、定理条件和计算步骤逐项验证。'
        rows.append({'id':'P'+h,'content':content,'question_type':kind,'options':json.dumps(q.get('options') or [],ensure_ascii=False),'answer':q.get('answer') or '待人工审核','analysis':analysis,'category':'高等数学一','sub_categories':'函数与极限/期末综合','knowledge_points':json.dumps(['高等数学一','期末综合'],ensure_ascii=False),'difficulty':4,'estimated_time':8,'source':'PDF:4e068e81320b-cb.pdf','common_mistakes':json.dumps([{'type':'视觉识别复核','description':'扫描公式或题号可能存在识别偏差。','suggestion':'对照原图核对公式、选项和边界条件。'}],ensure_ascii=False),'answer_spec':json.dumps({'kind':'vision_ocr','verification_status':'needs_human_review'},ensure_ascii=False),'review_status':'draft'})
    await init_db(); result=await QuestionImporter().import_from_dict_list(rows,trusted=False); await close_db()
    Path('tmp/ocr_import_result.json').write_text(json.dumps({'parsed':len(rows),'success':result.success,'failed':result.failed,'errors':result.errors},ensure_ascii=False,indent=2),encoding='utf8')
    print(result.success,result.failed)
asyncio.run(main())
