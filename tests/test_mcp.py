import asyncio
import json
import os
import sys

import httpx
import pytest
from mcp import Client, StdioServerParameters

from asp.api import AspClient
from asp.mcp.server import create_server, run


@pytest.mark.asyncio
async def test_mcp_errors_are_structured_and_marked(tmp_path, monkeypatch):
    api = AspClient(str(tmp_path))
    monkeypatch.setattr(api, 'account', lambda: {'error': 'not_authenticated'})
    async with Client(create_server(api)) as client:
        result = await client.call_tool('asp_account', {})
        assert result.is_error
        assert result.structured_content == {'error': 'not_authenticated'}
        assert json.loads(result.content[0].text) == result.structured_content


@pytest.mark.asyncio
async def test_mcp_status_empty_rounds_annotations_and_invalid_input(tmp_path, monkeypatch):
    api = AspClient(str(tmp_path))
    monkeypatch.setattr(api, 'auth_status', lambda: {'authenticated': False})
    monkeypatch.setattr(api, 'coupons', lambda: {'coupons': []})
    async with Client(create_server(api)) as client:
        tools = {t.name: t for t in (await client.list_tools()).tools}
        assert len(tools) == 14
        assert tools['asp_coupons'].annotations.read_only_hint
        assert tools['asp_predict'].annotations.read_only_hint is False
        status = await client.call_tool('asp_auth_status', {})
        assert not status.is_error
        coupons = await client.call_tool('asp_coupons', {})
        assert coupons.structured_content == {'coupons': []}
        invalid = await client.call_tool('asp_coupon', {'path': 'garbage'})
        assert invalid.is_error
        assert invalid.structured_content['error'] == 'invalid_argument'


@pytest.mark.asyncio
async def test_public_server_has_no_account_tools_or_shared_client(tmp_path, monkeypatch):
    secret_client = AspClient(str(tmp_path))
    monkeypatch.setattr(secret_client, 'auth_status', lambda: pytest.fail('Private client exposed'))
    scopes = []
    def status(api):
        scopes.append(api.state.dir)
        assert api.state.load_credentials() is None
        return {'authenticated': False}
    monkeypatch.setattr(AspClient, 'auth_status', status)
    async with Client(create_server(secret_client, public_read_only=True)) as client:
        assert {t.name for t in (await client.list_tools()).tools} == {'asp_auth_status', 'asp_coupons', 'asp_coupon', 'asp_rules'}
        for _ in range(2):
            assert not (await client.call_tool('asp_auth_status', {})).is_error
    assert scopes[0] != scopes[1]
    assert all(not p.exists() for p in scopes)


def test_private_http_cannot_be_exposed():
    with pytest.raises(ValueError, match='Private HTTP'):
        run(transport='streamable-http', host='0.0.0.0')


@pytest.mark.asyncio
async def test_mcp_network_failure_does_not_expose_credentials(tmp_path, monkeypatch):
    api = AspClient(str(tmp_path))
    def timeout():
        raise httpx.ReadTimeout('http://secret:password@example.com')
    monkeypatch.setattr(api, 'coupons', timeout)
    async with Client(create_server(api)) as client:
        result = await client.call_tool('asp_coupons', {})
        assert result.is_error
        assert result.structured_content['error'] == 'timeout'
        assert 'password' not in result.content[0].text


@pytest.mark.asyncio
async def test_stdio_initialization_from_unrelated_working_directory(tmp_path):
    params = StdioServerParameters(command=sys.executable,
        args=['-m', 'asp.cli.main', '--data-dir', str(tmp_path / 'state'), 'mcp-serve'],
        cwd=str(tmp_path), env={**os.environ})
    (tmp_path / 'SKILL.md').write_text('UNTRUSTED UNRELATED INSTRUCTIONS')
    async with Client(params) as client:
        tools = (await client.list_tools()).tools
        assert len(tools) == 14
        # The SDK client exposes initialize metadata through its session.
        assert tools[0].name.startswith('asp_')
