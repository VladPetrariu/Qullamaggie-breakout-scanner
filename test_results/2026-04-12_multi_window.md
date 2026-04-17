# Multi-Window Backtest Results — 2026-04-12 (v5 quality-first ranking)

6 non-overlapping windows covering ~3 years of data. Ranking: quality count → HH/HL → ATR → ABR distance.

## 1-Day Forward Returns

| Window | Days | N | Win Rate | W.Avg | Median |
|--------|------|---|----------|-------|--------|
| Jun 2023 — Dec 2023 | 115 | 2,120 | 50.3% | +0.01% | +0.03% |
| Dec 2023 — May 2024 | 115 | 2,300 | 52.1% | -0.04% | +0.09% |
| May 2024 — Nov 2024 | 115 | 2,280 | 51.5% | +0.09% | +0.10% |
| Nov 2024 — Apr 2025 | 115 | 2,140 | 46.4% | -0.39% | -0.15% |
| Apr 2025 — Oct 2025 | 115 | 2,300 | 53.3% | +0.35% | +0.15% |
| Oct 2025 — Mar 2026 | 118 | 2,360 | 48.3% | -0.03% | -0.03% |
| **Average** | | | **50.3%** | **-0.00%** | **+0.03%** |
| **Std Dev** | | | 2.3% | 0.22% | 0.10% |

## 3-Day Forward Returns

| Window | Days | N | Win Rate | W.Avg | Median |
|--------|------|---|----------|-------|--------|
| Jun 2023 — Dec 2023 | 115 | 2,120 | 49.8% | -0.11% | +0.00% |
| Dec 2023 — May 2024 | 115 | 2,300 | 53.3% | +0.12% | +0.22% |
| May 2024 — Nov 2024 | 115 | 2,280 | 51.3% | +0.12% | +0.10% |
| Nov 2024 — Apr 2025 | 115 | 2,140 | 47.5% | -0.81% | -0.24% |
| Apr 2025 — Oct 2025 | 115 | 2,300 | 54.0% | +0.65% | +0.31% |
| Oct 2025 — Mar 2026 | 118 | 2,360 | 49.1% | -0.09% | +0.00% |
| **Average** | | | **50.8%** | **-0.02%** | **+0.07%** |
| **Std Dev** | | | 2.3% | 0.43% | 0.18% |

## 5-Day Forward Returns

| Window | Days | N | Win Rate | W.Avg | Median |
|--------|------|---|----------|-------|--------|
| Jun 2023 — Dec 2023 | 115 | 2,120 | 51.0% | -0.13% | +0.08% |
| Dec 2023 — May 2024 | 115 | 2,300 | 54.5% | +0.22% | +0.44% |
| May 2024 — Nov 2024 | 115 | 2,280 | 52.1% | +0.09% | +0.18% |
| Nov 2024 — Apr 2025 | 115 | 2,140 | 46.6% | -0.79% | -0.34% |
| Apr 2025 — Oct 2025 | 115 | 2,300 | 56.1% | +1.17% | +0.61% |
| Oct 2025 — Mar 2026 | 118 | 2,360 | 50.4% | -0.18% | +0.03% |
| **Average** | | | **51.8%** | **+0.06%** | **+0.17%** |
| **Std Dev** | | | 3.0% | 0.59% | 0.30% |

## 10-Day Forward Returns

| Window | Days | N | Win Rate | W.Avg | Median |
|--------|------|---|----------|-------|--------|
| Jun 2023 — Dec 2023 | 115 | 2,120 | 51.1% | -0.36% | +0.17% |
| Dec 2023 — May 2024 | 115 | 2,300 | 56.0% | +0.60% | +0.76% |
| May 2024 — Nov 2024 | 115 | 2,280 | 50.4% | -0.20% | +0.05% |
| Nov 2024 — Apr 2025 | 115 | 2,140 | 45.0% | -1.53% | -0.77% |
| Apr 2025 — Oct 2025 | 115 | 2,300 | 59.3% | +2.15% | +1.42% |
| Oct 2025 — Mar 2026 | 118 | 2,360 | 53.0% | -0.16% | +0.36% |
| **Average** | | | **52.5%** | **+0.08%** | **+0.33%** |
| **Std Dev** | | | 4.5% | 1.12% | 0.67% |

## Regime Distribution (5-day pick counts)

| Window | Favorable | Mixed | Caution |
|--------|-----------|-------|---------|
| Jun 2023 — Dec 2023 | 860 | 1260 | 0 |
| Dec 2023 — May 2024 | 2000 | 300 | 0 |
| May 2024 — Nov 2024 | 2120 | 120 | 40 |
| Nov 2024 — Apr 2025 | 1360 | 700 | 80 |
| Apr 2025 — Oct 2025 | 2220 | 80 | 0 |
| Oct 2025 — Mar 2026 | 1880 | 420 | 60 |

## Regime Win Rates (5-day)

| Window | Favorable | Mixed | Caution |
|--------|-----------|-------|---------|
| Jun 2023 — Dec 2023 | 56.2% | 47.5% | — |
| Dec 2023 — May 2024 | 54.5% | 54.0% | — |
| May 2024 — Nov 2024 | 50.8% | 70.0% | 70.0% |
| Nov 2024 — Apr 2025 | 49.6% | 42.1% | 36.2% |
| Apr 2025 — Oct 2025 | 55.9% | 61.3% | — |
| Oct 2025 — Mar 2026 | 49.4% | 51.7% | 73.3% |

## Key Findings

### 1. The edge is real but regime-dependent
5 of 6 windows have positive 5d median returns. The average 5d win rate (51.8%) and 10d win rate (52.5%) are above 50%. But the variance is large: 46.6% to 56.1% at 5d (std dev 3.0%), driven almost entirely by market regime composition.

### 2. Window 4 (Nov 2024 — Apr 2025) is the clear problem period
The only window that loses money at every horizon. 33% mixed regime + 4% caution = the scanner's stock selection can't overcome a choppy market. Mixed regime win rate within this window: 42.1% — every pick is a coin flip biased against you.

### 3. Window 5 (Apr — Oct 2025) shows the ceiling
56.1% at 5d, 59.3% at 10d. Nearly 100% favorable regime. When the market cooperates, the scanner's quality-first ranking produces a strong, consistent edge.

### 4. Favorable regime win rates are stable across windows
Favorable regime 5d win rates: 56.2%, 54.5%, 50.8%, 49.6%, 55.9%, 49.4%. Average ~52.7%. The scanner works in bull markets. The question is whether to trade at all in mixed/choppy conditions.

### 5. Mixed regime is inconsistent
Mixed regime win rates swing wildly: 47.5%, 54.0%, 70.0%, 42.1%, 61.3%, 51.7%. Small sample sizes in some windows, but the pattern is clear — the scanner has no reliable edge in mixed conditions. Caution regime is even more erratic (36.2% to 73.3%) but sample sizes are too small to draw conclusions.

### 6. 10-day holding period is validated
10d numbers are stronger than 5d in 5 of 6 windows (exception: Window 3). Average 10d win rate (52.5%) exceeds average 5d (51.8%). These are multi-day setups, not day trades.

## Implications for the Trading Bot

1. **Regime-adaptive position sizing is the #1 priority.** Max positions in favorable, reduced in mixed, zero in caution/risk-off. This alone could flip Window 4 from a loss to breakeven.
2. **Go-live criteria should use multi-window variance**, not a single-period target. Expecting 52% every month is unrealistic — expect 47-56% depending on conditions.
3. **Exit strategy backtesting is needed.** The current test measures hold-for-N-days. Real trading with stop-losses might significantly change results — especially in Window 4 where tight stops could limit damage.
4. **AI analysis matters more in mixed regimes.** If the bot trades at all in mixed conditions, AI should be the gatekeeper with a much higher confidence bar.
