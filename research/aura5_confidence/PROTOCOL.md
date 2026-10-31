# Aura 5.0 Signal Confidence — frozen research protocol

- Scope: public Bitget BTCUSDT USDT-M archive; no orders, accounts or Paper/Active43.
- Score version `AURA5_TECHNICAL_SCORE_V1_FROZEN`: trend 30, RSI/MACD momentum
  25, structure 20, volume 10, support/resistance 15. These are descriptive
  subjective weights **not learned probabilities**. Correlated evidence is capped.
- Score bins: 50–64 weak, 65–79 moderate, 80–100 strong; user threshold 50–100
  filters UI display, never risk/freshness/validation gates.
- Causal cutoff at completed candle. Historical entry no earlier than next open,
  initial zone ±0.5 ATR, stop beyond known S/R, illustrative target 2.5R;
  net R/R minimum 1.5 with conservative fee/spread/slippage/funding assumptions.
- Frozen partitions: July 2026 TRAIN, August VALIDATION, September–October 29
  REUSED_TEST. **No untouched holdout exists** because Aura already explored
  these bars. No thresholds or weights were fitted to replay outcomes.
- A maximum of one active hypothetical trade per frame/side; bins are scored at
  all closes; period boundaries never take exits from the next partition.
  Results are overlapping hypotheses across frames, not portfolio cashflows.
- Missing funding is modeled conservatively. Historical executable Bid/Ask and
  real fills unavailable. No calibrated probability or validated edge claim.

Reproduce from repo root with requirements installed:

```sh
python -m research.aura5_confidence.replay
```
