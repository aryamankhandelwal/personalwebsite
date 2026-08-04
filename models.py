"""SQLAlchemy models for the Ask Me Anything app."""
from datetime import datetime, timezone
from sqlalchemy import Boolean, Column, Date, Integer, LargeBinary, String, Text, DateTime, ForeignKey, func
from sqlalchemy.orm import declarative_base, deferred, relationship

Base = declarative_base()


def _utcnow():
    return datetime.now(timezone.utc)

class Question(Base):
    """Database model for a submitted question."""
    __tablename__ = 'questions'
    id = Column(Integer, primary_key=True, index=True)
    text = Column(Text, nullable=False)
    nickname = Column(String(50), nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    status = Column(String(20), default='unanswered')
    responder_answer = Column(Text, nullable=True)
    reply_count = Column(Integer, default=0)
    edited = Column(Integer, default=0)  # 0 = not edited, 1 = edited
    replies = relationship('Reply', back_populates='question', cascade='all, delete-orphan')

class Reply(Base):
    """Database model for a reply to a question."""
    __tablename__ = 'replies'
    id = Column(Integer, primary_key=True, index=True)
    question_id = Column(Integer, ForeignKey('questions.id'), nullable=False)
    reply_text = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)
    edited = Column(Integer, default=0)  # 0 = not edited, 1 = edited
    question = relationship('Question', back_populates='replies')
    admin_reply = relationship('AdminReply', back_populates='reply', uselist=False, cascade='all, delete-orphan')

class AdminReply(Base):
    """Database model for an admin reply to a reply."""
    __tablename__ = 'admin_replies'
    id = Column(Integer, primary_key=True, index=True)
    reply_id = Column(Integer, ForeignKey('replies.id'), nullable=False, unique=True)
    admin_answer = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)
    edited = Column(Integer, default=0)  # 0 = not edited, 1 = edited
    reply = relationship('Reply', back_populates='admin_reply')

class LiveTweet(Base):
    __tablename__ = 'livetweets'
    id = Column(Integer, primary_key=True, index=True)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class TrackerCompany(Base):
    __tablename__ = 'tracker_companies'
    id = Column(Integer, primary_key=True, index=True)
    name = Column(Text, nullable=False)
    description = Column(Text, nullable=False)
    alpha = Column(Text, nullable=True)
    founders = Column(Text, nullable=True)
    stage = Column(Text, nullable=True)
    notable_investors = Column(Text, nullable=True)
    website = Column(Text, nullable=True)
    sector = Column(Text, nullable=False)
    region = Column(Text, nullable=True)
    is_featured = Column(Boolean, server_default='false', default=False, nullable=False)
    is_archived = Column(Boolean, server_default='false', default=False, nullable=False)
    date_added = Column(Date, server_default=func.current_date(), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

class BlogPost(Base):
    """A blog post, drafted in the admin panel and published to the public site."""
    __tablename__ = 'blog_posts'
    id = Column(Integer, primary_key=True, index=True)
    title = Column(Text, nullable=False, server_default='', default='')
    # Raw editor text. Blank lines separate paragraphs; [Image #N] tokens
    # reference the BlogImage rows below. Rendered by blogfmt.render().
    content = Column(Text, nullable=False, server_default='', default='')
    # Month picker in the admin, so this is always the 1st of the month.
    # Displayed as "August 2026" to match the older hand-written posts.
    date_posted = Column(Date, nullable=True)
    slug = Column(String(200), nullable=True, unique=True, index=True)
    status = Column(String(20), nullable=False, server_default='draft', default='draft')
    # Python-side defaults as well as server ones, so the values are readable on the
    # object straight after a commit without an extra round trip.
    created_at = Column(DateTime(timezone=True), server_default=func.now(),
                        default=_utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(),
                        default=_utcnow, onupdate=_utcnow, nullable=False)
    published_at = Column(DateTime(timezone=True), nullable=True)
    images = relationship('BlogImage', back_populates='post', cascade='all, delete-orphan',
                          order_by='BlogImage.n', lazy='selectin')

class BlogImage(Base):
    """An image dropped into a blog post.

    Bytes live in the database because Render's filesystem is ephemeral — anything
    written to disk is lost on restart. Images are downscaled before storage.
    """
    __tablename__ = 'blog_images'
    id = Column(Integer, primary_key=True, index=True)
    post_id = Column(Integer, ForeignKey('blog_posts.id'), nullable=False, index=True)
    # Per-post ordinal behind the [Image #N] token. Assigned as max(n)+1 and never
    # reused, so a token keeps pointing at the same image after other images go away.
    n = Column(Integer, nullable=False)
    # Deferred so listing a post's images doesn't drag every blob into memory.
    # Reading it needs an explicit undefer() — a lazy load would blow up under async.
    data = deferred(Column(LargeBinary, nullable=False))
    mime = Column(String(40), nullable=False)
    width = Column(Integer, nullable=False)
    height = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(),
                        default=_utcnow, nullable=False)
    post = relationship('BlogPost', back_populates='images')

class BlogTweet(Base):
    """A tweet embedded in a post, copied into our own database.

    Stored rather than embedded live so the post keeps rendering if the tweet is
    deleted or X changes its embed API, and so no third-party script or tracking
    is loaded on the public site. Keyed by tweet id and shared across posts.
    """
    __tablename__ = 'blog_tweets'
    tweet_id = Column(String(30), primary_key=True, index=True)
    url = Column(Text, nullable=False)
    author_name = Column(Text, nullable=False, server_default='', default='')
    author_handle = Column(Text, nullable=False, server_default='', default='')
    text = Column(Text, nullable=False, server_default='', default='')
    date_label = Column(String(40), nullable=False, server_default='', default='')
    avatar = deferred(Column(LargeBinary, nullable=True))
    avatar_mime = Column(String(40), nullable=True)
    fetched_at = Column(DateTime(timezone=True), server_default=func.now(),
                        default=_utcnow, nullable=False)

    @property
    def has_avatar(self):
        return self.avatar_mime is not None
