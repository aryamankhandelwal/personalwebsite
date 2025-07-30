import os
from fastapi import FastAPI, Depends, HTTPException, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from dotenv import load_dotenv
from pydantic import BaseModel
from models import Base, Question, Reply
from database import engine, get_db
from typing import Optional
from datetime import datetime

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '.env'))

ADMIN_TOKEN = os.getenv('ADMIN_TOKEN')

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

@app.on_event("startup")
async def on_startup():
    await init_db()

async def admin_auth(x_admin_token: str = Header(None)):
    if x_admin_token != ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")

class QuestionCreate(BaseModel):
    text: str
    nickname: Optional[str] = None

class QuestionOut(BaseModel):
    id: int
    text: str
    nickname: Optional[str] = None
    timestamp: datetime  # Accept datetime, not str
    status: str
    responder_answer: Optional[str] = None
    reply_count: int
    class Config:
        from_attributes = True

class ReplyCreate(BaseModel):
    reply_text: str

class ReplyOut(BaseModel):
    id: int
    question_id: int
    reply_text: str
    timestamp: datetime  # Accept datetime, not str
    class Config:
        from_attributes = True

class AnswerCreate(BaseModel):
    responder_answer: str

class QuestionEdit(BaseModel):
    text: str

class ReplyEdit(BaseModel):
    reply_text: str

class AdminReplyOut(BaseModel):
    id: int
    reply_id: int
    admin_answer: str
    timestamp: datetime
    edited: int
    class Config:
        from_attributes = True

class AdminReplyCreate(BaseModel):
    admin_answer: str

@app.post("/questions", response_model=QuestionOut)
async def create_question(q: QuestionCreate, db: AsyncSession = Depends(get_db)):
    question = Question(text=q.text, nickname=q.nickname)
    db.add(question)
    await db.commit()
    await db.refresh(question)
    return question

@app.post("/questions/{question_id}/replies", response_model=ReplyOut)
async def create_reply(question_id: int, reply: ReplyCreate, db: AsyncSession = Depends(get_db)):
    question = await db.get(Question, question_id)
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")
    
    reply_obj = Reply(question_id=question_id, reply_text=reply.reply_text)
    db.add(reply_obj)
    
    # Update reply count
    question.reply_count += 1
    
    await db.commit()
    await db.refresh(reply_obj)
    return reply_obj

@app.get("/questions", response_model=list[QuestionOut])
async def list_questions(skip: int = 0, limit: int = 10, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Question).order_by(Question.timestamp.desc()).offset(skip).limit(limit)
    )
    return result.scalars().all()

@app.get("/questions/{question_id}")
async def get_question(question_id: int, db: AsyncSession = Depends(get_db)):
    try:
        question = await db.get(Question, question_id)
        if not question:
            raise HTTPException(status_code=404, detail="Question not found")
        # Fetch replies
        result = await db.execute(select(Reply).where(Reply.question_id == question_id).order_by(Reply.timestamp))
        replies = result.scalars().all()
        # Fetch admin replies for each reply
        from models import AdminReply
        reply_ids = [r.id for r in replies]
        admin_replies = {}
        if reply_ids:
            admin_results = await db.execute(select(AdminReply).where(AdminReply.reply_id.in_(reply_ids)))
            for ar in admin_results.scalars().all():
                admin_replies[ar.reply_id] = AdminReplyOut.model_validate(ar).dict()
        return {
            "question": QuestionOut.model_validate(question),
            "replies": [dict(ReplyOut.model_validate(r).dict(), admin_reply=admin_replies.get(r.id)) for r in replies],
        }
    except Exception as e:
        raise 

@app.post("/questions/{question_id}/answer", dependencies=[Depends(admin_auth)])
async def answer_question(question_id: int, answer: AnswerCreate, db: AsyncSession = Depends(get_db)):
    question = await db.get(Question, question_id)
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")
    question.responder_answer = answer.responder_answer
    question.status = "answered"
    await db.commit()
    await db.refresh(question)
    return {"status": "ok"}

@app.patch("/questions/{question_id}")
async def edit_question(question_id: int, q: QuestionEdit, db: AsyncSession = Depends(get_db)):
    question = await db.get(Question, question_id)
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")
    question.text = q.text
    question.edited = 1
    await db.commit()
    await db.refresh(question)
    return QuestionOut.model_validate(question)

@app.patch("/replies/{reply_id}")
async def edit_reply(reply_id: int, r: ReplyEdit, db: AsyncSession = Depends(get_db)):
    reply = await db.get(Reply, reply_id)
    if not reply:
        raise HTTPException(status_code=404, detail="Reply not found")
    reply.reply_text = r.reply_text
    reply.edited = 1
    await db.commit()
    await db.refresh(reply)
    return ReplyOut.model_validate(reply)

@app.post("/replies/{reply_id}/admin_answer", dependencies=[Depends(admin_auth)])
async def admin_answer_reply(reply_id: int, a: AdminReplyCreate, db: AsyncSession = Depends(get_db)):
    reply = await db.get(Reply, reply_id)
    if not reply:
        raise HTTPException(status_code=404, detail="Reply not found")
    # Only one admin reply per reply
    from models import AdminReply
    existing = await db.execute(select(AdminReply).where(AdminReply.reply_id == reply_id))
    existing_admin = existing.scalars().first()
    if existing_admin:
        existing_admin.admin_answer = a.admin_answer
        existing_admin.edited = 1
        await db.commit()
        await db.refresh(existing_admin)
        return AdminReplyOut.model_validate(existing_admin)
    admin_reply = AdminReply(reply_id=reply_id, admin_answer=a.admin_answer)
    db.add(admin_reply)
    await db.commit()
    await db.refresh(admin_reply)
    return AdminReplyOut.model_validate(admin_reply)

@app.delete("/questions/{question_id}", dependencies=[Depends(admin_auth)])
async def delete_question(question_id: int, db: AsyncSession = Depends(get_db)):
    question = await db.get(Question, question_id)
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")
    await db.delete(question)
    await db.commit()
    return {"status": "deleted"} 

@app.get("/ping", include_in_schema=False)
def ping():
    """Health check endpoint for Render wake-up pings."""
    return JSONResponse({"status": "ok", "message": "pong"})

@app.get("/", include_in_schema=False)
def root():
    # Root GET endpoint for Render and browser requests
    return JSONResponse({"status": "ok", "message": "Ask Me Anything API is running."})

@app.head("/", include_in_schema=False)
def root_head():
    # Prevent 404 for HEAD / requests (Render health checks)
    return JSONResponse({"status": "ok"}) 