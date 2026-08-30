"""Boundary conformance against verdict-core's provider receipt contract (ADR-021)."""

from __future__ import annotations

import verdict.provider_receipts as verdict_receipts

from edge_mining_framework.provider_receipts import build_strategy_receipt, canonical_hash


def _receipt() -> dict[str, object]:
    return build_strategy_receipt(
        run_id="conformance-1",
        inputs={"probability": 0.58, "price_cents": 42, "features": {"rsi": 30.5}},
        config={"minimum_ev_cents": 1.0, "exchange_fee_pct": 0.07},
        outcome="approved",
        provenance={"source": "fixture", "authority": "observed"},
        evidence_refs=(canonical_hash({"evidence": "strategy-conformance"}),),
        details={"advisory_note": "audit-only"},
    )


def test_canonical_hash_matches_core() -> None:
    payload = {"b": [1, 2.5, "x"], "a": {"nested": True, "n": None}}
    assert canonical_hash(payload) == verdict_receipts.canonical_hash(payload)


def test_receipt_round_trips_through_core_provider_receipt() -> None:
    receipt = _receipt()
    core_receipt = verdict_receipts.ProviderReceipt.from_dict(receipt)
    assert core_receipt.to_dict() == receipt
