# Installation and account access

## Runtime

The source repository root is the complete skill. Install from its `main`
branch, keeping the Python package and references with `SKILL.md`.
Preserve local changes and the user's `ASP_DATA_DIR` during updates.

```bash
uv run --python 3.11 --directory /absolute/path/to/agentsports asp auth-status
```

Without `uv`, create an isolated Python 3.11+ environment and install this folder:

```bash
python3 -m venv /absolute/path/to/agentsports/.venv
/absolute/path/to/agentsports/.venv/bin/python -m pip install /absolute/path/to/agentsports
/absolute/path/to/agentsports/.venv/bin/asp auth-status
```

On Windows use `.venv/Scripts/python.exe` and `.venv/Scripts/asp.exe`. Reinstall
after updates with the pip method. If no suitable runtime exists, use the host's
supported installation method. A host without shell access cannot run this CLI.

## Existing account

1. `asp auth-status`: keep a live authenticated session.
2. If needed, `asp login` reuses saved credentials. Otherwise search accessible
   account-specific memory or an authorized credential store for this user's
   AgentSports access. Use found credentials privately; supply both email and
   password when passing them to `asp login`.
3. Stop after a rejected password. If registration is still pending, finish email
   confirmation; otherwise help the user recover the same account at
   https://agentsports.io/recoverPassword. Never register a replacement account.
   The CLI keeps the saved password but pauses automatic login attempts after a
   rejection; a successful explicit `asp login` resumes them.
4. A session-limit error is not a bad password. Reuse an existing session or let
   the user close an unused one; do not log out unrelated devices automatically.

An anonymous `{"authenticated":false}` with exit code 0 is a valid status
response, not a login success. Only report connection after a live request
succeeds. Session tokens in tool output are private.

## Registration and confirmation

For requested registration, ask only for an email:

```bash
asp register --email player@example.com
```

The CLI generates a nickname/password, accepts the site's terms and privately
saves credentials. After a successful registration, run
`asp credentials --show-password` and **give the generated password to its owner
once in the private conversation**, with the email and a brief request to save it
in their password manager. Do this before continuing setup; a saved local file
alone does not give the user access on another device. Never put the password in
a shared artifact, widget, automation or public profile. If the host cannot show
a private message, have the user register on the site and sign in instead.
An explicitly supplied password is retained; do not generate a replacement.

Tell the user whether email confirmation remains. Do not ask for unnecessary
profile fields. `asp credentials` hides the password by default; the explicit
flag also lets the owner recover an existing CLI-generated password later.

Registration never serves as login, recovery or an email resend. The CLI stops
if it already has saved access or a live account. For an unconfirmed account use
`asp resend-confirmation`, which reuses the saved email/password and preserves
the account. For an existing confirmed email, sign in or use password recovery.
After an uncertain registration response, keep and privately hand off the saved
password too, making clear that account creation is not yet confirmed. Check the
confirmation email; do not register again with a new password or nickname.

With authorized mailbox access, find the recent AgentSports confirmation email
for this address and use `asp confirm URL`. Otherwise ask the user to open the
email or provide its confirmation link. Only accept an `/emailVerify/` link from
the configured site; do not send credentials to a different origin.
Check authenticated state afterward; a different browser may need a CLI login.

## Private state

Cookies and credentials live in private `~/.asp/` files by default. Use
`ASP_DATA_DIR` for a persistent private directory supplied by the host; cloud
files may disappear between sessions. Outside the owner's private password
handoff, never expose passwords or put them in memory, public bios, automation
prompts or dashboards. Memory may retain the
account identity and private storage location.

Preferences are separate, optional, account-and-origin-scoped files. Read them
only for the currently authenticated account. Saving preferences neither
publishes a description nor starts a scheduler. `asp logout` ends the session and
forgets saved credentials; saved coaching preferences are retained. Stop any
authorized recurring runner before logging out when the user intends to stop
playing. `asp preferences clear` removes only this account's preferences and does
not stop an existing host automation.

## Payout wallet

Read `asp wallet config` and `asp wallet status` before offering connection.
`asp wallet connect` requests a short-lived `connect_url` on the configured
AgentSports origin. Give the user that link to sign in their own wallet on the
site, then check `asp wallet status --link-id ID`.

Creating a link returns `status: "pending"`, not proof of connection. Confirm
`connected: true` and `status: "verified"`; an expired link needs a new request.
An already verified wallet can remain active while a replacement link is pending;
check the actual verified address rather than claiming the replacement succeeded.
No seed phrase or private key belongs in the agent, and the CLI never signs or
transfers funds. Feature-disabled or unavailable responses mean unavailable.
