# Cost ledger

Cost is the argument. The claim is not a 2-second job. The claim is **keeping
an IBM QPU in the launch loop for a long time**: measure → decode → predict →
broadcast → next job, hours and days of billed execution, 64 qubits × 16 layers.

Write the **high** numbers first. A cheap per-shot line is how the story gets
watered down.

## Headline (public IBM rates, retrieved 2026-09-17)

Source: [ibm.com/quantum/products](https://www.ibm.com/quantum/products)
(`ibm.com/quantum/pricing` redirected there). Pay-As-You-Go **$96 USD / minute**,
billed per second. Dedicated / On-Prem: **Contact for quote** — this repo will
not invent a dedicated price.

If billed QPU time filled the calendar at that public PAYG rate:

| Hold the QPU | Arithmetic | USD |
| --- | --- | ---: |
| **30 days, every second billed** | 2,592,000 s × $1.60/s | **$4,147,200** |
| **365 days, every second billed** | 31,536,000 s × $1.60/s | **$50,457,600** |
| same 30d at Flex $72/min | | $3,110,400 |
| same 30d at Premium $48/min | | $2,073,600 |
| same 365d at Flex / Premium list | | $37,843,200 / $25,228,800 |
| Dedicated / On-Prem | IBM: quote only | **ask IBM** |

Those are list-rate extrapolations, not an IBM dedicated invoice. They are
the honest public ceiling: **this is what “leave the quantum computer on
the launch loop” costs at the only per-second number IBM prints.**

## Published minutes are not long enough

| Plan | What IBM sells | Duration | Enough for this claim? |
| --- | --- | --- | --- |
| Open | 10 minutes / month | **10 min** | **No.** |
| Premium | 5200 minutes / year at $48/min = **$249,600/year floor** | **86.7 hours / year** | **No.** Still shared fleet minutes, not a held machine. |
| Calendar | 720 h / 30d, 8760 h / year | — | This is the clock the loop has to match. |
| Dedicated / On-Prem | **Price requires quote** | Held system | **This is the SKU.** |

A 2.4-second billed job, or 10 free minutes, cannot be the public demonstration.
The demonstration is **staying connected**.

## Shared-queue $55,296 is a lower bound, not the pitch

If wall-clock stays ~180 s/job (queue included): 14,400 jobs × $3.84 = $55,296
/ 30 days. Arithmetic is correct. **Do not lead with it.**

That 180 s includes the shared queue. This project has seen `ibm_fez` pending
**98** and `ibm_marrakesh` pending **1** at the same moment. A long queue does
not make each job’s QPU bill larger; it stops you holding the machine. Shared
queue cannot promise hours of connected time.

## Two clocks

- `usageSeconds` — billed QPU execution.
- `wallSeconds` / timestamps — queue plus run.

They differ by orders of magnitude. Never present them as one number.
Billed time of zero is refused. Missing billed time stays missing.

## Unit cost

`usdPerSporePayAsYouGo = (billable QPU seconds × $1.60) / shots`

Looks cheap if you divide a short job by 1024 shots. **The product is not
one spore. The product is the QPU remaining in the loop.**

## Modes

- `autonomous --broadcast` is the expensive claim: the program keeps
  measuring and launching until you stop it or the bill stops it.
- `confirmed` is what you run when you cannot yet buy reserved time.

```sh
python -m quantum_launch cost --job runs/job.json
```
