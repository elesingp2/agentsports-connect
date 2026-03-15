"""StateManager — disk persistence for cookies, CSRF, and credentials with file locking."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

import filelock
import httpx

log = logging.getLogger(__name__)

DEFAULT_DATA_DIR = "~/.asp/"


class StateManager:
    """Manages session state on disk with file-level locking.

    Files managed:
        .lock            — filelock (automatic)
        cookies.json     — HTTP cookies (list of {name, value, domain, path})
        state.json       — CSRF token, last login timestamp, username
        credentials.json — email + password (if user allowed saving)
    """

    def __init__(self, data_dir: str = DEFAULT_DATA_DIR):
        self.dir = Path(data_dir).expanduser()
        self.dir.mkdir(parents=True, exist_ok=True)
        lock_timeout = int(os.environ.get("ASP_LOCK_TIMEOUT", "10"))
        self._lock = filelock.FileLock(str(self.dir / ".lock"), timeout=lock_timeout)

    @property
    def cookie_file(self) -> Path:
        return self.dir / "cookies.json"

    @property
    def state_file(self) -> Path:
        return self.dir / "state.json"

    @property
    def credentials_file(self) -> Path:
        return self.dir / "credentials.json"

    def lock(self) -> filelock.FileLock:
        """Context manager. Holds lock for the duration of load → request → save."""
        return self._lock

    def load(self) -> tuple[httpx.Cookies, dict[str, Any]]:
        """Read cookies and metadata from disk."""
        cookies = self._load_cookies()
        meta = self._load_meta()
        return cookies, meta

    def save(self, cookies: httpx.Cookies, meta: dict[str, Any]) -> None:
        """Write updated cookies and metadata to disk."""
        self._save_cookies(cookies)
        self._save_meta(meta)

    # ── cookies ────────────────────────────────────────────────────────

    def _load_cookies(self) -> httpx.Cookies:
        cookies = httpx.Cookies()
        if not self.cookie_file.exists():
            return cookies
        try:
            for c in json.loads(self.cookie_file.read_text()):
                cookies.set(c["name"], c["value"], domain=c.get("domain", ""))
        except Exception:
            log.debug("Failed to load cookies", exc_info=True)
        return cookies

    def _save_cookies(self, cookies: httpx.Cookies) -> None:
        jar_list = []
        for cookie in cookies.jar:
            jar_list.append({
                "name": cookie.name,
                "value": cookie.value,
                "domain": cookie.domain,
                "path": cookie.path,
            })
        self.cookie_file.write_text(json.dumps(jar_list, ensure_ascii=False, indent=2))

    # ── metadata ───────────────────────────────────────────────────────

    def _load_meta(self) -> dict[str, Any]:
        if not self.state_file.exists():
            return {}
        try:
            return json.loads(self.state_file.read_text())
        except Exception:
            return {}

    def _save_meta(self, meta: dict[str, Any]) -> None:
        self.state_file.write_text(json.dumps(meta, ensure_ascii=False, indent=2))

    # ── credentials ────────────────────────────────────────────────────

    def load_credentials(self) -> dict[str, str] | None:
        if not self.credentials_file.exists():
            return None
        try:
            data = json.loads(self.credentials_file.read_text())
            if data.get("email") and data.get("password"):
                return data
        except Exception:
            pass
        return None

    def save_credentials(self, email: str, password: str) -> None:
        self.credentials_file.write_text(
            json.dumps({"email": email, "password": password}, indent=2)
        )

