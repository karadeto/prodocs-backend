"""Auth: proxies Supabase password auth so clients only ever talk to this API.

Dev fallback: if SUPABASE_URL is not configured, /auth/login mints a local
HS256 token (signed with the dev JWT secret) so the whole stack runs without
a Supabase project. Never configure production without SUPABASE_URL.
"""

import time
import uuid

import httpx
import jwt
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr

from app.config import get_settings

router = APIRouter(prefix="/auth", tags=["auth"])


class Credentials(BaseModel):
    email: EmailStr
    password: str


class TokenOut(BaseModel):
    access_token: str
    refresh_token: str | None = None
    user_id: str
    email: str


@router.post("/login", response_model=TokenOut)
async def login(body: Credentials) -> TokenOut:
    s = get_settings()
    if not s.supabase_url:
        return _dev_token(body.email)

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            f"{s.supabase_url}/auth/v1/token?grant_type=password",
            headers={"apikey": s.supabase_anon_key or ""},
            json={"email": body.email, "password": body.password},
        )
    if resp.status_code != 200:
        detail = resp.json().get("error_description") or resp.json().get("msg") or "Login failed"
        raise HTTPException(401, detail)
    data = resp.json()
    return TokenOut(
        access_token=data["access_token"],
        refresh_token=data.get("refresh_token"),
        user_id=data["user"]["id"],
        email=data["user"]["email"],
    )


@router.post("/register", response_model=TokenOut)
async def register(body: Credentials) -> TokenOut:
    s = get_settings()
    if not s.supabase_url:
        return _dev_token(body.email)

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            f"{s.supabase_url}/auth/v1/signup",
            headers={"apikey": s.supabase_anon_key or ""},
            json={"email": body.email, "password": body.password},
        )
    if resp.status_code not in (200, 201):
        detail = resp.json().get("error_description") or resp.json().get("msg") or "Registration failed"
        raise HTTPException(400, detail)
    data = resp.json()
    session = data.get("session") or data  # depending on email-confirmation settings
    if not session.get("access_token"):
        raise HTTPException(400, "Account created — confirm your email, then sign in.")
    return TokenOut(
        access_token=session["access_token"],
        refresh_token=session.get("refresh_token"),
        user_id=data["user"]["id"] if "user" in data else data["id"],
        email=body.email,
    )


def _dev_token(email: str) -> TokenOut:
    """Deterministic per-email user id so dev data survives re-logins."""
    s = get_settings()
    user_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"prodocs-dev:{email.lower()}"))
    token = jwt.encode(
        {"sub": user_id, "email": email, "aud": s.jwt_audience,
         "iat": int(time.time()), "exp": int(time.time()) + 60 * 60 * 24 * 7},
        s.supabase_jwt_secret,
        algorithm="HS256",
    )
    return TokenOut(access_token=token, user_id=user_id, email=email)
