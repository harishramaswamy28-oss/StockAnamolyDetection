"""Password and opaque-cookie session helpers for application users."""

import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, Request

from database.connection import get_connection


SESSION_COOKIE = "stock_session"
SESSION_DAYS = 7
SCRYPT_N = 2**14


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=SCRYPT_N, r=8, p=1, dklen=64)
    return f"scrypt${SCRYPT_N}$8$1${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str | None) -> bool:
    if not stored:
        return False
    try:
        algorithm, n, r, p, salt_hex, digest_hex = stored.split("$")
        if algorithm != "scrypt":
            return False
        computed = hashlib.scrypt(
            password.encode("utf-8"), salt=bytes.fromhex(salt_hex),
            n=int(n), r=int(r), p=int(p), dklen=len(bytes.fromhex(digest_hex)),
        )
        return hmac.compare_digest(computed, bytes.fromhex(digest_hex))
    except (ValueError, TypeError):
        return False


def issue_session(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode("ascii")).hexdigest()
    expires_at = datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS)
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM app_session WHERE expires_at <= now()")
            cursor.execute(
                "INSERT INTO app_session(token_hash, user_id, expires_at) VALUES (%s, %s, %s)",
                (token_hash, user_id, expires_at),
            )
        connection.commit()
    return token


def revoke_session(token: str | None) -> None:
    if not token:
        return
    token_hash = hashlib.sha256(token.encode("ascii")).hexdigest()
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM app_session WHERE token_hash = %s", (token_hash,))
        connection.commit()


def get_current_user(request: Request):
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(status_code=401, detail="Please sign in to continue.")
    token_hash = hashlib.sha256(token.encode("ascii", errors="ignore")).hexdigest()
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """SELECT u.user_id, u.name, u.email
                   FROM app_session s JOIN app_user u USING (user_id)
                   WHERE s.token_hash = %s AND s.expires_at > now()""",
                (token_hash,),
            )
            row = cursor.fetchone()
    if row is None:
        raise HTTPException(status_code=401, detail="Your session has expired. Please sign in again.")
    return {"user_id": row[0], "name": row[1], "email": row[2]}


def require_matching_user(user_id: int, current_user=Depends(get_current_user)):
    if user_id != current_user["user_id"]:
        # 404 avoids confirming another account's existence.
        raise HTTPException(status_code=404, detail="Record not found.")
    return current_user
