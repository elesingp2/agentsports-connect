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
from asp.api.validation import request_key

EXIT_OK = 0
EXIT_API_ERROR = 1
EXIT_NETWORK = 2
EXIT_BAD_ARGS = 3
EXIT_LOCK_TIMEOUT = 4


def _output(data: dict[str, Any]) -> None:
    click.echo(json.dumps(data, ensure_ascii=False, default=str))


def _run(fn, *args: Any, **kwargs: Any) -> None:
    """Execute an API call, handle errors, set exit code."""
    # A caller can reuse this key after an ambiguous network failure instead of
    # accidentally starting a second logical Daily action.
    action = {"request_id": kwargs["request_id"]} if kwargs.get("request_id") else {}
    try:
        result = fn(*args, **kwargs)
    except filelock.Timeout:
        click.echo(json.dumps({"error": "lock_timeout", **action}), err=True)
        sys.exit(EXIT_LOCK_TIMEOUT)
    except httpx.TimeoutException:
        click.echo(json.dumps({"error": "timeout", **action}), err=True)
        sys.exit(EXIT_NETWORK)
    except httpx.ConnectError:
        click.echo(json.dumps({"error": "connection_failed", **action}), err=True)
        sys.exit(EXIT_NETWORK)
    except httpx.HTTPError as exc:
        click.echo(json.dumps({"error": "http_error", "detail": str(exc), **action}), err=True)
        sys.exit(EXIT_NETWORK)
    except ValueError as exc:
        click.echo(json.dumps({"error": "invalid_argument", "detail": str(exc), **action}), err=True)
        sys.exit(EXIT_BAD_ARGS)

    _output(result)

    if result.get("error") or result.get("success") is False:
        sys.exit(EXIT_API_ERROR)
    sys.exit(EXIT_OK)


class JsonGroup(click.Group):
    def main(self, *args: Any, **kwargs: Any) -> Any:
        kwargs["standalone_mode"] = False
        try:
            return super().main(*args, **kwargs)
        except (click.UsageError, ValueError) as exc:
            click.echo(json.dumps({"error": "invalid_argument", "detail": str(exc)}), err=True)
            sys.exit(EXIT_BAD_ARGS)


@click.group(cls=JsonGroup)
@click.version_option(version="3.0.1")
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
@click.option("--username", default="", help="Generated automatically when omitted")
@click.option("--email", required=True)
@click.option("--password", default="", help="Generated securely and saved privately when omitted")
@click.option("--first-name", default="")
@click.option("--last-name", default="")
@click.option("--birth-date", default="", help="Optional: DD/MM/YYYY")
@click.option("--phone", default="")
@click.option("--country-code", default="")
@click.option("--city", default="")
@click.option("--address", default="")
@click.option("--zip-code", default="")
@click.option("--sex", default="", type=click.Choice(["", "male", "female"]))
@click.pass_context
def register(ctx: click.Context, **kwargs: Any) -> None:
    """Register with email only; generate credentials and accept site terms."""
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
    """Get round details — events, outcomes, rooms, scoring rules. Accepts path or numeric ID."""
    _run(ctx.obj["client"].coupon_details, path)


@cli.command("rules")
@click.argument("path")
@click.pass_context
def rules(ctx: click.Context, path: str) -> None:
    """Get scoring rules for a prediction round. Shows the accuracy scoring matrix."""
    _run(ctx.obj["client"].coupon_rules, path)


@cli.command("predict")
@click.option("--coupon", "coupon_path", required=True, help="Round path or ID")
@click.option("--selections", required=True, help='JSON: {"eventId":"outcomeCode"} or {"eventId:aspectCode":"value"}; see asp rules ID')
@click.option("--room", "room_index", type=int, default=0, help="roomIndex from asp coupon ID")
@click.option("--stake", default="", help="Stake amount")
@click.option("--competition", "competition_id", type=click.IntRange(min=1), help="Daily competition ID")
@click.option("--request-id", default=None, help="Reuse the same key when retrying one Daily entry")
@click.pass_context
def predict(ctx: click.Context, coupon_path: str, selections: str, room_index: int, stake: str,
            competition_id: int | None, request_id: str | None) -> None:
    """Submit a prediction."""
    try:
        json.loads(selections)
    except json.JSONDecodeError as exc:
        click.echo(json.dumps({"error": "invalid_selections_json", "detail": str(exc)}), err=True)
        sys.exit(EXIT_BAD_ARGS)
    _run(ctx.obj["client"].predict, coupon_path, selections, room_index, stake,
         competition_id=competition_id, request_id=request_key(request_id))


# ── Monitoring ────────────────────────────────────────────────────────────

@cli.command("pool-csv")
@click.argument("path")
@click.option("--output", required=True, type=click.Path(dir_okay=False), help="New CSV file; existing files are never overwritten")
@click.pass_context
def pool_csv(ctx: click.Context, path: str, output: str) -> None:
    """Save all predictions in a round as CSV. Returns file metadata, not rows."""
    _run(ctx.obj["client"].pool_csv, path, output)


@cli.command("active")
@click.option("--competition", "competition_id", type=click.IntRange(min=1))
@click.option("--day", help="Filter by UTC day: YYYY-MM-DD")
@click.pass_context
def active(ctx: click.Context, competition_id: int | None, day: str | None) -> None:
    """Active (pending) predictions."""
    _run(ctx.obj["client"].active_predictions, competition_id=competition_id, day=day)


@cli.command("history")
@click.option("--competition", "competition_id", type=click.IntRange(min=1))
@click.option("--day", help="Filter by UTC day: YYYY-MM-DD")
@click.pass_context
def history(ctx: click.Context, competition_id: int | None, day: str | None) -> None:
    """Prediction history — scored or cancelled entries. Use 'asp active' for pending."""
    _run(ctx.obj["client"].prediction_history, competition_id=competition_id, day=day)


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
    """Daily competitions, balances, history and rankings."""


@daily.command("status")
@click.option("--day", help="UTC day: YYYY-MM-DD; current day by default")
@click.option("--me", is_flag=True, help="Read this account's day balance and entries")
@click.pass_context
def daily_status(ctx: click.Context, day: str | None, me: bool) -> None:
    """Check availability and real day state; this does not join."""
    _run(ctx.obj["client"].daily_me if me else ctx.obj["client"].daily_status, day=day)


@daily.command("me")
@click.option("--day", help="UTC day: YYYY-MM-DD")
@click.pass_context
def daily_me(ctx: click.Context, day: str | None) -> None:
    """Read this account's day balance, rank and entries."""
    _run(ctx.obj["client"].daily_me, day=day)


@daily.command("history")
@click.option("--day", required=True, help="UTC day: YYYY-MM-DD")
@click.pass_context
def daily_history(ctx: click.Context, day: str) -> None:
    """Read a day's full snapshot, including still-pending entries."""
    _run(ctx.obj["client"].daily_history, day=day)


@daily.command("join")
@click.option("--day", help="UTC day: YYYY-MM-DD; current day by default")
@click.option("--request-id", default=None, help="Reuse this key to retry the same join")
@click.pass_context
def daily_join(ctx: click.Context, day: str | None, request_id: str | None) -> None:
    """Join and receive the day's starting ASP once, when authorized."""
    _run(ctx.obj["client"].daily_join, day=day, request_id=request_key(request_id))


@daily.command("claim")
@click.option("--day", help="UTC day: YYYY-MM-DD")
@click.option("--request-id", default=None)
@click.pass_context
def daily_claim(ctx: click.Context, day: str | None, request_id: str | None) -> None:
    """Alias of Daily join; never issues an additional bonus."""
    _run(ctx.obj["client"].daily_claim, day=day, request_id=request_key(request_id))


@daily.command("leaderboard")
@click.option("--day", help="UTC day: YYYY-MM-DD")
@click.option("--scope", type=click.Choice(["daily", "30d"]), default="daily", show_default=True)
@click.option("--page", type=click.IntRange(1, 100000), default=1, show_default=True)
@click.pass_context
def daily_leaderboard(ctx: click.Context, day: str | None, scope: str, page: int) -> None:
    """Read public standings and user descriptions."""
    _run(ctx.obj["client"].daily_leaderboard, day=day, scope=scope, page=page)


@cli.group("profile")
def profile() -> None:
    """The ordinary user's public description; private coaching stays local."""


@profile.command("description")
@click.argument("text")
@click.pass_context
def profile_description(ctx: click.Context, text: str) -> None:
    """Publish TEXT (up to 500 characters); pass empty text to clear."""
    _run(ctx.obj["client"].update_public_description, text)


@cli.group("wallet")
def wallet() -> None:
    """Human-signed payout-wallet connection; no transfers or private keys."""


@wallet.command("config")
@click.pass_context
def wallet_config(ctx: click.Context) -> None:
    """Read supported network and feature availability."""
    _run(ctx.obj["client"].wallet_config)


@wallet.command("connect")
@click.pass_context
def wallet_connect(ctx: click.Context) -> None:
    """Request a site link for the user to sign in their own wallet."""
    _run(ctx.obj["client"].wallet_connect)


@wallet.command("status")
@click.option("--link-id", help="Optional pending connection ID")
@click.pass_context
def wallet_status(ctx: click.Context, link_id: str | None) -> None:
    """Check actual connection status; creating a link is not verification."""
    _run(ctx.obj["client"].wallet_status, link_id=link_id)


@cli.group("preferences")
def preferences() -> None:
    """Optional private coaching settings; these commands never change a host scheduler."""


@preferences.command("show")
@click.pass_context
def preferences_show(ctx: click.Context) -> None:
    """Read preferences only for the currently authenticated account."""
    _run(ctx.obj["client"].preferences_show)


@preferences.command("save")
@click.option("--json", "json_text", required=True, help="JSON object to merge; null removes a field")
@click.pass_context
def preferences_save(ctx: click.Context, json_text: str) -> None:
    """Save agreed private settings locally; never publishes a description."""
    _run(ctx.obj["client"].preferences_save, json.loads(json_text))


@preferences.command("clear")
@click.pass_context
def preferences_clear(ctx: click.Context) -> None:
    """Remove this account's local preferences; does not stop existing schedules."""
    _run(ctx.obj["client"].preferences_clear)


def main() -> None:
    cli(auto_envvar_prefix="ASP")


if __name__ == "__main__":
    main()
