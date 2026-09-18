"""Salt and plan-hash derivation.

Public authority in this repository: js/derive.mjs and vectors/derive.json.

    salt     = keccak256(utf8_bytes(bitstring))   # bitstring like "0111", MSB first
    planHash = keccak256(utf8(canonical_json(plan)))  # keys sorted, recursively

This is not SHA3-256. Ethereum keccak256 is the pre-NIST sponge. hashlib.sha3_256
is the wrong function and will not match the published vectors.
"""

from __future__ import annotations

import json
import math
import re
from typing import Any

from .errors import QuantumLaunchError

# One QPU shot is at most 64 bits. A launch spec may concatenate shots (≤256).
BITSTRING_PATTERN = re.compile(r"^[01]{2,256}$")
SHOT_WIDTH_MAX = 64
_HEX64 = re.compile(r"^0x[0-9a-f]{64}$")


class DerivationError(QuantumLaunchError):
    """Input is not a measured bitstring or a canonicalisable plan value."""


def keccak256(data: bytes) -> str:
    """Return 0x-prefixed keccak256 of `data`."""
    try:
        from Crypto.Hash import keccak
    except ImportError as exc:  # pragma: no cover - declared dependency
        raise ImportError(
            "pycryptodome is required for keccak256 (Ethereum, not SHA3-256)"
        ) from exc
    digest = keccak.new(digest_bits=256)
    digest.update(data)
    return "0x" + digest.hexdigest()


def _js_stringify_primitive(value: Any) -> str:
    """Match JavaScript JSON.stringify for non-object values.

    canonical() in js/derive.mjs ends at `JSON.stringify(value ?? null)`.
    """
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return "null"
        if value.is_integer() and abs(value) <= 9007199254740991:
            return str(int(value))
        return json.dumps(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    raise DerivationError(f"Plan value is not JSON-canonicalisable: {type(value).__name__}")


def canonical(value: Any) -> str:
    """Canonical JSON: object keys sorted recursively; array order preserved.

    Matches js/derive.mjs:

        if (Array.isArray(value)) return `[${value.map(canonical).join(',')}]`;
        if (value && typeof value === 'object') {
          return `{${Object.keys(value).sort().map(k =>
            `${JSON.stringify(k)}:${canonical(value[k])}`).join(',')}}`;
        }
        return JSON.stringify(value ?? null);
    """
    if isinstance(value, list):
        return "[" + ",".join(canonical(item) for item in value) + "]"
    if isinstance(value, dict):
        keys = sorted(value.keys(), key=lambda k: k if isinstance(k, str) else str(k))
        for key in keys:
            if not isinstance(key, str):
                raise DerivationError("Plan object keys must be strings")
        inner = ",".join(
            json.dumps(key, ensure_ascii=False) + ":" + canonical(value[key])
            for key in keys
        )
        return "{" + inner + "}"
    return _js_stringify_primitive(value)


def salt_from_bitstring(bitstring: str) -> str:
    """keccak256 of the UTF-8 bytes of the measured bitstring, e.g. "0111"."""
    if not isinstance(bitstring, str) or not BITSTRING_PATTERN.fullmatch(bitstring):
        raise DerivationError(f"Not a measured bitstring: {bitstring}")
    return keccak256(bitstring.encode("utf-8"))


def plan_hash(plan: Any) -> str:
    """keccak256 of the UTF-8 bytes of canonical(plan)."""
    return keccak256(canonical(plan).encode("utf-8"))


def is_bytes32(value: str) -> bool:
    return isinstance(value, str) and bool(_HEX64.fullmatch(value.lower()))
