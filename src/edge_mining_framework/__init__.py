"""
Edge Mining Framework - Prediction Market Alpha Engine

An agnostic signal feature evaluator and EV payout gating engine for
prediction markets. This library evaluates live orderbook/alpha features
against strict compound thresholds and mathematically blocks deployment
unless the Expected Value (EV) exceeds friction parameters.

Architecture:
    FeatureEvaluator -> ExpectedValueGate -> Execution Decision

    Pipeline -> FeatureEvaluator: evaluate_compound(features: Dict, rules: List[Dict])
    If Signal Miss: FeatureEvaluator -> Pipeline: False (Abort)
    If Signal Match: FeatureEvaluator -> ExpectedValueGate: is_profitable_after_fees()
    If Negative EV: ExpectedValueGate -> Pipeline: False (Friction too high)
    If Positive Alpha: ExpectedValueGate -> Pipeline: True (Execute Order)

Modules:
    evaluator: FeatureEvaluator - compound rule evaluation with fail-fast logic
    gate: ExpectedValueGate - EV calculation with fee-aware gating

Example:
    >>> from edge_mining_framework import FeatureEvaluator, ExpectedValueGate
    >>> features = {"rsi": 30.5, "volume_spike": True}
    >>> rules = [
    ...     {"feature": "rsi", "operator": "<", "threshold": 40.0},
    ...     {"feature": "volume_spike", "operator": "==", "threshold": True}
    ... ]
    >>> if FeatureEvaluator.evaluate_compound(features, rules):
    ...     if ExpectedValueGate.is_profitable_after_fees(0.55, 45):
    ...         print("Execute trade")
    Execute trade

Supported Operators (O(1) via operator module):
    ==, !=, >, <, >=, <=, in_range, in_set
"""

from edge_mining_framework.evaluator import FeatureEvaluator
from edge_mining_framework.gate import ExpectedValueGate
from edge_mining_framework.provider_receipts import build_strategy_receipt

__version__ = "0.1.0"
__author__ = "edge-mining-framework contributors"
__all__ = ["ExpectedValueGate", "FeatureEvaluator", "build_strategy_receipt"]
