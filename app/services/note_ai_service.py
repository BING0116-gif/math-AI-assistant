"""Read-only handwritten-note recognition pipeline."""
from datetime import datetime, timezone
from typing import Protocol
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from app.data.database import get_db_session
from app.data.models import NoteAiRun, NotePage, StudyNote
from app.services.note_service import get_current_revision, NoteServiceError

class KnowledgeCandidate(BaseModel):
 model_config=ConfigDict(extra="forbid")
 knowledge_point_code:str=Field(min_length=1,max_length=100); confidence:float=Field(ge=0,le=1); reason:str=Field(default="",max_length=500)
class Recognition(BaseModel):
 model_config=ConfigDict(extra="forbid")
 title:str=Field(max_length=200); summary:str=Field(max_length=2000); recognized_text:str=Field(max_length=20000); latex_blocks:list[str]=Field(default_factory=list,max_length=100); tags:list[str]=Field(default_factory=list,max_length=20)
 knowledge_candidates:list[KnowledgeCandidate]=Field(default_factory=list,max_length=50)
class Provider(Protocol):
 async def recognize(self,payload:dict)->dict: ...
class AiError(Exception): pass
def data(run,page_revision): return {"run_id":run.id,"page_id":run.page_id,"source_revision":run.source_revision,"status":"stale" if run.status=="needs_review" and run.source_revision!=page_revision else run.status,"model":run.model,"prompt_version":run.prompt_version,"result":run.result,"error":run.error,"attempt_no":run.attempt_no}
async def create_run(user,note,page,key,model="qwen-vl-plus",prompt_version="v1"):
 async with get_db_session() as db:
  p=await db.scalar(select(NotePage).join(StudyNote).where(NotePage.id==page,NotePage.note_id==note,NotePage.user_id==user,StudyNote.status=="active"))
  if not p: raise NoteServiceError("NOTE_NOT_FOUND","笔记页面不存在")
  old=await db.scalar(select(NoteAiRun).where(NoteAiRun.user_id==user,NoteAiRun.idempotency_key==key))
  if old:return data(old,p.current_revision)
  r=NoteAiRun(note_id=note,page_id=page,user_id=user,source_revision=p.current_revision,model=model,prompt_version=prompt_version,idempotency_key=key);db.add(r);await db.flush();return data(r,p.current_revision)
async def execute_run(user,note,run_id,provider):
 async with get_db_session() as db:
  r=await db.scalar(select(NoteAiRun).where(NoteAiRun.id==run_id,NoteAiRun.user_id==user,NoteAiRun.note_id==note))
  if not r: raise NoteServiceError("NOTE_NOT_FOUND","AI 任务不存在")
  r.status="running";r.attempt_no+=1;await db.flush(); page_id=r.page_id;rev=r.source_revision
 try:
  source=await get_current_revision(user,note,page_id)
  if source["current_revision"]!=rev: raise AiError("source revision is stale")
  parsed=Recognition.model_validate(await provider.recognize(source["stroke_payload"]))
  async with get_db_session() as db:
   r=await db.get(NoteAiRun,run_id);r.status="needs_review";r.result=parsed.model_dump();r.error=None;r.completed_at=datetime.now(timezone.utc)
  from app.services.note_knowledge_service import materialize_ai_suggestions
  await materialize_ai_suggestions(user,note,run_id,parsed.model_dump()["knowledge_candidates"])
  async with get_db_session() as db:
   r=await db.get(NoteAiRun,run_id);return data(r,rev)
 except Exception as exc:
  async with get_db_session() as db:
   r=await db.get(NoteAiRun,run_id);r.status="failed";r.error=str(exc)[:500];r.completed_at=datetime.now(timezone.utc);return data(r,rev)
async def get_run(user,note,run_id):
 async with get_db_session() as db:
  r=await db.scalar(select(NoteAiRun).where(NoteAiRun.id==run_id,NoteAiRun.user_id==user,NoteAiRun.note_id==note));p=await db.get(NotePage,r.page_id) if r else None
  if not r or not p: raise NoteServiceError("NOTE_NOT_FOUND","AI 任务不存在")
  return data(r,p.current_revision)
