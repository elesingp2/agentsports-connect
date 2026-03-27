"""Authentication: login, logout, register, confirm, auth_status."""

from __future__ import annotations

from typing import Any


class AuthMixin:
    """Auth methods mixed into AspClient."""

    def auth_status(self) -> dict[str, Any]:
        return self.request("GET", "/api/status")

    def login(self, email: str | None = None, password: str | None = None) -> dict[str, Any]:
        email = (email or "").strip()
        password = (password or "").strip()
        if not email or not password:
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
        result = self.request("POST", "/api/logout", _clear_csrf=True)
        return result

    def register(
        self,
        username: str,
        email: str,
        password: str,
        first_name: str,
        last_name: str,
        birth_date: str,
        phone: str,
        country_code: str = "US",
        city: str = "",
        address: str = "",
        zip_code: str = "",
        sex: str = "male",
    ) -> dict[str, Any]:
        result = self.request("POST", "/api/register", json={
            "username": username,
            "email": email,
            "password": password,
            "firstName": first_name,
            "lastName": last_name,
            "birthDate": birth_date,
            "phone": phone,
            "countryCode": country_code,
            "city": city or "-",
            "address": address or "-",
            "zipCode": zip_code or "00000",
            "sex": sex,
            "acceptTerms": True,
        })
        if result.get("success"):
            self.state.save_credentials(email, password)
        return result

    def confirm(self, confirmation_url: str) -> dict[str, Any]:
        if not confirmation_url.startswith("http"):
            confirmation_url = f"{self._base_url}{confirmation_url}"
        from urllib.parse import urlparse
        allowed = urlparse(self._base_url).netloc
        actual = urlparse(confirmation_url).netloc
        if actual != allowed:
            return {"error": "invalid_confirmation_url", "detail": f"URL must belong to {allowed}"}
        return self._raw_get(confirmation_url)
