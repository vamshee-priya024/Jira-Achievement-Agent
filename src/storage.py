# src/storage.py
#
# Handles all database operations for the achievement agent.
# Uses SQLite — a file-based database built into Python's standard library.
#
# WHY SQLITE?
# - Zero setup — no server, no install, just a .db file on disk
# - Built into Python — no extra pip install needed
# - Perfect for single-user tools like this agent
# - Easy to inspect with free tools like DB Browser for SQLite
# - When/if you outgrow it, migrating to Postgres is straightforward
#
# THE FILE: achievements.db is created automatically in your project root
# on first run. You can open it in DB Browser for SQLite to browse your data.
# Download DB Browser free at: https://sqlitebrowser.org

import sqlite3
import json
import os
from datetime import datetime, timedelta


# ─────────────────────────────────────────────
# DB PATH
# ─────────────────────────────────────────────

# Store the DB file in the project root (one level up from src/)
# __file__ is this file's path, so we navigate up to find the root
DB_PATH = os.path.join(os.path.dirname(__file__), "..", "achievements.db")


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def get_week_start(date_str: str = None) -> str:
    """
    Returns the Monday of the current week as "YYYY-MM-DD".

    WHY NORMALIZE TO MONDAY?
    If you run the agent on Wednesday, Friday, and Saturday of the same week,
    all three runs should be grouped under the same week.
    Anchoring to Monday makes weekly queries simple:
      SELECT * FROM achievements WHERE week_start = '2026-03-30'

    If date_str is provided (e.g. from a ticket's resolution_date),
    we return the Monday of THAT week instead.
    """
    if date_str:
        # Parse the date string — Jira uses ISO format with timezone
        # We strip the timezone part and just use the date
        date_part = date_str[:10]   # "2026-03-31T10:00:00+0000" → "2026-03-31"
        date      = datetime.strptime(date_part, "%Y-%m-%d")
    else:
        date = datetime.now()

    # weekday() returns 0=Monday, 1=Tuesday ... 6=Sunday
    # Subtracting weekday() days brings us back to Monday
    monday = date - timedelta(days=date.weekday())
    return monday.strftime("%Y-%m-%d")


# ─────────────────────────────────────────────
# SETUP
# ─────────────────────────────────────────────

def init_db():
    """
    Creates the database and achievements table if they don't exist yet.
    Safe to call every time the agent runs — IF NOT EXISTS means it's a no-op
    if the table already exists.

    SQLITE DATA TYPES:
    SQLite uses loose typing — TEXT, INTEGER, REAL are the main ones.
    We store labels (a Python list) as a JSON string in TEXT column,
    and deserialize it back to a list when we read it out.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS achievements (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_key    TEXT NOT NULL,
            week_start    TEXT NOT NULL,
            summary       TEXT,
            achievement   TEXT,
            brag_bullet   TEXT,
            theme         TEXT,
            impact_level  TEXT,
            story_points  INTEGER DEFAULT 0,
            priority      TEXT,
            labels        TEXT,    -- stored as JSON string e.g. '["auth", "backend"]'
            url           TEXT,
            created_at    TEXT DEFAULT (datetime('now')),

            -- Composite unique key: one row per ticket per week
            -- UNIQUE constraint enables upsert behavior —
            -- if you run the agent twice in the same week for the same ticket,
            -- it updates rather than creating a duplicate
            UNIQUE(ticket_key, week_start)
        )
    """)

    conn.commit()
    conn.close()
    print(f"   📦 Database ready: {os.path.abspath(DB_PATH)}")


# ─────────────────────────────────────────────
# WRITE
# ─────────────────────────────────────────────

def save_tickets(enriched_tickets: list[dict]) -> int:
    """
    Saves a list of enriched ticket dicts to the database.
    Returns the number of rows saved.

    UPSERT PATTERN — "INSERT OR REPLACE":
    If a row with the same (ticket_key, week_start) already exists,
    SQLite replaces it entirely with the new data.
    This means running the agent twice in the same week is safe —
    you get updated summaries, not duplicate rows.

    This is the SQLite equivalent of Postgres's "ON CONFLICT DO UPDATE".
    """
    if not enriched_tickets:
        return 0

    week_start = get_week_start()   # Monday of current week
    conn       = sqlite3.connect(DB_PATH)
    cursor     = conn.cursor()
    saved      = 0

    for ticket in enriched_tickets:
        cursor.execute("""
            INSERT OR REPLACE INTO achievements (
                ticket_key, week_start, summary, achievement,
                brag_bullet, theme, impact_level, story_points,
                priority, labels, url
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            ticket.get("key", ""),
            week_start,
            ticket.get("summary", ""),
            ticket.get("achievement", ""),
            ticket.get("brag_bullet", ""),
            ticket.get("theme", "Other"),
            ticket.get("impact_level", "medium"),
            ticket.get("story_points") or 0,
            ticket.get("priority", ""),
            json.dumps(ticket.get("labels", [])),   # serialize list → JSON string
            ticket.get("url", ""),
        ))
        saved += 1

    conn.commit()
    conn.close()
    return saved


# ─────────────────────────────────────────────
# READ
# ─────────────────────────────────────────────

def get_weekly_achievements(week_start: str) -> list[dict]:
    """Fetch all achievements for a specific week. week_start = "YYYY-MM-DD" (Monday)"""
    return _query("SELECT * FROM achievements WHERE week_start = ?", (week_start,))


def get_date_range_achievements(from_date: str, to_date: str) -> list[dict]:
    """
    Fetch all achievements between two dates.
    This is the query that powers quarterly and annual rollups.

    Example:
      get_date_range_achievements("2025-10-01", "2025-12-31")  → Q4 achievements
      get_date_range_achievements("2025-01-01", "2025-12-31")  → full year
    """
    return _query(
        "SELECT * FROM achievements WHERE week_start BETWEEN ? AND ? ORDER BY week_start ASC",
        (from_date, to_date)
    )


def get_all_achievements() -> list[dict]:
    """Fetch every achievement ever saved — useful for annual reviews."""
    return _query("SELECT * FROM achievements ORDER BY week_start DESC")


def get_stats() -> dict:
    """
    Returns a summary of what's in the database.
    Great for a quick health check — how many weeks recorded, total points, etc.
    """
    conn   = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM achievements")
    total_tickets = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(DISTINCT week_start) FROM achievements")
    total_weeks = cursor.fetchone()[0]

    cursor.execute("SELECT SUM(story_points) FROM achievements")
    total_points = cursor.fetchone()[0] or 0

    cursor.execute("SELECT MIN(week_start), MAX(week_start) FROM achievements")
    date_range = cursor.fetchone()

    conn.close()

    return {
        "total_tickets": total_tickets,
        "total_weeks":   total_weeks,
        "total_points":  total_points,
        "from_date":     date_range[0],
        "to_date":       date_range[1],
    }


# ─────────────────────────────────────────────
# INTERNAL HELPER
# ─────────────────────────────────────────────

def _query(sql: str, params: tuple = ()) -> list[dict]:
    """
    Runs a SELECT query and returns results as a list of dicts.

    WHY DICTS INSTEAD OF TUPLES?
    sqlite3 by default returns rows as tuples — (value1, value2, ...).
    Setting row_factory = sqlite3.Row makes it return dict-like objects
    so you can access fields by name: row["ticket_key"] instead of row[0].
    Much more readable and less error-prone.
    """
    conn            = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row   # enables dict-style access
    cursor          = conn.cursor()

    cursor.execute(sql, params)
    rows = cursor.fetchall()
    conn.close()

    # Convert Row objects to plain dicts and deserialize labels JSON
    result = []
    for row in rows:
        d = dict(row)
        # Deserialize labels back from JSON string → Python list
        if d.get("labels"):
            try:
                d["labels"] = json.loads(d["labels"])
            except json.JSONDecodeError:
                d["labels"] = []
        result.append(d)

    return result