"""StateManager — disk persistence for cookies, CSRF, and credentials with file locking."""

from __future__ import annotations

import json
import logging
import os
import tempfile
from http.cookiejar import Cookie
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
        self.dir.chmod(0o700)
        for name in ("cookies.json", "state.json", "credentials.json"):
            path = self.dir / name
            if path.exists():
                path.chmod(0o600)
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
                cookies.jar.set_cookie(Cookie(
                    version=0, name=c["name"], value=c["value"], port=None,
                    port_specified=False, domain=c.get("domain", ""),
                    domain_specified=c.get("domain_specified", bool(c.get("domain"))),
                    domain_initial_dot=c.get("domain_initial_dot", c.get("domain", "").startswith(".")),
                    path=c.get("path", "/"), path_specified=True,
                    secure=c.get("secure", False), expires=c.get("expires"),
                    discard=c.get("expires") is None, comment=None, comment_url=None,
                    rest=c.get("rest", {}), rfc2109=False,
                ))
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
                "domain_specified": cookie.domain_specified,
                "domain_initial_dot": cookie.domain_initial_dot,
                "path": cookie.path,
                "secure": cookie.secure,
                "expires": cookie.expires,
                "rest": cookie._rest,
            })
        self._write_json(self.cookie_file, jar_list)

    # ── metadata ───────────────────────────────────────────────────────

    def _load_meta(self) -> dict[str, Any]:
        if not self.state_file.exists():
            return {}
        try:
            data = json.loads(self.state_file.read_text())
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _save_meta(self, meta: dict[str, Any]) -> None:
        self._write_json(self.state_file, meta)

    # ── credentials ────────────────────────────────────────────────────

    def load_credentials(self) -> dict[str, str] | None:
        if not self.credentials_file.exists():
            return None
        try:
            data = json.loads(self.credentials_file.read_text())
            if isinstance(data, dict) and data.get("email") and data.get("password"):
                return data
        except Exception:
            pass
        return None

    def save_credentials(self, email: str, password: str) -> None:
        with self.lock():
            self._write_json(self.credentials_file, {"email": email, "password": password})

    def clear(self) -> None:
        """Forget the local login, including credentials used for auto-relogin."""
        with self.lock():
            for path in [self.cookie_file, self.state_file, self.credentials_file]:
                path.unlink(missing_ok=True)

    def _write_json(self, path: Path, value: Any) -> None:
        # Replacement is atomic and the file is private from creation, regardless of umask.
        fd, name = tempfile.mkstemp(dir=self.dir, prefix=f".{path.name}.")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(value, stream, ensure_ascii=False, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, path)
        finally:
            Path(name).unlink(missing_ok=True)
