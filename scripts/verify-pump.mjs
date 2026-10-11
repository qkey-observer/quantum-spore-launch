#!/usr/bin/env node
// Check this repo's pump.fun launch builder against the chain itself, in the
// only two ways that actually settle it:
//
//   1. Against the program's own Anchor IDL, which pump publishes on chain:
//      the discriminator, the account names and their order, the argument types.
//   2. Against real launches: decode what somebody's transaction sent, feed
//      those same inputs back into the builder, and require the instruction to
//      come out byte for byte identical — accounts, flags and data.
//
// Step 2 is the one worth having. An IDL can be stale, and a builder written
// from a stale IDL agrees with it perfectly while producing transactions the
// program rejects.
import zlib from 'node:zlib';
import { findProgramAddress, base58Decode, base58Encode } from '../src/derive/index.mjs';
import { buildCreateV2, CREATE_V2_DISCRIMINATOR, IDL_ACCOUNT, PROGRAMS } from '../src/launch/pump-create.mjs';
import { buildBuyV2, buyV2Accounts, BUY_V2_DISCRIMINATOR, readGlobalState, readLookupTable } from '../src/launch/pump-buy.mjs';
import { createSolanaClient } from '../src/chains/solana.mjs';

const RPC = process.env.SOLANA_RPC_URL ?? 'https://api.mainnet-beta.solana.com';
const SAMPLES = Number(process.env.SAMPLES ?? 6);
// Sampled separately from the creates: a quarter of launches carry no buy at
// all, so a window of a few launches can hold none, and "none found" would then
// read as a failure of the builder rather than of the window.
const BUY_SAMPLES = Number(process.env.BUY_SAMPLES ?? 2);
// Touched by create and create_v2 and by nothing else, so its signature history
// is a list of launches rather than of trades.
const MINT_AUTHORITY = findProgramAddress([new TextEncoder().encode('mint-authority')], PROGRAMS.pump).address;
const hex = u8 => [...u8].map(b => b.toString(16).padStart(2, '0')).join('');

let id = 0;
async function rpc(method, params) {
  for (let attempt = 0; attempt < 8; attempt++) {
    const res = await fetch(RPC, {
      method: 'POST', headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ jsonrpc: '2.0', id: ++id, method, params }),
    });
    if (res.status === 429) { await new Promise(r => setTimeout(r, 1200 * (attempt + 1))); continue; }
    const body = await res.json();
    if (body.error) throw new Error(`${method}: ${body.error.message}`);
    return body.result;
  }
  throw new Error(`${method}: rate limited by ${new URL(RPC).host}`);
}

const problems = [];
const report = (ok, line) => { console.log(`  ${ok ? '✓' : '✗'} ${line}`); if (!ok) problems.push(line); };

console.log(`\nIDL account ${IDL_ACCOUNT}`);
const idlAccount = await rpc('getAccountInfo', [IDL_ACCOUNT, { encoding: 'base64' }]);
if (!idlAccount?.value) {
  report(false, 'no IDL on chain — cannot check the ABI this way');
} else {
  const raw = Buffer.from(idlAccount.value.data[0], 'base64');
  const idl = JSON.parse(zlib.inflateSync(raw.subarray(44, 44 + raw.readUInt32LE(40))).toString('utf8'));
  const ix = idl.instructions.find(i => i.name === 'create_v2');
  report(idlAccount.value.owner === PROGRAMS.pump, `owned by the pump program`);
  report(!!ix, 'create_v2 is in the IDL');
  if (ix) {
    report(hex(Uint8Array.from(ix.discriminator)) === hex(CREATE_V2_DISCRIMINATOR), `discriminator ${hex(CREATE_V2_DISCRIMINATOR)}`);
    const built = buildCreateV2({
      mint: base58Encode(new Uint8Array(32).fill(7)), user: base58Encode(new Uint8Array(32).fill(9)),
      name: 'n', symbol: 's', uri: 'https://x/y',
    });
    report(ix.accounts.length === built.keys.length, `${built.keys.length} accounts`);
    const names = ix.accounts.map(a => a.name).join(',');
    const ours = buildCreateV2({
      mint: base58Encode(new Uint8Array(32).fill(7)), user: base58Encode(new Uint8Array(32).fill(9)),
      name: 'n', symbol: 's', uri: 'https://x/y',
    }).accountNames.join(',');
    report(names === ours, 'account names and order');
    for (let i = 0; i < Math.min(ix.accounts.length, built.keys.length); i++) {
      const a = ix.accounts[i];
      const k = built.keys[i];
      if (!!a.signer !== k.isSigner || !!a.writable !== k.isWritable) {
        report(false, `flags on ${a.name}: IDL says ${a.signer ? 's' : '-'}${a.writable ? 'w' : '-'}, we send ${k.isSigner ? 's' : '-'}${k.isWritable ? 'w' : '-'}`);
      }
    }
    report(ix.args.map(a => a.name).join(',') === 'name,symbol,uri,creator,is_mayhem_mode,is_cashback_enabled,creator_fee_bps,is_holder_reward', 'argument names and order');
  }
}

console.log(`\nReal launches, via the mint authority's history (${MINT_AUTHORITY})`);
const signatures = await rpc('getSignaturesForAddress', [MINT_AUTHORITY, { limit: Math.max(SAMPLES * 4, 60) }]);
let checked = 0;
let buysChecked = 0;
let legacyCreate = 0;
for (const entry of signatures) {
  if (checked >= SAMPLES && buysChecked >= BUY_SAMPLES) break;
  if (entry.err) continue;
  const tx = await rpc('getTransaction', [entry.signature, { encoding: 'json', maxSupportedTransactionVersion: 1 }]);
  if (!tx) continue;
  const message = tx.transaction.message;
  const loaded = tx.meta.loadedAddresses ?? { writable: [], readonly: [] };
  const keys = [...message.accountKeys, ...loaded.writable, ...loaded.readonly];
  // The creator a buy pays its creator fee to is the create's `creator`
  // argument, not necessarily the buyer — launches do separate the two. So it
  // is read from the create in the same transaction before any buy is checked.
  let launchCreator = null;
  for (const ix of message.instructions) {
    if (keys[ix.programIdIndex] !== PROGRAMS.pump) continue;
    const data = base58Decode(ix.data);
    if (hex(data.slice(0, 8)) !== hex(CREATE_V2_DISCRIMINATOR)) continue;
    const view = new DataView(data.buffer, data.byteOffset, data.byteLength);
    let offset = 8;
    for (let field = 0; field < 3; field++) offset += 4 + view.getUint32(offset, true);
    launchCreator = base58Encode(data.slice(offset, offset + 32));
  }
  for (const ix of message.instructions) {
    if (keys[ix.programIdIndex] !== PROGRAMS.pump) continue;
    const data = base58Decode(ix.data);
    // The dev buy that rides along in the same transaction. Its accounts are
    // derived from the mint and the user except for the two fee recipients,
    // which the launch chose from pools — those are fed back in as inputs.
    if (hex(data.slice(0, 8)) === hex(BUY_V2_DISCRIMINATOR)) {
      if (buysChecked >= BUY_SAMPLES || !launchCreator) continue;
      const sent = ix.accounts.map(n => keys[n]);
      if (sent.length < 27) continue;
      const separate = launchCreator !== sent[13];
      console.log(`  ${entry.signature.slice(0, 12)}…  buy_v2 bundled with the create${separate ? '  (creator is not the buyer)' : ''}`);
      const derived = buyV2Accounts({
        mint: sent[1], user: sent[13], creator: launchCreator,
        feeRecipient: sent[6], buybackFeeRecipient: sent[8],
      }).map(a => a.pubkey);
      const same = derived.join(',') === sent.slice(0, 27).join(',');
      report(same, `    buy_v2: its ${derived.length} accounts reproduced in order`);
      const rebuilt = buildBuyV2({
        mint: sent[1], user: sent[13], creator: launchCreator,
        feeRecipient: sent[6], buybackFeeRecipient: sent[8],
        amount: new DataView(data.buffer, data.byteOffset + 8, 8).getBigUint64(0, true),
        maxSolCost: new DataView(data.buffer, data.byteOffset + 16, 8).getBigUint64(0, true),
      });
      report(hex(rebuilt.data) === hex(data), '    buy_v2: instruction data reproduced byte for byte');
      buysChecked++;
      continue;
    }
    if (hex(data.slice(0, 8)) !== hex(CREATE_V2_DISCRIMINATOR)) { if (data.length > 8) legacyCreate++; continue; }
    if (checked >= SAMPLES) continue;
    checked++;

    const view = new DataView(data.buffer, data.byteOffset, data.byteLength);
    let offset = 8;
    const string = () => {
      const length = view.getUint32(offset, true); offset += 4;
      const value = new TextDecoder().decode(data.slice(offset, offset + length)); offset += length;
      return value;
    };
    const name = string(), symbol = string(), uri = string();
    const creator = base58Encode(data.slice(offset, offset + 32)); offset += 32;
    const tail = data.slice(offset);
    const sentMint = keys[ix.accounts[0]];

    // Some clients stop early: pump's OptionBool/OptionU64 arguments tolerate a
    // short buffer, so a launch can leave the last fields off. Rebuilding with
    // the flags that transaction actually carried is the comparison that means
    // something; the builder always writes all four.
    const built = buildCreateV2({
      mint: sentMint, user: keys[ix.accounts[5]], name, symbol, uri, creator,
      isMayhemMode: tail[0] === 1,
      isCashbackEnabled: tail[1] === 1,
      creatorFeeBps: tail.length >= 10 ? new DataView(tail.buffer, tail.byteOffset + 2, 8).getBigUint64(0, true) : 0,
      isHolderReward: tail[10] === 1,
    });

    const short = tail.length < 11;
    const sameData = short
      ? hex(built.data.slice(0, 8 + offset - 8 + tail.length)) === hex(data)
      : hex(built.data) === hex(data);
    // Accounts beyond the sixteen create_v2 declares are Anchor's
    // remaining_accounts: the program does not read them, and bundlers do
    // append them. Comparing the full list would fail on those launches for a
    // reason that has nothing to do with this builder.
    const sent = ix.accounts.map(n => keys[n]);
    const extras = sent.length - built.keys.length;
    const sameAccounts = built.keys.map(k => k.pubkey).join(',') === sent.slice(0, built.keys.length).join(',');
    console.log(`  ${entry.signature.slice(0, 12)}…  ${symbol.padEnd(12)} ${sent.length} accounts  ${data.length}B${short ? '  (short argument buffer)' : ''}${extras > 0 ? `  (${extras} trailing extras)` : ''}`);
    report(sameAccounts, `    the ${built.keys.length} declared accounts reproduced in order`);
    report(sameData, `    instruction data reproduced byte for byte${short ? ' up to the bytes it sent' : ''}`);
  }
}
report(checked > 0, `found ${checked} create_v2 launch${checked === 1 ? '' : 'es'} to check against`);
// Across 60 launches, finding no buy_v2 at all would itself be news: it would
// mean launches have moved to another instruction, and this builder with them.
report(buysChecked > 0, `found ${buysChecked} bundled buy_v2${buysChecked === 1 ? '' : 's'} to check against${buysChecked ? '' : ' in the last 60 launches — have launches moved to another buy instruction?'}`);

console.log('\nThe launchpad state a dev buy needs');
try {
  const call = createSolanaClient({ rpcUrl: RPC });
  const global = await readGlobalState(call);
  report(global.feeRecipients.length === 7, `${global.feeRecipients.length} fee recipients in the pool`);
  report(global.buybackFeeRecipients.length === 8, `${global.buybackFeeRecipients.length} buyback fee recipients in the pool`);
  report(global.feeBasisPoints + global.creatorFeeBasisPoints > 0n, `fees ${global.feeBasisPoints}+${global.creatorFeeBasisPoints} basis points`);
  report(global.initialVirtualSolReserves > 0n && global.initialVirtualTokenReserves > 0n, 'the curve publishes its starting reserves');
  const table = await readLookupTable(call);
  // Without this table a create and a buy do not fit in one transaction, so a
  // table that has shrunk or moved is worth knowing about before a launch.
  report(table.addresses.length > 0, `the launch lookup table holds ${table.addresses.length} addresses`);
} catch (error) {
  report(false, `could not read the launchpad state: ${error.message}`);
}
if (legacyCreate) console.log(`  (${legacyCreate} launch${legacyCreate === 1 ? '' : 'es'} in this window used a different pump instruction)`);

console.log(problems.length ? `\n${problems.length} problem(s)\n` : '\nEverything checked out.\n');
process.exit(problems.length ? 1 : 0);
