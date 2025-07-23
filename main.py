import os
from fastapi import FastAPI, Depends, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from dotenv import load_dotenv
from pydantic import BaseModel
from models import Base, Question, Reply
from database import engine, get_db

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '.env'))

ADMIN_TOKEN = os.getenv('ADMIN_TOKEN')

app = FastAPI()

@app.get("/")
def root():
    return {"status": "ok", "message": "Ask Me Anything API is running."}

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
    nickname: str = None

class QuestionOut(BaseModel):
    id: int
    text: str
    nickname: str = None
    timestamp: str
    status: str
    responder_answer: str = None
    reply_count: int
    class Config:
        from_attributes = True

class ReplyCreate(BaseModel):
    reply_text: str

class ReplyOut(BaseModel):
    id: int
    question_id: int
    reply_text: str
    timestamp: str
    class Config:
        from_attributes = True

class AnswerCreate(BaseModel):
    responder_answer: str

@app.post("/questions", response_model=QuestionOut)
async def create_question(q: QuestionCreate, db: AsyncSession = Depends(get_db)):
    question = Question(text=q.text, nickname=q.nickname)
    db.add(question)
    await db.commit()
    await db.refresh(question)
    return question

@app.get("/questions", response_model=list[QuestionOut])
async def list_questions(skip: int = 0, limit: int = 10, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Question).order_by(Question.timestamp.desc()).offset(skip).limit(limit)
    )
    return result.scalars().all()

@app.get("/questions/{question_id}")
async def get_question(question_id: int, db: AsyncSession = Depends(get_db)):
    question = await db.get(Question, question_id)
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")
    return question

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

@app.post("/questions/{question_id}/reply", response_model=ReplyOut)
async def add_reply(question_id: int, reply: ReplyCreate, db: AsyncSession = Depends(get_db)):
    question = await db.get(Question, question_id)
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")
    new_reply = Reply(question_id=question_id, reply_text=reply.reply_text)
    db.add(new_reply)
    question.reply_count += 1
    await db.commit()
    await db.refresh(new_reply)
    return new_reply

@app.delete("/questions/{question_id}", dependencies=[Depends(admin_auth)])
async def delete_question(question_id: int, db: AsyncSession = Depends(get_db)):
    question = await db.get(Question, question_id)
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")
    await db.delete(question)
    await db.commit()
    return {"status": "deleted"}

@app.delete("/replies/{reply_id}", dependencies=[Depends(admin_auth)])
async def delete_reply(reply_id: int, db: AsyncSession = Depends(get_db)):
    reply = await db.get(Reply, reply_id)
    if not reply:
        raise HTTPException(status_code=404, detail="Reply not found")
    await db.delete(reply)
    await db.commit()
    return {"status": "deleted"} 