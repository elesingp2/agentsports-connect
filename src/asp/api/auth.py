"""Authentication: login, logout, register, confirm, auth_status."""

from __future__ import annotations

from typing import Any
import secrets


class AuthMixin:
    """Auth methods mixed into AspClient."""

    def auth_status(self) -> dict[str, Any]:
        return self.request("GET", "/api/status")

    def login(self, email: str | None = None, password: str | None = None) -> dict[str, Any]:
        email = (email or "").strip()
        password = password or ""
        if bool(email) != bool(password):
            return {"error": "missing_credentials", "hint": "Provide both email and password, or omit both."}
        if not email and not password:
            creds = self.state.load_credentials()
            if creds:
                email, password = creds["email"], creds["password"]
            else:
                return {
                    "error": "no_saved_credentials",
                    "hint": 'Pass email and password: login(email="...", password="...")',
                }
        result = self.request(
            "POST", "/api/login",
            json={"email": email, "password": password},
            _allow_relogin=False,
        )
        if result.get("authenticated"):
            self.state.save_credentials(email, password)
        return result

    def logout(self) -> dict[str, Any]:
        result = self.request("POST", "/api/logout", _clear_csrf=True, _allow_relogin=False)
        if not result.get("error") or result.get("error") == "not_authenticated":
            self.state.clear()
            return {"status": "ok"}
        return result

    def register(
        self,
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
        username = username.strip() or "player_" + secrets.token_hex(6)
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
        result = self.request("POST", "/api/register", json=body)
        if result.get("success"):
            self.state.save_credentials(email, password)
            result = {**result, "username": username, "credentials_saved": True, "terms_accepted": True}
        return result

    def confirm(self, confirmation_url: str) -> dict[str, Any]:
        from urllib.parse import urljoin, urlparse
        import re
        confirmation_url = urljoin(self._base_url + "/", confirmation_url)
        parsed = urlparse(confirmation_url)
        if not self._same_origin(confirmation_url) or not re.fullmatch(r"/emailVerify/[^/]+", parsed.path):
            return {"error": "invalid_confirmation_url", "detail": "Use the emailVerify link from this site's confirmation email."}
        result = self._raw_get(confirmation_url)
        if result.get("error") or result.get("status", 500) >= 400:
            return {**result, "confirmed": False, "error": result.get("error", "confirmation_failed")}
        status = self.auth_status()
        return {**result, "confirmed": status.get("authenticated") is True,
                **({"error": "confirmation_failed"} if not status.get("authenticated") else {})}
