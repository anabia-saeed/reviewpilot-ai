import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .config import settings
from .database import get_db
from .models import AuditLog, User

bearer = HTTPBearer(auto_error=False)
ALGO = "HS256"


def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode()[:72], bcrypt.gensalt()).decode()


def verify_password(pw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode()[:72], hashed.encode())
    except ValueError:
        return False


def create_token(user: User) -> str:
    exp = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    return jwt.encode({"sub": str(user.id), "role": user.role, "exp": exp}, settings.jwt_secret, algorithm=ALGO)


def audit(db: Session, action: str, user: User | None = None, email: str | None = None,
          target: str | None = None, detail: str | None = None):
    db.add(AuditLog(user_id=user.id if user else None, email=user.email if user else email,
                    action=action, target=target, detail=detail))
    db.commit()


def current_user(request: Request, creds: HTTPAuthorizationCredentials = Depends(bearer),
                 db: Session = Depends(get_db)) -> User:
    if creds is None:
        audit(db, "access_denied", detail=f"no token: {request.method} {request.url.path}")
        raise HTTPException(401, "Not authenticated")
    try:
        payload = jwt.decode(creds.credentials, settings.jwt_secret, algorithms=[ALGO])
        user = db.get(User, int(payload["sub"]))
    except (jwt.PyJWTError, KeyError, ValueError):
        user = None
    if user is None:
        audit(db, "access_denied", detail=f"bad/expired token: {request.method} {request.url.path}")
        raise HTTPException(401, "Invalid or expired token")
    return user


def require_roles(*roles: str):
    def dep(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)) -> User:
        if user.role not in roles:
            audit(db, "access_denied", user, target=request.url.path,
                  detail=f"role {user.role} needs {'/'.join(roles)}")
            raise HTTPException(403, "Access denied")
        return user
    return dep


# --- simple in-memory rate limiter (per user, sliding 60s window) ---
_hits: dict[int, deque] = defaultdict(deque)


def rate_limit(user: User = Depends(current_user)):
    q, t = _hits[user.id], time.monotonic()
    while q and t - q[0] > 60:
        q.popleft()
    if len(q) >= settings.rate_limit_per_minute:
        raise HTTPException(429, "Too many reviews submitted. Please wait a minute.")
    q.append(t)
