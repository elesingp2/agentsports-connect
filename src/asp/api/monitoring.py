"""Monitoring: prediction history, active predictions."""

from __future__ import annotations

from typing import Any


class MonitoringMixin:
    """Monitoring methods mixed into AspClient."""

    def predictions(self, active_only: bool = False) -> dict[str, Any]:
        params: dict[str, str] = {}
        if active_only:
            params["active"] = "true"
        return self.request("GET", "/api/bets", params=params or None)

    def active_predictions(self) -> dict[str, Any]:
        return self.predictions(active_only=True)

    def prediction_history(self) -> dict[str, Any]:
        return self.predictions(active_only=False)
