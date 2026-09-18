from pathlib import Path

from quantum_launch.derive import plan_hash, salt_from_bitstring
from quantum_launch.pipeline import freeze_plan, load_plan, next_unused_shot
from quantum_launch.platforms import GENIUS_BSC
from quantum_launch.record import normalize_spores, verify_derivation
from quantum_launch.errors import LaunchError
import json
import pytest

ROOT = Path(__file__).resolve().parents[1]
JOB = json.loads((ROOT / "tests/fixtures/job.json").read_text(encoding="utf-8"))


def test_shots_are_consumed_in_order() -> None:
    measurements = JOB["measurements"]
    used: set[int] = set()
    assert next_unused_shot(measurements, used) == 1
    used.add(1)
    assert next_unused_shot(measurements, used) == 2
    used.update({2, 3, 4})
    with pytest.raises(LaunchError, match="No unused shot"):
        next_unused_shot(measurements, used)


def test_each_shot_maps_to_its_salt() -> None:
    expected = {
        "0111": "0x334fe1125e74700a86e339a5f102282ceaeb5a83bb3ca03cb42b44d576d6d9a0",
        "1010": "0x578b93b62a110a7a4f03d18a7146d78b7e4ad5f48df01b90c555649fea625487",
        "0000": "0xe8d1f6cb90fef5fc9696cc77858b42d4e99b0959246d86f4584b49f5af0fe3f9",
        "1111": "0x3531cc3dc5bb231b65d260771886cc583d8fe8fb29b457554cb1930a722a747d",
    }
    for i, bits in enumerate(JOB["measurements"], start=1):
        assert salt_from_bitstring(bits) == expected[bits]


def test_freeze_plan_commits_to_factory_and_quote() -> None:
    plan = load_plan(ROOT / "examples/launch-plan.example.json")
    frozen = freeze_plan(plan, GENIUS_BSC)
    hashed = plan_hash(frozen)
    again = plan_hash(freeze_plan(plan, GENIUS_BSC))
    assert hashed == again
    changed = json.loads(json.dumps(frozen))
    changed["token"]["name"] = "NOTQKEY"
    assert plan_hash(changed) != hashed
    changed_quote = json.loads(json.dumps(frozen))
    changed_quote["quote"]["address"] = "0x" + "11" * 20
    assert plan_hash(changed_quote) != hashed


def test_fixture_job_normalizes_and_verifier_follows_the_bitstring() -> None:
    plan = {
        "chainId": 56,
        "factoryAddress": GENIUS_BSC["factory"],
        "initiator": "0xCEB16Fa2cA6d9E9608Da614dA24336314542A707",
        "planHash": "0x" + "ab" * 32,
    }
    bits = JOB["measurements"][0]
    spore = {
        "shot": 1,
        "bitstring": bits,
        "salt": salt_from_bitstring(bits),
        "address": "0x" + "cd" * 20,
        "status": "awaiting_launch",
        "predictedAt": "2026-09-17T10:05:00.000Z",
    }
    record = {"job": JOB, "plan": plan, "spores": [spore]}
    out = normalize_spores(record)
    assert out["job"]["measurements"][0] == "0111"
    findings = verify_derivation(out)
    salt_row = next(f for f in findings if f["check"] == "salt")
    assert salt_row["ok"] is True
    assert salt_row["bitstring"] == "0111"
    assert salt_row["expectedSalt"] == salt_from_bitstring("0111")
