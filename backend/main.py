"""FastAPI app for Ask Me Anything experience."""
from typing import Optional, List
from datetime import datetime
import os
from fastapi import FastAPI, Depends, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from dotenv import load_dotenv
from pydantic import BaseModel
from backend.models import Base, Question, Reply
from backend.database import engine, get_db

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '.env'))

ADMIN_TOKEN = os.getenv('ADMIN_TOKEN')

app = FastAPI()

@app.get("/")
def root():
    """Root endpoint for health check."""
    return {"status": "ok", "message": "Ask Me Anything API is running."}

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

async def init_db():
    """Initialize the database tables."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

@app.on_event("startup")
async def on_startup():
    """Run on app startup."""
    await init_db()

async def admin_auth(x_admin_token: Optional[str] = Header(None)):
    """Dependency to check admin token in header."""
    if x_admin_token != ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")

class QuestionCreate(BaseModel):
    """Schema for creating a question."""
    text: str
    nickname: Optional[str] = None

class QuestionOut(BaseModel):
    """Schema for outputting a question."""
    id: int
    text: str
    nickname: Optional[str]
    timestamp: datetime
    status: str
    responder_answer: Optional[str]
    reply_count: int
    class Config:
        from_attributes = True

class ReplyCreate(BaseModel):
    """Schema for creating a reply."""
    reply_text: str

class ReplyOut(BaseModel):
    """Schema for outputting a reply."""
    id: int
    question_id: int
    reply_text: str
    timestamp: datetime
    class Config:
        from_attributes = True

class AnswerCreate(BaseModel):
    """Schema for admin answering a question."""
    responder_answer: str

@app.post("/questions", response_model=QuestionOut)
async def create_question(q: QuestionCreate, db: AsyncSession = Depends(get_db)):
    """Create a new question."""
    question = Question(text=q.text, nickname=q.nickname)
    db.add(question)
    await db.commit()
    await db.refresh(question)
    return question

@app.get("/questions", response_model=List[QuestionOut])
async def list_questions(skip: int = 0, limit: int = 10, db: AsyncSession = Depends(get_db)):
    """List all questions with pagination."""
    result = await db.execute(
        select(Question).order_by(Question.timestamp.desc()).offset(skip).limit(limit)
    )
    return result.scalars().all()

@app.get("/questions/{question_id}")
async def get_question(question_id: int, db: AsyncSession = Depends(get_db)):
    """Get a question and its replies."""
    q = await db.get(Question, question_id)
    if not q:
        raise HTTPException(404, "Question not found")
    replies = (
        await db.execute(
            select(Reply).where(Reply.question_id == question_id).order_by(Reply.timestamp)
        )
    ).scalars().all()
    return {
        "question": QuestionOut.model_validate(q),
        "replies": [ReplyOut.model_validate(r) for r in replies],
    }

@app.post("/questions/{question_id}/answer", dependencies=[Depends(admin_auth)])
async def answer_question(question_id: int, answer: AnswerCreate, db: AsyncSession = Depends(get_db)):
    """Admin: answer a question."""
    q = await db.get(Question, question_id)
    if not q:
        raise HTTPException(404, "Question not found")
    q.responder_answer = answer.responder_answer
    q.status = "answered"
    await db.commit()
    return {"success": True}

@app.post("/questions/{question_id}/reply", response_model=ReplyOut)
async def add_reply(question_id: int, reply: ReplyCreate, db: AsyncSession = Depends(get_db)):
    """Add a reply to a question."""
    q = await db.get(Question, question_id)
    if not q:
        raise HTTPException(404, "Question not found")
    r = Reply(question_id=question_id, reply_text=reply.reply_text)
    db.add(r)
    q.reply_count += 1
    await db.commit()
    await db.refresh(r)
    return r

@app.delete("/questions/{question_id}", dependencies=[Depends(admin_auth)])
async def delete_question(question_id: int, db: AsyncSession = Depends(get_db)):
    """Admin: delete a question and its replies."""
    q = await db.get(Question, question_id)
    if not q:
        raise HTTPException(404, "Question not found")
    await db.delete(q)
    await db.commit()
    return {"success": True}

@app.delete("/replies/{reply_id}", dependencies=[Depends(admin_auth)])
async def delete_reply(reply_id: int, db: AsyncSession = Depends(get_db)):
    """Admin: delete a reply."""
    r = await db.get(Reply, reply_id)
    if not r:
        raise HTTPException(404, "Reply not found")
    q = await db.get(Question, r.question_id)
    if q:
        q.reply_count = max(0, q.reply_count - 1)
    await db.delete(r)
    await db.commit()
    return {"success": True} 