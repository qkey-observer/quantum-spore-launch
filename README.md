# quantum-spore-service

Tooling for a launch whose address is fixed by a quantum measurement rather than
chosen:

1. **Derive the address a measured bitstring fixes**, on EVM chains and on Solana.
2. **Read balances across those chains** and report them as one figure, or say
   plainly why that figure cannot be produced.
3. **Prepare a pump.fun launch** at the derived address: build the transaction,
   simulate it against the live program, and leave it unsigned.

The service in `src/server.mjs` has no write path — not disabled behind a flag,
absent — and no keys. The launch CLI is where signing and sending live, as two
separate commands that nothing else calls. [Read-only, enforced](#read-only-enforced)
says exactly which guarantee covers which part.

## Why a bitstring can fix an address

A measurement is useless as a commitment unless anyone can check it. Both chains
here support that, by different arithmetic:

| Chain family | Mechanism | Seed |
| --- | --- | --- |
| EVM | `CREATE2(deployer, salt, keccak256(initCode))` | `salt = keccak256(utf8(bitstring))` |
| Solana | Program Derived Address | `seed = sha256(utf8(bitstring))` |

Solana has no CREATE2. Its deterministic address is the first
`sha256(seed, bump, programId, "ProgramDerivedAddress")` that is **not** a point
on the ed25519 curve — an address nobody can hold a key for.

Different arithmetic, same property: publish the bitstring and the address
follows. Nothing has to be taken on trust.

```sh
npm run derive -- --bitstring 0111 \
  --program TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA
```

### What the derivation is checked against

Correctness here is not self-assessed:

- **EVM** reproduces all four vectors in [EIP-1014](https://eips.ethereum.org/EIPS/eip-1014).
- **Solana** reproduces `@solana/web3.js` on two vectors, one of which has an
  on-curve first candidate and forces the bump down to 254. That second vector
  exists because a broken off-curve check returns `false` for every input, takes
  the first candidate every time, and still looks correct.

`@solana/web3.js` is not a dependency. The derivation is built on
`@noble/curves` and `@noble/hashes` and nothing else.

## pump.fun: the mint is a keypair, so the order matters

A pump.fun mint is not a PDA. It is an ordinary ed25519 keypair — which is why
those addresses can end in `pump` at all, since vanity suffixes come from
grinding keys, not from deriving addresses. Deriving the mint from a bitstring
therefore works like this:

```
seed = sha256(utf8(bitstring))  →  ed25519 keypair  →  public key = the mint
bonding curve = PDA(["bonding-curve", mint], 6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P)
```

```sh
npm run derive -- --bitstring 1001001000010000000100000000000000000000000000000000000000000000 --pump
```

**The consequence is the whole reason to read this section: on this launchpad
the bitstring *is* the mint's private key.** Anyone who has it can recompute the
key and mint, so publishing a measurement before the launch hands away control
of the token. The commitment still works, in one order only:

1. measure,
2. publish the **address**,
3. launch,
4. publish the bitstring.

Step 4 is what makes step 2 checkable, and by then the key no longer controls
anything — pump.fun's mint authority is the bonding curve, not the keypair. That
sequence is a security property here, not a presentation choice, so this library
splits the two paths apart: `mintAddressFromBitstring` returns an address and
cannot leak a key, `mintKeypairFromBitstring` returns the secret and says in its
own return value what holding it means. The `--pump` CLI prints the address
only; a flag that printed the key would put it in a shell history every time
someone asked where the token would live.

The curve seeds are checked against three real pump.fun launches, whose curve
accounts appeared in the same transactions as their mints — on-chain evidence
rather than documentation. Their bumps are 255, 250 and 254, so the off-curve
search is genuinely exercised instead of always taking its first candidate.

## Preparing a launch

Three commands, because they carry different risks. `prepare` is arithmetic and
one read-only simulation; it cannot cost anything. `sign` is the only step that
reads a key. `send` is the only step that cannot be undone.

```sh
npm run launch -- prepare --bitstring <01…> --payer <your pubkey> \
  --name "Quantum Spore" --symbol SPORE --uri https://…/metadata.json \
  --out launch.json

npm run launch -- sign --in launch.json --bitstring <01…> \
  --payer-keypair ~/.config/solana/id.json

npm run launch -- send --in launch.signed.json --yes
```

`<bits>` is the measured bitstring itself, 0s and 1s; `--payer` is a base58
address. Arguments are checked before anything touches the network, so a
placeholder left in by accident costs one line of output rather than a stack
trace halfway through a round trip.

`prepare` simulates before it writes anything out, so a transaction that the
program would reject is visible before any key is involved. A simulation that
fails for want of lamports is reported as a funding problem rather than as a
broken transaction, because those two look identical on screen and mean
opposite things.

`sign` reads the fee payer's key from a file, never from an argument or an
environment variable, and zeroes both secrets when it is done. `send` refuses a
transaction with a blank signature slot before it opens a socket, and simulates
once more with signature checking on before it submits.

### Where the instruction layout comes from

pump publishes its own Anchor IDL on chain, in the account Anchor derives from
the program id with the seed `anchor:idl`. That account is where the
discriminator, the account names, their order and the argument types in
`src/launch/pump-create.mjs` come from.

Reading it instead of a guide was not pedantry:

| | discriminator | accounts | token program |
| --- | --- | --- | --- |
| `create` — what `sha256("global:create")` gives you | `181ec828051c0777` | 14 | legacy, plus a Metaplex metadata account |
| `create_v2` — what launches actually send | `d6904cec5f8b31b4` | 16 | Token-2022, no Metaplex account |

Both are in the IDL. In a window of 23 consecutive launches, 23 used
`create_v2` and none used `create`. A tool built from the instruction's name
would have produced a transaction the program rejects.

`npm run verify:pump` re-checks that against the chain: it reads the IDL, then
decodes recent real launches, feeds each one's own inputs back into this
builder, and requires the instruction to come out byte for byte identical —
accounts, flags and data. An IDL can go stale, and a builder written from a
stale IDL agrees with it perfectly while producing transactions that fail; only
the second check catches that. Eight of eight launches reproduced exactly on the
last run, including ones that append extra accounts and ones that send a short
argument buffer.

One account, `mayhem_token_vault`, has no seeds in the IDL. It is derived here
as the sol vault's token account for the new mint, which is what every sampled
launch passed.

The whole prepared transaction has also been simulated against mainnet and
accepted — `err: null`, 94,543 compute units, the logs showing the mint
initialised, the bonding curve's token account created, metadata written, the
supply minted and the mint authority handed away.

## Reading a treasury across chains

```sh
npm start                                  # runs on config/example.json
```

That works on a fresh clone, against the example configuration. For your own
holders, RPCs and assets:

```sh
cp config/example.json config/local.json   # config/local.json is gitignored
npm start                                  # local.json is preferred when present
npm start -- /path/to/other.json           # or name one directly
```

`PORT` (default 8787), `HOST` (default 127.0.0.1) and `ALLOWED_HOSTS` are read
from the environment. It binds loopback unless told otherwise: a service that
listens on every interface the moment it starts is one misconfigured firewall
away from being someone else's.

| Route | Returns |
| --- | --- |
| `GET /health` | liveness, and that this process is read-only |
| `GET /treasury` | every source and, when it can, their total |
| `GET /derivations` | the addresses the configured bitstring fixes |

Three outcomes, kept distinct on purpose:

| | `complete` | `summable` | `total` |
| --- | --- | --- | --- |
| All sources read, same units | `true` | `true` | the sum |
| All sources read, different units | `true` | `false` | `null`, parts kept |
| A source could not be read | `false` | — | `null`, failures named |

**A sum missing one of its terms is not a smaller total, it is an unknown one.**
Dropping an unreadable source and publishing what remains understates the
holding while looking perfectly healthy. That is the failure this is built
against, and the tests assert the partial figure never appears.

Assets are added only when they agree on decimals. Different decimals are
different units, and adding them yields a number that means nothing while
looking like a total — so the parts are reported and the total is withheld.

## Read-only, enforced

The service and the derivation library cannot write. The launch CLI can, in two
commands and nowhere else.

- `src/launch/broadcast.mjs` is the only file in the repository that can change
  anything on a chain. It is short on purpose: "this does not send" is then a
  claim you can check in one screen rather than one you have to trust.
- `bin/launch.mjs sign` is the only code that reads a key. It takes a file path,
  wipes the secrets afterwards, and prints no secret at any point.
- Nothing in the service imports either of them.
- Both RPC clients carry a method allowlist. A client that forwards any method
  is an open proxy wearing a library's name.
- `eth_call` is narrowed further to the specific contract the source names.
- Chains are identified before they are read: EVM by `eth_chainId`, Solana by
  its genesis hash. A URL repointed at another chain or cluster is caught.
- The HTTP surface is GET/HEAD, a fixed route set, no query parameters, and a
  host allowlist. Errors are never cached.
- Configuration carrying anything key-shaped is refused at load.

## Limits worth knowing

- An SPL balance is the sum of the owner's token accounts for that mint, not one
  lookup. Reading only the first understates it. A holder with more than 64 such
  accounts is refused rather than summed — measured against mainnet, one address
  held 12,159 for a single mint, which is not what a treasury looks like.
- A Solana reading is pinned to a slot, an EVM reading to a block. They are not
  the same instant and are reported separately rather than merged.
- No price feed. Figures are in their own units; nothing is converted.

## Testing

```sh
npm test            # offline; the launch builder is pinned to a captured real launch
npm run verify:pump # against mainnet: the IDL, then recent launches, byte for byte
```

`npm test` needs no network. `verify:pump` is the one that can tell you the
launchpad has changed under this code, so it is the one to run before a launch
rather than after.

## License

MIT.
