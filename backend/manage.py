"""Admin commands for Ask AI accounts (there is no public sign-up).

    python manage.py user-add --email a@b.com --name "Ann" [--admin] [--daily-tokens N] [--generate-password]
    python manage.py user-list
    python manage.py user-passwd --email a@b.com [--generate-password]
    python manage.py user-disable --email a@b.com      # also signs them out
    python manage.py user-enable --email a@b.com
    python manage.py user-limit --email a@b.com --daily-tokens N   (or --default)

Passwords are read without echo (asked twice), or generated and printed once
with --generate-password. Runs as bgpt_app via APP_DATABASE_URL.
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import secrets
import sys
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent
load_dotenv(BACKEND_DIR / ".env")
load_dotenv(BACKEND_DIR.parent / ".env")

import psycopg  # noqa: E402

import accounts  # noqa: E402
import appdb  # noqa: E402


def _password(generate: bool) -> tuple[str, bool]:
    if generate:
        return secrets.token_urlsafe(12), True
    while True:
        pw = getpass.getpass("Password: ")
        if len(pw) < accounts.MIN_PASSWORD_LENGTH:
            print(f"At least {accounts.MIN_PASSWORD_LENGTH} characters, please.")
            continue
        if getpass.getpass("Again: ") != pw:
            print("They don't match; try again.")
            continue
        return pw, False


async def _run(args: argparse.Namespace) -> int:
    try:
        if args.command == "user-add":
            pw, generated = _password(args.generate_password)
            user = await accounts.create_user(args.email, pw, args.name, "admin" if args.admin else "user",
                                              args.daily_tokens)
            print(f"Created {user['role']} {user['email']} ({user['display_name']}).")
            if generated:
                print(f"Password (shown once): {pw}")
        elif args.command == "user-list":
            rows = await appdb.fetch(
                f"""SELECT u.email, u.display_name, u.role, u.is_active, u.daily_token_limit,
                           u.last_login_at::date AS last_login,
                           (SELECT {accounts._WEIGHTED_TOKENS} FROM app.chat_usage c
                            WHERE c.user_id = u.id AND c.created_at > now() - interval '24 hours') AS tokens_24h
                    FROM app.users u ORDER BY u.created_at""")
            if not rows:
                print("No accounts yet. Add one with `make user-add EMAIL=... NAME=...`.")
            for r in rows:
                limit = r["daily_token_limit"] if r["daily_token_limit"] is not None else f"{accounts.CHAT_DAILY_TOKENS} (default)"
                print(f"{r['email']:32s} {r['display_name']:20s} {r['role']:5s} "
                      f"{'active' if r['is_active'] else 'DISABLED':8s} tokens 24h {r['tokens_24h']:>8} / {limit}  "
                      f"last login {r['last_login'] or '—'}")
        elif args.command == "user-passwd":
            pw, generated = _password(args.generate_password)
            if not await accounts.set_password(args.email, pw):
                print(f"No account for {args.email}.")
                return 1
            print(f"Password changed for {args.email}; their sessions were signed out.")
            if generated:
                print(f"Password (shown once): {pw}")
        elif args.command in ("user-disable", "user-enable"):
            active = args.command == "user-enable"
            if not await accounts.set_active(args.email, active):
                print(f"No account for {args.email}.")
                return 1
            print(f"{'Enabled' if active else 'Disabled (and signed out)'} {args.email}.")
        elif args.command == "user-limit":
            limit = None if args.default else args.daily_tokens
            row = await appdb.fetch_one("UPDATE app.users SET daily_token_limit = %s WHERE email = %s RETURNING id",
                                        (limit, accounts.normalize_email(args.email)))
            if not row:
                print(f"No account for {args.email}.")
                return 1
            print(f"Daily token limit for {args.email}: {limit if limit is not None else 'server default'}.")
    except psycopg.errors.UniqueViolation:
        print(f"An account for {args.email} already exists.")
        return 1
    except (ValueError, psycopg.errors.CheckViolation) as e:
        print(f"Invalid input: {e}")
        return 1
    except psycopg.OperationalError as e:
        print(f"Can't reach the database as bgpt_app ({e}). Run `make db-up`; check APP_DATABASE_URL.")
        return 1
    finally:
        await appdb.close_pool()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="manage.py", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    add = sub.add_parser("user-add", help="create an account")
    add.add_argument("--email", required=True)
    add.add_argument("--name", required=True)
    add.add_argument("--admin", action="store_true")
    add.add_argument("--daily-tokens", type=int, help="override the server's daily token allowance")
    add.add_argument("--generate-password", action="store_true", help="generate a password and print it once")
    sub.add_parser("user-list", help="list accounts with their last-24h token use")
    pw = sub.add_parser("user-passwd", help="set a new password (signs the user out)")
    pw.add_argument("--email", required=True)
    pw.add_argument("--generate-password", action="store_true")
    for name in ("user-disable", "user-enable"):
        sub.add_parser(name).add_argument("--email", required=True)
    lim = sub.add_parser("user-limit", help="set a user's daily token allowance")
    lim.add_argument("--email", required=True)
    g = lim.add_mutually_exclusive_group(required=True)
    g.add_argument("--daily-tokens", type=int)
    g.add_argument("--default", action="store_true", help="use the server default (CHAT_DAILY_TOKENS)")
    return asyncio.run(_run(parser.parse_args(argv)))


if __name__ == "__main__":
    sys.exit(main())
