"""Optional private coaching state, scoped to the authenticated account and origin."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import json
from typing import Any

from .validation import day_value, positive_id


TEXT_FIELDS = {"strategy", "personality", "coaching", "language", "timezone"}
FIELDS = TEXT_FIELDS | {"autonomy_enabled", "limits", "schedules", "notification_cursors"}
LIMIT_FIELDS = {"max_entry_asp", "max_coupon_asp", "min_reserve_asp"}


def validate_preferences(patch: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(patch, dict):
        raise ValueError("Preferences must be a JSON object")
    if set(patch) - FIELDS:
        raise ValueError("Unknown preference field; credentials belong only in credential storage")
    # Round-trip rejects objects that could not actually be stored, and detaches caller-owned values.
    try:
        text = json.dumps(patch, allow_nan=False, ensure_ascii=False)
    except (ValueError, TypeError):
        raise ValueError("Preferences must contain valid JSON values") from None
    if len(text.encode("utf-8")) > 65536:
        raise ValueError("Preferences must be at most 64 KiB")
    value = json.loads(text)
    for key, item in value.items():
        if item is None:  # Explicit removal of a previously stored preference.
            continue
        if key in TEXT_FIELDS and not isinstance(item, str):
            raise ValueError(f"{key} must be text")
        if key == "autonomy_enabled" and not isinstance(item, bool):
            raise ValueError("autonomy_enabled must be true or false")
        if key == "limits":
            if not isinstance(item, dict) or set(item) - LIMIT_FIELDS:
                raise ValueError("limits accepts max_entry_asp, max_coupon_asp and min_reserve_asp")
            for limit, amount in item.items():
                try:
                    parsed = Decimal(str(amount))
                except InvalidOperation:
                    raise ValueError(f"{limit} must be a finite nonnegative amount") from None
                if not parsed.is_finite() or parsed < 0:
                    raise ValueError(f"{limit} must be a finite nonnegative amount")
                item[limit] = str(parsed)
        if key == "schedules":
            if not isinstance(item, list):
                raise ValueError("schedules must be a list")
            identities = set()
            for schedule in item:
                if (not isinstance(schedule, dict)
                    or set(schedule) - {"host", "id", "status", "next_run_at"}
                    or not all(isinstance(v, str) for v in schedule.values())
                    or not schedule.get("host", "").strip() or not schedule.get("id", "").strip()):
                    raise ValueError("Each schedule needs host and id; status and next_run_at are optional text")
                identity = (schedule["host"], schedule["id"])
                if identity in identities:
                    raise ValueError("Duplicate schedule host/id")
                identities.add(identity)
        if key == "notification_cursors":
            if not isinstance(item, dict):
                raise ValueError("notification_cursors must map UTC day to cursor text")
            for day, cursor in item.items():
                day_value(day)
                if not isinstance(cursor, str):
                    raise ValueError("Notification cursors must be text")
    return value


class PreferencesMixin:
    def _load_preferences(self, account_id: int) -> dict[str, Any] | None:
        document = self.state.load_preferences(account_id)
        if document is not None:
            if document.get("origin") != self._base_url:
                raise ValueError("Saved preferences do not match this site")
            document["preferences"] = validate_preferences(document["preferences"])
        return document

    def _preferences_account(self) -> tuple[int | None, dict[str, Any] | None]:
        account = self.account()
        if account.get("error") or account.get("success") is False:
            return None, account
        if account.get("id") is None:
            return None, {"error": "not_authenticated"}
        return positive_id(account["id"], "account id"), None

    def preferences_show(self) -> dict[str, Any]:
        account_id, error = self._preferences_account()
        if error is not None:
            return error
        with self.state.lock():
            document = self._load_preferences(account_id)
        return {"account_id": account_id, "stored": document is not None,
                "preferences": document.get("preferences", {}) if document else {},
                "updated_at": document.get("updated_at") if document else None,
                "storage": "private_local"}

    def preferences_save(self, patch: dict[str, Any]) -> dict[str, Any]:
        patch = validate_preferences(patch)
        account_id, error = self._preferences_account()
        if error is not None:
            return error
        with self.state.lock():
            current = self._load_preferences(account_id) or {}
            preferences = current.get("preferences", {}).copy()
            for key, value in patch.items():
                if value is None:
                    preferences.pop(key, None)
                else:
                    preferences[key] = value
            preferences = validate_preferences(preferences)
            document = {"schema_version": 1, "account_id": account_id, "origin": self._base_url,
                        "updated_at": datetime.now(timezone.utc).isoformat(), "preferences": preferences}
            self.state.save_preferences(account_id, document)
        return {"saved": True, "account_id": account_id, "preferences": preferences,
                "storage": "private_local", "scheduler_changed": False}

    def preferences_clear(self) -> dict[str, Any]:
        account_id, error = self._preferences_account()
        if error is not None:
            return error
        with self.state.lock():
            self.state.clear_preferences(account_id)
        return {"cleared": True, "account_id": account_id, "scheduler_changed": False}
