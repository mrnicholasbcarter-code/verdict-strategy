# Verdict Edge — Edge Mining Framework

> A small library for prediction-market signals. It evaluates compound feature rules, then approves a trade only if the expected value remains positive after exchange fees. It also reports a Kelly-sized position. The package is `verdict-edge`; the import is `edge_mining_framework`.

---

## What ships today

A small, dependency-light library (`numpy` only) with two stages and a receipt helper:

```
features (dict) ──▶ FeatureEvaluator.evaluate_compound(rules) ──▶ ExpectedValueGate ──▶ trade / no trade
                                                                        │
                                                   build_strategy_receipt (Verdict provider receipt)
```

| Component | What it does | Source |
|-----------|--------------|--------|
| `FeatureEvaluator` | AND-only compound rules with fail-fast short-circuit. Scalar operators `== != > < >= <= in_range in_set`; series operators `crosses_above crosses_below zscore rolling_corr rank`. No `eval()`. | `src/edge_mining_framework/evaluator.py` |
| `ExpectedValueGate` | Fee-aware expected value per contract, Kelly fraction, and recommended size for binary prediction-market contracts. | `src/edge_mining_framework/gate.py` |
| `build_strategy_receipt` / `canonical_hash` | Builds a Verdict provider receipt (ADR-021 shape). Conformance against `verdict-core` is tested in `tests/test_core_conformance.py`. | `src/edge_mining_framework/provider_receipts.py` |

The evaluator is data-source agnostic. It does not ingest market feeds, place orders, or
call exchange APIs; those belong to the caller. Risk limits live in
[`verdict-risk`](https://github.com/mrnicholasbcarter-code/verdict-risk), and Monte Carlo
validation lives in [`verdict-backtest`](https://github.com/mrnicholasbcarter-code/verdict-backtest).

### Principles

1. **Deterministic**: the same inputs give the same outputs.
2. **Friction-aware**: the EV gate subtracts the exchange fee before it approves a trade.
3. **Agnostic**: rules evaluate plain dictionaries. There are no exchange SDK imports.

---

## Quick start

The package is not published to PyPI. Install from source:

```bash
git clone https://github.com/mrnicholasbcarter-code/verdict-strategy.git
cd verdict-strategy
uv sync --extra dev
uv run python examples/gate_kalshi.py      # EV gate rejects / accepts two trades
uv run python examples/run_evaluator.py    # rules from examples/rules.yaml through both stages
uv run pytest -q
```

```python
from edge_mining_framework import ExpectedValueGate, FeatureEvaluator

features = {"rsi": 28.0, "vol_expansion": True}
rules = [
    {"feature": "rsi", "operator": "<", "threshold": 30},
    {"feature": "vol_expansion", "operator": "==", "threshold": True},
]

if FeatureEvaluator.evaluate_compound(features, rules):
    metrics = ExpectedValueGate.calculate_ev_metrics(
        predicted_win_prob=0.57,
        current_contract_price_cents=48,
        payout_cents=100,
        exchange_fee_pct=0.04,
        bankroll=500.0,
    )
    print(metrics.profitable, round(metrics.expected_value, 2), round(metrics.kelly_fraction, 4))
```

`examples/rules.yaml` shows the rule format, including series operators.
`examples/backtest_adapter.py` shows the optional hand-off to an installed `verdict-backtest`.

---

## Links

- **Verdict Core**: https://github.com/mrnicholasbcarter-code/verdict-core
- **Verdict Risk**: https://github.com/mrnicholasbcarter-code/verdict-risk
- **Verdict Backtest**: https://github.com/mrnicholasbcarter-code/verdict-backtest

---

## License

MIT — see [LICENSE](LICENSE)
