from __future__ import annotations
import asyncio, json, re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from openai import AsyncOpenAI
from sqlalchemy import select
from app.config.settings import settings
from app.data.database import init_db, close_db, get_db_session
from app.data.models import Question

PROMPT = """你是高等数学一教研员。请只处理给出的题目，严禁编造题干条件。对每题给出可核验的最终答案、简洁但完整的中文推导解析、2-4个知识点和一个具体易错点。若题目文字或公式确实无法辨认，answer 必须写‘待人工审核’，analysis 说明缺失信息。输出严格 JSON 数组，每项字段：id, answer, analysis, knowledge_points(数组), common_mistakes(数组对象 type/description/suggestion), difficulty(1-5)。题目如下：\n"""

def parse_json(text: str):
    text = text.strip().replace("```json", "").replace("```", "")
    m = re.search(r"\[[\s\S]*\]", text)
    return json.loads(m.group(0) if m else text)

async def main():
    await init_db()
    async with get_db_session() as db:
        qs=(await db.execute(select(Question).where(Question.answer.in_(['待人工审核','待补充']), ~Question.source.like('%核心考点%')))).scalars().all()
        items=[{'id':q.id,'source':q.source,'type':q.question_type,'content':q.content} for q in qs]
    client=AsyncOpenAI(api_key=settings.DEEPSEEK_API_KEY,base_url=settings.DEEPSEEK_BASE_URL,timeout=35)
    updates={}
    for start in range(0,len(items),3):
        batch=items[start:start+3]
        try:
            resp=await client.chat.completions.create(model=settings.DEEPSEEK_MODEL,messages=[{'role':'system','content':'你只输出合法 JSON。'},{'role':'user','content':PROMPT+json.dumps(batch,ensure_ascii=False)}],temperature=0.1,max_tokens=7000)
            for item in parse_json(resp.choices[0].message.content or '[]'):
                if item.get('id'): updates[item['id']]=item
            print('batch',start,'of',len(items),'updates',len(updates),flush=True)
        except Exception as exc:
            print('batch_error',start,str(exc),flush=True)
    async with get_db_session() as db:
        qs=(await db.execute(select(Question).where(Question.id.in_(list(updates))))).scalars().all()
        for q in qs:
            u=updates[q.id]
            if u.get('answer') and u['answer'] != '待人工审核': q.answer=str(u['answer'])[:10000]
            if u.get('analysis'): q.analysis=str(u['analysis'])[:30000]
            if isinstance(u.get('knowledge_points'),list): q.knowledge_points=json.dumps(['高等数学一',*u['knowledge_points']],ensure_ascii=False)
            if isinstance(u.get('common_mistakes'),list): q.common_mistakes=u['common_mistakes']
            if isinstance(u.get('difficulty'),int) and 1<=u['difficulty']<=5: q.difficulty=u['difficulty']
            q.ai_provider='deepseek'
            q.answer_spec={'kind':'model_enrichment','verification_status':'needs_human_review'}
        await db.commit()
    Path('tmp/model_enrichment_result.json').write_text(json.dumps({'candidates':len(items),'updated':len(updates)},ensure_ascii=False,indent=2),encoding='utf8')
    await close_db()

asyncio.run(main())
