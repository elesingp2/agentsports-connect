"""Start a human-signed wallet connection; never sign or transfer funds."""

from __future__ import annotations

import re
from typing import Any


class WalletMixin:
    def wallet_config(self) -> dict[str, Any]:
        return self.request("GET", "/api/wallet/config")

    def wallet_connect(self) -> dict[str, Any]:
        return self.request("POST", "/api/wallet/connect", json={})

    def wallet_status(self, link_id: str | None = None) -> dict[str, Any]:
        if link_id is not None and (
            not isinstance(link_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,200}", link_id)
        ):
            raise ValueError("link_id contains invalid characters")
        params = {"link_id": link_id} if link_id is not None else None
        return self.request("GET", "/api/wallet/status", params=params)
