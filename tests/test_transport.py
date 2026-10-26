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
            if request.url.path == "/api/status":
                return httpx.Response(200, json={"authenticated": False})
            bodies.append(json.loads(request.content))
            return httpx.Response(200, json={"success": True, "needs_email_confirmation": True})

        with self.transport(handler):
            result = self.client.register(email="player@example.test")
        self.assertTrue(result["credentials_saved"])
        self.assertTrue(result["terms_accepted"])
        self.assertNotIn("password", result)
        self.assertTrue(result["password_handoff_required"])
        self.assertEqual(set(bodies[0]), {"username", "email", "password", "acceptTerms"})
        self.assertEqual(self.client.state.load_credentials()["password"], bodies[0]["password"])

    def test_registration_does_not_replace_saved_credentials(self):
        self.client.state.save_credentials("player@example.test", "original-test-password")
        with self.transport(lambda _: self.fail("Existing access must not trigger registration")):
            result = self.client.register(email="player@example.test")
        self.assertEqual(result["error"], "saved_account_exists")
        self.assertEqual(self.client.state.load_credentials()["password"], "original-test-password")

    def test_registration_keeps_a_live_account_even_without_saved_password(self):
        requests = []

        def handler(request):
            requests.append(request.url.path)
            return httpx.Response(200, json={"authenticated": True, "username": "original"})

        with self.transport(handler):
            result = self.client.register(email="player@example.test")
        self.assertEqual(result["error"], "already_authenticated")
        self.assertEqual(requests, ["/api/status"])
        self.assertIsNone(self.client.state.load_credentials())

    def test_registration_timeout_preserves_exact_password_and_blocks_retry(self):
        sent = []

        def handler(request):
            if request.url.path == "/api/status":
                return httpx.Response(200, json={"authenticated": False})
            sent.append(json.loads(request.content))
            raise httpx.ReadTimeout("response lost", request=request)

        with self.transport(handler):
            with self.assertRaises(httpx.ReadTimeout):
                self.client.register(email="player@example.test")
            retry = self.client.register(email="player@example.test")
        self.assertEqual(retry["error"], "saved_account_exists")
        self.assertEqual(len(sent), 1)
        self.assertEqual(self.client.state.load_credentials()["password"], sent[0]["password"])

    def test_rejected_registration_does_not_save_an_unusable_password(self):
        def handler(request):
            if request.url.path == "/api/status":
                return httpx.Response(200, json={"authenticated": False})
            return httpx.Response(409, json={"error": "already_registered"})

        with self.transport(handler):
            result = self.client.register(email="player@example.test")
        self.assertEqual(result["error"], "already_registered")
        self.assertIsNone(self.client.state.load_credentials())

    def test_registration_server_error_keeps_credentials_for_unknown_outcome(self):
        def handler(request):
            if request.url.path == "/api/status":
                return httpx.Response(200, json={"authenticated": False})
            return httpx.Response(500, json={"error": "server_error"})

        with self.transport(handler):
            result = self.client.register(email="player@example.test", password="KnownTestPassword!")
        self.assertEqual(result["status"], 500)
        self.assertEqual(self.client.state.load_credentials()["password"], "KnownTestPassword!")

    def test_credentials_hide_password_without_explicit_handoff(self):
        self.client.state.save_credentials("player@example.test", "private-test-password")
        self.assertEqual(self.client.credentials(), {"email": "player@example.test", "credentials_saved": True})
        self.assertEqual(self.client.credentials(show_password=True)["password"], "private-test-password")

    def test_resend_uses_saved_password_and_never_registers(self):
        self.client.state.save_credentials("player@example.test", "original-test-password")
        requests = []

        def handler(request):
            requests.append((request.url.path, json.loads(request.content)))
            return httpx.Response(200, json={"success": True, "needs_email_confirmation": True})

        with self.transport(handler):
            result = self.client.resend_confirmation()
        self.assertTrue(result["needs_email_confirmation"])
        self.assertEqual(requests, [("/api/register/resend", {"email": "player@example.test", "password": "original-test-password"})])
        self.assertEqual(self.client.state.load_credentials()["password"], "original-test-password")


if __name__ == "__main__":
    unittest.main()
