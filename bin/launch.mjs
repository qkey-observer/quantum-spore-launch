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

class Refused extends Error {}
const die = message => { throw new Refused(message); };

const USAGE = `
usage:
  launch prepare --bitstring <bits> --payer <pubkey> --name <n> --symbol <s> --uri <url>
                 [--creator <pubkey>] [--creator-fee-bps <n>] [--mayhem] [--cashback]
                 [--holder-reward] [--out <file.json>] [--no-simulate] [--rpc <url>]
  launch sign    --in <file.json> --bitstring <bits> --payer-keypair <path.json> [--out <file.json>]
  launch send    --in <file.json> --yes [--rpc <url>]

<bits> is the measured bitstring, e.g. 10010010000100000001…  (0s and 1s only)
<pubkey> is a base58 Solana address, e.g. 7BqXuedSVx3fETcDsvmZPqTw4dEvtPGhkHwhc5yMD6st

The mint is derived from the bitstring, which means the bitstring is the mint's
private key. Publish the address before the launch and the bitstring after it.
`;

/**
 * Check an address here rather than letting it fail several layers down. The
 * value usually comes from a shell, so the thing most likely to be wrong with
 * it is that it is still a placeholder — and that should be said in one line,
 * before anything reaches the network.
 */
function requireAddress(value, label) {
  if (!value) die(`${label} is missing.\n${USAGE}`);
  if (value.startsWith('--')) die(`${label} looks like the next flag (${value}) — a value is missing.`);
  let bytes;
  try { bytes = base58Decode(value); } catch { die(`${label} is not a Solana address: ${value}\nIt must be base58 — no spaces, no angle brackets, no placeholder text.`); }
  if (bytes.length !== 32) die(`${label} decodes to ${bytes.length} bytes, and a Solana address is 32: ${value}`);
  return value;
}

function requireBitstring(value, label = '--bitstring') {
  if (!value) die(`${label} is missing.\n${USAGE}`);
  if (!/^[01]+$/.test(value)) die(`${label} must be 0s and 1s only — this was ${JSON.stringify(value.slice(0, 24))}.\nIt is the measured shot, not a label for one.`);
  return value;
}

const readDoc = path => {
  if (!path) die(`--in is missing.\n${USAGE}`);
  try { return JSON.parse(readFileSync(path, 'utf8')); }
  catch (error) { die(error.code === 'ENOENT' ? `No such file: ${path}\nRun \`prepare --out ${path}\` first.` : `${path} is not readable JSON: ${error.message}`); }
};

async function prepare() {
  const bitstring = requireBitstring(flag('bitstring'));
  const payer = requireAddress(flag('payer'), '--payer');
  const creator = flag('creator') ? requireAddress(flag('creator'), '--creator') : payer;
  const name = flag('name'), symbol = flag('symbol'), uri = flag('uri');
  if (!name || !symbol || !uri) die(USAGE);
  const feeBps = Number(flag('creator-fee-bps') ?? 0);
  if (!Number.isInteger(feeBps) || feeBps < 0) die(`--creator-fee-bps must be a whole number, not ${flag('creator-fee-bps')}.`);

  const mint = mintAddressFromBitstring(bitstring);
  const curve = bondingCurveFor(mint);
  // Only now is the network touched: everything above can fail for free.
  const blockhash = has('no-simulate') ? base58Encode(new Uint8Array(32)) : (await latestBlockhash(rpc)).blockhash;
  const tx = buildLaunchTransaction({
    mint, user: payer, name, symbol, uri, creator,
    creatorFeeBps: feeBps,
    isMayhemMode: has('mayhem'), isCashbackEnabled: has('cashback'), isHolderReward: has('holder-reward'),
    recentBlockhash: blockhash,
  });

  console.log(`mint          ${mint}`);
  console.log(`bonding curve ${curve.address}  bump ${curve.bump}`);
  console.log(`payer         ${payer}`);
  console.log(`signatures    ${tx.signatureSlots.length} required, 0 present`);
  console.log(`blockhash     ${blockhash}${has('no-simulate') ? ' (placeholder — fetch a real one before signing)' : ''}`);

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
  if (!out) { console.log(`\n${tx.transactionBase64}`); return; }
  // The bitstring is deliberately not written: it is the mint's private key,
  // and this file is meant to be safe to keep, copy and inspect.
  writeFileSync(out, `${JSON.stringify({ mint, curve: curve.address, payer, creator, blockhash, transactionBase64: tx.transactionBase64, signers: tx.signatureSlots, bitstringIsMintKey: true }, null, 2)}\n`);
  console.log(`\nwrote ${out} — unsigned, and without the bitstring. Nothing has been sent.`);
}

async function sign() {
  const input = flag('in');
  const doc = readDoc(input);
  const payerKeypairPath = flag('payer-keypair');
  if (!payerKeypairPath) die(`--payer-keypair is missing.\n${USAGE}`);
  const bitstring = requireBitstring(flag('bitstring') ?? doc.bitstring);

  const mintKey = mintKeypairFromBitstring(bitstring);
  if (mintKey.address !== doc.mint) die(`That bitstring derives ${mintKey.address}, but this transaction launches ${doc.mint}.`);
  // Read from a file rather than an argument or an environment variable, so the
  // secret never lands in a shell history or a process listing.
  let payerSecret;
  try { payerSecret = Uint8Array.from(JSON.parse(readFileSync(payerKeypairPath, 'utf8'))).slice(0, 32); }
  catch (error) { die(`Could not read a keypair from ${payerKeypairPath}: ${error.message}`); }
  if (payerSecret.length !== 32) die(`${payerKeypairPath} does not hold a 64-byte Solana keypair.`);

  const raw = Buffer.from(doc.transactionBase64, 'base64');
  const signatureCount = raw[0];
  const message = raw.subarray(1 + signatureCount * 64);
  const secrets = { [base58Encode(ed25519.getPublicKey(payerSecret))]: payerSecret, [mintKey.address]: mintKey.secret };
  try {
    doc.signers.forEach((signer, i) => {
      const secret = secrets[signer];
      if (!secret) die(`No key given for required signer ${signer}.`);
      raw.set(ed25519.sign(message, secret), 1 + i * 64);
    });
  } finally {
    payerSecret.fill(0);
    mintKey.secret.fill(0);
  }

  const out = flag('out') ?? input.replace(/(\.json)?$/, '.signed.json');
  writeFileSync(out, `${JSON.stringify({ ...doc, transactionBase64: raw.toString('base64'), signed: true }, null, 2)}\n`);
  console.log(`signed ${doc.signers.length} of ${doc.signers.length} → ${out}`);
  console.log('Still not sent. `launch send --in <file> --yes` does that.');
}

async function sendCommand() {
  const doc = readDoc(flag('in'));
  // Before the network, before --yes: an unsigned file is a mistake worth
  // naming plainly rather than letting a cluster error stand in for it.
  try { assertSigned(doc.transactionBase64); } catch (error) { die(error.message); }
  if (!has('yes')) {
    console.log(`Would submit the launch of ${doc.mint} to ${new URL(rpc).host}.`);
    console.log('This cannot be undone, and after it lands the bitstring is safe to publish.');
    console.log('Add --yes to actually send it.');
    return;
  }
  const check = await simulate(doc.transactionBase64, { rpc, signed: true });
  if (!check.ok) {
    die(`Refusing to send: the cluster rejects this transaction (${JSON.stringify(check.err)}).\n${check.logs.slice(-8).map(l => `  ${l}`).join('\n')}`);
  }
  const { signature, explorer } = await send(doc.transactionBase64, { rpc });
  console.log(`sent ${signature}\n${explorer}`);
}

const COMMANDS = { prepare, sign, send: sendCommand };
try {
  const run = COMMANDS[command];
  if (!run) die(USAGE);
  await run();
} catch (error) {
  // One line the reader can act on. A stack trace here would only ever point at
  // this tool's internals when the problem is in the arguments.
  console.error(error instanceof Refused ? `${error.message}\n` : `${error.message}\n`);
  process.exit(1);
}
