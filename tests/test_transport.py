from __future__ import annotations

import json
import os
import tempfile
import unittest
from unittest.mock import patch

import httpx

from asp.api import AspClient


KEY = "89ed5a47-8567-45c9-bdf3-87a84cfa2cf6"
HTTP_CLIENT = httpx.Client


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.environment = patch.dict(os.environ, {"ASP_MAX_STAKE": ""})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.client = AspClient(self.temp.name)
        self.client.state.save(httpx.Cookies({"PLAY_SESSION": "test-session"}), {"csrf_token": "old-test-token"})

    def transport(self, handler):
        transport = httpx.MockTransport(handler)
        return patch("asp.api.client.httpx.Client", side_effect=lambda **kwargs: HTTP_CLIENT(transport=transport, **kwargs))

    def test_csrf_refresh_preserves_idempotency_key_and_payload(self):
        attempts = []

        def handler(request):
            if request.url.path == "/user/details":
                return httpx.Response(200, text='<div data-request-confirmation="new-test-token"></div>',
                                      headers={"Content-Type": "text/html"})
            attempts.append((dict(request.headers), json.loads(request.content)))
            if len(attempts) == 1:
                return httpx.Response(403, json={"error": "invalid_request_confirmation"})
            return httpx.Response(200, json={"success": True, "joined": True})

        with self.transport(handler):
            result = self.client.daily_join(day="2026-10-25", request_id=KEY)
        self.assertTrue(result["joined"])
        self.assertEqual(attempts[0][1], attempts[1][1])
        self.assertEqual(attempts[1][1]["request_id"], KEY)
        self.assertEqual(attempts[0][0]["x-csrf-token"], "old-test-token")
        self.assertEqual(attempts[1][0]["x-csrf-token"], "new-test-token")

    def test_session_refresh_preserves_daily_entry_identity(self):
        self.client.state.save_credentials("player@example.test", "test-only-password")
        entries = []

        def handler(request):
            if request.url.path == "/api/login":
                return httpx.Response(200, json={"authenticated": True, "sessionToken": "renewed-test-token"})
            entries.append(json.loads(request.content))
            if len(entries) == 1:
                return httpx.Response(401, json={"error": "not_authenticated"})
            return httpx.Response(200, json={"success": True, "betId": 71, "stake": "5"})

        with self.transport(handler):
            result = self.client.predict("123", {"456": "8"}, 0, "5", competition_id=42, request_id=KEY)
        self.assertEqual(result["betId"], 71)
        self.assertEqual(entries[0], entries[1])
        self.assertEqual(entries[1]["request_id"], KEY)

    def test_rejected_saved_password_is_forgotten_not_repeated(self):
        self.client.state.save_credentials("player@example.test", "test-only-password")
        login_requests = []

        def handler(request):
            if request.url.path == "/api/login":
                login_requests.append(request)
                return httpx.Response(401, json={"error": "invalid_credentials"})
            return httpx.Response(401, json={"error": "not_authenticated"})

        with self.transport(handler):
            self.client.daily_me()
            self.client.daily_me()
        self.assertEqual(len(login_requests), 1)
        self.assertIsNone(self.client.state.load_credentials())

    def test_registration_keeps_generated_credentials_out_of_result(self):
        bodies = []

        def handler(request):
            bodies.append(json.loads(request.content))
            return httpx.Response(200, json={"success": True, "needs_email_confirmation": True})

        with self.transport(handler):
            result = self.client.register(email="player@example.test")
        self.assertTrue(result["credentials_saved"])
        self.assertTrue(result["terms_accepted"])
        self.assertNotIn("password", result)
        self.assertEqual(set(bodies[0]), {"username", "email", "password", "acceptTerms"})
        self.assertEqual(self.client.state.load_credentials()["password"], bodies[0]["password"])


if __name__ == "__main__":
    unittest.main()
