# Record schema and self-checks

Two shapes are written under `--out`:

1. `spores.json` — compact public export with three keys: `job`, `plan`,
   `spores`. Extra top-level keys are refused.
2. `run.json` — schema `quantum-spore-launch/v1`. The same job plus the
   frozen plan, publication timestamps, cost, rounds (including skips), and
   launch receipts.

## Job (same session; anything missed is gone)

| Field | Why |
| --- | --- |
| `id`, `device`, `submittedAt`, `ranAt`, `completedAt` | identity of the run |
| **`measurements`** | ordered per-shot bitstrings. A spore names the shot it came from; aggregated counts alone make the cycle impossible |
| `counts` | the distribution’s noise is the strongest signal of a real measurement |
| `circuitQasm` | what was actually run (transpiled) |
| `qubitLayout` | physical qubits the transpiler used; width must equal the bitstring width; no qubit twice |
| `calibration` | T1/T2, readout and gate error; cross-checkable against IBM’s published properties |
| `queueDepthAtSubmit` | evidence of a real shared queue |
| `usageSeconds` | billed QPU time, **not** wall clock. Must be `> 0` if present |

Per-shot results come from SamplerV2 `BitArray.get_bitstrings()`. Confirm
that path with `quantum-launch probe-extraction` before spending quota.

## Plan

`chainId`, `factoryAddress`, `initiator`, `planHash`. A salt alone never
determines an address. `planHash = keccak256(utf8(canonical(frozenPlan)))`
with keys sorted recursively. `run.json` also stores `plan.frozen`.

When a launch map is used, `mapHash` is stored the same way (canonical JSON,
`comment` stripped).

## Spores

`shot` (1-based, consumed in order, never reused), `bitstring`, `salt`,
`address`, `status`, `predictedAt`.

| status | meaning |
| --- | --- |
| `queued` | predicted, not yet launched |
| `awaiting_launch` | prediction published, waiting for broadcast |
| `launched` | requires `launchTx` and `launchedAt` |
| `skipped` | map said do not launch (in `run.json` rounds) |
| `spec_cont` | continuation shot of a multi-shot spec; not a second token |

`codeVerified` is true only after `eth_getCode` shows bytecode.

`run.json` stores `rounds`: every shot in order, including skips and
`spec_cont`. `spores.json` keeps launched / awaiting / queued rows.

`tally()` counts a launch on the **head** shot of a spec (`specRole=head`)
so two-shot specs do not double-count.

## Self-checks

The same refuses as `normalize_spores`:

- spores without a job
- reused or out-of-range shot
- launched without a receipt
- non-`ibm_*` device name
- readout/gate error ≥ 1 (a percentage stuffed into a fraction field)
- unparseable timestamps
- counts that do not match the per-shot data
- ordered shots that do not account for every claimed shot
- layout narrower than the bitstrings, or a physical qubit used twice
- ragged bit widths
- billed QPU time of zero
- prediction missing `chainId` / `factoryAddress` / `initiator` / `planHash`
- unknown top-level keys on the compact export

The verifier additionally recomputes `salt` from the bitstring and
`planHash` from the frozen plan, refuses a launch timestamp that precedes
its prediction, and with `--rpc` re-calls `predictLaunchAddresses` on the
wired deployer.
