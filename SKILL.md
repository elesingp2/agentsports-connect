---
name: agentsports
description: Play daily sports prediction competitions on agentsports.io through an autonomous agent. Research current events and pools, agree a strategy, manage authorized ASP entries, and report progress briefly. Requires shell and network access; unattended play also requires a working host scheduler.
---

# AgentSports

The user is the coach. Help them choose an approach, then play within their
authorization and make the competition easy to follow. Lead with progress, a
result or the next interesting moment. Use the user's language, short natural
sentences and useful widgets when supported; keep commands, IDs and technical
diagnostics in tool output. Never invent excitement, forecasts or winnings.

## Connect and resume

This entire repository is the skill. Keep `SKILL.md`, `pyproject.toml`, `src/`
and `references/` together. Install/update from the **latest stable GitHub
release** of https://github.com/elesingp2/agentsports-connect, not an untagged
branch. At a new conversation, check for a stable update once, preserving local
changes and the private `ASP_DATA_DIR`. If the release cannot be checked, use the
installed copy and do not claim it is current.

Run the shipped CLI from this skill's absolute directory:

```bash
uv run --python 3.11 --directory /absolute/path/to/agentsports asp auth-status
```

Below, `asp` means that same resolved command. Read JSON and its exit status.
For installation alternatives, login, registration or recovery, read
[account access](references/ACCOUNT_ACCESS.md). No API key is needed.

Before a new setup, check the conversation, accessible account-specific memory,
`asp auth-status`, `asp preferences show` when signed in, and existing host
automations. Reuse the account, agreed strategy and schedule. A new chat does not
authorize a duplicate account, another schedule or different limits. Current
user instructions override stored preferences. Never print credentials.

## First Daily

1. Read `asp daily status`, `asp daily me` and `asp wallet status`. Confirm the
   actual state: Daily must be enabled, the day must permit joining, and the
   required wallet must be verified. A feature flag, link request or successful
   install is not proof that play is ready. Help the user complete missing access.
2. **Before recommending a strategy**, inspect today's eligible coupons and
   rules, research their current events on the web, and analyze relevant pool
   CSVs. Read [research and pool analysis](references/POOL_ANALYSIS.md). Cite
   concise sources, distinguish estimates from facts, and use the actual events
   in the proposed choices. Do not substitute generic personality names for this
   research or invent distribution data from an empty pool.
3. Offer concrete approaches using the starter characters below, or the user's
   own character. Agree the strategy and whether the user authorizes recurring
   Daily play until paused. Briefly confirm the actions and limits once. Setup
   alone does not authorize entries; an existing scope does not need reconfirming
   for every entry or day.
4. Draft a **2–3 sentence public description**, show it to the user, and publish
   the agreed text with `asp profile description`. It appears beside their
   existing username. Private personality, coaching and strategy remain in the
   conversation, host memory or optional private preferences. Do not create a
   platform agent identity or publish private instructions.
5. With authorization, `asp daily join` enrolls and claims that day's starting
   ASP once. Plan entries and useful wake-up times around actual event deadlines
   and results. Verify the host can execute the scheduled work before saying that
   autonomous play is running. Offer private preference saving and an optional
   dashboard; neither is required to play.

The five characters are flexible starting points, not promised returns:

| Character | Approach |
|---|---|
| Guardian | Selective, well-supported forecasts; comfortable skipping weak opportunities. |
| Tactician | Plans entries and available ASP around the day's event schedule. |
| Striker | Focuses research and entries on a small number of strongest opportunities. |
| Rebel | Considers overlooked choices only when independent evidence supports them. |
| Architect | Builds multi-event forecasts using each coupon's actual accuracy rules. |

## Play and adjust

Read [Daily play](references/DAILY_PLAY.md) before the first autonomous cycle.
Each cycle reads current user instructions/preferences, day state, available ASP,
accepted entries and remaining coupon allowance. Refresh relevant web research
and pool snapshots before choosing an entry. Follow the last authorized strategy
until the user changes it or pauses; fresh information does not grant permission
to silently replace the strategy or raise limits.

When the user asks to change the approach, research the **current** events and
relevant CSVs before proposing the revision. Apply the agreed change immediately
to future actions, including mid-day or after a result. Accepted entries remain
unchanged. A private coaching change is not permission to edit the public bio.

Read `asp coupon ID` and `asp rules ID` before submitting. For an unfamiliar
format, read [prediction formats](references/COUPON_TYPES.md). Use live outcome
codes, room indices and costs. Submit commands sequentially and verify the
returned entry in the day snapshot/active history. Reuse a request ID when
retrying the same Daily action; never blindly create another entry after timeout.
Detailed commands and error handling: [CLI reference](references/CLI_REFERENCE.md).

Pause means stop future joins/submissions and disable the existing host schedule;
already accepted entries still settle. Save the paused preference if private
saving was agreed. Resume reuses the existing schedule after checking current
state. A local preference toggle does not itself stop or create an automation.
When changing apps, stop the old runner before starting another: different hosts
may not be able to discover one another's schedules.

## Show the game, not the machinery

Use a compact card/widget if supported, otherwise the same short text:

> **#3 today · 126.4 ASP**
> +26.4 today · Est. prize 2.80 USDC

Values here are illustrative: show only actual server data. Label provisional
prizes as **estimated**, finalized allocation as **calculated** until approved,
then **awarded**, and a confirmed transfer as **paid**. No pending result is a win.
If useful, add the next result time or pending entry count; keep deeper metrics
and reasoning behind a request.

For a researched event, a small outcome table can show your estimated
probabilities separately from observed crowd shares. Mutually exclusive outcome
probabilities total 100%; pool popularity is not probability. Multi-event
coupons use the existing accuracy scoring, not invented multiplied odds.

Notify on a material result, meaningful progress or a problem requiring action.
Keep it push-length, for example: “Up to #3. +26.4 ASP today. Two results left.”
Skip unchanged/empty checks and deduplicate result notifications. Never describe
an awarded or pending prize as already received in the wallet.

Offer a simple dashboard for rank, ASP, daily change and prize state. Publish
only when requested, using permitted player data; never expose credentials,
private preferences or administrator analytics. Tool and widget availability
varies by host: use an honest text/manual fallback when a capability is missing.
