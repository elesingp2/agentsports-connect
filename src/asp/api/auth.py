"""Authentication: login, logout, register, confirm, auth_status."""

from __future__ import annotations

from typing import Any
import secrets


class AuthMixin:
    """Auth methods mixed into AspClient."""

    def auth_status(self) -> dict[str, Any]:
        return self.request("GET", "/api/status")

    def credentials(self, show_password: bool = False) -> dict[str, Any]:
        """Read this installation's private login; secrets require an explicit flag."""
        with self.state.lock():
            credentials = self.state.load_credentials()
        if not credentials:
            return {"error": "no_saved_credentials"}
        result = {"email": credentials["email"], "credentials_saved": True}
        if show_password:
            result["password"] = credentials["password"]
        return result

    def resend_confirmation(self, email: str = "", password: str = "") -> dict[str, Any]:
        """Resend activation without replacing the pending account or password."""
        email = email.strip()
        if bool(email) != bool(password):
            return {"error": "missing_credentials", "hint": "Provide both email and password, or omit both."}
        if not email:
            credentials = self.state.load_credentials()
            if not credentials:
                return {"error": "no_saved_credentials"}
            email, password = credentials["email"], credentials["password"]
        return self.request("POST", "/api/register/resend", json={"email": email, "password": password},
                            _allow_relogin=False)

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
                    "hint": 'Use asp login --email YOUR_EMAIL --password YOUR_PASSWORD',
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
        if self.state.load_credentials():
            return {"error": "saved_account_exists", "hint": "Use login, confirm or resend-confirmation for the existing account."}
        status = self.request("GET", "/api/status", _allow_relogin=False)
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
        with self.state.lock():
            if self.state.load_credentials():
                return {"error": "saved_account_exists", "hint": "Use login, confirm or resend-confirmation for the existing account."}
            self.state._write_json(self.state.credentials_file, {"email": email, "password": password})
        result = self.request("POST", "/api/register", json=body, _allow_relogin=False)
        if result.get("success"):
            result = {**result, "username": username, "credentials_saved": True, "terms_accepted": True,
                      "password_generated": generated_password,
                      "password_handoff_required": generated_password}
        elif 400 <= result.get("status", 0) < 500:
            # A definite rejection created no account. A timeout or server error
            # is ambiguous, so retain the credentials for confirmation/recovery.
            self.state.clear_credentials()
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
