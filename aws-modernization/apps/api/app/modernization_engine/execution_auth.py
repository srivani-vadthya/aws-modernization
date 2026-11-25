"""Deny-by-default execution API authorization.

Operators configure EXECUTION_AUTH_TOKENS as JSON: {"token": {"subject": "...",
"permissions": ["execution:read", "execution:control"], "engagements": ["..."]}}.
No identities are created by this module.
"""
import hashlib
import hmac
import json
import os
import secrets
import time
from dataclasses import dataclass
from fastapi import Cookie, Header, HTTPException

SESSION_COOKIE = "modernization_execution_session"
_sessions: dict[str, tuple["Principal", float]] = {}

@dataclass(frozen=True)
class Principal:
    subject: str
    permissions: frozenset[str]
    engagements: frozenset[str]

def _tokens() -> dict:
    raw = os.getenv("EXECUTION_AUTH_TOKENS", "")
    try: return json.loads(raw) if raw else {}
    except json.JSONDecodeError: return {}

def authenticate(authorization: str | None = Header(default=None), session: str | None = Cookie(default=None, alias=SESSION_COOKIE)) -> Principal:
    if session:
        saved = _sessions.get(session)
        if saved and saved[1] > time.time():
            return saved[0]
        _sessions.pop(session, None)
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Execution API authentication is required")
    supplied = authorization.removeprefix("Bearer ")
    for token, details in _tokens().items():
        if hmac.compare_digest(supplied, token) and isinstance(details, dict):
            subject = details.get("subject")
            if isinstance(subject, str) and subject:
                return Principal(subject, frozenset(details.get("permissions", [])), frozenset(details.get("engagements", [])))
    raise HTTPException(401, "Invalid execution API credentials")


def issue_session(principal: Principal) -> str:
    """Exchange a configured operator token for a short-lived HttpOnly session."""
    session = secrets.token_urlsafe(32)
    _sessions[session] = (principal, time.time() + 900)
    return session

def require(principal: Principal, engagement_id: str, permission: str) -> Principal:
    if permission not in principal.permissions or ("*" not in principal.engagements and engagement_id not in principal.engagements):
        raise HTTPException(403, "Execution API permission denied")
    return principal
