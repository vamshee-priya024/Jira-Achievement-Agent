# src/main.py
#
# Entry point — orchestrates all phases.
# Phase 1: Fetch tickets from Jira
# Phase 2: Summarize with Claude  ← NEW
#
# Notice how main.py stays clean and readable.
# It doesn't know HOW fetching or summarizing works —
# it just calls the right module in the right order.
# This is the "Orchestrator" pattern.

import json
from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv())

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))  # adds src/ to Python's search path

from jira_client import JiraClient
from summarizer import summarize_tickets

# ─────────────────────────────────────────────
# DISPLAY HELPERS
# ─────────────────────────────────────────────

IMPACT_ICONS = {"high": "🔴", "medium": "🟡", "low": "🟢"}
THEME_ICONS  = {
    "Feature Delivery":  "🚀",
    "Bug Fix":           "🐛",
    "Infrastructure":    "⚙️",
    "Collaboration":     "🤝",
    "Tech Debt":         "🔧",
    "Other":             "📌",
}

def display_enriched_ticket(ticket: dict, index: int) -> None:
    theme_icon  = THEME_ICONS.get(ticket.get("theme", "Other"), "📌")
    impact_icon = IMPACT_ICONS.get(ticket.get("impact_level", "medium"), "🟡")

    print(f"\n  {index}. {impact_icon} [{ticket['key']}] {theme_icon} {ticket.get('theme', '')}")
    print(f"     {ticket['summary']}")
    if ticket.get("brag_bullet"):
        print(f"\n     ✍️  Brag bullet:")
        print(f"     → {ticket['brag_bullet']}")
    print(f"\n     Points: {ticket['story_points'] or '?'}  |  Priority: {ticket['priority'] or 'N/A'}")


def display_weekly_summary(enriched: list[dict]) -> None:
    """
    Groups tickets by theme and prints a digest —
    a preview of what the weekly email will look like in Phase 4.
    """
    from collections import defaultdict
    by_theme = defaultdict(list)
    for t in enriched:
        by_theme[t.get("theme", "Other")].append(t)

    total_points = sum(t.get("story_points") or 0 for t in enriched)

    print(f"\n{'═' * 58}")
    print(f"  📊 WEEKLY ACHIEVEMENT SUMMARY")
    print(f"{'═' * 58}")
    print(f"  Tickets closed : {len(enriched)}")
    print(f"  Story points   : {total_points}")
    print(f"  Themes covered : {len(by_theme)}")
    print(f"{'─' * 58}")

    for theme, tickets in sorted(by_theme.items()):
        icon = THEME_ICONS.get(theme, "📌")
        print(f"\n  {icon}  {theme.upper()} ({len(tickets)} tickets)")
        for t in tickets:
            impact = IMPACT_ICONS.get(t.get("impact_level", "medium"), "🟡")
            print(f"     {impact} {t['key']}: {t.get('achievement', t['summary'])}")

    print(f"\n{'═' * 58}")
    print("  📋 BRAG BULLETS (ready to paste into your 1:1 doc)")
    print(f"{'─' * 58}")
    high_first = sorted(enriched, key=lambda t: {"high": 0, "medium": 1, "low": 2}.get(t.get("impact_level"), 1))
    for t in high_first:
        if t.get("brag_bullet"):
            print(f"\n  • {t['brag_bullet']}")


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def main():
    print("🤖 Jira Achievement Agent — Phase 2")
    print("=" * 58)

    # ── Phase 1: Fetch ──────────────────────────────────────
    print("\n📡 Connecting to Jira...")
    client  = JiraClient()
    print(f"   Connected : {client.base_url}")
    print(f"   User      : {client.email}")

    print("\n🔍 Fetching resolved tickets (last 7 days)...")
    tickets = client.get_my_resolved_tickets(days_back=7)

    if not tickets:
        print("\n⚠️  No resolved tickets found. Try days_back=14 or check your JQL.")
        return

    # ── Phase 2: Summarize ──────────────────────────────────
    enriched = summarize_tickets(tickets)

    if not enriched:
        print("⚠️  Summarization returned no results. Check your ANTHROPIC_API_KEY.")
        return

    # ── Display ─────────────────────────────────────────────
    print(f"\n{'─' * 58}")
    print("  🎫 TICKET DETAILS")
    print(f"{'─' * 58}")
    for i, ticket in enumerate(enriched, 1):
        display_enriched_ticket(ticket, i)

    display_weekly_summary(enriched)

    # Raw JSON dump of first enriched ticket — useful for Phase 3 DB schema design
    print(f"\n\n{'─' * 58}")
    print("🔬 ENRICHED TICKET SCHEMA (first ticket) — for Phase 3:")
    print("─" * 58)
    print(json.dumps(enriched[0], indent=2))

    print(f"\n✅ Phase 2 complete.")
    print("   Next: Phase 3 — store this in SQLite + append to Notion brag doc.\n")


if __name__ == "__main__":
    main()