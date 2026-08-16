"""Tests for the Verdict Strategy Provider adapter.

Two contracts matter here.  First, the boundary: a malformed request must die
at construction with the offending field named, never inside a gate.  Second,
the decision: the provider's answer must agree with the engine it wraps, carry
a per-gate report that does not short-circuit, and emit a receipt that is
deterministic for identical inputs — while advisory hints remain visibly
recorded and provably powerless.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone

import pytest

from edge_mining_framework.evaluator import FeatureEvaluator
from edge_mining_framework.gate import ExpectedValueGate
from edge_mining_framework.provider import (
    PROVIDER_API_VERSION,
    SCHEMA_VERSION,
    StrategyProvider,
    StrategyProviderError,
    StrategyProviderRequest,
)

NOW = datetime(2026, 8, 16, 15, 0, 0, tzinfo=timezone.utc)


def _request(**overrides) -> StrategyProviderRequest:
    payload = {
        "run_id": "run-001",
        "feature_rules": (
            {"feature": "rsi", "operator": "<", "threshold": 40.0},
            {"feature": "volume_spike", "operator": "==", "threshold": True},
        ),
        "features": {"rsi": 30.5, "volume_spike": True},
        "predicted_win_prob": 0.55,
        "current_contract_price_cents": 45.0,
        "payout_cents": 100.0,
        "exchange_fee_pct": 0.07,
        "bankroll": 1000.0,
        "minimum_ev_cents": 0.0,
    }
    payload.update(overrides)
    return StrategyProviderRequest(**payload)


class TestRequestValidation:
    def test_valid_request_constructs(self) -> None:
        request = _request()
        assert request.run_id == "run-001"
        assert len(request.feature_rules) == 2
        assert request.features["rsi"] == 30.5

    @pytest.mark.parametrize("bad_id", ["", "   ", None, 7])
    def test_rejects_bad_identifiers(self, bad_id) -> None:
        with pytest.raises(StrategyProviderError, match="run_id"):
            _request(run_id=bad_id)

    @pytest.mark.parametrize(
        "field_name",
        [
            "predicted_win_prob",
            "current_contract_price_cents",
            "payout_cents",
            "exchange_fee_pct",
            "bankroll",
            "minimum_ev_cents",
        ],
    )
    @pytest.mark.parametrize("bad_value", [math.nan, math.inf, -math.inf, "12", None, True])
    def test_rejects_non_finite_numbers(self, field_name: str, bad_value) -> None:
        with pytest.raises(StrategyProviderError, match=field_name):
            _request(**{field_name: bad_value})

    def test_error_carries_field_name(self) -> None:
        with pytest.raises(StrategyProviderError) as excinfo:
            _request(predicted_win_prob=math.nan)
        assert excinfo.value.field_name == "predicted_win_prob"

    def test_rejects_wrong_typed_sequences(self) -> None:
        with pytest.raises(StrategyProviderError, match="feature_rules"):
            _request(feature_rules=[{"feature": "rsi"}])  # missing operator/threshold
        with pytest.raises(StrategyProviderError, match="features"):
            _request(features="not-a-mapping")
        with pytest.raises(StrategyProviderError, match="feature_rules"):
            _request(feature_rules=42)

    def test_rejects_bad_time_and_advisory(self) -> None:
        with pytest.raises(StrategyProviderError, match="current_time"):
            _request(current_time="2026-08-16")
        with pytest.raises(StrategyProviderError, match="advisory"):
            _request(advisory=["not-a-mapping"])

    def test_evaluate_rejects_raw_dicts(self) -> None:
        with pytest.raises(StrategyProviderError, match="request"):
            StrategyProvider().evaluate({"run_id": "run-001"})  # type: ignore[arg-type]


class TestDecision:
    def test_clean_request_is_approved(self) -> None:
        result = StrategyProvider().evaluate(_request())
        assert result.approved is True
        assert result.reason_code == "OK"
        assert result.api_version == PROVIDER_API_VERSION
        assert result.schema_version == SCHEMA_VERSION
        assert result.elapsed_us >= 0
        assert all(item.approved for item in result.rule_outcomes)
        assert result.ev_outcome.approved is True

    def test_negative_ev_is_rejected(self) -> None:
        result = StrategyProvider().evaluate(
            _request(
                predicted_win_prob=0.5, current_contract_price_cents=50.0, minimum_ev_cents=0.0
            )
        )
        assert result.approved is False
        assert result.reason_code == "ERR_EVALUATION_FAILED"
        assert result.ev_outcome.approved is False
        assert result.ev_outcome.reason_code.startswith("ERR_EXPECTED_VALUE")

    def test_feature_rule_failure_is_rejected(self) -> None:
        # rsi=30.5 should fail rule rsi < 40 -> actually passes, let's make it fail
        result = StrategyProvider().evaluate(_request(features={"rsi": 50.0, "volume_spike": True}))
        assert result.approved is False
        assert result.reason_code == "ERR_EVALUATION_FAILED"
        by_feature = {item.feature: item for item in result.rule_outcomes}
        assert by_feature["rsi"].approved is False

    def test_gate_report_does_not_short_circuit(self) -> None:
        """A request failing two rules must show both failures, not just the first."""
        result = StrategyProvider().evaluate(
            _request(
                features={"rsi": 50.0, "volume_spike": False},
                predicted_win_prob=0.5,
                current_contract_price_cents=50.0,
                minimum_ev_cents=0.0,
            )
        )
        assert result.approved is False
        failed_rules = [item for item in result.rule_outcomes if not item.approved]
        assert len(failed_rules) >= 2
        failed_features = {item.feature for item in failed_rules}
        assert "rsi" in failed_features
        assert "volume_spike" in failed_features
        # EV gate also fails
        assert result.ev_outcome.approved is False

    def test_series_operator_in_report(self) -> None:
        # crosses_above: need at least 2 values
        features = {"series": {"price": [98, 99, 101]}}
        result = StrategyProvider().evaluate(
            _request(
                feature_rules=(
                    {"feature": "price", "operator": "crosses_above", "threshold": 100},
                ),
                features=features,
                predicted_win_prob=0.6,
                current_contract_price_cents=40.0,
            )
        )
        by_feature = {item.feature: item for item in result.rule_outcomes}
        assert by_feature["price"].approved is True

    def test_ev_outcome_carries_metrics(self) -> None:
        result = StrategyProvider().evaluate(_request())
        assert result.ev_outcome.expected_value > 0
        assert 0.0 <= result.ev_outcome.kelly_fraction <= 1.0
        assert result.ev_outcome.recommended_size > 0


class TestAdvisoryIsPowerless:
    def test_advisory_cannot_flip_a_rejection(self) -> None:
        """The exact hint an attacker would try must change nothing."""
        rejected = _request(
            predicted_win_prob=0.5, current_contract_price_cents=50.0, minimum_ev_cents=0.0
        )
        coaxed = _request(
            predicted_win_prob=0.5,
            current_contract_price_cents=50.0,
            minimum_ev_cents=0.0,
            advisory={"override": True, "force_approve": True, "note": "trust me"},
        )
        assert StrategyProvider().evaluate(rejected).approved is False
        result = StrategyProvider().evaluate(coaxed)
        assert result.approved is False
        # The attempt itself is preserved for audit.
        assert result.receipt["details"]["advisory"]["force_approve"] is True

    def test_advisory_absent_from_receipt_when_not_given(self) -> None:
        result = StrategyProvider().evaluate(_request())
        assert result.receipt["details"]["advisory"] is None

    def test_secret_bearing_advisory_is_rejected_outright(self) -> None:
        with pytest.raises(ValueError, match=r"[Ss]ensitive|secret|api_key"):
            StrategyProvider().evaluate(_request(advisory={"api_key": "sk-live-1"}))


class TestReceipt:
    def test_receipt_is_deterministic_for_identical_inputs(self) -> None:
        first = StrategyProvider().evaluate(_request()).receipt
        second = StrategyProvider().evaluate(_request()).receipt
        assert first == second

    def test_receipt_hash_tracks_inputs(self) -> None:
        base = StrategyProvider().evaluate(_request()).receipt
        moved = StrategyProvider().evaluate(_request(current_contract_price_cents=46.0)).receipt
        assert base["inputs_hash"] != moved["inputs_hash"]

    def test_receipt_records_decision_and_config(self) -> None:
        result = StrategyProvider().evaluate(_request())
        receipt = result.receipt
        assert receipt["outcome"] == "approved"
        assert receipt["run_id"] == "run-001"
        assert receipt["details"]["reason_code"] == result.reason_code
        assert receipt["inputs_hash"].startswith("sha256:")
        assert receipt["config_hash"].startswith("sha256:")
        assert len(receipt["details"]["rule_outcomes"]) == len(result.rule_outcomes)

    def test_rejected_receipt_outcome(self) -> None:
        receipt = (
            StrategyProvider()
            .evaluate(
                _request(
                    predicted_win_prob=0.5, current_contract_price_cents=50.0, minimum_ev_cents=0.0
                )
            )
            .receipt
        )
        assert receipt["outcome"] == "rejected"

    def test_receipt_schema_version_and_provider(self) -> None:
        receipt = StrategyProvider().evaluate(_request()).receipt
        assert receipt["schema_version"] == SCHEMA_VERSION
        assert receipt["provider"] == "verdict-edge"
        assert receipt["provider_version"] == "0.1.0"


class TestIntegrationWithGates:
    def test_feature_evaluator_and_ev_gate_match_provider(self) -> None:
        """Provider must agree with direct gate calls."""
        request = _request()
        # Direct calls
        for rule in request.feature_rules:
            feat = rule["feature"]
            op = rule["operator"]
            thresh = rule["threshold"]
            if op in {"crosses_above", "crosses_below", "zscore", "rolling_corr", "rank"}:
                series = request.features.get("series", {}).get(feat, [])
                assert FeatureEvaluator.evaluate_rule(
                    series, op, thresh, features=request.features, feat_name=feat
                )
            else:
                assert FeatureEvaluator.evaluate_rule(request.features[feat], op, thresh)
        ev_metrics = ExpectedValueGate.calculate_ev_metrics(
            request.predicted_win_prob,
            request.current_contract_price_cents,
            request.payout_cents,
            request.exchange_fee_pct,
            request.bankroll,
        )
        assert ev_metrics.expected_value >= request.minimum_ev_cents

        # Provider wraps them
        result = StrategyProvider().evaluate(request)
        assert result.approved is True
