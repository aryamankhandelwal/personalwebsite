"""SQLAlchemy models for the Ask Me Anything app."""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
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
    replies = relationship('Reply', back_populates='question', cascade='all, delete-orphan')

class Reply(Base):
    """Database model for a reply to a question."""
    __tablename__ = 'replies'
    id = Column(Integer, primary_key=True, index=True)
    question_id = Column(Integer, ForeignKey('questions.id'), nullable=False)
    reply_text = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)
    question = relationship('Question', back_populates='replies') 