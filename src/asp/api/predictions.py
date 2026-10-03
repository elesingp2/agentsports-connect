"""Predictions: coupons, coupon details, submit prediction."""

from __future__ import annotations

import json
import re
from decimal import Decimal, InvalidOperation
from typing import Any


class PredictionMixin:
    """Prediction methods mixed into AspClient."""

    def coupons(self) -> dict[str, Any]:
        return self.request("GET", "/api/coupons")

    def coupon_details(self, path_or_id: str) -> dict[str, Any]:
        cid = _coupon_id(path_or_id)
        return self.request("GET", f"/api/coupons/{cid}")

    def coupon_rules(self, path_or_id: str) -> dict[str, Any]:
        cid = _coupon_id(path_or_id)
        return self.request("GET", f"/api/coupons/{cid}/rules")

    def predict(
        self,
        coupon_path: str,
        selections: dict[str, str] | str,
        room_index: int = 0,
        stake: str | int | float = "",
    ) -> dict[str, Any]:
        if isinstance(room_index, bool) or not isinstance(room_index, int) or room_index < 0:
            raise ValueError("room_index must be a nonnegative integer")
        stake_value = "" if stake in ("", None) else str(stake)
        if stake_value:
            try:
                amount = Decimal(stake_value)
            except InvalidOperation:
                raise ValueError("Stake must be a positive finite number") from None
            if not amount.is_finite() or amount <= 0:
                raise ValueError("Stake must be a positive finite number")
        if self._max_stake is not None:
            if not stake_value:
                raise ValueError("An explicit stake is required when ASP_MAX_STAKE is set")
            if amount > self._max_stake:
                raise ValueError(f"Stake exceeds ASP_MAX_STAKE ({self._max_stake})")
        sel = json.loads(selections) if isinstance(selections, str) else selections
        if not isinstance(sel, dict) or not sel:
            raise ValueError("Selections must be a nonempty JSON object")
        for key, value in sel.items():
            if not re.fullmatch(r"\d+(?::\d+)?", str(key)) or not isinstance(value, (str, int, float, bool)):
                raise ValueError("Selections map eventId or eventId:aspectCode to scalar outcome values")
            if isinstance(value, float) and not Decimal(str(value)).is_finite():
                raise ValueError("Selection values must be finite")
        cid = _coupon_id(coupon_path)
        if self._max_stake is not None:
            details = self.coupon_details(str(cid))
            if details.get("error"):
                return details
            room = next((r for r in details.get("rooms", []) if r.get("roomIndex") == room_index), None)
            if room is None:
                raise ValueError("Selected room is not available")
            # The backend can raise a submitted stake to the room minimum or fixed price.
            try:
                minimum = Decimal(str(room["minStake"]))
            except (KeyError, InvalidOperation):
                raise ValueError("Cannot verify the room's minimum stake") from None
            if not minimum.is_finite() or minimum > self._max_stake:
                raise ValueError("Room minimum stake exceeds ASP_MAX_STAKE")
        body: dict[str, Any] = {"selections": sel, "roomIndex": room_index}
        if stake_value:
            body["stake"] = stake_value
        return self.request("POST", f"/api/coupons/{cid}/bet", json=body)


def _coupon_id(path_or_id: str) -> int:
    """Extract numeric coupon ID from path like '/FOOTBALL/laLiga/18638' or plain '18638'."""
    m = re.fullmatch(r"(?:/(?:[^/?#]+/)*)?(\d+)", str(path_or_id).strip())
    if m:
        return int(m.group(1))
    raise ValueError(f"Cannot extract coupon ID from: {path_or_id}")
