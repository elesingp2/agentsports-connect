"""Account: account info, payment methods, social, daily bonus."""

from __future__ import annotations

from typing import Any


class AccountMixin:
    """Account methods mixed into AspClient."""

    def account(self) -> dict[str, Any]:
        return self.request("GET", "/api/account")

    def payment_methods(self) -> dict[str, Any]:
        return self.request("GET", "/api/payment-methods")

    def social(self) -> dict[str, Any]:
        return self.request("GET", "/api/social")

    def daily_status(self) -> dict[str, Any]:
        return self.request("GET", "/api/daily")

    def daily_claim(self) -> dict[str, Any]:
        return self.request("POST", "/api/daily/claim")
