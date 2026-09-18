"""Launchpad adapters. Measurement and derivation do not belong to one pad.

genius.fun on BSC is the worked example. Pons V2 on Robinhood Chain is a
second adapter of the same CREATE2 shape. Add a pad with a JSON file
(see examples/platform.template.json); do not assume salt alone is the address.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from eth_utils import to_checksum_address

GENIUS_BSC: dict[str, Any] = {
    "id": "genius-bsc",
    "name": "genius.fun",
    "chainName": "BSC",
    "chainId": 56,
    "createUrl": "https://genius.fun/create",
    "contractsUrl": "https://genius.fun/docs/contracts",
    "release": "prod-foundation-20260916",
    "stack": "bnb-mainnet-m4.1",
    "factory": "0x78EAE9537C0ef90DFe9B7ae964682Fe8138afe31",
    "deployer": "0xaB3eAD42ec2587D16BAE8f2c9Fb133c533C7fAAf",
    "hook": "0xFf17F41c5Efd6CCe944Af0912F300097D62df5c9",
    "feeEscrow": "0xFf8A2ae655E5851CB414Ac5aB41B311dA4287281",
    "buybackVault": "0x6EcBe74E6CF896c610C34A3BE59Bd54c5A5B784E",
    "router": "0x2EF00378984e84f2DAa08DfB5Fb03bBDE2038ae6",
    "quote": {
        "symbol": "IBMB",
        "name": "IBM",
        "address": "0xfA273B076Feb8c0FB34e554ae341082323D016A3",
        "decimals": 18,
    },
    "abiFile": "genius_bsc.json",
    "nativeIsZeroAddress": True,
    "note": (
        "genius.fun is a Pons v2 fork on BSC. CREATE2 lives on the wired launch "
        "deployer, not the factory. originalDeployer is the initiating EOA "
        "(msg.sender), not the deployer contract. canLaunch is protocol-owned; "
        "this program cannot whitelist itself."
    ),
}

PONS_ROBINHOOD: dict[str, Any] = {
    "id": "pons-robinhood",
    "name": "Pons V2",
    "chainName": "Robinhood Chain",
    "chainId": 4663,
    "factory": "0x7eD598BcEf8bd9Edd8C97A195C6d13f40801EC7e",
    "deployer": "0x3711ceA4feaDE896C913C68F01Eda97Cb06D1A42",
    "hook": "0xE5e702641Ea86F4ae6cC3cDaeD2B886f976Be044",
    "feeEscrow": "0xd3AFEB2a57f70eF218Aa82451c51B2fb0416Ac9e",
    "buybackVault": "0x42df2a798f82289E177311362e8f5ccC45c1219c",
    "router": "0xe33E9E479dF8802cb0866d5d05258bEc4cF62948",
    "quote": {
        "symbol": "ETH",
        "name": "ETH",
        "address": "0x0000000000000000000000000000000000000000",
        "decimals": 18,
    },
    "abiFile": "pons_v2.json",
    "nativeIsZeroAddress": True,
    "note": (
        "Second target. Predict on the wired deployer 0x3711ceA4…, not the factory. "
        "Native quote only in the original Pons tooling; this program still takes "
        "pairToken from the plan."
    ),
}

PLATFORMS = {GENIUS_BSC["id"]: GENIUS_BSC, PONS_ROBINHOOD["id"]: PONS_ROBINHOOD}
ZERO = "0x0000000000000000000000000000000000000000"


def checksum(address: str) -> str:
    return to_checksum_address(address)


def load_platform(path_or_id: str | dict[str, Any]) -> dict[str, Any]:
    if isinstance(path_or_id, dict):
        return deepcopy(path_or_id)
    if path_or_id in PLATFORMS:
        return deepcopy(PLATFORMS[path_or_id])
    import json
    from pathlib import Path

    data = json.loads(Path(path_or_id).read_text(encoding="utf-8"))
    if "id" in data and data["id"] in PLATFORMS:
        base = deepcopy(PLATFORMS[data["id"]])
        base.update(data)
        return base
    return data


def pair_token(plan: dict[str, Any], platform: dict[str, Any]) -> str:
    quote = plan.get("quote") or {}
    address = quote.get("address") or platform["quote"]["address"]
    return checksum(address)
