"""Read-only factory gate check. No keys, no spend."""

from __future__ import annotations

from typing import Any

from .abi_util import decode_typed, encode_call
from .platforms import checksum, load_platform
from .predict import (
    APPROVED_PAIR_SIG,
    CAN_LAUNCH_SIG,
    LAUNCH_DEPLOYER_SIG,
    LAUNCH_ENABLED_SIG,
    LAUNCH_FEE_SIG,
    PAIR_ECON_SIG,
    _addr,
    _bool,
    _uint,
)
from .rpc import Rpc


def inspect_factory(
    rpc: Rpc,
    platform: str | dict[str, Any] = "genius-bsc",
    initiator: str | None = None,
    pair: str | None = None,
) -> dict[str, Any]:
    plat = load_platform(platform)
    chain = rpc.chain_id()
    block = rpc.block_number()
    factory = checksum(plat["factory"])
    configured_deployer = checksum(plat["deployer"])
    wired = _addr(rpc.call(factory, encode_call(LAUNCH_DEPLOYER_SIG, [], []), block))
    enabled = _bool(rpc.call(factory, encode_call(LAUNCH_ENABLED_SIG, [], []), block))
    fee = _uint(rpc.call(factory, encode_call(LAUNCH_FEE_SIG, [], []), block))
    out: dict[str, Any] = {
        "chainId": chain,
        "blockNumber": block,
        "factory": factory,
        "configuredDeployer": configured_deployer,
        "wiredDeployer": wired,
        "deployerMatches": wired.lower() == configured_deployer.lower(),
        "launchEnabled": enabled,
        "launchFeeWei": str(fee),
    }
    who = initiator or plat.get("initiator")
    if who:
        allowed = _bool(rpc.call(factory, encode_call(CAN_LAUNCH_SIG, ["address"], [checksum(who)]), block))
        out["initiator"] = checksum(who)
        out["canLaunch"] = allowed
    quote = pair or (plat.get("quote") or {}).get("address")
    if quote:
        q = checksum(quote)
        approved = _bool(rpc.call(factory, encode_call(APPROVED_PAIR_SIG, ["address"], [q]), block))
        econ = decode_typed(
            ["uint256", "uint256", "uint8"],
            rpc.call(factory, encode_call(PAIR_ECON_SIG, ["address"], [q]), block),
        )
        out["pairToken"] = q
        out["pairApproved"] = approved
        out["pairEconomics"] = {
            "phantomQuote": str(int(econ[0])),
            "graduationThreshold": str(int(econ[1])),
            "decimals": int(econ[2]),
        }
    return out
