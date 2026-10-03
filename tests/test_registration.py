import json

import pytest
from click.testing import CliRunner
from mcp import Client

from asp.api import AspClient
from asp.cli.main import cli
from asp.mcp.server import create_server


def test_email_only_registration_generates_private_credentials(tmp_path, monkeypatch):
    api = AspClient(str(tmp_path))
    bodies = []
    def request(method, path, **kwargs):
        bodies.append(kwargs['json'])
        assert (method, path) == ('POST', '/api/register')
        return {'success': True, 'needs_email_confirmation': True}
    monkeypatch.setattr(api, 'request', request)
    first = api.register(email=' player@example.com ')
    second = api.register(email='another@example.com')
    assert bodies[0].keys() == {'username', 'email', 'password', 'acceptTerms'}
    assert bodies[0]['email'] == 'player@example.com'
    assert bodies[0]['acceptTerms'] is True
    assert first['username'].startswith('player_') and len(first['username']) <= 20
    assert first['username'] != second['username']
    assert 32 <= len(bodies[0]['password']) <= 50
    assert bodies[0]['password'] != bodies[1]['password']
    assert bodies[0]['password'] not in json.dumps(first)
    assert second['terms_accepted'] is True and second['credentials_saved'] is True
    assert api.state.load_credentials() == {'email': 'another@example.com', 'password': bodies[1]['password']}


def test_registration_preserves_supplied_values_without_fake_profile(tmp_path, monkeypatch):
    api = AspClient(str(tmp_path))
    bodies = []
    monkeypatch.setattr(api, 'request', lambda *a, **k: bodies.append(k['json']) or {'success': True})
    api.register(username='my_name', email='player@example.com', password=' exact password ', first_name='Test')
    assert bodies[0]['username'] == 'my_name'
    assert bodies[0]['password'] == ' exact password '
    assert bodies[0]['firstName'] == 'Test'
    assert 'phone' not in bodies[0] and 'countryCode' not in bodies[0] and 'sex' not in bodies[0]


def test_failed_registration_does_not_replace_existing_credentials(tmp_path, monkeypatch):
    api = AspClient(str(tmp_path))
    api.state.save_credentials('old@example.com', 'old password')
    monkeypatch.setattr(api, 'request', lambda *a, **k: {'success': False, 'errors': ['Email already registered']})
    result = api.register(email='old@example.com')
    assert result['success'] is False
    assert api.state.load_credentials()['password'] == 'old password'


def test_registration_needs_email_before_any_request(tmp_path, monkeypatch):
    api = AspClient(str(tmp_path))
    monkeypatch.setattr(api, 'request', lambda *a, **k: pytest.fail('No email supplied'))
    with pytest.raises(ValueError, match='Email is required'):
        api.register(email=' ')


def test_cli_registration_requires_only_email(tmp_path, monkeypatch):
    bodies = []
    monkeypatch.setattr(AspClient, 'request', lambda *a, **k: bodies.append(k['json']) or {'success': True})
    result = CliRunner().invoke(cli, ['--data-dir', str(tmp_path), 'register', '--email', 'player@example.com'])
    assert result.exit_code == 0
    assert json.loads(result.output)['username'] == bodies[0]['username']
    assert bodies[0]['password'] not in result.output


@pytest.mark.asyncio
async def test_mcp_registration_requires_only_email(tmp_path, monkeypatch):
    api = AspClient(str(tmp_path))
    bodies = []
    monkeypatch.setattr(api, 'request', lambda *a, **k: bodies.append(k['json']) or {'success': True})
    async with Client(create_server(api)) as mcp:
        tool = next(t for t in (await mcp.list_tools()).tools if t.name == 'asp_register')
        assert tool.input_schema['required'] == ['email']
        result = await mcp.call_tool('asp_register', {'email': 'player@example.com'})
        assert not result.is_error
        assert result.structured_content['credentials_saved'] is True
        assert bodies[0]['password'] not in result.content[0].text
