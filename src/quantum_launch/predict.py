"""CREATE2 prediction via the wired launch deployer.

The address is not a function of salt alone. Under CREATE2 it depends on the
deploying contract, the initiating account, and the full init code (name,
symbol, image URL, quote asset, fee recipient, tax, buyback, …).
"""

from __future__ import annotations

from typing import Any

from .abi_util import (
    FEE_POLICY,
    LAUNCH_CONFIG,
    LAUNCH_DEPLOYMENT,
    TOKEN_PARAMS,
    bytes32,
    decode_typed,
    encode_call,
)
from .errors import PredictError
from .platforms import ZERO, checksum, pair_token
from .rpc import Rpc
from .trace import trace

PREDICT_SIG = f"predictLaunchAddresses({LAUNCH_DEPLOYMENT})"
LAUNCH_FEE_SIG = "launchFee()"
CAN_LAUNCH_SIG = "canLaunch(address)"
LAUNCH_DEPLOYER_SIG = "launchDeployer()"
MEME_HOOK_SIG = "memeHook()"
FEE_ESCROW_SIG = "feeEscrow()"
BUYBACK_VAULT_SIG = "buybackVault()"
LAUNCH_ENABLED_SIG = "launchEnabled()"
GET_CONFIG_SIG = f"getLaunchConfig(uint256)"
CONFIG_COUNT_SIG = "launchConfigCount()"
PREVIEW_ECON_SIG = "previewLaunchEconomics(uint256,address)"
APPROVED_PAIR_SIG = "approvedPairTokens(address)"
PAIR_ECON_SIG = "pairTokenEconomics(address)"
POLICY_SIG = "currentFeePolicy()"
FACTORY_ON_DEPLOYER_SIG = "factory()"


def _addr(data: str) -> str:
    decoded = decode_typed(["address"], data)[0]
    return checksum(decoded)


def _bool(data: str) -> bool:
    return bool(decode_typed(["bool"], data)[0])


def _uint(data: str) -> int:
    return int(decode_typed(["uint256"], data)[0])


def _bytes32(data: str) -> str:
    value = decode_typed(["bytes32"], data)[0]
    return "0x" + value.hex()


def tax_bps(plan: dict[str, Any]) -> int:
    launch = plan.get("launch") or {}
    if launch.get("creatorTaxBps") is not None:
        return int(launch["creatorTaxBps"])
    percent = launch.get("creatorTaxPercent", "0")
    return int(round(float(percent) * 100))


def to_foundation(plan: dict[str, Any]) -> bool:
    dest = (plan.get("launch") or {}).get("feeDestination", "creator_payout")
    return dest in {"foundation", "to_foundation", True}


def socials(plan: dict[str, Any]) -> tuple[str, str, str, str, str]:
    token = plan.get("token") or {}
    return (
        token.get("x") or token.get("twitter") or "",
        token.get("telegram") or "",
        token.get("discord") or "",
        token.get("website") or "",
        token.get("farcaster") or "",
    )


def token_fields(plan: dict[str, Any]) -> dict[str, str]:
    token = plan.get("token") or {}
    name = token.get("name") or ""
    symbol = token.get("symbol") or ""
    logo = token.get("imageUrl") or token.get("logo") or ""
    description = token.get("description") or ""
    if not name or not symbol:
        raise PredictError("frozen plan is missing token name/symbol")
    if "REPLACE" in logo or logo.startswith("REPLACE"):
        raise PredictError("imageUrl is still a placeholder; CREATE2 commits to it")
    return {"name": name, "symbol": symbol, "logo": logo, "description": description}


def read_snapshot(rpc: Rpc, platform: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    chain_id = rpc.chain_id()
    expected = int(plan.get("chain", {}).get("chainId") or plan.get("chainId") or platform["chainId"])
    if chain_id != expected:
        raise PredictError(f"RPC chain id {chain_id} is not {expected}")
    block = rpc.get_block("latest")
    block_number = int(block["number"], 16)
    factory = checksum(platform["factory"])
    deployer = checksum(platform["deployer"])
    wired = _addr(rpc.call(factory, encode_call(LAUNCH_DEPLOYER_SIG, [], []), block_number))
    if wired.lower() != deployer.lower():
        raise PredictError("factory.launchDeployer() is not the configured wired deployer")
    back = _addr(rpc.call(deployer, encode_call(FACTORY_ON_DEPLOYER_SIG, [], []), block_number))
    if back.lower() != factory.lower():
        raise PredictError("deployer.factory() does not point at the configured factory")
    hook = _addr(rpc.call(factory, encode_call(MEME_HOOK_SIG, [], []), block_number))
    escrow = _addr(rpc.call(factory, encode_call(FEE_ESCROW_SIG, [], []), block_number))
    vault = _addr(rpc.call(factory, encode_call(BUYBACK_VAULT_SIG, [], []), block_number))
    enabled = _bool(rpc.call(factory, encode_call(LAUNCH_ENABLED_SIG, [], []), block_number))
    fee = _uint(rpc.call(factory, encode_call(LAUNCH_FEE_SIG, [], []), block_number))
    initiator = checksum(plan["initiator"])
    allowed = _bool(rpc.call(factory, encode_call(CAN_LAUNCH_SIG, ["address"], [initiator]), block_number))
    config_id = int((plan.get("launch") or {}).get("launchConfigId") or plan.get("launchConfigId") or 0)
    count = _uint(rpc.call(factory, encode_call(CONFIG_COUNT_SIG, [], []), block_number))
    if config_id >= count:
        raise PredictError("launchConfigId is out of range")
    raw_config = rpc.call(factory, encode_call(GET_CONFIG_SIG, ["uint256"], [config_id]), block_number)
    config = decode_typed([LAUNCH_CONFIG], raw_config)[0]
    pair = pair_token(plan, platform)
    if pair.lower() != ZERO.lower():
        approved = _bool(rpc.call(factory, encode_call(APPROVED_PAIR_SIG, ["address"], [pair]), block_number))
        if not approved:
            raise PredictError(f"quote asset {pair} is not an approved pair token")
        econ = decode_typed(["uint256", "uint256", "uint8"], rpc.call(
            factory, encode_call(PAIR_ECON_SIG, ["address"], [pair]), block_number,
        ))
        phantom, graduation, decimals = int(econ[0]), int(econ[1]), int(econ[2])
    else:
        phantom, graduation, decimals = int(config[2]), int(config[3]), 18
    expected_econ = _bytes32(rpc.call(
        factory, encode_call(PREVIEW_ECON_SIG, ["uint256", "address"], [config_id, pair]), block_number,
    ))
    policy = decode_typed([FEE_POLICY], rpc.call(hook, encode_call(POLICY_SIG, [], []), block_number))[0]
    return {
        "chainId": chain_id,
        "blockNumber": block_number,
        "blockHash": block["hash"],
        "blockTimestamp": int(block["timestamp"], 16),
        "factory": factory,
        "deployer": deployer,
        "hook": hook,
        "feeEscrow": escrow,
        "buybackVault": vault,
        "launchEnabled": enabled,
        "launchFeeWei": str(fee),
        "initiator": initiator,
        "canLaunch": allowed,
        "launchConfigId": config_id,
        "config": {
            "supply": str(int(config[0])),
            "curveFeeBps": int(config[1]),
            "phantomQuote": str(phantom),
            "graduationThreshold": str(graduation),
            "poolFee": int(config[4]),
            "tickSpacing": int(config[5]),
            "enabled": bool(config[6]),
        },
        "pairToken": pair,
        "pairDecimals": decimals,
        "router": checksum(platform["router"]) if platform.get("router") else None,
        "expectedEconomics": expected_econ,
        "policy": {
            "protocolFeeRecipient": checksum(policy[0]),
            "protocolFeeShareBps": int(policy[1]),
            "buybackBurnBps": int(policy[2]),
            "hookFeeBps": int(policy[3]),
            "maxInternalPriceImpactBps": int(policy[4]),
        },
    }


def deployment_tuple(plan: dict[str, Any], snapshot: dict[str, Any], salt: str) -> tuple:
    token = token_fields(plan)
    recipient = checksum((plan.get("launch") or {}).get("creatorFeeRecipient") or plan["initiator"])
    cfg = snapshot["config"]
    pol = snapshot["policy"]
    buyback = bool((plan.get("launch") or {}).get("buybackAndLock") or (plan.get("launch") or {}).get("buybackEnabled") or False)
    return (
        snapshot["pairToken"],
        recipient,
        snapshot["initiator"],
        snapshot["hook"],
        (
            pol["protocolFeeRecipient"],
            pol["protocolFeeShareBps"],
            pol["buybackBurnBps"],
            pol["hookFeeBps"],
            pol["maxInternalPriceImpactBps"],
        ),
        snapshot["feeEscrow"],
        snapshot["buybackVault"],
        int(cfg["phantomQuote"]),
        int(cfg["curveFeeBps"]),
        tax_bps(plan),
        buyback,
        int(cfg["graduationThreshold"]),
        int(cfg["supply"]),
        bytes32(salt),
        token["name"],
        token["symbol"],
        token["logo"],
        token["description"],
        socials(plan),
    )


def token_params_tuple(plan: dict[str, Any], snapshot: dict[str, Any], salt: str) -> tuple:
    token = token_fields(plan)
    recipient = checksum((plan.get("launch") or {}).get("creatorFeeRecipient") or plan["initiator"])
    buyback = bool((plan.get("launch") or {}).get("buybackAndLock") or (plan.get("launch") or {}).get("buybackEnabled") or False)
    return (
        token["name"],
        token["symbol"],
        token["logo"],
        token["description"],
        socials(plan),
        recipient,
        tax_bps(plan),
        buyback,
        bytes32(snapshot["expectedEconomics"]),
        bytes32(salt),
    )


def predict_addresses(
    rpc: Rpc,
    platform: dict[str, Any],
    plan: dict[str, Any],
    salt: str,
    bitstring: str,
    shot: int,
    snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    snap = snapshot or read_snapshot(rpc, platform, plan)
    if not snap["launchEnabled"]:
        raise PredictError("factory.launchEnabled is false")
    if not snap["config"]["enabled"]:
        raise PredictError("selected launch config is disabled")
    if not snap["canLaunch"]:
        raise PredictError(
            "canLaunch(initiator) is false. The launch gate is protocol-owned; "
            "this program cannot grant the initiating account permission."
        )
    data = encode_call(PREDICT_SIG, [LAUNCH_DEPLOYMENT], [deployment_tuple(plan, snap, salt)])
    raw = rpc.call(snap["deployer"], data, snap["blockNumber"])
    token, curve = decode_typed(["address", "address"], raw)
    token_a, curve_a = checksum(token), checksum(curve)
    if token_a.lower() == curve_a.lower() or token_a.lower() == ZERO.lower():
        raise PredictError("deployer returned an invalid predicted address")
    token_code = rpc.get_code(token_a, snap["blockNumber"])
    curve_code = rpc.get_code(curve_a, snap["blockNumber"])
    if token_code != "0x" or curve_code != "0x":
        raise PredictError("predicted token or curve already has code")
    trace(
        shot=shot,
        bitstring=bitstring,
        step="CREATE2 predict",
        salt=salt,
        token=token_a,
        curve=curve_a,
        deployer=snap["deployer"],
        initiator=snap["initiator"],
        pair=snap["pairToken"],
        block=snap["blockNumber"],
    )
    return {
        "token": token_a,
        "curve": curve_a,
        "reserved": False,
        "salt": salt.lower(),
        "bitstring": bitstring,
        "shot": shot,
        "snapshot": snap,
        "tokenParams": None,
    }


def encode_launch_tx(plan: dict[str, Any], snapshot: dict[str, Any], salt: str) -> dict[str, Any]:
    """Unsigned factory.launchToken. Exemptions use the 4-arg overload; otherwise 3-arg."""
    params = token_params_tuple(plan, snapshot, salt)
    pair = snapshot["pairToken"]
    config_id = snapshot["launchConfigId"]
    exemptions = list((plan.get("launch") or {}).get("exemptAddresses") or [])
    foundation = to_foundation(plan)
    if exemptions and foundation:
        raise PredictError(
            "this Genius factory ABI has no launchToken overload that takes both "
            "snipeTaxExemptions and toFoundation; pick one"
        )
    opening = int((plan.get("launch") or {}).get("openingBuy") or 0)
    router = snapshot.get("router")
    native = pair.lower() == ZERO.lower()
    if opening > 0 and native and router:
        data = encode_call(
            f"launchAndBuy({TOKEN_PARAMS},uint256,address,uint256,uint256,address,bool)",
            [TOKEN_PARAMS, "uint256", "address", "uint256", "uint256", "address", "bool"],
            [params, config_id, pair, opening, 0, snapshot["initiator"], foundation],
        )
        return {
            "chainId": snapshot["chainId"],
            "from": snapshot["initiator"],
            "to": checksum(router),
            "value": hex(int(snapshot["launchFeeWei"]) + opening),
            "data": data,
            "openingBuy": str(opening),
        }
    if exemptions:
        data = encode_call(
            f"launchToken({TOKEN_PARAMS},uint256,address,address[])",
            [TOKEN_PARAMS, "uint256", "address", "address[]"],
            [params, config_id, pair, [checksum(a) for a in exemptions]],
        )
    elif foundation:
        data = encode_call(
            f"launchToken({TOKEN_PARAMS},uint256,address,bool)",
            [TOKEN_PARAMS, "uint256", "address", "bool"],
            [params, config_id, pair, True],
        )
    else:
        data = encode_call(
            f"launchToken({TOKEN_PARAMS},uint256,address)",
            [TOKEN_PARAMS, "uint256", "address"],
            [params, config_id, pair],
        )
    return {
        "chainId": snapshot["chainId"],
        "from": snapshot["initiator"],
        "to": snapshot["factory"],
        "value": hex(int(snapshot["launchFeeWei"])),
        "data": data,
        "openingBuy": str(opening),
    }
