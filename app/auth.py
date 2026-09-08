"""
Arcane Panel — Authentication
PBKDF2-SHA256 with high iteration count, secure session cookies,
brute-force protection.
"""
import hashlib
import secrets
import time
import re
from typing import Optional, Tuple

from fastapi import HTTPException, Request
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

from . import config
from .storage import get_db, log_audit


def hash_password(password: str, salt: Optional[str] = None) -> dict:
    salt = salt or secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        iterations=600_000,
    )
    return {"hash": dk.hex(), "salt": salt}


def verify_password(password: str, salt: str, expected_hash: str) -> bool:
    dk = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        iterations=600_000,
    )
    return secrets.compare_digest(dk.hex(), expected_hash)


def validate_password(password: str) -> Tuple[bool, str]:
    if len(password) < config.MIN_PASSWORD_LEN:
        return False, f"password-too-short: minimum {config.MIN_PASSWORD_LEN} characters"
    if config.REQUIRE_LOWERCASE and not re.search(r"[a-z]", password):
        return False, "password-needs-lowercase"
    if config.REQUIRE_UPPERCASE and not re.search(r"[A-Z]", password):
        return False, "password-needs-uppercase"
    if config.REQUIRE_DIGIT and not re.search(r"[0-9]", password):
        return False, "password-needs-digit"
    if config.REQUIRE_SPECIAL and not re.search(rf"[{re.escape(config.SPECIAL_CHARS)}]", password):
        return False, "password-needs-special-character"
    if len(password) > 256:
        return False, "password-too-long"
    return True, ""


def get_serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(config.SECRET_KEY, salt="arcane-session-v1")


def create_session_token(username: str, password_hash_prefix: str) -> str:
    return get_serializer().dumps({
        "u": username,
        "v": password_hash_prefix,
        "iat": int(time.time()),
    })


def verify_session_token(token: str) -> Optional[str]:
    try:
        data = get_serializer().loads(token, max_age=config.SESSION_MAX_AGE)
        return data.get("u")
    except (BadSignature, SignatureExpired):
        return None


def set_session_cookie(response, request: Request, username: str, password_hash_prefix: str):
    token = create_session_token(username, password_hash_prefix)
    response.set_cookie(
        config.SESSION_COOKIE,
        token,
        max_age=config.SESSION_MAX_AGE,
        httponly=True,
        samesite="strict",
        secure=(request.url.scheme == "https") or not config.DEBUG,
        path="/",
    )


def clear_session_cookie(response):
    response.delete_cookie(
        config.SESSION_COOKIE,
        path="/",
        samesite="strict",
    )


async def check_login_lock(ip: str) -> Optional[int]:
    async with get_db() as db:
        async with db.execute(
            "SELECT locked_until FROM login_attempts WHERE ip = ?", (ip,)
        ) as cursor:
            row = await cursor.fetchone()
            if row is None:
                return None
            locked_until = row[0]
            if locked_until > time.time():
                return int(locked_until - time.time())
            return None


async def record_login_attempt(ip: str, success: bool):
    async with get_db() as db:
        if success:
            await db.execute("DELETE FROM login_attempts WHERE ip = ?", (ip,))
        else:
            await db.execute(
                "INSERT INTO login_attempts (ip, count, locked_until) VALUES (?, 1, 0) "
                "ON CONFLICT(ip) DO UPDATE SET "
                "count = count + 1, "
                "locked_until = CASE WHEN count + 1 >= ? THEN ? + ? ELSE locked_until END",
                (ip, config.LOGIN_MAX_ATTEMPTS, time.time(), config.LOGIN_LOCK_SECONDS),
            )
        await db.commit()


async def verify_admin_credentials(username: str, password: str) -> Optional[dict]:
    async with get_db() as db:
        async with db.execute(
            "SELECT username, password_hash, salt FROM admin WHERE id = 1"
        ) as cursor:
            row = await cursor.fetchone()
            if row is None:
                return None
            if row[0] != username:
                return None
            if not verify_password(password, row[2], row[1]):
                return None
            return {"username": row[0], "password_hash": row[1], "salt": row[2]}


async def require_auth(request: Request) -> str:
    token = request.cookies.get(config.SESSION_COOKIE)
    if not token:
        raise HTTPException(401, "not-authenticated")
    username = verify_session_token(token)
    if not username:
        raise HTTPException(401, "session-expired")
    async with get_db() as db:
        async with db.execute(
            "SELECT password_hash FROM admin WHERE id = 1"
        ) as cursor:
            row = await cursor.fetchone()
            if row is None:
                raise HTTPException(401, "admin-not-configured")
            try:
                data = get_serializer().loads(token, max_age=config.SESSION_MAX_AGE)
                if data.get("v") != row[0][:12]:
                    raise HTTPException(401, "session-invalidated")
            except (BadSignature, SignatureExpired):
                raise HTTPException(401, "session-expired")
    return username


def get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
