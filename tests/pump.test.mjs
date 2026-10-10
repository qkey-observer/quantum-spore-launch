import test from 'node:test';
import assert from 'node:assert/strict';
import { bondingCurveFor, mintAddressFromBitstring, mintKeypairFromBitstring, PUMP_PROGRAM_ID } from '../src/derive/pump.mjs';

const SHOT = '1001001000010000000100000000000000000000000000000000000000000000';

// Checked against @solana/web3.js: Keypair.fromSeed(sha256(bits)) and
// findProgramAddressSync(["bonding-curve", mint]) produce exactly these.
test('the mint and its curve match @solana/web3.js', () => {
  assert.equal(mintAddressFromBitstring(SHOT), 'AruKhDcqVmq4g4xMnCMx1YJXprZsWuJm1tVeWNeY4JGn');
  const curve = bondingCurveFor('AruKhDcqVmq4g4xMnCMx1YJXprZsWuJm1tVeWNeY4JGn');
  assert.equal(curve.address, 'CzRZyARDFdGzGo4Q1mLLbVPy6UKm4kWfKJmiyTXuWRWL');
  assert.equal(curve.bump, 255);
});

// These three are real pump.fun launches. Their curve accounts appeared in the
// same transactions as their mints, which is what settles the seeds — the
// derivation is checked against the chain, not against documentation. The
// varying bumps also prove the off-curve search is exercised rather than
// always taking its first candidate.
test('the curve seeds reproduce real launched tokens', () => {
  const launched = [
    ['7PFSE8CUbWCfRqnxsEQ3WM4FbRTSvKKCPB79Vk7Vpump', '9gP8bMavpUepcDyzGgakELXYP6rfHSpdnwqrnCFfr6dt', 255],
    ['HwT68ZHTDkkvq8nouCkwvmYvn1g6v8uhPCf6B5gMpump', '23JoPgHKSoJbJuNj8tKmRBmQRQDc5ti9Kvm1NUkrrbkv', 250],
    ['B4hnwQSJvbhrhTYmsuvzjEWQFL3ddq47tGErygtcpump', '9AT9PvPPQg7P9DRGY9bNdvEEeZVaDN3CDPurNzDFo9r2', 254],
  ];
  for (const [mint, curve, bump] of launched) {
    const derived = bondingCurveFor(mint);
    assert.equal(derived.address, curve, `curve for ${mint}`);
    assert.equal(derived.bump, bump);
  }
});

// The address path must not be able to hand anyone a key by accident. On this
// launchpad the bitstring IS the private key, so which function a caller
// reached for is the difference between publishing an address and publishing
// control of the token.
test('the address path yields no secret, and the key path says what it is', () => {
  const address = mintAddressFromBitstring(SHOT);
  assert.equal(typeof address, 'string');

  const keypair = mintKeypairFromBitstring(SHOT);
  assert.equal(keypair.address, address, 'both paths agree on the address');
  assert.equal(keypair.secret.length, 32);
  assert.match(keypair.warning, /recoverable by anyone holding the bitstring/);
  assert.match(keypair.warning, /until after the launch/);
});

test('anyone holding the bitstring can recompute the key, which is the whole risk', () => {
  // Stated as a test because it is the property the launch order exists for.
  const mine = mintKeypairFromBitstring(SHOT);
  const theirs = mintKeypairFromBitstring(SHOT);
  assert.deepEqual([...theirs.secret], [...mine.secret]);
  assert.equal(theirs.address, mine.address);
});

test('only a measured shot derives a mint, and the program id is pinned', () => {
  assert.equal(PUMP_PROGRAM_ID, '6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P');
  for (const bad of ['', '0x01', '012', 'abc', null]) {
    assert.throws(() => mintAddressFromBitstring(bad), /measured shot/);
    assert.throws(() => mintKeypairFromBitstring(bad), /measured shot/);
  }
  assert.throws(() => bondingCurveFor('not-a-mint'), /invalid character|32 bytes/);
});
