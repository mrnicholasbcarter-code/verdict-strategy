"""Verdict Strategy Provider: bounded evaluation input, typed evidenced decision.

The engine answers "may this strategy proceed?"; a Verdict runtime needs that
answer in a portable shape it can gate on and audit later.  This adapter is
that boundary.  It accepts a validated request, evaluates it entirely
in-process (no network I/O on the hot path), and returns the authoritative
decision together with per-gate outcomes, the schema version, latency
telemetry, and a deterministic strategy receipt.

Two properties are load-bearing:

* Invalid input is rejected at the boundary, not deep in a gate.  Non-finite
  numbers, wrong types, and empty identifiers raise
  :class:`StrategyProviderError` before any gate runs.
* Advisory data cannot weaken hard policy.  A request may carry an
  ``advisory`` mapping (hints from strategy or operator tooling); it is
  recorded in the receipt for audit but is structurally unreachable by the
  gates, so nothing an advisor says can turn a rejection into an approval.
"""

from __future__ import annotations

import math
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .evaluator import OPERATORS, SERIES_OPERATORS, FeatureEvaluator
from .gate import EVMetrics, ExpectedValueGate
from .provider_receipts import SCHEMA_VERSION, build_strategy_receipt

__all__ = [
    "PROVIDER_API_VERSION",
    "SCHEMA_VERSION",
    "EVOutcome",
    "RuleOutcome",
    "StrategyProvider",
    "StrategyProviderError",
    "StrategyProviderRequest",
    "StrategyProviderResult",
]

PROVIDER_API_VERSION = 1


class StrategyProviderError(ValueError):
    """Raised when a request fails boundary validation.

    Carries the offending field name so callers can report precisely which
    input was malformed without parsing the message.
    """

    def __init__(self, field_name: str, message: str) -> None:
        self.field_name = field_name
        super().__init__(f"{field_name}: {message}")


def _require_finite(name: str, value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise StrategyProviderError(name, f"expected a real number, got {type(value).__name__}")
    number = float(value)
    if not math.isfinite(number):
        raise StrategyProviderError(name, f"must be finite, got {number!r}")
    return number


def _require_identifier(name: str, value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise StrategyProviderError(name, "expected a non-empty string")
    return value


def _require_rules(name: str, value: Any) -> tuple[dict[str, Any], ...]:
    """Validate the rule list structurally so no gate meets a half-formed rule.

    ``evaluate_compound`` raises :class:`KeyError` on a rule missing its
    threshold and :class:`ValueError` on an unknown operator — deep inside the
    evaluator.  Catching the shape here keeps the boundary contract honest:
    a request that exists is one the engine can evaluate.
    """
    if not isinstance(value, (list, tuple)):
        raise StrategyProviderError(name, "expected a sequence of rule mappings")
    rules: list[dict[str, Any]] = []
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            raise StrategyProviderError(
                name, f"rule {index} is {type(item).__name__}, expected a mapping"
            )
        for key in ("feature", "operator", "threshold"):
            if key not in item:
                raise StrategyProviderError(name, f"rule {index} is missing {key!r}")
        for key in ("feature", "operator"):
            if not isinstance(item[key], str) or not item[key].strip():
                raise StrategyProviderError(
                    name, f"rule {index} {key!r} must be a non-empty string"
                )
        if item["operator"] not in OPERATORS and item["operator"] not in SERIES_OPERATORS:
            raise StrategyProviderError(
                name, f"rule {index} operator {item['operator']!r} is not supported"
            )
        rules.append(dict(item))
    return tuple(rules)


def _require_mapping(name: str, value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise StrategyProviderError(name, "expected a mapping")
    return dict(value)


@dataclass(frozen=True, slots=True)
class StrategyProviderRequest:
    """A bounded, fully validated strategy evaluation request.

    Construction is the validation boundary: a request that exists is a
    request the engine can safely evaluate.
    """

    run_id: str
    feature_rules: tuple[dict[str, Any], ...] = ()
    features: dict[str, Any] = field(default_factory=dict)
    predicted_win_prob: float = 0.0
    current_contract_price_cents: float = 0.0
    payout_cents: float = 100.0
    exchange_fee_pct: float = 0.07
    bankroll: float = 1.0
    minimum_ev_cents: float = 0.0
    current_time: datetime | None = None
    # Hints only.  Recorded for audit, never consulted by any gate.
    advisory: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_id", _require_identifier("run_id", self.run_id))
        object.__setattr__(
            self,
            "feature_rules",
            _require_rules("feature_rules", self.feature_rules),
        )
        object.__setattr__(
            self,
            "features",
            _require_mapping("features", self.features),
        )
        for name in (
            "predicted_win_prob",
            "current_contract_price_cents",
            "payout_cents",
            "exchange_fee_pct",
            "bankroll",
            "minimum_ev_cents",
        ):
            object.__setattr__(self, name, _require_finite(name, getattr(self, name)))
        if self.current_time is not None and not isinstance(self.current_time, datetime):
            raise StrategyProviderError("current_time", "expected a datetime or None")
        if self.advisory is not None and not isinstance(self.advisory, Mapping):
            raise StrategyProviderError("advisory", "expected a mapping or None")


@dataclass(frozen=True, slots=True)
class RuleOutcome:
    """One feature rule's independent verdict on the request."""

    feature: str
    operator: str
    approved: bool


@dataclass(frozen=True, slots=True)
class EVOutcome:
    """Expected value gate's independent verdict."""

    gate: str
    approved: bool
    reason_code: str
    expected_value: float
    kelly_fraction: float
    recommended_size: float


@dataclass(frozen=True, slots=True)
class StrategyProviderResult:
    """The portable decision a Verdict runtime gates on."""

    approved: bool
    reason_code: str
    rule_outcomes: tuple[RuleOutcome, ...]
    ev_outcome: EVOutcome
    schema_version: str
    elapsed_us: int
    receipt: Mapping[str, Any]
    api_version: int = PROVIDER_API_VERSION


def _gate_report(request: StrategyProviderRequest) -> tuple[RuleOutcome, ...]:
    """Run every feature rule independently for the audit report.

    The authoritative decision short-circuits on first failure; the report
    deliberately does not, so an auditor sees each rule's own verdict rather
    than only the first tripwire.
    """
    outcomes = []
    for rule in request.feature_rules:
        feat_name = rule["feature"]
        op_str = rule["operator"]
        threshold = rule["threshold"]

        if op_str in {"crosses_above", "crosses_below", "zscore", "rolling_corr", "rank"}:
            # Series operator
            series = request.features.get("series", {}).get(feat_name, [])
            if (
                not series
                and feat_name in request.features
                and isinstance(request.features[feat_name], (list, tuple))
            ):
                series = request.features[feat_name]
            if len(series) < 2:
                outcomes.append(RuleOutcome(feature=feat_name, operator=op_str, approved=False))
                continue
            try:
                approved = FeatureEvaluator.evaluate_rule(
                    series, op_str, threshold, features=request.features, feat_name=feat_name
                )
            except (ValueError, KeyError, TypeError):
                approved = False
        else:
            # Scalar operator
            if feat_name not in request.features:
                outcomes.append(RuleOutcome(feature=feat_name, operator=op_str, approved=False))
                continue
            val = request.features[feat_name]
            try:
                approved = FeatureEvaluator.evaluate_rule(val, op_str, threshold)
            except (ValueError, KeyError, TypeError):
                approved = False
        outcomes.append(RuleOutcome(feature=feat_name, operator=op_str, approved=approved))
    return tuple(outcomes)


class StrategyProvider:
    """In-process adapter from a Verdict runtime onto the strategy engine."""

    def evaluate(self, request: StrategyProviderRequest) -> StrategyProviderResult:
        if not isinstance(request, StrategyProviderRequest):
            raise StrategyProviderError("request", "expected a StrategyProviderRequest")

        start_ns = time.perf_counter_ns()

        # Gate 1: Feature rules (short-circuit on first failure)
        rules_approved = True
        for rule in request.feature_rules:
            feat_name = rule["feature"]
            op_str = rule["operator"]
            threshold = rule["threshold"]

            if op_str in {"crosses_above", "crosses_below", "zscore", "rolling_corr", "rank"}:
                series = request.features.get("series", {}).get(feat_name, [])
                if (
                    not series
                    and feat_name in request.features
                    and isinstance(request.features[feat_name], (list, tuple))
                ):
                    series = request.features[feat_name]
                if len(series) < 2:
                    rules_approved = False
                    break
                if not FeatureEvaluator.evaluate_rule(
                    series, op_str, threshold, features=request.features, feat_name=feat_name
                ):
                    rules_approved = False
                    break
            else:
                if feat_name not in request.features:
                    rules_approved = False
                    break
                val = request.features[feat_name]
                if not FeatureEvaluator.evaluate_rule(val, op_str, threshold):
                    rules_approved = False
                    break

        # Gate 2: EV gate
        try:
            ev_metrics = ExpectedValueGate.calculate_ev_metrics(
                predicted_win_prob=request.predicted_win_prob,
                current_contract_price_cents=request.current_contract_price_cents,
                payout_cents=request.payout_cents,
                exchange_fee_pct=request.exchange_fee_pct,
                bankroll=request.bankroll,
            )
            ev_approved = ev_metrics.expected_value >= request.minimum_ev_cents
        except ValueError:
            ev_approved = False
            ev_metrics = EVMetrics(
                expected_value=float("-inf"),
                kelly_fraction=0.0,
                recommended_size=0.0,
                profitable=False,
            )

        approved = rules_approved and ev_approved
        reason_code = "OK" if approved else "ERR_EVALUATION_FAILED"

        rule_outcomes = _gate_report(request)
        ev_outcome = EVOutcome(
            gate="evaluate_expected_value",
            approved=ev_approved,
            reason_code="OK" if ev_approved else "ERR_EXPECTED_VALUE",
            expected_value=ev_metrics.expected_value,
            kelly_fraction=ev_metrics.kelly_fraction,
            recommended_size=ev_metrics.recommended_size,
        )
        elapsed_us = (time.perf_counter_ns() - start_ns) // 1000

        outcome = "approved" if approved else "rejected"
        receipt = build_strategy_receipt(
            run_id=request.run_id,
            inputs={
                "feature_rules": list(request.feature_rules),
                "features": dict(request.features),
                "predicted_win_prob": request.predicted_win_prob,
                "current_contract_price_cents": request.current_contract_price_cents,
                "payout_cents": request.payout_cents,
                "exchange_fee_pct": request.exchange_fee_pct,
                "bankroll": request.bankroll,
                "minimum_ev_cents": request.minimum_ev_cents,
                "current_time": request.current_time.isoformat() if request.current_time else None,
                "advisory": dict(request.advisory) if request.advisory else None,
            },
            config={
                "schema_version": SCHEMA_VERSION,
            },
            outcome=outcome,
            evidence_refs=(),
            provenance={},
            details={
                "advisory": dict(request.advisory) if request.advisory else None,
                "reason_code": reason_code,
                "rule_outcomes": [
                    {"feature": r.feature, "operator": r.operator, "approved": r.approved}
                    for r in rule_outcomes
                ],
                "ev_outcome": {
                    "gate": ev_outcome.gate,
                    "approved": ev_outcome.approved,
                    "reason_code": ev_outcome.reason_code,
                    "expected_value": ev_outcome.expected_value,
                    "kelly_fraction": ev_outcome.kelly_fraction,
                    "recommended_size": ev_outcome.recommended_size,
                },
                "api_version": PROVIDER_API_VERSION,
            },
        )

        return StrategyProviderResult(
            approved=approved,
            reason_code=reason_code,
            rule_outcomes=rule_outcomes,
            ev_outcome=ev_outcome,
            schema_version=SCHEMA_VERSION,
            elapsed_us=elapsed_us,
            receipt=receipt,
        )
