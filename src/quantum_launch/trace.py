"""Print the measured bitstring at every step so the address is visibly from it."""

from __future__ import annotations

from typing import Any

_ENABLED = True


def set_trace(enabled: bool) -> None:
    global _ENABLED
    _ENABLED = enabled


def trace(*, shot: int | None = None, bitstring: str | None = None, step: str, **fields: Any) -> None:
    if not _ENABLED:
        return
    head = []
    if shot is not None:
        head.append(f"shot {shot}")
    if bitstring is not None:
        head.append(f"bitstring {bitstring}")
    label = "  ".join(head) if head else ""
    print(f"→ {step}" + (f"  {label}" if label else ""))
    for key, value in fields.items():
        if value is None:
            continue
        print(f"    {key:<16} {value}")
