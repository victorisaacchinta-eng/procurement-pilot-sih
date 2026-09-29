"""
Authentication and role-based access.

JWT (HS256) bearer tokens. Three roles:
  officer          evaluate bids, record decisions, view the audit log
  senior_approver  everything an officer can do, plus qualify a bid the
                   system did not mark Compliant (with a written reason)
  admin            everything, plus export the audit log and run retention

Demo accounts are for the prototype only. Override them with DEMO_USERS
(format "user:password:role,user2:password2:role2") and set JWT_SECRET
before any real use.
"""
import os
import time
import hmac
import hashlib
import secrets

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

JWT_SECRET = os.environ.get("JWT_SECRET") or secrets.token_hex(32)
JWT_TTL_SECONDS = int(os.environ.get("JWT_TTL_SECONDS", str(8 * 3600)))
ROLES = ("officer", "senior_approver", "admin")

_DEFAULT_USERS = "officer1:officer123:officer,approver1:approver123:senior_approver,admin1:admin123:admin"


def _hash(password: str, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 120_000)


def _load_users() -> dict:
    users = {}
    for entry in (os.environ.get("DEMO_USERS") or _DEFAULT_USERS).split(","):
        parts = entry.strip().split(":")
        if len(parts) != 3 or parts[2] not in ROLES:
            continue
        salt = secrets.token_bytes(16)
        users[parts[0]] = {"salt": salt, "hash": _hash(parts[1], salt), "role": parts[2]}
    return users


USERS = _load_users()
_bearer = HTTPBearer(auto_error=False)


def authenticate(username: str, password: str):
    u = USERS.get(username or "")
    if not u or not hmac.compare_digest(u["hash"], _hash(password or "", u["salt"])):
        return None
    return {"username": username, "role": u["role"]}


def issue_token(user: dict) -> str:
    now = int(time.time())
    return jwt.encode({"sub": user["username"], "role": user["role"], "iat": now, "exp": now + JWT_TTL_SECONDS},
                      JWT_SECRET, algorithm="HS256")


def current_user(creds: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> dict:
    if creds is None:
        raise HTTPException(401, "Sign in required.")
    try:
        claims = jwt.decode(creds.credentials, JWT_SECRET, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Session expired. Sign in again.")
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Invalid session. Sign in again.")
    if claims.get("sub") not in USERS:
        raise HTTPException(401, "Account no longer exists.")
    return {"username": claims["sub"], "role": claims.get("role")}


def require_roles(*roles):
    def dep(user: dict = Depends(current_user)) -> dict:
        if user["role"] not in roles:
            raise HTTPException(403, f"This action needs one of these roles: {', '.join(roles)}.")
        return user
    return dep
