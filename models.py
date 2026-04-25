"""SQLAlchemy models for the Ask Me Anything app."""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, func
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

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