# Jira Achievement Agent

A personal productivity tool that automatically fetches your resolved Jira tickets and uses AI (Gemini 2.0 Flash) to transform them into polished achievement summaries and "brag bullets" — ready to paste into performance reviews, 1:1 docs, or weekly updates.

## What it does

1. **Fetches** all Jira tickets you closed in the last 7 days (configurable)
2. **Enriches** each ticket with an AI-generated achievement summary, theme classification, and impact level
3. **Generates** STAR-format brag bullets starting with strong action verbs
4. **Groups** tickets by theme and prints a weekly digest to the terminal

### Example output
```
  📊 WEEKLY ACHIEVEMENT SUMMARY
  Tickets closed : 6
  Story points   : 21
  Themes covered : 3

  🚀 FEATURE DELIVERY (2 tickets)
     🔴 PROJ-101: Shipped user authentication flow with OAuth2 support
     🟡 PROJ-98:  Delivered dashboard filtering by date range

  📋 BRAG BULLETS
  • Architected and shipped OAuth2 authentication flow, reducing login friction for 10k+ users
  • Resolved a critical data pipeline bug that was causing 15% report inaccuracies in production
```

## Project structure

```
jira-agent/
├── src/
│   ├── main.py          # Orchestrator — runs all phases in order
│   ├── jira_client.py   # Jira REST API client (fetches & parses tickets)
│   ├── summarizer.py    # Gemini AI layer (builds prompts, calls API, parses responses)
│   └── check_quota.py   # Utility to verify your Gemini API key and quota
├── mock_server/
│   ├── mock_jira_server.py  # Local fake Jira server for development
│   └── seed_data.py         # Sample tickets to populate the mock server
├── .env.example         # Template for required environment variables
└── requirements.txt
```

## Setup

### 1. Clone and install dependencies
```bash
git clone https://github.com/vamshee-priya024/Jira-Achievement-Agent.git
cd Jira-Achievement-Agent
pip install -r requirements.txt
```

### 2. Configure environment variables
```bash
cp .env.example .env
```

Edit `.env` with your credentials:

| Variable | Description |
|---|---|
| `GEMINI_API_KEY` | Get a free key at [aistudio.google.com](https://aistudio.google.com/apikey) |
| `JIRA_BASE_URL` | Your Jira instance, e.g. `https://yourcompany.atlassian.net` |
| `JIRA_EMAIL` | The email linked to your Jira account |
| `JIRA_API_TOKEN` | Create one at [id.atlassian.com/manage-profile/security/api-tokens](https://id.atlassian.com/manage-profile/security/api-tokens) |
| `USE_MOCK` | Set to `true` to use the local mock server (no real Jira needed) |

### 3. Run

**With real Jira:**
```bash
cd src
python main.py
```

**With mock server (for testing):**
```bash
# Terminal 1 — start the mock server
cd mock_server
python mock_jira_server.py

# Terminal 2 — run the agent
USE_MOCK=true python src/main.py
```

## Tech stack

- **Python 3.13**
- **Jira REST API v3** — direct HTTP calls via `requests`
- **Gemini 2.0 Flash** — AI summarization (free tier friendly)
- **python-dotenv** — environment variable management

## Roadmap

- [x] Phase 1 — Fetch and parse resolved Jira tickets
- [x] Phase 2 — AI enrichment with Gemini (achievements, themes, brag bullets)
- [ ] Phase 3 — Store results in SQLite + append to Notion brag doc
- [ ] Phase 4 — Weekly email digest
