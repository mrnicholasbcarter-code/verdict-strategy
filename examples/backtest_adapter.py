"""Use the installed backtest-harness package through its public API.

This example intentionally has no sibling-path or ``sys.path`` fallback. Install
the dependency first, then run the example from this repository::

    uv pip install -e ../verdict-backtest
    uv run python examples/backtest_adapter.py
"""

from __future__ import annotations

from backtest_harness import run_counterfactual

# Small illustrative per-trade return series (fractions). Synthetic, not market data.
SAMPLE_RETURNS = (0.04, -0.02, 0.03, -0.05, 0.06, 0.01, -0.03, 0.05, -0.01, 0.02, 0.03, -0.04)


def main() -> None:
    """Print a small deterministic report from the installed backtest package."""
    evidence = run_counterfactual(
        run_id="strategy-adapter-example",
        trade_returns=SAMPLE_RETURNS,
        starting_equity=1_000.0,
        seed=20_260_713,
        dataset_ref="synthetic:strategy-example-v1",
        num_simulations=1_000,
        trades_per_sim=len(SAMPLE_RETURNS),
        walk_forward_splits=3,
    )
    results = evidence["results"]
    monte_carlo = results["monte_carlo"]

    print("Installed backtest-harness adapter")
    print(
        f"  Provider: {evidence['receipt']['provider']} {evidence['receipt']['provider_version']}"
    )
    print(f"  P50 final equity: ${monte_carlo['p50_equity']:.2f}")
    print(f"  Risk of ruin: {monte_carlo['prob_ruin']:.2%}")
    print(f"  Max drawdown: {results['tearsheet']['max_drawdown']:.2%}")
    print(f"  Results hash: {evidence['results_hash']}")


if __name__ == "__main__":
    main()
