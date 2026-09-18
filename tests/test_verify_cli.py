from pathlib import Path
import json

from quantum_launch.cli import main
from quantum_launch.derive import salt_from_bitstring
from quantum_launch.platforms import GENIUS_BSC

ROOT = Path(__file__).resolve().parents[1]


def test_verify_cli_reprints_the_bitstring(tmp_path, capsys) -> None:
    job = json.loads((ROOT / "tests/fixtures/job.json").read_text(encoding="utf-8"))
    bits = job["measurements"][0]
    record = {
        "job": job,
        "plan": {
            "chainId": 56,
            "factoryAddress": GENIUS_BSC["factory"],
            "initiator": "0xCEB16Fa2cA6d9E9608Da614dA24336314542A707",
            "planHash": "0x" + "ab" * 32,
        },
        "spores": [{
            "shot": 1,
            "bitstring": bits,
            "salt": salt_from_bitstring(bits),
            "address": "0x" + "cd" * 20,
            "status": "awaiting_launch",
            "predictedAt": "2026-09-17T10:05:00.000Z",
        }],
    }
    path = tmp_path / "record.json"
    path.write_text(json.dumps(record), encoding="utf-8")
    assert main(["--quiet", "verify", str(path)]) == 0
    out = capsys.readouterr().out
    assert "0111" in out
    assert salt_from_bitstring("0111") in out
    assert "OK" in out


def test_verify_cli_64qubit_fixture(capsys) -> None:
    path = ROOT / "examples/verify-live-64qubit.json"
    assert main(["--quiet", "verify", str(path)]) == 0
    out = capsys.readouterr().out
    assert "1001001000010000000100000000000000000000000000000000000000000000" in out
    assert "0x7b0552d55123ba9314be1606794c35a59cdd748279c55fe7c9c3a9e3727cda64" in out
    assert "0x2c670B551d2B15c68eE08E492Ed2506eC22e6F83" in out
    assert "OK" in out
