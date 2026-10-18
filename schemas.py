from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field

Sentiment = Literal["POSITIVE", "NEUTRAL", "NEGATIVE"]
Role = Literal["owner", "staff", "admin"]


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    expires_in: int


class ReviewIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    rating: Optional[int] = Field(default=None, ge=1, le=5)
    platform: Optional[str] = Field(default=None, max_length=50)


class ReviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    text: str
    rating: Optional[int]
    platform: Optional[str]
    sentiment: str
    category: str
    urgent: bool
    suggested_reply: str
    ai_source: str
    created_at: datetime


class StatsOut(BaseModel):
    total: int
    urgent: int
    negative: int
    neutral: int
    positive: int


class PolicyOut(BaseModel):
    text: str
    updated_at: Optional[datetime] = None


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    role: Role
    business_id: Optional[int] = None  # staff: owner's business. owner: auto-assigned if omitted


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: str
    role: str
    business_id: Optional[int]


class AuditOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    user_id: Optional[int]
    email: Optional[str]
    action: str
    target: Optional[str]
    detail: Optional[str]
    created_at: datetime
