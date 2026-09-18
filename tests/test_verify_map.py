from pathlib import Path
import json

from quantum_launch.derive import salt_from_bitstring
from quantum_launch.mapping import apply_job, map_hash
from quantum_launch.platforms import GENIUS_BSC
from quantum_launch.verify_public import verify_public_record

ROOT = Path(__file__).resolve().parents[1]


def test_verifier_accepts_published_skips() -> None:
    job = json.loads((ROOT / "tests/fixtures/job.json").read_text(encoding="utf-8"))
    launch_map = json.loads((ROOT / "examples/launch-map.example.json").read_text(encoding="utf-8"))
    rounds = apply_job(job["measurements"], launch_map)
    launched = [r for r in rounds if r["launch"]]
    record = {
        "schema": "quantum-spore-launch/v1",
        "job": job,
        "plan": {
            "chainId": 56,
            "factoryAddress": GENIUS_BSC["factory"],
            "initiator": "0xCEB16Fa2cA6d9E9608Da614dA24336314542A707",
            "planHash": "0x" + "ab" * 32,
            "mapHash": map_hash(launch_map),
        },
        "launchMap": launch_map,
        "rounds": rounds,
        "spores": [
            {
                "shot": r["shot"],
                "bitstring": r["bitstring"],
                "salt": salt_from_bitstring(r["bitstring"]),
                "address": "0x" + f"{r['shot']:02x}" * 20,
                "status": "awaiting_launch",
                "predictedAt": "2026-09-17T10:05:00.000Z",
            }
            for r in launched
        ],
    }
    findings = verify_public_record(record, launch_map=launch_map)
    rounds_row = next(f for f in findings if f["check"] == "rounds")
    assert rounds_row["measured"] == 4
    assert rounds_row["launched"] == 2
    assert rounds_row["skipped"] == 2
    assert any(f["check"] == "mapHash" and f["ok"] for f in findings)
