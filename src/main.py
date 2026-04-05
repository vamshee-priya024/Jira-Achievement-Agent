# src/main.py — Phase 3 with rate limiting

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv())

from jira_client  import JiraClient
from summarizer   import summarize_tickets
from storage      import init_db, save_tickets, get_stats, get_week_start
from rate_limiter import init_usage_table, print_usage_report

IMPACT_ICONS = {"high": "🔴", "medium": "🟡", "low": "🟢"}
THEME_ICONS  = {
    "Feature Delivery": "🚀", "Bug Fix": "🐛",
    "Infrastructure":   "⚙️",  "Collaboration": "🤝",
    "Tech Debt":        "🔧", "Other": "📌",
}

def display_weekly_summary(enriched):
    from collections import defaultdict
    by_theme     = defaultdict(list)
    for t in enriched:
        by_theme[t.get("theme", "Other")].append(t)
    total_points = sum(t.get("story_points") or 0 for t in enriched)

    print(f"\n{'═' * 58}")
    print(f"  📊 WEEKLY ACHIEVEMENT SUMMARY — {get_week_start()}")
    print(f"{'═' * 58}")
    print(f"  Tickets : {len(enriched)}   |   Story points : {total_points}")
    print(f"{'─' * 58}")
    for theme, tickets in sorted(by_theme.items()):
        print(f"\n  {THEME_ICONS.get(theme,'📌')}  {theme.upper()}")
        for t in tickets:
            print(f"     {IMPACT_ICONS.get(t.get('impact_level','medium'),'🟡')} {t['key']}: {t.get('achievement') or t['summary']}")

    print(f"\n{'═' * 58}")
    print("  📋 BRAG BULLETS")
    print(f"{'─' * 58}")
    for t in sorted(enriched, key=lambda t: {"high":0,"medium":1,"low":2}.get(t.get("impact_level"),1)):
        if t.get("brag_bullet"):
            print(f"\n  • {t['brag_bullet']}")


def main():
    print("🤖 Jira Achievement Agent — Phase 3")
    print("=" * 58)

    # Init DB tables (achievements + token_usage)
    print("\n📦 Initializing database...")
    init_db()
    init_usage_table()

    # Fetch
    print("\n📡 Connecting to Jira...")
    client  = JiraClient()
    tickets = client.get_my_resolved_tickets(days_back=7)
    if not tickets:
        print("\n⚠️  No resolved tickets found.")
        return

    # Summarize (with budget checks built in)
    enriched = summarize_tickets(tickets)
    if not enriched:
        print("⚠️  Summarization returned no results.")
        return

    # Save
    print(f"\n💾 Saving to database...")
    saved = save_tickets(enriched)
    print(f"   ✅ Saved {saved} tickets")

    # Display results
    display_weekly_summary(enriched)

    # DB stats
    stats = get_stats()
    print(f"\n{'─' * 58}")
    print(f"  🗄️  DATABASE  |  {stats['total_tickets']} tickets  |  {stats['total_weeks']} weeks  |  {stats['total_points']} pts total")

    # Token usage report — shows budget bars
    print_usage_report()

    print(f"\n✅ Done. achievements.db updated.\n")


if __name__ == "__main__":
    main()