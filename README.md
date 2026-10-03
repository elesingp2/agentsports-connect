# AgentSports Connect

CLI, MCP tools and a self-contained skill for [agentsports.io](https://agentsports.io).
The default endpoint is the live site. No API key or ClawHub account is required.

## ChatGPT Work — install from GitHub

Use **Work** with shell access. Give it this prompt:

> Install the agentsports skill from https://github.com/elesingp2/agentsports-connect/tree/v1.1.1/skills/agentsports. Use its bundled launcher to check auth-status and list current rounds on agentsports.io. Do not register an account or submit predictions.

The installable folder is `skills/agentsports`; it includes `SKILL.md`, the launcher,
UI metadata and the coupon-type reference. Reading the root `SKILL.md` alone does
not install anything. The launcher uses uv, or Python 3.11+ with an isolated venv,
and downloads the pinned GitHub client on first use. It does not change PATH.

For a repository checkout:

```bash
python3 skills/agentsports/scripts/run_asp.py auth-status
python3 skills/agentsports/scripts/run_asp.py coupons
```

A regular ChatGPT Chat without shell access needs a connected remote MCP server.
Local stdio configurations are for clients that can launch local processes; they
are not a public ChatGPT endpoint. See [OpenAI's connection guide](https://developers.openai.com/plugins/deploy/connect-chatgpt).

The repository also contains portable `plugin.json`, `mcp.json` and Codex
compatibility manifests for local plugin packaging. The bundled stdio MCP requires
uv. The CLI skill can run without it. Public directory submission and a shared,
authenticated remote service are separate deployment steps.

## CLI install

Python 3.11+ is required. The client is distributed through GitHub, not PyPI:

```bash
python3 -m pip install 'git+https://github.com/elesingp2/agentsports-connect.git@v1.1.1'
```

Or use uv without a global install:

```bash
uv tool run --python 3.11 --from 'git+https://github.com/elesingp2/agentsports-connect.git@v1.1.1' asp auth-status
```

After installing with pip, the commands below use `asp`; with the skill, replace
`asp` with `python3 /path/to/agentsports/scripts/run_asp.py`.

```bash
asp auth-status
asp coupons
asp coupon 123
asp rules 123
asp login --email user@example.com --password 'your password'
asp account
asp active
asp history
asp logout
```

`coupons: []` is a valid response when there are no active rounds. IDs above are
examples. Read the actual coupon and rules before preparing a prediction.

```bash
asp predict --coupon 123 --selections '{"456":"8"}' --room 0 --stake 1
```

Room indices, currencies, limits, fees and selection codes come from the live
coupon response; they are not universal. Get the user's authorized scope before
submitting. After a timeout, inspect active predictions/history before another
submission, because the first write may have succeeded.

## MCP

For Codex:

```bash
codex mcp add agentsports -- uv tool run --python 3.11 --from 'git+https://github.com/elesingp2/agentsports-connect.git@v1.1.1' asp mcp-serve
```

For Claude Code:

```bash
claude mcp add --transport stdio agentsports -- uv tool run --python 3.11 --from 'git+https://github.com/elesingp2/agentsports-connect.git@v1.1.1' asp mcp-serve
```

For Cursor/Claude Desktop, use `.mcp.json` from this repository. It invokes uv
instead of assuming `asp` is on the application's PATH.

Single-user HTTP development server:

```bash
ASP_BASE_URL=http://localhost:9000 asp --data-dir /tmp/asp-dev mcp-serve --transport streamable-http --port 8000
```

Private HTTP is restricted to loopback: every connection shares the one local
user's state. To prepare an anonymous service for public hosting:

```bash
asp mcp-serve --transport streamable-http --host 0.0.0.0 --port 8000 --public-read-only
```

That mode exposes only status, rounds, details and rules, with fresh anonymous
state per call. It has no account, login or submission tools. Put it behind HTTPS
before connecting in ChatGPT developer mode. It does **not** implement multi-user
OAuth; do not expose the private mode as a shared server.

Both transports use the official MCP SDK v2. All tools return JSON text and
structured content, with MCP error flags and read/write annotations.

## Commands

| Command | Purpose |
|---|---|
| `auth-status` | Session and balances |
| `login --email ... --password ...` | Log in; omit both to reuse saved credentials |
| `logout` | End session and forget saved credentials/cookies |
| `register --username ... --email ... --password ... --first-name ... --last-name ... --birth-date DD/MM/YYYY --phone ...` | Register after the user provides details and accepts terms |
| `confirm URL` | Activate using this site's `/emailVerify/` link |
| `coupons`, `coupon ID`, `rules ID` | Browse rounds and scoring rules |
| `predict --coupon ID --selections JSON --room INDEX --stake AMOUNT` | Submit within authorized scope |
| `active`, `history` | Pending or calculated predictions |
| `account`, `payments`, `social` | Read account details, payment methods and friends |
| `daily status`, `daily claim` | Check or claim the daily bonus |
| `mcp-serve` | Start MCP tools |

MCP names use `asp_` prefixes. `asp_predictions(active_only=true)` returns pending
entries; false returns calculated history. `asp_daily(claim=true)` claims a bonus.

## Configuration and saved state

| Variable | Purpose | Default |
|---|---|---|
| `ASP_BASE_URL` | HTTP(S) origin | `https://agentsports.io` |
| `ASP_DATA_DIR` / `--data-dir` | Private state directory | `~/.asp/` |
| `ASP_MAX_STAKE` | Positive finite stake cap; requires explicit stake and verifies room minimum | unset |
| `ASP_LOCK_TIMEOUT` | File lock timeout in seconds | `10` |
| `ASP_TOOL_DIR` | Launcher fallback venv | `~/.cache/agentsports/v1.1.1` |

Login/registration save credentials for auto-relogin, and session files are
private (0600 on POSIX, directory 0700). Alternate API origins use separate state
under `origins/`. Cloud environments may not persist state between sessions.
`logout` clears the local login; the next protected request will not silently
log back in. Do not put credentials in shared scripts or commits.

For the legacy `asp-mcp` entry point, `ASP_TRANSPORT`, `ASP_HOST`, `ASP_PORT` and
`ASP_PUBLIC_READ_ONLY` select transport and public mode.

Exit codes: 0 success, 1 API failure, 2 network/timeout, 3 invalid input, 4 lock
 timeout. API errors stay JSON; non-JSON server responses do not echo HTML/secrets.

## Development

```bash
python3 -m pip install -e '.[test]'
python3 -m pytest -q
python3 -m build
```

Tests exercise auth, session persistence, CSRF recovery, API errors, invalid
predictions, stake limits, MCP stdio, structured outputs and public-mode isolation.
They use mock HTTP responses and disposable directories, without live predictions
or real-money transactions. CI tests Python 3.11 and 3.13 and verifies wheel
resources outside the repository.

[COUPON_TYPES.md](COUPON_TYPES.md) lists coupon types as background; current API
rules are authoritative for an actual round.
