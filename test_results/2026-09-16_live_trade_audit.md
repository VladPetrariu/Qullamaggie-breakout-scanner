# Live Paper-Trade Audit — 2026-09-16

Why the paper account is not profitable after 4.5 months, measured against the
theory the repo implements. Sources: `paper_trades/` (41 closed trades, 310
orders, 93-day equity curve), all 70 `scans/signals_*.json`, the daily price
caches, the run logs, and the 13,420 saved multi-window backtest picks
re-scored under the live sizing formula. Read-only analysis; nothing changed.

## Account as of 2026-09-15

| | |
|---|---|
| Equity | $24,603.85 (**−1.58%**), realized −$371, unrealized −$26 |
| Closed trades | 41 — 20W/21L (48.8%), profit factor 0.86, expectancy −$9/trade |
| Payoff | avg win **+0.51R**, avg loss **−0.53R** (payoff 0.95); only 2 wins > 1R, 8 losses at ≈ −1R |
| Exits | 33 time (60.6% win, +$1,531), 8 stops (0% win, −$1,902) |
| Max drawdown | −5.15% |
| SPY same span | +5.76% (05-04 → 09-15); account beta to SPY 0.10, daily corr 0.14 |
| Exposure | avg 37% invested (51% since 06-11) |

The result is 0.4σ from zero and 0.7σ below what the backtest predicts. It is
not evidence the bot is broken; it is what a system with this expectancy looks
like at n = 41.

## Reason 1 — the payoff structure caps the edge at ~0.05R per trade

The bot risks 1R on a 3×ATR stop (avg 11–12% of price; 51% of picks carry a
stop ≥ 10%) and exits at the close of day 10 no matter what. That makes the
risk unit huge and the winners time-capped, so a 49–51% win rate produces
almost nothing:

| Sample | win | avg win R | avg loss R | expectancy | $/trade @ $250 risk |
|---|---|---|---|---|---|
| Live, 41 trades | 48.8% | +0.51 | −0.53 | **−0.02R** | −$9 |
| Backtest top-5, fav+mixed, 2,665 picks (`atr_3_10d`) | 51.2% | +0.66 | −0.60 | **+0.046R** | +$11 |

Per-trade noise is ~$190 (std). Detecting a +$11 mean at 2σ needs ≈ **1,150
trades ≈ 10.7 years** at the bot's ~9 closed trades/month. At the 60-trade
go-live gate the expected P&L is +$660 against a 1σ band of ±$1,470 — the
gate's "positive P&L" line will be decided by noise either way.

Where the money leaks inside a trade (live):

- Time exits closed at +4.1% on average after peaking at **+10.4% MFE — 18%
  of the excursion captured**. Post-exit drift is negative (−2.8% avg / −4.3%
  median 10 days after a time exit, positive in only 7/23), so holding longer
  would not have helped — consistent with the hold15/hold20 backtest. The
  peak comes inside the window and is given back.
- The v6 partial (+3×ATR ≈ +11.2% above fill) was reached by **4 of 41**
  trades (a 2×ATR target: 13; 1.5×ATR: 21). It fired twice live (GCT, SN).

Qullamaggie's structure is the inverse: a tight low-of-day stop (2–5%), sell
⅓–½ into strength within 3–5 days, trail the remainder on the 10/20-day MA
for weeks — ~35% win rate with 3–5R winners. The May exit backtest found
tight stops "destroy the edge", but it only tested them with a fixed 10-day
exit. Tight stop + open-ended trail was never tested, and cannot be tested in
isolation: it only works on stocks that trend for weeks, which brings us to
the pool.

## Reason 2 — the sizing formula puts the most money in the stocks least able to break out

Risk-based sizing on a volatility-scaled stop makes position size ∝ 1/ATR.
Backtest correlation(position $, ADR20) = **−0.57**; live −0.43.

| ADR20 at entry | backtest avg position | live n | live P&L | live avg position |
|---|---|---|---|---|
| < 2% | $4,600–4,950 | 10 | **−$1,124** (10% win) | |
| 2–3% | $3,460 | 4 | −$326 | |
| ≥ 3% | $1,235–2,530 | 21 | **+$976** | $1,757 |

Every live position over $3,500 lost (5/5, −$938: SMFG, RDY, CM, LTC, WES —
banks, REITs, a midstream). Seven of the eight positions under $1,500 won
(+$979: WOLF, LESL, GCT, SN, LPG, ADPT, ARX). WOLF's +57.9% was worth $500
because the formula gave it an $865 position; SMFG's −6.4% cost $286 on a
$4,475 one.

What feeds the formula: the universe filter is only price ≥ $5 and volume ≥
500K, and the ranking rewards ATH + zero ATR + perfect HH/HL + EMA stack. So
41% of top-5 backtest picks have ADR < 3% (20% under 2%), and the live signal
stream included 8 ETFs/funds (WEAT filled and lost; DBA, UGL, ZSL, MDY, SHNY,
USA, IGR), foreign banks (SMFG, NWG, ING, BBVA, SAN, CM), mega-caps (MS, JPM,
RTX, GM, AAPL), and **merger-arb-pinned stocks**: OGN (0.27% ADR, currently
17% of equity — 300 shares in a stock that moved 3.3% in 60 days), APGE
(0.1–0.2% ADR), ATKR / TECH / PAYO (0.25–0.44% ADR after ~40% deal gaps —
the "pole" is the acquisition announcement and the "tight flag" is the deal
price). 21 signals had their stop floored at 3% because ATR < 1% of price;
the floor then hands them the biggest positions (16.6% of account on average
for ADR < 1% vs 5.7% for ADR > 5%).

**Caveat that must travel with this finding:** the 13k-pick backtest does
*not* support cutting low-ADR names — under the current exit they are the
best bucket (+$16–24/pick for ADR < 3 vs −$14 for ADR > 6, positive in 4/6
windows), matching the July result that an ADR ≥ 3.5 floor hurts. The live
−$1,450 from ADR < 3 names is an era effect on 14 trades, not a proven
defect. What *is* structural: the account is a low-volatility large-cap
drift harvester, not a momentum-breakout book, so it cannot produce the
theory's returns; and pinned names are dead capital (excluding stop-floored
picks costs nothing in the backtest: $10.75 vs $10.94/pick).

## Reason 3 — seven weeks at full size in the wrong regime

Until 07-30 the regime aggregator used max() instead of min(), so all 37
pre-fix scan days were labeled favorable. Recomputed from the saved breadth
values with the corrected rule: 12 favorable, 22 mixed, 3 caution.

| pre-fix trades by true regime | n | P&L | avg R |
|---|---|---|---|
| favorable | 8 | +$8 | 0.00 |
| mixed (traded at full size) | 15 | **−$648** | −0.17 |
| caution | 1 | +$122 | |

All 41 by true regime: favorable +$47 (n=16), mixed −$539 (n=24). Since the
fix the account is +$148 on 17 trades (52.9%). Since 09-02 breadth has been
caution/risk-off (38% above the 50-day, 28% above the 20-day on 09-16) and
the bot has correctly issued no signals on 6 of the last 10 scan days.

## Reason 4 (smaller) — entries take any intraday touch, unconfirmed

The order fills the instant the day's high crosses the level. 51% of live
fills closed *below* the entry price on the fill day; median fill-day volume
was 0.96× the 50-day average (only 17% ≥ 1.5×). On the larger sample of live
fills plus slot-skipped signals that would have filled (n = 77):

| fill-day close | n | avg R | win |
|---|---|---|---|
| above entry | 33 | **+0.15** | 55% |
| below entry | 44 | **−0.16** | 41% |

The trigger itself works — never-triggered orders fell −5.1% on average over
the next 10 days — the leak is the wick fill. Directional evidence only.

## Things that are NOT the problem

- **Slots / throughput.** The 138 slot-skipped signals would have filled 42
  times at 45% win, +0.07% avg — no better than what was traded.
- **Data feed (post-v6).** Every run still logs 50–190 failed downloads and
  14+ yfinance sqlite "unable to open database file" errors, but the preflight
  gate caught the four stale days (08-12 refused; 08-18, 09-08, 09-16 needed a
  re-download; 09-16's first attempt had 24% of the universe). Reliability
  issue, not P&L.
- **Market beta.** SPY rose 5.8%; the account's beta is 0.10. The P&L is
  idiosyncratic.

## Secondary backtest findings (top-5, fav+mixed, risk-sized $/pick)

- `level_type = prior_resistance` is negative (−$6.5/pick, w.avg −1.48%);
  ath +$10.2, multi_year +$12.8. "ath + multi_year only" lifts the pool to
  +$12.8/pick but is consistent in only 3/6 windows — weak.
- `has_pole = True` is negative in 4/6 windows (w.avg −0.55% vs +0.42% for
  no-pole; $0.66 vs $15.59/pick). The pole detector is flagging extension,
  the opposite of "pole then tight flag".

## Improvements, in order of expected impact

1. **Restructure the payoff, and test it together with the pool.** Add to
   `--exit-backtest`: partial at +1.5–2×ATR (not 3), tighter initial stop
   paired with an open-ended 10/20-EMA trail (no fixed 10-day cap once the
   partial is banked), and run those variants on an ADR ≥ 3–4% subset as well
   as on everything. The July test rejected tight stops only under a fixed
   10-day exit. Success metric: expectancy in R with a confidence interval,
   not win rate — the theory's target is ~35% win / 3R+ winners.
2. **Clean the universe; stop the dead-capital allocations.** Skip ETFs/CEFs
   (no `sector` in the profile is a usable proxy; better, yfinance `quoteType`),
   skip any signal whose 3×ATR stop hits the 3% floor (ATR < 1% of price —
   pinned or a fund; zero backtest cost), and lower `MAX_POSITION_PCT` so a
   3%-stop name cannot take 17–20% of equity. An ADR floor should only ship
   *with* the exit change in (1); on its own the backtest says it hurts.
3. **Confirm the breakout before committing.** Simplest daily-bar version:
   if the fill day closes below the entry, exit at that close (turns a −1R
   loser into ≈ −0.2R). The backtest harness enters at the pick-day close, so
   it needs a level-trigger entry to evaluate this properly — that upgrade
   also lets it test the fill logic the simulator actually uses.
4. **Re-state the go-live gate in R.** Track cumulative R and its standard
   error; gate on "lower 95% bound of mean R > 0" (or a fixed minimum sample
   sized from the measured std), and compare to a beta-adjusted benchmark.
   P&L sign at n = 60 is uninformative for this design.
5. **Data feed hygiene.** Point yfinance's timezone cache at a project-local
   directory (`yf.set_tz_cache_location`, available in 1.2.1) and/or disable
   download threads; the sqlite errors are the same 14 threads every day.

Optional, lower confidence: drop `prior_resistance` signals; re-examine the
pole detector.
