"""
SQLite persistence for scraped + geocoded De Anza events
and Campus Compass email subscribers.

Event tier/reason are NOT stored here because they are computed
per student profile by priority_agent.py.

Campus Compass does not require login. Students can optionally
subscribe with their email and profile information to receive
personalized event notifications.
"""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


DB_PATH = Path(__file__).parent / "events.db"


# ---------------------------------------------------------
# Events
# ---------------------------------------------------------

EVENTS_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    event_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    date TEXT,
    time TEXT,
    location TEXT,
    category TEXT,
    description TEXT,
    url TEXT,
    latitude REAL,
    longitude REAL,
    is_virtual INTEGER NOT NULL DEFAULT 0,
    match_type TEXT,
    scraped_at TEXT NOT NULL
);
"""


# ---------------------------------------------------------
# Email subscribers
# ---------------------------------------------------------

SUBSCRIBERS_SCHEMA = """
CREATE TABLE IF NOT EXISTS subscribers (
    email TEXT PRIMARY KEY,
    year TEXT,
    major TEXT,
    interests TEXT,
    notifications_enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""

# ---------------------------------------------------------
# Users
# ---------------------------------------------------------

USERS_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    year TEXT,
    major TEXT,
    interests TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


def get_connection() -> sqlite3.Connection:
    """
    Open the Campus Compass SQLite database and make sure
    all required tables exist.
    """

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    conn.execute(EVENTS_SCHEMA)
    conn.execute(SUBSCRIBERS_SCHEMA)
    conn.execute(USERS_SCHEMA)

    return conn


# =========================================================
# EVENT FUNCTIONS
# =========================================================

def _event_id(ev: dict) -> str:
    """
    De Anza event ids normally live in the detail URL (?id=12345).

    Events without an id use title + date as a stable fallback key.
    """

    url = ev.get("url") or ""

    if "id=" in url:
        return url.split("id=")[-1]

    return f"{ev.get('title', '')}|{ev.get('date', '')}"


def save_events(events: list[dict], scraped_at: str) -> None:
    """
    Replace the current event dataset with a fresh scrape.
    """

    conn = get_connection()

    with conn:
        conn.execute("DELETE FROM events")

        conn.executemany(
            """
            INSERT INTO events (
                event_id,
                title,
                date,
                time,
                location,
                category,
                description,
                url,
                latitude,
                longitude,
                is_virtual,
                match_type,
                scraped_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    _event_id(ev),
                    ev.get("title"),
                    ev.get("date"),
                    ev.get("time"),
                    ev.get("location"),
                    ev.get("category"),
                    ev.get("description"),
                    ev.get("url"),
                    ev.get("latitude"),
                    ev.get("longitude"),
                    1 if ev.get("is_virtual") else 0,
                    ev.get("match_type"),
                    scraped_at,
                )
                for ev in events
            ],
        )

    conn.close()


def load_events() -> list[dict] | None:
    """
    Load all scraped events.

    Returns None when the database has not been populated yet.
    """

    conn = get_connection()

    rows = conn.execute(
        """
        SELECT *
        FROM events
        ORDER BY date IS NULL, date
        """
    ).fetchall()

    conn.close()

    if not rows:
        return None

    events = []

    for row in rows:
        ev = dict(row)
        ev["is_virtual"] = bool(ev["is_virtual"])
        events.append(ev)

    return events


def distinct_categories() -> list[str]:
    """
    Return the real De Anza event categories found during scraping.
    """

    conn = get_connection()

    rows = conn.execute(
        """
        SELECT DISTINCT category
        FROM events
        WHERE category IS NOT NULL
          AND category != ''
        ORDER BY category
        """
    ).fetchall()

    conn.close()

    return [row["category"] for row in rows]


def last_scraped_at() -> str | None:
    """
    Return the timestamp of the most recent scrape.
    """

    conn = get_connection()

    row = conn.execute(
        """
        SELECT scraped_at
        FROM events
        LIMIT 1
        """
    ).fetchone()

    conn.close()

    return row["scraped_at"] if row else None


# =========================================================
# SUBSCRIBER FUNCTIONS
# =========================================================

def save_subscriber(
    email: str,
    year: str = "",
    major: str = "",
    interests: list[str] | None = None,
) -> None:
    """
    Create or update an email subscriber.

    If the email already exists, update the student's profile
    and turn notifications back on.
    """

    if interests is None:
        interests = []

    email = email.strip().lower()

    now = datetime.now(timezone.utc).isoformat()

    conn = get_connection()

    with conn:
        conn.execute(
            """
            INSERT INTO subscribers (
                email,
                year,
                major,
                interests,
                notifications_enabled,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, 1, ?, ?)

            ON CONFLICT(email) DO UPDATE SET
                year = excluded.year,
                major = excluded.major,
                interests = excluded.interests,
                notifications_enabled = 1,
                updated_at = excluded.updated_at
            """,
            (
                email,
                year,
                major,
                json.dumps(interests, ensure_ascii=False),
                now,
                now,
            ),
        )

    conn.close()


def unsubscribe(email: str) -> None:
    """
    Disable email notifications without deleting subscriber data.
    """

    email = email.strip().lower()

    conn = get_connection()

    with conn:
        conn.execute(
            """
            UPDATE subscribers
            SET
                notifications_enabled = 0,
                updated_at = ?
            WHERE email = ?
            """,
            (
                datetime.now(timezone.utc).isoformat(),
                email,
            ),
        )

    conn.close()


def load_active_subscribers() -> list[dict]:
    """
    Return every student who currently has email notifications enabled.
    """

    conn = get_connection()

    rows = conn.execute(
        """
        SELECT *
        FROM subscribers
        WHERE notifications_enabled = 1
        ORDER BY created_at
        """
    ).fetchall()

    conn.close()

    subscribers = []

    for row in rows:
        subscriber = dict(row)

        try:
            subscriber["interests"] = json.loads(
                subscriber.get("interests") or "[]"
            )
        except (json.JSONDecodeError, TypeError):
            subscriber["interests"] = []

        subscriber["notifications_enabled"] = bool(
            subscriber["notifications_enabled"]
        )

        subscribers.append(subscriber)

    return subscribers


def get_subscriber(email: str) -> dict | None:
    """
    Return one subscriber by email.
    """

    email = email.strip().lower()

    conn = get_connection()

    row = conn.execute(
        """
        SELECT *
        FROM subscribers
        WHERE email = ?
        """,
        (email,),
    ).fetchone()

    conn.close()

    if not row:
        return None

    subscriber = dict(row)

    try:
        subscriber["interests"] = json.loads(
            subscriber.get("interests") or "[]"
        )
    except (json.JSONDecodeError, TypeError):
        subscriber["interests"] = []

    subscriber["notifications_enabled"] = bool(
        subscriber["notifications_enabled"]
    )

    return subscriber

def create_user(
    email: str,
    password_hash: str,
    year: str = "",
    major: str = "",
    interests: list[str] | None = None,
) -> dict:
    """
    Create a new Campus Compass user.
    """

    if interests is None:
        interests = []

    email = email.strip().lower()
    now = datetime.now(timezone.utc).isoformat()

    conn = get_connection()

    try:
        with conn:
            cursor = conn.execute(
                """
                INSERT INTO users (
                    email,
                    password_hash,
                    year,
                    major,
                    interests,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    email,
                    password_hash,
                    year,
                    major,
                    json.dumps(interests, ensure_ascii=False),
                    now,
                    now,
                ),
            )

        user_id = cursor.lastrowid

    finally:
        conn.close()

    return {
        "user_id": user_id,
        "email": email,
        "year": year,
        "major": major,
        "interests": interests,
    }


def get_user_by_email(email: str) -> dict | None:
    """
    Find a Campus Compass user by email.
    """

    email = email.strip().lower()

    conn = get_connection()

    row = conn.execute(
        """
        SELECT *
        FROM users
        WHERE email = ?
        """,
        (email,),
    ).fetchone()

    conn.close()

    if not row:
        return None

    user = dict(row)

    try:
        user["interests"] = json.loads(
            user.get("interests") or "[]"
        )
    except (json.JSONDecodeError, TypeError):
        user["interests"] = []

    return user

def update_user_profile(
    email: str,
    year: str,
    major: str,
    interests: list[str],
) -> None:
    """
    Update the profile for an existing Campus Compass user.
    """

    email = email.strip().lower()
    now = datetime.now(timezone.utc).isoformat()

    conn = get_connection()

    with conn:
        conn.execute(
            """
            UPDATE users
            SET
                year = ?,
                major = ?,
                interests = ?,
                updated_at = ?
            WHERE email = ?
            """,
            (
                year,
                major,
                json.dumps(interests, ensure_ascii=False),
                now,
                email,
            ),
        )

    conn.close()