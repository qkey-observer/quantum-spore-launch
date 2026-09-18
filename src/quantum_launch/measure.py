"""Submit a circuit to a real IBM backend and collect ordered per-shot bits.

Per-shot bitstrings come from the V2 Sampler BitArray (`get_bitstrings()`).
A run that only yields aggregated counts cannot name which shot a spore came
from and is refused. Probe that path before spending quota.
"""

from __future__ import annotations

import time
from collections import Counter
from datetime import datetime, timezone
from typing import Any

from .errors import MeasureError

DEVICE_PREFIX = "ibm_"


def utc_now() -> str:
    now = datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%S") + f".{now.microsecond // 1000:03d}Z"


def build_hadamard_circuit(num_qubits: int = 4):
    if num_qubits < 2 or num_qubits > 64:
        raise MeasureError("qubit count must be in 2..64 (bitstring length limits)")
    from qiskit import QuantumCircuit

    circuit = QuantumCircuit(num_qubits, num_qubits, name="qkey_shot")
    circuit.h(range(num_qubits))
    circuit.measure(range(num_qubits), range(num_qubits))
    return circuit


def build_entropy_circuit(num_qubits: int, layers: int, angles: list[float]):
    """Hardware-efficient layers: RY/RZ on every qubit, then CZ on a linear chain.

    Angles come from the published map (angleSeed). Depth is the billed-QPU
    lever: more layers → more QPU seconds → the public cost argument.
    """
    if num_qubits < 2 or num_qubits > 64:
        raise MeasureError("qubit count must be in 2..64")
    if layers < 1 or layers > 64:
        raise MeasureError("layers must be 1..64")
    need = num_qubits * layers * 2
    if len(angles) < need:
        raise MeasureError(f"need {need} published angles, got {len(angles)}")
    from qiskit import QuantumCircuit

    circuit = QuantumCircuit(num_qubits, num_qubits, name="qkey_entropy")
    k = 0
    for _ in range(layers):
        for q in range(num_qubits):
            circuit.ry(angles[k], q)
            k += 1
            circuit.rz(angles[k], q)
            k += 1
        for q in range(0, num_qubits - 1, 2):
            circuit.cz(q, q + 1)
        for q in range(1, num_qubits - 1, 2):
            circuit.cz(q, q + 1)
    circuit.measure(range(num_qubits), range(num_qubits))
    return circuit


def ordered_bitstrings_from_pub(pub: Any) -> list[str]:
    """Extract ordered per-shot bitstrings from a SamplerV2 PubResult.

    Looks for a BitArray with get_bitstrings(). Counts-only results raise.
    """
    data = getattr(pub, "data", pub)
    arrays: list[Any] = []
    names: list[str] = []
    if hasattr(data, "__iter__") and not isinstance(data, (str, bytes, dict)):
        try:
            names.extend(str(n) for n in list(data))
        except TypeError:
            pass
    for name in ("meas", "c", "creg", "measure", "c0"):
        if name not in names:
            names.append(name)
    for name in dir(data):
        if not name.startswith("_") and name not in names:
            names.append(name)
    for name in names:
        item = getattr(data, name, None)
        if item is None:
            try:
                item = data[name]
            except Exception:
                continue
        if callable(item) and name == "get_bitstrings":
            continue
        if hasattr(item, "get_bitstrings"):
            arrays.append(item)
    if not arrays and hasattr(data, "get_bitstrings"):
        arrays.append(data)
    if not arrays:
        raise MeasureError(
            "Sampler result has no BitArray.get_bitstrings(). "
            "Aggregated counts alone cannot name which shot a spore came from. "
            "Do not spend quota on this path."
        )
    bitstrings = list(arrays[0].get_bitstrings())
    if not bitstrings:
        raise MeasureError("get_bitstrings() returned an empty list")
    width = len(bitstrings[0])
    if width < 2 or width > 64:
        raise MeasureError(f"bitstring width {width} is outside 2..64")
    for bits in bitstrings:
        if len(bits) != width or any(ch not in "01" for ch in bits):
            raise MeasureError(f"not a measured bitstring: {bits!r}")
    return bitstrings


def counts_from_bitstrings(bitstrings: list[str]) -> dict[str, int]:
    return dict(Counter(bitstrings))


def probe_extraction(num_qubits: int = 4, shots: int = 8) -> dict[str, Any]:
    """Confirm the per-shot path works before a billed job is submitted."""
    samples = []
    for i in range(shots):
        samples.append(format(i % (1 << num_qubits), f"0{num_qubits}b"))
    qiskit_ok = False
    retrieved: list[str] | None = None
    try:
        from qiskit.primitives.containers.bit_array import BitArray

        array = BitArray.from_samples(samples, num_bits=num_qubits)
        retrieved = list(array.get_bitstrings())
        qiskit_ok = True
    except ImportError:
        class _Duck:
            def get_bitstrings(self):
                return list(samples)

        retrieved = ordered_bitstrings_from_pub(type("P", (), {"data": _Duck()})())
    if retrieved is None:
        raise MeasureError("extraction probe failed")
    if retrieved != samples and qiskit_ok:
        # BitArray may endian-swap; record what it actually returns.
        pass
    checked = ordered_bitstrings_from_pub(
        type("P", (), {"data": type("D", (), {"meas": type("B", (), {"get_bitstrings": lambda self: retrieved})() })()})()
    )
    return {
        "ok": True,
        "qiskitBitArray": qiskit_ok,
        "shots": shots,
        "width": len(checked[0]),
        "sample": checked[: min(4, len(checked))],
        "note": (
            "get_bitstrings() is available. Submit a real backend only after this probe passes. "
            if qiskit_ok
            else "qiskit is not installed; only the duck-typed extractor was probed."
        ),
    }


def usage_seconds_from_job(job: Any) -> float | None:
    """Billed QPU seconds. Never substitute zero for missing."""
    usage = None
    if hasattr(job, "usage"):
        try:
            usage = job.usage()
        except Exception:
            usage = None
    if isinstance(usage, (int, float)) and usage > 0:
        return float(usage)
    if isinstance(usage, dict):
        for key in ("quantum_seconds", "seconds", "qpu_seconds"):
            val = usage.get(key)
            if isinstance(val, (int, float)) and val > 0:
                return float(val)
    if hasattr(job, "metrics"):
        try:
            metrics = job.metrics()
        except Exception:
            metrics = None
        if isinstance(metrics, dict):
            nested = metrics.get("usage") if isinstance(metrics.get("usage"), dict) else metrics
            for key in ("quantum_seconds", "seconds", "usage"):
                val = nested.get(key) if isinstance(nested, dict) else None
                if isinstance(val, (int, float)) and val > 0:
                    return float(val)
    return None


def timestamps_from_job(job: Any) -> dict[str, str | None]:
    created = running = finished = None
    if hasattr(job, "metrics"):
        try:
            metrics = job.metrics() or {}
            stamps = metrics.get("timestamps") or {}
            created = stamps.get("created") or stamps.get("t_created")
            running = stamps.get("running") or stamps.get("t_running")
            finished = stamps.get("finished") or stamps.get("t_completed")
        except Exception:
            pass
    def _iso(value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, str) and value:
            return value if value.endswith("Z") or "+" in value else value
        return None
    return {
        "submittedAt": _iso(created),
        "ranAt": _iso(running) or _iso(created),
        "completedAt": _iso(finished),
    }


def layout_from_circuit(isa: Any) -> list[int] | None:
    layout = getattr(isa, "layout", None)
    if layout is None:
        return None
    for method in ("final_index_layout", "final_virtual_layout"):
        fn = getattr(layout, method, None)
        if callable(fn):
            try:
                mapping = fn()
            except TypeError:
                mapping = fn(filter_idle_qubits=False)
            if isinstance(mapping, dict):
                return [int(mapping[k]) for k in sorted(mapping)]
            if isinstance(mapping, (list, tuple)):
                return [int(x) for x in mapping]
    return None


def calibration_snapshot(backend: Any, qubit_layout: list[int] | None) -> dict[str, Any] | None:
    props = None
    if hasattr(backend, "properties"):
        try:
            props = backend.properties()
        except Exception:
            props = None
    if props is None:
        return None
    qubits = qubit_layout or list(range(min(4, getattr(backend, "num_qubits", 4) or 4)))
    t1s: list[float] = []
    t2s: list[float] = []
    readouts: list[float] = []
    for q in qubits:
        try:
            t1 = props.t1(q)
            if t1:
                t1s.append(float(t1) * 1_000_000.0)
        except Exception:
            pass
        try:
            t2 = props.t2(q)
            if t2:
                t2s.append(float(t2) * 1_000_000.0)
        except Exception:
            pass
        try:
            err = props.readout_error(q)
            if err is not None:
                readouts.append(float(err))
        except Exception:
            pass
    twoq: list[float] = []
    oneq: list[float] = []
    try:
        for gate in getattr(props, "gates", []) or []:
            name = getattr(gate, "gate", "")
            qubits_g = list(getattr(gate, "qubits", []) or [])
            err = None
            try:
                err = props.gate_error(name, qubits_g)
            except Exception:
                continue
            if err is None:
                continue
            if len(qubits_g) == 2 and (not qubit_layout or all(q in qubit_layout for q in qubits_g)):
                twoq.append(float(err))
            if len(qubits_g) == 1 and name in {"sx", "x", "id", "rz"} and (not qubit_layout or qubits_g[0] in qubit_layout):
                oneq.append(float(err))
    except Exception:
        pass

    def _mean(values: list[float]) -> float | None:
        return sum(values) / len(values) if values else None

    snap: dict[str, Any] = {"snapshotAt": utc_now()}
    readout = _mean(readouts)
    two = _mean(twoq)
    one = _mean(oneq)
    t1 = _mean(t1s)
    t2 = _mean(t2s)
    if readout is not None and 0 <= readout < 1:
        snap["readoutError"] = readout
    if two is not None and 0 <= two < 1:
        snap["twoQubitError"] = two
    if one is not None and 0 <= one < 1:
        snap["singleQubitError"] = one
    if t1 is not None and 0 < t1 <= 100_000:
        snap["t1Micros"] = t1
    if t2 is not None and 0 < t2 <= 100_000:
        snap["t2Micros"] = t2
    return snap


def run_ibm_job(
    *,
    backend_name: str | None,
    shots: int,
    num_qubits: int = 4,
    api_key: str | None = None,
    instance_crn: str | None = None,
    channel: str = "ibm_cloud",
    circuit_kind: str = "hadamard",
    layers: int = 8,
    angle_seed: str = "qkey-entropy-v1",
) -> dict[str, Any]:
    """Submit, wait, and return a job record. Requires qiskit-ibm-runtime."""
    try:
        from qiskit.qasm2 import dumps as qasm_dumps
        from qiskit.transpiler.preset_passmanagers import generate_preset_pass_manager
        from qiskit_ibm_runtime import QiskitRuntimeService, SamplerV2 as Sampler
    except ImportError as exc:
        raise MeasureError("qiskit and qiskit-ibm-runtime are required for a real backend job") from exc

    probe = probe_extraction(num_qubits=num_qubits, shots=min(8, shots))
    if not probe.get("qiskitBitArray"):
        raise MeasureError("BitArray.get_bitstrings() probe failed; refusing to spend quota")

    kwargs: dict[str, Any] = {}
    if api_key:
        kwargs["token"] = api_key
        kwargs["channel"] = channel
    if instance_crn:
        kwargs["instance"] = instance_crn
    service = QiskitRuntimeService(**kwargs) if kwargs else QiskitRuntimeService()
    if backend_name:
        backend = service.backend(backend_name)
    else:
        backend = service.least_busy(operational=True, simulator=False)
    name = getattr(backend, "name", None) or str(backend)
    if not str(name).startswith(DEVICE_PREFIX):
        raise MeasureError(f"backend {name!r} is not an ibm_* device; refusing to record it as a QPU job")

    queue_depth = None
    if hasattr(backend, "status"):
        try:
            status = backend.status()
            pending = getattr(status, "pending_jobs", None)
            if isinstance(pending, int) and pending >= 0:
                queue_depth = pending
        except Exception:
            queue_depth = None

    if circuit_kind == "hardware_efficient":
        from .mapping import circuit_angles

        circuit = build_entropy_circuit(
            num_qubits, layers, circuit_angles(angle_seed, num_qubits * layers * 2),
        )
    elif circuit_kind == "hadamard":
        circuit = build_hadamard_circuit(num_qubits)
    else:
        raise MeasureError(f"unknown circuit kind {circuit_kind!r}")
    pm = generate_preset_pass_manager(backend=backend, optimization_level=1)
    isa = pm.run(circuit)
    wall_start = time.time()
    submitted_at = utc_now()
    sampler = Sampler(mode=backend)
    job = sampler.run([isa], shots=shots)
    result = job.result()
    wall_end = time.time()
    pub = result[0]
    bitstrings = ordered_bitstrings_from_pub(pub)
    if len(bitstrings) != shots:
        raise MeasureError(f"got {len(bitstrings)} bitstrings, job claimed {shots} shots")
    counts = counts_from_bitstrings(bitstrings)
    usage = usage_seconds_from_job(job)
    if usage is None:
        raise MeasureError("job did not report billed QPU seconds; refusing to invent them")
    stamps = timestamps_from_job(job)
    layout = layout_from_circuit(isa)
    qasm = None
    try:
        qasm = qasm_dumps(isa)
    except Exception:
        try:
            qasm = isa.qasm()
        except Exception:
            qasm = None
    job_id = job.job_id() if callable(getattr(job, "job_id", None)) else getattr(job, "job_id", None)
    record = {
        "id": str(job_id),
        "device": str(name),
        "shots": shots,
        "submittedAt": stamps["submittedAt"] or submitted_at,
        "ranAt": stamps["ranAt"] or submitted_at,
        "completedAt": stamps["completedAt"] or utc_now(),
        "usageSeconds": usage,
        "wallSeconds": wall_end - wall_start,
        "measurements": bitstrings,
        "counts": counts,
        "circuitKind": circuit_kind,
        "circuitLayers": layers if circuit_kind == "hardware_efficient" else 0,
        "angleSeed": angle_seed if circuit_kind == "hardware_efficient" else None,
    }
    if queue_depth is not None:
        record["queueDepthAtSubmit"] = queue_depth
    depth = getattr(isa, "depth", None)
    if callable(depth):
        record["circuitDepth"] = int(depth())
    if qasm:
        record["circuitQasm"] = qasm[:100_000]
    if layout:
        record["qubitLayout"] = layout
    cal = calibration_snapshot(backend, layout)
    if cal:
        record["calibration"] = cal
    record["processor"] = str(getattr(getattr(backend, "processor_type", None), "family", "") or "") or None
    return record
