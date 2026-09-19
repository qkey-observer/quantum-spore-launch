# Launchpad adapters

The QPU loop (measure → decode map → salt → publish → sign) is pad-agnostic.
A **platform** is the on-chain object that turns a salt plus a frozen plan
into a CREATE2 address and a `launchToken` transaction.

## Worked example: genius.fun (BSC)

File: `examples/platform.genius-bsc.json`. Built-in id: `genius-bsc`.

| Role | Address |
| --- | --- |
| Factory | `0x78EAE9537C0ef90DFe9B7ae964682Fe8138afe31` |
| Wired launch deployer | `0xaB3eAD42ec2587D16BAE8f2c9Fb133c533C7fAAf` |
| Quote (IBMB) | `0xfA273B076Feb8c0FB34e554ae341082323D016A3` |
| Router | `0x2EF00378984e84f2DAa08DfB5Fb03bBDE2038ae6` |
| Hook | `0xFf17F41c5Efd6CCe944Af0912F300097D62df5c9` |
| Fee escrow | `0xFf8A2ae655E5851CB414Ac5aB41B311dA4287281` |
| Buyback vault | `0x6EcBe74E6CF896c610C34A3BE59Bd54c5A5B784E` |

Addresses from [genius.fun contracts](https://genius.fun/docs/contracts)
release `prod-foundation-20260916`. genius.fun is a Pons v2 fork.
**Predict on the wired deployer**, not the factory. `originalDeployer` is
the initiating EOA (`msg.sender`). `canLaunch` is protocol-owned; this
program cannot whitelist itself.

```sh
python -m quantum_launch inspect --platform genius-bsc
python -m quantum_launch predict --platform genius-bsc \
  --plan examples/launch-plan.example.json --bitstring 0111
python -m quantum_launch run --platform genius-bsc \
  --plan examples/launch-plan.example.json \
  --map examples/launch-map.direct.json
```

Live read-only prediction of `0111` is in `examples/live-predict-0111.json`.

## Second adapter: Pons V2 (Robinhood Chain)

File: `examples/platform.pons-robinhood.json`. Built-in id: `pons-robinhood`.

| Role | Address |
| --- | --- |
| Factory | `0x7eD598BcEf8bd9Edd8C97A195C6d13f40801EC7e` |
| Wired launch deployer | `0x3711ceA4feaDE896C913C68F01Eda97Cb06D1A42` |
| Quote | native ETH (`0x0000…0000`) |
| Router | `0xe33E9E479dF8802cb0866d5d05258bEc4cF62948` |
| Hook | `0xE5e702641Ea86F4ae6cC3cDaeD2B886f976Be044` |
| Fee escrow | `0xd3AFEB2a57f70eF218Aa82451c51B2fb0416Ac9e` |
| Buyback vault | `0x42df2a798f82289E177311362e8f5ccC45c1219c` |

Chain `4663`, public RPC `https://rpc.mainnet.chain.robinhood.com`, explorer
[robinhoodchain.blockscout.com](https://robinhoodchain.blockscout.com/). Every
address above was confirmed to hold code at block 66658781; the factory,
deployer and escrow are also verified on
[Sourcify](https://sourcify.dev/server/v2/contract/4663/0x7eD598BcEf8bd9Edd8C97A195C6d13f40801EC7e).

genius.fun is a Pons v2 fork, so the CREATE2 tuple shape is the same and the
same rule applies: **predict on the wired deployer**, not the factory, and
`originalDeployer` is the initiating EOA. Two differences matter.

- **The quote is native ETH, not an ERC-20.** A buy sends value rather than
  approving a token, and a treasury on this chain is read with
  `eth_getBalance` instead of a `balanceOf` call.
- **Fees accrue in the escrow and are not a wallet balance.** The recipient
  claims them in a separate transaction. An address showing nothing on the
  explorer can still have fees waiting.

```sh
python -m quantum_launch inspect --platform pons-robinhood
python -m quantum_launch predict --platform pons-robinhood \
  --plan examples/launch-plan.example.json --bitstring 0111
```

A plan frozen for one chain does not carry to the other. `chainId`, the
factory and the quote asset all feed the init code, so the same bitstring
gives a different address on 4663 than on 56 — which is the point: the
measurement picks the address, the platform decides what that address is.

## Adding a pad

1. Copy `examples/platform.template.json`.
2. Set `chainId`, `factory`, **wired deployer** (the contract that actually
   CREATE2s), hook/escrow/vault if the prediction tuple needs them.
3. Drop a slim ABI JSON next to `src/quantum_launch/abi/` or point `abiFile`
   at a path you keep with the platform JSON.
4. Implement or reuse `predictLaunchAddresses` encoding. If the pad’s tuple
   differs from Pons/genius, extend `predict.py` behind a `platform["id"]`
   branch — do not guess CREATE2 from salt alone.
5. Pass `--platform your.json`. Do not hard-code a new pad into the CLI
   default until it has a live `eth_call` fixture like genius.fun.

A salt never determines the address by itself. The pad’s deployer, the
initiator, and the full init code (name, symbol, image, quote, tax, …)
all feed CREATE2. Freeze the plan. Hash it. Predict against the **wired**
contract.

## What is not a pad

Chapel (BSC testnet 97) has empty code at the genius.fun factory. Marker
CREATE2 there only proves the local pipeline, not a genius.fun launch.
See `docs/RUNBOOK.md`.
