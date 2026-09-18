# Contributing

This repo is meant to be run by a stranger. A change that only works on one
machine proves nothing.

## Do

- Keep salt and planHash byte-for-byte with `vectors/derive.json` and
  `js/derive.mjs`. If they drift, published predictions will not reproduce.
- Add a failing test before fixing a derivation or record self-check.
- Treat billed QPU seconds and wall-clock as different numbers.
- Put new launchpads in a platform JSON, not in CLI defaults, until there
  is a live `eth_call` fixture.
- Leave missing values as missing. Never substitute zero for unknown.
- Write public docs in English.

## Do not

- Commit `.env`, keystores, private keys, or IBM API keys.
- Attribute launches to IBM.
- Claim a bitstring is proven to come from a QPU.
- Skip ordered per-shot bitstrings (counts alone cannot name shot *n*).
- Predict against a factory if the pad’s CREATE2 lives on a wired deployer.

## Checks

```sh
pytest
npm test
python -m quantum_launch derive --bitstring 0111
```
