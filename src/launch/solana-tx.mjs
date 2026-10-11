// Serialise a legacy Solana message and an unsigned transaction. Kept apart
// from any launchpad so the encoding can be tested on its own, and so nothing
// here needs to know what is being launched.
import { base58Decode, base58Encode } from '../derive/index.mjs';

export const SYSTEM_PROGRAM = '11111111111111111111111111111111';

function compactU16(n) {
  // Solana's "short vec": 7 bits per byte, low group first.
  const out = [];
  let rest = n;
  do { let byte = rest & 0x7f; rest >>= 7; if (rest) byte |= 0x80; out.push(byte); } while (rest);
  return out;
}

const keyOf = value => {
  const bytes = value instanceof Uint8Array ? value : base58Decode(value);
  if (bytes.length !== 32) throw new Error('A Solana address is 32 bytes.');
  return bytes;
};

/**
 * Collapse the instructions' accounts into the single ordered table a message
 * carries. The order is part of the format, not a preference: writable signers,
 * readonly signers, writable others, readonly others, with the fee payer first.
 */
export function compileMessage({ payer, instructions, recentBlockhash }) {
  if (!instructions?.length) throw new Error('A transaction needs at least one instruction.');
  const metas = new Map();
  const note = (address, { isSigner = false, isWritable = false }) => {
    const existing = metas.get(address);
    // Flags accumulate. An account that is writable in one instruction and
    // readonly in another is writable in the message, or the writable use of it
    // fails for a reason that looks nothing like its cause.
    if (existing) { existing.isSigner ||= isSigner; existing.isWritable ||= isWritable; return; }
    metas.set(address, { address, isSigner, isWritable });
  };
  note(payer, { isSigner: true, isWritable: true });
  for (const ix of instructions) {
    for (const account of ix.keys) note(account.pubkey, account);
    note(ix.programId, {});
  }

  const all = [...metas.values()];
  const rank = m => (m.isSigner ? 0 : 2) + (m.isWritable ? 0 : 1);
  const ordered = [
    all.find(m => m.address === payer),
    ...all.filter(m => m.address !== payer).sort((a, b) => rank(a) - rank(b)),
  ];
  const index = new Map(ordered.map((m, i) => [m.address, i]));

  const header = {
    numRequiredSignatures: ordered.filter(m => m.isSigner).length,
    numReadonlySignedAccounts: ordered.filter(m => m.isSigner && !m.isWritable).length,
    numReadonlyUnsignedAccounts: ordered.filter(m => !m.isSigner && !m.isWritable).length,
  };

  const bytes = [
    header.numRequiredSignatures, header.numReadonlySignedAccounts, header.numReadonlyUnsignedAccounts,
    ...compactU16(ordered.length), ...ordered.flatMap(m => [...keyOf(m.address)]),
    ...keyOf(recentBlockhash),
    ...compactU16(instructions.length),
  ];
  for (const ix of instructions) {
    bytes.push(index.get(ix.programId));
    bytes.push(...compactU16(ix.keys.length), ...ix.keys.map(k => index.get(k.pubkey)));
    bytes.push(...compactU16(ix.data.length), ...ix.data);
  }
  return { bytes: Uint8Array.from(bytes), header, accounts: ordered, signers: ordered.filter(m => m.isSigner).map(m => m.address) };
}

/**
 * Parse an address lookup table account into the addresses it holds.
 *
 * A table is what makes a transaction with many accounts fit at all: each
 * address it supplies costs one index byte in the message instead of 32 bytes
 * of key. The header below is the on-chain layout — a u32 kind, two slots, a
 * start index, an optional authority and two bytes of padding — and everything
 * after it is a flat array of keys.
 */
export function parseLookupTable(data) {
  const HEADER = 4 + 8 + 8 + 1 + 1 + 32 + 2;
  const bytes = data instanceof Uint8Array ? data : new Uint8Array(data);
  if (bytes.length < HEADER) throw new Error('That account is too short to be an address lookup table.');
  const body = bytes.length - HEADER;
  if (body % 32 !== 0) throw new Error('The lookup table does not end on an address boundary.');
  return Array.from({ length: body / 32 }, (_, i) => base58Encode(bytes.slice(HEADER + i * 32, HEADER + (i + 1) * 32)));
}

/**
 * Compile a version 0 message, moving whatever it can into address lookup
 * tables.
 *
 * Needed because create and the dev buy do not fit in one legacy transaction:
 * together they touch more accounts than 1232 bytes of message can name, and
 * splitting them into two transactions reopens the gap this bundling exists to
 * close. Real launches solve it the same way, with one table.
 *
 * Three kinds of account have to stay in the static list, and the partition
 * below follows what live launches actually do rather than a reading of the
 * rules: signers, the program id of any top-level instruction, and anything the
 * table does not happen to contain.
 */
export function compileV0Message({ payer, instructions, recentBlockhash, lookupTables = [] }) {
  if (!instructions?.length) throw new Error('A transaction needs at least one instruction.');
  const metas = new Map();
  const note = (address, { isSigner = false, isWritable = false }) => {
    const existing = metas.get(address);
    if (existing) { existing.isSigner ||= isSigner; existing.isWritable ||= isWritable; return; }
    metas.set(address, { address, isSigner, isWritable });
  };
  note(payer, { isSigner: true, isWritable: true });
  const topLevelPrograms = new Set(instructions.map(ix => ix.programId));
  for (const ix of instructions) {
    for (const account of ix.keys) note(account.pubkey, account);
    note(ix.programId, {});
  }

  const tables = lookupTables.map(table => ({ address: table.address, addresses: table.addresses, writable: [], readonly: [] }));
  const findInTable = address => {
    for (const table of tables) {
      const index = table.addresses.indexOf(address);
      if (index !== -1 && index <= 255) return { table, index };
    }
    return null;
  };

  const statics = [];
  const loadedWritable = [];
  const loadedReadonly = [];
  for (const meta of metas.values()) {
    const mustStay = meta.isSigner || topLevelPrograms.has(meta.address);
    const found = mustStay ? null : findInTable(meta.address);
    if (!found) { statics.push(meta); continue; }
    found.table[meta.isWritable ? 'writable' : 'readonly'].push(found.index);
    (meta.isWritable ? loadedWritable : loadedReadonly).push(meta.address);
  }

  const rank = m => (m.isSigner ? 0 : 2) + (m.isWritable ? 0 : 1);
  const ordered = [
    statics.find(m => m.address === payer),
    ...statics.filter(m => m.address !== payer).sort((a, b) => rank(a) - rank(b)),
  ];
  const index = new Map();
  ordered.forEach((m, i) => index.set(m.address, i));
  loadedWritable.forEach((address, i) => index.set(address, ordered.length + i));
  loadedReadonly.forEach((address, i) => index.set(address, ordered.length + loadedWritable.length + i));

  const header = {
    numRequiredSignatures: ordered.filter(m => m.isSigner).length,
    numReadonlySignedAccounts: ordered.filter(m => m.isSigner && !m.isWritable).length,
    numReadonlyUnsignedAccounts: ordered.filter(m => !m.isSigner && !m.isWritable).length,
  };

  const bytes = [
    0x80, // the version prefix: the high bit set, version 0 in the low bits.
    header.numRequiredSignatures, header.numReadonlySignedAccounts, header.numReadonlyUnsignedAccounts,
    ...compactU16(ordered.length), ...ordered.flatMap(m => [...keyOf(m.address)]),
    ...keyOf(recentBlockhash),
    ...compactU16(instructions.length),
  ];
  for (const ix of instructions) {
    bytes.push(index.get(ix.programId));
    bytes.push(...compactU16(ix.keys.length), ...ix.keys.map(k => index.get(k.pubkey)));
    bytes.push(...compactU16(ix.data.length), ...ix.data);
  }
  const used = tables.filter(table => table.writable.length || table.readonly.length);
  bytes.push(...compactU16(used.length));
  for (const table of used) {
    bytes.push(...keyOf(table.address));
    bytes.push(...compactU16(table.writable.length), ...table.writable);
    bytes.push(...compactU16(table.readonly.length), ...table.readonly);
  }
  return {
    bytes: Uint8Array.from(bytes), header,
    accounts: ordered,
    signers: ordered.filter(m => m.isSigner).map(m => m.address),
    staticCount: ordered.length,
    loaded: { writable: loadedWritable, readonly: loadedReadonly },
  };
}

/**
 * The wire transaction with the signatures left as zeroes. It is not valid to
 * submit — that is the point. Whoever holds the keys signs the `message` bytes
 * and fills the slots in, on their own machine.
 */
export function unsignedTransaction(message) {
  const blanks = new Uint8Array(64 * message.header.numRequiredSignatures);
  const wire = Uint8Array.from([...compactU16(message.header.numRequiredSignatures), ...blanks, ...message.bytes]);
  return {
    message: message.bytes,
    messageBase64: Buffer.from(message.bytes).toString('base64'),
    transactionBase64: Buffer.from(wire).toString('base64'),
    signatureSlots: message.signers,
    signaturesPresent: 0,
  };
}

export const encodeString = value => {
  const utf8 = new TextEncoder().encode(value);
  const length = new Uint8Array(4);
  new DataView(length.buffer).setUint32(0, utf8.length, true);
  return Uint8Array.from([...length, ...utf8]);
};

export const encodeU64 = value => {
  const out = new Uint8Array(8);
  new DataView(out.buffer).setBigUint64(0, BigInt(value), true);
  return out;
};

export const addressOf = keyOf;
export { base58Encode };
