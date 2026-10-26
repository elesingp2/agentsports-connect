"""AgentSports HTTP calls: auth, coupons, Daily, wallet and private preferences."""
from __future__ import annotations

import json
import logging
import re
import secrets
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

from . import state
from .state import day_value, positive_id, request_key, validate_preferences

log = logging.getLogger(__name__)
_TIMEOUT = httpx.Timeout(60.0, connect=15.0)


def _same_origin(session, url: str) -> bool:
    a, b = urlparse(session["origin"]), urlparse(url)
    return (b.username is None and b.password is None and
            (a.scheme, a.hostname, a.port) == (b.scheme, b.hostname, b.port))


def request(session, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
    """Atomic HTTP request with auto-persist and optional auto-relogin.

    Keyword _allow_relogin (bool, default True): set False for login itself.
    """
    allow_relogin = kwargs.pop("_allow_relogin", True)
    clear_csrf = kwargs.pop("_clear_csrf", False)
    resp = _do_request(session, method, path, allow_relogin=allow_relogin, clear_csrf=clear_csrf, **kwargs)
    return _parse_response(resp)


def _do_request(
    session,
    method: str,
    path: str,
    *,
    allow_relogin: bool = True,
    clear_csrf: bool = False,
    **kwargs: Any,
) -> httpx.Response:
    with session["lock"]:
        cookies, meta = state.load(session)
        csrf = meta.get("csrf_token", "")

        headers = kwargs.pop("headers", {})
        headers.setdefault("Accept", "application/json")
        if csrf:
            headers["X-CSRF-TOKEN"] = csrf

        with httpx.Client(
            base_url=session["origin"],
            cookies=cookies,
            timeout=_TIMEOUT,
            follow_redirects=False,
        ) as http:
            # Email activation creates a browser session without an API sessionToken.
            # The existing account page contains the same token used by the site's forms.
            if method.upper() != "GET" and path not in ("/api/login", "/api/register", "/api/register/resend") and not csrf and cookies:
                details = http.get("/user/details")
                _extract_csrf(details, meta)
                if meta.get("csrf_token"):
                    headers["X-CSRF-TOKEN"] = meta["csrf_token"]
            resp = http.request(method, path, headers=headers, **kwargs)
            _extract_csrf(resp, meta)

            # This explicit error is returned before any action is performed.
            # Refresh a stale token once; never retry arbitrary forbidden writes.
            if resp.status_code == 403 and method.upper() != "GET" and _parse_response(resp).get("error") == "invalid_request_confirmation":
                old_csrf = meta.get("csrf_token", "")
                details = http.get("/user/details")
                if details.is_success:
                    _extract_csrf(details, meta)
                    refreshed_csrf = meta.get("csrf_token", "")
                    if refreshed_csrf and refreshed_csrf != old_csrf:
                        headers["X-CSRF-TOKEN"] = refreshed_csrf
                        resp = http.request(method, path, headers=headers, **kwargs)
                        _extract_csrf(resp, meta)

            if resp.status_code == 401 and allow_relogin:
                resp = _try_relogin(session, http, method, path, headers, meta, resp, kwargs)
                _extract_csrf(resp, meta)

            if clear_csrf:
                meta["csrf_token"] = ""
            state.save(session, http.cookies, meta)

    return resp


def _try_relogin(
    session,
    http: httpx.Client,
    method: str,
    path: str,
    headers: dict[str, str],
    meta: dict[str, Any],
    orig_resp: httpx.Response,
    kwargs: dict[str, Any],
) -> httpx.Response:
    """Attempt auto-relogin with saved credentials, then retry the original request."""
    creds = state.load_credentials(session)
    if not creds or meta.get("auto_relogin_blocked"):
        return orig_resp

    login_resp = http.post(
        "/api/login",
        json=creds,
        headers={"Accept": "application/json", "Content-Type": "application/json"},
    )
    if login_resp.status_code != 200:
        if _parse_response(login_resp).get("error") in ("invalid_credentials", "too_many_attempts"):
            # An unconfirmed account also returns invalid_credentials. Keep
            # its password for confirmation/resend and the owner's handoff;
            # stop automatic attempts until an explicit login succeeds.
            meta["auto_relogin_blocked"] = True
            meta["csrf_token"] = ""
        return login_resp

    login_data = _parse_response(login_resp)
    if not login_data.get("authenticated"):
        return orig_resp

    _extract_csrf(login_resp, meta)
    csrf = meta.get("csrf_token", "")
    if csrf:
        headers["X-CSRF-TOKEN"] = csrf

    log.info("Auto-relogin successful, retrying request")
    return http.request(method, path, headers=headers, **kwargs)


def _raw_get(session, url: str) -> dict[str, Any]:
    """Direct GET to an arbitrary URL (e.g. confirmation links)."""
    with session["lock"]:
        cookies, meta = state.load(session)
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
                if not _same_origin(session, target):
                    return {"error": "unsafe_confirmation_redirect", "status": resp.status_code}
                resp = http.get(target)
            if resp.is_redirect:
                return {"error": "too_many_redirects", "status": resp.status_code}
            _extract_csrf(resp, meta)
            state.save(session, http.cookies, meta)
    return {
        "status": resp.status_code,
    }


def _extract_csrf(resp: httpx.Response, meta: dict[str, Any]) -> None:
    """Extract the token supplied by the API or existing account form."""
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


def _parse_response(resp: httpx.Response) -> dict[str, Any]:
    try:
        body = resp.json()
    except ValueError:
        body = None
    if not isinstance(body, dict):
        # Avoid reflecting HTML, cookies, confirmation tokens, or credentials in tool output.
        return {"error": "invalid_response", "status": resp.status_code}
    if not resp.is_success:
        return {**body, "error": body.get("error", "http_error"), "status": resp.status_code}
    return body


def credentials(session, show_password: bool = False) -> dict[str, Any]:
    """Read this installation's private login; secrets require an explicit flag."""
    with session["lock"]:
        credentials = state.load_credentials(session)
    if not credentials:
        return {"error": "no_saved_credentials"}
    result = {"email": credentials["email"], "credentials_saved": True}
    if show_password:
        result["password"] = credentials["password"]
    return result


def resend_confirmation(session, email: str = "", password: str = "") -> dict[str, Any]:
    """Resend activation without replacing the pending account or password."""
    email = email.strip()
    if bool(email) != bool(password):
        return {"error": "missing_credentials", "hint": "Provide both email and password, or omit both."}
    if not email:
        credentials = state.load_credentials(session)
        if not credentials:
            return {"error": "no_saved_credentials"}
        email, password = credentials["email"], credentials["password"]
    return request(session, "POST", "/api/register/resend", json={"email": email, "password": password},
                        _allow_relogin=False)


def login(session, email: str | None = None, password: str | None = None) -> dict[str, Any]:
    email = (email or "").strip()
    password = password or ""
    if bool(email) != bool(password):
        return {"error": "missing_credentials", "hint": "Provide both email and password, or omit both."}
    if not email and not password:
        creds = state.load_credentials(session)
        if creds:
            email, password = creds["email"], creds["password"]
        else:
            return {
                "error": "no_saved_credentials",
                "hint": 'Use asp login --email YOUR_EMAIL --password YOUR_PASSWORD',
            }
    result = request(session, 
        "POST", "/api/login",
        json={"email": email, "password": password},
        _allow_relogin=False,
    )
    if result.get("authenticated"):
        state.save_credentials(session, email, password)
    return result


def logout(session) -> dict[str, Any]:
    result = request(session, "POST", "/api/logout", _clear_csrf=True, _allow_relogin=False)
    if not result.get("error") or result.get("error") == "not_authenticated":
        state.clear(session)
        return {"status": "ok"}
    return result


def register(
    session,
    username: str = "",
    email: str = "",
    password: str = "",
    first_name: str = "",
    last_name: str = "",
    birth_date: str = "",
    phone: str = "",
    country_code: str = "",
    city: str = "",
    address: str = "",
    zip_code: str = "",
    sex: str = "",
) -> dict[str, Any]:
    email = email.strip()
    if not email:
        raise ValueError("Email is required")
    if state.load_credentials(session):
        return {"error": "saved_account_exists", "hint": "Use login, confirm or resend-confirmation for the existing account."}
    status = request(session, "GET", "/api/status", _allow_relogin=False)
    if status.get("error"):
        return status
    if status.get("authenticated"):
        return {"error": "already_authenticated", "hint": "Keep using the signed-in account."}
    username = username.strip() or "player_" + secrets.token_hex(6)
    generated_password = not password
    password = password or "Aa1!" + secrets.token_urlsafe(24)
    body = {
        "username": username,
        "email": email,
        "password": password,
        "acceptTerms": True,
    }
    optional = {
        "firstName": first_name,
        "lastName": last_name,
        "birthDate": birth_date,
        "phone": phone,
        "countryCode": country_code,
        "city": city,
        "address": address,
        "zipCode": zip_code,
        "sex": sex,
    }
    body.update({key: value for key, value in optional.items() if value})
    # Keep the exact credentials if the server accepts the request but its
    # response is lost. Another register command must not replace them.
    with session["lock"]:
        if state.load_credentials(session):
            return {"error": "saved_account_exists", "hint": "Use login, confirm or resend-confirmation for the existing account."}
        state._write_json(session, (session["directory"] / "credentials.json"), {"email": email, "password": password})
    result = request(session, "POST", "/api/register", json=body, _allow_relogin=False)
    if result.get("success"):
        result = {**result, "username": username, "credentials_saved": True, "terms_accepted": True,
                  "password_generated": generated_password,
                  "password_handoff_required": generated_password}
    elif 400 <= result.get("status", 0) < 500:
        # A definite rejection created no account. A timeout or server error
        # is ambiguous, so retain the credentials for confirmation/recovery.
        state.clear_credentials(session)
    return result


def confirm(session, confirmation_url: str) -> dict[str, Any]:
    confirmation_url = urljoin(session["origin"] + "/", confirmation_url)
    parsed = urlparse(confirmation_url)
    if not _same_origin(session, confirmation_url) or not re.fullmatch(r"/emailVerify/[^/]+", parsed.path):
        return {"error": "invalid_confirmation_url", "detail": "Use the emailVerify link from this site's confirmation email."}
    result = _raw_get(session, confirmation_url)
    if result.get("error") or result.get("status", 500) >= 400:
        return {**result, "confirmed": False, "error": result.get("error", "confirmation_failed")}
    status = request(session, "GET", "/api/status")
    return {**result, "confirmed": status.get("authenticated") is True,
            **({"error": "confirmation_failed"} if not status.get("authenticated") else {})}


def predict(
    session,
    coupon_path: str,
    selections: dict[str, str] | str,
    room_index: int = 0,
    stake: str | int | float = "",
    competition_id: str | int | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    idempotency_key = request_key(request_id)
    competition = positive_id(competition_id, "competition_id") if competition_id is not None else None
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
    if session["max_stake"] is not None:
        if not stake_value:
            raise ValueError("An explicit stake is required when ASP_MAX_STAKE is set")
        if amount > session["max_stake"]:
            raise ValueError(f"Stake exceeds ASP_MAX_STAKE ({session['max_stake']})")
    sel = json.loads(selections) if isinstance(selections, str) else selections
    if not isinstance(sel, dict) or not sel:
        raise ValueError("Selections must be a nonempty JSON object")
    for key, value in sel.items():
        if not re.fullmatch(r"\d+(?::\d+)?", str(key)) or not isinstance(value, (str, int, float, bool)):
            raise ValueError("Selections map eventId or eventId:aspectCode to scalar outcome values")
        if isinstance(value, float) and not Decimal(str(value)).is_finite():
            raise ValueError("Selection values must be finite")
    cid = _coupon_id(coupon_path)
    if session["max_stake"] is not None:
        details = request(session, "GET", f"/api/coupons/{cid}")
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
        if not minimum.is_finite() or minimum > session["max_stake"]:
            raise ValueError("Room minimum stake exceeds ASP_MAX_STAKE")
    body: dict[str, Any] = {"selections": sel, "roomIndex": room_index, "request_id": idempotency_key}
    if competition is not None:
        body["competition_id"] = competition
    if stake_value:
        body["stake"] = stake_value
    result = request(session, "POST", f"/api/coupons/{cid}/bet", json=body)
    return {**result, "request_id": idempotency_key}


def _coupon_id(path_or_id: str) -> int:
    """Extract numeric coupon ID from path like '/FOOTBALL/laLiga/18638' or plain '18638'."""
    m = re.fullmatch(r"(?:/(?:[^/?#]+/)*)?(\d+)", str(path_or_id).strip())
    if m:
        return int(m.group(1))
    raise ValueError(f"Cannot extract coupon ID from: {path_or_id}")


def daily_status(session, day: str | None = None) -> dict[str, Any]:
    params = {"day": day_value(day)} if day is not None else None
    return request(session, "GET", "/api/daily", params=params)


def daily_me(session, day: str | None = None) -> dict[str, Any]:
    params = {"day": day_value(day)} if day is not None else None
    return request(session, "GET", "/api/daily/me", params=params)


def daily_claim(session, day: str | None = None, request_id: str | None = None) -> dict[str, Any]:
    key = request_key(request_id)
    body: dict[str, Any] = {"request_id": key}
    if day is not None:
        body["day"] = day_value(day)
    result = request(session, "POST", "/api/daily/claim", json=body)
    return {**result, "request_id": key}


def daily_leaderboard(session, day: str | None = None, scope: str = "daily", page: int = 1) -> dict[str, Any]:
    if scope not in ("daily", "30d"):
        raise ValueError("Leaderboard scope must be daily or 30d")
    if isinstance(page, bool) or not isinstance(page, int) or not 1 <= page <= 100000:
        raise ValueError("Leaderboard page must be between 1 and 100000")
    params: dict[str, Any] = {"scope": scope, "page": page}
    if day is not None:
        params["day"] = day_value(day)
    return request(session, "GET", "/api/daily/leaderboard", params=params)


def update_public_description(session, description: str) -> dict[str, Any]:
    if not isinstance(description, str):
        raise ValueError("Description must be text")
    description = description.strip()
    if len(description) > 500:
        raise ValueError("Public description must be at most 500 characters")
    return request(session, "POST", "/api/account/public-description", json={"description": description})


def predictions(session, active_only: bool = False, competition_id: str | int | None = None,
                day: str | None = None) -> dict[str, Any]:
    params: dict[str, str] = {}
    if active_only:
        params["active"] = "true"
    if competition_id is not None:
        params["competition_id"] = str(positive_id(competition_id, "competition_id"))
    if day is not None:
        params["day"] = day_value(day)
    return request(session, "GET", "/api/bets", params=params or None)


def prediction_history(session, competition_id: str | int | None = None,
                       day: str | None = None) -> dict[str, Any]:
    result = predictions(session, active_only=False, competition_id=competition_id, day=day)
    if "bets" in result:
        settled_daily = {"won", "returned", "lost", "canceled"}
        calculated = [b for b in result["bets"] if (
            b.get("status") in settled_daily if b.get("competition_id") is not None
            else b.get("points") != "-" or b.get("status") == "cancelled"
        )]
        return {"bets": calculated, "count": len(calculated)}
    return result


def wallet_status(session, link_id: str | None = None) -> dict[str, Any]:
    if link_id is not None and (
        not isinstance(link_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,200}", link_id)
    ):
        raise ValueError("link_id contains invalid characters")
    params = {"link_id": link_id} if link_id is not None else None
    return request(session, "GET", "/api/wallet/status", params=params)


def _load_preferences(session, account_id: int) -> dict[str, Any] | None:
    document = state.load_preferences(session, account_id)
    if document is not None:
        if document.get("origin") != session["origin"]:
            raise ValueError("Saved preferences do not match this site")
        document["preferences"] = validate_preferences(document["preferences"])
    return document


def _preferences_account(session) -> tuple[int | None, dict[str, Any] | None]:
    account = request(session, "GET", "/api/account")
    if account.get("error") or account.get("success") is False:
        return None, account
    if account.get("id") is None:
        return None, {"error": "not_authenticated"}
    return positive_id(account["id"], "account id"), None


def preferences_show(session) -> dict[str, Any]:
    account_id, error = _preferences_account(session)
    if error is not None:
        return error
    with session["lock"]:
        document = _load_preferences(session, account_id)
    return {"account_id": account_id, "stored": document is not None,
            "preferences": document.get("preferences", {}) if document else {},
            "updated_at": document.get("updated_at") if document else None,
            "storage": "private_local"}


def preferences_save(session, patch: dict[str, Any]) -> dict[str, Any]:
    patch = validate_preferences(patch)
    account_id, error = _preferences_account(session)
    if error is not None:
        return error
    with session["lock"]:
        current = _load_preferences(session, account_id) or {}
        preferences = current.get("preferences", {}).copy()
        for key, value in patch.items():
            if value is None:
                preferences.pop(key, None)
            else:
                preferences[key] = value
        preferences = validate_preferences(preferences)
        document = {"schema_version": 1, "account_id": account_id, "origin": session["origin"],
                    "updated_at": datetime.now(timezone.utc).isoformat(), "preferences": preferences}
        state.save_preferences(session, account_id, document)
    return {"saved": True, "account_id": account_id, "preferences": preferences,
            "storage": "private_local", "scheduler_changed": False}


def preferences_clear(session) -> dict[str, Any]:
    account_id, error = _preferences_account(session)
    if error is not None:
        return error
    with session["lock"]:
        state.clear_preferences(session, account_id)
    return {"cleared": True, "account_id": account_id, "scheduler_changed": False}
