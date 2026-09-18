"""Derivation must match vectors/derive.json and js/derive.mjs on every published vector."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from quantum_launch.derive import DerivationError, canonical, plan_hash, salt_from_bitstring

ROOT = Path(__file__).resolve().parents[1]
VECTORS = json.loads((ROOT / "vectors" / "derive.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("row", VECTORS["salt"], ids=lambda r: r["bitstring"])
def test_salt_vector(row: dict) -> None:
    assert salt_from_bitstring(row["bitstring"]) == row["salt"]
    assert salt_from_bitstring(row["bitstring"]) == salt_from_bitstring(row["bitstring"])


@pytest.mark.parametrize("bad", VECTORS["saltRejected"] + ["0" * 257, "01 11"])
def test_salt_rejects_non_bitstring(bad: str) -> None:
    with pytest.raises(DerivationError, match="measured bitstring"):
        salt_from_bitstring(bad)


@pytest.mark.parametrize("row", VECTORS["planHash"], ids=lambda r: r["name"])
def test_plan_hash_vector(row: dict) -> None:
    assert plan_hash(row["plan"]) == row["hash"]


def test_plan_hash_ignores_key_order_not_values() -> None:
    a = {"chainId": 56, "token": {"name": "QKEY", "symbol": "QKEY"}, "tax": "0"}
    b = {"tax": "0", "token": {"symbol": "QKEY", "name": "QKEY"}, "chainId": 56}
    assert plan_hash(a) == plan_hash(b)
    assert plan_hash(a) != plan_hash({**a, "tax": "1"})
    assert plan_hash(a) != plan_hash({**a, "token": {"name": "QKEY", "symbol": "QKEY2"}})


def test_array_order_matters_null_is_not_missing() -> None:
    assert plan_hash({"a": [1, 2]}) != plan_hash({"a": [2, 1]})
    assert plan_hash({"a": None}) != plan_hash({})
    assert canonical({"a": None}) == '{"a":null}'
    assert canonical({}) == "{}"


def test_canonical_sorts_nested_keys() -> None:
    assert canonical({"z": 1, "a": {"d": 2, "c": 3}}) == '{"a":{"c":3,"d":2},"z":1}'
