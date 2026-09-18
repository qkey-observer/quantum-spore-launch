from pathlib import Path
import json

from quantum_launch.derive import salt_from_bitstring
from quantum_launch.mapping import apply_job, apply_map, map_hash, tally

ROOT = Path(__file__).resolve().parents[1]
MAP = json.loads((ROOT / "examples/launch-map.example.json").read_text(encoding="utf-8"))
JOB = json.loads((ROOT / "tests/fixtures/job.json").read_text(encoding="utf-8"))


def test_map_hash_stable_and_ignores_comment() -> None:
    hashed = map_hash(MAP)
    again = map_hash({**MAP, "comment": "rewritten later"})
    assert hashed == again
    assert hashed.startswith("0x") and len(hashed) == 66


def test_bitstring_0111_is_a_published_skip() -> None:
    decision = apply_map("0111", MAP)
    assert decision["launch"] is False
    assert decision["reason"] == "map.launchBit"
    assert decision["symbol"] == "QKEYC"
    assert decision["creatorTaxBps"] == 200
    assert decision["delaySeconds"] == 300
    assert salt_from_bitstring("0111") == "0x334fe1125e74700a86e339a5f102282ceaeb5a83bb3ca03cb42b44d576d6d9a0"


def test_bitstring_1010_launches() -> None:
    decision = apply_map("1010", MAP)
    assert decision["launch"] is True
    assert decision["symbol"] == "QKEYA"
    assert decision["creatorTaxBps"] == 50
    assert decision["delaySeconds"] == 0


def test_job_rounds_include_skips_in_order() -> None:
    rounds = apply_job(JOB["measurements"], MAP)
    assert [r["shot"] for r in rounds] == [1, 2, 3, 4]
    counts = tally(rounds)
    assert counts["measured"] == 4
    assert counts["launched"] == 2
    assert counts["skipped"] == 2
    assert [r["launch"] for r in rounds] == [False, True, False, True]
    assert rounds[0]["bitstring"] == "0111"
    assert rounds[1]["bitstring"] == "1010"


SUFFIX = json.loads((ROOT / "examples/launch-map.suffix.json").read_text(encoding="utf-8"))
SUFFIX_BITS = "10000000100000000111000000001010"
DIRECT = json.loads((ROOT / "examples/launch-map.direct.json").read_text(encoding="utf-8"))


def test_suffix_encoding_still_decodes() -> None:
    decision = apply_map(SUFFIX_BITS, SUFFIX)
    assert decision["name"] == "QKEY-A"
    assert decision["symbol"] == "QA"


def test_qpu_spells_the_name_from_the_alphabet() -> None:
    # 64 bits: launch, tax=4, delay=3, buyback, creator dest, quote=IBMB,
    # logo 0, config 0, opening 2, name AAAA, symbol AAA
    bits = (
        "1"
        + "00000100"
        + "000011"
        + "1"
        + "0"
        + "01"
        + "00"
        + "00"
        + "000010"
        + "00000" * 4
        + "00000" * 3
        + "0" * 64
    )
    assert len(bits) == 128
    decision = apply_map(bits, DIRECT)
    assert decision["launch"] is True
    assert decision["name"] == "AAAAAAAA"
    assert decision["symbol"] == "AAA"
    assert "QKEY" not in decision["name"]
    assert decision["nextLayers"] == 1
    assert decision["nextBackend"] == "ibm_fez"
    assert decision["creatorFeeRecipient"].startswith("0xcFf79628")
    assert decision["creatorTaxBps"] == 4
    assert decision["delaySeconds"] == 30
    assert decision["buybackAndLock"] is True
    assert decision["quote"]["symbol"] == "IBMB"
    assert decision["imageUrl"].endswith("logo-0.png")
    assert decision["launchConfigId"] == 0
    assert decision["openingBuy"] == "2"
    assert decision["description"] == "measured:" + bits
    assert "quote" in decision["fromQpu"]
    assert "imageUrl" in decision["fromQpu"]
    assert "openingBuy" in decision["fromQpu"]
    other = "1" + bits[1:-5] + "00001"
    # last 15 bits of symbol become AAB if last group is 00001
    # rebuild last 15 as 00000 00000 00001
    bits_b = bits[:49] + "00000" + "00000" + "00001" + bits[64:]
    other = apply_map(bits_b, DIRECT)
    assert other["symbol"] == "AAB"
    assert other["name"].startswith("AAAA")


def test_two_shots_make_one_spec() -> None:
    first = "1" + "0" * 63
    second = "0" * 64
    rounds = apply_job([first, second, first, second], DIRECT)
    assert len(rounds) == 4
    assert rounds[0]["specRole"] == "head"
    assert rounds[1]["specRole"] == "cont"
    assert rounds[0]["specBitstring"] == first + second
    counts = tally(rounds)
    assert counts["measured"] == 4
    assert counts["specs"] == 2


def test_direct_map_hash_pins_the_circuit() -> None:
    hashed = map_hash(DIRECT)
    changed = json.loads(json.dumps(DIRECT))
    changed["circuit"]["layers"] = 9
    assert map_hash(changed) != hashed
    changed_seed = json.loads(json.dumps(DIRECT))
    changed_seed["circuit"]["angleSeed"] = "other"
    assert map_hash(changed_seed) != hashed
    changed_alpha = json.loads(json.dumps(DIRECT))
    changed_alpha["alphabet"] = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
    assert map_hash(changed_alpha) != hashed
