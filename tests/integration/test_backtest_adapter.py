"""Cross-package checks for the installed backtest-harness boundary."""

import pytest

SAMPLE_RETURNS = (0.04, -0.02, 0.03, -0.05, 0.06, 0.01, -0.03, 0.05, -0.01, 0.02, 0.03, -0.04)


def _run(seed: int) -> dict:
    backtest_harness = pytest.importorskip("backtest_harness")
    return backtest_harness.run_counterfactual(
        run_id="strategy-adapter",
        trade_returns=SAMPLE_RETURNS,
        starting_equity=1_000.0,
        seed=seed,
        dataset_ref="synthetic:strategy-adapter-v1",
        num_simulations=100,
        trades_per_sim=len(SAMPLE_RETURNS),
        walk_forward_splits=3,
    )


@pytest.mark.integration
def test_backtest_harness_public_adapter() -> None:
    """Use only the installed package surface when the sibling package is present."""
    evidence = _run(seed=20_260_713)

    assert evidence["receipt"]["provider"] == "verdict-backtest"
    assert evidence["receipt"]["outcome"] == "success"
    monte_carlo = evidence["results"]["monte_carlo"]
    assert monte_carlo["p05_equity"] <= monte_carlo["p50_equity"] <= monte_carlo["p95_equity"]
    assert 0.0 <= monte_carlo["prob_ruin"] <= 1.0


@pytest.mark.integration
def test_backtest_harness_adapter_is_reproducible() -> None:
    """The same seed must give the same evidence hash across the package boundary."""
    assert _run(seed=7)["results_hash"] == _run(seed=7)["results_hash"]
