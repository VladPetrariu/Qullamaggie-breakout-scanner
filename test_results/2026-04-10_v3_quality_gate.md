# Backtest Results - 2026-04-10 v3 (ATR + quality gate ranking)

## What changed from v1 (original)
- Primary sort key: ATR compression (was catalyst freshness)
- Quality gate: stocks must have uptrend (EMA stack >= weak), RS >= 20, volume ratio >= 0.1
- Removed vol_ratio_50d from quality count (anti-predictive in v1)
- Post-catalyst cooldown penalty (fresh catalyst + loose ATR)
- Extension penalty (>2 ABR above breakout level)

## What changed from v2 (ATR-only, no gate)
- Added quality gate requiring minimum uptrend, RS, and volume
- v2 selected 59.4% stocks with no uptrend — v3 selects 0%

## Overall Returns (Top 20 picks per day)

| Horizon | N | Win Rate | Avg Return | Median Return | Best | Worst |
|---------|---|----------|------------|---------------|------|-------|
| 1 day | 2,400 | 46.2% | -0.11% | +0.00% | +40.23% | -22.96% |
| 3 day | 2,400 | 49.1% | -0.42% | +0.00% | +49.56% | -85.62% |
| 5 day | 2,399 | **51.4%** | -0.30% | **+0.05%** | +103.72% | -87.32% |
| 10 day | 2,397 | **53.0%** | -0.48% | **+0.14%** | +108.60% | -91.19% |

## Comparison vs v1 (original ranking)

| Metric (5d) | v1 (freshness-first) | v3 (ATR + gate) | Change |
|-------------|---------------------|-----------------|--------|
| Win Rate | 45.9% | 51.4% | **+5.5pp** |
| Avg Return | -0.60% | -0.30% | **+0.30pp** |
| Median Return | -0.64% | +0.05% | **+0.69pp** |
| Best | +710.34% | +103.72% | Outliers tamed |
| Worst | -87.16% | -87.32% | Similar |

## Top 5 vs Top 20

| Horizon | Top 5 Avg | Top 20 Avg | Top 5 Win% | Top 20 Win% |
|---------|-----------|------------|------------|-------------|
| 1 day | -0.29% | -0.11% | 42.2% | 46.2% |
| 3 day | -1.10% | -0.42% | 47.2% | 49.1% |
| 5 day | -1.20% | -0.30% | 50.7% | 51.4% |
| 10 day | -1.68% | -0.48% | 54.2% | 53.0% |

Top 5 still underperforms top 20, suggesting the very tightest ATR stocks (which rank 1-5) may be too tight. A potential improvement: cap ATR compression at a floor (e.g., 0.3) so extremely tight stocks don't get extra ranking credit.

## Returns by Market Regime (5-day horizon)

| Regime | N | Avg Return | Win Rate |
|--------|---|------------|----------|
| Favorable | 1,900 | -0.20% | 49.3% |
| Mixed | 419 | -0.95% | 57.8% |
| Caution | 80 | +0.68% | 67.5% |

Favorable regime nearly break-even (-0.20% vs -0.67% in v1). Mixed regime win rate jumped to 57.8%.

## Factor Quintile Analysis (5-day returns)

| Factor | Q1 | Q5 | Spread | vs v1 |
|--------|----|----|--------|-------|
| hh_hl_pct | +0.60% | -1.46% | **+2.06%** | was +0.90% |
| vol_ratio_50d | +0.06% | -2.43% | **+2.49%** | was -4.78% (inverted!) |
| rs_percentile | -0.11% | -0.39% | +0.28% | was +0.42% |
| freshness_score | -1.01% | +1.30% | -2.31% | was -4.84% (less extreme) |
| atr_compression | -0.92% | +0.86% | -1.78% | was +3.05% (inverted within gate) |

Key observations:
- **hh_hl_pct became the strongest predictor** (+2.06% spread) — within quality-gated stocks, good price structure matters most
- **vol_ratio_50d flipped** from anti-predictive to positive — within uptrend stocks, moderate volume is good, very low volume is bad
- **atr_compression inverted** within the gated pool — the gate already selects tight stocks, so within that group, moderate tightness beats extreme tightness
- **Freshness still anti-predictive** but less extreme (-2.31% vs -4.84%)

## Key Takeaways

1. **Quality gate was the critical fix.** ATR compression alone selected dead stocks; requiring uptrend + RS + volume context turned it into a useful signal.
2. **Median returns flipped positive** at 5d and 10d. Win rate crossed 50% for the first time.
3. **Average returns still slightly negative** — likely pulled down by outlier losses (winsorization would help).
4. **Top 5 underperforms Top 20** — extreme tightness within the quality pool may indicate stagnation rather than coiling.
5. **HH/HL price structure is the next factor to emphasize** — strongest quintile spread within the gated pool.

## Recommended Next Steps

1. Floor ATR compression at 0.3 — prevent very-tight-but-stagnant stocks from ranking first
2. Emphasize hh_hl_pct in ranking — strongest predictor within quality-gated stocks
3. Winsorize returns at +/-30% for cleaner analysis
4. SPY benchmark comparison
