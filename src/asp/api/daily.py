"""Daily competition reads and an idempotent join."""

from __future__ import annotations

from typing import Any

from .validation import day_value, request_key


class DailyMixin:
    def daily_status(self, day: str | None = None) -> dict[str, Any]:
        params = {"day": day_value(day)} if day is not None else None
        return self.request("GET", "/api/daily", params=params)

    def daily_me(self, day: str | None = None) -> dict[str, Any]:
        params = {"day": day_value(day)} if day is not None else None
        return self.request("GET", "/api/daily/me", params=params)

    def daily_history(self, day: str) -> dict[str, Any]:
        """The full day snapshot includes pending, settled and cancelled entries."""
        return self.daily_me(day_value(day))

    def daily_join(self, day: str | None = None, request_id: str | None = None) -> dict[str, Any]:
        """Compatibility alias for the existing daily-bonus claim."""
        return self.daily_claim(day=day, request_id=request_id)

    def daily_claim(self, day: str | None = None, request_id: str | None = None) -> dict[str, Any]:
        key = request_key(request_id)
        body: dict[str, Any] = {"request_id": key}
        if day is not None:
            body["day"] = day_value(day)
        result = self.request("POST", "/api/daily/claim", json=body)
        return {**result, "request_id": key}

    def daily_leaderboard(self, day: str | None = None, scope: str = "daily", page: int = 1) -> dict[str, Any]:
        if scope not in ("daily", "30d"):
            raise ValueError("Leaderboard scope must be daily or 30d")
        if isinstance(page, bool) or not isinstance(page, int) or not 1 <= page <= 100000:
            raise ValueError("Leaderboard page must be between 1 and 100000")
        params: dict[str, Any] = {"scope": scope, "page": page}
        if day is not None:
            params["day"] = day_value(day)
        return self.request("GET", "/api/daily/leaderboard", params=params)
