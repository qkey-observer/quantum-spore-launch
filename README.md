# quantum-spore-service

A read-only service that does two things with a quantum measurement:

1. **Derives the address a measured bitstring fixes**, on EVM chains and on Solana.
2. **Reads balances across those chains** and reports them as one figure, or says plainly why it cannot.

It never signs, never sends, never deploys, and holds no keys. There is no write
path in this process — not disabled behind a flag, absent.

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
npm test
```

## License

MIT.
