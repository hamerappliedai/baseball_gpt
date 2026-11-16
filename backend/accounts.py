"""Accounts for Ask AI: login, server-side sessions and per-user usage limits.

Browse is public. Ask AI spends API tokens, so /api/chat needs a signed-in
user (see `current_user`) and is limited per user (see `check_chat_allowed`).

  POST /api/auth/login   {"email", "password"} -> sets the session cookie
  POST /api/auth/logout  deletes the session and the cookie
  GET  /api/auth/me      the signed-in user and their remaining allowance, or 401

Accounts are created by an admin (`make user-add`); there is no public sign-up,
because every account can spend tokens.

Security notes:
- Passwords are hashed with Argon2id. A wrong email and a wrong password get the
  same answer, and an unknown email still costs one hash, so responses don't
  reveal which emails have accounts.
- The session cookie holds 256 random bits; the database stores only their
  SHA-256, so the sessions table can't be replayed. Sessions can be revoked
  (logout, disabling a user, changing a password).
- The cookie is HttpOnly and SameSite=Lax, so other sites can't send it with
  a POST (CSRF) and page scripts can't read it; Secure unless COOKIE_SECURE=false.
- Failed logins are rate limited per email and per client address, in the
  database so the limit holds across several backend instances.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import secrets
from typing import Any

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

import appdb

log = logging.getLogger("baseball_gpt.accounts")

COOKIE = "bgpt_session"
SESSION_DAYS = int(os.environ.get("SESSION_DAYS", "14"))
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "true").lower() not in ("0", "false", "no")
LOGIN_WINDOW_MINUTES = 15
LOGIN_MAX_FAILURES_EMAIL = int(os.environ.get("LOGIN_MAX_FAILURES_EMAIL", "5"))
LOGIN_MAX_FAILURES_IP = int(os.environ.get("LOGIN_MAX_FAILURES_IP", "20"))

# Ask AI allowance per user. Tokens are counted as the API reports them, summed
# over a question's tool-use rounds, with cache reads at a tenth (they cost a
# tenth as much, and every round re-reads the cached schema prompt).
CHAT_HOURLY_LIMIT = int(os.environ.get("CHAT_HOURLY_LIMIT", "20"))      # questions per hour
CHAT_DAILY_TOKENS = int(os.environ.get("CHAT_DAILY_TOKENS", "300000"))  # per rolling 24 h
CHAT_MAX_TURNS = int(os.environ.get("CHAT_MAX_TURNS", "20"))            # questions per conversation

_hasher = PasswordHasher()  # Argon2id with the library's current recommended parameters
_DUMMY_HASH = _hasher.hash(secrets.token_urlsafe(16))
_in_flight: set[int] = set()  # users with a question streaming in this process

router = APIRouter(prefix="/api/auth", tags=["auth"])


# --- passwords and users -----------------------------------------------------

MIN_PASSWORD_LENGTH = 10


def hash_password(password: str) -> str:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"password must be at least {MIN_PASSWORD_LENGTH} characters")
    return _hasher.hash(password)


def normalize_email(email: str) -> str:
    return email.strip().lower()


async def create_user(email: str, password: str, display_name: str, role: str = "user",
                      daily_token_limit: int | None = None) -> dict[str, Any]:
    row = await appdb.fetch_one(
        "INSERT INTO app.users (email, password_hash, display_name, role, daily_token_limit) "
        "VALUES (%s, %s, %s, %s, %s) RETURNING id, email, display_name, role",
        (normalize_email(email), hash_password(password), display_name.strip(), role, daily_token_limit),
    )
    assert row is not None
    return row


async def set_password(email: str, password: str) -> bool:
    """Change a password and sign the user out everywhere."""
    row = await appdb.fetch_one(
        "UPDATE app.users SET password_hash = %s WHERE email = %s RETURNING id",
        (hash_password(password), normalize_email(email)))
    if row:
        await appdb.fetch("DELETE FROM app.sessions WHERE user_id = %s", (row["id"],))
    return row is not None


async def set_active(email: str, active: bool) -> bool:
    """Enable or disable an account; disabling also ends its sessions."""
    row = await appdb.fetch_one(
        "UPDATE app.users SET is_active = %s WHERE email = %s RETURNING id", (active, normalize_email(email)))
    if row and not active:
        await appdb.fetch("DELETE FROM app.sessions WHERE user_id = %s", (row["id"],))
    return row is not None


# --- sessions ----------------------------------------------------------------

def _token_hash(token: str) -> bytes:
    return hashlib.sha256(token.encode()).digest()


async def _create_session(user_id: int, user_agent: str | None) -> str:
    token = secrets.token_urlsafe(32)
    await appdb.fetch(
        "INSERT INTO app.sessions (token_hash, user_id, expires_at, user_agent) "
        "VALUES (%s, %s, now() + make_interval(days => %s), %s)",
        (_token_hash(token), user_id, SESSION_DAYS, (user_agent or "")[:300]),
    )
    return token


def _set_cookie(response: Response, token: str) -> None:
    response.set_cookie(COOKIE, token, max_age=SESSION_DAYS * 86400, httponly=True,
                        secure=COOKIE_SECURE, samesite="lax", path="/")


async def current_user_or_none(request: Request) -> dict[str, Any] | None:
    token = request.cookies.get(COOKIE)
    if not token or len(token) > 100:
        return None
    return await appdb.fetch_one(
        # Touch last_seen_at at most every 5 minutes, not on every request.
        """WITH s AS (
               SELECT s.token_hash, s.user_id, s.last_seen_at
               FROM app.sessions s JOIN app.users u ON u.id = s.user_id
               WHERE s.token_hash = %(h)s AND s.expires_at > now() AND u.is_active
           ), touch AS (
               UPDATE app.sessions SET last_seen_at = now()
               WHERE token_hash = (SELECT token_hash FROM s WHERE last_seen_at < now() - interval '5 minutes')
           )
           SELECT u.id, u.email, u.display_name, u.role, u.daily_token_limit
           FROM s JOIN app.users u ON u.id = s.user_id""",
        {"h": _token_hash(token)},
    )


async def current_user(request: Request) -> dict[str, Any]:
    """FastAPI dependency: the signed-in user, or 401."""
    user = await current_user_or_none(request)
    if user is None:
        raise HTTPException(401, "Sign in to use Ask AI.")
    return user


# --- usage limits --------------------------------------------------------------

_WEIGHTED_TOKENS = ("coalesce(sum(input_tokens + output_tokens + cache_creation_tokens"
                    " + cache_read_tokens / 10), 0)::bigint")


async def allowance(user: dict[str, Any]) -> dict[str, Any]:
    row = await appdb.fetch_one(
        f"""SELECT {_WEIGHTED_TOKENS} AS tokens_today,
                   count(*) FILTER (WHERE created_at > now() - interval '1 hour') AS questions_last_hour
            FROM app.chat_usage
            WHERE user_id = %s AND created_at > now() - interval '24 hours'""",
        (user["id"],),
    )
    assert row is not None
    limit = user["daily_token_limit"] if user["daily_token_limit"] is not None else CHAT_DAILY_TOKENS
    return {
        "tokens_today": row["tokens_today"], "daily_token_limit": limit,
        "questions_last_hour": row["questions_last_hour"], "hourly_question_limit": CHAT_HOURLY_LIMIT,
        "max_turns": CHAT_MAX_TURNS,
    }


async def check_chat_allowed(user: dict[str, Any], user_turns: int) -> None:
    """Raise 4xx if this question would go over the user's allowance."""
    if user_turns > CHAT_MAX_TURNS:
        raise HTTPException(400, f"Conversations are limited to {CHAT_MAX_TURNS} questions. Start a new chat.")
    if user["id"] in _in_flight:
        raise HTTPException(429, "You already have a question running. Wait for it to finish.")
    a = await allowance(user)
    if a["questions_last_hour"] >= a["hourly_question_limit"]:
        raise HTTPException(429, f"You've asked {a['hourly_question_limit']} questions in the last hour. "
                                 "Try again a little later.")
    if a["tokens_today"] >= a["daily_token_limit"]:
        raise HTTPException(429, "You've used today's Ask AI allowance. It frees up over the next 24 hours; "
                                 "Leaders, Players and Standings don't need it.")


class InFlight:
    """Marks a user as having a question streaming (one at a time per user)."""

    def __init__(self, user_id: int):
        self.user_id = user_id

    def __enter__(self):
        _in_flight.add(self.user_id)
        return self

    def __exit__(self, *exc):
        _in_flight.discard(self.user_id)
        return False


async def record_usage(user_id: int, model: str, usage: dict[str, Any]) -> None:
    """Store what a question cost. Runs even when the client disconnects mid-answer."""
    try:
        await asyncio.shield(appdb.fetch(
            "INSERT INTO app.chat_usage (user_id, model, input_tokens, output_tokens, cache_creation_tokens, "
            "cache_read_tokens, tool_rounds, stop_reason) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (user_id, model, usage.get("input_tokens", 0), usage.get("output_tokens", 0),
             usage.get("cache_creation_input_tokens", 0), usage.get("cache_read_input_tokens", 0),
             usage.get("tool_rounds", 0), usage.get("stop_reason")),
        ))
    except Exception:  # noqa: BLE001 - never lose the answer over bookkeeping
        log.exception("could not record chat usage for user %s", user_id)


# --- routes ----------------------------------------------------------------------

class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=1024)


def _client_ip(request: Request) -> str:
    # Behind a load balancer, run uvicorn with --proxy-headers so this is the
    # real client address (see README, Deployment).
    return request.client.host if request.client else "unknown"


_BAD_LOGIN = "Wrong email or password."


@router.post("/login")
async def login(body: LoginRequest, request: Request, response: Response):
    email, ip = normalize_email(body.email), _client_ip(request)
    recent = await appdb.fetch_one(
        """SELECT count(*) FILTER (WHERE email = %(email)s) AS by_email,
                  count(*) FILTER (WHERE client_ip = %(ip)s) AS by_ip
           FROM app.login_failures
           WHERE at > now() - make_interval(mins => %(window)s)
             AND (email = %(email)s OR client_ip = %(ip)s)""",
        {"email": email, "ip": ip, "window": LOGIN_WINDOW_MINUTES},
    )
    assert recent is not None
    if recent["by_email"] >= LOGIN_MAX_FAILURES_EMAIL or recent["by_ip"] >= LOGIN_MAX_FAILURES_IP:
        raise HTTPException(429, f"Too many failed sign-ins. Try again in {LOGIN_WINDOW_MINUTES} minutes.")

    user = await appdb.fetch_one(
        "SELECT id, email, display_name, role, password_hash, is_active FROM app.users WHERE email = %s",
        (email,))
    ok = False
    try:  # always hash once, so timing doesn't reveal whether the email exists
        ok = await asyncio.to_thread(_hasher.verify, user["password_hash"] if user else _DUMMY_HASH, body.password)
    except (VerificationError, InvalidHashError):
        ok = False
    if not (ok and user and user["is_active"]):
        await appdb.fetch("INSERT INTO app.login_failures (email, client_ip) VALUES (%s, %s)", (email, ip))
        raise HTTPException(401, _BAD_LOGIN)

    if _hasher.check_needs_rehash(user["password_hash"]):
        await appdb.fetch("UPDATE app.users SET password_hash = %s WHERE id = %s",
                          (_hasher.hash(body.password), user["id"]))
    await appdb.fetch("UPDATE app.users SET last_login_at = now() WHERE id = %s", (user["id"],))
    # Housekeeping: expired sessions and old failures.
    await appdb.fetch("DELETE FROM app.sessions WHERE expires_at < now()")
    await appdb.fetch("DELETE FROM app.login_failures WHERE at < now() - interval '1 day'")
    token = await _create_session(user["id"], request.headers.get("user-agent"))
    _set_cookie(response, token)
    return {"user": {k: user[k] for k in ("email", "display_name", "role")}}


@router.post("/logout")
async def logout(request: Request, response: Response):
    token = request.cookies.get(COOKIE)
    if token:
        await appdb.fetch("DELETE FROM app.sessions WHERE token_hash = %s", (_token_hash(token),))
    response.delete_cookie(COOKIE, path="/", httponly=True, secure=COOKIE_SECURE, samesite="lax")
    return {"ok": True}


@router.get("/me")
async def me(response: Response, user: dict[str, Any] = Depends(current_user)):
    response.headers["Cache-Control"] = "no-store"
    return {"user": {k: user[k] for k in ("email", "display_name", "role")},
            "allowance": await allowance(user)}
