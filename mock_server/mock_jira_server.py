# mock_server/mock_jira_server.py
#
# A lightweight fake Jira REST API server using Python's built-in http.server.
# No extra dependencies needed beyond what's already in requirements.txt.
#
# WHY BUILD A MOCK SERVER vs. just hardcoding fake data?
#
# Option A — hardcode fake data directly in jira_client.py:
#   ✅ Simple
#   ❌ You change production code to support testing (bad practice)
#   ❌ You can't test the actual HTTP request/response cycle
#
# Option B — mock server on localhost (what we're doing):
#   ✅ Your production jira_client.py is UNCHANGED
#   ✅ You test the real HTTP layer (auth headers, JSON parsing, error handling)
#   ✅ One env var switches between mock and real — no code changes ever
#   ✅ Mirrors how professional teams use tools like WireMock or MSW
#
# HOW IT WORKS:
# Python's http.server.BaseHTTPRequestHandler lets you define
# what happens when a specific URL path is hit.
# We intercept the Jira search endpoint and return our fake tickets.

import json
import sys
import os
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

# Add parent dir to path so we can import seed_data
sys.path.insert(0, os.path.dirname(__file__))
from seed_data import MOCK_TICKETS, MOCK_USER

PORT = 8080


class MockJiraHandler(BaseHTTPRequestHandler):
    """
    Handles incoming HTTP requests and routes them to mock responses.

    BaseHTTPRequestHandler calls do_GET() for every GET request.
    We parse the path and return the appropriate mock response.
    """

    def do_GET(self):
        parsed = urlparse(self.path)
        path   = parsed.path

        # Route: Jira search (the main endpoint our agent uses)
        # Real URL: GET /rest/api/3/search?jql=...&fields=...
        if path == "/rest/api/3/search":
            self._handle_search(parsed)

        # Route: Current user info (useful for debugging auth)
        elif path == "/rest/api/3/myself":
            self._handle_myself()

        # Route: anything else → 404
        else:
            self._send_json(404, {"error": f"Mock server: unknown path {path}"})

    def _handle_search(self, parsed):
        """
        Returns mock tickets in Jira's real response envelope format.

        REAL JIRA RESPONSE SHAPE:
        {
          "total": 8,
          "maxResults": 50,
          "startAt": 0,
          "issues": [ ...ticket objects... ]
        }

        We match this shape exactly so jira_client.py needs zero changes.
        """
        params = parse_qs(parsed.query)
        jql    = params.get("jql", [""])[0]
        print(f"   [mock] JQL received: {jql}")

        # In a real mock you'd parse JQL and filter.
        # For our purposes, we return all mock tickets — they're all "Done".
        self._send_json(200, {
            "total":      len(MOCK_TICKETS),
            "maxResults": 50,
            "startAt":    0,
            "issues":     MOCK_TICKETS
        })

    def _handle_myself(self):
        """Returns the mock current user — useful to verify auth is wired up."""
        self._send_json(200, MOCK_USER)

    def _send_json(self, status_code: int, data: dict):
        """Helper to send a JSON response with correct headers."""
        body = json.dumps(data).encode("utf-8")

        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        """Override default logging to make output cleaner."""
        print(f"   [mock] {self.address_string()} → {args[0]} {args[1]}")


def run():
    server = HTTPServer(("localhost", PORT), MockJiraHandler)
    print(f"🟢 Mock Jira server running at http://localhost:{PORT}")
    print(f"   Loaded {len(MOCK_TICKETS)} fake tickets")
    print(f"   Press Ctrl+C to stop\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n🔴 Mock server stopped.")
        server.server_close()


if __name__ == "__main__":
    run()