"""Publish the prediction before the launch transaction exists.

A local file is the working copy. An on-chain commit transaction is what a
third party can timestamp. Publishing afterwards only proves that some
bitstring maps to the address.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .errors import LaunchError
from .keys import Signer
from .launch import fill_tx, send_signed, wait_receipt
from .measure import utc_now
from .rpc import Rpc
from .trace import trace


def append_prediction(path: Path, entry: dict[str, Any]) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    published = {**entry, "publishedAt": entry.get("publishedAt") or utc_now()}
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(published, separators=(",", ":")) + "\n")
    return published


def commit_onchain(
    rpc: Rpc,
    signer: Signer,
    initiator: str,
    plan_hash: str,
    salt: str,
    token: str,
    shot: int,
    bitstring: str,
) -> dict[str, Any]:
    from .derive import keccak256

    magic = keccak256(b"quantum-spore-launch/prediction-v1")[2:]
    data = (
        "0x"
        + magic
        + salt[2:]
        + plan_hash[2:]
        + token[2:].rjust(40, "0")[-40:]
        + f"{shot:08x}"
        + bitstring.encode("utf-8").hex()
    )
    unsigned = {
        "chainId": rpc.chain_id(),
        "from": initiator,
        "to": initiator,
        "value": hex(0),
        "data": data,
    }
    filled = fill_tx(rpc, unsigned)
    tx_hash = send_signed(rpc, signer, filled)
    receipt = wait_receipt(rpc, tx_hash)
    if receipt.get("status") not in ("0x1", 1, "1"):
        raise LaunchError("prediction-commit transaction reverted")
    block = int(receipt["blockNumber"], 16) if isinstance(receipt["blockNumber"], str) else int(receipt["blockNumber"])
    trace(shot=shot, bitstring=bitstring, step="on-chain prediction commit", commitTx=tx_hash, block=block)
    return {"commitTx": tx_hash, "commitBlock": block, "publishedAt": utc_now()}
