"""Student text-answer subjective scoring; evidence only, never mastery mutation."""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from app.api.student_contracts import STUDENT_API_RESPONSES, StudentOperationEnvelope
from app.services.subjective_scoring_service import score_text_answer

router = APIRouter(prefix="/api/subjective-evaluations", tags=["主观题评分"])

class ScoreRequest(BaseModel):
    question_id: str = Field(min_length=1, max_length=20)
    answer: str = Field(min_length=1, max_length=20000)
    idempotency_key: str = Field(min_length=8, max_length=128)
    attempt_id: str | None = Field(default=None, max_length=36)

@router.post("/score", response_model=StudentOperationEnvelope, responses=STUDENT_API_RESPONSES)
async def score(request: Request, body: ScoreRequest):
    user_id = getattr(request.state, "user_id", None)
    if not user_id: raise HTTPException(401, detail={"code":"UNAUTHENTICATED", "message":"请先登录"})
    try:
        return {"code": 0, "data": await score_text_answer(user_id=str(user_id), **body.model_dump())}
    except LookupError as exc: raise HTTPException(404, detail={"code":"QUESTION_NOT_FOUND", "message":str(exc)})
    except ValueError as exc: raise HTTPException(409, detail={"code":"SCORING_CONFLICT", "message":str(exc)})
