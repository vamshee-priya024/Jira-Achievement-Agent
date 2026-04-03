# src/jira_client.py
#
# This module handles ALL communication with the Jira API.
# Keeping API logic in its own file is a key engineering principle:
# "Separation of Concerns" — each file has ONE job.
#
# If Jira ever changes their API, you only update THIS file.
# The rest of your code stays untouched.

import os
import requests
from requests.auth import HTTPBasicAuth
from datetime import datetime, timedelta


class JiraClient:
    """
    A client class that wraps the Jira REST API.

    WHY A CLASS?
    We use a class (not just functions) because the base_url and auth
    are shared across every API call. Instead of passing them to every
    function, we store them once in __init__ and reuse via self.
    This is called "encapsulation".
    """

    def __init__(self):
        # USE_MOCK=true → point at local mock server, skip real credentials
        # USE_MOCK=false (or unset) → use real Jira
        use_mock = os.environ.get("USE_MOCK", "false").lower() == "true"

        if use_mock:
            # Mock server runs locally — no real credentials needed
            self.base_url = "http://localhost:8080"
            self.email    = "mock@localhost"
            self.token    = "mock-token"
            print("   ⚠️  MOCK MODE — using local fake Jira server")
        else:
            self.base_url = os.environ.get("JIRA_BASE_URL", "").rstrip("/")
            self.email    = os.environ.get("JIRA_EMAIL", "")
            self.token    = os.environ.get("JIRA_API_TOKEN", "")

            if not all([self.base_url, self.email, self.token]):
                raise ValueError(
                    "Missing Jira credentials. "
                    "Check your .env file for JIRA_BASE_URL, JIRA_EMAIL, JIRA_API_TOKEN"
                )

        # HTTPBasicAuth encodes "email:token" in base64 for us automatically.
        # Jira's API uses this instead of session cookies.
        self.auth = HTTPBasicAuth(self.email, self.token)

        # Standard headers for Jira REST API v3
        # "Accept: application/json" tells Jira to respond in JSON, not HTML
        self.headers = {
            "Accept": "application/json",
            "Content-Type": "application/json"
        }

    def _get(self, endpoint: str, params: dict = None) -> dict:
        """
        Private helper method for GET requests.

        WHY A HELPER?
        Every API call needs auth + headers + error handling.
        Rather than repeating that 10 times, we centralize it here.
        The underscore prefix (_get) signals "internal use only" by convention.
        """
        url = f"{self.base_url}/rest/api/3/{endpoint}"

        response = requests.get(
            url,
            headers=self.headers,
            auth=self.auth,
            params=params  # These become ?key=value query string params
        )

        # raise_for_status() throws an exception for 4xx/5xx HTTP errors.
        # Without this, a 401 Unauthorized would silently return empty data.
        response.raise_for_status()

        return response.json()

    def get_my_resolved_tickets(self, days_back: int = 7) -> list[dict]:
        """
        Fetches tickets assigned to you that were resolved in the last N days.

        JQL BREAKDOWN:
          assignee = currentUser()         → only your tickets
          statusCategory = Done            → only completed work
                                             (catches Done, Closed, Resolved, etc.)
          updated >= -{days_back}d         → within the time window
          ORDER BY updated DESC            → newest first

        WHY statusCategory instead of status?
        Jira lets teams name statuses anything ("Ship It!", "Deployed", etc.)
        statusCategory is standardized: To Do / In Progress / Done
        """
        jql = (
            f"assignee = currentUser() "
            f"AND statusCategory = Done "
            f"AND updated >= -{days_back}d "
            f"ORDER BY updated DESC"
        )

        # These are the Jira fields we want back.
        # Requesting only what we need keeps the response small and fast.
        fields = [
            "summary",          # ticket title
            "description",      # full description (Atlassian Document Format)
            "status",           # current status name
            "priority",         # Highest / High / Medium / Low
            "issuetype",        # Bug / Story / Task / Epic
            "story_points",     # effort estimate (custom field)
            "customfield_10016",# story points on most Jira configs (common field ID)
            "labels",           # free-form tags your team adds
            "updated",          # when it last changed
            "resolutiondate",   # when it was marked Done
            "comment",          # comments count / last comment
            "assignee",         # confirm it's you
        ]

        params = {
            "jql": jql,
            "fields": ",".join(fields),
            "maxResults": 50,   # cap at 50; you rarely close >50 tickets/week
        }

        data = self._get("search", params=params)

        # data["issues"] is the list of ticket objects
        # We pass it to a parser to extract only what we care about
        raw_issues = data.get("issues", [])
        print(f"✅ Found {len(raw_issues)} resolved tickets in the last {days_back} days")

        return [self._parse_ticket(issue) for issue in raw_issues]

    def _parse_ticket(self, issue: dict) -> dict:
        """
        Transforms raw Jira JSON into a clean, flat dictionary.

        WHY PARSE?
        Raw Jira JSON is deeply nested and verbose. For example, priority
        lives at issue["fields"]["priority"]["name"] — 3 levels deep.
        Parsing once here means the rest of your code uses clean keys like
        ticket["priority"] instead of navigating nested dicts everywhere.

        This is the "Data Transfer Object" (DTO) pattern.
        """
        fields = issue.get("fields", {})

        # Story points can live in different fields depending on Jira config.
        # We check the standard name first, then the common custom field ID.
        story_points = (
            fields.get("story_points") or
            fields.get("customfield_10016") or
            0
        )

        # Extract plain text from description.
        # Jira descriptions use Atlassian Document Format (ADF) — a nested JSON.
        # We pull just the text content for the LLM later.
        description_text = self._extract_description_text(fields.get("description"))

        return {
            "key":             issue.get("key", ""),           # e.g. "PROJ-123"
            "summary":         fields.get("summary", ""),      # ticket title
            "description":     description_text,
            "status":          fields.get("status", {}).get("name", ""),
            "issue_type":      fields.get("issuetype", {}).get("name", ""),  # Bug, Story, Task
            "priority":        fields.get("priority", {}).get("name", ""),
            "story_points":    story_points,
            "labels":          fields.get("labels", []),
            "resolution_date": fields.get("resolutiondate", ""),
            "updated":         fields.get("updated", ""),
            "url":             f"{self.base_url}/browse/{issue.get('key', '')}",
        }

    def _extract_description_text(self, description: dict) -> str:
        """
        Jira descriptions are stored in Atlassian Document Format (ADF).
        This is a JSON tree of nodes — paragraphs, bullet lists, code blocks, etc.

        We recursively walk the tree and collect all text nodes.
        Result: a flat string that the LLM can read easily.
        """
        if not description:
            return ""

        texts = []

        def walk(node):
            if isinstance(node, dict):
                if node.get("type") == "text":
                    texts.append(node.get("text", ""))
                for child in node.get("content", []):
                    walk(child)

        walk(description)
        return " ".join(texts).strip()