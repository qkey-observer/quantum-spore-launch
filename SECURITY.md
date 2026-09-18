# Security

- Never commit `.env`, keystores, or private keys. `.env.example` lists names only.
- Launch keys are read from the environment, a keystore, a file, or Clef.
  They are not CLI flags and must not appear in logs.
- Default is dry-run. `--broadcast` is explicit.
- IBM API keys (`QKEY_IBM_API_KEY`, instance CRN) stay on the operator machine.
- A predicted CREATE2 address is not reserved. Do not send funds to it before
  `eth_getCode` shows bytecode.
- This software is unaffiliated with IBM and with genius.fun.
