# Phase 8 — Multi-Factor Combination Analysis (2026-04-10)

## Methodology
Tested all single factors, pairs (66), and trios (197) across 2,400 picks from the v4 backtest.
Minimum sample size: 50 picks. Returns winsorized at +/-30%. 5-day forward returns.

## Baseline
All 2,399 picks: win 51.2%, avg -0.33%, median +0.05%

## Key Finding: HH/HL Dominates Everything

**Every single top combo includes high_hh_hl (>= 50%).** It's the universal differentiator.

### Best Single Factor
- **high_hh_hl**: 57.5% win rate (n=670) — 6.3pp above baseline
- tight_atr alone: 51.4% (n=808) — barely above baseline despite being the current primary sort key

### Best Pairs
| Combo | N | Win% | Avg |
|-------|---|------|-----|
| high_hh_hl + high_vol | 62 | 61.3% | +0.61% |
| high_hh_hl + high_rs | 449 | **59.7%** | +0.64% |
| good_candle + high_hh_hl | 278 | 59.0% | +0.99% |
| ath_level + high_hh_hl | 418 | 58.6% | +0.95% |

Note: high_hh_hl + high_rs has n=449 — large sample, very reliable.

### Best Trios
| Combo | N | Win% | Avg |
|-------|---|------|-----|
| **flag_dryup + good_candle + high_hh_hl** | 141 | **63.8%** | **+1.54%** |
| flag_dryup + high_hh_hl + tight_atr | 133 | 61.7% | +0.19% |
| good_candle + high_hh_hl + tight_atr | 73 | 60.3% | +0.56% |
| has_pole + high_hh_hl + tight_atr | 143 | 60.1% | +0.29% |

Best trio: flag_dryup + good_candle + high_hh_hl at **63.8%** win rate, **+1.54%** avg return (n=141).

## Regime Analysis (Step 45)

### Best combo per regime:
| Regime | Best Combo | N | Win% | Avg |
|--------|-----------|---|------|-----|
| Favorable | flag_dryup + good_candle + high_hh_hl | 101/1900 | 59.4% | +1.76% |
| Mixed | ath_level + high_hh_hl | 58/420 | **79.3%** | +1.26% |
| Caution | ath_level | 39/80 | 71.8% | +1.13% |

Mixed regime is remarkable: ath_level + high_hh_hl = 79.3% win rate. In uncertain markets, stocks near ATH with good price structure are extremely reliable.

## Implications for Ranking

1. **ATR compression should NOT be the primary sort key.** It ranks 51.4% as a single factor — barely above baseline. It's useful as a filter but not as the primary differentiator.
2. **Quality count + HH/HL should be primary.** The combo data shows multi-factor setups work, and HH/HL is in every top combo.
3. **Recommended new sort key:** `quality_count → hh_hl_pct → atr → abr_dist` (currently: `atr → quality → abr_dist`)

## Anti-predictive factors (confirm)
- **has_pole alone:** 46.5% win rate — below baseline. Useful in combos but not alone.
- **good_candle alone:** 47.9% — same. Predictive only when combined with high_hh_hl.
- **flag_dryup alone:** 49.5% — same pattern.

These factors are *conditional predictors*: they work only when combined with good price structure (HH/HL).
