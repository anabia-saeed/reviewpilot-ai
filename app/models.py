from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text

from .database import Base


def now():
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(String, nullable=False)  # owner | staff | admin
    business_id = Column(Integer, nullable=True, index=True)  # None for admin
    created_at = Column(DateTime(timezone=True), default=now)


class Review(Base):
    __tablename__ = "reviews"
    id = Column(Integer, primary_key=True)
    business_id = Column(Integer, index=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"))
    text = Column(Text, nullable=False)
    rating = Column(Integer, nullable=True)
    platform = Column(String, nullable=True)
    sentiment = Column(String, nullable=False)
    category = Column(String, nullable=False)
    urgent = Column(Boolean, default=False, index=True)
    suggested_reply = Column(Text, nullable=False)
    ai_source = Column(String, default="fallback")  # gemini | fallback
    created_at = Column(DateTime(timezone=True), default=now, index=True)


class Policy(Base):
    __tablename__ = "policies"
    id = Column(Integer, primary_key=True)
    business_id = Column(Integer, unique=True, index=True, nullable=False)
    text = Column(Text, nullable=False)
    updated_by = Column(Integer, ForeignKey("users.id"))
    updated_at = Column(DateTime(timezone=True), default=now)


class AuditLog(Base):
    __tablename__ = "audit_log"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=True)
    email = Column(String, nullable=True)
    action = Column(String, index=True, nullable=False)
    target = Column(String, nullable=True)
    detail = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=now, index=True)
