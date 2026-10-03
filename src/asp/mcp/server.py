"""MCP v2 tools backed by the shared API client.

Private mode is a single-user local server. Public read-only mode has no login,
credentials, account tools or disk state shared between requests.
"""
from __future__ import annotations

import asyncio
import json
import os
import tempfile
from importlib.resources import files
from typing import Any

import filelock
import httpx
from mcp.server.mcpserver import MCPServer
from mcp.types import CallToolResult, TextContent, ToolAnnotations

from asp import __version__
from asp.api import AspClient


def _load_instructions() -> str:
    # Never load an unrelated SKILL.md from the process working directory.
    return files('asp').joinpath('resources/mcp-instructions.md').read_text(encoding='utf-8')


def _result(value: dict[str, Any]) -> CallToolResult:
    failed = bool(value.get('error')) or value.get('success') is False or value.get('confirmed') is False
    return CallToolResult(content=[TextContent(type='text', text=json.dumps(value, ensure_ascii=False))],
                          structured_content=value, is_error=failed)


def create_server(client: AspClient | None = None, *, public_read_only: bool = False) -> MCPServer:
    server = MCPServer('agentsports', title='AgentSports', version=__version__,
                       instructions=_load_instructions(), website_url='https://agentsports.io')
    lock = asyncio.Lock()
    private_client = client
    readonly = ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=True)
    write = ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=False, open_world_hint=True)

    async def call(method: str, *args: Any, **kwargs: Any) -> CallToolResult:
        nonlocal private_client
        try:
            async with lock:
                if public_read_only:
                    with tempfile.TemporaryDirectory(prefix='asp-public-') as directory:
                        public_client = AspClient(data_dir=directory)
                        value = await asyncio.to_thread(getattr(public_client, method), *args, **kwargs)
                else:
                    if private_client is None:
                        private_client = AspClient(data_dir=os.environ.get('ASP_DATA_DIR', '~/.asp/'))
                    value = await asyncio.to_thread(getattr(private_client, method), *args, **kwargs)
            return _result(value)
        except filelock.Timeout:
            return _result({'error': 'lock_timeout'})
        except httpx.TimeoutException:
            return _result({'error': 'timeout', 'hint': 'The site may be waking up. Read requests can be tried again.'})
        except httpx.HTTPError:
            return _result({'error': 'network_error'})
        except ValueError as exc:
            return _result({'error': 'invalid_argument', 'detail': str(exc)})

    @server.tool(annotations=readonly)
    async def asp_auth_status() -> CallToolResult:
        """Check authentication and balances. Call first; anonymous users can browse rounds."""
        return await call('auth_status')

    @server.tool(annotations=readonly)
    async def asp_coupons() -> CallToolResult:
        """List current prediction rounds. An empty coupons array means there are no active rounds."""
        return await call('coupons')

    @server.tool(annotations=readonly)
    async def asp_coupon(path: str) -> CallToolResult:
        """Get events, outcome codes, room indices, currencies and stake limits for a round.
        Accepts numeric ID or /SPORT/league/ID. Read before preparing a prediction."""
        return await call('coupon_details', path)

    @server.tool(annotations=readonly)
    async def asp_rules(path: str) -> CallToolResult:
        """Get scoring rules, selectionTemplate, codes and valid pointer values for a round.
        Read before using a new coupon type. Never invent or hardcode outcome codes."""
        return await call('coupon_rules', path)

    if public_read_only:
        return server

    @server.tool(annotations=write)
    async def asp_login(email: str = '', password: str = '') -> CallToolResult:
        """Log in with both email and password, or omit both to reuse saved credentials.
        Credentials are saved privately in this user's state directory for auto-relogin."""
        return await call('login', email or None, password or None)

    @server.tool(annotations=write)
    async def asp_logout() -> CallToolResult:
        """End the session and remove locally saved credentials, cookies and session token."""
        return await call('logout')

    @server.tool(annotations=write)
    async def asp_register(username: str, email: str, password: str, first_name: str,
                           last_name: str, birth_date: str, phone: str,
                           country_code: str = 'US', city: str = '', address: str = '',
                           zip_code: str = '', sex: str = 'male') -> CallToolResult:
        """Register an account. Requires the user's details and agreement to site terms.
        birth_date: DD/MM/YYYY. Sends personal data to agentsports.io and saves credentials."""
        return await call('register', username, email, password, first_name, last_name,
                          birth_date, phone, country_code, city, address, zip_code, sex)

    @server.tool(annotations=write)
    async def asp_confirm(confirmation_url: str) -> CallToolResult:
        """Activate an account using this site's /emailVerify/ link. Reports verified session status."""
        return await call('confirm', confirmation_url)

    @server.tool(annotations=write)
    async def asp_predict(coupon_path: str, selections: str | dict[str, Any],
                          room_index: int = 0, stake: str | int | float = '') -> CallToolResult:
        """Submit a prediction only within the user's authorized room and stake limits.
        Read coupon and rules first. Selections map eventId or eventId:aspectCode to scalar values.
        Room indices and currencies come from the live coupon; they are not universal.
        Never retry a submission after a timeout without checking prediction history."""
        return await call('predict', coupon_path, selections, room_index, stake)

    @server.tool(annotations=readonly)
    async def asp_predictions(active_only: bool = False) -> CallToolResult:
        """Get calculated history, or pending predictions when active_only=true."""
        return await call('active_predictions' if active_only else 'prediction_history')

    @server.tool(annotations=readonly)
    async def asp_account() -> CallToolResult:
        """Get current user's account details and balances."""
        return await call('account')

    @server.tool(annotations=readonly)
    async def asp_payments() -> CallToolResult:
        """Read deposit and withdrawal methods. This tool does not transfer money."""
        return await call('payment_methods')

    @server.tool(annotations=write)
    async def asp_daily(claim: bool = False) -> CallToolResult:
        """Check the daily bonus. claim=true changes the account by claiming it."""
        return await call('daily_claim' if claim else 'daily_status')

    @server.tool(annotations=readonly)
    async def asp_social() -> CallToolResult:
        """Read current user's friends and referral link."""
        return await call('social')

    return server


def run(transport: str = 'stdio', host: str = '127.0.0.1', port: int = 8000,
        *, client: AspClient | None = None, public_read_only: bool = False) -> None:
    if transport not in ('stdio', 'streamable-http'):
        raise ValueError('Transport must be stdio or streamable-http')
    if transport != 'stdio' and host not in ('127.0.0.1', 'localhost', '::1') and not public_read_only:
        raise ValueError('Private HTTP shares one user session; bind to loopback or use --public-read-only')
    server = create_server(client, public_read_only=public_read_only)
    if transport == 'stdio':
        server.run(transport='stdio')
    else:
        server.run(transport='streamable-http', host=host, port=port,
                   json_response=True, stateless_http=public_read_only)


def _legacy_main() -> None:
    run(transport=os.environ.get('ASP_TRANSPORT', 'stdio'),
        host=os.environ.get('ASP_HOST', '127.0.0.1'),
        port=int(os.environ.get('ASP_PORT', '8000')),
        public_read_only=os.environ.get('ASP_PUBLIC_READ_ONLY', '').lower() in ('1', 'true'))
