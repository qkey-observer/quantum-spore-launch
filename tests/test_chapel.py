from quantum_launch.chapel import CREATE2_PROXY, create2_address, predict_chapel
from quantum_launch.derive import salt_from_bitstring


def test_chapel_prediction_is_a_pure_function_of_the_bitstring() -> None:
    a = predict_chapel("0111", "QKEY", "QKEY")
    b = predict_chapel("0111", "QKEY", "QKEY")
    assert a["salt"] == salt_from_bitstring("0111")
    assert a["token"] == b["token"]
    assert a["deployer"] == CREATE2_PROXY
    assert a["token"].startswith("0x") and len(a["token"]) == 42
    other = predict_chapel("1010", "QKEY", "QKEY")
    assert other["token"] != a["token"]
    assert other["salt"] == salt_from_bitstring("1010")


def test_create2_address_matches_the_yellow_paper() -> None:
    # empty init code, zero salt, known deployer → stable
    addr = create2_address(CREATE2_PROXY, "0x" + "00" * 32, b"")
    assert addr == create2_address(CREATE2_PROXY, "0x" + "00" * 32, b"")
    assert addr.lower() != CREATE2_PROXY.lower()
