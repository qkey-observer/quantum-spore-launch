# quantum-spore-launch

Tooling for a token launch whose address is fixed by a quantum measurement
rather than chosen by whoever launches it.

1. **Derive the address a measured bitstring fixes** — by CREATE2 on EVM chains,
   by Program Derived Address on Solana, and as a pump.fun mint.
2. **Prepare the pump.fun launch at that address** — the create and, optionally,
   the creator's first buy in one transaction, simulated against mainnet and
   left unsigned.
3. **Let anyone check the commitment afterwards** — one command, public inputs,
   no account.
4. **Read balances across chains** through a read-only service, and report them
   as one figure or say plainly why that figure cannot be produced.

The service has no write path — not disabled behind a flag, absent — and no
keys. Signing and sending live in the launch CLI as two separate commands that
nothing else calls. [Read-only, enforced](#read-only-enforced) says exactly
which guarantee covers which part.

## Check it rather than trust it

Nothing here asks to be taken on someone's word. Three commands, no credentials:

```sh
npm ci && npm test       # offline: derivations against EIP-1014 and @solana/web3.js, launches pinned
npm run verify:pump      # mainnet: pump's own on-chain IDL, then real launches, byte for byte
npm run launch -- verify --bitstring <bits> --mint <published address> --onchain
```

The last is the one that matters to an outsider. Give it the bitstring
published after a launch and the address published before it: it recomputes the
address, and with `--onchain` confirms the token at that address exists, is a
Token-2022 mint, and has a curve owned by the pump program. A mismatch exits
non-zero.

## What this cannot prove

Worth stating before anything else, because the gap is real and a reader will
find it anyway.

**This code proves that the machinery is real, not that a measurement happened.**
It shows that an address follows from a bitstring by arithmetic anyone can
repeat, and that the launch transaction it builds is one the live program
accepts. Where the bitstring came from is a different kind of claim, and no
command in this repository settles it. IBM job results are scoped to the account
that ran them, so a third party holding a job id cannot fetch the result and
check it — that link cannot be made independently verifiable, and saying
otherwise would be the one lie that discredits everything else here.

What *is* verifiable is the ordering. Publish the address, launch, then publish
the bitstring: `verify` confirms the two correspond, which establishes that the
address was fixed in advance rather than chosen afterwards to fit. That is a
commitment, not a provenance proof, and the difference matters.

Also: an address appearing in a config file is not evidence that anyone owns or
controls it, and finding an account at an address is not an audit.

## Why a bitstring can fix an address

A measurement is useless as a commitment unless anyone can check it. Three
mechanisms support that, and they do not all carry the same risk:

| Where | Mechanism | Seed | Does a key exist for the address? |
| --- | --- | --- | --- |
| EVM | `CREATE2(deployer, salt, keccak256(initCode))` | `salt = keccak256(utf8(bitstring))` | No — it is a contract address |
| Solana, any program | Program Derived Address | `seed = sha256(utf8(bitstring))` | No — the address is chosen *off* the ed25519 curve |
| Solana, pump.fun mint | ed25519 keypair | `seed = sha256(utf8(bitstring))` | **Yes — and the bitstring is it** |

The first two can be published at any time; nothing follows from knowing the
seed except the address. The third cannot, and
[the next section](#pumpfun-the-mint-is-a-keypair-so-the-order-matters) is about
why.

```sh
npm run derive -- --bitstring 0111 --program TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA
npm run derive -- --bitstring 1001001000010000000100000000000000000000000000000000000000000000 --pump
```

### What the derivation is checked against

Correctness here is not self-assessed:

- **EVM** reproduces all four vectors in [EIP-1014](https://eips.ethereum.org/EIPS/eip-1014).
- **Solana PDAs** reproduce `@solana/web3.js` on two vectors, one of which has an
  on-curve first candidate and forces the bump down to 254. That vector exists
  because a broken off-curve check returns `false` for every input, takes the
  first candidate every time, and still looks correct.
- **pump.fun mints** reproduce `@solana/web3.js`'s `Keypair.fromSeed`, and the
  bonding-curve seeds reproduce three real launches whose curve accounts appear
  in the same transactions as their mints. Their bumps are 255, 250 and 254, so
  the off-curve search is genuinely exercised.

`@solana/web3.js` is a cross-check, not a dependency. Everything here is built
on `@noble/curves` and `@noble/hashes`.

## pump.fun: the mint is a keypair, so the order matters

A pump.fun mint is not a PDA. It is an ordinary ed25519 keypair — which is why
those addresses can end in `pump` at all, since vanity suffixes come from
grinding keys, not from deriving addresses:

```
seed = sha256(utf8(bitstring))  →  ed25519 keypair  →  public key = the mint
bonding curve = PDA(["bonding-curve", mint], 6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P)
```

**On this launchpad the bitstring *is* the mint's private key.** Anyone who has
it can recompute the key and launch the token themselves, so publishing a
measurement before the launch hands away the token. The commitment still works,
in one order only:

1. measure,
2. publish the **address**,
3. launch,
4. publish the bitstring.

Step 4 is what makes step 2 checkable, and by then the key controls nothing —
the launch hands the mint authority to the bonding curve. That sequence is a
security property, not a presentation choice, so the library keeps the two paths
apart: `mintAddressFromBitstring` returns an address and cannot leak a key;
`mintKeypairFromBitstring` returns the secret and says in its own return value
what holding it means. The `--pump` CLI prints the address only — a flag that
printed the key would put it in a shell history every time someone asked where
the token would live.

## Preparing a launch

Three commands, because they carry different risks. `prepare` is arithmetic and
read-only queries; it cannot cost anything. `sign` is the only step that reads a
key. `send` is the only step that cannot be undone.

```sh
npm run launch -- prepare --bitstring <bits> --payer <your address> \
  --name "Quantum Spore" --symbol SPORE --uri https://…/metadata.json \
  --buy 0.5 --out launch.json

npm run launch -- sign --in launch.json --bitstring <bits> \
  --payer-keypair ~/.config/solana/id.json

npm run launch -- send --in launch.signed.json --yes
```

`<bits>` is the measured bitstring itself, 0s and 1s; `--payer` is a base58
address. Arguments are checked before anything touches the network, so a
placeholder left in by accident costs one line of output rather than a stack
trace halfway through a round trip.

**The node is identified before it is trusted.** `prepare` and `send` read the
genesis hash behind `--rpc` and refuse anything but mainnet unless `--cluster`
names the other cluster. Without that, a devnet endpoint produces a transaction
that is valid, simulates cleanly and signs — on the wrong network, with every
line of output reading as if it were real. The prepared file records its
cluster, and `send` refuses to submit it anywhere else.

`prepare` simulates before it writes anything out, so a transaction the program
would reject is visible before any key is involved. A simulation that fails for
want of lamports is reported as a funding problem rather than a broken
transaction, because the two look identical on screen and mean opposite things.
The file it writes does not contain the bitstring.

`sign` reads the fee payer's key from a file, never from an argument or an
environment variable, and zeroes both secrets when it is done. `send` refuses a
blank signature slot before it opens a socket, checks the cluster, and simulates
once more with signature checking on before it submits.

### Where the instruction layout comes from

pump publishes its own Anchor IDL on chain, in the account Anchor derives from
the program id with the seed `anchor:idl`. That account — not a guide — is where
the discriminators, account names, their order and the argument types come
from.

Reading it instead of a guide was not pedantry:

| | discriminator | accounts | token program |
| --- | --- | --- | --- |
| `create` — what `sha256("global:create")` gives you | `181ec828051c0777` | 14 | legacy, plus a Metaplex metadata account |
| `create_v2` — what launches actually send | `d6904cec5f8b31b4` | 16 | Token-2022, no Metaplex account |

Both are in the IDL, and the program's own `Global` account carries a
`create_v2_enabled` flag. In a window of 23 consecutive launches, 23 used
`create_v2` and none used `create`. A tool built from the instruction's name
would have produced a transaction the program rejects.

`npm run verify:pump` re-checks all of this against the chain: it reads the IDL,
then decodes recent real launches, feeds each one's own inputs back into the
builders, and requires every instruction — the create and the dev buy — to come
out byte for byte identical, accounts, flags and data. An IDL can go stale, and
a builder written from a stale IDL agrees with it perfectly while producing
transactions that fail; only the second check catches that. On 2026-10-10 every
sampled launch reproduced exactly, including ones that append extra accounts and
ones that send a short argument buffer.

One `create_v2` account, `mayhem_token_vault`, has no seeds in the IDL. It is
derived as the sol vault's token account for the new mint, which is what every
sampled launch passed.

### The dev buy, and why it shares the transaction

`--buy <SOL>` adds pump's `buy_v2` to the same transaction as the create. A
create on its own leaves the first buy of the token to whoever is watching, and
the creator holding none of it; split across two transactions, the gap between
them is that same window.

It is optional because launches genuinely differ. Of 34 consecutive launches on
2026-10-10, 21 put a recognisable buy in the same transaction — `buy_v2` 10,
`buy_exact_sol_in` 6, the older `buy` 5 — 8 were a bare create, and 5 used an
instruction the published IDL does not name at all. That last group is the
plainest evidence for checking against live launches and not only the IDL: the
program has already moved past the description it publishes of itself.

Two of `buy_v2`'s 27 accounts cannot be derived. `fee_recipient` and
`buyback_fee_recipient` are chosen from pools the program keeps in its `Global`
account — seven and eight of them — and the IDL gives them no seeds. So
`prepare` reads `Global` rather than guessing, and checks the chosen pair
against those pools before building: a recipient the program does not recognise
fails the whole transaction, and at a launch that failure arrives too late to
act on. The other 25 follow from the mint and the buyer.

The amount is a deliberate under-estimate. `buy_v2` takes a token amount and a
spending cap and prices the tokens itself, so asking for more than the cap
covers reverts everything. This asks for about 1% fewer tokens than the budget
affords and sets the cap at the budget exactly: a reverted launch cannot be
retried at the same moment, and the cap means the shortfall can never become an
overspend. Fees — 0.95% platform plus 0.05% creator, read from `Global` — come
off before the curve. The quote does not try to reproduce pump's own client,
whose input cannot be recovered from the transactions it sends; it only has to
stay under the cap it sets.

Two things had to be learned from the chain rather than reasoned out:

- **A create and a buy do not fit in one legacy transaction.** Together they
  name more accounts than 1232 bytes can hold. Real launches are version 0
  transactions using one address lookup table, so this compiles version 0 the
  same way and the message drops from about 1,400 bytes to under 800. Signers
  and the program id of a top-level instruction stay in the static list, as
  they do in live launches; everything the table contains moves into it.
- **`buy_v2` does not create the buyer's token account for the new mint.** It
  requires it. Simulation says so in as many words — `AnchorError caused by
  account: associated_base_user. AccountNotInitialized` — so an idempotent
  account creation sits between the create and the buy.

### What has been simulated against mainnet

Read-only simulations, 2026-10-10. Nothing was signed or sent.

| Transaction | Result | Compute units |
| --- | --- | --- |
| `create_v2` alone, legacy | `err: null` | 94,543 |
| `create_v2` + account creation + `buy_v2`, version 0 | `err: null` | 204,837 |

The first run's logs show the mint initialised, the curve's token account
created, metadata written, the supply minted and the mint authority handed to
the curve.

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

- `src/launch/broadcast.mjs` is the only file that can change anything on a
  chain, and it calls exactly three methods: `getLatestBlockhash`,
  `simulateTransaction`, `sendTransaction`. It is short on purpose — "this does
  not send" is then a claim you can check in one screen rather than one you have
  to trust.
- `bin/launch.mjs sign` is the only code that reads a key. It takes a file path,
  wipes the secrets afterwards, and prints no secret at any point.
- Nothing in the service imports either of them.
- Every other read — the service's, and the launch CLI's reads of `Global`, the
  lookup table and the cluster — goes through RPC clients with a method
  allowlist. A client that forwards any method is an open proxy wearing a
  library's name. `eth_call` is narrowed further to the specific contract a
  source names.
- Chains are identified before they are read: EVM by `eth_chainId`, Solana by
  its genesis hash — in the service, and in `prepare` and `send`. A URL
  repointed at another chain or cluster is caught.
- The HTTP surface is GET/HEAD, a fixed route set, no query parameters, and a
  host allowlist. Errors are never cached.
- Configuration carrying anything key-shaped is refused at load.

`scripts/verify-pump.mjs` is a standalone checker. It only reads.

## Limits worth knowing

The service:

- An SPL balance is the sum of the owner's token accounts for that mint, not one
  lookup. Reading only the first understates it. A holder with more than 64 such
  accounts is refused rather than summed — measured against mainnet, one address
  held 12,159 for a single mint, which is not what a treasury looks like.
- A Solana reading is pinned to a slot, an EVM reading to a block. They are not
  the same instant and are reported separately rather than merged.
- No price feed. Figures are in their own units; nothing is converted.

The launch:

- **pump can change its program.** This is checked against the program's own
  IDL and against live launches, not frozen in place. Run `npm run verify:pump`
  before a launch rather than after.
- **The lookup table is someone else's account.** It is read and used as found,
  and `verify:pump` reports its size. If it moves, `--lookup-table` points
  elsewhere.
- **The dev buy buys about 1% less than the budget could**, by design; see above.
  The first recipient in each `Global` pool is used — any member is valid.
  `buy_exact_sol_in`, which some launches use instead, takes the SOL amount
  directly and would not need the margin; it is not implemented here.
- **`--no-simulate` is for looking, not launching.** It skips the cluster check
  and uses a placeholder blockhash, so what it produces cannot be signed into
  anything real.

## Layout

```
src/derive/index.mjs       CREATE2, PDAs, base58 — the arithmetic
src/derive/pump.mjs        bitstring → mint and bonding curve; the key path kept apart
src/launch/solana-tx.mjs   legacy and version 0 messages, lookup tables, unsigned transactions
src/launch/pump-create.mjs create_v2, from the on-chain IDL
src/launch/pump-buy.mjs    buy_v2, Global, the quote, the account creation it needs
src/launch/broadcast.mjs   the only code that writes to a chain
bin/launch.mjs             prepare / sign / send / verify
src/server.mjs             the read-only service
src/chains/                allowlisted EVM and Solana RPC clients
scripts/verify-pump.mjs    the builders against the live program
```

## Testing

```sh
npm test            # offline; launches are pinned to captured real transactions
npm run verify:pump # mainnet: the IDL, recent launches, Global and the lookup table
```

`npm test` needs no network and runs in CI on every push. `verify:pump` is the
one that can tell you the launchpad has changed under this code, so it is the
one to run before a launch — it is deliberately not in CI, because a check that
fails whenever a public RPC rate-limits teaches a reader to ignore it.

## License

MIT.
