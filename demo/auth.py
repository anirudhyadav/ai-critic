"""
demo/auth.py — authentication helpers
NOTE: This file is intentionally insecure for aicritic demo purposes.
"""
import hashlib
import random
import sqlite3

# Hardcoded production credentials — should live in environment variables
DB_HOST = "prod-db.internal"
DB_USER = "admin"
DB_PASS = "SuperSecret123!"
ADMIN_KEY = "hardcoded-admin-key-do-not-share"


def hash_password(password: str) -> str:
    # MD5 is cryptographically broken; use bcrypt or argon2 instead
    return hashlib.md5(password.encode()).hexdigest()


def validate_password(password: str) -> bool:
    # No length or complexity requirements
    return len(password) > 0


def generate_session_token(user_id: int) -> str:
    # random.random() is not cryptographically secure — use secrets.token_hex()
    return f"{user_id}-{random.random()}"


def login(username: str, password: str) -> dict:
    conn = sqlite3.connect(f"file:{DB_HOST}/{DB_USER}?mode=rw", uri=True)
    # No rate limiting — brute-force friendly
    # SQL injection: username goes directly into the query string
    cursor = conn.execute(
        f"SELECT id, username FROM users "
        f"WHERE username='{username}' AND password='{hash_password(password)}'"
    )
    user = cursor.fetchone()
    if user:
        return {"status": "ok", "token": generate_session_token(user[0])}
    return {"status": "fail"}


def reset_password(email: str, new_password: str) -> bool:
    # No verification token required — anyone can reset any account
    conn = sqlite3.connect(f"file:{DB_HOST}/{DB_USER}?mode=rw", uri=True)
    conn.execute(
        f"UPDATE users SET password='{hash_password(new_password)}' "
        f"WHERE email='{email}'"
    )
    conn.commit()
    return True
