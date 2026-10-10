// One measured bitstring, two ways to fix an address.
//
// EVM chains use CREATE2: the salt is a hash of the shot, and the address falls
// out of the deployer, that salt and the init code. Solana has no CREATE2 at
// all — its deterministic address is a Program Derived Address, the first hash
// of the seeds that is NOT a point on the ed25519 curve, so that nobody can
// hold a key for it.
//
// Different arithmetic, same property: publish the bitstring and anyone
// recomputes the address. Nothing here signs, sends or deploys.
import { keccak_256 } from '@noble/hashes/sha3';
import { sha256 } from '@noble/hashes/sha256';
import { ed25519 } from '@noble/curves/ed25519';

const PDA_MARKER = new TextEncoder().encode('ProgramDerivedAddress');
const B58 = '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz';

export function assertBitstring(bitstring) {
  if (typeof bitstring !== 'string' || !/^[01]+$/.test(bitstring)) {
    throw new Error('A bitstring is the measured shot itself: ones and zeros, nothing else.');
  }
  return bitstring;
}

const utf8 = text => new TextEncoder().encode(text);
const hex = bytes => `0x${Buffer.from(bytes).toString('hex')}`;

/** EVM: salt = keccak256(utf8(bitstring)). */
export function saltFromBitstring(bitstring) {
  return hex(keccak_256(utf8(assertBitstring(bitstring))));
}

/** Solana: seed = sha256(utf8(bitstring)). */
export function seedFromBitstring(bitstring) {
  return sha256(utf8(assertBitstring(bitstring)));
}

export function base58Encode(bytes) {
  let zeros = 0;
  while (zeros < bytes.length && bytes[zeros] === 0) zeros += 1;
  const digits = [];
  for (let i = zeros; i < bytes.length; i += 1) {
    let carry = bytes[i];
    for (let j = 0; j < digits.length; j += 1) {
      carry += digits[j] << 8;
      digits[j] = carry % 58;
      carry = (carry / 58) | 0;
    }
    while (carry > 0) { digits.push(carry % 58); carry = (carry / 58) | 0; }
  }
  return '1'.repeat(zeros) + digits.reverse().map(d => B58[d]).join('');
}

export function base58Decode(text) {
  if (typeof text !== 'string' || text.length === 0) throw new Error('base58: empty input');
  let zeros = 0;
  while (zeros < text.length && text[zeros] === '1') zeros += 1;
  const bytes = [];
  for (let i = zeros; i < text.length; i += 1) {
    const value = B58.indexOf(text[i]);
    if (value < 0) throw new Error(`base58: invalid character ${text[i]}`);
    let carry = value;
    for (let j = 0; j < bytes.length; j += 1) {
      carry += bytes[j] * 58;
      bytes[j] = carry & 0xff;
      carry >>= 8;
    }
    while (carry > 0) { bytes.push(carry & 0xff); carry >>= 8; }
  }
  return Uint8Array.from(new Array(zeros).fill(0).concat(bytes.reverse()));
}

/** On the curve means someone could hold the private key. A PDA must not be.
 *
 * A catch that also swallows a missing API returns false for every input, the
 * bump search then takes its first candidate, and the derivation can hand back
 * an address somebody owns. The two failures are told apart deliberately. */
export function isOnCurve(bytes) {
  try {
    ed25519.ExtendedPoint.fromHex(bytes);
    return true;
  } catch (error) {
    if (error instanceof TypeError && /is not a function|undefined/.test(error.message)) {
      throw new Error(`ed25519 point decoding is unavailable, so off-curve cannot be checked: ${error.message}`);
    }
    return false;
  }
}

export function findProgramAddress(seeds, programId) {
  const program = typeof programId === 'string' ? base58Decode(programId) : programId;
  if (program.length !== 32) throw new Error('A program id is 32 bytes.');
  for (let bump = 255; bump >= 0; bump -= 1) {
    const parts = [...seeds, Uint8Array.of(bump), program, PDA_MARKER];
    const buffer = new Uint8Array(parts.reduce((sum, part) => sum + part.length, 0));
    let offset = 0;
    for (const part of parts) { buffer.set(part, offset); offset += part.length; }
    const candidate = sha256(buffer);
    if (!isOnCurve(candidate)) return { address: base58Encode(candidate), bytes: candidate, bump };
  }
  throw new Error('No off-curve address for these seeds.');
}

export function deriveSolana(bitstring, programId) {
  const seed = seedFromBitstring(bitstring);
  const { address, bump } = findProgramAddress([seed], programId);
  return { kind: 'solana', mechanism: 'pda', bitstring, seed: hex(seed), programId, address, bump };
}

/** EVM CREATE2. initCodeHash is the caller's: it commits to the token's whole identity. */
export function deriveCreate2({ bitstring, deployer, initCodeHash, namespace = null }) {
  const salt = namespace ?? saltFromBitstring(bitstring);
  for (const [name, value] of [['deployer', deployer], ['initCodeHash', initCodeHash]]) {
    if (typeof value !== 'string') throw new Error(`${name} is required.`);
  }
  if (!/^0x[0-9a-fA-F]{40}$/.test(deployer)) throw new Error('deployer is not an EVM address.');
  if (!/^0x[0-9a-fA-F]{64}$/.test(initCodeHash)) throw new Error('initCodeHash is not 32 bytes.');
  if (!/^0x[0-9a-fA-F]{64}$/.test(salt)) throw new Error('salt is not 32 bytes.');
  const buffer = new Uint8Array(85);
  buffer[0] = 0xff;
  buffer.set(Buffer.from(deployer.slice(2), 'hex'), 1);
  buffer.set(Buffer.from(salt.slice(2), 'hex'), 21);
  buffer.set(Buffer.from(initCodeHash.slice(2), 'hex'), 53);
  const digest = keccak_256(buffer);
  return {
    kind: 'evm', mechanism: 'create2', bitstring,
    salt, deployer, initCodeHash,
    address: `0x${Buffer.from(digest.slice(12)).toString('hex')}`,
  };
}
