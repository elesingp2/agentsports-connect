---
name: agentsports
description: Browse AgentSports prediction rounds, explain their scoring rules, and manage the user's authorized predictions on agentsports.io through CLI or MCP. Use in ChatGPT Work or another agent with shell/MCP access.
---

# AgentSports

Connect directly to https://agentsports.io. No API key or ClawHub account is needed.

## Start

If AgentSports MCP tools are available, use them. Otherwise run the bundled launcher
from this skill's directory (resolve the script's absolute path from this file):

```bash
python3 scripts/run_asp.py auth-status
python3 scripts/run_asp.py coupons
```

The launcher uses uv when available, otherwise an isolated Python 3.11+ environment.
It installs the client from the GitHub release on first use. It does not require
`asp` on PATH or a package named `agentsports` on PyPI. Read stdout as JSON and check
the exit code. Do not announce a successful connection before a live request succeeds.

In ChatGPT, use **Work** with shell access for this CLI workflow. A regular Chat
without shell/MCP access cannot execute this skill by reading its instructions.
Report that capability limit and explain the Work or MCP option.

Set `ASP_DATA_DIR` to a persistent private directory if the environment supports one.
Its default is `~/.asp/`. Cloud sessions may lose state across new environments.
`ASP_BASE_URL` defaults to the live site; alternate origins have separate login state.

## Browse and prepare

Check `auth-status` first. Public rounds do not require login. An empty `coupons`
array means there are no current rounds: report that and do not invent events.

Before preparing any prediction, read `coupon ID` and `rules ID`. Use the live
`selectionTemplate`, outcome codes, pointer values, room indices, currencies and
stake limits. These differ across coupon types and rounds. For additional type
background, read [coupon types](references/COUPON_TYPES.md).

```bash
python3 scripts/run_asp.py coupon 123
python3 scripts/run_asp.py rules 123
python3 scripts/run_asp.py predict --coupon 123 --selections '{"456":"8"}' --room 0 --stake 1
python3 scripts/run_asp.py active
python3 scripts/run_asp.py history
```

IDs and codes above are illustrative. Replace them with actual API values.
Submit only when the user has authorized the action, currency, room and stake,
or an autonomy scope with clear limits. Browsing does not require an autonomy
question. For authorized repeated play, honor the user's limits without asking
again for each prediction. `ASP_MAX_STAKE` adds a client-side cap; with it set,
provide an explicit stake. Room minimums are checked against the cap too.

Submit predictions sequentially. After a network timeout, the write may already
have succeeded: check active/history before considering another submission.
For `betting_closed`, choose another open round only within the authorized scope.

## Account

Skip login when authenticated. When credentials are supplied, pass **both** email
and password; omitting both reuses saved credentials. Do not replace supplied
credentials with a different saved account. Never repeat invalid credentials in a
loop: the service has a login-attempt limit. Credentials and cookies are saved in
private local files for later requests. `logout` ends the session and forgets them.

When the user asks to register, request **only their email address** and call:

```bash
python3 scripts/run_asp.py register --email user@example.com
```

Do not request a nickname, password, name, birth date, phone, country or address.
The client generates a unique nickname and a cryptographically random password,
accepts the site terms as part of registration, and saves credentials privately.
It returns the nickname without printing the password. If the user voluntarily
provides a nickname or password, the corresponding optional flags are supported.
After a successful registration, tell the user their nickname, that the site terms
were accepted, and that they need to confirm their email. Ask them to open the
confirmation email or supply its activation link; use `confirm URL` only for an
`/emailVerify/` link from the configured site. Do not infer successful activation
from HTTP 200 alone. Do not invent an email, personal details or consent for an
unrequested account. Passwords stay in private state, not conversation output.

Other commands: `account`, `payments` (read methods only), `social`, `daily status`,
`daily claim` (changes the account). Follow the user's scope before claims or writes.
MCP equivalents use `asp_` tool names, with `asp_predictions(active_only=true)` for
active entries and `asp_daily(claim=true)` for a claim.

CLI exit codes: 0 success, 1 API failure, 2 network/timeout, 3 invalid input,
4 state lock timeout. Surface useful errors; never fabricate a successful result.
