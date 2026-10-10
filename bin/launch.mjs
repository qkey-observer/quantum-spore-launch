#!/usr/bin/env node
// Prepare, sign and send a pump.fun launch, as three separate steps on purpose.
//
//   prepare  arithmetic and one read-only simulation. No key, no write.
//   sign     reads key files on this machine and fills in the signatures.
//   send     submits a transaction that is already signed.
//
// They are separate because the middle one is the only step that needs a key
// and the last one is the only step that cannot be undone. Running `prepare`
// can never cost anything; running `send` always can.
import { readFileSync, writeFileSync } from 'node:fs';
import { ed25519 } from '@noble/curves/ed25519.js';
import { base58Decode, base58Encode } from '../src/derive/index.mjs';
import { mintAddressFromBitstring, mintKeypairFromBitstring, bondingCurveFor } from '../src/derive/pump.mjs';
import { buildLaunchTransaction } from '../src/launch/pump-create.mjs';
import { assertSigned, DEFAULT_RPC, latestBlockhash, send, simulate } from '../src/launch/broadcast.mjs';

const argv = process.argv.slice(2);
const command = argv[0];
const flag = name => { const i = argv.indexOf(`--${name}`); return i === -1 ? null : argv[i + 1]; };
const has = name => argv.includes(`--${name}`);
const rpc = flag('rpc') ?? process.env.SOLANA_RPC_URL ?? DEFAULT_RPC;
const die = message => { console.error(`${message}\n`); process.exit(1); };

const USAGE = `
usage:
  launch prepare --bitstring <01…> --payer <pubkey> --name <n> --symbol <s> --uri <url>
                 [--creator <pubkey>] [--creator-fee-bps <n>] [--mayhem] [--cashback]
                 [--holder-reward] [--out <file.json>] [--no-simulate] [--rpc <url>]
  launch sign    --in <file.json> --payer-keypair <path.json> [--out <file.json>]
  launch send    --in <file.json> --yes [--rpc <url>]

The mint is derived from the bitstring, which means the bitstring is the mint's
private key. Publish the address before the launch and the bitstring after it.
`;

if (command === 'prepare') {
  const bitstring = flag('bitstring');
  const payer = flag('payer');
  const name = flag('name'), symbol = flag('symbol'), uri = flag('uri');
  if (!bitstring || !payer || !name || !symbol || !uri) die(USAGE);

  const mint = mintAddressFromBitstring(bitstring);
  const curve = bondingCurveFor(mint);
  const blockhash = has('no-simulate') && !has('fetch-blockhash')
    ? base58Encode(new Uint8Array(32)) : (await latestBlockhash(rpc)).blockhash;
  const tx = buildLaunchTransaction({
    mint, user: payer, name, symbol, uri,
    creator: flag('creator') ?? payer,
    creatorFeeBps: Number(flag('creator-fee-bps') ?? 0),
    isMayhemMode: has('mayhem'), isCashbackEnabled: has('cashback'), isHolderReward: has('holder-reward'),
    recentBlockhash: blockhash,
  });

  console.log(`mint          ${mint}`);
  console.log(`bonding curve ${curve.address}  bump ${curve.bump}`);
  console.log(`payer         ${payer}`);
  console.log(`signatures    ${tx.signatureSlots.length} required, 0 present`);
  console.log(`blockhash     ${blockhash}${has('no-simulate') ? ' (placeholder — replace before signing)' : ''}`);

  if (!has('no-simulate')) {
    const result = await simulate(tx.transactionBase64, { rpc });
    console.log(`\nsimulation    ${result.ok ? 'accepted' : `rejected: ${JSON.stringify(result.err)}`}  (${result.unitsConsumed} compute units)`);
    if (!result.ok) {
      for (const line of result.logs.slice(-8)) console.log(`  ${line}`);
      // Two rejections look alike on screen and mean opposite things, so say
      // which one this is rather than offering the same guess for both.
      const funding = result.err === 'AccountNotFound' || result.logs.some(line => line.includes('insufficient lamports'));
      console.log(funding
        ? `\n${result.err === 'AccountNotFound' ? 'The payer account does not exist on this cluster' : 'The payer cannot cover rent and fees'} — fund it and run this again. The transaction itself was accepted up to that point.`
        : '\nThis one is the transaction, not the funding. Run `npm run verify:pump` to see whether the launchpad has changed under this builder.');
    }
  }

  const out = flag('out');
  if (out) {
    writeFileSync(out, `${JSON.stringify({ mint, curve: curve.address, payer, blockhash, transactionBase64: tx.transactionBase64, signers: tx.signatureSlots, bitstringIsMintKey: true }, null, 2)}\n`);
    console.log(`\nwrote ${out} — unsigned. Nothing has been sent.`);
  } else {
    console.log(`\n${tx.transactionBase64}`);
  }
  process.exit(0);
}

if (command === 'sign') {
  const input = flag('in');
  const payerKeypairPath = flag('payer-keypair');
  if (!input || !payerKeypairPath) die(USAGE);
  const doc = JSON.parse(readFileSync(input, 'utf8'));
  const bitstring = flag('bitstring') ?? doc.bitstring;
  if (!bitstring) die('The mint signature comes from the bitstring; pass --bitstring.');

  const mintKey = mintKeypairFromBitstring(bitstring);
  if (mintKey.address !== doc.mint) die(`That bitstring derives ${mintKey.address}, but this transaction launches ${doc.mint}.`);
  // Read from a file rather than an argument or an environment variable, so the
  // secret never lands in a shell history or a process listing.
  const payerSecret = Uint8Array.from(JSON.parse(readFileSync(payerKeypairPath, 'utf8'))).slice(0, 32);

  const raw = Buffer.from(doc.transactionBase64, 'base64');
  const signatureCount = raw[0];
  const message = raw.subarray(1 + signatureCount * 64);
  const keys = { [base58Encode(ed25519.getPublicKey(payerSecret))]: payerSecret, [mintKey.address]: mintKey.secret };
  doc.signers.forEach((signer, i) => {
    const secret = keys[signer];
    if (!secret) die(`No key given for required signer ${signer}.`);
    raw.set(ed25519.sign(message, secret), 1 + i * 64);
  });
  payerSecret.fill(0);
  mintKey.secret.fill(0);

  const out = flag('out') ?? input.replace(/(\.json)?$/, '.signed.json');
  writeFileSync(out, `${JSON.stringify({ ...doc, transactionBase64: raw.toString('base64'), signed: true }, null, 2)}\n`);
  console.log(`signed ${doc.signers.length} of ${doc.signers.length} → ${out}`);
  console.log('Still not sent. `launch send --in <file> --yes` does that.');
  process.exit(0);
}

if (command === 'send') {
  const input = flag('in');
  if (!input) die(USAGE);
  const doc = JSON.parse(readFileSync(input, 'utf8'));
  // Before the network, before --yes: an unsigned file is a mistake worth
  // naming plainly rather than letting a cluster error stand in for it.
  try { assertSigned(doc.transactionBase64); } catch (error) { die(error.message); }
  if (!has('yes')) {
    console.log(`Would submit the launch of ${doc.mint} to ${new URL(rpc).host}.`);
    console.log('This cannot be undone, and after it lands the bitstring is safe to publish.');
    console.log('Add --yes to actually send it.');
    process.exit(0);
  }
  const check = await simulate(doc.transactionBase64, { rpc, signed: true });
  if (!check.ok) {
    console.error(`Refusing to send: the cluster rejects this transaction (${JSON.stringify(check.err)}).`);
    for (const line of check.logs.slice(-8)) console.error(`  ${line}`);
    process.exit(1);
  }
  const { signature, explorer } = await send(doc.transactionBase64, { rpc });
  console.log(`sent ${signature}\n${explorer}`);
  process.exit(0);
}

die(USAGE);
