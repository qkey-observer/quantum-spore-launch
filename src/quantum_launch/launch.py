"""Sign and broadcast the launch. Default is dry-run; --broadcast is required to send."""

from __future__ import annotations

import time
from typing import Any

from .errors import LaunchError
from .keys import Signer
from .rpc import Rpc
from .trace import trace


def fill_tx(rpc: Rpc, unsigned: dict[str, Any]) -> dict[str, Any]:
    nonce = rpc.nonce(unsigned["from"])
    gas_price = rpc.gas_price()
    estimate_fields = {
        "from": unsigned["from"],
        "to": unsigned["to"],
        "data": unsigned["data"],
        "value": unsigned["value"],
    }
    try:
        gas = rpc.estimate_gas(estimate_fields)
    except Exception:
        gas = 4_000_000
    tx = {
        "chainId": unsigned["chainId"],
        "nonce": nonce,
        "to": unsigned["to"],
        "value": int(unsigned["value"], 16),
        "data": unsigned["data"],
        "gas": int(gas * 12 / 10),
        "gasPrice": gas_price,
    }
    return tx


def send_signed(rpc: Rpc, signer: Signer, tx: dict[str, Any]) -> str:
    raw = signer.sign_transaction(tx)
    return rpc.send_raw("0x" + raw.hex())


def wait_receipt(rpc: Rpc, tx_hash: str, timeout_s: float = 180.0, poll_s: float = 2.0) -> dict[str, Any]:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        receipt = rpc.receipt(tx_hash)
        if receipt and receipt.get("blockNumber"):
            return receipt
        time.sleep(poll_s)
    raise LaunchError("timed out waiting for receipt")


def code_verified(rpc: Rpc, address: str) -> tuple[bool, str]:
    code = rpc.get_code(address, "latest")
    ok = isinstance(code, str) and code.startswith("0x") and len(code) > 2
    return ok, code


def publish_commit_tx(plan_hash: str, salt: str, token: str, shot: int, bitstring: str) -> dict[str, Any]:
    """Calldata for an on-chain prediction commit (sent to the initiator, value 0).

    Chain timestamps this before the launch transaction. File mtime is not a proof.
    """
    from .derive import keccak256

    magic = keccak256(b"quantum-spore-launch/prediction-v1")
    payload = magic + salt[2:] + plan_hash[2:] + token[2:] + f"{shot:08x}" + bitstring.encode().hex()
    return {"data": "0x" + payload if not payload.startswith("0x") else payload}


def run_launch(
    *,
    rpc: Rpc,
    signer: Signer | None,
    unsigned: dict[str, Any],
    bitstring: str,
    shot: int,
    predicted_token: str,
    predicted_curve: str,
    broadcast: bool,
    dry_run: bool = True,
) -> dict[str, Any]:
    trace(shot=shot, bitstring=bitstring, step="unsigned launch", **{
        "from": unsigned["from"],
        "to": unsigned["to"],
        "value": unsigned["value"],
        "token": predicted_token,
    })
    if dry_run or not broadcast:
        return {
            "broadcast": False,
            "dryRun": True,
            "unsigned": unsigned,
            "token": predicted_token,
            "curve": predicted_curve,
            "note": "default is dry-run. pass --broadcast to sign and send.",
        }
    if signer is None:
        raise LaunchError("broadcast requires a signer")
    filled = fill_tx(rpc, unsigned)
    tx_hash = send_signed(rpc, signer, filled)
    trace(shot=shot, bitstring=bitstring, step="broadcast", launchTx=tx_hash)
    receipt = wait_receipt(rpc, tx_hash)
    status = receipt.get("status")
    if status not in ("0x1", 1, "1"):
        raise LaunchError("launch transaction reverted")
    ok, code = code_verified(rpc, predicted_token)
    curve_ok, curve_code = code_verified(rpc, predicted_curve)
    trace(
        shot=shot,
        bitstring=bitstring,
        step="eth_getCode",
        token=predicted_token,
        tokenBytes=max(0, (len(code) - 2) // 2),
        curve=predicted_curve,
        curveBytes=max(0, (len(curve_code) - 2) // 2),
        codeVerified=ok and curve_ok,
    )
    if not ok:
        raise LaunchError("eth_getCode at the predicted token is empty after the receipt")
    return {
        "broadcast": True,
        "dryRun": False,
        "launchTx": tx_hash,
        "blockNumber": int(receipt["blockNumber"], 16) if isinstance(receipt["blockNumber"], str) else receipt["blockNumber"],
        "token": predicted_token,
        "curve": predicted_curve,
        "codeVerified": True,
        "tokenCodeBytes": (len(code) - 2) // 2,
        "curveCodeVerified": curve_ok,
    }
