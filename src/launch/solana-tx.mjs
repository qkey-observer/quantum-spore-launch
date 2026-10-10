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
