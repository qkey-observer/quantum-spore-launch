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

## Reading a treasury across chains

```sh
cp config/example.json config/local.json   # edit holders, RPCs and assets
npm start
```

`GET /treasury` returns every source and, when it can, their total.

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
