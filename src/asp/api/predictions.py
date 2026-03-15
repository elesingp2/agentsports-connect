"""Predictions: coupons, coupon details, submit prediction."""

from __future__ import annotations

import json
import re
from typing import Any


class PredictionMixin:
    """Prediction methods mixed into AspClient."""

    def coupons(self) -> dict[str, Any]:
        return self.request("GET", "/api/coupons")

    def coupon_details(self, path_or_id: str) -> dict[str, Any]:
        cid = _coupon_id(path_or_id)
        return self.request("GET", f"/api/coupons/{cid}")

    def predict(
        self,
        coupon_path: str,
        selections: dict[str, str] | str,
        room_index: int = 0,
        stake: str | int | float = "",
    ) -> dict[str, Any]:
        stake_value = "" if stake in ("", None) else str(stake)
        if self._max_stake is not None and stake_value:
            try:
                if float(stake_value) > self._max_stake:
                    return {"error": f"Stake {stake_value} exceeds ASP_MAX_STAKE limit ({self._max_stake})"}
            except ValueError:
                pass
        sel = json.loads(selections) if isinstance(selections, str) else selections
        cid = _coupon_id(coupon_path)
        body: dict[str, Any] = {"selections": sel, "roomIndex": room_index}
        if stake_value:
            body["stake"] = stake_value
        return self.request("POST", f"/api/coupons/{cid}/bet", json=body)


def _coupon_id(path_or_id: str) -> int:
    """Extract numeric coupon ID from path like '/FOOTBALL/laLiga/18638' or plain '18638'."""
    m = re.search(r"(\d+)$", str(path_or_id).strip())
    if m:
        return int(m.group(1))
    raise ValueError(f"Cannot extract coupon ID from: {path_or_id}")
