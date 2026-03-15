"""AspClient — central class for all agentsport.io API operations.

Lifecycle per request (CLI): load cookies → HTTP request → save cookies (under filelock).
Lifecycle per request (MCP): same, but AspClient instance is long-lived.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

from .auth import AuthMixin
from .predictions import PredictionMixin
from .account import AccountMixin
from .monitoring import MonitoringMixin
from .state import StateManager

log = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://agentsport.io"
_TIMEOUT = httpx.Timeout(30.0, connect=10.0)


class AspClient(AuthMixin, PredictionMixin, AccountMixin, MonitoringMixin):
    """Stateful HTTP client with disk-persisted session and file locking.

    Each public method performs: lock → load → HTTP request → save → unlock.
    Auto-relogin on 401 if saved credentials are available.
    CSRF token extracted from responses and injected into subsequent requests.
    """

    def __init__(self, data_dir: str = "~/.asp/", base_url: str | None = None):
        self.state = StateManager(data_dir)
        self._base_url = (
            base_url or os.environ.get("ASP_BASE_URL", DEFAULT_BASE_URL)
        ).rstrip("/")
        self._max_stake = self._parse_max_stake()

    @staticmethod
    def _parse_max_stake() -> float | None:
        raw = os.environ.get("ASP_MAX_STAKE", "").strip()
        return float(raw) if raw else None

    def request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        """Atomic HTTP request with auto-persist and optional auto-relogin.

        Keyword _allow_relogin (bool, default True): set False for login itself.
        """
        allow_relogin = kwargs.pop("_allow_relogin", True)
        resp = self._do_request(method, path, allow_relogin=allow_relogin, **kwargs)
        return self._parse_response(resp)

    def _do_request(
        self,
        method: str,
        path: str,
        *,
        allow_relogin: bool = True,
        **kwargs: Any,
    ) -> httpx.Response:
        with self.state.lock():
            cookies, meta = self.state.load()
            csrf = meta.get("csrf_token", "")

            headers = kwargs.pop("headers", {})
            headers.setdefault("Accept", "application/json")
            if csrf:
                headers["X-CSRF-TOKEN"] = csrf

            with httpx.Client(
                base_url=self._base_url,
                cookies=cookies,
                timeout=_TIMEOUT,
                follow_redirects=True,
            ) as http:
                resp = http.request(method, path, headers=headers, **kwargs)
                self._extract_csrf(resp, meta)

                if resp.status_code == 401 and allow_relogin:
                    resp = self._try_relogin(http, method, path, headers, meta, kwargs)

                self.state.save(http.cookies, meta)

        return resp

    def _try_relogin(
        self,
        http: httpx.Client,
        method: str,
        path: str,
        headers: dict[str, str],
        meta: dict[str, Any],
        kwargs: dict[str, Any],
    ) -> httpx.Response:
        """Attempt auto-relogin with saved credentials, then retry the original request."""
        creds = self.state.load_credentials()
        if not creds:
            return http.request(method, path, headers=headers, **kwargs)

        login_resp = http.post(
            "/api/login",
            json=creds,
            headers={"Accept": "application/json", "Content-Type": "application/json"},
        )
        if login_resp.status_code != 200:
            return http.request(method, path, headers=headers, **kwargs)

        login_data = self._parse_response(login_resp)
        if not login_data.get("authenticated"):
            return http.request(method, path, headers=headers, **kwargs)

        self._extract_csrf(login_resp, meta)
        csrf = meta.get("csrf_token", "")
        if csrf:
            headers["X-CSRF-TOKEN"] = csrf

        log.info("Auto-relogin successful, retrying request")
        return http.request(method, path, headers=headers, **kwargs)

    def _raw_get(self, url: str) -> dict[str, Any]:
        """Direct GET to an arbitrary URL (e.g. confirmation links)."""
        with self.state.lock():
            cookies, meta = self.state.load()
            with httpx.Client(
                cookies=cookies,
                timeout=_TIMEOUT,
                follow_redirects=True,
            ) as http:
                resp = http.get(url)
                self.state.save(http.cookies, meta)
        return {
            "confirmed": resp.status_code in (200, 302),
            "status": resp.status_code,
            "url": str(resp.url),
        }

    @staticmethod
    def _extract_csrf(resp: httpx.Response, meta: dict[str, Any]) -> None:
        """Extract CSRF token from response header, body, or cookie."""
        csrf = resp.headers.get("X-CSRF-Token")
        if not csrf:
            try:
                body = resp.json()
                csrf = body.get("sessionToken") or body.get("csrf_token")
            except Exception:
                pass
        if csrf:
            meta["csrf_token"] = csrf

    @staticmethod
    def _parse_response(resp: httpx.Response) -> dict[str, Any]:
        try:
            return resp.json()
        except Exception:
            return {"error": "invalid_response", "status": resp.status_code, "body": resp.text[:500]}
