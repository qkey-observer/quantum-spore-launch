// pump.fun: the mint is a keypair, not a derived address.
//
// On this launchpad the token's address IS an ed25519 public key, and the
// matching private key signs the create transaction. That is how vanity
// addresses ending in "pump" are produced — by grinding keypairs.
//
// So a measurement fixes an address by seeding that keypair:
//
//   seed = sha256(utf8(bitstring))   ->   ed25519 keypair   ->   public key = mint
//
// WHICH MEANS THE BITSTRING IS THE PRIVATE KEY. Anyone holding it can sign for
// that mint. Publishing a shot before its launch hands the token to whoever
// reads it first, so the order is not a narrative choice here, it is the
// security property:
//
//   measure -> publish the ADDRESS -> launch -> publish the bitstring
//
// After the launch, pump.fun has moved mint authority to the bonding curve and
// the key no longer controls anything; before it, the key is everything. This
// module derives and never stores: the secret is returned to the caller that
// asked for it, and the address path never produces one.
import { ed25519 } from '@noble/curves/ed25519';
import { sha256 } from '@noble/hashes/sha256';
import { assertBitstring, base58Decode, base58Encode, findProgramAddress } from './index.mjs';

export const PUMP_PROGRAM_ID = '6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P';
const BONDING_CURVE_SEED = new TextEncoder().encode('bonding-curve');

/** The address a shot fixes. No secret is produced or returned. */
export function mintAddressFromBitstring(bitstring) {
  const seed = sha256(new TextEncoder().encode(assertBitstring(bitstring)));
  return base58Encode(ed25519.getPublicKey(seed));
}

/**
 * The signing key for that mint. Separate from the address path on purpose:
 * code that only needs to predict an address must not be able to obtain a key
 * by accident, and a reviewer can see which callers asked for one.
 */
export function mintKeypairFromBitstring(bitstring) {
  const secret = sha256(new TextEncoder().encode(assertBitstring(bitstring)));
  const publicKey = ed25519.getPublicKey(secret);
  return {
    address: base58Encode(publicKey),
    publicKey,
    secret,
    warning: 'This secret key is recoverable by anyone holding the bitstring. Do not publish the bitstring until after the launch.',
  };
}

/** pump.fun derives the curve account from the mint. Checked against a real
 *  launched token rather than taken from documentation. */
export function bondingCurveFor(mint, programId = PUMP_PROGRAM_ID) {
  const bytes = mint instanceof Uint8Array ? mint : base58Decode(mint);
  if (bytes.length !== 32) throw new Error('A mint address is 32 bytes.');
  return findProgramAddress([BONDING_CURVE_SEED, bytes], programId);
}
