"""MCP server — thin wrappers delegating to AspClient.

All business logic lives in asp.api. This module only defines MCP tool
handlers, JSON serialization, and transport setup.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from asp.api import AspClient


def _load_instructions() -> str:
    for candidate in [
        Path(__file__).resolve().parent.parent.parent.parent / "SKILL.md",
        Path.cwd() / "SKILL.md",
    ]:
        if candidate.exists():
            text = candidate.read_text(encoding="utf-8")
            if text.startswith("---"):
                end = text.find("---", 3)
                if end != -1:
                    text = text[end + 3:].lstrip("\n")
            return text
    return ""


mcp = FastMCP("agentsports", instructions=_load_instructions())

_client = AspClient()
_lock = asyncio.Lock()


def _j(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


async def _call(fn, *args: Any, **kwargs: Any) -> str:
    """Run a sync AspClient method under asyncio lock."""
    async with _lock:
        result = await asyncio.to_thread(fn, *args, **kwargs)
    return _j(result)


# ── Auth ──────────────────────────────────────────────────────────────────

@mcp.tool()
async def asp_register(
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
) -> str:
    """Register a new account. birth_date: DD/MM/YYYY, country_code: ISO 2-letter.
    Password: min 8 chars, upper/lower/numbers. New accounts get 100 free ASP tokens.
    After success, user must confirm email. Credentials auto-saved to ~/.asp/.
    IMPORTANT: Personal data is sent to agentsports.io. Get explicit user consent before calling."""
    async with _lock:
        result = await asyncio.to_thread(
            _client.register, username, email, password, first_name, last_name,
            birth_date, phone, country_code, city, address, zip_code,
        )
    return _j(result)


@mcp.tool()
async def asp_confirm(confirmation_url: str) -> str:
    """Activate account using the email confirmation link."""
    return await _call(_client.confirm, confirmation_url)


@mcp.tool()
async def asp_login(email: str = "", password: str = "") -> str:
    """Log in. ALWAYS pass email+password when user provides them.
    Omit both to reuse saved credentials. If 'player_already_logged_in' → asp_logout() first."""
    async with _lock:
        result = await asyncio.to_thread(_client.login, email or None, password or None)
    return _j(result)


@mcp.tool()
async def asp_logout() -> str:
    """End session."""
    return await _call(_client.logout)


@mcp.tool()
async def asp_auth_status() -> str:
    """Check session + balances. Call first — if authenticated, no login needed."""
    return await _call(_client.auth_status)


# ── Predictions ───────────────────────────────────────────────────────────

@mcp.tool()
async def asp_coupons() -> str:
    """List available prediction rounds: {coupons: [{id, path, sport, league, status, eventsCount, startTime}]}.
    Use id or path in asp_coupon."""
    return await _call(_client.coupons)


@mcp.tool()
async def asp_coupon(path: str) -> str:
    """Get round events, outcomes, rooms and stakes. ALWAYS call before submitting a prediction.
    Accepts path ('/FOOTBALL/laLiga/18638') or numeric ID ('18638')."""
    return await _call(_client.coupon_details, path)


@mcp.tool()
async def asp_predict(
    coupon_path: str,
    selections: str | dict,
    room_index: int = 0,
    stake: str | int | float = "",
) -> str:
    """Submit a prediction. selections: {"eventId": "outcomeCode"} (1X2: "8"=home, "9"=draw, "10"=away).
    room_index: 0=Wooden(ASP) 1=Bronze(EUR) 2=Silver 3=Golden. stake: amount or empty for default.
    IMPORTANT: For real-money rooms (1-3), always confirm with the user before calling."""
    async with _lock:
        result = await asyncio.to_thread(
            _client.predict, coupon_path, selections, room_index, stake,
        )
    return _j(result)


# ── Monitoring ────────────────────────────────────────────────────────────

@mcp.tool()
async def asp_predictions(active_only: bool = False) -> str:
    """Get prediction history. active_only=true for pending predictions only.
    Each entry has: id, sport, room, stake, points (accuracy 0-100), winning, status, selections."""
    return await _call(_client.predictions, active_only=active_only)


@mcp.tool()
async def asp_account() -> str:
    """Account details: name, email, balances, registration date."""
    return await _call(_client.account)


@mcp.tool()
async def asp_payments() -> str:
    """Deposit and withdrawal methods with fees and limits."""
    return await _call(_client.payment_methods)


# ── Daily & Social ────────────────────────────────────────────────────────

@mcp.tool()
async def asp_daily(claim: bool = False) -> str:
    """Daily bonus. claim=false → check status (available, amount, countdown).
    claim=true → claim bonus. Check status first to see if available."""
    if claim:
        return await _call(_client.daily_claim)
    return await _call(_client.daily_status)


@mcp.tool()
async def asp_social() -> str:
    """Friends list, invite link for referral bonuses."""
    return await _call(_client.social)


def run(transport: str = "stdio", host: str = "127.0.0.1", port: int = 8000) -> None:
    """Start the MCP server with given transport."""
    if transport != "stdio":
        mcp.settings.host = host
        mcp.settings.port = port
    mcp.run(transport=transport)


def _legacy_main() -> None:
    """Entry point for backward-compatible `asp-mcp` command."""
    transport = os.environ.get("ASP_TRANSPORT", "stdio")
    host = os.environ.get("ASP_HOST", "127.0.0.1")
    port = int(os.environ.get("ASP_PORT", "8000"))
    run(transport=transport, host=host, port=port)
