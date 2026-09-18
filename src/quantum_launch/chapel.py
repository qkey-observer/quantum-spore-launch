"""BSC Chapel (chain 97) rehearsal factory.

genius.fun is not deployed on chapel (factory/deployer code is empty). The
Arachnid CREATE2 proxy at 0x4e59b448… is. This path deploys a marker contract
whose CREATE2 salt is keccak256(utf8(bitstring)) — the same salt the mainnet
genius.fun launch uses — then checks the receipt and eth_getCode.

It is a pipeline proof, not a genius.fun token.
"""

from __future__ import annotations

import json
from importlib import resources
from pathlib import Path
from typing import Any

from eth_utils import keccak, to_checksum_address

from .abi_util import bytes32
from .derive import salt_from_bitstring
from .errors import LaunchError, PredictError
from .keys import Signer
from .launch import fill_tx, send_signed, wait_receipt
from .rpc import Rpc
from .trace import trace

CHAPEL_CHAIN_ID = 97
CREATE2_PROXY = "0x4e59b44847b379578588920cA78FbF26c0B4956C"
CHAPEL_RPC = "https://data-seed-prebsc-1-s1.binance.org:8545"
ARTIFACT = Path(__file__).resolve().parents[2] / "contracts" / "out" / "QuantumChapelToken.sol" / "QuantumChapelToken.json"


def load_artifact() -> dict[str, Any]:
    packed = resources.files("quantum_launch").joinpath("data").joinpath("chapel_token.json")
    if packed.is_file():
        return json.loads(packed.read_text(encoding="utf-8"))
    if ARTIFACT.exists():
        return json.loads(ARTIFACT.read_text(encoding="utf-8"))
    raise LaunchError("chapel artifact missing. Run: forge build")


def init_code(bitstring: str, name: str, symbol: str, salt: str) -> bytes:
    from eth_abi import encode

    artifact = load_artifact()
    bytecode = bytes.fromhex(artifact["bytecode"]["object"].replace("0x", ""))
    args = encode(
        ["string", "string", "string", "bytes32"],
        [bitstring, name, symbol, bytes32(salt)],
    )
    return bytecode + args


def create2_address(deployer: str, salt: str, code: bytes) -> str:
    salt_b = bytes32(salt)
    deployer_b = bytes.fromhex(deployer[2:])
    digest = keccak(b"\xff" + deployer_b + salt_b + keccak(code))
    return to_checksum_address("0x" + digest.hex()[-40:])


def predict_chapel(bitstring: str, name: str, symbol: str) -> dict[str, Any]:
    salt = salt_from_bitstring(bitstring)
    code = init_code(bitstring, name, symbol, salt)
    token = create2_address(CREATE2_PROXY, salt, code)
    trace(
        shot=None,
        bitstring=bitstring,
        step="chapel CREATE2 predict",
        salt=salt,
        token=token,
        deployer=CREATE2_PROXY,
    )
    return {
        "bitstring": bitstring,
        "salt": salt,
        "token": token,
        "deployer": CREATE2_PROXY,
        "initCodeHash": "0x" + keccak(code).hex(),
        "calldata": "0x" + salt[2:] + code.hex(),
    }


def deploy_chapel(
    rpc: Rpc,
    signer: Signer,
    bitstring: str,
    name: str,
    symbol: str,
    *,
    broadcast: bool,
) -> dict[str, Any]:
    chain = rpc.chain_id()
    if chain != CHAPEL_CHAIN_ID:
        raise PredictError(f"RPC chain id {chain} is not chapel 97")
    predicted = predict_chapel(bitstring, name, symbol)
    existing = rpc.get_code(predicted["token"])
    if existing != "0x":
        raise LaunchError(f"chapel predicted address already has code: {predicted['token']}")
    unsigned = {
        "chainId": CHAPEL_CHAIN_ID,
        "from": signer.address,
        "to": CREATE2_PROXY,
        "value": hex(0),
        "data": predicted["calldata"],
    }
    if not broadcast:
        return {**predicted, "broadcast": False, "unsigned": unsigned}
    filled = fill_tx(rpc, unsigned)
    tx_hash = send_signed(rpc, signer, filled)
    trace(bitstring=bitstring, step="chapel broadcast", launchTx=tx_hash)
    receipt = wait_receipt(rpc, tx_hash)
    if receipt.get("status") not in ("0x1", 1, "1"):
        raise LaunchError("chapel deploy reverted")
    code = rpc.get_code(predicted["token"])
    if code == "0x":
        raise LaunchError("eth_getCode empty after chapel receipt")
    return {
        **predicted,
        "broadcast": True,
        "launchTx": tx_hash,
        "blockNumber": int(receipt["blockNumber"], 16)
        if isinstance(receipt["blockNumber"], str)
        else receipt["blockNumber"],
        "codeVerified": True,
        "codeBytes": (len(code) - 2) // 2,
    }
