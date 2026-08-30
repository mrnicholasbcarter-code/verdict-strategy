"""Provider-neutral receipts for deterministic strategy evaluation."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from typing import Any

SCHEMA_VERSION = "1"
PROVIDER_VERSION = "0.1.0"


def canonical_hash(value: Any) -> str:
    """Hash JSON-compatible input using stable canonical serialization."""
    _validate_json(value)
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )
    return f"sha256:{hashlib.sha256(encoded.encode('utf-8')).hexdigest()}"


def build_strategy_receipt(
    *,
    run_id: str,
    inputs: Any,
    config: Any,
    outcome: str,
    evidence_refs: tuple[str, ...] = (),
    provenance: Mapping[str, Any] | None = None,
    details: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a deterministic, informational strategy-provider receipt."""
    if not run_id.strip() or not outcome.strip():
        raise ValueError("run_id and outcome must be non-empty")
    if provenance is not None and not isinstance(provenance, Mapping):
        raise ValueError("provenance must be a JSON object")
    if details is not None and not isinstance(details, Mapping):
        raise ValueError("details must be a JSON object")
    if any(not isinstance(ref, str) or not ref.strip() for ref in evidence_refs):
        raise ValueError("evidence_refs must contain non-empty strings")
    safe_provenance = _portable_copy(provenance or {})
    safe_details = _portable_copy(details or {})
    _reject_sensitive(safe_provenance)
    _reject_sensitive(safe_details)
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "provider": "verdict-edge",
        "provider_version": PROVIDER_VERSION,
        "inputs_hash": canonical_hash(inputs),
        "config_hash": canonical_hash(config),
        "outcome": outcome,
        "provenance": safe_provenance,
        "evidence_refs": list(evidence_refs),
        "details": safe_details,
    }


def _reject_sensitive(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if str(key).lower().replace("-", "_") in {
                "access_token",
                "api_key",
                "auth_token",
                "authorization",
                "bearer_token",
                "client_secret",
                "password",
                "private_key",
                "refresh_token",
                "secret",
                "token",
            }:
                raise ValueError(f"sensitive receipt field rejected: {key}")
            _reject_sensitive(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            _reject_sensitive(child)


def _validate_json(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if not isinstance(key, str):
                raise TypeError("JSON object keys must be strings")
            _validate_json(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            _validate_json(child)
    elif value is None or isinstance(value, (str, bool, int)):
        return
    elif isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("JSON numbers must be finite")
    else:
        raise TypeError("value must be JSON-compatible")


def _portable_copy(value: Any) -> Any:
    _validate_json(value)
    if isinstance(value, Mapping):
        return {key: _portable_copy(child) for key, child in value.items()}
    if isinstance(value, (list, tuple)):
        return [_portable_copy(child) for child in value]
    return value


__all__ = ["PROVIDER_VERSION", "SCHEMA_VERSION", "build_strategy_receipt", "canonical_hash"]
