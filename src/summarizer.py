# src/summarizer.py
#
# This module takes raw parsed Jira tickets and turns them into
# human-readable achievement summaries using the Gemini API.
#
# DESIGN PRINCIPLE: This module knows NOTHING about Jira.
# It only knows: "given a list of ticket dicts, return summaries."
# That clean boundary means you could swap Gemini for any other
# LLM later by only changing this file.

import os
import json
import requests


# ─────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────

GEMINI_MODEL = "gemini-2.0-flash"

# Gemini's REST endpoint — the API key goes in the URL as a query param,
# not in the headers like Claude or OpenAI do.
# We build the full URL at call time once we have the key from .env.
GEMINI_API_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models"
    "/{model}:generateContent?key={api_key}"
)

# We categorize every ticket into one of these themes.
# This lets us group achievements in the final report.
THEMES = ["Feature Delivery", "Bug Fix", "Infrastructure", "Collaboration", "Tech Debt", "Other"]


# ─────────────────────────────────────────────
# PROMPT BUILDER
# ─────────────────────────────────────────────

def build_prompt(tickets: list[dict]) -> str:
    """
    Converts a list of ticket dicts into a structured prompt string.

    WHY A SEPARATE FUNCTION?
    Prompt construction is logic, not just a string.
    It deserves its own function so you can:
    - Unit test it independently
    - Tweak the prompt without touching API call logic
    - See clearly what you're sending to the model

    PROMPT ENGINEERING PRINCIPLES USED HERE:
    1. Give the model a clear ROLE ("You are an expert...")
    2. Show the exact INPUT FORMAT with real field names
    3. Define the exact OUTPUT FORMAT — JSON schema with field names & types
    4. Provide RULES to constrain behavior (no fluff, active voice, etc.)
    5. Inject the actual DATA at the end, clearly delimited
    """

    ticket_data = []
    for t in tickets:
        ticket_data.append({
            "key":          t["key"],
            "type":         t["issue_type"],
            "summary":      t["summary"],
            "description":  t["description"][:400] if t["description"] else "",
            "priority":     t["priority"],
            "story_points": t["story_points"],
            "labels":       t["labels"],
        })

    tickets_json = json.dumps(ticket_data, indent=2)

    return f"""You are an expert technical writer helping a software engineer document their weekly work achievements for performance reviews.

Your job: Transform raw Jira ticket data into clear, professional achievement summaries.

## Output Format
Return ONLY a valid JSON array. No preamble, no explanation, no markdown fences.
Each element must have exactly these fields:

{{
  "key": "PROJ-123",
  "achievement": "One concise sentence (max 25 words) in active voice describing what was accomplished and its impact.",
  "theme": "One of: {', '.join(THEMES)}",
  "impact_level": "high | medium | low",
  "brag_bullet": "A polished STAR-format bullet point (max 40 words) suitable for a performance review. Start with a strong action verb. Include the business or technical impact where inferable."
}}

## Rules
- Use active voice: "Delivered X" not "X was delivered"
- Start brag_bullet with a strong verb: Resolved, Delivered, Architected, Reduced, Improved, Led, Shipped, Automated, Refactored
- Infer impact from: priority (High/Highest = higher impact), story_points (more points = more complexity), issue type (Bug in prod = high impact)
- If description is empty, infer context from the summary
- theme must be exactly one of the values listed above
- impact_level: high = priority Highest/High or points >= 5 | low = points <= 1 | medium = everything else
- Return ONLY the JSON array. Nothing else.

## Ticket Data
{tickets_json}"""


# ─────────────────────────────────────────────
# API CALLER
# ─────────────────────────────────────────────

def call_gemini(prompt: str) -> str:
    """
    Sends a prompt to the Gemini API and returns the raw text response.

    HOW GEMINI DIFFERS FROM CLAUDE:
    ┌─────────────┬──────────────────────────────┬──────────────────────────────┐
    │             │ Claude                       │ Gemini                       │
    ├─────────────┼──────────────────────────────┼──────────────────────────────┤
    │ Auth        │ x-api-key header             │ ?key= query param in URL     │
    │ Body shape  │ {"messages": [...]}          │ {"contents": [...]}          │
    │ Role name   │ "user"                       │ "user" (same)                │
    │ Text field  │ content (string)             │ parts: [{text: ...}]         │
    │ Response    │ data.content[0].text         │ data.candidates[0]           │
    │             │                              │   .content.parts[0].text     │
    └─────────────┴──────────────────────────────┴──────────────────────────────┘

    Everything else — prompt design, JSON parsing, merging — stays identical.
    That's the payoff of keeping the API caller isolated in its own function.
    """
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        raise ValueError(
            "Missing GEMINI_API_KEY in .env\n"
            "Get a free key at: https://aistudio.google.com/apikey"
        )

    url = GEMINI_API_URL.format(model=GEMINI_MODEL, api_key=api_key)

    # Gemini request body shape:
    # "contents" is the conversation — each turn has a "role" and "parts"
    # "parts" is a list because a single message can have text + images + files
    # For our use case it's always just one text part
    body = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": prompt}]
            }
        ],
        "generationConfig": {
            "temperature": 0.2,       # low temp = more deterministic, better for structured JSON
            "maxOutputTokens": 2000,  # enough for ~20 ticket summaries
        }
    }

    import time
    MAX_RETRIES = 4
    wait        = 5  # start at 5s, doubles each retry

    for attempt in range(1, MAX_RETRIES + 1):
        print(f"   🧠 Calling Gemini API (attempt {attempt}/{MAX_RETRIES})...")

        response = requests.post(
            url,
            headers={"Content-Type": "application/json"},
            json=body
        )

        if response.status_code == 429:
            if attempt == MAX_RETRIES:
                raise RuntimeError(
                    f"Gemini rate limit hit after {MAX_RETRIES} attempts. "
                    f"Wait a minute and try again."
                )
            print(f"   ⏳ Rate limited (429). Waiting {wait}s before retry...")
            time.sleep(wait)
            wait *= 2   # exponential backoff: 5 → 10 → 20 → 40s
            continue

        response.raise_for_status()

        data = response.json()

        try:
            return data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError) as e:
            raise ValueError(f"Unexpected Gemini response shape: {data}") from e


# ─────────────────────────────────────────────
# RESPONSE PARSER
# ─────────────────────────────────────────────

def parse_summaries(raw_response: str) -> list[dict]:
    """
    Parses the JSON array returned by Gemini.

    WHY DEFENSIVE PARSING?
    Even with a strict prompt, LLMs occasionally wrap output in
    markdown fences (```json ... ```) or add a brief intro sentence.
    We strip those defensively before parsing.
    """
    text = raw_response.strip()

    # Strip markdown code fences if present (```json ... ``` or ``` ... ```)
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1]).strip()

    try:
        summaries = json.loads(text)
        if not isinstance(summaries, list):
            raise ValueError("Expected a JSON array, got something else")
        return summaries
    except json.JSONDecodeError as e:
        print(f"⚠️  Failed to parse Gemini response as JSON: {e}")
        print(f"   Raw response was:\n{raw_response[:500]}")
        return []


# ─────────────────────────────────────────────
# PUBLIC INTERFACE
# ─────────────────────────────────────────────

def summarize_tickets(tickets: list[dict]) -> list[dict]:
    """
    Replaces the old batch version. Processes one ticket at a time
    with a delay between calls to stay within Gemini free tier limits.

    WHY ONE TICKET AT A TIME?
    Gemini free tier allows ~15 RPM (requests per minute).
    Sending all 8 tickets in one large prompt hits that limit hard.
    Processing individually with a 4s gap keeps us at ~15 RPM safely.
    Bonus: if one ticket fails, the rest still succeed.
    This is called "chunked processing".
    """
    import time

    if not tickets:
        print("   No tickets to summarize.")
        return []

    print(f"\n📝 Summarizing {len(tickets)} tickets one at a time (free tier safe)...")

    enriched = []
    for i, ticket in enumerate(tickets, 1):
        summary_text = ticket['summary'][:50]
        print(f"   [{i}/{len(tickets)}] {ticket['key']}: {summary_text}...")

        prompt    = build_prompt([ticket])   # one ticket per call
        raw       = call_gemini(prompt)
        summaries = parse_summaries(raw)

        summary = summaries[0] if summaries else {}
        enriched.append({
            **ticket,
            "achievement":  summary.get("achievement", ""),
            "theme":        summary.get("theme", "Other"),
            "impact_level": summary.get("impact_level", "medium"),
            "brag_bullet":  summary.get("brag_bullet", ""),
        })

        # 4s gap between calls → ~15 RPM, safely under free tier cap.
        # Skip the wait after the last ticket.
        if i < len(tickets):
            time.sleep(4)

    print(f"   ✅ Summarized {len(enriched)} tickets")
    return enriched