"""Accounts, sessions and Ask AI gating, against the real app schema (skipped
when it isn't migrated). Claude is a scripted fake: no API calls, no tokens."""

import secrets
from types import SimpleNamespace as NS

import httpx2 as httpx
import pytest

import accounts
import agent
import app as app_module
import appdb
from app import app
from tests.test_agent import FakeClient, reply, text

pytestmark = pytest.mark.anyio
DOMAIN = "example.test"


@pytest.fixture
async def users(app_db, monkeypatch):
    """Creates throwaway accounts; deletes them (and their sessions, usage and
    failed logins) afterwards."""
    monkeypatch.setattr(accounts, "COOKIE_SECURE", False)  # the test client talks plain http
    made = []

    async def make(password="correct horse battery", **kw):
        email = f"test-{secrets.token_hex(4)}@{DOMAIN}"
        await accounts.create_user(email, password, kw.pop("name", "Test User"), **kw)
        made.append(email)
        return email, password

    yield make
    await appdb.fetch("DELETE FROM app.users WHERE email LIKE %s", (f"test-%@{DOMAIN}",))
    await appdb.fetch("DELETE FROM app.login_failures WHERE email LIKE %s", (f"%@{DOMAIN}",))


@pytest.fixture
async def api():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        yield client


async def login(api, email, password):
    return await api.post("/api/auth/login", json={"email": email, "password": password})


def scripted(*replies):
    """A fake Claude whose replies report token usage."""
    for r in replies:
        r.usage = NS(input_tokens=1000, output_tokens=200, cache_creation_input_tokens=0,
                     cache_read_input_tokens=5000)
    return FakeClient(*replies)


@pytest.fixture
def fake_claude(monkeypatch):
    async def schema_prompt():
        return "## players\n- player_id text"
    monkeypatch.setattr(agent, "schema_prompt", schema_prompt)

    def install(*replies):
        client = scripted(*replies)
        monkeypatch.setattr(app_module, "client", client)
        return client
    return install


async def ask(api, question="Who hit 73?"):
    return await api.post("/api/chat", json={"messages": [{"role": "user", "content": question}]})


# --- sign-in -------------------------------------------------------------------

async def test_login_me_logout(api, users):
    email, pw = await users(name="Ann")
    assert (await api.get("/api/auth/me")).status_code == 401

    res = await login(api, email.upper(), pw)  # emails are case-insensitive
    assert res.status_code == 200 and res.json()["user"]["display_name"] == "Ann"
    cookie = res.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie

    me = (await api.get("/api/auth/me")).json()
    assert me["user"]["email"] == email and me["allowance"]["tokens_today"] == 0

    assert (await api.post("/api/auth/logout")).status_code == 200
    assert (await api.get("/api/auth/me")).status_code == 401


async def test_cookie_is_secure_by_default(api, users, monkeypatch):
    email, pw = await users()
    monkeypatch.setattr(accounts, "COOKIE_SECURE", True)
    assert "secure" in (await login(api, email, pw)).headers["set-cookie"].lower()


async def test_wrong_password_and_unknown_email_look_the_same(api, users):
    email, _ = await users()
    wrong = await login(api, email, "not the password")
    unknown = await login(api, f"nobody-{secrets.token_hex(4)}@{DOMAIN}", "whatever123")
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()
    assert "set-cookie" not in wrong.headers


async def test_failed_logins_are_rate_limited(api, users):
    email, pw = await users()
    for _ in range(accounts.LOGIN_MAX_FAILURES_EMAIL):
        assert (await login(api, email, "wrong password")).status_code == 401
    # Locked out for the window, even with the right password.
    assert (await login(api, email, pw)).status_code == 429


async def test_disabled_user_cannot_sign_in_and_is_signed_out(api, users):
    email, pw = await users()
    assert (await login(api, email, pw)).status_code == 200
    await accounts.set_active(email, False)
    assert (await api.get("/api/auth/me")).status_code == 401
    assert (await login(api, email, pw)).status_code == 401


async def test_password_change_ends_sessions(api, users):
    email, pw = await users()
    await login(api, email, pw)
    await accounts.set_password(email, "a brand new password")
    assert (await api.get("/api/auth/me")).status_code == 401
    assert (await login(api, email, "a brand new password")).status_code == 200


async def test_expired_and_forged_sessions_are_rejected(api, users):
    email, pw = await users()
    await login(api, email, pw)
    await appdb.fetch("UPDATE app.sessions s SET expires_at = now() - interval '1 second' "
                      "FROM app.users u WHERE u.id = s.user_id AND u.email = %s", (email,))
    assert (await api.get("/api/auth/me")).status_code == 401
    api.cookies.set(accounts.COOKIE, secrets.token_urlsafe(32))
    assert (await api.get("/api/auth/me")).status_code == 401


async def test_session_token_is_stored_hashed(api, users):
    email, pw = await users()
    token = (await login(api, email, pw)).cookies[accounts.COOKIE]
    row = await appdb.fetch_one("SELECT token_hash FROM app.sessions s JOIN app.users u ON u.id = s.user_id "
                                "WHERE u.email = %s", (email,))
    assert bytes(row["token_hash"]) == accounts._token_hash(token) and token.encode() not in bytes(row["token_hash"])


def test_short_passwords_are_refused():
    with pytest.raises(ValueError):
        accounts.hash_password("short")


# --- Ask AI gating ----------------------------------------------------------------

async def test_chat_needs_sign_in(api, app_db, fake_claude):
    client = fake_claude(reply(text("73")))
    res = await ask(api)
    assert res.status_code == 401
    assert client.requests == []  # Claude was never called


async def test_chat_records_usage(api, users, fake_claude):
    email, pw = await users()
    await login(api, email, pw)
    fake_claude(reply(text("Barry Bonds, 73.")))
    res = await ask(api)
    assert res.status_code == 200 and "Barry Bonds" in res.text
    row = await appdb.fetch_one("SELECT c.* FROM app.chat_usage c JOIN app.users u ON u.id = c.user_id "
                                "WHERE u.email = %s", (email,))
    assert (row["input_tokens"], row["output_tokens"], row["cache_read_tokens"]) == (1000, 200, 5000)
    assert row["stop_reason"] == "end_turn" and row["model"] == agent.MODEL
    # Cache reads count a tenth: 1000 + 200 + 5000 / 10.
    assert (await api.get("/api/auth/me")).json()["allowance"]["tokens_today"] == 1700


async def test_daily_token_budget(api, users, fake_claude):
    email, pw = await users(daily_token_limit=1500)
    await login(api, email, pw)
    client = fake_claude(reply(text("one")), reply(text("two")))
    assert (await ask(api)).status_code == 200  # 1700 weighted tokens: now over 1500
    res = await ask(api)
    assert res.status_code == 429 and "allowance" in res.json()["detail"]
    assert len(client.requests) == 1


async def test_hourly_question_limit(api, users, fake_claude, monkeypatch):
    monkeypatch.setattr(accounts, "CHAT_HOURLY_LIMIT", 2)
    email, pw = await users()
    await login(api, email, pw)
    fake_claude(*(reply(text("ok")) for _ in range(3)))
    assert (await ask(api)).status_code == 200
    assert (await ask(api)).status_code == 200
    assert (await ask(api)).status_code == 429


async def test_conversation_length_is_capped(api, users, fake_claude, monkeypatch):
    monkeypatch.setattr(accounts, "CHAT_MAX_TURNS", 2)
    email, pw = await users()
    await login(api, email, pw)
    client = fake_claude(reply(text("ok")))
    history = [{"role": "user", "content": "q"}, {"role": "assistant", "content": "a"}] * 2
    res = await api.post("/api/chat", json={"messages": history + [{"role": "user", "content": "q3"}]})
    assert res.status_code == 400 and "new chat" in res.json()["detail"]
    assert client.requests == []


async def test_one_question_at_a_time(api, users, fake_claude):
    email, pw = await users()
    await login(api, email, pw)
    fake_claude(reply(text("ok")))
    user = await accounts.current_user_or_none(NS(cookies=dict(api.cookies)))
    with accounts.InFlight(user["id"]):
        assert (await ask(api)).status_code == 429


async def test_reader_role_cannot_see_accounts(reader):
    import db
    with pytest.raises(db.QueryError):
        await db.run_query("SELECT email FROM app.users")
