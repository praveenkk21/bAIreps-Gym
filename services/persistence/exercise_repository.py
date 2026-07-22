import sqlite3
import streamlit as st
from pathlib import Path
import os
import tempfile
import bcrypt

if os.getenv("STREAMLIT_SERVER_HEADLESS") == "true":
    _DB_PATH = os.path.join(tempfile.gettempdir(), "data.db")
else:
    _DB_PATH = str(Path(__file__).parent.parent.parent / "data.db")


@st.cache_resource
def _get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = _get_connection()

    with conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                username      TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL DEFAULT '',
                google_id     TEXT UNIQUE,
                email         TEXT,
                created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        # migrate existing databases that lack newer columns
        cols = {row[1] for row in conn.execute("PRAGMA table_info(users)")}
        if "password_hash" not in cols:
            conn.execute("ALTER TABLE users ADD COLUMN password_hash TEXT NOT NULL DEFAULT ''")
        if "google_id" not in cols:
            conn.execute("ALTER TABLE users ADD COLUMN google_id TEXT")
        if "email" not in cols:
            conn.execute("ALTER TABLE users ADD COLUMN email TEXT")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS exercises (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id       INTEGER NOT NULL REFERENCES users(id),
                exercise_name TEXT    NOT NULL,
                reps          INTEGER NOT NULL DEFAULT 0,
                sets          INTEGER NOT NULL DEFAULT 0,
                time          INTEGER NOT NULL DEFAULT 0,
                created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )


def get_user(username: str) -> sqlite3.Row:
    conn = _get_connection()

    return conn.execute(
        "SELECT * FROM users WHERE username = ?", (username,)
    ).fetchone()


def create_user(username: str, password: str) -> sqlite3.Row:
    conn = _get_connection()
    password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    with conn:
        conn.execute(
            "INSERT INTO users (username, password_hash) VALUES (?, ?)",
            (username, password_hash),
        )

    return get_user(username)


def verify_user(username: str, password: str) -> sqlite3.Row | None:
    user = get_user(username)
    if user is None:
        return None
    if not user["password_hash"] or not bcrypt.checkpw(password.encode(), user["password_hash"].encode()):
        return None
    return user


def get_or_create_google_user(google_id: str, email: str, name: str) -> sqlite3.Row:
    conn = _get_connection()
    user = conn.execute(
        "SELECT * FROM users WHERE google_id = ?", (google_id,)
    ).fetchone()
    if user is not None:
        return user

    # derive a unique username from the Google display name
    base = name.replace(" ", "_").lower() or email.split("@")[0]
    username = base
    suffix = 1
    while conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone():
        username = f"{base}_{suffix}"
        suffix += 1

    with conn:
        conn.execute(
            "INSERT INTO users (username, password_hash, google_id, email) VALUES (?, '', ?, ?)",
            (username, google_id, email),
        )
    return conn.execute("SELECT * FROM users WHERE google_id = ?", (google_id,)).fetchone()


def add_exercise(user_id, exercise_name, reps, sets, time):
    conn = _get_connection()

    with conn:
        existing = conn.execute("""
            SELECT * FROM exercises 
            WHERE user_id = ? AND exercise_name = ? AND Date('created_at') = Date('now')
        """, (user_id, exercise_name)).fetchone()

        if existing:
            conn.execute("""
                UPDATE exercises 
                SET reps = reps + ?, sets = sets + ?, time = time + ?
                WHERE id = ?
            """, (reps, sets, time, existing['id']))
        else:
            conn.execute("""
                INSERT INTO exercises (user_id, exercise_name, sets, reps, time)
                VALUES (?, ?, ?, ?, ?)
            """, (user_id, exercise_name, sets, reps, time))


def get_users_exercises(user_id):
    conn = _get_connection()

    return conn.execute("""
        SELECT * FROM exercises 
        WHERE user_id = ?
    """, (user_id,)).fetchall()
