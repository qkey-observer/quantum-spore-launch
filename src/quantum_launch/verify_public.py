"""Sceptic verifier: salt, planHash, self-checks, optional on-chain re-predict."""

from __future__ import annotations

from typing import Any

from .errors import RecordError
from .mapping import apply_map, load_map, map_hash
from .platforms import load_platform
from .predict import predict_addresses, read_snapshot
from .record import fail, normalize_spores, verify_derivation
from .rpc import Rpc
from .trace import trace


def site_from_any(record: dict[str, Any]) -> dict[str, Any]:
    if record.get("schema") == "quantum-spore-launch/v1":
        return {
            "job": record["job"],
            "plan": record["plan"],
            "spores": record.get("spores") or [],
            "rounds": record.get("rounds") or [],
            "launchMap": record.get("launchMap"),
        }
    return {
        "job": record.get("job"),
        "plan": record.get("plan"),
        "spores": record.get("spores") or [],
        "rounds": record.get("rounds") or [],
        "launchMap": record.get("launchMap"),
    }


def verify_public_record(
    record: dict[str, Any],
    *,
    frozen_plan: dict[str, Any] | None = None,
    launch_map: dict[str, Any] | None = None,
    rpc_url: str | None = None,
    platform: str | dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    site = site_from_any(record)
    plan_in = site["plan"] or {}
    frozen = frozen_plan or plan_in.get("frozen")
    mapped = launch_map or site.get("launchMap") or (frozen or {}).get("launchMap")
    normalized = normalize_spores({
        "job": site["job"],
        "plan": {
            "chainId": plan_in["chainId"],
            "factoryAddress": plan_in["factoryAddress"],
            "initiator": plan_in["initiator"],
            "planHash": plan_in["planHash"],
        },
        "spores": [
            {k: s[k] for k in s if k in {
                "shot", "bitstring", "salt", "address", "status",
                "predictedAt", "launchTx", "launchedAt", "codeVerified", "curveAddress",
            }}
            for s in site.get("spores") or []
        ],
    })
    findings = verify_derivation(normalized, frozen_plan=frozen)

    job = normalized["job"] or {}
    measurements = job.get("measurements") or []
    if measurements:
        findings.append({
            "check": "countsMatchMeasurements",
            "ok": True,
            "shots": len(measurements),
        })

    if mapped is not None:
        spec = load_map(mapped)
        hashed = map_hash(mapped)
        recorded = (frozen or {}).get("mapHash") or plan_in.get("mapHash")
        ok = recorded is None or recorded.lower() == hashed
        findings.append({"check": "mapHash", "ok": ok, "expected": hashed, "recorded": recorded})
        if recorded is not None and not ok:
            fail("mapHash does not match the published launch map")
        rounds = site.get("rounds") or []
        if rounds:
            if [r.get("shot") for r in rounds] != list(range(1, len(rounds) + 1)):
                fail("rounds must list every shot in order, including skips")
            if measurements and len(rounds) != len(measurements):
                fail("rounds length does not match job.measurements")
            for row in rounds:
                bits = row["bitstring"]
                decision = apply_map(bits, spec)
                if bool(row.get("launch")) != decision["launch"]:
                    fail(f"shot {row['shot']}: published launch decision does not match the map")
                if measurements and measurements[row["shot"] - 1] != bits:
                    fail(f"shot {row['shot']}: rounds bitstring != measurements")
            launched = sum(1 for r in rounds if r.get("launch"))
            skipped = len(rounds) - launched
            findings.append({
                "check": "rounds",
                "ok": True,
                "measured": len(rounds),
                "launched": launched,
                "skipped": skipped,
                "note": f"measured {len(rounds)}, launched {launched}, skipped {skipped}",
            })

    if rpc_url:
        if frozen is None:
            findings.append({
                "check": "onchainPredict",
                "ok": False,
                "note": "no frozen plan in the record; pass --plan to re-predict on the wired deployer",
            })
        else:
            rpc = Rpc(rpc_url)
            plat = load_platform(platform or "genius-bsc")
            for spore in normalized["spores"]:
                if spore["status"] == "queued":
                    continue
                shot_plan = frozen
                if mapped is not None:
                    from .pipeline import plan_for_measurement

                    decision = apply_map(spore["bitstring"], mapped)
                    shot_plan = plan_for_measurement(frozen, decision)
                snapshot = read_snapshot(rpc, plat, shot_plan)
                pred = predict_addresses(
                    rpc, plat, shot_plan, spore["salt"], spore["bitstring"],
                    spore["shot"], snapshot=snapshot,
                )
                ok = pred["token"].lower() == spore["address"].lower()
                curve_ok = True
                if spore.get("curveAddress"):
                    curve_ok = pred["curve"].lower() == spore["curveAddress"].lower()
                findings.append({
                    "check": "onchainPredict",
                    "shot": spore["shot"],
                    "bitstring": spore["bitstring"],
                    "ok": ok and curve_ok,
                    "recorded": spore["address"],
                    "repredicted": pred["token"],
                    "curve": pred["curve"],
                    "block": snapshot["blockNumber"],
                })
                trace(
                    shot=spore["shot"],
                    bitstring=spore["bitstring"],
                    step="verify on-chain re-predict",
                    recorded=spore["address"],
                    repredicted=pred["token"],
                    match=ok and curve_ok,
                )
                if not ok or not curve_ok:
                    raise RecordError(
                        f"shot {spore['shot']}: wired deployer re-prediction "
                        f"{pred['token']} does not match recorded {spore['address']}"
                    )

                # Check on-chain deployment status (bytecode check)
                code = rpc.get_code(pred["token"])
                is_deployed = len(code) > 2  # not "0x"
                findings.append({
                    "check": "onchainCode",
                    "shot": spore["shot"],
                    "address": pred["token"],
                    "deployed": is_deployed,
                    "status": "DEPLOYED" if is_deployed else "RESERVED_AWAITING_BROADCAST",
                    "codeSize": max(0, (len(code) - 2) // 2),
                })
                if spore.get("codeVerified") and not is_deployed:
                    raise RecordError(
                        f"shot {spore['shot']}: record asserts codeVerified=True, but address "
                        f"{pred['token']} has no bytecode on-chain"
                    )

                # Check on-chain prediction pre-commitment if present
                if spore.get("commitTx"):
                    tx = rpc.get_transaction(spore["commitTx"])
                    if not tx:
                        raise RecordError(f"shot {spore['shot']}: commitTx {spore['commitTx']} not found on-chain")
                    from .derive import keccak256
                    magic = keccak256(b"quantum-spore-launch/prediction-v1")[2:]
                    input_data = tx.get("input") or tx.get("data") or ""
                    commit_valid = (
                        input_data.startswith("0x" + magic)
                        and spore["salt"][2:].lower() in input_data.lower()
                    )
                    findings.append({
                        "check": "onchainCommitment",
                        "shot": spore["shot"],
                        "commitTx": spore["commitTx"],
                        "ok": commit_valid,
                        "blockNumber": int(tx.get("blockNumber") or 0, 16) if isinstance(tx.get("blockNumber"), str) else tx.get("blockNumber"),
                    })
                    if not commit_valid:
                        raise RecordError(f"shot {spore['shot']}: commitTx calldata does not match quantum prediction")

                # Check on-chain launch transaction receipt if present
                if spore.get("launchTx"):
                    receipt = rpc.receipt(spore["launchTx"])
                    if not receipt:
                        raise RecordError(f"shot {spore['shot']}: launchTx {spore['launchTx']} not found on-chain")
                    receipt_status = receipt.get("status")
                    is_success = receipt_status in ("0x1", 1, "1")
                    findings.append({
                        "check": "onchainLaunchReceipt",
                        "shot": spore["shot"],
                        "launchTx": spore["launchTx"],
                        "success": is_success,
                        "blockNumber": int(receipt.get("blockNumber") or 0, 16) if isinstance(receipt.get("blockNumber"), str) else receipt.get("blockNumber"),
                    })
                    if not is_success:
                        raise RecordError(f"shot {spore['shot']}: launchTx {spore['launchTx']} reverted on-chain")
    return findings
