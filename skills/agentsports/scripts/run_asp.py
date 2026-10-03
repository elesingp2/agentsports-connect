#!/usr/bin/env python3
"""Launch the pinned GitHub client without relying on global installation or PATH."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

SOURCE = 'git+https://github.com/elesingp2/agentsports-connect.git@v1.1.0'


def main():
    uv = shutil.which('uv')
    if uv:
        return subprocess.call([uv, 'run', '--no-project', '--python', '3.11', '--from', SOURCE, 'asp', *sys.argv[1:]])
    if sys.version_info < (3, 11):
        for name in ('python3.13', 'python3.12', 'python3.11'):
            python = shutil.which(name)
            if python:
                return subprocess.call([python, str(Path(__file__).resolve()), *sys.argv[1:]])
        print(json.dumps({'error': 'python_version', 'hint': 'Install Python 3.11+ or uv, then run this command again.'}), file=sys.stderr)
        return 3
    root = Path(os.environ.get('ASP_TOOL_DIR', '~/.cache/agentsports/v1.1.0')).expanduser()
    python = root / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    marker = root / '.source'
    if not python.exists():
        subprocess.run([sys.executable, '-m', 'venv', str(root)], check=True)
    if not marker.exists() or marker.read_text().strip() != SOURCE:
        # Installation logs go to stderr so command stdout remains machine-readable JSON.
        subprocess.run([str(python), '-m', 'pip', 'install', '--disable-pip-version-check', SOURCE],
                       stdout=sys.stderr, check=True)
        marker.write_text(SOURCE + '\n')
    return subprocess.call([str(python), '-m', 'asp.cli.main', *sys.argv[1:]])


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (subprocess.CalledProcessError, OSError) as exc:
        print(json.dumps({'error': 'client_setup_failed', 'detail': str(exc)}), file=sys.stderr)
        sys.exit(2)
