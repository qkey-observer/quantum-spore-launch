# Launch maps

A launch map is the public rule that turns measured bits into a launch spec.
Hash it, publish it, **then** submit the IBM job. Changing any field after
seeing bits is a different `mapHash`.

```
mapHash = keccak256(utf8(canonical_json(map_without_comment)))
```

`comment` is stripped before hashing so a note can be edited without moving
the hash. Everything else, including menus and `circuit.angleSeed`, is in
the hash.

Two encodings ship in this repo.

## Schema 1 — table (demo only)

File: `examples/launch-map.example.json`. Width 4. A name table, tax tiers,
and delay tiers. Use it to learn the CLI. Do not present it as the public
claim.

Bit 0 (MSB) is launch vs skip (`launchWhen: "1"`). Skipped shots stay in
`run.json` rounds so “measured N, launched M, skipped K” is checkable.

## Schema 2 — direct (public-claim path)

File: `examples/launch-map.direct.json`.

| | |
| --- | --- |
| `schemaVersion` | 2 |
| `mode` | `direct` |
| `width` | 64 (one SamplerV2 shot) |
| `shotsPerSpec` | 2 (concatenate two ordered shots → 128-bit spec) |
| `msbFirst` | true |
| `alphabet` | `ABCDEFGHJKLMNPQRSTUVWXYZ23456789` (32 chars, 5 bits each) |
| circuit | 64-qubit hardware-efficient, **16 layers**, `angleSeed` `qkey-entropy-v1` |
| `maxDelaySeconds` | 3600 (honoured on `--broadcast`) |

Salt is keccak of the **concatenated** bitstring, not of each 64-bit shot
alone. Shot 1 of a pair is the head (`specRole=head`); shot 2 is
`spec_cont` and is not counted as a second launch.

### 128-bit field layout

Indices are 0-based, MSB first, across the concatenated spec.

| field | bits | encoding |
| --- | --- | --- |
| `launch` | 0 | `1` = launch, `0` = skip |
| `creatorTaxBps` | 1–8 | integer, capped at 1000 |
| `delaySeconds` | 9–14 | integer × 10, capped at 3600 |
| `buyback` | 15 | 1 = buyback and lock |
| `feeDestination` | 16 | 0 = `creator_payout`, 1 = `foundation` |
| `quote` | 17–18 | index into `menus.quotes` |
| `logo` | 19–20 | index into `menus.logos` |
| `launchConfigId` | 21–22 | integer |
| `openingBuy` | 23–28 | integer × 1 |
| `name` | 29–48 | four alphabet characters (5 bits each) |
| `symbol` | 49–63 | three alphabet characters |
| `extraName` | 64–83 | four more name characters appended |
| `feeRecipient` | 84–91 | index into `menus.feeRecipients` |
| `exemptions` | 92–95 | bit mask over `menus.exemptCandidates` |
| `nextLayers` | 96–99 | next job’s layer count (decoded from the field) |
| `nextShots` | 100–103 | index into `menus.shotTiers` |
| `nextBackend` | 104–106 | index into `menus.backends` |
| `website` | 107 | 1 = `{websiteBase}/{salt}` |
| `x` | 108–112 | social handle from alphabet |
| `telegram` | 113–117 | social handle from alphabet |
| unused | 118–127 | reserved |

Menus are part of the hashed map. Placeholder logo URLs (`example.invalid`)
must be replaced with permanent public URLs **before** a prediction you
intend to keep — CREATE2 commits to the image string.

### What the QPU does not choose

Initiator, factory, wired deployer, chain id, and the secp256k1 signer.
Those are classical and must be real.

### Check a spec without a QPU

```sh
python -m quantum_launch map \
  --map examples/launch-map.direct.json \
  --bitstring "$(python -c 'print("0"*128)')"
```

`mapHash` is printed first. A third party with the published map file and
the bitstring can recompute every decoded field.
