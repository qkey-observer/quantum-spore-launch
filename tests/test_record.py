"""Compact public-record refuses: identity, shot order, and launched-with-receipt."""

from __future__ import annotations

import pytest

from quantum_launch.derive import salt_from_bitstring
from quantum_launch.errors import RecordError
from quantum_launch.record import EMPTY_SPORES, normalize_spores, verify_derivation

JOB = {
    "id": "d3k91f-003",
    "device": "ibm_fez",
    "shots": 1024,
    "ranAt": "2026-09-17T10:00:00.000Z",
    "readoutError": 0.012,
    "circuitDepth": 14,
}
SPORE = {
    "shot": 4,
    "bitstring": "0111",
    "salt": "0x" + "ab" * 32,
    "address": "0x" + "cd" * 20,
    "status": "awaiting_launch",
    "predictedAt": "2026-09-17T10:05:00.000Z",
}
PLAN = {
    "chainId": 4663,
    "factoryAddress": "0x" + "11" * 20,
    "initiator": "0x" + "22" * 20,
    "planHash": "0x" + "33" * 32,
}


def record(**over):
    base = {"job": JOB, "plan": PLAN, "spores": [SPORE]}
    base.update(over)
    return base


def test_spore_without_job_is_refused() -> None:
    with pytest.raises(RecordError):
        normalize_spores({"job": None, "plan": None, "spores": [SPORE]})
    assert normalize_spores({"job": None, "plan": None, "spores": []}) == {
        "job": None,
        "plan": None,
        "spores": [],
    }


def test_shots_consumed_once_within_job() -> None:
    with pytest.raises(RecordError):
        normalize_spores(record(spores=[SPORE, dict(SPORE)]))
    with pytest.raises(RecordError):
        normalize_spores(record(spores=[{**SPORE, "shot": JOB["shots"] + 1}]))
    with pytest.raises(RecordError):
        normalize_spores(record(spores=[{**SPORE, "shot": 0}]))
    out = normalize_spores(record(spores=[{**SPORE, "shot": 9}, {**SPORE, "shot": 2}]))
    assert [s["shot"] for s in out["spores"]] == [2, 9]


def test_launched_without_receipt_is_refused() -> None:
    with pytest.raises(RecordError):
        normalize_spores(record(spores=[{**SPORE, "status": "launched"}]))
    launched = normalize_spores(record(spores=[{
        **SPORE,
        "status": "launched",
        "launchTx": "0x" + "ef" * 32,
        "launchedAt": "2026-09-17T11:00:00.000Z",
    }]))["spores"][0]
    assert launched["codeVerified"] is False


def test_implausible_provenance_is_refused() -> None:
    with pytest.raises(RecordError):
        normalize_spores(record(job={**JOB, "device": "acme_super"}))
    with pytest.raises(RecordError):
        normalize_spores(record(job={**JOB, "readoutError": 12}))
    with pytest.raises(RecordError):
        normalize_spores(record(job={**JOB, "ranAt": "yesterday"}))
    with pytest.raises(RecordError):
        normalize_spores(record(spores=[{**SPORE, "bitstring": "not-bits"}]))
    with pytest.raises(RecordError):
        normalize_spores(record(spores=[{**SPORE, "address": "0x123"}]))


def test_empty_is_not_unreadable() -> None:
    assert dict(EMPTY_SPORES) == {"job": None, "plan": None, "spores": []}


def test_prediction_without_plan_is_refused() -> None:
    with pytest.raises(RecordError):
        normalize_spores({"job": JOB, "spores": [SPORE]})
    for missing in ("chainId", "factoryAddress", "initiator", "planHash"):
        plan = dict(PLAN)
        del plan[missing]
        with pytest.raises(RecordError):
            normalize_spores(record(plan=plan))
    assert normalize_spores(record())["plan"]["chainId"] == 4663


def test_job_checks_itself() -> None:
    base = {"id": "d3k91f-003", "device": "ibm_fez", "shots": 4, "ranAt": "2026-09-17T10:00:00.000Z"}
    measurements = ["0111", "0111", "1010", "0000"]
    counts = {"0111": 2, "1010": 1, "0000": 1}

    def wrap(job):
        return {"job": job, "plan": PLAN, "spores": []}

    ok = normalize_spores(wrap({**base, "measurements": measurements, "counts": counts, "qubitLayout": [12, 13, 17, 21]}))
    assert ok["job"]["qubitLayout"] == [12, 13, 17, 21]
    assert len(ok["job"]["measurements"]) == 4

    with pytest.raises(RecordError):
        normalize_spores(wrap({**base, "measurements": measurements, "counts": {"0111": 4}}))
    with pytest.raises(RecordError):
        normalize_spores(wrap({**base, "measurements": ["0111"]}))
    with pytest.raises(RecordError):
        normalize_spores(wrap({**base, "measurements": measurements, "qubitLayout": [1, 2]}))
    with pytest.raises(RecordError):
        normalize_spores(wrap({**base, "measurements": measurements, "qubitLayout": [12, 12, 13, 14]}))
    with pytest.raises(RecordError):
        normalize_spores(wrap({**base, "measurements": ["0111", "01", "1010", "0000"]}))
    with pytest.raises(RecordError):
        normalize_spores(wrap({**base, "usageSeconds": 0}))


def test_unknown_top_level_key_is_refused() -> None:
    with pytest.raises(RecordError):
        normalize_spores({**record(), "extra": 1})


def test_verifier_recomputes_salt_from_bitstring() -> None:
    bit = "0111"
    spore = {
        **SPORE,
        "shot": 1,
        "bitstring": bit,
        "salt": salt_from_bitstring(bit),
    }
    job = {**JOB, "shots": 4, "measurements": ["0111", "1010", "0000", "1111"]}
    findings = verify_derivation({"job": job, "plan": PLAN, "spores": [spore]})
    assert findings[-1]["ok"] is True
    assert findings[-1]["bitstring"] == "0111"
    bad = {**spore, "salt": "0x" + "ab" * 32}
    with pytest.raises(RecordError, match="salt is not keccak256"):
        verify_derivation({"job": job, "plan": PLAN, "spores": [bad]})
