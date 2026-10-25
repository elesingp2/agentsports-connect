from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from asp.api import AspClient


KEY = "89ed5a47-8567-45c9-bdf3-87a84cfa2cf6"


class DailyApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.environment = patch.dict(os.environ, {"ASP_MAX_STAKE": ""})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.client = AspClient(self.temp.name)
        self.client.request = Mock(return_value={})

    def test_join_and_legacy_claim_use_same_idempotent_endpoint(self):
        self.client.request.return_value = {"success": True, "joined": True, "balance_asp": "100.00"}
        for operation in (self.client.daily_join, self.client.daily_claim):
            with self.subTest(operation=operation.__name__):
                response = operation(day="2026-10-25", request_id=KEY)
                self.assertEqual(response["request_id"], KEY)
                self.assertEqual(response["balance_asp"], "100.00")
                self.client.request.assert_called_with("POST", "/api/daily/join", json={
                    "day": "2026-10-25", "request_id": KEY})

    def test_join_defaults_day_on_server_and_generates_request_id(self):
        response = self.client.daily_join()
        body = self.client.request.call_args.kwargs["json"]
        self.assertNotIn("day", body)
        self.assertEqual(response["request_id"], body["request_id"])
        self.assertRegex(body["request_id"], r"^[0-9a-f-]{36}$")

    def test_invalid_dates_are_rejected_before_request(self):
        for day in ("2026-02-29", "2026-13-01", "20261025", "2026-1-1", "../../account", ""):
            with self.subTest(day=day):
                with self.assertRaises(ValueError):
                    self.client.daily_status(day)
        self.client.request.assert_not_called()

    def test_valid_leap_day_and_public_status_are_forwarded(self):
        payload = {"enabled": False, "state": "disabled", "can_join": False}
        self.client.request.return_value = payload
        self.assertEqual(self.client.daily_status("2028-02-29"), payload)
        self.client.request.assert_called_with("GET", "/api/daily", params={"day": "2028-02-29"})

    def test_daily_history_keeps_pending_entries_for_delayed_settlement(self):
        payload = {"day": "2026-10-24", "state": "settling", "entries": [
            {"id": 1, "status": "pending"}, {"id": 2, "status": "won"}]}
        self.client.request.return_value = payload
        self.assertEqual(self.client.daily_history("2026-10-24"), payload)
        self.client.request.assert_called_with("GET", "/api/daily/me", params={"day": "2026-10-24"})

    def test_leaderboard_uses_public_scope_and_pagination(self):
        self.client.daily_leaderboard(day="2026-10-25", scope="30d", page=3)
        self.client.request.assert_called_with("GET", "/api/daily/leaderboard", params={
            "day": "2026-10-25", "scope": "30d", "page": 3})
        for kwargs in ({"scope": "all"}, {"page": 0}, {"page": True}, {"page": 100001}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.client.daily_leaderboard(**kwargs)

    def test_prediction_keeps_exact_daily_identity_across_retry(self):
        self.client.request.return_value = {"success": True, "betId": 44, "stake": "5"}
        for _ in range(2):
            response = self.client.predict("123", {"456": "8"}, 0, "5", competition_id="42", request_id=KEY)
            self.assertEqual(response["betId"], 44)
            self.assertEqual(response["request_id"], KEY)
        first, second = self.client.request.call_args_list
        self.assertEqual(first, second)
        self.assertEqual(first.kwargs["json"], {"selections": {"456": "8"}, "roomIndex": 0,
                                              "stake": "5", "competition_id": 42, "request_id": KEY})

    def test_bad_identity_never_submits(self):
        for kwargs in ({"competition_id": True}, {"competition_id": "1.5"},
                       {"competition_id": "9223372036854775808"}, {"request_id": "short"},
                       {"request_id": "unsafe/path"}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.client.predict("123", {"456": "8"}, 0, "5", **kwargs)
        self.client.request.assert_not_called()

    def test_existing_max_stake_guard_checks_room_actual_minimum(self):
        self.client._max_stake = __import__("decimal").Decimal("5")
        self.client.request.return_value = {"rooms": [{"roomIndex": 0, "minStake": "6"}]}
        with self.assertRaisesRegex(ValueError, "minimum stake"):
            self.client.predict("123", {"456": "8"}, 0, "4", competition_id=42, request_id=KEY)
        self.client.request.assert_called_once_with("GET", "/api/coupons/123")

    def test_filtered_legacy_history_retains_cancelled_entries(self):
        self.client.request.return_value = {"bets": [
            {"id": 1, "points": "-", "status": "pending"},
            {"id": 2, "points": "20", "status": "lost"},
            {"id": 3, "points": "-", "status": "cancelled"}]}
        response = self.client.prediction_history(competition_id=42, day="2026-10-25")
        self.assertEqual([b["id"] for b in response["bets"]], [2, 3])
        self.client.request.assert_called_once_with("GET", "/api/bets", params={
            "competition_id": "42", "day": "2026-10-25"})

    def test_description_only_posts_agreed_public_text(self):
        self.client.update_public_description("  Research-led. Patient with uncertain events.  ")
        self.client.request.assert_called_once_with("POST", "/api/account/public-description", json={
            "description": "Research-led. Patient with uncertain events."})
        self.assertFalse((Path(self.temp.name) / "preferences").exists())
        with self.assertRaises(ValueError):
            self.client.update_public_description("x" * 501)

    def test_daily_history_filter_uses_settlement_status_not_available_points(self):
        self.client.request.return_value = {"bets": [
            {"id": 1, "competition_id": 42, "points": "50", "status": "pending"},
            {"id": 2, "competition_id": 42, "points": "-", "status": "canceled"},
            {"id": 3, "competition_id": 42, "points": "-", "status": "returned"},
            {"id": 4, "competition_id": 42, "points": "0", "status": "lost"},
            {"id": 5, "competition_id": 42, "points": "100", "status": "won"}]}
        response = self.client.prediction_history(competition_id=42)
        self.assertEqual([b["id"] for b in response["bets"]], [2, 3, 4, 5])
        self.assertEqual(response["count"], 4)

    def test_wallet_connect_does_not_convert_pending_to_connected(self):
        payload = {"success": True, "link_id": KEY, "status": "pending", "connect_url": "https://agentsports.io/wallet/connect/example"}
        self.client.request.return_value = payload
        self.assertEqual(self.client.wallet_connect(), payload)
        self.client.request.assert_called_once_with("POST", "/api/wallet/connect", json={})
        self.client.wallet_status(KEY)
        self.client.request.assert_called_with("GET", "/api/wallet/status", params={"link_id": KEY})
        self.client.wallet_config()
        self.client.request.assert_called_with("GET", "/api/wallet/config")


if __name__ == "__main__":
    unittest.main()
