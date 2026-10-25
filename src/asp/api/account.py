"""Account information and the user's public description."""

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

    def update_public_description(self, description: str) -> dict[str, Any]:
        if not isinstance(description, str):
            raise ValueError("Description must be text")
        description = description.strip()
        if len(description) > 500:
            raise ValueError("Public description must be at most 500 characters")
        return self.request("POST", "/api/account/public-description", json={"description": description})
