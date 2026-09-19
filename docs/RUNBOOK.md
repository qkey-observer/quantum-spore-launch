# Runbook

Default is dry-run. Nothing is signed or broadcast unless `--broadcast` is
passed. If `pytest` or `npm test` fail, stop — published predictions will
not reproduce.

## 0. Factory gate (read-only, no spend)

```sh
python -m quantum_launch inspect --platform genius-bsc \
  --initiator 0xCEB16Fa2cA6d9E9608Da614dA24336314542A707
```

If `canLaunch` is false the launch path is dead until the protocol owner
authorises that account. This program cannot whitelist itself.

Live CREATE2 predict (still read-only):

```sh
python -m quantum_launch predict --platform genius-bsc \
  --plan examples/launch-plan.example.json \
  --bitstring 0111
```

Expected token for that example plan and `0111`:
`0x999Ca7a3ba3cF02C29fc844caE603712222A2e81`. Changing `imageUrl` or any
other frozen field moves it. Nothing is deployed there: it is what the
deployer would produce, not a contract that exists.

## 0b. Probe the per-shot path (no QPU bill)

```sh
python -m quantum_launch probe-extraction
```

If this cannot see `BitArray.get_bitstrings()`, do not submit a billed job.
Aggregated counts cannot name shot *n*.

## 1. Software path, no IBM job

```sh
python -m quantum_launch derive --bitstring 0111
python -m quantum_launch derive --plan examples/launch-plan.example.json
python -m quantum_launch map --map examples/launch-map.direct.json \
  --bitstring "$(python -c 'print("0"*128)')"
python -m quantum_launch verify tests/fixtures/record.json
python -m quantum_launch verify examples/verify-live-0111.json \
  --rpc https://bsc-dataseed.binance.org
```

`tests/fixtures/record.json` is a software fixture (synthetic device fields).
After a real `run`, verify `runs/latest/run.json` and pass `--plan` so
`planHash` is checked against the frozen file.

Dry-run the loop against a captured job and a public RPC (view calls only):

```sh
python -m quantum_launch run \
  --plan examples/launch-plan.example.json \
  --platform examples/platform.genius-bsc.json \
  --map examples/launch-map.direct.json \
  --mode confirmed \
  --job tests/fixtures/job.json \
  --rpc "$QKEY_RPC_URL" \
  --out runs/dry \
  --max-spores 1
```

No `--broadcast`: the program predicts, writes the public record, and stops
before sending. `confirmed` waits for `YES` on stdin; `autonomous` does not
wait, but still does not send without `--broadcast`.

Replace `imageUrl` in the plan (and logo URLs in the map menus) with
**permanent public** URLs before a prediction you intend to keep. CREATE2
commits to those strings.

## 2. Real IBM job (billed)

Needs `QKEY_IBM_API_KEY` and `QKEY_IBM_INSTANCE_CRN`. This spends Open Plan
minutes or Pay-As-You-Go dollars.

Publish the map hash first. Then:

```sh
python -m quantum_launch measure \
  --backend ibm_fez \
  --shots 32 \
  --qubits 64 \
  --layers 16 \
  --circuit hardware_efficient \
  --out runs/job.json
python -m quantum_launch cost --job runs/job.json
```

Defaults match the public-claim map: 64 qubits, 16 layers. Then run the
pipeline with `--job runs/job.json` so you do not measure twice.

```sh
python -m quantum_launch run \
  --plan examples/launch-plan.example.json \
  --platform genius-bsc \
  --map examples/launch-map.direct.json \
  --job runs/job.json \
  --mode confirmed \
  --out runs/latest
```

## 3. Broadcast (mainnet, irreversible)

1. The initiating wallet must already pass `canLaunch`.
2. Freeze every plan field. Hash it. Publish the prediction.
3. Signer address **must** equal `plan.initiator`.
4. `--publish-onchain` sends a zero-value self-transaction whose calldata
   binds `planHash`, salt, predicted token, shot and bitstring **before**
   the launch tx. That is the chain timestamp.
5. On `--broadcast` the program sleeps `delaySeconds` from the map (capped
   at `maxDelaySeconds`).
6. Only then is `launchToken` sent. Check the receipt and `eth_getCode`.

```sh
python -m quantum_launch run \
  --plan plan.json \
  --platform examples/platform.genius-bsc.json \
  --map examples/launch-map.direct.json \
  --mode confirmed \
  --job runs/job.json \
  --rpc "$QKEY_RPC_URL" \
  --publish-onchain \
  --broadcast
```

`autonomous --broadcast` keeps going until shots in **this** job are
exhausted. A new IBM job is a separate invocation, so a runaway loop still
has a human-sized gate: you have to start the next measurement. Passing
`--broadcast` on a tight loop is how the monthly ledger becomes real.

## Chapel (BSC testnet 97)

genius.fun is **not** on chapel: `eth_getCode` of the mainnet factory and
wired deployer is empty there. Do not treat chain 97 as a genius.fun clone.

A full CREATE2 launch (predict → empty code → signed tx → receipt 0x1 →
`eth_getCode` 475 bytes → on-contract `bitstring() == "0111"`) was run on
**Anvil `--chain-id 97`**, recorded in `examples/chapel-rehearsal.json`.
That is a local chain with the same chain id, not a public chapel
transaction. Public chapel still needs a testnet signer and tBNB. Do not
reuse the mainnet initiator key.

```sh
python -m quantum_launch chapel-run --bitstring 0111
# --broadcast requires a testnet signer and chapel tBNB
```

## Signer

Never argv. Never logs. See `.env.example`.

- `QKEY_LAUNCH_PRIVATE_KEY`
- `QKEY_LAUNCH_KEYSTORE` + `QKEY_LAUNCH_KEYSTORE_PASSWORD`
- `QKEY_LAUNCH_KEY_FILE`
- Clef / hardware bridge: `--signer-url` and `--signer-address` (public
  address only; the device holds the key)

## After a launch

```sh
python -m quantum_launch verify runs/latest/run.json \
  --plan plan.json \
  --map examples/launch-map.direct.json \
  --rpc "$QKEY_RPC_URL"
```

A sceptic with those files, this repo, and no IBM credentials can recompute
every salt, the plan hash, the map hash, and (with `--rpc`) the CREATE2
address. They cannot pull the Runtime job by id. They cannot be shown a
proof that the bits came from a QPU.
