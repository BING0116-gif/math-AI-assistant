import asyncio,glob,os,json,sys
sys.path.insert(0,os.getcwd())
from app.services.pdf_question_parser import PDFQuestionParser
root=r'C:\Users\HUAWEI\Desktop\高数题＋答案pdf'; files=glob.glob(root+r'\*.pdf'); ans=[p for p in files if '答案' in os.path.basename(p) or '提示' in os.path.basename(p)]; qs=[p for p in files if p not in ans]
async def run():
 p=PDFQuestionParser(default_category='高等数学一'); out=[]
 for f in qs:
  base=os.path.basename(f); ar=next((a for a in ans if base[:2] in os.path.basename(a)[:2]),None)
  try:
   r=await p.parse(f,ar); out.append({'file':base,'answer':os.path.basename(ar) if ar else None,'success':r.success,'questions':r.total_questions,'with_answers':sum(bool(q.answer and q.answer!='待补充') for q in r.questions),'with_analysis':sum(bool(q.analysis) for q in r.questions),'warnings':r.warnings[:2],'errors':r.errors[:2]})
  except Exception as e: out.append({'file':base,'error':str(e)})
 open('tmp/pdf_parse_stats.json','w',encoding='utf-8').write(json.dumps(out,ensure_ascii=False,indent=2))
asyncio.run(run())
