"""ABI encode/decode for the Genius / Pons launch tuple."""

from __future__ import annotations

import json
from importlib import resources

from eth_abi import decode, encode
from eth_utils import keccak

from .derive import keccak256

LAUNCH_DEPLOYMENT = (
    "(address,address,address,address,(address,uint16,uint16,uint16,uint16),"
    "address,address,uint256,uint256,uint256,bool,uint256,uint256,bytes32,"
    "string,string,string,string,(string,string,string,string,string))"
)
TOKEN_PARAMS = (
    "(string,string,string,string,(string,string,string,string,string),"
    "address,uint16,bool,bytes32,bytes32)"
)
FEE_POLICY = "(address,uint16,uint16,uint16,uint16)"
LAUNCH_CONFIG = "(uint256,uint256,uint256,uint256,uint24,int24,bool)"


def selector(signature: str) -> bytes:
    return keccak(text=signature)[:4]


def encode_call(signature: str, types: list[str], args: list[object]) -> str:
    return "0x" + (selector(signature) + encode(types, args)).hex()


def decode_addresses(data: str, n: int = 2) -> list[str]:
    raw = bytes.fromhex(data[2:] if data.startswith("0x") else data)
    decoded = decode(["address"] * n, raw)
    return ["0x" + d[-40:] if False else _to_addr(d) for d in decoded]


def _to_addr(value: str) -> str:
    if isinstance(value, bytes):
        return "0x" + value.hex()[-40:]
    text = value.lower()
    if not text.startswith("0x"):
        text = "0x" + text
    return text


def decode_typed(types: list[str], data: str):
    raw = bytes.fromhex(data[2:] if data.startswith("0x") else data)
    return decode(types, raw)


def load_abi(name: str) -> dict:
    text = resources.files("quantum_launch").joinpath("abi").joinpath(name).read_text(encoding="utf-8")
    return json.loads(text)


def bytes32(hex_str: str) -> bytes:
    text = hex_str.lower()
    if text.startswith("0x"):
        text = text[2:]
    raw = bytes.fromhex(text)
    if len(raw) != 32:
        raise ValueError("expected bytes32")
    return raw


# Keep keccak256 imported for callers that want a local hex digest of calldata.
_ = keccak256
