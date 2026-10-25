from __future__ import annotations

import json
import tempfile
import unittest
from unittest.mock import Mock, patch

from click.testing import CliRunner
import httpx

from asp.cli import cli


KEY = "89ed5a47-8567-45c9-bdf3-87a84cfa2cf6"


class CliTests(unittest.TestCase):
    def setUp(self):
        self.runner = CliRunner()
        self.client = Mock()
        self.factory = patch("asp.cli.AspClient", return_value=self.client)
        self.factory.start()
        self.addCleanup(self.factory.stop)

    def invoke(self, *args):
        return self.runner.invoke(cli, list(args))

    def test_daily_join_and_claim_return_matching_keys(self):
        for command in ("join", "claim"):
            method = getattr(self.client, "daily_" + command)
            method.return_value = {"joined": True, "request_id": KEY}
            result = self.invoke("daily", command, "--day", "2026-10-25", "--request-id", KEY)
            self.assertEqual(result.exit_code, 0, result.output)
            self.assertEqual(json.loads(result.stdout)["request_id"], KEY)
            method.assert_called_once_with(day="2026-10-25", request_id=KEY)

    def test_network_timeout_returns_key_for_retry(self):
        self.client.predict.side_effect = httpx.ReadTimeout("response not received")
        result = self.invoke("predict", "--coupon", "123", "--selections", '{"456":"8"}',
                             "--stake", "5", "--competition", "42", "--request-id", KEY)
        self.assertEqual(result.exit_code, 2)
        self.assertEqual(json.loads(result.stderr), {"error": "timeout", "request_id": KEY})
        self.assertEqual(self.client.predict.call_args.kwargs, {"competition_id": 42, "request_id": KEY})

    def test_generated_join_key_survives_connection_error(self):
        self.client.daily_join.side_effect = httpx.ConnectError("connection failed")
        result = self.invoke("daily", "join")
        self.assertEqual(result.exit_code, 2)
        data = json.loads(result.stderr)
        self.assertEqual(data["request_id"], self.client.daily_join.call_args.kwargs["request_id"])
        self.assertRegex(data["request_id"], r"^[0-9a-f-]{36}$")

    def test_api_failure_has_nonzero_exit(self):
        self.client.daily_join.return_value = {"success": False, "error": "wallet_required"}
        result = self.invoke("daily", "join")
        self.assertEqual(result.exit_code, 1)
        self.assertEqual(json.loads(result.stdout)["error"], "wallet_required")

    def test_disabled_is_not_converted_to_ready(self):
        self.client.daily_status.return_value = {"enabled": False, "can_join": False, "state": "disabled"}
        result = self.invoke("daily", "status")
        self.assertEqual(result.exit_code, 0)
        self.assertFalse(json.loads(result.stdout)["enabled"])

    def test_me_and_history_have_explicit_day_semantics(self):
        self.client.daily_me.return_value = {"joined": False}
        self.client.daily_history.return_value = {"entries": [{"id": 1, "status": "pending"}]}
        self.assertEqual(self.invoke("daily", "status", "--me").exit_code, 0)
        self.client.daily_me.assert_called_once_with(day=None)
        history = self.invoke("daily", "history", "--day", "2026-10-24")
        self.assertEqual(json.loads(history.stdout)["entries"][0]["status"], "pending")
        self.assertEqual(self.invoke("daily", "history").exit_code, 3)

    def test_profile_and_private_preferences_are_separate_commands(self):
        self.client.update_public_description.return_value = {"success": True}
        self.client.preferences_save.return_value = {"saved": True, "scheduler_changed": False}
        self.assertEqual(self.invoke("profile", "description", "Two public sentences. Clear approach.").exit_code, 0)
        result = self.invoke("preferences", "save", "--json", '{"strategy":"Private plan"}')
        self.assertEqual(result.exit_code, 0, result.output)
        self.client.update_public_description.assert_called_once_with("Two public sentences. Clear approach.")
        self.client.preferences_save.assert_called_once_with({"strategy": "Private plan"})

    def test_wallet_pending_and_verified_are_not_reinterpreted(self):
        self.client.wallet_connect.return_value = {"status": "pending", "link_id": KEY}
        result = self.invoke("wallet", "connect")
        self.assertEqual(json.loads(result.stdout)["status"], "pending")
        self.client.wallet_status.return_value = {"connected": True, "status": "verified"}
        result = self.invoke("wallet", "status", "--link-id", KEY)
        self.assertTrue(json.loads(result.stdout)["connected"])
        self.client.wallet_status.assert_called_once_with(link_id=KEY)

    def test_invalid_cli_arguments_are_json_and_do_not_call_api(self):
        result = self.invoke("daily", "leaderboard", "--page", "0")
        self.assertEqual(result.exit_code, 3)
        self.assertEqual(json.loads(result.stderr)["error"], "invalid_argument")
        self.client.daily_leaderboard.assert_not_called()
        result = self.invoke("preferences", "save", "--json", "{invalid")
        self.assertEqual(result.exit_code, 3)
        self.client.preferences_save.assert_not_called()


if __name__ == "__main__":
    unittest.main()
