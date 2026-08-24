"""
Minimal SQLite persistence for scraped + geocoded De Anza events.

This replaces the plain JSON cache file (deanza_events_geocoded.json)
with a real, queryable database -- "최소 Database 도입", priority #2 on
the post-hackathon-review punch list (see PROJECT_LOG.md and the
progress-vs-plan notes).

Deliberately NOT stored here: tier/reason. Those are computed PER
STUDENT PROFILE by priority_agent.py on every /api/rerank call -- they
are not an intrinsic property of an event. Baking them into this table
would mean the next student with a different profile sees stale
priorities computed for someone else.

Also deliberately no Users/Preferences/SavedEvents tables yet. Per the
plan, Login is a lower priority than this, and the product direction
right now is explicitly "no login required" -- a student sets their
year/major/interests once and the browser remembers it (see
localStorage usage in campus_map_prototype.html) instead of needing an
account. If/when real accounts get built, those tables belong here.
"""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "events.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    event_id TEXT PRIMARY KEY,   -- De Anza's own event id (from the URL), or a
                                  -- title+date fallback key for events with none
    title TEXT NOT NULL,
    date TEXT,
    time TEXT,
    location TEXT,
    category TEXT,               -- only populated for events from the list page
    description TEXT,
    url TEXT,
    latitude REAL,
    longitude REAL,
    is_virtual INTEGER NOT NULL DEFAULT 0,
    match_type TEXT,
    scraped_at TEXT NOT NULL
);
"""


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute(SCHEMA)
    return conn


def _event_id(ev: dict) -> str:
    """De Anza event ids live in the detail URL (?id=12345). A handful of
    events (holidays, generic deadlines) have no url at all, so those get
    a stable fallback key instead of colliding on an empty string."""
    url = ev.get("url") or ""
    if "id=" in url:
        return url.split("id=")[-1]
    return f"{ev.get('title', '')}|{ev.get('date', '')}"


def save_events(events: list[dict], scraped_at: str) -> None:
    """Full refresh: wipes and re-inserts. The dataset is small (a few
    dozen events) and always comes from one fresh scrape, so there's no
    need for incremental upsert logic here."""
    conn = get_connection()
    with conn:
        conn.execute("DELETE FROM events")
        conn.executemany(
            """
            INSERT INTO events (
                event_id, title, date, time, location, category,
                description, url, latitude, longitude, is_virtual,
                match_type, scraped_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
    """Returns None if nothing has been scraped into the DB yet (caller
    should trigger a scrape in that case)."""
    conn = get_connection()
    rows = conn.execute("SELECT * FROM events ORDER BY date IS NULL, date").fetchall()
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
    """Real category labels actually seen in scraped events (only the
    De Anza list-page template provides these -- month-grid events have
    none). Used to offer students real categories instead of guessed ones."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT DISTINCT category FROM events WHERE category IS NOT NULL AND category != '' ORDER BY category"
    ).fetchall()
    conn.close()
    return [row["category"] for row in rows]


def last_scraped_at() -> str | None:
    conn = get_connection()
    row = conn.execute("SELECT scraped_at FROM events LIMIT 1").fetchone()
    conn.close()
    return row["scraped_at"] if row else None
