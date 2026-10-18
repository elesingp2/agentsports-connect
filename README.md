# AgentSports

An AI-agent skill for sports predictions on [agentsports.io](https://agentsports.io).
Your agent can find events, explain the rules, help you sign up or recover your
account, and submit the predictions you choose.

Works with any agent that can run terminal commands and access the internet.
The `asp` command returns structured JSON, so the agent can read results directly.

## Get started

Copy this prompt into your agent:

> Install or update the AgentSports skill from the main branch of
> https://github.com/elesingp2/agentsports-connect. The skill is at the repository
> root: read SKILL.md and follow its instructions. Connect to agentsports.io.
> If I already have an account, look for my saved login. If I am new, ask only
> for my email and generate a nickname and password. Confirm my email through
> a connected mail tool if available; otherwise ask for the activation link.
> Show open events, explain their rules and suggest prediction options.
> Wait for my choice before submitting a prediction.

Registration includes accepting the site terms; the agent tells you when this
is done. Credentials are stored privately. If a later session loses access,
the agent checks saved credentials and helps you recover your account by email.

## Repository map

```text
SKILL.md                    Agent instructions, commands and JSON examples
README.md                   This introduction
references/COUPON_TYPES.md   How to build predictions for each format
src/asp/cli.py              The asp commands
src/asp/api/                Website requests and saved login state
pyproject.toml              Package installation and dependencies
```

## Run it yourself

From a downloaded copy of this repository, with `uv` installed:

```bash
uv run --python 3.11 asp auth-status
uv run --python 3.11 asp coupons
```

The first run installs the required Python and dependencies if needed.
See [SKILL.md](SKILL.md) for other installation options, commands and example
responses. See [prediction formats](references/COUPON_TYPES.md) for how to turn
a selected outcome, exact score or finishing order into a CLI submission.
