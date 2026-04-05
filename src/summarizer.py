# src/summarizer.py

import os
import json
import time
import requests

CLAUDE_API_URL = "https://api.anthropic.com/v1/messages"
CLAUDE_MODEL   = "claude-haiku-4-5-20251001"
THEMES = ["Feature Delivery", "Bug Fix", "Infrastructure", "Collaboration", "Tech Debt", "Other"]


def build_prompt(tickets: list[dict]) -> str:
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
- Infer impact from: priority (High/Highest = higher impact), story_points (more points = more complexity), issue type (Bug = high impact)
- theme must be exactly one of the values listed above
- impact_level: high = priority Highest/High or points >= 5 | low = points <= 1 | medium = everything else
- Return ONLY the JSON array. Nothing else.

## Ticket Data
{tickets_json}"""


def call_claude(prompt: str) -> tuple[str, int, int]:
    """
    Calls Claude API and returns (response_text, input_tokens, output_tokens).

    WHY RETURN TOKEN COUNTS?
    The API response includes exact token usage in data["usage"].
    We return these alongside the text so the caller can record
    actual usage in the budget tracker — more accurate than estimates.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise ValueError("Missing ANTHROPIC_API_KEY in .env — get yours at https://console.anthropic.com")

    headers = {
        "Content-Type":      "application/json",
        "x-api-key":         api_key,
        "anthropic-version": "2023-06-01"
    }
    body = {
        "model":      CLAUDE_MODEL,
        "max_tokens": 1000,
        "messages":   [{"role": "user", "content": prompt}]
    }

    MAX_RETRIES = 4
    wait        = 5

    for attempt in range(1, MAX_RETRIES + 1):
        print(f"   🧠 Calling Claude API (attempt {attempt}/{MAX_RETRIES})...")
        response = requests.post(CLAUDE_API_URL, headers=headers, json=body)

        if response.status_code == 429:
            if attempt == MAX_RETRIES:
                raise RuntimeError("Rate limited after 4 attempts. Wait a minute and retry.")
            print(f"   ⏳ Rate limited. Waiting {wait}s...")
            time.sleep(wait)
            wait *= 2
            continue

        if response.status_code == 401:
            raise ValueError("Invalid API key — check ANTHROPIC_API_KEY in your .env")

        response.raise_for_status()
        data = response.json()

        # Claude returns exact token usage in every response
        # data["usage"] = {"input_tokens": 312, "output_tokens": 148}
        input_tokens  = data.get("usage", {}).get("input_tokens",  0)
        output_tokens = data.get("usage", {}).get("output_tokens", 0)
        text          = data["content"][0]["text"]

        return text, input_tokens, output_tokens


def parse_summaries(raw_response: str) -> list[dict]:
    text = raw_response.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text  = "\n".join(lines[1:-1]).strip()
    try:
        summaries = json.loads(text)
        if not isinstance(summaries, list):
            raise ValueError("Expected a JSON array")
        return summaries
    except json.JSONDecodeError as e:
        print(f"⚠️  Failed to parse response as JSON: {e}")
        print(f"   Raw response:\n{raw_response[:500]}")
        return []


def summarize_tickets(tickets: list[dict]) -> list[dict]:
    """
    Processes one ticket at a time.
    Checks token budget BEFORE each call, records actual usage AFTER.
    Skips tickets that would exceed the weekly budget.
    """
    # Import here to avoid circular imports
    from rate_limiter import check_budget, record_usage, estimate_call_cost

    if not tickets:
        print("   No tickets to summarize.")
        return []

    print(f"\n📝 Summarizing {len(tickets)} tickets with Claude Haiku...")

    enriched = []
    skipped  = 0

    for i, ticket in enumerate(tickets, 1):
        print(f"\n   [{i}/{len(tickets)}] {ticket['key']}: {ticket['summary'][:50]}...")

        prompt = build_prompt([ticket])

        # ── Budget check BEFORE calling ──────────────────────
        # This is the safety valve — if we'd exceed the weekly
        # budget, we skip this ticket rather than making the call.
        budget = check_budget(prompt, ticket_key=ticket["key"])

        if not budget["allowed"]:
            print(f"   ⛔ Skipping — budget exceeded:")
            print(f"      {budget['reason']}")
            skipped += 1
            # Still append the ticket, just without AI summary
            enriched.append({
                **ticket,
                "achievement":  "",
                "theme":        "Other",
                "impact_level": "medium",
                "brag_bullet":  "",
            })
            continue

        est = budget["estimate"]
        print(f"   📊 Estimated: ~{est['input_tokens']} input + ~{est['output_tokens']} output tokens (${est['estimated_cost']:.4f})")

        # ── Make the API call ─────────────────────────────────
        raw, actual_input, actual_output = call_claude(prompt)

        # ── Record ACTUAL usage after the call ───────────────
        # Claude returns exact counts — more accurate than estimates
        from rate_limiter import HAIKU_INPUT_COST_PER_M, HAIKU_OUTPUT_COST_PER_M
        actual_cost = (
            (actual_input  / 1_000_000) * HAIKU_INPUT_COST_PER_M +
            (actual_output / 1_000_000) * HAIKU_OUTPUT_COST_PER_M
        )
        record_usage(ticket["key"], actual_input, actual_output, actual_cost)
        print(f"   ✅ Actual: {actual_input} input + {actual_output} output tokens (${actual_cost:.4f})")

        summaries = parse_summaries(raw)
        summary   = summaries[0] if summaries else {}

        enriched.append({
            **ticket,
            "achievement":  summary.get("achievement", ""),
            "theme":        summary.get("theme", "Other"),
            "impact_level": summary.get("impact_level", "medium"),
            "brag_bullet":  summary.get("brag_bullet", ""),
        })

        if i < len(tickets):
            time.sleep(2)

    if skipped:
        print(f"\n   ⚠️  {skipped} ticket(s) skipped due to budget limits")

    print(f"\n   ✅ Summarized {len(enriched) - skipped}/{len(tickets)} tickets")
    return enriched