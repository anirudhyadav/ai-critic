"""
demo/api.py — API request handlers
NOTE: This file is intentionally insecure for aicritic demo purposes.
"""
import os
import pickle
import sqlite3

DB_PATH = "app.db"


def get_user(user_id: str) -> dict:
    conn = sqlite3.connect(DB_PATH)
    # SQL injection: user_id is embedded directly in the query
    query = f"SELECT id, name, email FROM users WHERE id = {user_id}"
    row = conn.execute(query).fetchone()
    return {"id": row[0], "name": row[1], "email": row[2]} if row else {}


def search_users(term: str) -> list:
    conn = sqlite3.connect(DB_PATH)
    # SQL injection via LIKE clause
    query = f"SELECT name, email FROM users WHERE name LIKE '%{term}%'"
    return conn.execute(query).fetchall()


def get_admin_panel(request_token: str) -> dict:
    # Missing authentication check — any token (or no token) is accepted
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT * FROM admin_config").fetchall()
    return {"config": rows}


def load_user_preferences(blob: bytes) -> dict:
    # Insecure deserialization: pickle.loads on untrusted data allows
    # arbitrary code execution
    return pickle.loads(blob)


def serve_file(filename: str) -> str:
    # Path traversal: ../../etc/passwd would bypass the intended base_dir
    base_dir = "/var/app/static"
    file_path = os.path.join(base_dir, filename)
    with open(file_path, "r") as fh:
        return fh.read()


def run_report_filter(user_query: str) -> list:
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT * FROM reports").fetchall()
    # eval() on user-supplied input — remote code execution
    filter_fn = eval(f"lambda row: {user_query}")
    return [row for row in rows if filter_fn(row)]
