# agentsports — Coupon Type Reference

Short descriptions of coupon types available in the platform.
Outcome codes and full betting rules are always in `asp rules <id>` — never hardcode them.

## Coupon Types by Sport

### Football
| couponType | Short description |
|---|---|
| football_1x2 | 1X2 — pick home win / draw / away win |
| football_score | Exact goals (home + away, full time) |
| football_score_half | Exact goals at half time |
| football_1x2_pass | 1X2 + who advances (playoff) |
| football_score_pass | Exact score + who advances |
| football_1x2_GD | 1X2 + goal difference margin |
| football_2_1x2_pass | Two-leg 1X2 with advance |
| championship_16_football | 16-team bracket — predict all rounds |

### Hockey
| couponType | Short description |
|---|---|
| hockey_correct_score | Exact goals (NUMERIC) ± overtime/shootout |
| hockey_outcome_difference | Win margin band: big/medium/small/OT/SO |
| hockey_goal_difference | Goal diff home-away (integer −5…+5) |
| detailed_hockey | Who wins + how (reg/OT/SO) |

### Tennis
| couponType | Short description |
|---|---|
| sets_3_tennis | Sets won by each player (3-set match) |
| sets_5_tennis | Sets won by each player (5-set match) |
| games_3_tennis | Games per set, all 3 sets |
| games_5_tennis | Games per set, all 5 sets |
| tennis_set | Exact games in one set |
| tennis_tiebreak_score | Exact tiebreak set score |
| tennis_game | Game winner + loser's score (0/15/30/40) |
| tennis_match_winner | Who wins the match |
| tennis_set_winner | Who wins the set |
| quarterfinals_tennis | QF bracket winners (POINTER) |

### Basketball
| couponType | Short description |
|---|---|
| outcome_basketball | Who wins + reg/OT (4 outcomes) |
| basketball_period_score | Total points in a period (integer) |
| basketball_score_difference | Point diff home-away (integer) |

### Volleyball
| couponType | Short description |
|---|---|
| volleyball_score | Exact set score: 3-0/3-1/3-2/2-3/1-3/0-3 |

### MMA
| couponType | Short description |
|---|---|
| mma_3_round | Exact result: winner + method + round (3R) |
| mma_5_round | Exact result: winner + method + round (5R) |

### Boxing
| couponType | Short description |
|---|---|
| boxing_10_round | Decision / KO quarter / draw (10R) |
| boxing_12_round | Decision / KO quarter / draw (12R) |

### Formula 1
| couponType | Short description |
|---|---|
| formula1_winner | Top 13 finishers in order (POINTER) |
| places_22_formula1 | Full 22-car grid in order (POINTER) |
| formula1_3_winners | Podium top 3 (POINTER) |
| formula1_pilot_place | Where a specific pilot finishes (POINTER) |

### Biathlon
| couponType | Short description |
|---|---|
| biathlon_winner_20 | Top 20 finishers in order (POINTER) |
| biathlon_3_winners | Podium top 3 (POINTER) |
| biathlon_place_4 | Top 4 finishers (POINTER) |

### Overall (cross-sport)
| couponType | Short description |
|---|---|
| overall_1v2 | 1v2 match winner, no draw (any sport) |

## Value Types

- **BOOLEAN** — pick ONE outcome code per event
- **NUMERIC** — provide integer per aspect per event
- **POINTER** — provide subject tag per place aspect (use pointerValues from `asp rules`)
