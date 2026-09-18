# What may and may not be claimed

Overclaiming is the failure mode that destroys the one asset this program
has: its numbers can be checked. This page is the allowed language.

## Independently checkable by a third party

Device status, queue depth, processor generation, qubit counts. Anyone can
compare these with IBM’s own pages.

## Cross-checkable

The calibration snapshot against IBM’s published backend properties for that
backend and timestamp. Agreement is evidence the snapshot is of that device
at that time. Disagreement is a reason to distrust the record.

## Self-attested

The job record itself. IBM Runtime job results are private to the account. A
third party **cannot** retrieve someone else’s job by id. Say so plainly.
Fabricated results usually fail on the noise profile of `counts`, but that
is evidence, not proof.

## Not provable with current technology

That a given bitstring came from a quantum processor rather than a random
number generator. Verifiable quantum randomness is an open research problem.
Do not imply otherwise.

## Autonomy

`autonomous` mode in this program is automatic: measure → predict → publish
→ sign → broadcast → next shot, with no operator prompt. That sentence is
true of **this program**.

Do not attribute any of those actions to IBM. IBM does not launch tokens,
does not endorse this project, and is not affiliated with it. The honest
form is: *a measurement run on IBM hardware we rented*.

## Publish before launch

A prediction that appears only after the launch transaction exists proves
only that some bitstring maps to that address. The chain timestamp of a
prediction-commit transaction (or any other public record that predates the
launch tx) is what proves the prediction came first.

## Recommended public wording

**Say this:**

> Whether a token launches, what it is called, its tax, delay, buyback flag,
> fee destination and CREATE2 address are all decoded from a measurement
> taken on rented IBM hardware, under a rule-file that was hashed and
> published before the job. An open-source program then broadcasts the
> launch transaction. IBM does not issue the token, does not sign, and is
> not affiliated. A third party can recompute every field from the published
> bits; they cannot currently prove those bits came from a quantum processor
> rather than a RNG.

**Do not say:** “IBM launched this token.” “The quantum computer signed.”
“These bits are proven quantum.” “genius.fun or IBM endorses this program.”

Call it an open-source **quantum-measurement token launch**. The worked
example is genius.fun. That is an integration, not an affiliation.

The 4-bit name table is a cheap demo. The public-claim path is
`examples/launch-map.direct.json`: **64 qubits × 16 layers**, **two shots
per token** (128 bits of spec). Name/symbol from a published alphabet.
Quote, logo, config id, opening buy, fee recipient, exemption mask,
website, socials, and the *next* job’s backend/shots/layers are sliced
from those bits. The program waits `delaySeconds` before broadcast.
Cost goes up with width, depth, and how long the QPU stays in the loop.

## What stays classical on purpose

Initiator wallet, factory, wired deployer, chain id, and the secp256k1
signer. The QPU does not hold keys and does not call `launchToken`. The
program signs after the measurement.

Quote asset and image URL **can** come from the published map menus. Those
menus are classical lists, hashed with the map before the job. The bits
only choose an index. Placeholder URLs (`example.invalid`) are not a live
logo; replace them before a prediction you intend to keep.

## CREATE2 Immutability vs Bonding Curve MEV

- **CREATE2 protects**: The deployer cannot alter token name, tax rate, fee
  recipient, or liquidity curve without moving the predicted address. It also
  prevents factory nonce-hijacking.
- **CREATE2 does not protect**: Secondary trading on the bonding curve or
  PancakeSwap. Once a token is deployed or a transaction enters the public
  mempool, public trades are subject to standard DEX dynamics (sandwich bots,
  arbitrage, and sniping). Do not claim "immunity to all MEV".

## On-Chain Status: Pre-Computed Reservation vs Live Deployed Token

- `examples/verify-live-0111.json` and `examples/verify-live-64qubit.json`
  are **read-only CREATE2 prediction records** verifying that the genius.fun
  deployer logic executes deterministically on BSC mainnet.
- Unless `eth_getCode` returns contract bytecode (>2 bytes), an address is
  strictly `RESERVED_AWAITING_BROADCAST (codeSize=0 bytes)`. Never claim an
  un-broadcast CREATE2 address is an actively traded token.

