import os
from fastapi import FastAPI, Depends, Form, HTTPException, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from dotenv import load_dotenv
from pydantic import BaseModel
from models import Base, Question, Reply, LiveTweet, TrackerCompany
from database import engine, get_db
from typing import Optional
from datetime import date, datetime

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '.env'))
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), 'backend', '.env'))

ADMIN_TOKEN = os.getenv('ADMIN_TOKEN')
if not ADMIN_TOKEN:
    raise RuntimeError("ADMIN_TOKEN environment variable is not set.")

TRACKER_SECTORS = ['Fintech', 'Deep Tech', 'Sports & Media', 'Others']
SESSION_MAX_AGE = 7 * 24 * 60 * 60  # 7 days

templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), 'templates'))

app = FastAPI()

app.add_middleware(
    SessionMiddleware,
    secret_key=ADMIN_TOKEN,
    max_age=SESSION_MAX_AGE,
    same_site="lax",
    https_only=False,  # set True behind HTTPS in prod; cookies work over http for local dev
    session_cookie="admin_session",
)

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

class LiveTweetCreate(BaseModel):
    content: str

class LiveTweetOut(BaseModel):
    id: int
    content: str
    created_at: datetime
    class Config:
        from_attributes = True

class TrackerCompanyOut(BaseModel):
    id: int
    name: str
    description: str
    alpha: Optional[str] = None
    founders: Optional[str] = None
    stage: Optional[str] = None
    notable_investors: Optional[str] = None
    website: Optional[str] = None
    sector: str
    region: Optional[str] = None
    is_featured: bool
    is_archived: bool
    date_added: date
    class Config:
        from_attributes = True

def require_admin_session(request: Request):
    if not request.session.get("authed"):
        raise HTTPException(status_code=401, detail="Not authenticated")

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

@app.delete("/replies/{reply_id}", dependencies=[Depends(admin_auth)])
async def delete_reply(reply_id: int, db: AsyncSession = Depends(get_db)):
    reply = await db.get(Reply, reply_id)
    if not reply:
        raise HTTPException(status_code=404, detail="Reply not found")
    
    # Update reply count on the question
    question = await db.get(Question, reply.question_id)
    if question:
        question.reply_count = max(0, question.reply_count - 1)
    
    await db.delete(reply)
    await db.commit()
    return {"status": "deleted"} 

@app.post("/livetweets", response_model=LiveTweetOut, dependencies=[Depends(admin_auth)])
async def create_livetweet(lt: LiveTweetCreate, db: AsyncSession = Depends(get_db)):
    tweet = LiveTweet(content=lt.content)
    db.add(tweet)
    await db.commit()
    await db.refresh(tweet)
    return tweet

@app.get("/livetweets", response_model=list[LiveTweetOut])
async def list_livetweets(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(LiveTweet).order_by(LiveTweet.created_at.desc()))
    return result.scalars().all()

@app.delete("/livetweets/{tweet_id}", dependencies=[Depends(admin_auth)])
async def delete_livetweet(tweet_id: int, db: AsyncSession = Depends(get_db)):
    tweet = await db.get(LiveTweet, tweet_id)
    if not tweet:
        raise HTTPException(status_code=404, detail="Not found")
    await db.delete(tweet)
    await db.commit()
    return {"status": "deleted"}

@app.get("/tracker_companies", response_model=list[TrackerCompanyOut])
async def list_tracker_companies(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(TrackerCompany).order_by(
            TrackerCompany.sector,
            TrackerCompany.is_featured.desc(),
            TrackerCompany.date_added.desc(),
        )
    )
    return result.scalars().all()


# --- Admin (cookie-protected) ---

@app.get("/admin", include_in_schema=False)
async def admin_root(request: Request, db: AsyncSession = Depends(get_db)):
    if not request.session.get("authed"):
        return templates.TemplateResponse(
            request, "admin_login.html", {"error": None}
        )

    result = await db.execute(
        select(TrackerCompany).order_by(
            TrackerCompany.is_featured.desc(),
            TrackerCompany.date_added.desc(),
            TrackerCompany.id.desc(),
        )
    )
    companies = result.scalars().all()

    active_by_sector = {s: [] for s in TRACKER_SECTORS}
    archived_companies = []
    for c in companies:
        if c.is_archived:
            archived_companies.append(c)
        elif c.sector in active_by_sector:
            active_by_sector[c.sector].append(c)
        else:
            # Companies whose sector got renamed/removed: surface them under "Others"
            active_by_sector.setdefault('Others', []).append(c)

    banner = None
    ok = request.query_params.get("ok")
    if ok == "created":
        banner = "Company added."
    elif ok == "updated":
        banner = "Company updated."
    elif ok == "featured":
        banner = "Featured updated."
    elif ok == "archived":
        banner = "Company archived."
    elif ok == "tweeted":
        banner = "Live tweet posted."

    return templates.TemplateResponse(
        request,
        "admin_dashboard.html",
        {
            "sectors": TRACKER_SECTORS,
            "active_by_sector": active_by_sector,
            "archived_companies": archived_companies,
            "banner": banner,
        },
    )


@app.post("/admin/livetweets", include_in_schema=False)
async def admin_post_livetweet(request: Request, content: str = Form(...), db: AsyncSession = Depends(get_db)):
    if not request.session.get("authed"):
        return RedirectResponse(url="/admin", status_code=303)
    tweet = LiveTweet(content=content.strip())
    db.add(tweet)
    await db.commit()
    return RedirectResponse(url="/admin?ok=tweeted", status_code=303)


@app.post("/admin/login", include_in_schema=False)
async def admin_login(request: Request, password: str = Form(...)):
    if password != ADMIN_TOKEN:
        return templates.TemplateResponse(
            request,
            "admin_login.html",
            {"error": "Incorrect password."},
            status_code=401,
        )
    request.session["authed"] = True
    return RedirectResponse(url="/admin", status_code=303)


@app.post("/admin/logout", include_in_schema=False)
async def admin_logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/admin", status_code=303)


@app.post("/admin/tracker/companies", include_in_schema=False)
async def admin_create_company(
    request: Request,
    name: str = Form(...),
    description: str = Form(...),
    sector: str = Form(...),
    alpha: str = Form(""),
    founders: str = Form(""),
    stage: str = Form(""),
    notable_investors: str = Form(""),
    region: str = Form(""),
    website: str = Form(""),
    is_featured: Optional[str] = Form(None),
    is_archived: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin_session),
):
    if sector not in TRACKER_SECTORS:
        raise HTTPException(status_code=400, detail=f"Invalid sector: {sector}")

    featured = bool(is_featured)
    archived = bool(is_archived)
    # An archived company should never be the featured one for its sector.
    if archived:
        featured = False

    def _opt(value: str) -> Optional[str]:
        v = value.strip()
        return v or None

    company = TrackerCompany(
        name=name.strip(),
        description=description.strip(),
        sector=sector,
        alpha=_opt(alpha),
        founders=_opt(founders),
        stage=_opt(stage),
        notable_investors=_opt(notable_investors),
        region=_opt(region),
        website=_opt(website),
        is_featured=featured,
        is_archived=archived,
    )
    db.add(company)
    await db.flush()  # populate company.id

    if featured:
        await db.execute(
            update(TrackerCompany)
            .where(TrackerCompany.sector == sector)
            .where(TrackerCompany.id != company.id)
            .values(is_featured=False)
        )

    await db.commit()
    return RedirectResponse(url="/admin?ok=created", status_code=303)


@app.get("/admin/tracker/companies/{company_id}/edit", include_in_schema=False)
async def admin_edit_form(
    request: Request,
    company_id: int,
    db: AsyncSession = Depends(get_db),
):
    if not request.session.get("authed"):
        return RedirectResponse(url="/admin", status_code=303)
    company = await db.get(TrackerCompany, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return templates.TemplateResponse(
        request,
        "admin_edit_company.html",
        {"company": company, "sectors": TRACKER_SECTORS},
    )


@app.post("/admin/tracker/companies/{company_id}/edit", include_in_schema=False)
async def admin_edit_submit(
    request: Request,
    company_id: int,
    name: str = Form(...),
    description: str = Form(...),
    sector: str = Form(...),
    alpha: str = Form(""),
    founders: str = Form(""),
    stage: str = Form(""),
    notable_investors: str = Form(""),
    region: str = Form(""),
    website: str = Form(""),
    is_featured: Optional[str] = Form(None),
    is_archived: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin_session),
):
    if sector not in TRACKER_SECTORS:
        raise HTTPException(status_code=400, detail=f"Invalid sector: {sector}")

    company = await db.get(TrackerCompany, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    featured = bool(is_featured)
    archived = bool(is_archived)
    if archived:
        featured = False  # archived rows are never the sector's featured pick

    def _opt(value: str) -> Optional[str]:
        v = value.strip()
        return v or None

    company.name = name.strip()
    company.description = description.strip()
    company.sector = sector
    company.alpha = _opt(alpha)
    company.founders = _opt(founders)
    company.stage = _opt(stage)
    company.notable_investors = _opt(notable_investors)
    company.region = _opt(region)
    company.website = _opt(website)
    company.is_featured = featured
    company.is_archived = archived

    if featured:
        await db.execute(
            update(TrackerCompany)
            .where(TrackerCompany.sector == sector)
            .where(TrackerCompany.id != company.id)
            .values(is_featured=False)
        )

    await db.commit()
    return RedirectResponse(url="/admin?ok=updated", status_code=303)


@app.post("/admin/tracker/companies/{company_id}/feature", include_in_schema=False)
async def admin_toggle_feature(
    company_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin_session),
):
    company = await db.get(TrackerCompany, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    if company.is_featured:
        company.is_featured = False
    else:
        await db.execute(
            update(TrackerCompany)
            .where(TrackerCompany.sector == company.sector)
            .where(TrackerCompany.id != company.id)
            .values(is_featured=False)
        )
        company.is_featured = True
        # Re-featuring an archived company brings it back to active.
        if company.is_archived:
            company.is_archived = False

    await db.commit()
    return RedirectResponse(url="/admin?ok=featured", status_code=303)


@app.post("/admin/tracker/companies/{company_id}/archive", include_in_schema=False)
async def admin_archive(
    company_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin_session),
):
    company = await db.get(TrackerCompany, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    company.is_archived = True
    company.is_featured = False
    await db.commit()
    return RedirectResponse(url="/admin?ok=archived", status_code=303)


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