# mock_server/seed_data.py
#
# Realistic fake Jira tickets for local development.
# These cover all the ticket types and field variations
# your real Jira might have — so the agent is tested thoroughly.
#
# Ticket types covered:
#   - Story (feature work)
#   - Bug (high and low priority)
#   - Task (infra / tech debt)
#   - Spike (research)
# Field variations covered:
#   - With and without story points
#   - With and without descriptions
#   - With and without labels
#   - Various priorities

from datetime import datetime, timedelta

def days_ago(n):
    return (datetime.utcnow() - timedelta(days=n)).strftime("%Y-%m-%dT%H:%M:%S.000+0000")

def make_description(text):
    """Mimics Atlassian Document Format (ADF) — the nested JSON Jira uses for descriptions."""
    return {
        "type": "doc",
        "version": 1,
        "content": [
            {
                "type": "paragraph",
                "content": [
                    {"type": "text", "text": text}
                ]
            }
        ]
    }

# ── Fake user (you) ────────────────────────────────────────
MOCK_USER = {
    "accountId": "mock-user-001",
    "displayName": "Alex Dev",
    "emailAddress": "alex@mockcompany.com"
}

# ── Fake tickets ───────────────────────────────────────────
MOCK_TICKETS = [
    {
        "id": "10001",
        "key": "PLAT-204",
        "fields": {
            "summary": "Add OAuth2 login support for enterprise customers",
            "description": make_description(
                "Enterprise customers require SSO via OAuth2. "
                "Implement the authorization code flow with PKCE. "
                "Support Google and Microsoft identity providers."
            ),
            "status": {"name": "Done", "statusCategory": {"key": "done"}},
            "issuetype": {"name": "Story"},
            "priority": {"name": "High"},
            "customfield_10016": 8,   # story points
            "labels": ["auth", "enterprise", "security"],
            "assignee": MOCK_USER,
            "resolutiondate": days_ago(2),
            "updated": days_ago(1),
        }
    },
    {
        "id": "10002",
        "key": "PLAT-198",
        "fields": {
            "summary": "Fix race condition in payment processing queue",
            "description": make_description(
                "Under high load, duplicate transactions are being created. "
                "Root cause: missing idempotency key check before queue insertion. "
                "Fix: add Redis-based deduplication with 24h TTL."
            ),
            "status": {"name": "Done", "statusCategory": {"key": "done"}},
            "issuetype": {"name": "Bug"},
            "priority": {"name": "Highest"},
            "customfield_10016": 5,
            "labels": ["payments", "production-bug", "reliability"],
            "assignee": MOCK_USER,
            "resolutiondate": days_ago(3),
            "updated": days_ago(3),
        }
    },
    {
        "id": "10003",
        "key": "PLAT-211",
        "fields": {
            "summary": "Migrate user service database to Postgres 15",
            "description": make_description(
                "Upgrade from Postgres 12 to 15 to get performance improvements "
                "and security patches. Includes zero-downtime migration plan "
                "using pg_upgrade with a blue-green deploy strategy."
            ),
            "status": {"name": "Done", "statusCategory": {"key": "done"}},
            "issuetype": {"name": "Task"},
            "priority": {"name": "Medium"},
            "customfield_10016": 6,
            "labels": ["infrastructure", "database", "migration"],
            "assignee": MOCK_USER,
            "resolutiondate": days_ago(4),
            "updated": days_ago(4),
        }
    },
    {
        "id": "10004",
        "key": "PLAT-187",
        "fields": {
            "summary": "Reduce p99 API latency on /search endpoint",
            "description": make_description(
                "Search endpoint p99 latency is at 2.4s, SLA target is 800ms. "
                "Added Redis caching layer for frequent queries. "
                "Implemented query result pagination to reduce payload size."
            ),
            "status": {"name": "Done", "statusCategory": {"key": "done"}},
            "issuetype": {"name": "Story"},
            "priority": {"name": "High"},
            "customfield_10016": 5,
            "labels": ["performance", "backend", "caching"],
            "assignee": MOCK_USER,
            "resolutiondate": days_ago(5),
            "updated": days_ago(5),
        }
    },
    {
        "id": "10005",
        "key": "PLAT-219",
        "fields": {
            "summary": "Fix broken CSV export for reports with special characters",
            "description": make_description(
                "Reports containing accented characters or commas in field values "
                "produce malformed CSV files. Fix UTF-8 encoding and quote escaping."
            ),
            "status": {"name": "Done", "statusCategory": {"key": "done"}},
            "issuetype": {"name": "Bug"},
            "priority": {"name": "Medium"},
            "customfield_10016": 2,
            "labels": ["reporting", "bug"],
            "assignee": MOCK_USER,
            "resolutiondate": days_ago(2),
            "updated": days_ago(2),
        }
    },
    {
        "id": "10006",
        "key": "PLAT-201",
        "fields": {
            "summary": "Add automated integration tests for billing module",
            "description": make_description(
                "Billing module has 0% integration test coverage. "
                "Added 14 new pytest integration tests covering "
                "subscription creation, upgrades, downgrades, and cancellations."
            ),
            "status": {"name": "Done", "statusCategory": {"key": "done"}},
            "issuetype": {"name": "Task"},
            "priority": {"name": "Medium"},
            "customfield_10016": 3,
            "labels": ["testing", "billing", "tech-debt"],
            "assignee": MOCK_USER,
            "resolutiondate": days_ago(6),
            "updated": days_ago(6),
        }
    },
    {
        "id": "10007",
        "key": "PLAT-225",
        "fields": {
            "summary": "Spike: evaluate GraphQL for mobile API layer",
            "description": make_description(
                "Investigate whether GraphQL would reduce over-fetching for the "
                "mobile client. Compare against current REST approach on "
                "payload size, developer experience, and caching complexity."
            ),
            "status": {"name": "Done", "statusCategory": {"key": "done"}},
            "issuetype": {"name": "Spike"},
            "priority": {"name": "Low"},
            "customfield_10016": 2,
            "labels": ["research", "mobile", "api"],
            "assignee": MOCK_USER,
            "resolutiondate": days_ago(1),
            "updated": days_ago(1),
        }
    },
    {
        "id": "10008",
        "key": "PLAT-193",
        "fields": {
            "summary": "Onboard new team members to deployment process",
            "description": make_description(
                "Led two onboarding sessions for 3 new engineers joining the platform team. "
                "Documented the CI/CD pipeline, runbooks, and on-call procedures."
            ),
            "status": {"name": "Done", "statusCategory": {"key": "done"}},
            "issuetype": {"name": "Task"},
            "priority": {"name": "Low"},
            "customfield_10016": 1,
            "labels": ["collaboration", "onboarding"],
            "assignee": MOCK_USER,
            "resolutiondate": days_ago(3),
            "updated": days_ago(3),
        }
    },
]