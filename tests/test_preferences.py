from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import Mock, patch

from asp.api import AspClient


class PreferencesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.environment = patch.dict(os.environ, {"ASP_MAX_STAKE": ""})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.client = AspClient(self.temp.name)
        self.client.request = Mock(return_value={"id": 41})

    def test_save_merges_private_fields_without_uploading_them(self):
        self.client.preferences_save({"strategy": "Use researched football forecasts.", "autonomy_enabled": True})
        response = self.client.preferences_save({"autonomy_enabled": False, "coaching": "Skip weak evidence."})
        self.assertEqual(response["preferences"]["strategy"], "Use researched football forecasts.")
        self.assertFalse(response["preferences"]["autonomy_enabled"])
        self.assertFalse(response["scheduler_changed"])
        self.assertEqual(self.client.preferences_show()["preferences"], response["preferences"])
        for request in self.client.request.call_args_list:
            self.assertEqual(request.args, ("GET", "/api/account"))
            self.assertEqual(request.kwargs, {})

    def test_state_is_private_and_scoped_to_account(self):
        self.client.preferences_save({"strategy": "Private account 41 strategy"})
        path = Path(self.temp.name) / "preferences" / "41.json"
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(path.parent.stat().st_mode), 0o700)
        self.client.request.return_value = {"id": 42}
        self.assertFalse(self.client.preferences_show()["stored"])
        self.client.preferences_save({"strategy": "Other account"})
        self.client.preferences_clear()
        self.assertTrue(path.exists())
        self.client.request.return_value = {"id": 41}
        self.assertEqual(self.client.preferences_show()["preferences"]["strategy"], "Private account 41 strategy")

    def test_same_account_id_on_another_origin_cannot_read_preferences(self):
        self.client.preferences_save({"strategy": "Production strategy"})
        other = AspClient(self.temp.name, base_url="https://example.test")
        other.request = Mock(return_value={"id": 41})
        self.assertFalse(other.preferences_show()["stored"])
        other.preferences_save({"strategy": "Test strategy"})
        self.assertEqual(self.client.preferences_show()["preferences"]["strategy"], "Production strategy")

    def test_signed_out_never_returns_previously_saved_preferences(self):
        self.client.preferences_save({"strategy": "Private"})
        self.client.request.return_value = {"error": "not_authenticated"}
        self.assertEqual(self.client.preferences_show(), {"error": "not_authenticated"})
        self.assertEqual(self.client.preferences_clear(), {"error": "not_authenticated"})
        self.assertTrue((Path(self.temp.name) / "preferences" / "41.json").exists())

    def test_unknown_credentials_and_invalid_scope_values_are_rejected(self):
        invalid = [{"password": "not-a-real-password"}, {"autonomy_enabled": "false"},
                   {"limits": {"max_entry_asp": float("inf")}},
                   {"limits": {"private_key": "not-a-key"}},
                   {"limits": {"max_entry_asp": -1}},
                   {"notification_cursors": {"2026-02-29": "cursor"}},
                   {"schedules": [{"host": "local", "id": "1"}, {"host": "local", "id": "1"}]}]
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.client.preferences_save(value)
        self.client.request.assert_not_called()

    def test_null_removes_field_and_decimal_limit_is_canonical(self):
        self.client.preferences_save({"coaching": "Temporary", "limits": {"max_entry_asp": 5}})
        self.client.preferences_save({"coaching": None})
        value = self.client.preferences_show()["preferences"]
        self.assertNotIn("coaching", value)
        self.assertEqual(value["limits"]["max_entry_asp"], "5")

    def test_corrupt_or_wrong_origin_preferences_fail_closed(self):
        self.client.preferences_save({"strategy": "Preserve"})
        path = Path(self.temp.name) / "preferences" / "41.json"
        original = json.loads(path.read_text())
        for content in ("{broken", json.dumps({**original, "origin": "https://other.test"}),
                        json.dumps({**original, "preferences": {"autonomy_enabled": "false"}})):
            path.write_text(content)
            with self.assertRaises(ValueError):
                self.client.preferences_show()
            with self.assertRaises(ValueError):
                self.client.preferences_save({"coaching": "Should not overwrite corrupt scope"})
            self.assertEqual(path.read_text(), content)

    def test_concurrent_preference_patches_do_not_drop_fields(self):
        other = AspClient(self.temp.name)
        other.request = Mock(return_value={"id": 41})
        with ThreadPoolExecutor(max_workers=2) as executor:
            first = executor.submit(self.client.preferences_save, {"strategy": "Researched plan"})
            second = executor.submit(other.preferences_save, {"language": "en"})
            first.result()
            second.result()
        self.assertEqual(self.client.preferences_show()["preferences"], {
            "strategy": "Researched plan", "language": "en"})


if __name__ == "__main__":
    unittest.main()
