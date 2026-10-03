import importlib.util
from pathlib import Path
import sys


def launcher():
    path = Path(__file__).parents[1] / 'skills/agentsports/scripts/run_asp.py'
    spec = importlib.util.spec_from_file_location('asp_launcher', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_launcher_uses_tool_run_without_assuming_asp_on_path(monkeypatch):
    module = launcher()
    calls = []
    monkeypatch.setattr(module.shutil, 'which', lambda name: '/bin/uv' if name == 'uv' else None)
    monkeypatch.setattr(module.subprocess, 'call', lambda args: calls.append(args) or 0)
    monkeypatch.setattr(sys, 'argv', ['run_asp.py', 'auth-status'])
    assert module.main() == 0
    assert calls == [['/bin/uv', 'tool', 'run', '--python', '3.11', '--from', module.SOURCE, 'asp', 'auth-status']]


def test_launcher_fallback_reuses_its_isolated_environment(tmp_path, monkeypatch):
    module = launcher()
    (tmp_path / 'bin').mkdir()
    (tmp_path / 'bin/python').touch()
    (tmp_path / '.source').write_text(module.SOURCE)
    calls = []
    monkeypatch.setenv('ASP_TOOL_DIR', str(tmp_path))
    monkeypatch.setattr(module.shutil, 'which', lambda name: None)
    monkeypatch.setattr(module.subprocess, 'run', lambda *a, **k: (_ for _ in ()).throw(AssertionError('Must not reinstall')))
    monkeypatch.setattr(module.subprocess, 'call', lambda args: calls.append(args) or 0)
    monkeypatch.setattr(sys, 'argv', ['run_asp.py', 'coupons'])
    assert module.main() == 0
    assert calls[0][-3:] == ['-m', 'asp.cli.main', 'coupons']
