"""AspClient — central class for all agentsports.io API operations.

Lifecycle per request (CLI): load cookies → HTTP request → save cookies (under filelock).
Lifecycle per request (MCP): same, but AspClient instance is long-lived.
"""

from __future__ import annotations

import logging
import os
import hashlib
import re
from pathlib import Path
from decimal import Decimal, InvalidOperation
from urllib.parse import urljoin, urlparse
from typing import Any

import httpx

from .auth import AuthMixin
from .predictions import PredictionMixin
from .account import AccountMixin
from .monitoring import MonitoringMixin
from .state import StateManager

log = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://agentsports.io"
_TIMEOUT = httpx.Timeout(60.0, connect=15.0)


class AspClient(AuthMixin, PredictionMixin, AccountMixin, MonitoringMixin):
    """Stateful HTTP client with disk-persisted session and file locking.

    Each public method performs: lock → load → HTTP request → save → unlock.
    Auto-relogin on 401 if saved credentials are available.
    CSRF token extracted from responses and injected into subsequent requests.
    """

    def __init__(self, data_dir: str = "~/.asp/", base_url: str | None = None):
        self._base_url = (
            base_url or os.environ.get("ASP_BASE_URL", DEFAULT_BASE_URL)
        ).rstrip("/")
        parsed = urlparse(self._base_url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path:
            raise ValueError("ASP_BASE_URL must be an HTTP(S) origin without credentials or a path")
        # Retain primary-site state location; isolate every alternate origin (local dev included).
        if self._base_url != DEFAULT_BASE_URL:
            scope = hashlib.sha256(self._base_url.encode()).hexdigest()[:16]
            data_dir = str(Path(data_dir).expanduser() / "origins" / scope)
        self.state = StateManager(data_dir)
        self._max_stake = self._parse_max_stake()

    @staticmethod
    def _parse_max_stake() -> Decimal | None:
        raw = os.environ.get("ASP_MAX_STAKE", "").strip()
        if not raw:
            return None
        try:
            value = Decimal(raw)
        except InvalidOperation:
            raise ValueError("ASP_MAX_STAKE must be a positive finite number") from None
        if not value.is_finite() or value <= 0:
            raise ValueError("ASP_MAX_STAKE must be a positive finite number")
        return value

    def _same_origin(self, url: str) -> bool:
        a, b = urlparse(self._base_url), urlparse(url)
        return (b.username is None and b.password is None and
                (a.scheme, a.hostname, a.port) == (b.scheme, b.hostname, b.port))

    def request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        """Atomic HTTP request with auto-persist and optional auto-relogin.

        Keyword _allow_relogin (bool, default True): set False for login itself.
        """
        allow_relogin = kwargs.pop("_allow_relogin", True)
        clear_csrf = kwargs.pop("_clear_csrf", False)
        resp = self._do_request(method, path, allow_relogin=allow_relogin, clear_csrf=clear_csrf, **kwargs)
        return self._parse_response(resp)

    def _do_request(
        self,
        method: str,
        path: str,
        *,
        allow_relogin: bool = True,
        clear_csrf: bool = False,
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
                follow_redirects=False,
            ) as http:
                # Email activation creates a browser session without an API sessionToken.
                # The existing account page contains the same token used by the site's forms.
                if method.upper() != "GET" and path not in ("/api/login", "/api/register") and not csrf and cookies:
                    details = http.get("/user/details")
                    self._extract_csrf(details, meta)
                    if meta.get("csrf_token"):
                        headers["X-CSRF-TOKEN"] = meta["csrf_token"]
                resp = http.request(method, path, headers=headers, **kwargs)
                self._extract_csrf(resp, meta)

                # This explicit error is returned before any action is performed.
                # Refresh a stale token once; never retry arbitrary forbidden writes.
                if resp.status_code == 403 and method.upper() != "GET" and self._parse_response(resp).get("error") == "invalid_request_confirmation":
                    old_csrf = meta.get("csrf_token", "")
                    details = http.get("/user/details")
                    if details.is_success:
                        self._extract_csrf(details, meta)
                        refreshed_csrf = meta.get("csrf_token", "")
                        if refreshed_csrf and refreshed_csrf != old_csrf:
                            headers["X-CSRF-TOKEN"] = refreshed_csrf
                            resp = http.request(method, path, headers=headers, **kwargs)
                            self._extract_csrf(resp, meta)

                if resp.status_code == 401 and allow_relogin:
                    resp = self._try_relogin(http, method, path, headers, meta, resp, kwargs)
                    self._extract_csrf(resp, meta)

                if clear_csrf:
                    meta["csrf_token"] = ""
                self.state.save(http.cookies, meta)

        return resp

    def _try_relogin(
        self,
        http: httpx.Client,
        method: str,
        path: str,
        headers: dict[str, str],
        meta: dict[str, Any],
        orig_resp: httpx.Response,
        kwargs: dict[str, Any],
    ) -> httpx.Response:
        """Attempt auto-relogin with saved credentials, then retry the original request."""
        creds = self.state.load_credentials()
        if not creds:
            return orig_resp

        login_resp = http.post(
            "/api/login",
            json=creds,
            headers={"Accept": "application/json", "Content-Type": "application/json"},
        )
        if login_resp.status_code != 200:
            if login_resp.status_code == 401 and self._parse_response(login_resp).get("error") == "invalid_credentials":
                # A changed password must not cause repeated login attempts and a lockout.
                self.state.clear_credentials()
                meta["csrf_token"] = ""
            return orig_resp

        login_data = self._parse_response(login_resp)
        if not login_data.get("authenticated"):
            return orig_resp

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
                follow_redirects=False,
            ) as http:
                resp = http.get(url)
                for _ in range(5):
                    if not resp.is_redirect:
                        break
                    target = urljoin(str(resp.url), resp.headers.get("location", ""))
                    if not self._same_origin(target):
                        return {"error": "unsafe_confirmation_redirect", "status": resp.status_code}
                    resp = http.get(target)
                if resp.is_redirect:
                    return {"error": "too_many_redirects", "status": resp.status_code}
                self._extract_csrf(resp, meta)
                self.state.save(http.cookies, meta)
        return {
            "status": resp.status_code,
        }

    @staticmethod
    def _extract_csrf(resp: httpx.Response, meta: dict[str, Any]) -> None:
        """Extract CSRF token from response header, body, or cookie."""
        csrf = resp.headers.get("X-CSRF-Token")
        if not csrf:
            try:
                body = resp.json()
                if isinstance(body, dict):
                    csrf = body.get("sessionToken") or body.get("csrf_token")
            except Exception:
                if "text/html" in resp.headers.get("content-type", ""):
                    match = re.search(r'data-request-confirmation=["\']([^"\']+)["\']', resp.text)
                    csrf = match.group(1) if match else None
        if csrf:
            meta["csrf_token"] = csrf

    @staticmethod
    def _parse_response(resp: httpx.Response) -> dict[str, Any]:
        try:
            body = resp.json()
        except ValueError:
            body = None
        if not isinstance(body, dict):
            # Avoid reflecting HTML, cookies, confirmation tokens, or credentials in tool output.
            return {"error": "invalid_response", "status": resp.status_code}
        if not resp.is_success and not body.get("error"):
            return {**body, "error": "http_error", "status": resp.status_code}
        return body
