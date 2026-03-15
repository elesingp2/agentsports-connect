"""CLI entrypoint: asp <command> [options]

JSON on stdout, errors on stderr. Exit codes:
  0 — success
  1 — API error (prediction_closed, invalid_credentials, etc.)
  2 — network error / timeout
  3 — invalid arguments
  4 — lock timeout
"""

from __future__ import annotations

import json
import sys
from typing import Any

import click
import filelock
import httpx

from asp.api import AspClient

EXIT_OK = 0
EXIT_API_ERROR = 1
EXIT_NETWORK = 2
EXIT_BAD_ARGS = 3
EXIT_LOCK_TIMEOUT = 4


def _output(data: dict[str, Any]) -> None:
    click.echo(json.dumps(data, ensure_ascii=False, default=str))


def _run(fn, *args: Any, **kwargs: Any) -> None:
    """Execute an API call, handle errors, set exit code."""
    try:
        result = fn(*args, **kwargs)
    except filelock.Timeout:
        click.echo(json.dumps({"error": "lock_timeout"}), err=True)
        sys.exit(EXIT_LOCK_TIMEOUT)
    except httpx.TimeoutException:
        click.echo(json.dumps({"error": "timeout"}), err=True)
        sys.exit(EXIT_NETWORK)
    except httpx.ConnectError:
        click.echo(json.dumps({"error": "connection_failed"}), err=True)
        sys.exit(EXIT_NETWORK)
    except httpx.HTTPError as exc:
        click.echo(json.dumps({"error": "http_error", "detail": str(exc)}), err=True)
        sys.exit(EXIT_NETWORK)
    except ValueError as exc:
        click.echo(json.dumps({"error": "invalid_argument", "detail": str(exc)}), err=True)
        sys.exit(EXIT_BAD_ARGS)

    _output(result)

    if result.get("error"):
        sys.exit(EXIT_API_ERROR)
    sys.exit(EXIT_OK)


@click.group()
@click.option("--data-dir", envvar="ASP_DATA_DIR", default="~/.asp/", help="State directory")
@click.pass_context
def cli(ctx: click.Context, data_dir: str) -> None:
    """agentsports CLI — sports predictions from the command line."""
    ctx.ensure_object(dict)
    ctx.obj["client"] = AspClient(data_dir=data_dir)


# ── Auth ──────────────────────────────────────────────────────────────────

@cli.command("auth-status")
@click.pass_context
def auth_status(ctx: click.Context) -> None:
    """Check session and balances. Call first."""
    _run(ctx.obj["client"].auth_status)


@cli.command("login")
@click.option("--email", default="", help="Account email")
@click.option("--password", default="", help="Account password")
@click.pass_context
def login(ctx: click.Context, email: str, password: str) -> None:
    """Log in. Omit both flags to reuse saved credentials."""
    _run(ctx.obj["client"].login, email or None, password or None)


@cli.command("logout")
@click.pass_context
def logout(ctx: click.Context) -> None:
    """End session."""
    _run(ctx.obj["client"].logout)


@cli.command("register")
@click.option("--username", required=True)
@click.option("--email", required=True)
@click.option("--password", required=True)
@click.option("--first-name", required=True)
@click.option("--last-name", required=True)
@click.option("--birth-date", required=True, help="DD/MM/YYYY")
@click.option("--phone", required=True)
@click.option("--country-code", default="US")
@click.option("--city", default="")
@click.option("--address", default="")
@click.option("--zip-code", default="")
@click.option("--sex", default="male", type=click.Choice(["male", "female"]))
@click.pass_context
def register(ctx: click.Context, **kwargs: Any) -> None:
    """Register a new account."""
    _run(ctx.obj["client"].register, **kwargs)


@cli.command("confirm")
@click.argument("url")
@click.pass_context
def confirm(ctx: click.Context, url: str) -> None:
    """Activate account using the email confirmation link."""
    _run(ctx.obj["client"].confirm, url)


# ── Predictions ───────────────────────────────────────────────────────────

@cli.command("coupons")
@click.pass_context
def coupons(ctx: click.Context) -> None:
    """List available prediction rounds."""
    _run(ctx.obj["client"].coupons)


@cli.command("coupon")
@click.argument("path")
@click.pass_context
def coupon(ctx: click.Context, path: str) -> None:
    """Get round details — events, outcomes, rooms. Accepts path or numeric ID."""
    _run(ctx.obj["client"].coupon_details, path)


@cli.command("predict")
@click.option("--coupon", "coupon_path", required=True, help="Round path or ID")
@click.option("--selections", required=True, help='JSON: {"eventId": "outcomeCode"}')
@click.option("--room", "room_index", type=int, default=0, help="Room index (0=Wooden)")
@click.option("--stake", default="", help="Stake amount")
@click.pass_context
def predict(ctx: click.Context, coupon_path: str, selections: str, room_index: int, stake: str) -> None:
    """Submit a prediction."""
    try:
        json.loads(selections)
    except json.JSONDecodeError as exc:
        click.echo(json.dumps({"error": "invalid_selections_json", "detail": str(exc)}), err=True)
        sys.exit(EXIT_BAD_ARGS)
    _run(ctx.obj["client"].predict, coupon_path, selections, room_index, stake)


# ── Monitoring ────────────────────────────────────────────────────────────

@cli.command("active")
@click.pass_context
def active(ctx: click.Context) -> None:
    """Active (pending) predictions."""
    _run(ctx.obj["client"].active_predictions)


@cli.command("history")
@click.pass_context
def history(ctx: click.Context) -> None:
    """Prediction history."""
    _run(ctx.obj["client"].prediction_history)


# ── Account ───────────────────────────────────────────────────────────────

@cli.command("account")
@click.pass_context
def account(ctx: click.Context) -> None:
    """Account details and balances."""
    _run(ctx.obj["client"].account)


@cli.command("payments")
@click.pass_context
def payments(ctx: click.Context) -> None:
    """Deposit and withdrawal methods."""
    _run(ctx.obj["client"].payment_methods)


@cli.command("social")
@click.pass_context
def social(ctx: click.Context) -> None:
    """Friends list and invite link."""
    _run(ctx.obj["client"].social)


# ── Daily ─────────────────────────────────────────────────────────────────

@cli.group("daily")
def daily() -> None:
    """Daily bonus commands."""


@daily.command("status")
@click.pass_context
def daily_status(ctx: click.Context) -> None:
    """Check daily bonus availability."""
    _run(ctx.obj["client"].daily_status)


@daily.command("claim")
@click.pass_context
def daily_claim(ctx: click.Context) -> None:
    """Claim daily bonus."""
    _run(ctx.obj["client"].daily_claim)


# ── MCP serve ─────────────────────────────────────────────────────────────

@cli.command("mcp-serve")
@click.option("--transport", default="stdio", type=click.Choice(["stdio", "streamable-http"]))
@click.option("--port", default=8000, type=int, help="HTTP port (streamable-http only)")
@click.option("--host", default="127.0.0.1", help="HTTP host (streamable-http only)")
def mcp_serve(transport: str, port: int, host: str) -> None:
    """Start MCP server (stdio or HTTP)."""
    from asp.mcp.server import run
    run(transport=transport, host=host, port=port)


def main() -> None:
    cli(auto_envvar_prefix="ASP")


if __name__ == "__main__":
    main()
