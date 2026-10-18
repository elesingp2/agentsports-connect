# AgentSports

An AI-agent skill for sports predictions on [agentsports.io](https://agentsports.io).
Your agent can find events, explain the rules, help you sign up or recover your
account, and submit the predictions you choose.

Works with any agent that can run terminal commands and access the internet.
The `asp` command returns structured JSON, so the agent can read results directly.

## Get started

1. Use an AI agent that can run terminal commands and access the internet.
2. Copy the prompt below, paste it into the agent and send it.
3. Sign in or register, get a short introduction, then choose where to start.

```text
Install or update the AgentSports skill from
https://github.com/elesingp2/agentsports-connect (main) and follow SKILL.md.
Help me sign in, briefly explain the game and how you can help in my language,
then suggest a first step. Ask before submitting predictions.
```

For a new account, you only need to provide your email. The agent generates and
privately saves a nickname and password, and tells you that the site terms were
accepted. If it cannot access your inbox, open the confirmation email yourself
and tell the agent when you are done, or give it the activation link.

Returning players reuse saved access or recover their existing account. If no
rounds are open, setup still finishes and the agent tells you there is nothing
to predict yet. Installing the skill does not submit a prediction.

## Repository map

```text
SKILL.md                    Agent instructions, commands and JSON examples
README.md                   This introduction
references/COUPON_TYPES.md   How to build predictions for each format
references/POOL_ANALYSIS.md  How to interpret a selected pool export
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

## Export a coupon's pool

```bash
asp pool-csv 123 --output ./coupon-123.csv
```

Downloads the website's existing full-coupon Excel report and saves all its
values as UTF-8 CSV, including both header rows. JSON output gives the file path,
bet count, size and snapshot time without filling the agent's context with rows.
Existing files are never overwritten. See [pool analysis](references/POOL_ANALYSIS.md)
for the format and interpretation. Research and shortlist one or two coupons
before exporting; combine the pool snapshot with current event research and
remove temporary files after analysis when no longer needed.
