from quantum_launch.errors import MeasureError
from quantum_launch.measure import counts_from_bitstrings, ordered_bitstrings_from_pub, probe_extraction
import pytest


class _Bits:
    def __init__(self, values):
        self._values = values

    def get_bitstrings(self):
        return list(self._values)


class _Pub:
    def __init__(self, values):
        self.data = type("D", (), {"meas": _Bits(values)})()


def test_ordered_bitstrings_from_v2_bitarray() -> None:
    bits = ["0111", "1010", "0000", "1111"]
    assert ordered_bitstrings_from_pub(_Pub(bits)) == bits
    assert counts_from_bitstrings(bits) == {"0111": 1, "1010": 1, "0000": 1, "1111": 1}


def test_counts_only_is_refused() -> None:
    class CountsOnly:
        data = type("D", (), {"get_counts": lambda self: {"0111": 4}})()

    with pytest.raises(MeasureError, match="get_bitstrings"):
        ordered_bitstrings_from_pub(CountsOnly())


def test_probe_extraction_does_not_need_a_backend() -> None:
    result = probe_extraction(num_qubits=4, shots=8)
    assert result["ok"] is True
    assert result["width"] == 4
    assert len(result["sample"]) >= 1
