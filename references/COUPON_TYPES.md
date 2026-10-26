# Building a prediction

A **coupon** is a prediction round containing one or more **events**. A **room**
sets the currency and stake. A **selection** is your forecast for an event or one
aspect of that event. `asp predict` submits the whole coupon in one request.

Always begin with:

```bash
asp coupon 123
asp rules 123
```

Use the returned `couponId`, `events[].eventId`, `rooms[].roomIndex`, outcome codes
and participant tags. The numbers below illustrate the format; replace them with
the current round's values. A label such as `1 (home wins)` is not its API code.

## Read the response

- `coupon`: events, start times and rooms. Select an available room with the
  authorized currency and a permitted stake.
- `rules.outcomes`: each aspect's `code`, `label` and `valueType`.
- `rules.selectionTemplate`: the selection key/value shape.
- `rules.instructions`, `rulesText`, `scoringRules`: constraints and scoring.
- `rules.pointerValues`: allowed participant tags for each event.

The current API sometimes includes explanatory `/* comments */` **inside string
values** in `selectionExample`. Remove those annotations before submitting.
A structural example also does not establish that a score satisfies sport rules.
Never send placeholders, comments, display names or aspect labels as values.

## 1. One outcome per event — BOOLEAN

Example: `football_1x2`, with codes returned by `asp rules`:

```json
{
  "outcomes": [
    {"code": "8", "label": "1 (home wins)", "valueType": "BOOLEAN"},
    {"code": "9", "label": "X (draw)", "valueType": "BOOLEAN"},
    {"code": "10", "label": "2 (away wins)", "valueType": "BOOLEAN"}
  ]
}
```

For event `456`, choosing a home win is `{"456":"8"}`:

```bash
asp predict --coupon 123 --selections '{"456":"8"}' --room 0 --stake 1
```

For a two-event coupon, provide both choices in one object:

```bash
asp predict --coupon 123 --selections '{"456":"8","457":"9"}' --room 0 --stake 1
```

This shape also applies to ordinary winner/margin categories, including
`football_1x2_GD`, `hockey_outcome_difference`, `outcome_basketball` and
`basketball_score_difference`. The last one uses outcome codes despite its name;
it does **not** accept an arbitrary integer margin.

Combined formats such as match result **and** qualification can require more
than one Boolean group. Use explicit `eventId:aspectCode` keys with `"true"` or
`"false"` for those groups, following that coupon's rules. The single-event-key
shortcut can select only one Boolean aspect.

## 2. Exact score — multiple NUMERIC aspects

For `football_score`, a live rule response may expose:

```json
{
  "outcomes": [
    {"code": "0", "label": "home goals full time (integer)", "valueType": "NUMERIC"},
    {"code": "1", "label": "away goals full time (integer)", "valueType": "NUMERIC"}
  ]
}
```

To predict **2–1**, provide each component separately:

```bash
asp predict --coupon 124 --selections '{"456:0":"2","456:1":"1"}' --room 0 --stake 1
```

`456` is the event ID; `0` and `1` are aspect codes; `2` and `1` are predicted
numbers. Do not send `"2:1"`, or put both scores under the same event-level key.
For multiple events, repeat every required score component with the next event ID.

Other numeric formats can ask for sets, games, period points or a single score.
Use their own aspect codes and limits. Required values must also form a valid
sports result: for example, a best-of-three set score cannot be 0–0 or 3–0.

## 3. A single number — NUMERIC

For `hockey_goal_difference`, a positive value means home minus away:

```bash
asp predict --coupon 125 --selections '{"458":"1"}' --room 0 --stake 1
```

This predicts a one-goal home margin. The explicit equivalent, when the returned
aspect code is `111`, is `{"458:111":"1"}`. Use one of these forms, not both.
Check the allowed range in the live rules; do not interpret `1` as an outcome code.

## 4. Finishers — POINTER

A pointer value is a participant's exact `tag`, not their name, numeric ID or
position in the participants array. A podium example with live codes for places
1, 2 and 3 is:

```bash
asp predict --coupon 126 --selections '{"459:239":"georgeRussell","459:240":"kimiAntonelli","459:241":"charlesLeclerc"}' --room 0 --stake 1
```

Choose tags from **that event's** `pointerValues`/`participants`. Assign distinct
participants to the required places.

The legacy API can expose all result positions even when the forecast asks for
fewer positions. In particular:

| Coupon type | Forecast to submit per event |
|---|---|
| `formula1_winner`, `biathlon_winner_20` | First place only |
| `formula1_3_winners`, `biathlon_3_winners` | Places 1–3 |

Do not infer the number of picks from the number in a coupon name, or assume that
every aspect in a legacy result schema is a required prediction. For bracket and
other pointer formats, read the round's instructions and position labels.

## 5. Score plus overtime/shootout — mixed NUMERIC and BOOLEAN

`hockey_correct_score` combines goal counts and the way the match ends. Given
numeric codes `101`/`102` and Boolean codes `96`/`97`/`99`/`98`, a **3–1 regulation
home win** is:

```bash
asp predict --coupon 127 --selections '{"458:101":"3","458:102":"1","458:96":"false","458:97":"false","458:99":"false","458:98":"false"}' --room 0 --stake 1
```

For a **3–2 home win in overtime**, change the away score to `2` and set the
returned home-overtime aspect (`96` in this example) to `"true"`. Keep the other
three ending flags false. This format requires unequal, nonnegative goal counts;
an overtime/shootout forecast must have a one-goal margin and one ending flag.

Other mixed formats, such as `tennis_game`, use the same `eventId:aspectCode`
shape: numeric values for numeric aspects and true/false values for Boolean
aspects. Apply that format's own valid-score and winner constraints.

## Submit and verify

All examples assume room `0` accepts a stake of `1`; verify this with `asp coupon`
first. Fixed rooms use their fixed price. `ASP_MAX_STAKE` can enforce the user's
limit and also checks the room minimum.

A successful submission returns `success: true` and `betId`. Find that ID in
`asp active`, then check `asp history` after scoring. `points: "-"` means the bet
has not been scored. A zero score is still a scored result.

On `invalid_selections`, reread the specific rules and correct the payload; do not
blindly retry. On a timeout, inspect `active` and `history` before resubmitting,
since a successful write may have lost its response. Never submit solely to test
an installation; predictions require the user's authorization.

## Read a pool CSV

`asp pool-csv ID --output /absolute/path/to/pool.csv` exports the existing full-coupon report. Parse it as CSV: row 1 names events, row 2 labels aspects, and later rows contain entries. Carry merged event headings right across blank cells; identify repeated aspect labels by their event and column position. Preserve repeated rows and zeros.

Rows are entries, not unique people. The report has no identities, per-row stakes, room IDs or payouts, so do not invent stake-weighted shares. Blank cells depend on the live format; timestamps retain the report's timezone. Empty or small pools support limited conclusions, and crowd popularity is not outcome probability. Multi-event forecasts use the coupon's scoring rules, not multiplied odds.
