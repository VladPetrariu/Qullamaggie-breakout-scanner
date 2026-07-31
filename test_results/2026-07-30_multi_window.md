# Multi-Window Backtest Results — 2026-07-30 (v5 quality-first ranking)

6 non-overlapping windows covering ~3 years of data. Ranking: quality count → HH/HL → ATR → ABR distance.

## 1-Day Forward Returns

| Window | Days | N | Win Rate | W.Avg | Median |
|--------|------|---|----------|-------|--------|
| Jul 2023 — Jan 2024 | 126 | 1,840 | 50.2% | -0.13% | +0.02% |
| Jan 2024 — Jul 2024 | 126 | 2,400 | 52.8% | +0.06% | +0.12% |
| Jul 2024 — Jan 2025 | 126 | 2,340 | 49.2% | -0.00% | +0.00% |
| Jan 2025 — Jul 2025 | 126 | 2,040 | 50.2% | -0.02% | +0.02% |
| Jul 2025 — Jan 2026 | 126 | 2,500 | 50.3% | +0.08% | +0.03% |
| Jan 2026 — Jul 2026 | 126 | 2,300 | 50.7% | +0.08% | +0.06% |
| **Average** | | | **50.6%** | **+0.01%** | **+0.04%** |
| **Std Dev** | | | 1.1% | 0.07% | 0.04% |

## 3-Day Forward Returns

| Window | Days | N | Win Rate | W.Avg | Median |
|--------|------|---|----------|-------|--------|
| Jul 2023 — Jan 2024 | 126 | 1,840 | 48.5% | -0.27% | -0.09% |
| Jan 2024 — Jul 2024 | 126 | 2,400 | 54.0% | +0.25% | +0.25% |
| Jul 2024 — Jan 2025 | 126 | 2,340 | 48.8% | -0.30% | -0.11% |
| Jan 2025 — Jul 2025 | 126 | 2,040 | 51.0% | -0.13% | +0.12% |
| Jul 2025 — Jan 2026 | 126 | 2,500 | 51.0% | +0.25% | +0.10% |
| Jan 2026 — Jul 2026 | 126 | 2,300 | 51.0% | -0.02% | +0.08% |
| **Average** | | | **50.7%** | **-0.04%** | **+0.06%** |
| **Std Dev** | | | 1.8% | 0.22% | 0.12% |

## 5-Day Forward Returns

| Window | Days | N | Win Rate | W.Avg | Median |
|--------|------|---|----------|-------|--------|
| Jul 2023 — Jan 2024 | 126 | 1,840 | 47.2% | -0.32% | -0.24% |
| Jan 2024 — Jul 2024 | 126 | 2,400 | 55.9% | +0.34% | +0.53% |
| Jul 2024 — Jan 2025 | 126 | 2,340 | 50.1% | -0.27% | +0.02% |
| Jan 2025 — Jul 2025 | 126 | 2,040 | 51.6% | +0.03% | +0.17% |
| Jul 2025 — Jan 2026 | 126 | 2,500 | 53.4% | +0.54% | +0.39% |
| Jan 2026 — Jul 2026 | 126 | 2,300 | 48.6% | -0.38% | -0.09% |
| **Average** | | | **51.1%** | **-0.01%** | **+0.13%** |
| **Std Dev** | | | 2.9% | 0.35% | 0.27% |

## 10-Day Forward Returns

| Window | Days | N | Win Rate | W.Avg | Median |
|--------|------|---|----------|-------|--------|
| Jul 2023 — Jan 2024 | 126 | 1,840 | 47.0% | -0.61% | -0.41% |
| Jan 2024 — Jul 2024 | 126 | 2,400 | 56.0% | +0.53% | +0.72% |
| Jul 2024 — Jan 2025 | 126 | 2,340 | 50.4% | -0.04% | +0.07% |
| Jan 2025 — Jul 2025 | 126 | 2,040 | 50.6% | -0.25% | +0.11% |
| Jul 2025 — Jan 2026 | 126 | 2,500 | 55.1% | +1.00% | +0.88% |
| Jan 2026 — Jul 2026 | 126 | 2,299 | 50.0% | -0.11% | +0.00% |
| **Average** | | | **51.5%** | **+0.09%** | **+0.23%** |
| **Std Dev** | | | 3.1% | 0.53% | 0.44% |

## Regime Distribution (5-day pick counts)

| Window | Favorable | Mixed | Caution |
|--------|-----------|-------|---------|
| Jul 2023 — Jan 2024 | 1000 | 260 | 580 |
| Jan 2024 — Jul 2024 | 660 | 1240 | 500 |
| Jul 2024 — Jan 2025 | 1060 | 880 | 400 |
| Jan 2025 — Jul 2025 | 420 | 1020 | 600 |
| Jul 2025 — Jan 2026 | 960 | 1160 | 380 |
| Jan 2026 — Jul 2026 | 600 | 1400 | 300 |

## Regime Win Rates (5-day)

| Window | Favorable | Mixed | Caution |
|--------|-----------|-------|---------|
| Jul 2023 — Jan 2024 | 52.0% | 43.5% | 40.7% |
| Jan 2024 — Jul 2024 | 54.1% | 57.1% | 55.4% |
| Jul 2024 — Jan 2025 | 45.9% | 53.3% | 54.0% |
| Jan 2025 — Jul 2025 | 52.6% | 51.9% | 50.5% |
| Jul 2025 — Jan 2026 | 53.5% | 53.4% | 53.2% |
| Jan 2026 — Jul 2026 | 45.7% | 50.4% | 46.0% |

## Addendum: corrected-regime split (added post-run)

First multi-window run with the fixed min() regime aggregation, 5y warm-up
(252-bar-bounded 52wk indicators), and windows shifted ~4 months vs the
2026-04-12 run (now Jul 2023 – Jul 2026, so it includes the weak Apr–Jul 2026
live era and drops Jun–Jul 2023). Picks are generated with the corrected
regime active — risk_off days produce no picks.

Forward returns by corrected regime (winsorized ±30):

| regime | n | 5d win / w.avg | 10d win / w.avg | 10d top-5 w.avg |
|---|---|---|---|---|
| favorable | 4,700 | 50.5% / +0.00% | 51.0% / +0.17% | +0.29% |
| mixed | 5,959 | 52.8% / +0.16% | 52.6% / +0.32% | +0.25% |
| caution | 2,760 | 49.7% / −0.30% | 51.2% / −0.34% | −0.65% |

**What reproduces:** caution days are negative (both window sets, both
horizons, top-5 included) — skipping caution/risk_off is the robust part of
the regime gate. **What does not:** the 2026-07-29 experiment's ~4× favorable
premium over mixed (measured on the old window set) inverts here — pooled
mixed slightly beats favorable, and favorable-only swings from −1.9% to +2.1%
w.avg across windows (window 6, Jan–Jul 2026, favorable = −1.87%: the recent
era was weak even on favorable days, consistent with the live losing streak).
Regime labels partly proxy for era, exactly as the experiment's verifier
warned.

Policy implication: the implemented tiered sizing (favorable 1.0×, mixed
0.5×, caution/risk_off 0×) keeps both positive buckets and skips the negative
one — blended +0.166%/traded pick vs +0.134% trading everything. The
favorable/mixed size ratio is the era-dependent part; re-evaluate it once
~50 tiered live trades exist rather than tuning it on either window set.
