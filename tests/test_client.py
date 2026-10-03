import json
import os
from http.cookiejar import Cookie

import httpx
import pytest

from asp.api import AspClient


@pytest.fixture
def client(tmp_path):
    return AspClient(data_dir=str(tmp_path))


def test_partial_login_does_not_use_another_saved_account(client, monkeypatch):
    client.state.save_credentials('old@example.com', 'old password')
    monkeypatch.setattr(client, 'request', lambda *a, **k: pytest.fail('Must not log in'))
    assert client.login(email='new@example.com')['error'] == 'missing_credentials'


def test_password_whitespace_preserved(client, monkeypatch):
    monkeypatch.setattr(client, 'request', lambda *a, **k: k['json'])
    assert client.login('test@example.com', ' space ')['password'] == ' space '


def test_logout_forgets_credentials_and_session(client, monkeypatch):
    client.state.save_credentials('test@example.com', 'password')
    cookies = httpx.Cookies()
    cookies.set('PLAY_SESSION', 'test', domain='agentsports.io')
    client.state.save(cookies, {'csrf_token': 'secret'})
    monkeypatch.setattr(client, 'request', lambda *a, **k: {'status': 'ok'})
    assert client.logout()['status'] == 'ok'
    assert client.state.load_credentials() is None
    assert len(client.state.load()[0]) == 0
    assert not client.state.load()[1].get('csrf_token')


def test_base_urls_do_not_share_saved_credentials(tmp_path):
    production = AspClient(str(tmp_path), 'https://agentsports.io')
    development = AspClient(str(tmp_path), 'http://localhost:9000')
    production.state.save_credentials('prod@example.com', 'secret')
    assert development.state.load_credentials() is None


def test_cookie_scope_expiry_and_secure_round_trip(client):
    cookies = httpx.Cookies()
    cookies.jar.set_cookie(Cookie(0, 'session', 'secret', None, False,
        'agentsports.io', True, False, '/api', True, True, 2000000000, False,
        None, None, {'HttpOnly': None}, False))
    client.state.save(cookies, {'csrf_token': 'secret'})
    cookie = next(iter(client.state.load()[0].jar))
    assert (cookie.path, cookie.secure, cookie.expires) == ('/api', True, 2000000000)


@pytest.mark.skipif(os.name == 'nt', reason='POSIX permission bits')
def test_session_files_private(client):
    client.state.save_credentials('test@example.com', 'password')
    client.state.save(httpx.Cookies(), {'csrf_token': 'secret'})
    for path in [client.state.cookie_file, client.state.state_file, client.state.credentials_file]:
        assert path.stat().st_mode & 0o777 == 0o600
    assert client.state.dir.stat().st_mode & 0o777 == 0o700


@pytest.mark.parametrize('body', [[], None, 'text', 42])
def test_non_object_json_is_a_useful_error(body):
    result = AspClient._parse_response(httpx.Response(200, json=body))
    assert result['error'] == 'invalid_response'


def test_http_error_json_without_error_field_is_not_success():
    result = AspClient._parse_response(httpx.Response(503, json={'detail': 'Unavailable'}))
    assert result['error'] == 'http_error'
    assert result['status'] == 503


@pytest.mark.parametrize('url', ['https://agentsports.io/', 'http://agentsports.io/authByEmail/x',
    'https://agentsports.io@evil.example/emailVerify/x', '//evil.example/emailVerify/x'])
def test_confirmation_rejects_non_confirmation_or_wrong_origin(client, url, monkeypatch):
    monkeypatch.setattr(client, '_raw_get', lambda *a: pytest.fail('Must not send request'))
    assert client.confirm(url)['error'] == 'invalid_confirmation_url'


def test_failed_confirmation_is_not_reported_as_success(client, monkeypatch):
    # An expired link redirects to the home page with no authenticated session.
    monkeypatch.setattr(client, '_raw_get', lambda *a: {'status': 200})
    monkeypatch.setattr(client, 'auth_status', lambda: {'authenticated': False})
    assert client.confirm('/emailVerify/token')['confirmed'] is False


@pytest.mark.parametrize('stake', ['NaN', 'inf', '-1', '0', 'bad'])
def test_invalid_stakes_never_reach_server(client, stake, monkeypatch):
    monkeypatch.setattr(client, 'request', lambda *a, **k: pytest.fail('Must not send prediction'))
    with pytest.raises(ValueError):
        client.predict('123', {'456': '8'}, stake=stake)


@pytest.mark.parametrize('selections', ['[]', '{}', '{"456": null}', '{"456": {}}'])
def test_invalid_selections_never_reach_server(client, selections, monkeypatch):
    monkeypatch.setattr(client, 'request', lambda *a, **k: pytest.fail('Must not send prediction'))
    with pytest.raises(ValueError):
        client.predict('123', selections, stake=1)


def test_stake_cap_cannot_be_bypassed_by_default_stake(tmp_path, monkeypatch):
    monkeypatch.setenv('ASP_MAX_STAKE', '5')
    client = AspClient(str(tmp_path))
    monkeypatch.setattr(client, 'request', lambda *a, **k: pytest.fail('Must not send prediction'))
    with pytest.raises(ValueError):
        client.predict('123', {'456': '8'})


def test_valid_prediction_payload_preserved(client, monkeypatch):
    monkeypatch.setattr(client, 'request', lambda *a, **k: {'method': a[0], 'path': a[1], **k})
    result = client.predict('/FOOTBALL/league/123', {'456': '8'}, stake='2.5')
    assert result['path'] == '/api/coupons/123/bet'
    assert result['json'] == {'selections': {'456': '8'}, 'roomIndex': 0, 'stake': '2.5'}
