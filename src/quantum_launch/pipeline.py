"""autonomous and confirmed loops. Default is dry-run (no broadcast)."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable

from .cost import continuous_projection, format_ledger, job_cost, spore_unit_cost
from .derive import plan_hash, salt_from_bitstring
from .errors import LaunchError, MeasureError, QuantumLaunchError
from .keys import Signer, assert_initiator, load_signer
from .launch import run_launch
from .measure import run_ibm_job, utc_now
from .platforms import load_platform
from .predict import encode_launch_tx, predict_addresses, read_snapshot
from .publish import append_prediction, commit_onchain
from .record import normalize_spores, shots_in_order
from .rpc import Rpc
from .trace import trace

ConfirmFn = Callable[[str], str]


def plan_for_measurement(frozen: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
    """Overlay QPU-decoded fields onto the frozen infrastructure plan."""
    plan = json.loads(json.dumps(frozen))
    token = dict(plan.get("token") or {})
    token["name"] = decision["name"]
    token["symbol"] = decision["symbol"]
    if decision.get("imageUrl"):
        token["imageUrl"] = decision["imageUrl"]
        token["logo"] = decision["imageUrl"]
    if decision.get("description"):
        token["description"] = decision["description"]
    plan["token"] = token
    launch = dict(plan.get("launch") or {})
    launch["creatorTaxBps"] = decision["creatorTaxBps"]
    launch["buybackAndLock"] = bool(decision.get("buybackAndLock"))
    launch["feeDestination"] = decision.get("feeDestination") or launch.get("feeDestination") or "creator_payout"
    if decision.get("openingBuy") is not None:
        launch["openingBuy"] = str(decision["openingBuy"])
    if decision.get("launchConfigId") is not None:
        launch["launchConfigId"] = int(decision["launchConfigId"])
    plan["launch"] = launch
    if decision.get("quote"):
        plan["quote"] = dict(decision["quote"])
    if decision.get("creatorFeeRecipient"):
        launch["creatorFeeRecipient"] = decision["creatorFeeRecipient"]
        plan["launch"] = launch
    if decision.get("exemptAddresses") is not None:
        launch["exemptAddresses"] = list(decision["exemptAddresses"])
        plan["launch"] = launch
    if decision.get("website") is not None:
        token["website"] = decision["website"]
        plan["token"] = token
    if decision.get("x"):
        token["x"] = decision["x"]
        plan["token"] = token
    if decision.get("telegram"):
        token["telegram"] = decision["telegram"]
        plan["token"] = token
    return plan


def freeze_plan(plan: dict[str, Any], platform: dict[str, Any]) -> dict[str, Any]:
    frozen = json.loads(json.dumps(plan))
    chain = dict(frozen.get("chain") or {})
    chain["chainId"] = int(chain.get("chainId") or platform["chainId"])
    chain["name"] = chain.get("name") or platform.get("chainName")
    frozen["chain"] = chain
    frozen["factoryAddress"] = platform["factory"]
    frozen["deployerAddress"] = platform["deployer"]
    frozen["initiator"] = plan["initiator"]
    plat = dict(frozen.get("platform") or {})
    plat["name"] = plat.get("name") or platform.get("name")
    plat["id"] = platform.get("id")
    frozen["platform"] = plat
    quote = dict(frozen.get("quote") or {})
    if not quote.get("address"):
        quote.update(platform.get("quote") or {})
    frozen["quote"] = quote
    if plan.get("mapHash"):
        frozen["mapHash"] = plan["mapHash"]
    if plan.get("launchMap"):
        from .mapping import map_hash

        frozen["launchMap"] = plan["launchMap"]
        frozen["mapHash"] = map_hash(plan["launchMap"])
    return frozen


def load_plan(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def next_unused_shot(measurements: list[str], used: set[int]) -> int:
    for index, _bits in enumerate(measurements):
        shot = index + 1
        if shot not in used:
            return shot
    raise LaunchError("No unused shot left in this job record. Run a new measurement.")


def build_job_record(job: dict[str, Any], frozen: dict[str, Any], spores: list[dict[str, Any]]) -> dict[str, Any]:
    plan_meta = {
        "chainId": frozen["chain"]["chainId"],
        "factoryAddress": frozen["factoryAddress"],
        "initiator": frozen["initiator"],
        "planHash": plan_hash(frozen),
    }
    return {"job": job, "plan": plan_meta, "spores": spores}


def write_outputs(out_dir: Path, job: dict[str, Any], frozen: dict[str, Any], spores: list[dict[str, Any]]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    site_spores = [
        s for s in spores
        if s.get("status") in {"queued", "awaiting_launch", "launched"} and s.get("address")
    ]
    site = build_job_record(job, frozen, site_spores)
    (out_dir / "spores.json").write_text(json.dumps(site, indent=2) + "\n", encoding="utf-8")
    run = {
        "schema": "quantum-spore-launch/v1",
        "job": job,
        "plan": {**site["plan"], "frozen": frozen},
        "spores": site_spores,
        "rounds": [
            {
                "shot": s["shot"],
                "bitstring": s["bitstring"],
                "salt": s.get("salt"),
                "launch": s.get("status") != "skipped",
                "status": s.get("status"),
                "name": s.get("name"),
                "symbol": s.get("symbol"),
                "address": s.get("address"),
            }
            for s in spores
        ],
    }
    (out_dir / "run.json").write_text(json.dumps(run, indent=2) + "\n", encoding="utf-8")


def _confirm(mode: str, message: str, confirm_fn: ConfirmFn | None) -> str:
    if mode == "autonomous":
        return "YES"
    if confirm_fn is None:
        return input(message)
    return confirm_fn(message)


def run_pipeline(
    *,
    plan_path: str | Path,
    platform: str | dict[str, Any] = "genius-bsc",
    mode: str = "confirmed",
    backend: str | None = None,
    shots: int = 32,
    qubits: int = 4,
    rpc_url: str | None = None,
    job_path: str | Path | None = None,
    out_dir: str | Path = "runs/latest",
    broadcast: bool = False,
    publish_all_shots: bool = True,
    publish_onchain: bool = False,
    env: dict[str, str] | None = None,
    confirm_fn: ConfirmFn | None = None,
    max_spores: int | None = None,
    signer_url: str | None = None,
    signer_address: str | None = None,
    map_path: str | Path | None = None,
    circuit_kind: str = "hadamard",
    layers: int = 8,
    angle_seed: str = "qkey-entropy-v1",
) -> dict[str, Any]:
    if mode not in {"autonomous", "confirmed"}:
        raise QuantumLaunchError("mode must be autonomous or confirmed")
    platform_cfg = load_platform(platform)
    plan = load_plan(plan_path)
    launch_map = None
    if map_path:
        launch_map = json.loads(Path(map_path).read_text(encoding="utf-8"))
        from .mapping import map_hash

        plan = {**plan, "launchMap": launch_map, "mapHash": map_hash(launch_map)}
        if launch_map.get("schemaVersion") == 2:
            circuit_kind = launch_map["circuit"]["kind"]
            qubits = int(launch_map["circuit"]["qubits"])
            layers = int(launch_map["circuit"]["layers"])
            angle_seed = str(launch_map["circuit"]["angleSeed"])
    frozen = freeze_plan(plan, platform_cfg)
    hashed = plan_hash(frozen)
    trace(step="frozen plan", planHash=hashed, initiator=frozen["initiator"], factory=frozen["factoryAddress"])

    if job_path:
        job = json.loads(Path(job_path).read_text(encoding="utf-8"))
        if "job" in job and isinstance(job["job"], dict):
            job = job["job"]
    else:
        from os import environ
        job = run_ibm_job(
            backend_name=backend,
            shots=shots,
            num_qubits=qubits,
            api_key=(env or environ).get("QKEY_IBM_API_KEY") or (env or environ).get("QISKIT_IBM_TOKEN"),
            instance_crn=(env or environ).get("QKEY_IBM_INSTANCE_CRN"),
            circuit_kind=circuit_kind,
            layers=layers,
            angle_seed=angle_seed,
        )
    measurements = job.get("measurements")
    if not measurements:
        raise MeasureError("job record has no ordered per-shot measurements")
    if job.get("usageSeconds") in (None, 0):
        raise MeasureError("job record has no billed QPU seconds")
    wall = float(job.get("wallSeconds") or job["usageSeconds"])
    cost = spore_unit_cost(float(job["usageSeconds"]), int(job["shots"]))
    projection = continuous_projection(float(job["usageSeconds"]), wall, int(job["shots"]))
    print(format_ledger(projection, job_cost(float(job["usageSeconds"]))))

    out = Path(out_dir)
    predictions_path = out / "predictions.jsonl"
    spores: list[dict[str, Any]] = []
    used: set[int] = set()

    rpc = Rpc(rpc_url) if rpc_url else None
    snapshot = None
    if rpc is not None:
        snapshot = read_snapshot(rpc, platform_cfg, frozen)

    signer: Signer | None = None
    if broadcast:
        signer = load_signer(env, signer_url=signer_url, signer_address=signer_address)
        assert_initiator(signer, frozen["initiator"])

    def predict_one(shot: int) -> dict[str, Any]:
        bitstring = measurements[shot - 1]
        spec_bits = bitstring
        per = 1
        if launch_map is not None:
            from .mapping import load_map as _load_map

            per = int(_load_map(launch_map).get("shotsPerSpec") or 1)
            start = ((shot - 1) // per) * per
            group = measurements[start:start + per]
            if len(group) < per:
                return {
                    "shot": shot,
                    "bitstring": bitstring,
                    "salt": salt_from_bitstring(bitstring),
                    "status": "skipped",
                    "reason": "incomplete_spec",
                    "predictedAt": utc_now(),
                    "planHash": hashed,
                    "launch": False,
                }
            spec_bits = "".join(group)
            if (shot - 1) % per != 0:
                return {
                    "shot": shot,
                    "bitstring": bitstring,
                    "salt": salt_from_bitstring(spec_bits),
                    "status": "spec_cont",
                    "specBitstring": spec_bits,
                    "reason": "spec_cont",
                    "predictedAt": utc_now(),
                    "planHash": hashed,
                    "launch": False,
                }
        salt = salt_from_bitstring(spec_bits)
        decision = None
        shot_plan = frozen
        if launch_map is not None:
            from .mapping import apply_map

            decision = apply_map(spec_bits, launch_map)
            shot_plan = plan_for_measurement(frozen, decision)
            trace(
                shot=shot, bitstring=bitstring, step="map",
                launch=decision["launch"], name=decision["name"], symbol=decision["symbol"],
                tax=decision["creatorTaxBps"],
            )
            if not decision["launch"]:
                return {
                    "shot": shot,
                    "bitstring": bitstring,
                    "salt": salt,
                    "status": "skipped",
                    "reason": decision["reason"],
                    "name": decision["name"],
                    "symbol": decision["symbol"],
                    "predictedAt": utc_now(),
                    "planHash": hashed,
                    "launch": False,
                }
        trace(shot=shot, bitstring=bitstring, step="salt", salt=salt, planHash=hashed)
        if rpc is None:
            raise QuantumLaunchError("RPC URL is required to predict a CREATE2 address")
        snap = snapshot
        if launch_map is not None:
            snap = read_snapshot(rpc, platform_cfg, shot_plan)
        if snap is None:
            raise QuantumLaunchError("RPC URL is required to predict a CREATE2 address")
        prediction = predict_addresses(
            rpc, platform_cfg, shot_plan, salt, bitstring, shot, snapshot=snap,
        )
        return {
            "shot": shot,
            "bitstring": bitstring,
            "salt": salt,
            "address": prediction["token"],
            "curveAddress": prediction["curve"],
            "status": "awaiting_launch",
            "predictedAt": utc_now(),
            "planHash": hashed,
            "name": (decision or {}).get("name") or shot_plan.get("token", {}).get("name"),
            "symbol": (decision or {}).get("symbol") or shot_plan.get("token", {}).get("symbol"),
            "delaySeconds": (decision or {}).get("delaySeconds") or 0,
            "nextBackend": (decision or {}).get("nextBackend"),
            "nextShots": (decision or {}).get("nextShots"),
            "nextLayers": (decision or {}).get("nextLayers"),
            "specBitstring": spec_bits,
            "launch": True,
        }

    if publish_all_shots:
        print("Publishing every shot before any launch. Future addresses are fixed and auditable.")
        published = []
        limit = len(measurements) if max_spores is None else min(len(measurements), max_spores)
        for shot in range(1, limit + 1):
            spore = predict_one(shot)
            payload = {
                "shot": shot,
                "bitstring": spore["bitstring"],
                "salt": spore["salt"],
                "planHash": hashed,
                "jobId": job.get("id"),
                "launch": spore.get("status") != "skipped",
            }
            if spore.get("address"):
                payload["address"] = spore["address"]
                payload["curveAddress"] = spore.get("curveAddress")
            entry = append_prediction(predictions_path, payload)
            spore["publishedAt"] = entry["publishedAt"]
            published.append(spore)
            used.add(shot)
        spores = published
        write_outputs(out, job, frozen, spores)
        shots_in_order([
            {"shot": s["shot"]} for s in spores
        ] if all("shot" in s for s in spores) else [])

    launched = 0
    while True:
        if max_spores is not None and launched >= max_spores:
            break
        try:
            shot = next_unused_shot(measurements, used) if not publish_all_shots else None
        except LaunchError:
            break
        if publish_all_shots:
            remaining = [s for s in spores if s["status"] == "awaiting_launch"]
            if not remaining:
                break
            spore = remaining[0]
            shot = spore["shot"]
        else:
            spore = predict_one(shot)  # type: ignore[arg-type]
            payload = {
                "shot": shot,
                "bitstring": spore["bitstring"],
                "salt": spore["salt"],
                "planHash": hashed,
                "jobId": job.get("id"),
                "launch": spore.get("status") != "skipped",
            }
            if spore.get("address"):
                payload["address"] = spore["address"]
                payload["curveAddress"] = spore.get("curveAddress")
            entry = append_prediction(predictions_path, payload)
            spore["publishedAt"] = entry["publishedAt"]
            spores.append(spore)
            used.add(shot)  # type: ignore[arg-type]
            shots_in_order(spores)
            write_outputs(out, job, frozen, spores)

        bitstring = spore["bitstring"]
        trace(
            shot=spore["shot"],
            bitstring=bitstring,
            step="prediction published (before launch tx)",
            address=spore["address"],
            publishedAt=spore.get("publishedAt"),
        )
        prompt = (
            f"\nShot {spore['shot']} bitstring {bitstring}\n"
            f"salt      {spore['salt']}\n"
            f"token     {spore['address']}\n"
            f"curve     {spore['curveAddress']}\n"
            f"Type YES to sign+broadcast, SKIP to leave this shot predicted, QUIT to stop: "
        )
        decision = _confirm(mode, prompt, confirm_fn).strip().upper()
        if decision in {"QUIT", "Q", "NO"}:
            break
        if decision == "SKIP":
            continue
        if decision != "YES":
            print("expected YES, SKIP or QUIT")
            if mode == "confirmed":
                continue
            break

        if rpc is None or snapshot is None:
            raise QuantumLaunchError("RPC URL is required to launch")
        delay_s = int(spore.get("delaySeconds") or 0)
        if broadcast and delay_s > 0:
            wait = min(delay_s, 3600)
            trace(shot=spore["shot"], bitstring=bitstring, step="QPU-ordered delay", delaySeconds=wait)
            time.sleep(wait)
        if publish_onchain and broadcast and signer is not None:
            commit = commit_onchain(
                rpc, signer, frozen["initiator"], hashed, spore["salt"],
                spore["address"], spore["shot"], bitstring,
            )
            spore["commitTx"] = commit["commitTx"]
            spore["commitBlock"] = commit["commitBlock"]

        unsigned = encode_launch_tx(frozen, snapshot, spore["salt"])
        result = run_launch(
            rpc=rpc,
            signer=signer,
            unsigned=unsigned,
            bitstring=bitstring,
            shot=spore["shot"],
            predicted_token=spore["address"],
            predicted_curve=spore["curveAddress"],
            broadcast=broadcast,
            dry_run=not broadcast,
        )
        if result.get("broadcast"):
            spore["status"] = "launched"
            spore["launchTx"] = result["launchTx"]
            spore["launchedAt"] = utc_now()
            spore["codeVerified"] = result.get("codeVerified") is True
        else:
            spore["dryRun"] = True
            spore["unsigned"] = result.get("unsigned")
        write_outputs(out, job, frozen, spores)
        launched += 1
        if mode == "confirmed" and not broadcast:
            break
        if not publish_all_shots and not broadcast:
            break

    site = build_job_record(job, frozen, [s for s in spores if "address" in s])
    try:
        normalize_spores({"job": job, "plan": site["plan"], "spores": [
            {k: v for k, v in s.items() if k in {"shot", "bitstring", "salt", "address", "status", "predictedAt", "launchTx", "launchedAt", "codeVerified", "curveAddress"}}
            for s in site["spores"]
        ]})
    except Exception:
        # dry-run spores without a real address still fail site normalize if address missing
        pass
    return {
        "mode": mode,
        "broadcast": broadcast,
        "planHash": hashed,
        "jobId": job.get("id"),
        "device": job.get("device"),
        "spores": spores,
        "cost": cost,
        "projection": projection,
        "outDir": str(out),
    }
