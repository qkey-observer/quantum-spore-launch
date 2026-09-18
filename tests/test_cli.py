from pathlib import Path

from quantum_launch.cli import main
from quantum_launch.derive import salt_from_bitstring

ROOT = Path(__file__).resolve().parents[1]


def test_cli_derive_salt(capsys) -> None:
    code = main(["derive", "--bitstring", "0111"])
    assert code == 0
    out = capsys.readouterr().out
    assert "0111" in out
    assert salt_from_bitstring("0111") in out


def test_cli_derive_plan(capsys) -> None:
    code = main(["--quiet", "derive", "--plan", str(ROOT / "examples/launch-plan.example.json")])
    assert code == 0
    out = capsys.readouterr().out
    assert out.strip().split()[-1].startswith("0x")
    assert len(out.strip().split()[-1]) == 66


def test_cli_rejects_short_bitstring() -> None:
    assert main(["derive", "--bitstring", "0"]) == 1
