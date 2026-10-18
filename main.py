import logging
import os
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from . import ai_service
from .config import settings
from .database import Base, SessionLocal, engine, get_db
from .models import AuditLog, Policy, Review, User, now
from .schemas import (AuditOut, LoginIn, PolicyOut, ReviewIn, ReviewOut, StatsOut, TokenOut,
                      UserCreate, UserOut)
from .security import (audit, create_token, hash_password, rate_limit, require_roles,
                       verify_password)

logging.basicConfig(level=logging.INFO)
SAMPLE_POLICY = """Restaurant: Demo Restaurant
Contact: phone 0300-0000000, email help@demo.example
Late delivery: more than 60 minutes late gets 20% off the next order.
Wrong order: replaced or refunded within 24 hours.
Cold or bad food: replaced or refunded; share the order number.
Hygiene complaints: manager calls within 2 hours.
Refunds: returned to original payment method in 5-7 working days."""


def seed():
    """Create demo admin + owner (+ sample policy) on first start."""
    with SessionLocal() as db:
        if db.query(User).count():
            return
        db.add(User(email=settings.admin_email, password_hash=hash_password(settings.admin_password),
                    role="admin", business_id=None))
        owner = User(email=settings.demo_owner_email, password_hash=hash_password(settings.demo_owner_password),
                     role="owner", business_id=1)
        db.add(owner)
        db.flush()
        db.add(Policy(business_id=1, text=SAMPLE_POLICY, updated_by=owner.id))
        db.commit()


def init_db():
    Base.metadata.create_all(engine)
    seed()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


if os.getenv("VERCEL"):      # Vercel may not run lifespan events, so set up tables on cold start
    init_db()


app = FastAPI(title="ReviewPilot AI API", version="1.0", lifespan=lifespan)
origins = [o.strip() for o in settings.cors_origins.split(",")]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=origins != ["*"],
                   allow_methods=["*"], allow_headers=["*"])

Owner = require_roles("owner")
OwnerOrStaff = require_roles("owner", "staff")
Admin = require_roles("admin")


@app.get("/", tags=["system"])
@app.get("/health", tags=["system"])
def health():
    return {"status": "ok", "ai": "gemini" if settings.gemini_api_key else "fallback-only"}


# ---------------- auth ----------------
@app.post("/login", response_model=TokenOut, tags=["auth"])
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == body.email.lower()).first()
    if not user or not verify_password(body.password, user.password_hash):
        audit(db, "login_failed", email=body.email.lower())
        raise HTTPException(401, "Wrong email or password")
    audit(db, "login_success", user)
    return TokenOut(access_token=create_token(user), role=user.role, expires_in=settings.jwt_expire_minutes * 60)


@app.post("/users", response_model=UserOut, status_code=201, tags=["admin"])
def create_user(body: UserCreate, db: Session = Depends(get_db), admin: User = Depends(Admin)):
    email = body.email.lower()
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(409, "Email already exists")
    bid = body.business_id
    if body.role == "admin":
        bid = None
    elif body.role == "staff" and bid is None:
        raise HTTPException(422, "staff needs business_id (the owner's business)")
    elif body.role == "owner" and bid is None:
        bid = (db.query(func.max(User.business_id)).scalar() or 0) + 1
    user = User(email=email, password_hash=hash_password(body.password), role=body.role, business_id=bid)
    db.add(user)
    db.commit()
    audit(db, "user_created", admin, target=email, detail=f"role={body.role} business_id={bid}")
    return user


# ---------------- reviews ----------------
def _policy_text(db: Session, business_id: int) -> str:
    p = db.query(Policy).filter(Policy.business_id == business_id).first()
    return p.text if p else ""


@app.post("/reviews", response_model=ReviewOut, status_code=201, tags=["reviews"],
          dependencies=[Depends(rate_limit)])
def add_review(body: ReviewIn, db: Session = Depends(get_db), user: User = Depends(Owner)):
    text = body.text.strip()
    if not text:
        raise HTTPException(422, "Review text is empty")
    analysis, src1 = ai_service.analyze_review(text, body.rating)
    reply, src2 = ai_service.draft_reply(text, analysis["sentiment"], analysis["category"],
                                         _policy_text(db, user.business_id))
    review = Review(business_id=user.business_id, user_id=user.id, text=text, rating=body.rating,
                    platform=body.platform, sentiment=analysis["sentiment"], category=analysis["category"],
                    urgent=analysis["urgent"], suggested_reply=reply,
                    ai_source="gemini" if src1 == src2 == "gemini" else "fallback")
    db.add(review)
    db.commit()
    db.refresh(review)
    audit(db, "review_added", user, target=f"review:{review.id}",
          detail=f"{review.sentiment}/{review.category}/urgent={review.urgent}/{review.ai_source}")
    return review


@app.get("/reviews", response_model=list[ReviewOut], tags=["reviews"])
def list_reviews(urgent: Optional[bool] = None, sentiment: Optional[str] = None,
                 category: Optional[str] = None, limit: int = 50, offset: int = 0,
                 db: Session = Depends(get_db), user: User = Depends(OwnerOrStaff)):
    q = db.query(Review).filter(Review.business_id == user.business_id)  # data isolation
    if urgent is not None:
        q = q.filter(Review.urgent == urgent)
    if sentiment:
        q = q.filter(Review.sentiment == sentiment.upper())
    if category:
        q = q.filter(func.lower(Review.category) == category.lower())
    q = q.order_by(Review.urgent.desc(), Review.created_at.desc(), Review.id.desc())
    return q.offset(max(offset, 0)).limit(min(max(limit, 1), 200)).all()


@app.get("/reviews/{review_id}", response_model=ReviewOut, tags=["reviews"])
def get_review(review_id: int, db: Session = Depends(get_db), user: User = Depends(OwnerOrStaff)):
    r = db.query(Review).filter(Review.id == review_id, Review.business_id == user.business_id).first()
    if not r:
        raise HTTPException(404, "Review not found")
    return r


@app.get("/stats", response_model=StatsOut, tags=["reviews"])
def stats(db: Session = Depends(get_db), user: User = Depends(OwnerOrStaff)):
    def n(cond):
        return func.coalesce(func.sum(case((cond, 1), else_=0)), 0)
    row = db.query(func.count(Review.id), n(Review.urgent == True), n(Review.sentiment == "NEGATIVE"),  # noqa: E712
                   n(Review.sentiment == "NEUTRAL"), n(Review.sentiment == "POSITIVE")
                   ).filter(Review.business_id == user.business_id).one()
    return StatsOut(total=row[0], urgent=row[1], negative=row[2], neutral=row[3], positive=row[4])


# ---------------- policy ----------------
@app.post("/policy", response_model=PolicyOut, tags=["policy"])
async def upload_policy(file: UploadFile = File(...), db: Session = Depends(get_db), user: User = Depends(Owner)):
    if not (file.filename or "").lower().endswith(".txt"):
        raise HTTPException(400, "Only .txt files are allowed")
    raw = await file.read(settings.max_policy_bytes + 1)
    if len(raw) > settings.max_policy_bytes:
        raise HTTPException(413, f"File too large (max {settings.max_policy_bytes // 1000} KB)")
    try:
        text = raw.decode("utf-8-sig").strip()
    except UnicodeDecodeError:
        raise HTTPException(400, "File must be UTF-8 text")
    if not text:
        raise HTTPException(400, "Policy file is empty")
    p = db.query(Policy).filter(Policy.business_id == user.business_id).first()
    if p:
        p.text, p.updated_by, p.updated_at = text, user.id, now()
    else:
        p = Policy(business_id=user.business_id, text=text, updated_by=user.id)
        db.add(p)
    db.commit()
    audit(db, "policy_uploaded", user, target=file.filename, detail=f"{len(text)} chars")
    return PolicyOut(text=p.text, updated_at=p.updated_at)


@app.get("/policy", response_model=PolicyOut, tags=["policy"])
def get_policy(db: Session = Depends(get_db), user: User = Depends(OwnerOrStaff)):
    p = db.query(Policy).filter(Policy.business_id == user.business_id).first()
    if not p:
        raise HTTPException(404, "No policy uploaded yet")
    return PolicyOut(text=p.text, updated_at=p.updated_at)


# ---------------- admin ----------------
@app.get("/audit-log", response_model=list[AuditOut], tags=["admin"])
def audit_log(action: Optional[str] = None, limit: int = 100, db: Session = Depends(get_db),
              admin: User = Depends(Admin)):
    q = db.query(AuditLog)
    if action:
        q = q.filter(AuditLog.action == action)
    return q.order_by(AuditLog.id.desc()).limit(min(max(limit, 1), 500)).all()
