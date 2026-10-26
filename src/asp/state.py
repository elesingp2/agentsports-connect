"""Private files for session cookies, credentials and optional coaching preferences."""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import tempfile
from datetime import date
from decimal import Decimal, InvalidOperation
from http.cookiejar import Cookie
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

import filelock
import httpx

log = logging.getLogger(__name__)


def create_session(data_dir: str = "~/.asp/", base_url: str | None = None) -> dict[str, Any]:
    origin = (base_url or os.environ.get("ASP_BASE_URL", "https://agentsports.io")).rstrip("/")
    parsed = urlparse(origin)
    if (parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username
        or parsed.password or parsed.query or parsed.fragment or parsed.path):
        raise ValueError("ASP_BASE_URL must be an HTTP(S) origin without credentials or a path")
    directory = Path(data_dir).expanduser()
    if origin != "https://agentsports.io":
        directory /= "origins/" + hashlib.sha256(origin.encode()).hexdigest()[:16]
    directory.mkdir(parents=True, exist_ok=True)
    directory.chmod(0o700)
    for name in ("cookies.json", "state.json", "credentials.json"):
        path = directory / name
        if path.exists():
            path.chmod(0o600)
    maximum = os.environ.get("ASP_MAX_STAKE", "").strip()
    if maximum:
        try:
            maximum = Decimal(maximum)
        except InvalidOperation:
            raise ValueError("ASP_MAX_STAKE must be a positive finite number") from None
        if not maximum.is_finite() or maximum <= 0:
            raise ValueError("ASP_MAX_STAKE must be a positive finite number")
    return {"origin": origin, "directory": directory, "max_stake": maximum or None,
            "lock": filelock.FileLock(str(directory / ".lock"), timeout=int(os.environ.get("ASP_LOCK_TIMEOUT", "10")))}


def load(session) -> tuple[httpx.Cookies, dict[str, Any]]:
    """Read cookies and metadata from disk."""
    cookies = _load_cookies(session)
    meta = _load_meta(session)
    return cookies, meta


def save(session, cookies: httpx.Cookies, meta: dict[str, Any]) -> None:
    """Write updated cookies and metadata to disk."""
    _save_cookies(session, cookies)
    _save_meta(session, meta)


def _load_cookies(session) -> httpx.Cookies:
    cookies = httpx.Cookies()
    if not (session["directory"] / "cookies.json").exists():
        return cookies
    try:
        for c in json.loads((session["directory"] / "cookies.json").read_text()):
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


def _save_cookies(session, cookies: httpx.Cookies) -> None:
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
    _write_json(session, (session["directory"] / "cookies.json"), jar_list)


def _load_meta(session) -> dict[str, Any]:
    if not (session["directory"] / "state.json").exists():
        return {}
    try:
        data = json.loads((session["directory"] / "state.json").read_text())
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_meta(session, meta: dict[str, Any]) -> None:
    _write_json(session, (session["directory"] / "state.json"), meta)


def load_credentials(session) -> dict[str, str] | None:
    if not (session["directory"] / "credentials.json").exists():
        return None
    try:
        data = json.loads((session["directory"] / "credentials.json").read_text())
        if isinstance(data, dict) and data.get("email") and data.get("password"):
            return data
    except Exception:
        pass
    return None


def save_credentials(session, email: str, password: str) -> None:
    with session["lock"]:
        _write_json(session, (session["directory"] / "credentials.json"), {"email": email, "password": password})
        meta = _load_meta(session)
        meta.pop("auto_relogin_blocked", None)
        _save_meta(session, meta)


def clear(session) -> None:
    """Forget the local login, including credentials used for auto-relogin."""
    with session["lock"]:
        for path in [(session["directory"] / "cookies.json"), (session["directory"] / "state.json"), (session["directory"] / "credentials.json")]:
            path.unlink(missing_ok=True)


def clear_credentials(session) -> None:
    """Remove stored credentials without changing the current session."""
    with session["lock"]:
        (session["directory"] / "credentials.json").unlink(missing_ok=True)


def _write_json(session, path: Path, value: Any) -> None:
    # Replacement is atomic and the file is private from creation, regardless of umask.
    fd, name = tempfile.mkstemp(dir=session["directory"], prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def _preferences_path(session, account_id: int, create: bool = False) -> Path:
    account_id = positive_id(account_id, "account id")
    directory = session["directory"] / "preferences"
    if create:
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    if directory.exists():
        directory.chmod(0o700)
    return directory / f"{account_id}.json"


def load_preferences(session, account_id: int) -> dict[str, Any] | None:
    """Caller holds the state lock; corrupt preferences must never look like a fresh setup."""
    path = _preferences_path(session, account_id)
    if not path.exists():
        return None
    path.chmod(0o600)
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        raise ValueError("Saved preferences are unreadable; recover them before resuming autonomy") from None
    if (not isinstance(document, dict) or document.get("schema_version") != 1
        or document.get("account_id") != account_id or not isinstance(document.get("preferences"), dict)):
        raise ValueError("Saved preferences do not match this account or supported schema")
    return document


def save_preferences(session, account_id: int, document: dict[str, Any]) -> None:
    _write_json(session, _preferences_path(session, account_id, create=True), document)


def clear_preferences(session, account_id: int) -> None:
    _preferences_path(session, account_id).unlink(missing_ok=True)


def day_value(value: str | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError("Day must be YYYY-MM-DD (UTC)")
    try:
        date.fromisoformat(value)
    except ValueError:
        raise ValueError("Day must be a valid YYYY-MM-DD date (UTC)") from None
    return value


def positive_id(value: str | int, label: str) -> int:
    if isinstance(value, bool) or not re.fullmatch(r"[1-9]\d{0,18}", str(value)):
        raise ValueError(f"{label} must be a positive integer")
    number = int(value)
    if number > 9223372036854775807:
        raise ValueError(f"{label} is too large")
    return number


def request_key(value: str | None) -> str:
    if value is None:
        return str(uuid4())
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{8,100}", value):
        raise ValueError("request_id must contain 8–100 letters, digits, underscores or hyphens")
    return value


TEXT_FIELDS = {"strategy", "personality", "coaching", "language", "timezone"}
FIELDS = TEXT_FIELDS | {"autonomy_enabled", "limits", "schedules", "notification_cursors"}
LIMIT_FIELDS = {"max_entry_asp", "max_coupon_asp", "min_reserve_asp"}


def validate_preferences(patch: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(patch, dict):
        raise ValueError("Preferences must be a JSON object")
    if set(patch) - FIELDS:
        raise ValueError("Unknown preference field; credentials belong only in credential storage")
    # Round-trip rejects objects that could not actually be stored, and detaches caller-owned values.
    try:
        text = json.dumps(patch, allow_nan=False, ensure_ascii=False)
    except (ValueError, TypeError):
        raise ValueError("Preferences must contain valid JSON values") from None
    if len(text.encode("utf-8")) > 65536:
        raise ValueError("Preferences must be at most 64 KiB")
    value = json.loads(text)
    for key, item in value.items():
        if item is None:  # Explicit removal of a previously stored preference.
            continue
        if key in TEXT_FIELDS and not isinstance(item, str):
            raise ValueError(f"{key} must be text")
        if key == "autonomy_enabled" and not isinstance(item, bool):
            raise ValueError("autonomy_enabled must be true or false")
        if key == "limits":
            if not isinstance(item, dict) or set(item) - LIMIT_FIELDS:
                raise ValueError("limits accepts max_entry_asp, max_coupon_asp and min_reserve_asp")
            for limit, amount in item.items():
                try:
                    parsed = Decimal(str(amount))
                except InvalidOperation:
                    raise ValueError(f"{limit} must be a finite nonnegative amount") from None
                if not parsed.is_finite() or parsed < 0:
                    raise ValueError(f"{limit} must be a finite nonnegative amount")
                item[limit] = str(parsed)
        if key == "schedules":
            if not isinstance(item, list):
                raise ValueError("schedules must be a list")
            identities = set()
            for schedule in item:
                if (not isinstance(schedule, dict)
                    or set(schedule) - {"host", "id", "status", "next_run_at"}
                    or not all(isinstance(v, str) for v in schedule.values())
                    or not schedule.get("host", "").strip() or not schedule.get("id", "").strip()):
                    raise ValueError("Each schedule needs host and id; status and next_run_at are optional text")
                identity = (schedule["host"], schedule["id"])
                if identity in identities:
                    raise ValueError("Duplicate schedule host/id")
                identities.add(identity)
        if key == "notification_cursors":
            if not isinstance(item, dict):
                raise ValueError("notification_cursors must map UTC day to cursor text")
            for day, cursor in item.items():
                day_value(day)
                if not isinstance(cursor, str):
                    raise ValueError("Notification cursors must be text")
    return value
