import asyncio,glob,os,json,hashlib,sys,re
sys.path.insert(0,os.getcwd())
from app.services.pdf_question_parser import PDFQuestionParser
root=r'C:\Users\HUAWEI\Desktop\高数题＋答案pdf'
files=glob.glob(root+r'\*.pdf'); answers=[p for p in files if '答案' in os.path.basename(p) or '提示' in os.path.basename(p)]; questions=[p for p in files if p not in answers]
chapters=[('第一章','函数与极限'),('第二章','导数与微分'),('第三章','中值定理与导数的应用'),('第四章','不定积分'),('第五章','定积分'),('第六章','多元函数'),('第七章','无穷级数'),('第八章','微分方程'),('第九章','无穷级数')]
def chapter(name):
 for token,label in chapters:
  if token in name:return label
 return '高等数学一综合'
def mistakes(text):
 pairs=[]
 for k,v in [('极限运算','未先确认极限存在性或等价无穷小条件'),('导数','混淆导数定义、求导法则与几何意义'),('积分','积分上下限、换元或积分常数处理错误'),('级数','忽略收敛条件或判别法适用范围'),('微分方程','初始条件代入或通解结构处理错误'),('偏导','把偏导与全微分、复合函数链式法则混淆')]:
  if k in text:pairs.append({'type':k,'description':v,'suggestion':'先写出适用条件，再逐步核验公式'})
 return pairs or [{'type':'表达与计算','description':'符号、步骤或边界条件可能遗漏','suggestion':'保留完整推导并复核最终结论'}]
def difficulty(q):
 t=q.content
 if q.question_type in ('证明题','解答题'): return 4
 if any(x in t for x in ['\u53c2\u6570','\u65b9\u7a0b','\u8bc1\u660e','\u53c2\u6570']): return 4
 return 3
async def main():
 parser=PDFQuestionParser(default_category='高等数学一')
 rows=[]; stats=[]
 for f in questions:
  name=os.path.basename(f); ar=next((a for a in answers if chapter(os.path.basename(a))==chapter(name) and ('答案' in os.path.basename(a) or '提示' in os.path.basename(a))),None)
  result=await parser.parse(f,ar)
  n=0
  for q in result.questions:
   content=(q.content or '').strip()
   if len(content)<12: continue
   qid='PDF-H1-'+hashlib.sha1((name+'|'+str(q.number)+'|'+content).encode('utf-8','ignore')).hexdigest()[:18]
   kps=[chapter(name)]
   if any(x in content for x in ['极限','lim','趋近']): kps.append('极限与连续')
   if any(x in content for x in ['导数','切线','单调','极值']): kps.append('导数与微分')
   if any(x in content for x in ['积分','∫','定积分','不定积分']): kps.append('积分学')
   if any(x in content for x in ['级数','收敛','幂级数']): kps.append('无穷级数')
   if any(x in content for x in ['微分方程','dy','特征方程']): kps.append('微分方程')
   if any(x in content for x in ['偏导','二重积分','多元']): kps.append('多元函数')
   rows.append({'id':qid,'content':content,'question_type':q.question_type,'options':q.options,'answer':q.answer or '待人工核验','analysis':q.analysis or '待人工补充或复核','category':'高等数学一','sub_categories':chapter(name),'knowledge_points':list(dict.fromkeys(kps)),'difficulty':difficulty(q),'estimated_time':{'选择题':3,'填空题':4,'计算题':8,'证明题':12,'解答题':10}.get(q.question_type,6),'source':'本地PDF：'+name,'common_mistakes':mistakes(content),'answer_spec':{'kind':'choice' if q.question_type=='选择题' else 'text','verification_status':'needs_human_review'},'review_status':'draft','needs_review':True,'source_file':name,'source_question_number':q.number})
  stats.append({'file':name,'answer_file':os.path.basename(ar) if ar else None,'parser_success':result.success,'parsed':result.total_questions,'candidates':sum(1 for r in rows if r['source_file']==name),'warnings':result.warnings,'errors':result.errors})
 open('tmp/question_import_candidates.json','w',encoding='utf-8').write(json.dumps({'schema_version':'h1-pdf-candidates-v1','status':'draft_only','stats':stats,'questions':rows},ensure_ascii=False,indent=2))
 print(json.dumps({'files':len(questions),'candidates':len(rows),'stats':stats},ensure_ascii=False,indent=2))
asyncio.run(main())
