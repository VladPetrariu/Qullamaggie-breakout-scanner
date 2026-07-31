# Counterfactual Analysis — 2026-07-29

Five counterfactual experiments on saved data (13,456 multi-window backtest picks,
37 live signal files, the paper account, and the daily price caches), each
adversarially verified by an independent re-implementation. Motivated by the live
paper results since Jun 11: 14 closed trades, 28.6% win rate, −3.31% equity,
payoff ratio ~1:1, with 9 of 14 exits being 10-day time exits that peaked at
avg +9.95% MFE but closed +3.06%.

All winsorized figures clip at ±30% (the repo's W.Avg convention). Every
experiment inherits the optimistic stop-fill convention (stop fills at the stop
price on a Low touch; no gap modeling) and the survivorship bias of
yfinance-today snapshots (44/13,500 picks skipped; delisted names absent).

## 1. Exit variants (verified: CONFIRMED, exact reproduction)

Harness validated by reproducing the saved `atr_3_10d` / `baseline_hold_10d`
stats to 3 decimals. New variants use next-bar effectiveness for close-derived
stop changes (the original harness's same-bar trailing overstated the case
against trailing stops by ~0.5pp on breakeven variants).

| strategy | win% | w.avg | median | payoff | fav w.avg | top5 w.avg |
|---|---|---|---|---|---|---|
| atr_3_10d (old default) | 51.4 | −0.021 | +0.20 | 1.14 | +0.135 | **−0.234** |
| **partial3_trail3** (new default) | 53.2 | **+0.291** | +0.47 | 0.99 | **+0.441** | **+0.329** |
| partial2_be | 57.0 | +0.287 | +1.25 | 0.89 | +0.401 | +0.294 |
| trail2_after_2atr | 54.0 | +0.207 | +0.45 | 1.00 | +0.377 | +0.241 |
| hold15 / hold20 | 49.4/47.9 | −0.13/−0.15 | −0.10/−0.56 | — | — | −0.51 (h20) |

- The old exit was worst precisely in the top-5 ranks the bot trades.
- 39.4% of trades touch +2×ATR intraday; 49.3% of touchers close back below it —
  the same giveback leak observed live.
- Longer holds are outlier capture: raw avg up, median and w.avg down. Rejected.
- Mixed regime is negative under all 14 variants — no exit rescues it.
- Verifier caveat: the improvement is winsorized-only; raw mean favors the old
  exit via ~0.2% of trades beyond +100% which partialing halves. This trades
  moonshot capture for a better typical trade. The top three partial variants
  are within noise of each other; the robust finding is "50% partial at +2–3×ATR
  on the wide 3×ATR stop".

**Implemented:** `partial3_trail3` — resting limit sells 50% at entry +3×ATR,
remainder trails at highest close −3×ATR, next-bar effective, 3×ATR initial stop
and 10d max hold unchanged (`PARTIAL_PROFIT_ATR`, `TRAIL_STOP_ATR`).

## 2. Corrected regime gate (verified: PLAUSIBLE_WITH_CAVEATS, one correction)

`market_context.py` aggregated indicator regimes with max() over
["risk_off","caution","mixed","favorable"] — the most *bullish* indicator —
while the comment claimed most-bearish. Replication matched stored backtest
regimes 97.8% (mismatches = window-1 data-start artifact).

- Only 38.2% of buggy-"favorable" days are favorable under min(); 14.1% are
  actually caution/risk_off (w.exp −0.98%/−0.18% per trade under atr_3_10d).
- Corrected-favorable picks: +0.536% w.exp vs +0.135% for buggy-favorable (~4×).
- Live era verified exactly: 11 favorable / 21 mixed / 3 caution of 35 scan days.
- **Verifier correction:** the experiment's claim that tiered sizing beats the
  status quo on absolute monthly return contained a 1.384× arithmetic inflation.
  Corrected: tiered ≈ +0.26%/mo winsorized vs status quo +0.29%/mo. The case for
  tiered is risk-adjusted (2× per-trade expectancy, no full-size exposure on
  negative-expectancy days) plus throughput: strict favorable-only trades ~6
  days/mo (~28 months to 100 trades); tiered ~14 days/mo (~13 months).
- The statistically robust component is the caution/risk_off penalty
  (day-clustered z 2.2–2.9); the favorable premium leans partly on window 1,
  whose labels are unreliable — the 3y download left the 52-week H/L indicator
  degenerate for ~200 days (invisible under max(), dominant under min()).

**Implemented:** min() fix; `SIGNAL_TRADABLE_REGIMES = ("favorable","mixed")`
with `REGIME_RISK_MULTIPLIERS = {favorable: 1.0, mixed: 0.5}` applied in both
signal sizing and simulator fill re-sizing; `indicator_regimes` logged into
signal summaries; 52-week indicators bounded to 252 bars; backtest download
5y with the multi-window test span held at the trailing ~3 years; re-run queued.

## 3. ADR selection (verified: CONFIRMED)

The "v5 picks low-ADR defensives" hypothesis is refuted: live signals sit at the
61st percentile of the backtest ADR20 distribution (median 3.83%; filled trades
4.29%). An ADR ≥ 3.5 floor *hurts*: −0.53pp w.exp (95% CI [−0.86,−0.21],
p=0.0015), win rate 51.0→47.8, and a third fewer signals.

The opposite filter helps: the ADR20 > 8% bucket wins 41.5% with a −4.94% median
(sim) — its raw-mean appeal is one repeated squeeze (QMMM, 5 overlapping picks,
+840% to +2018%). A ceiling of 8 is worth +0.5–0.67pp w.exp per trade with
positive deltas in 5–6 of 6 windows and near-zero throughput cost (~7% of live
signals). Caveat that ships with it: the ceiling would have excluded the two
biggest live winners (WOLF +57.9%, LESL +19.3%) — re-evaluate after ~50 more
paper trades.

**Implemented:** `MAX_ADR20_PCT = 8.0`, skip reason `adr_too_high`, `adr20`
recorded on every signal.

## 4. Slot capacity (verified: PLAUSIBLE_WITH_CAVEATS, timelines corrected)

Replay harness reproduced by an independent implementation to the cent. A
5-slot replay of the live signal stream diverged from the real account by
+$682 purely from retroactive dividend adjustments (ILPT fill flip under the 2%
split tolerance) — data-revision risk for any live-vs-backtest comparison.

- Slot scarcity was not protecting the account: marginal trades at 8 slots were
  no worse than the shared trades (n=6 — "not worse", not "better").
- Beyond ~10 slots cash binds ($25k, 1% risk: max 13 concurrent ever, 19
  insufficient-cash skips at 50 slots); max DD worsens monotonically
  (−2.40/−2.97/−3.90/−4.82% at 5/8/10/50). P&L ordering between 8/10/50 is noise.
- Verifier-corrected go-live timelines (closed-trade rate): ~17 months at
  5 slots, ~12.6 at 8, ~8.9 unlimited. 100 trades was unreachable as a gate.

**Implemented:** `MAX_OPEN_POSITIONS = 8` (simulator) decoupled from
`MAX_SIGNALS_PER_DAY = 5` (signals.py previously reused one constant for both —
a naive bump would have started issuing untested rank-6+ signals). Go-live gate
restated: 60+ trades with a Wilson 95% CI win-rate test (fail only when the CI
sits conclusively below the 47–56% backtest band).

## 5. Missed trades + data integrity (verifier died on session limit; key claims re-verified by hand)

- Chasing all 12 gapped entries at the open would have LOST ~$136 (41.7% win);
  gaps >1.5% lose 5:1. The no-chase rule stays. *(directional — small n)*
- 18 of 26 never-triggered orders fell −2.91% avg over the next 10 days with
  zero positive outcomes. The buy-stop trigger is a working entry filter.
- Data feed (re-verified directly): SPY absent from 17/35 live daily caches;
  universe size swung 2,992–5,474; 6/35 scan days ran on catastrophically stale
  prices; the bot scanned and placed orders on Juneteenth and Jul 3 (holidays);
  `data.py`'s date-keyed cache means the shell retry loop re-reads the same
  poisoned parquet and can never repair bad data.
- Split-rescale misfire: a signal whose activation slipped past the 9:30 ET
  cutoff had its last_close compared against the wrong session, so a −7.8% day
  (JBL) was misread as a split and the order's levels silently rewritten.

**Implemented:** NYSE holiday guard (`market_calendar.py`, rule-based);
preflight gate (`preflight.py`, step 2.5): SPY + ^VIX + ≥90% of the universe
must carry the prior session's bar, else force re-download (up to 3 attempts,
bypassing the cache) and, still failing, write an empty signals file and exit
non-zero; benchmarks download in their own retried batch; signals now record
`last_close_date` and the simulator anchors split detection to it.

## Not implemented (evidence said no)

- Chase-at-open logic (loses money), ADR floor (hurts), longer holds (hurt),
  plain breakeven stops (win-rate optics break the gate), trailing from entry
  (still harmful), slots >10 (cash-bound, worse DD), strict favorable-only gate
  (starves throughput without absolute-return benefit).
