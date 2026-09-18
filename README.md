<div align="center">

# 🌌 Quantum Spore Launch (Q-Spore)

### Open-Source IBM QPU-to-EVM Launchpad Protocol & Engine
**Connecting Real Superconducting Quantum Processors to BSC & EVM Deterministic Smart Contracts**

*100% Turn-Key • Multi-Qubit NISQ Entropy • CREATE2 Deterministic Deployment • Publicly Verifiable*

<br/>

[![Official Explorer](https://img.shields.io/badge/Portal-qkey.observer-8A2BE2?style=for-the-badge&logo=googlechrome)](https://qkey.observer)
[![IBM Quantum Native](https://img.shields.io/badge/QPU-IBM%20Quantum%2064--Qubit-0530AD?style=for-the-badge&logo=ibm)](https://www.ibm.com/quantum)
[![Deterministic Deployment](https://img.shields.io/badge/EVM-CREATE2%20Deterministic-3C3C3D?style=for-the-badge&logo=ethereum)](https://ethereum.org)
[![Tested On](https://img.shields.io/badge/Launchpad-BSC%20%7C%20genius.fun-F0B90B?style=for-the-badge&logo=binance)](https://bscscan.com)
[![Open Source](https://img.shields.io/badge/License-MIT-success?style=for-the-badge)](LICENSE)
[![Tests Passed](https://img.shields.io/badge/Tests-67%2F67%20Passing-brightgreen?style=for-the-badge)](tests)
[![Production Ready](https://img.shields.io/badge/Status-Turn--Key%20CLI%20%26%20SDK-blueviolet?style=for-the-badge)](https://github.com)

<br/>

**[ 🌐 Official Portal: qkey.observer ](https://qkey.observer)** | **[ 🔬 On-Chain Evidence ](#-on-chain-evidence--dual-verification-vectors)** | **[ ⚙️ Pipeline Mechanics ](#-what-this-engine-actually-does-the-6-step-pipeline)** | **[ 🛡️ Security & MEV Bounds ](#-security-mev-boundaries--trust-model)** | **[ 🚀 Turn-Key Quickstart ](#-turn-key-quickstart)**

---

</div>

<br/>

## 🌟 Overview: Real Quantum Entropy Meets EVM Launchpads

**Quantum Spore Launch** is an open-source protocol and execution engine that automates the deployment of decentralized smart contract tokens by deriving their foundational parameters directly from **real superconducting quantum computer measurements (IBM Quantum QPU)** via **EVM `CREATE2` deterministic address prediction**.

Official protocol explorer, interactive verification dashboard, and real-time spore telemetry are available at **[https://qkey.observer](https://qkey.observer)**.

The project interfaces with the official **[genius.fun](https://genius.fun)** bonding curve launchpad on **Binance Smart Chain (BSC)**, utilizing the factory's verified on-chain deployer to cryptographically lock and pre-compute token addresses before any deployment transaction is broadcast.

```
+-------------------------------------------------------------------------+
|                  Official genius.fun BSC Infrastructure                 |
|  Factory:         0x78EAE9537C0ef90DFe9B7ae964682Fe8138afe31            |
|  LaunchDeployer:  0xaB3eAD42ec2587D16BAE8f2c9Fb133c533C7fAAf            |
+-------------------------------------------------------------------------+
```

---

## ⚙️ What This Engine Actually Does: The 6-Step Pipeline

The pipeline connects physical quantum hardware to on-chain execution in six discrete, reproducible steps:

```
[1. IBM QPU Job] ──────> [2. Ordered Shots] ──────> [3. Canonical Map]
  Qiskit SamplerV2         Preserves individual       Slices bits into Name,
  Hardware-efficient       shots; rejects lossy       Ticker, Tax, Buyback,
  64-qubit circuit         histogram counts           and Next-Job specs
         │
         ▼
[4. Cryptographic Salt] ─> [5. CREATE2 Predict] ─> [6. Optional Broadcast]
  salt = keccak256(        Calls official BSC         Operator signs with
  utf8(bitstring))         predictLaunchAddresses     hot wallet; code verifies
                           on wired deployer          on-chain via RPC
```

1. **Physical QPU Execution**: Dispatches quantum circuits to real IBM Quantum processors via Qiskit Runtime SamplerV2 (strictly requires `ibm_*` hardware backends; rejects classical simulators).
2. **Ordered Shot Extraction**: Retains ordered per-shot bitstrings from measurement registers rather than lossy aggregate histogram counts.
3. **Canonical Rule Mapping**: Slices measured bits into token attributes (token name, ticker symbol from a 32-character alphabet, creator tax bps, buyback flags, quote asset, initial purchase, fee routing, and next-generation circuit feedback) according to a rule map hashed and published prior to the job.
4. **Cryptographic Salt Derivation**: Derives an immutable cryptographic salt:
   $$\text{Salt} = \text{keccak256}\Big(\text{utf8}(\text{bitstring})\Big)$$
5. **Official Deployer Prediction**: Queries `predictLaunchAddresses` directly on the official genius.fun BSC deployer (`0xaB3eAD42…`) to obtain the deterministic CREATE2 token address and bonding curve pool.
6. **Operator Broadcast**: Signs and broadcasts `launchToken` or `launchAndBuy` to BSC mainnet only when `--broadcast` is explicitly passed by the operator.

---

## 🛡️ Security, MEV Boundaries & Trust Model

To maintain complete engineering and scientific rigor, the operational boundaries, trust assumptions, and cryptographic guarantees of this architecture are explicitly documented:

### 1. ⚛️ Physical Entropy vs. Certified QRNG (The NISQ Reality)
* **What it is**: The system executes a 64-qubit, 16-layer Hardware-Efficient Ansatz with parameterized single-qubit rotations ($R_Y, R_Z$) and linear entangling chains ($CZ$). On current Noisy Intermediate-Scale Quantum (NISQ) superconducting chips, output bitstreams reflect true physical macroscopic quantum state collapse coupled with hardware thermal and decoherence fluctuations.
* **What it is not**: This is physical hardware entropy, distinct from software pseudo-random number generators (PRNGs). However, it is not an idealized, fault-tolerant, or mathematically certified quantum random number generator (certified QRNG).

### 2. 🛡️ What CREATE2 Solves vs. What It Does Not
* **What CREATE2 Guarantees (Anti-Rug & Parameter Immutability)**:
  * The predicted token address is mathematically coupled to $\text{Salt}$ and $\text{InitCode}$ (which embeds the token name, symbol, creator tax, quote asset, and fee destination).
  * The deployer **cannot alter a single parameter** after announcing the salt without changing the contract address.
  * Protects against internal deployer nonce frontrunning and factory-level reordering.
* **The Trading MEV Boundary**:
  * CREATE2 pre-computation does **not** protect secondary trading on the bonding curve from standard mempool MEV. Once the token is deployed or the launch transaction is public, trades on PancakeSwap or the genius.fun curve remain subject to sandwich bots, slippage arbitrage, and mempool sniping.

### 3. ⚖️ The Trust Model & Operator Boundaries
* **Operator Role**: The operator controls machine selection, job submission, pre-published mapping files, private key custody, and the timing of the broadcast transaction.
* **IBM Provenance**: IBM Quantum Runtime results are private to the account holder. Third parties cannot inspect private jobs by ID on IBM servers. Provenance is established through self-attested job records, calibration property matching, and strict sequential shot verification ($1 \dots N$).
* **Anti-Cherrypicking Enforcement**: The built-in verifier rejects any record containing gaps or holes in the shot sequence. Any skipped shot must strictly match the deterministic `launch: false` rule specified in the pre-hashed map.

### 4. 🔬 The Verification Boundary: What Third Parties Can vs. Cannot Verify

| Verification Dimension | Third-Party Status | Technical Mechanism / Boundary |
| :--- | :--- | :--- |
| **Cryptographic Derivation** | ✅ 100% Verifiable | Anyone can run `python -m quantum_launch derive` to prove $\text{salt} = \text{keccak256}(\text{utf8}(\text{bitstring}))$ and verify canonical JSON plan hashes. |
| **CREATE2 Determinism** | ✅ 100% Verifiable | Anyone can execute `eth_call` against the official genius.fun deployer on public BSC RPCs to reproduce the exact address (`0x2c670B551d2B15c68eE08E492Ed2506eC22e6F83`). |
| **On-Chain Bytecode Audit** | ✅ 100% Verifiable | The verifier queries `eth_getCode` and transparently reports whether an address is an un-broadcast reservation (`codeSize=0`) or an active contract. |
| **Sequential Non-Cherrypicking** | ✅ 100% Verifiable | The verifier mathematically enforces that shots $1 \dots N$ are consumed in strict sequential order without arbitrary gaps or omissions. |
| **IBM Cloud QPU Provenance** | ℹ️ Account-Private / Attested | **IBM Quantum Runtime is an authenticated enterprise cloud service, not a public blockchain.** IBM does not expose an unauthenticated public explorer for private account jobs. Device status and calibration data can be cross-checked against IBM's public properties, but raw job retrieval requires account API credentials. Verifiable device-independent quantum randomness remains an active open research problem. |
| **On-Chain Activation** | ℹ️ Operator-Triggered | Quantum Spore Launch is a **toolchain & deployment engine**, not a single pre-mined token. Deploying to BSC mainnet requires passing `--broadcast` with a funded wallet to pay the 0.002 BNB factory fee. Demo fixtures preserve pre-flight reservations to enable zero-gas verification for any developer worldwide. |

---

## 🔬 On-Chain Evidence: Dual Verification Vectors

The repository provides two live on-chain verification fixtures independently checkable against public Binance Smart Chain RPC nodes.

### 1. 64-Qubit Production Hardware Vector ([`examples/verify-live-64qubit.json`](examples/verify-live-64qubit.json))
A 64-qubit hardware-efficient state measured on `ibm_marrakesh` (16 layers, 3,124 lines of synthesized OpenQASM 2.0 with Heron heavy-hex coupling):

| Parameter | Value | Verification Note |
| :--- | :--- | :--- |
| **QPU Hardware** | `ibm_marrakesh` | 64 superconducting transmon qubits (Heron layout) |
| **Job ID** | `cpt1m5p0p4ag00851vkg` | IBM Quantum Runtime job format |
| **Circuit Synthesis** | 3,124 lines of OpenQASM 2.0 | Full $R_Y, R_Z$ and $CZ$ 16-layer hardware-efficient circuit |
| **Quantum Shot 1** | `1001001000010000000100000000000000000000000000000000000000000000` | 64-bit physical measurement |
| **Derived Salt** | `0x7b0552d55123ba9314be1606794c35a59cdd748279c55fe7c9c3a9e3727cda64` | `keccak256(utf8(bits))` |
| **CREATE2 Token Address** | `0x2c670B551d2B15c68eE08E492Ed2506eC22e6F83` | Deterministic genius.fun deployer prediction |
| **Bonding Curve Pool** | `0x3e7d5b01FE7909714b6ECe1bAa9D15c518fAeDa5` | Deterministic bonding curve pair |
| **Mainnet Block** | `122553987` | Verified live on BSC mainnet |
| **Bytecode Audit** | `RESERVED_AWAITING_BROADCAST (codeSize=0 bytes)` | Verified via `eth_getCode` |

```bash
# Verify 64-qubit vector against live BSC public RPC:
python -m quantum_launch verify examples/verify-live-64qubit.json \
  --rpc https://bsc-dataseed.binance.org
```

---

### 2. 4-Bit Educational Table Demo ([`examples/verify-live-0111.json`](examples/verify-live-0111.json))
A minimal 4-qubit Hadamard test vector for rapid local demonstration:

| Parameter | Value | Verification Note |
| :--- | :--- | :--- |
| **Quantum Bitstring** | `0111` | Minimal 4-bit Hadamard shot |
| **Derived Salt** | `0x334fe1125e74700a86e339a5f102282ceaeb5a83bb3ca03cb42b44d576d6d9a0` | `keccak256(utf8("0111"))` |
| **CREATE2 Token Address** | `0x999Ca7a3ba3cF02C29fc844caE603712222A2e81` | Deterministic genius.fun deployer prediction |
| **Bonding Curve Pool** | `0x58f0045529308B2CAd3713E8939795B8c0193A7c` | Deterministic bonding curve pair |
| **Mainnet Block** | `122550017` | Verified live on BSC mainnet |
| **Bytecode Audit** | `RESERVED_AWAITING_BROADCAST (codeSize=0 bytes)` | Verified via `eth_getCode` |

```bash
# Verify 4-bit demo vector against live BSC public RPC:
python -m quantum_launch verify examples/verify-live-0111.json \
  --rpc https://bsc-dataseed.binance.org
```

### 💡 The Two-Phase Lifecycle: Reservation vs. Live Activation

* **Phase 1: Deterministic Pre-Flight Reservation (`codeSize == 0`)**:
  Allows any developer, researcher, or auditor to independently recompute the quantum salt, verify the canonical map hash, simulate the wired deployer call, and pre-determine the token address with **zero BNB spend**.
* **Phase 2: On-Chain Live Activation (`codeSize > 0`)**:
  Triggered when an operator passes `--broadcast` to the CLI with a funded wallet. The transaction submits the 0.002 BNB factory fee to genius.fun, deploys the ERC-20 contract to the exact reserved address, and initializes the bonding curve.
* **Continuous Integration (`.github/workflows/ci.yml`)**:
  GitHub Actions CI executes both offline cryptographic self-checks and live BSC mainnet RPC audits on every push, ensuring deployer ABI compatibility and bytecode transparency.

---

## 🚀 Turn-Key Quickstart

### 1. Installation

```bash
# Clone the repository
git clone https://github.com/qkey-observer/quantum-spore-launch.git
cd quantum-spore-launch

# Set up virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies (Python 3.11+)
pip install -e ".[dev]"

# (Optional) Install IBM Qiskit Runtime for live QPU submission
pip install -e ".[ibm]"

# Run test suite (67/67 tests passing)
pytest
```

---

### 2. Zero-Friction Dry-Run (No Credentials Needed)

Execute the full pipeline against a captured quantum job fixture:

```bash
python -m quantum_launch run \
  --plan examples/launch-plan.example.json \
  --platform genius-bsc \
  --map examples/launch-map.direct.json \
  --job tests/fixtures/job.json \
  --mode confirmed \
  --out runs/dry \
  --max-spores 1
```

---

### 3. Live Deployment Setup

Copy `.env.example` to `.env` and configure your credentials:

```ini
# IBM Quantum API Credentials (required for live QPU jobs)
QKEY_IBM_API_KEY=your_ibm_api_key_here
QKEY_IBM_INSTANCE_CRN=your_ibm_cloud_instance_crn

# Target Public Blockchain RPC (BSC Mainnet default)
QKEY_RPC_URL=https://bsc-dataseed.binance.org

# Launch Signer (Wallet with Gas on BSC)
QKEY_LAUNCH_PRIVATE_KEY=your_private_key_hex_here
```

Deploy in interactive operator mode:

```bash
python -m quantum_launch run \
  --plan examples/launch-plan.example.json \
  --platform genius-bsc \
  --map examples/launch-map.direct.json \
  --backend ibm_marrakesh \
  --mode confirmed \
  --broadcast \
  --out runs/live
```

---

## 🛠️ Complete CLI Command Reference

| Command | Function | Target / Use Case |
| :--- | :--- | :--- |
| `derive` | Recomputes salt and canonical `planHash` | Cryptographic verification |
| `inspect` | Read-only audit of launchpad deployer wiring & readiness | On-chain environment audit |
| `map` | Decodes a bitstring or QPU job under a published rule map | Quantum genomic translation |
| `predict` | Queries on-chain deployer for deterministic CREATE2 addresses | Address pre-computation |
| `verify` | Full sceptic verifier: derivation, shot ordering, and on-chain RPC checks | Independent third-party audit |
| `measure` | Submits entangling circuits to real IBM QPU and stores ordered shots | Physical quantum execution |
| `probe-extraction` | Verifies SamplerV2 bitstring extraction before spending quota | Hardware pre-flight check |
| `cost` | Audits billed QPU seconds vs wall clock duration | Economic tracking |
| `run` | Unified launch pipeline (default dry-run, `--broadcast` to sign) | End-to-end token deployment |
| `chapel-run` | Deploys testnet-style CREATE2 marker contracts | Local testing / Anvil rehearsal |

---

## 🌐 Multi-Chain Ecosystem & Launchpad Adapters

The engine uses a clean adapter pattern decoupling measurement logic from specific launchpads:

* **BSC (Chain ID 56)**: Primary adapter for [genius.fun](https://genius.fun) bonding curve factory & wired deployer.
* **Robinhood Chain (Chain ID 4663)**: Adapter for Pons v2 CREATE2 deterministic deployer.
* **Custom Launchpads**: Any EVM launchpad exposing a deterministic deployer view can be integrated in minutes by creating a JSON configuration matching [`examples/platform.template.json`](examples/platform.template.json).

---

## 📁 Repository Structure

```
├── src/quantum_launch/
│   ├── measure.py          # IBM Quantum Qiskit Runtime SamplerV2 client
│   ├── mapping.py          # Quantum bitstream decoding into token specifications
│   ├── derive.py           # Cryptographic keccak256 salt & canonical plan hashing
│   ├── predict.py          # EVM CREATE2 deployer prediction interface
│   ├── pipeline.py         # Autonomous & Confirmed execution pipeline orchestrator
│   ├── platforms.py        # Multi-chain launchpad JSON+ABI adapter registry
│   ├── verify_public.py    # Independent third-party on-chain verification suite
│   ├── cost.py             # QPU billing seconds & queue economics analysis
│   ├── inspect.py          # On-chain launchpad state auditor
│   ├── launch.py           # EVM transaction builder, signer, and broadcaster
│   ├── record.py           # Cryptographic provenance & launch artifact logger
│   └── cli.py              # Unified developer & operator command line interface
├── contracts/              # Solidity interfaces & reference ABIs
├── examples/               # Production launch plans, maps, and live on-chain proofs
├── js/                     # Thin Node.js module for cross-language test vectors
├── tests/                  # Exhaustive automated test suite (67/67 passing)
├── vectors/                # Shared multi-language cryptographic test vectors
└── docs/                   # Full architectural specifications and runbooks
```

---

## 📚 Technical Documentation & Specifications

* **[docs/RUNBOOK.md](docs/RUNBOOK.md)** — Production Operator Runbook & Key Management
* **[docs/MAP.md](docs/MAP.md)** — Mathematical Specification of the 128-bit Quantum Genome
* **[docs/SCHEMA.md](docs/SCHEMA.md)** — JSON Schemas for Plans, Maps, and Execution Records
* **[docs/PLATFORMS.md](docs/PLATFORMS.md)** — Launchpad Adapter Integration Guide
* **[docs/COST.md](docs/COST.md)** — Detailed QPU Economic Ledger & Pricing Models
* **[docs/CLAIMS.md](docs/CLAIMS.md)** — Allowed Public Language & Cryptographic Boundaries

---

## 📄 License & Open Standards

Distributed under the **[MIT License](LICENSE)**.

* Built on open standards: **Qiskit 1.2+**, **EVM CREATE2**, and **Ethereum keccak256**.
* Third-party integrations: Designed as an open client for public EVM smart contracts. IBM and genius.fun are independent entities; integration does not imply official endorsement or affiliation.
