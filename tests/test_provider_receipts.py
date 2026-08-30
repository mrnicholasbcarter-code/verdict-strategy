"""Receipt contract tests mirroring verdict-core's conformance template (ADR-021)."""

from __future__ import annotations

import pytest

from edge_mining_framework.provider_receipts import (
    PROVIDER_VERSION,
    SCHEMA_VERSION,
    build_strategy_receipt,
    canonical_hash,
)


def test_receipt_is_deterministic_and_hashes_inputs() -> None:
    receipt = build_strategy_receipt(
        run_id="run-1",
        inputs={"value": 1, "name": "sample"},
        config={"threshold": 0.5},
        outcome="approved",
        provenance={"source": "fixture", "authority": "observed"},
        evidence_refs=("evidence-1",),
        details={"approved": True},
    )
    same = build_strategy_receipt(
        run_id="run-1",
        inputs={"name": "sample", "value": 1},
        config={"threshold": 0.5},
        outcome="approved",
        provenance={"source": "fixture", "authority": "observed"},
        evidence_refs=("evidence-1",),
        details={"approved": True},
    )

    assert receipt == same
    assert receipt["inputs_hash"].startswith("sha256:")
    assert receipt["config_hash"].startswith("sha256:")
    assert receipt["schema_version"] == SCHEMA_VERSION
    assert receipt["provider"] == "verdict-edge"
    assert receipt["provider_version"] == PROVIDER_VERSION


def test_receipt_rejects_sensitive_metadata() -> None:
    with pytest.raises(ValueError, match="sensitive"):
        build_strategy_receipt(
            run_id="run-1",
            inputs={},
            config={},
            outcome="unknown",
            provenance={"api_key": "must-not-persist"},
        )
    with pytest.raises(ValueError, match="sensitive"):
        build_strategy_receipt(
            run_id="run-1",
            inputs={},
            config={},
            outcome="unknown",
            details={"nested": [{"Token": "x"}]},
        )


@pytest.mark.parametrize("field", ["access_token", "client-secret", "private_key"])
def test_receipt_rejects_common_sensitive_field_names(field: str) -> None:
    with pytest.raises(ValueError, match="sensitive"):
        build_strategy_receipt(
            run_id="run-1",
            inputs={},
            config={},
            outcome="unknown",
            provenance={field: "must-not-persist"},
        )


def test_receipt_rejects_empty_identifiers() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        build_strategy_receipt(run_id="  ", inputs={}, config={}, outcome="approved")
    with pytest.raises(ValueError, match="non-empty"):
        build_strategy_receipt(run_id="run-1", inputs={}, config={}, outcome="")


def test_canonical_hash_is_order_invariant_and_strict() -> None:
    assert canonical_hash({"a": 1, "b": 2}) == canonical_hash({"b": 2, "a": 1})
    assert canonical_hash([1.5, "x"]).startswith("sha256:")
    with pytest.raises(TypeError):
        canonical_hash(object())
    with pytest.raises(ValueError, match="JSON"):
        canonical_hash({"value": float("nan")})
    with pytest.raises(ValueError, match="JSON"):
        canonical_hash({"value": float("inf")})
    with pytest.raises((TypeError, ValueError), match=r"JSON|string"):
        canonical_hash({1: "silently-coerced-key"})


def test_receipt_rejects_nonportable_metadata_and_evidence_refs() -> None:
    with pytest.raises((TypeError, ValueError), match="JSON"):
        build_strategy_receipt(
            run_id="run-1",
            inputs={},
            config={},
            outcome="unknown",
            provenance={"nested": object()},
        )
    with pytest.raises(ValueError, match="evidence_refs"):
        build_strategy_receipt(
            run_id="run-1",
            inputs={},
            config={},
            outcome="unknown",
            evidence_refs=(" ",),
        )


@pytest.mark.parametrize("field", ["provenance", "details"])
def test_receipt_rejects_non_object_metadata(field: str) -> None:
    kwargs = {field: []}
    with pytest.raises(ValueError, match="JSON object"):
        build_strategy_receipt(
            run_id="run-1",
            inputs={},
            config={},
            outcome="unknown",
            **kwargs,  # type: ignore[arg-type]
        )


def test_receipt_metadata_is_detached_from_caller_mutation() -> None:
    provenance = {"nested": {"source": "fixture"}}
    receipt = build_strategy_receipt(
        run_id="run-1",
        inputs={},
        config={},
        outcome="unknown",
        provenance=provenance,
    )

    provenance["nested"]["api_key"] = "injected-after-build"

    assert receipt["provenance"] == {"nested": {"source": "fixture"}}
