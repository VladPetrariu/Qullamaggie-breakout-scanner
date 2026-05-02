# Exit Strategy Backtest — 2026-05-01

Simulated 12 exit strategies on 13,500 picks (skipped 44 for missing data) from the 6-window multi_window backtest. Picks come from v5 quality-first ranking. Entry = close on pick day, ATR = Wilder(14) at entry. Stop fills assumed at the stop price when day's Low touches it (no slippage modeled — a real bot will see slippage on gap-downs). Returns winsorized at +/-30%.

## Overall — ranked by expectancy

| Strategy | N | Win % | Avg | W.Avg | Median | Best | Worst | Expectancy | Avg Days | Avg DD |
|---|---|---|---|---|---|---|---|---|---|---|
| atr_3_10d | 13,456 | 51.4% | +0.72% | -0.02% | +0.20% | +2017.99% | -54.88% | +0.72% | 9.2 | -4.97% |
| baseline_hold_10d | 13,456 | 52.6% | +0.69% | +0.11% | +0.34% | +2017.99% | -97.48% | +0.69% | 10.0 | -5.54% |
| baseline_hold_5d | 13,456 | 51.9% | +0.56% | +0.07% | +0.17% | +3074.85% | -97.22% | +0.56% | 5.0 | -3.66% |
| pct_7_10d | 13,456 | 46.5% | +0.55% | +0.15% | -0.58% | +1413.47% | -7.00% | +0.55% | 8.1 | -3.70% |
| atr_2_10d | 13,456 | 47.8% | +0.52% | -0.04% | -0.40% | +1413.47% | -45.80% | +0.52% | 8.2 | -4.31% |
| atr_2_trail_3_10d | 13,456 | 47.8% | +0.33% | +0.03% | -0.39% | +1706.68% | -45.80% | +0.33% | 8.0 | -4.16% |
| trail_3_10d | 13,456 | 50.8% | +0.32% | +0.05% | +0.12% | +1706.68% | -54.88% | +0.32% | 8.8 | -4.67% |
| pct_5_10d | 13,456 | 42.1% | +0.32% | +0.14% | -1.83% | +423.01% | -5.00% | +0.32% | 7.3 | -3.21% |
| partial_atr_2_trail_2_10d | 13,456 | 49.0% | +0.08% | -0.09% | -0.21% | +1716.70% | -39.70% | +0.08% | 7.3 | -3.81% |
| trail_2_10d | 13,456 | 45.1% | -0.03% | -0.25% | -0.76% | +1716.70% | -39.70% | -0.03% | 7.3 | -3.81% |
| atr_2_trail_2_10d | 13,456 | 45.1% | -0.03% | -0.25% | -0.76% | +1716.70% | -39.70% | -0.03% | 7.3 | -3.81% |
| atr_2_trail_2_15d | 13,456 | 41.7% | -0.05% | -0.28% | -1.36% | +1716.70% | -41.31% | -0.05% | 9.0 | -4.01% |

## Exit reason mix (overall)

| Strategy | stop % | time % | other |
|---|---|---|---|
| atr_3_10d | 19.0% | 81.0% | - |
| baseline_hold_10d | 0.0% | 100.0% | - |
| baseline_hold_5d | 0.0% | 100.0% | - |
| pct_7_10d | 32.9% | 67.1% | - |
| atr_2_10d | 35.6% | 64.4% | - |
| atr_2_trail_3_10d | 41.5% | 58.5% | - |
| trail_3_10d | 29.8% | 70.2% | - |
| pct_5_10d | 44.6% | 55.4% | - |
| partial_atr_2_trail_2_10d | 58.3% | 41.7% | - |
| trail_2_10d | 58.3% | 41.7% | - |
| atr_2_trail_2_10d | 58.3% | 41.7% | - |
| atr_2_trail_2_15d | 74.3% | 25.7% | - |

## By regime — top 5 strategies per regime (by expectancy)

### favorable

| Strategy | N | Win % | W.Avg | Median | Expectancy |
|---|---|---|---|---|---|
| atr_3_10d | 10,402 | 51.5% | +0.14% | +0.23% | +1.07% |
| baseline_hold_10d | 10,402 | 52.5% | +0.21% | +0.36% | +0.99% |
| baseline_hold_5d | 10,402 | 52.6% | +0.21% | +0.24% | +0.83% |
| atr_2_10d | 10,402 | 48.1% | +0.12% | -0.35% | +0.80% |
| pct_7_10d | 10,402 | 46.5% | +0.25% | -0.59% | +0.73% |

### mixed

| Strategy | N | Win % | W.Avg | Median | Expectancy |
|---|---|---|---|---|---|
| pct_7_10d | 2,874 | 46.4% | -0.26% | -0.60% | -0.16% |
| pct_5_10d | 2,874 | 41.3% | -0.29% | -2.10% | -0.21% |
| atr_2_trail_3_10d | 2,874 | 46.6% | -0.53% | -0.60% | -0.42% |
| trail_3_10d | 2,874 | 49.8% | -0.50% | -0.01% | -0.42% |
| baseline_hold_5d | 2,874 | 48.9% | -0.51% | -0.09% | -0.48% |

### caution

| Strategy | N | Win % | W.Avg | Median | Expectancy |
|---|---|---|---|---|---|
| baseline_hold_10d | 180 | 61.1% | +1.85% | +1.39% | +2.42% |
| atr_3_10d | 180 | 57.2% | +0.99% | +1.11% | +1.56% |
| pct_5_10d | 180 | 45.6% | +0.86% | -2.15% | +1.49% |
| pct_7_10d | 180 | 50.6% | +0.80% | +0.06% | +1.44% |
| baseline_hold_5d | 180 | 56.1% | +1.27% | +0.81% | +1.32% |

## Per-window expectancy — top 3 strategies overall

| Strategy | W1 | W2 | W3 | W4 | W5 | W6 |
|---|---|---|---|---|---|---|
| atr_3_10d | -0.35% | +0.62% | -0.07% | -1.20% | +5.16% | -0.03% |
| baseline_hold_10d | -0.44% | +0.66% | -0.12% | -1.06% | +5.11% | -0.15% |
| baseline_hold_5d | -0.12% | +0.18% | +0.11% | -0.50% | +3.71% | -0.13% |
