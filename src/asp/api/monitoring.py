"""Monitoring: prediction history, active predictions."""

from __future__ import annotations

from typing import Any

from .validation import day_value, positive_id


class MonitoringMixin:
    """Monitoring methods mixed into AspClient."""

    def predictions(self, active_only: bool = False, competition_id: str | int | None = None,
                    day: str | None = None) -> dict[str, Any]:
        params: dict[str, str] = {}
        if active_only:
            params["active"] = "true"
        if competition_id is not None:
            params["competition_id"] = str(positive_id(competition_id, "competition_id"))
        if day is not None:
            params["day"] = day_value(day)
        return self.request("GET", "/api/bets", params=params or None)

    def active_predictions(self, competition_id: str | int | None = None,
                           day: str | None = None) -> dict[str, Any]:
        return self.predictions(active_only=True, competition_id=competition_id, day=day)

    def prediction_history(self, competition_id: str | int | None = None,
                           day: str | None = None) -> dict[str, Any]:
        result = self.predictions(active_only=False, competition_id=competition_id, day=day)
        if "bets" in result:
            settled_daily = {"won", "returned", "lost", "canceled"}
            calculated = [b for b in result["bets"] if (
                b.get("status") in settled_daily if b.get("competition_id") is not None
                else b.get("points") != "-" or b.get("status") == "cancelled"
            )]
            return {"bets": calculated, "count": len(calculated)}
        return result
