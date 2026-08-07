import io
import os
import re
import unicodedata
from fastapi import FastAPI, Depends, File, Form, HTTPException, Header, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy import func as sa_func, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import undefer
from dotenv import load_dotenv
from pydantic import BaseModel
from models import Base, BlogImage, BlogPost, BlogTweet, Question, Reply, LiveTweet, TrackerCompany
from database import engine, get_db
from typing import Optional
from datetime import date, datetime, timezone
import blogfmt
import tweets as tweetfetch

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

# --- Blog ---

# Posts are drafted in /admin/blog and served from here. The public blog pages are
# static HTML on Vercel that fetch this API, so a published post is live immediately
# with no redeploy. The twelve older posts remain hand-written files under blogs/.

IMAGE_MAX_WIDTH = 1080   # 2x the 540px content column, for retina
IMAGE_MAX_HEIGHT = 1400
MAX_UPLOAD_BYTES = 10 * 1024 * 1024


class BlogDraftIn(BaseModel):
    """Editor state sent by the admin autosave and by publish."""
    title: Optional[str] = ""
    content: Optional[str] = ""
    date_posted: Optional[str] = None  # "YYYY-MM" from the month picker


def _date_label(value: Optional[date]) -> str:
    """"August 2026" — the format every existing post uses."""
    return value.strftime('%B %Y') if value else ""


def _parse_month(value: Optional[str]) -> Optional[date]:
    """Accept "YYYY-MM" from <input type="month">, normalised to the 1st."""
    if not value:
        return None
    value = value.strip()
    try:
        if len(value) == 7:
            return date.fromisoformat(value + '-01')
        return date.fromisoformat(value).replace(day=1)
    except ValueError:
        return None


def _slugify(title: str) -> str:
    ascii_only = unicodedata.normalize('NFKD', title or '').encode('ascii', 'ignore').decode('ascii')
    slug = re.sub(r'[^a-z0-9]+', '-', ascii_only.lower()).strip('-')
    return slug[:80].strip('-') or 'post'


async def _unique_slug(db: AsyncSession, base: str, post_id: int) -> str:
    candidate, suffix = base, 1
    while True:
        owner = (await db.execute(
            select(BlogPost.id).where(BlogPost.slug == candidate)
        )).scalars().first()
        if owner is None or owner == post_id:
            return candidate
        suffix += 1
        candidate = f"{base}-{suffix}"


def _process_image(raw: bytes, max_size=None):
    """Downscale and re-encode an upload. Returns (bytes, mime, width, height).

    thumbnail() caps width and height together while preserving the aspect ratio,
    and never upscales — so a very wide or very tall photo comes back in
    proportion, just small enough to sit in the blog column.
    """
    from PIL import Image, ImageOps, UnidentifiedImageError

    try:
        image = ImageOps.exif_transpose(Image.open(io.BytesIO(raw)))
    except (UnidentifiedImageError, OSError):
        raise HTTPException(status_code=400, detail="That file isn't a readable image.")

    if image.mode in ('RGBA', 'LA', 'P'):
        # Flatten transparency onto the page background so screenshots with an
        # alpha channel don't come out with black edges.
        image = image.convert('RGBA')
        backdrop = Image.new('RGB', image.size, (26, 26, 26))  # --background #1a1a1a
        backdrop.paste(image, mask=image.split()[-1])
        image = backdrop
    elif image.mode != 'RGB':
        image = image.convert('RGB')

    image.thumbnail(max_size or (IMAGE_MAX_WIDTH, IMAGE_MAX_HEIGHT), Image.LANCZOS)

    buffer = io.BytesIO()
    try:
        image.save(buffer, format='WEBP', quality=82, method=4)
        mime = 'image/webp'
    except Exception:
        buffer = io.BytesIO()
        image.save(buffer, format='JPEG', quality=85, optimize=True)
        mime = 'image/jpeg'
    return buffer.getvalue(), mime, image.width, image.height


def _iso_utc(value: Optional[datetime]) -> Optional[str]:
    """Always stamp an offset. Timestamps are written in UTC, but SQLite hands
    them back naive, and the browser would read a naive string as local time."""
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


AVATAR_SIZE = (96, 96)


async def _load_tweets(db: AsyncSession, content: str) -> dict:
    """Whatever tweets this post embeds that we already hold, keyed by id."""
    ids = blogfmt.find_tweet_ids(content or '')
    if not ids:
        return {}
    rows = (await db.execute(
        select(BlogTweet).where(BlogTweet.tweet_id.in_(ids))
    )).scalars().all()
    return {row.tweet_id: row for row in rows}


async def _ensure_tweets(db: AsyncSession, content: str) -> dict:
    """As _load_tweets, but goes and fetches any tweet we haven't seen before.

    Called when drafting and publishing, never on the public read path, so a
    reader never waits on Twitter. A tweet that can't be fetched is simply left
    out and renders as a plain link.
    """
    known = await _load_tweets(db, content)
    missing = [i for i in blogfmt.find_tweet_ids(content or '') if i not in known]
    if not missing:
        return known

    for tweet_id in missing:
        data = await tweetfetch.fetch_tweet(tweet_id)
        if not data:
            continue

        avatar_bytes, avatar_mime = None, None
        if data.get('avatar'):
            try:
                avatar_bytes, avatar_mime, _, _ = _process_image(data['avatar'], AVATAR_SIZE)
            except Exception:
                pass  # a card without an avatar is still a fine card

        row = BlogTweet(
            tweet_id=tweet_id,
            url=data['url'],
            author_name=data['author_name'],
            author_handle=data['author_handle'],
            text=data['text'],
            date_label=data['date_label'],
            avatar=avatar_bytes,
            avatar_mime=avatar_mime,
        )
        db.add(row)
        await db.flush()
        known[tweet_id] = row

    await db.commit()
    return known


def _blogpost_json(post: BlogPost) -> dict:
    return {
        "id": post.id,
        "title": post.title or "",
        "content": post.content or "",
        "date_posted": post.date_posted.isoformat()[:7] if post.date_posted else None,
        "date_label": _date_label(post.date_posted),
        "slug": post.slug,
        "status": post.status,
        "updated_at": _iso_utc(post.updated_at),
        "published_at": _iso_utc(post.published_at),
        "images": [
            {"n": i.n, "id": i.id, "width": i.width, "height": i.height}
            for i in post.images
        ],
    }


@app.get("/blogposts")
async def list_blogposts(db: AsyncSession = Depends(get_db)):
    """Published posts, newest first — consumed by blog.html."""
    result = await db.execute(
        select(BlogPost)
        .where(BlogPost.status == 'published')
        .order_by(BlogPost.published_at.desc(), BlogPost.id.desc())
    )
    return [
        {"slug": p.slug, "title": p.title, "date_label": _date_label(p.date_posted)}
        for p in result.scalars().all()
    ]


@app.get("/blogposts/{slug}")
async def get_blogpost(slug: str, request: Request, db: AsyncSession = Depends(get_db)):
    """A single published post, body already rendered to HTML."""
    result = await db.execute(
        select(BlogPost).where(BlogPost.slug == slug, BlogPost.status == 'published')
    )
    post = result.scalars().first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    return {
        "slug": post.slug,
        "title": post.title,
        "date_label": _date_label(post.date_posted),
        "content_html": blogfmt.render(
            post.content,
            {i.n: i for i in post.images},
            await _load_tweets(db, post.content),
            str(request.base_url),
        ),
    }


@app.get("/blogimages/{image_id}")
async def get_blogimage(image_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(BlogImage).options(undefer(BlogImage.data)).where(BlogImage.id == image_id)
    )
    image = result.scalars().first()
    if not image:
        raise HTTPException(status_code=404, detail="Not found")
    return Response(
        content=image.data,
        media_type=image.mime,
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )


@app.get("/blogtweets/{tweet_id}/avatar")
async def get_blogtweet_avatar(tweet_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(BlogTweet).options(undefer(BlogTweet.avatar)).where(BlogTweet.tweet_id == tweet_id)
    )
    tweet = result.scalars().first()
    if not tweet or not tweet.avatar:
        raise HTTPException(status_code=404, detail="Not found")
    return Response(
        content=tweet.avatar,
        media_type=tweet.avatar_mime or "image/webp",
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )


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

# Same icon the public site uses. Served under /admin/ so the Vercel rewrite
# (/admin/:path* -> Render) reaches it from the main domain too.
ADMIN_FAVICON = os.path.join(os.path.dirname(__file__), 'images', 'favicon-32.png')


@app.get("/admin/favicon.png", include_in_schema=False)
def admin_favicon():
    return FileResponse(ADMIN_FAVICON, media_type="image/png")


# Served from here rather than as a Vercel static file so it is same-origin
# under the /admin/:path* rewrite, which is what gives it scope over /admin/.
ADMIN_SW = os.path.join(os.path.dirname(__file__), 'static', 'sw.js')


@app.get("/admin/sw.js", include_in_schema=False)
def admin_service_worker():
    return FileResponse(
        ADMIN_SW,
        media_type="application/javascript",
        # The worker script itself must never be served stale, or a fix to it
        # could never reach a browser that already has the broken one.
        headers={"Cache-Control": "no-cache"},
    )


@app.get("/admin/manifest.json", include_in_schema=False)
def admin_manifest():
    return JSONResponse({
        "name": "Blog — Aryaman Khandelwal",
        "short_name": "Blog",
        "description": "Write and publish blog posts, online or off.",
        "start_url": "/admin/blog",
        "scope": "/admin/",
        "display": "standalone",
        "background_color": "#1a1a1a",
        "theme_color": "#1a1a1a",
        "icons": [
            {"src": "/images/app-icon-192.png", "sizes": "192x192", "type": "image/png"},
            {"src": "/images/app-icon-512.png", "sizes": "512x512", "type": "image/png"},
            {"src": "/images/app-icon-maskable-512.png", "sizes": "512x512",
             "type": "image/png", "purpose": "maskable"},
        ],
    })

def _admin_banner(request: Request) -> Optional[str]:
    return {
        "created": "Company added.",
        "updated": "Company updated.",
        "featured": "Featured updated.",
        "archived": "Company archived.",
        "tweeted": "Live tweet posted.",
    }.get(request.query_params.get("ok"))


@app.get("/admin", include_in_schema=False)
async def admin_root(request: Request):
    """Tab 1 — live tweet composer (also the login screen when signed out)."""
    if not request.session.get("authed"):
        return templates.TemplateResponse(
            request, "admin_login.html", {"error": None}
        )

    return templates.TemplateResponse(
        request,
        "admin_dashboard.html",
        {"tab": "tweets", "banner": _admin_banner(request)},
    )


@app.get("/admin/tracker", include_in_schema=False)
async def admin_tracker(request: Request, db: AsyncSession = Depends(get_db)):
    """Tab 2 — add / manage tracker companies."""
    if not request.session.get("authed"):
        return RedirectResponse(url="/admin", status_code=303)

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

    return templates.TemplateResponse(
        request,
        "admin_tracker.html",
        {
            "tab": "tracker",
            "sectors": TRACKER_SECTORS,
            "active_by_sector": active_by_sector,
            "archived_companies": archived_companies,
            "banner": _admin_banner(request),
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


# --- Admin: blog ---

@app.get("/admin/blog", include_in_schema=False)
async def admin_blog(request: Request, db: AsyncSession = Depends(get_db)):
    """Tab 2 — two-pane draft editor. Every post is embedded as JSON so switching
    between drafts is instant and never navigates away from unsaved text."""
    if not request.session.get("authed"):
        return RedirectResponse(url="/admin", status_code=303)

    result = await db.execute(
        select(BlogPost).order_by(BlogPost.updated_at.desc(), BlogPost.id.desc())
    )
    posts = [_blogpost_json(p) for p in result.scalars().all()]

    return templates.TemplateResponse(
        request,
        "admin_blog.html",
        {"tab": "blog", "posts": posts, "banner": _admin_banner(request)},
    )


@app.get("/admin/blog/drafts.json", include_in_schema=False)
async def admin_blog_drafts_json(
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin_session),
):
    """Current server state for the sync pass, without re-rendering the page."""
    result = await db.execute(
        select(BlogPost).order_by(BlogPost.updated_at.desc(), BlogPost.id.desc())
    )
    return [_blogpost_json(p) for p in result.scalars().all()]


async def _get_blogpost_or_404(db: AsyncSession, post_id: int) -> BlogPost:
    post = await db.get(BlogPost, post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    return post


def _apply_draft(post: BlogPost, payload: BlogDraftIn) -> None:
    post.title = (payload.title or "").strip()
    post.content = payload.content or ""
    post.date_posted = _parse_month(payload.date_posted)


@app.post("/admin/blog/drafts", include_in_schema=False)
async def admin_create_blog_draft(
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin_session),
):
    post = BlogPost(title="", content="", status="draft", images=[])
    db.add(post)
    await db.commit()
    return _blogpost_json(post)


@app.post("/admin/blog/drafts/{post_id}/save", include_in_schema=False)
async def admin_save_blog_draft(
    post_id: int,
    payload: BlogDraftIn,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin_session),
):
    """Autosave target. Also hit via sendBeacon when the tab goes away."""
    post = await _get_blogpost_or_404(db, post_id)
    _apply_draft(post, payload)
    await db.commit()
    return {"id": post.id, "updated_at": _iso_utc(post.updated_at)}


@app.post("/admin/blog/drafts/{post_id}/preview", include_in_schema=False)
async def admin_preview_blog_draft(
    post_id: int,
    payload: BlogDraftIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin_session),
):
    """Renders the editor's current text through the same code as the published
    page, so the preview pane can never drift from the real thing."""
    post = await _get_blogpost_or_404(db, post_id)
    content = payload.content or ""
    return {
        "content_html": blogfmt.render(
            content,
            {i.n: i for i in post.images},
            await _ensure_tweets(db, content),
            str(request.base_url),
        )
    }


@app.post("/admin/blog/drafts/{post_id}/publish", include_in_schema=False)
async def admin_publish_blog_draft(
    post_id: int,
    payload: BlogDraftIn,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin_session),
):
    post = await _get_blogpost_or_404(db, post_id)
    _apply_draft(post, payload)  # publish carries the latest editor state with it

    if not post.title:
        raise HTTPException(status_code=400, detail="Give the post a title before publishing.")
    if post.date_posted is None:
        post.date_posted = date.today().replace(day=1)
    if not post.slug:
        # Frozen once assigned, so editing a published post never breaks its link.
        post.slug = await _unique_slug(db, _slugify(post.title), post.id)
    if post.status != 'published':
        post.status = 'published'
        post.published_at = datetime.now(timezone.utc)

    await db.commit()
    # Any tweet not already stored gets pulled in now, so the public read path
    # never has to wait on Twitter.
    await _ensure_tweets(db, post.content)
    return _blogpost_json(post)


@app.post("/admin/blog/drafts/{post_id}/delete", include_in_schema=False)
async def admin_delete_blog_draft(
    post_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin_session),
):
    post = await _get_blogpost_or_404(db, post_id)
    await db.delete(post)  # cascades to its images
    await db.commit()
    return {"status": "deleted"}


@app.post("/admin/blog/drafts/{post_id}/images", include_in_schema=False)
async def admin_upload_blog_image(
    post_id: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin_session),
):
    post = await _get_blogpost_or_404(db, post_id)

    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Empty file.")
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Image is larger than 10MB.")

    data, mime, width, height = _process_image(raw)

    # Ordinals are never reused, so [Image #2] keeps meaning the same image.
    next_n = (await db.execute(
        select(sa_func.coalesce(sa_func.max(BlogImage.n), 0)).where(BlogImage.post_id == post.id)
    )).scalar_one() + 1

    image = BlogImage(post_id=post.id, n=next_n, data=data, mime=mime, width=width, height=height)
    db.add(image)
    await db.flush()  # populate image.id
    image_id = image.id
    await db.commit()
    return {"id": image_id, "n": next_n, "width": width, "height": height}


@app.post("/admin/blog/images/{image_id}/delete", include_in_schema=False)
async def admin_delete_blog_image(
    image_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin_session),
):
    image = await db.get(BlogImage, image_id)
    if not image:
        raise HTTPException(status_code=404, detail="Not found")
    await db.delete(image)
    await db.commit()
    return {"status": "deleted"}


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
    return RedirectResponse(url="/admin/tracker?ok=created", status_code=303)


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
    return RedirectResponse(url="/admin/tracker?ok=updated", status_code=303)


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
    return RedirectResponse(url="/admin/tracker?ok=featured", status_code=303)


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
    return RedirectResponse(url="/admin/tracker?ok=archived", status_code=303)


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