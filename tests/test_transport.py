import json

import httpx
import pytest
from click.testing import CliRunner

from asp.api import AspClient
from asp.cli.main import cli


def mock_http(monkeypatch, handler):
    original = httpx.Client
    monkeypatch.setattr(httpx, 'Client', lambda **kw: original(transport=httpx.MockTransport(handler), **kw))


def test_relogin_updates_token_after_retry_and_retries_only_once(tmp_path, monkeypatch):
    api = AspClient(str(tmp_path))
    api.state.save_credentials('test@example.com', 'password')
    calls = []
    def handler(request):
        calls.append(request)
        if request.url.path == '/api/login':
            return httpx.Response(200, json={'authenticated': True, 'sessionToken': 'token-1'})
        if len(calls) == 1:
            return httpx.Response(401, json={'error': 'not_authenticated'})
        assert request.headers['X-CSRF-TOKEN'] == 'token-1'
        return httpx.Response(200, json={'ok': True, 'sessionToken': 'token-2'})
    mock_http(monkeypatch, handler)
    assert api.account()['ok']
    assert len(calls) == 3
    assert api.state.load()[1]['csrf_token'] == 'token-2'


def test_activation_session_can_write_without_an_extra_login(tmp_path, monkeypatch):
    api = AspClient(str(tmp_path))
    cookies = httpx.Cookies()
    cookies.set('PLAY_SESSION', 'session', domain='agentsports.io')
    api.state.save(cookies, {})
    calls = []
    def handler(request):
        calls.append(request.url.path)
        if request.url.path == '/user/details':
            return httpx.Response(200, text='<div data-request-confirmation="browser-token"></div>',
                headers={'content-type': 'text/html'})
        assert request.headers['X-CSRF-TOKEN'] == 'browser-token'
        return httpx.Response(200, json={'status': 'ok'})
    mock_http(monkeypatch, handler)
    assert api.logout()['status'] == 'ok'
    assert calls == ['/user/details', '/api/logout']


def test_confirmation_cannot_follow_an_external_redirect(tmp_path, monkeypatch):
    calls = []
    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(302, headers={'location': 'https://evil.example/steal'})
    mock_http(monkeypatch, handler)
    result = AspClient(str(tmp_path)).confirm('/emailVerify/token')
    assert result['error'] == 'unsafe_confirmation_redirect'
    assert len(calls) == 1


def test_timeout_on_prediction_is_not_retried(tmp_path, monkeypatch):
    calls = []
    def handler(request):
        calls.append(request)
        raise httpx.ReadTimeout('unknown outcome')
    mock_http(monkeypatch, handler)
    with pytest.raises(httpx.ReadTimeout):
        AspClient(str(tmp_path)).predict('123', {'456': '8'}, stake=1)
    assert len(calls) == 1


def test_cli_returns_nonzero_on_failed_registration(tmp_path, monkeypatch):
    monkeypatch.setattr(AspClient, 'register', lambda *a, **k: {'success': False, 'errors': ['invalid email']})
    result = CliRunner().invoke(cli, ['--data-dir', str(tmp_path), 'register', '--username', 'test',
        '--email', 'test@example.com', '--password', 'password', '--first-name', 'Test', '--last-name', 'User',
        '--birth-date', '01/01/1990', '--phone', '+12025550123'])
    assert result.exit_code == 1
    assert json.loads(result.output)['success'] is False


def test_cli_data_dir_is_used_by_mcp(tmp_path, monkeypatch):
    import asp.mcp.server
    seen = {}
    monkeypatch.setattr(asp.mcp.server, 'run', lambda **kw: seen.update(kw))
    result = CliRunner().invoke(cli, ['--data-dir', str(tmp_path), 'mcp-serve'])
    assert result.exit_code == 0
    assert seen['client'].state.dir == tmp_path


@pytest.mark.parametrize('minimum', ['10', 'NaN'])
def test_backend_minimum_cannot_bypass_stake_cap(tmp_path, monkeypatch, minimum):
    monkeypatch.setenv('ASP_MAX_STAKE', '5')
    api = AspClient(str(tmp_path))
    monkeypatch.setattr(api, 'coupon_details', lambda p: {'rooms': [{'roomIndex': 0, 'minStake': minimum}]})
    monkeypatch.setattr(api, 'request', lambda *a, **k: pytest.fail('Must not submit'))
    with pytest.raises(ValueError):
        api.predict('123', {'456': '8'}, stake=1)


def test_stale_csrf_refreshes_once_before_retrying_write(tmp_path, monkeypatch):
    api = AspClient(str(tmp_path))
    api.state.save(httpx.Cookies(), {'csrf_token': 'old-token'})
    calls = []

    def handler(request):
        calls.append(request.url.path)
        if request.url.path == '/user/details':
            return httpx.Response(200, text='<div data-request-confirmation="new-token"></div>',
                                  headers={'content-type': 'text/html'})
        if len(calls) == 1:
            assert request.headers['X-CSRF-TOKEN'] == 'old-token'
            return httpx.Response(403, json={'error': 'invalid_request_confirmation'})
        assert request.headers['X-CSRF-TOKEN'] == 'new-token'
        return httpx.Response(200, json={'success': True})

    mock_http(monkeypatch, handler)
    assert api.request('POST', '/api/daily/claim', json={})['success']
    assert calls == ['/api/daily/claim', '/user/details', '/api/daily/claim']
    assert api.state.load()[1]['csrf_token'] == 'new-token'


def test_generic_forbidden_write_is_not_retried(tmp_path, monkeypatch):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(403, json={'error': 'account_blocked'})

    mock_http(monkeypatch, handler)
    assert AspClient(str(tmp_path)).request('POST', '/api/daily/claim', json={})['error'] == 'account_blocked'
    assert len(calls) == 1


def test_rejected_saved_password_is_not_retried_on_subsequent_requests(tmp_path, monkeypatch):
    api = AspClient(str(tmp_path))
    api.state.save_credentials('test@example.com', 'old-password')
    calls = []

    def handler(request):
        calls.append(request.url.path)
        if request.url.path == '/api/login':
            return httpx.Response(401, json={'error': 'invalid_credentials'})
        return httpx.Response(401, json={'error': 'not_authenticated'})

    mock_http(monkeypatch, handler)
    assert api.account()['error'] == 'not_authenticated'
    assert api.state.load_credentials() is None
    assert api.account()['error'] == 'not_authenticated'
    assert calls == ['/api/account', '/api/login', '/api/account']
