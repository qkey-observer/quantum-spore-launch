"""Public spore record: job provenance + ordered shots + frozen plan.

A record that fails any of these checks is refused rather than shown. Extra
checks used only by this program's verifier (recomputed salt, planHash,
prediction-before-launch) live in verify().
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .derive import BITSTRING_PATTERN, plan_hash, salt_from_bitstring
from .errors import RecordError

DEVICE = re.compile(r"^ibm_[a-z0-9_]{2,40}$")
JOB_ID = re.compile(r"^[A-Za-z0-9_-]{4,64}$")
ADDRESS = re.compile(r"^0x[0-9a-fA-F]{40}$")
TX = re.compile(r"^0x[0-9a-fA-F]{64}$")
STATUSES = frozenset({"queued", "awaiting_launch", "launched"})
EMPTY_SPORES = {"job": None, "plan": None, "spores": []}
SITE_KEYS = frozenset({"job", "plan", "spores"})


def fail(message: str = "Spore record is invalid. Check the job provenance and the spore queue.") -> None:
    raise RecordError(message)


def want(cond: Any, message: str | None = None) -> None:
    if not cond:
        fail(message or "Spore record is invalid. Check the job provenance and the spore queue.")


def is_record(value: Any) -> bool:
    return bool(value) and isinstance(value, dict) and not isinstance(value, list)


def timestamp(value: Any) -> str:
    want(isinstance(value, str) and len(value) <= 40)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        fail()
    utc = parsed.replace(tzinfo=parsed.tzinfo or timezone.utc).astimezone(timezone.utc)
    ms = utc.microsecond // 1000
    return utc.strftime("%Y-%m-%dT%H:%M:%S") + f".{ms:03d}Z"


def _normalize_job(input_job: Any) -> dict[str, Any]:
    want(is_record(input_job))
    want(isinstance(input_job.get("id"), str) and JOB_ID.match(input_job["id"]))
    want(isinstance(input_job.get("device"), str) and DEVICE.match(input_job["device"]))
    shots = input_job.get("shots")
    want(isinstance(shots, int) and not isinstance(shots, bool) and 1 <= shots <= 100_000)
    job: dict[str, Any] = {
        "id": input_job["id"],
        "device": input_job["device"],
        "shots": shots,
        "ranAt": timestamp(input_job.get("ranAt")),
    }
    for key in ("submittedAt", "completedAt"):
        if input_job.get(key) is None:
            continue
        job[key] = timestamp(input_job[key])
    if input_job.get("usageSeconds") is not None:
        usage = input_job["usageSeconds"]
        want(isinstance(usage, (int, float)) and not isinstance(usage, bool) and 0 < usage <= 86_400)
        job["usageSeconds"] = usage
    if input_job.get("queueDepthAtSubmit") is not None:
        depth = input_job["queueDepthAtSubmit"]
        want(isinstance(depth, int) and not isinstance(depth, bool) and 0 <= depth <= 1_000_000)
        job["queueDepthAtSubmit"] = depth
    if input_job.get("circuitDepth") is not None:
        depth = input_job["circuitDepth"]
        want(isinstance(depth, int) and not isinstance(depth, bool) and 1 <= depth <= 100_000)
        job["circuitDepth"] = depth
    qasm = input_job.get("circuitQasm")
    if isinstance(qasm, str) and qasm:
        want(len(qasm) <= 100_000)
        job["circuitQasm"] = qasm

    if input_job.get("measurements") is not None:
        measurements = input_job["measurements"]
        want(isinstance(measurements, list) and 1 <= len(measurements) <= 8192)
        want(len(measurements) == shots)
        width = len(measurements[0]) if measurements else 0
        want(isinstance(width, int) and 1 <= width <= 64)
        for shot in measurements:
            want(isinstance(shot, str) and len(shot) == width and BITSTRING_PATTERN.fullmatch(shot))
        job["measurements"] = list(measurements)

    if input_job.get("qubitLayout") is not None:
        layout = input_job["qubitLayout"]
        want(isinstance(layout, list) and 1 <= len(layout) <= 1024)
        seen: set[int] = set()
        for q in layout:
            want(isinstance(q, int) and not isinstance(q, bool) and 0 <= q <= 8191 and q not in seen)
            seen.add(q)
        if "measurements" in job:
            want(len(layout) == len(job["measurements"][0]))
        job["qubitLayout"] = list(layout)

    if input_job.get("counts") is not None:
        counts = input_job["counts"]
        want(is_record(counts))
        entries = list(counts.items())
        want(1 <= len(entries) <= 4096)
        total = 0
        for outcome, n in entries:
            want(isinstance(outcome, str) and BITSTRING_PATTERN.fullmatch(outcome))
            want(isinstance(n, int) and not isinstance(n, bool) and 0 <= n <= shots)
            total += n
        want(total == shots)
        if "measurements" in job:
            tally: dict[str, int] = {}
            for shot in job["measurements"]:
                tally[shot] = tally.get(shot, 0) + 1
            want(len(entries) == len(tally))
            for outcome, n in entries:
                want(tally.get(outcome) == n)
        job["counts"] = dict(entries)

    if input_job.get("calibration") is not None:
        raw = input_job["calibration"]
        want(is_record(raw))
        cal: dict[str, Any] = {"snapshotAt": timestamp(raw.get("snapshotAt"))}
        for key in ("readoutError", "twoQubitError", "singleQubitError"):
            if raw.get(key) is None:
                continue
            want(isinstance(raw[key], (int, float)) and not isinstance(raw[key], bool) and 0 <= raw[key] < 1)
            cal[key] = raw[key]
        for key in ("t1Micros", "t2Micros"):
            if raw.get(key) is None:
                continue
            want(isinstance(raw[key], (int, float)) and not isinstance(raw[key], bool) and 0 < raw[key] <= 100_000)
            cal[key] = raw[key]
        job["calibration"] = cal

    for key in ("readoutError", "twoQubitError"):
        if input_job.get(key) is None:
            continue
        val = input_job[key]
        want(isinstance(val, (int, float)) and not isinstance(val, bool) and 0 <= val < 1)
        job[key] = val
    return job


def _normalize_spore(item: Any, job: dict[str, Any], seen_shots: set[int]) -> dict[str, Any]:
    want(is_record(item))
    shot = item.get("shot")
    want(isinstance(shot, int) and not isinstance(shot, bool) and 1 <= shot <= job["shots"])
    want(shot not in seen_shots)
    seen_shots.add(shot)
    want(isinstance(item.get("bitstring"), str) and BITSTRING_PATTERN.fullmatch(item["bitstring"]))
    want(isinstance(item.get("salt"), str) and TX.match(item["salt"]))
    want(isinstance(item.get("address"), str) and ADDRESS.match(item["address"]))
    want(isinstance(item.get("status"), str) and item["status"] in STATUSES)
    spore: dict[str, Any] = {
        "shot": shot,
        "bitstring": item["bitstring"],
        "salt": item["salt"].lower(),
        "address": item["address"],
        "status": item["status"],
        "predictedAt": timestamp(item.get("predictedAt")),
    }
    if item.get("curveAddress") is not None:
        want(isinstance(item["curveAddress"], str) and ADDRESS.match(item["curveAddress"]))
        spore["curveAddress"] = item["curveAddress"]
    if item["status"] == "launched":
        want(isinstance(item.get("launchTx"), str) and TX.match(item["launchTx"]))
        spore["launchTx"] = item["launchTx"]
        spore["launchedAt"] = timestamp(item.get("launchedAt"))
        spore["codeVerified"] = item.get("codeVerified") is True
    return spore


def normalize_spores(input_value: Any) -> dict[str, Any]:
    """Refuse a compact public record that fails identity or shot-order checks."""
    if not is_record(input_value):
        fail()
    if any(key not in SITE_KEYS for key in input_value.keys()):
        fail()
    if input_value.get("job") is None:
        if isinstance(input_value.get("spores"), list) and input_value["spores"]:
            fail()
        return dict(EMPTY_SPORES)
    job = _normalize_job(input_value["job"])
    plan_in = input_value.get("plan")
    want(is_record(plan_in))
    want(isinstance(plan_in.get("chainId"), int) and not isinstance(plan_in["chainId"], bool) and plan_in["chainId"] >= 1)
    want(isinstance(plan_in.get("factoryAddress"), str) and ADDRESS.match(plan_in["factoryAddress"]))
    want(isinstance(plan_in.get("initiator"), str) and ADDRESS.match(plan_in["initiator"]))
    want(isinstance(plan_in.get("planHash"), str) and TX.match(plan_in["planHash"]))
    plan = {
        "chainId": plan_in["chainId"],
        "factoryAddress": plan_in["factoryAddress"],
        "initiator": plan_in["initiator"],
        "planHash": plan_in["planHash"].lower(),
    }
    want(isinstance(input_value.get("spores"), list) and len(input_value["spores"]) <= 64)
    seen: set[int] = set()
    spores = [_normalize_spore(item, job, seen) for item in input_value["spores"]]
    spores.sort(key=lambda s: s["shot"])
    return {"job": job, "plan": plan, "spores": spores}


def site_export(record: dict[str, Any]) -> dict[str, Any]:
    """Strip to the three-key compact export: job, plan, spores."""
    normalized = normalize_spores({
        "job": record["job"],
        "plan": record["plan"],
        "spores": record.get("spores") or [],
    })
    return normalized


def shots_in_order(spores: list[dict[str, Any]]) -> None:
    """Shots are consumed in order, never reused or skipped.

    Publishing a subset is allowed only as a prefix: 1..k. A hole (1, 3) is
    exactly how a sequence would be filtered for a flattering address.
    """
    if not spores:
        return
    numbers = [s["shot"] for s in spores]
    want(numbers == list(range(1, len(numbers) + 1)), "shots must be consumed in order, never skipped or reused")


def verify_derivation(record: dict[str, Any], frozen_plan: Any | None = None) -> list[dict[str, Any]]:
    """Recompute salt (and planHash if a frozen plan is supplied).

    This is the sceptic's check. It does not prove the bits came from a QPU.
    """
    normalized = normalize_spores(
        record if set(record.keys()) <= SITE_KEYS else {
            "job": record["job"],
            "plan": record["plan"],
            "spores": record.get("spores") or [],
        }
    )
    job = normalized["job"]
    findings: list[dict[str, Any]] = []
    if frozen_plan is not None:
        recomputed = plan_hash(frozen_plan)
        ok = recomputed == normalized["plan"]["planHash"]
        findings.append({
            "check": "planHash",
            "ok": ok,
            "expected": recomputed,
            "recorded": normalized["plan"]["planHash"],
        })
        if not ok:
            fail("planHash does not match canonical(frozen plan)")
    measurements = (job or {}).get("measurements") if job else None
    for spore in normalized["spores"]:
        recomputed_salt = salt_from_bitstring(spore["bitstring"])
        salt_ok = recomputed_salt == spore["salt"]
        shot_ok = True
        measured = None
        if measurements:
            measured = measurements[spore["shot"] - 1]
            shot_ok = measured == spore["bitstring"]
        findings.append({
            "check": "salt",
            "shot": spore["shot"],
            "bitstring": spore["bitstring"],
            "measuredBitstring": measured,
            "ok": salt_ok and shot_ok,
            "expectedSalt": recomputed_salt,
            "recordedSalt": spore["salt"],
            "address": spore["address"],
        })
        if not salt_ok:
            fail(f"shot {spore['shot']}: salt is not keccak256(utf8({spore['bitstring']}))")
        if not shot_ok:
            fail(f"shot {spore['shot']}: bitstring does not match job.measurements[{spore['shot']}]")
        if spore["status"] == "launched":
            pred = datetime.fromisoformat(spore["predictedAt"].replace("Z", "+00:00"))
            launched = datetime.fromisoformat(spore["launchedAt"].replace("Z", "+00:00"))
            if launched < pred:
                fail(f"shot {spore['shot']}: launchedAt is before predictedAt")
    return findings


def load_json(path: str | Path) -> Any:
    source = Path(path).read_text(encoding="utf-8")
    if len(source) > 512_000:
        fail("Spore record is too large.")
    try:
        return json.loads(source)
    except json.JSONDecodeError as exc:
        fail(f"Spore record is invalid JSON: {exc}")
