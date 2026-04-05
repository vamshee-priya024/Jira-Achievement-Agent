# src/rate_limiter.py
#
# Token budget system — keeps your API costs predictable and under control.
#
# WHY TOKEN BUDGETING?
# LLM APIs charge per token. Without a budget, a bug or bad data
# could cause runaway costs. This module acts as a safety valve:
# estimate usage before each call, track cumulative usage per week,
# and refuse to proceed if you'd exceed your budget.
#
# REAL WORLD PATTERN:
# This is exactly how teams manage LLM costs in production —
# Anthropic, OpenAI, and Google all recommend client-side budgeting
# in addition to their own hard limits.

import sqlite3
import os
from datetime import datetime, timedelta


# ─────────────────────────────────────────────
# CONFIG — adjust these to your comfort level
# ─────────────────────────────────────────────

# Weekly token limits — change these in .env to override
# Defaults are conservative for a free/starter tier account
DEFAULT_WEEKLY_INPUT_LIMIT  = int(os.environ.get("WEEKLY_INPUT_TOKEN_LIMIT",  "50000"))
DEFAULT_WEEKLY_OUTPUT_LIMIT = int(os.environ.get("WEEKLY_OUTPUT_TOKEN_LIMIT", "20000"))

# Claude Haiku pricing (per million tokens) — used for cost estimation
HAIKU_INPUT_COST_PER_M  = 0.80   # $0.80 per million input tokens
HAIKU_OUTPUT_COST_PER_M = 4.00   # $4.00 per million output tokens

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "achievements.db")


# ─────────────────────────────────────────────
# TOKEN ESTIMATION
# ─────────────────────────────────────────────

def estimate_tokens(text: str) -> int:
    """
    Estimates token count from a string.

    WHY NOT USE A REAL TOKENIZER?
    The exact tokenizer (tiktoken for OpenAI, Anthropic's own) requires
    an extra library and adds complexity. For budgeting purposes, the
    "1 token ≈ 4 characters" rule is accurate enough — it's the same
    approximation Anthropic uses in their own documentation.

    For English text it typically overestimates by ~10%, which is
    actually what you want for a safety budget — better to be
    slightly conservative than to undercount.
    """
    return max(1, len(text) // 4)


def estimate_call_cost(prompt: str, max_output_tokens: int = 1000) -> dict:
    """
    Estimates the cost of a single API call before making it.
    Returns a dict with token counts and dollar cost estimate.
    """
    input_tokens  = estimate_tokens(prompt)
    output_tokens = max_output_tokens   # worst case — actual usage is usually less

    input_cost  = (input_tokens  / 1_000_000) * HAIKU_INPUT_COST_PER_M
    output_cost = (output_tokens / 1_000_000) * HAIKU_OUTPUT_COST_PER_M

    return {
        "input_tokens":  input_tokens,
        "output_tokens": output_tokens,
        "total_tokens":  input_tokens + output_tokens,
        "estimated_cost": round(input_cost + output_cost, 6),
    }


# ─────────────────────────────────────────────
# DB SETUP
# ─────────────────────────────────────────────

def init_usage_table():
    """
    Creates the token_usage table if it doesn't exist.
    Called once at startup alongside init_db().

    One row per API call — gives you a full audit trail
    of every call made, when, for which ticket, and how many tokens used.
    """
    conn   = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS token_usage (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            week_start     TEXT NOT NULL,
            ticket_key     TEXT,
            input_tokens   INTEGER DEFAULT 0,
            output_tokens  INTEGER DEFAULT 0,
            total_tokens   INTEGER DEFAULT 0,
            estimated_cost REAL DEFAULT 0,
            called_at      TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    conn.close()


# ─────────────────────────────────────────────
# USAGE TRACKING
# ─────────────────────────────────────────────

def get_week_start() -> str:
    """Returns Monday of current week as YYYY-MM-DD."""
    today  = datetime.now()
    monday = today - timedelta(days=today.weekday())
    return monday.strftime("%Y-%m-%d")


def get_weekly_usage(week_start: str = None) -> dict:
    """
    Returns cumulative token usage for the current (or given) week.
    This is what we check before each API call.
    """
    week = week_start or get_week_start()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT
            COALESCE(SUM(input_tokens), 0)   as input_tokens,
            COALESCE(SUM(output_tokens), 0)  as output_tokens,
            COALESCE(SUM(total_tokens), 0)   as total_tokens,
            COALESCE(SUM(estimated_cost), 0) as estimated_cost,
            COUNT(*)                         as api_calls
        FROM token_usage
        WHERE week_start = ?
    """, (week,))
    row = cursor.fetchone()
    conn.close()
    return {
        "week_start":     week,
        "input_tokens":   row[0],
        "output_tokens":  row[1],
        "total_tokens":   row[2],
        "estimated_cost": round(row[3], 6),
        "api_calls":      row[4],
    }


def record_usage(ticket_key: str, input_tokens: int, output_tokens: int, cost: float):
    """
    Records actual token usage after a successful API call.
    Called by summarizer.py after each call returns.
    """
    week   = get_week_start()
    conn   = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO token_usage (week_start, ticket_key, input_tokens, output_tokens, total_tokens, estimated_cost)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (week, ticket_key, input_tokens, output_tokens, input_tokens + output_tokens, cost))
    conn.commit()
    conn.close()


# ─────────────────────────────────────────────
# BUDGET GUARD
# ─────────────────────────────────────────────

def check_budget(prompt: str, ticket_key: str = "") -> dict:
    """
    Main function — call this BEFORE every API call.

    Returns a dict with:
      allowed  → True/False — whether to proceed
      reason   → human-readable explanation if blocked
      estimate → token/cost estimate for this call
      usage    → current weekly usage totals

    WHY RETURN A DICT INSTEAD OF RAISING?
    Raising an exception would abort the whole run.
    Returning a dict lets the caller decide — skip this ticket
    and continue with the rest, or abort entirely.
    That's more useful behavior for a weekly batch job.
    """
    estimate      = estimate_call_cost(prompt)
    current_usage = get_weekly_usage()

    projected_input  = current_usage["input_tokens"]  + estimate["input_tokens"]
    projected_output = current_usage["output_tokens"] + estimate["output_tokens"]

    # Check input token budget
    if projected_input > DEFAULT_WEEKLY_INPUT_LIMIT:
        return {
            "allowed": False,
            "reason":  (
                f"Weekly input token budget exceeded.\n"
                f"   Budget : {DEFAULT_WEEKLY_INPUT_LIMIT:,} tokens\n"
                f"   Used   : {current_usage['input_tokens']:,} tokens\n"
                f"   This call would add: ~{estimate['input_tokens']:,} tokens\n"
                f"   To increase limit, set WEEKLY_INPUT_TOKEN_LIMIT in .env"
            ),
            "estimate": estimate,
            "usage":    current_usage,
        }

    # Check output token budget
    if projected_output > DEFAULT_WEEKLY_OUTPUT_LIMIT:
        return {
            "allowed": False,
            "reason":  (
                f"Weekly output token budget exceeded.\n"
                f"   Budget : {DEFAULT_WEEKLY_OUTPUT_LIMIT:,} tokens\n"
                f"   Used   : {current_usage['output_tokens']:,} tokens\n"
                f"   To increase limit, set WEEKLY_OUTPUT_TOKEN_LIMIT in .env"
            ),
            "estimate": estimate,
            "usage":    current_usage,
        }

    return {
        "allowed":  True,
        "reason":   "",
        "estimate": estimate,
        "usage":    current_usage,
    }


def print_usage_report():
    """Prints a formatted weekly usage report. Called at end of each run."""
    usage = get_weekly_usage()
    if usage["api_calls"] == 0:
        return

    pct_input  = (usage["input_tokens"]  / DEFAULT_WEEKLY_INPUT_LIMIT)  * 100
    pct_output = (usage["output_tokens"] / DEFAULT_WEEKLY_OUTPUT_LIMIT) * 100

    print(f"\n{'─' * 58}")
    print(f"  💰 TOKEN USAGE — Week of {usage['week_start']}")
    print(f"{'─' * 58}")
    print(f"  API calls      : {usage['api_calls']}")
    print(f"  Input tokens   : {usage['input_tokens']:,} / {DEFAULT_WEEKLY_INPUT_LIMIT:,} ({pct_input:.1f}%)")
    print(f"  Output tokens  : {usage['output_tokens']:,} / {DEFAULT_WEEKLY_OUTPUT_LIMIT:,} ({pct_output:.1f}%)")
    print(f"  Est. cost      : ${usage['estimated_cost']:.4f}")

    # Visual budget bar
    bar_input  = int(pct_input  / 5)  # 20 chars = 100%
    bar_output = int(pct_output / 5)
    print(f"\n  Input  [{'█' * bar_input}{'░' * (20 - bar_input)}] {pct_input:.0f}%")
    print(f"  Output [{'█' * bar_output}{'░' * (20 - bar_output)}] {pct_output:.0f}%")