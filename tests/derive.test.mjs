import test from 'node:test';
import assert from 'node:assert/strict';
import { keccak_256 } from '@noble/hashes/sha3';
import { base58Decode, base58Encode, deriveCreate2, deriveSolana, findProgramAddress, isOnCurve, saltFromBitstring, seedFromBitstring } from '../src/derive/index.mjs';

const TOKEN_PROGRAM = 'TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA';
const hash = bytes => `0x${Buffer.from(keccak_256(bytes)).toString('hex')}`;

// The four vectors from EIP-1014 itself. If CREATE2 here ever stops matching
// them, every predicted EVM address this service produces is wrong.
test('CREATE2 matches all four EIP-1014 vectors', () => {
  const vectors = [
    ['0x0000000000000000000000000000000000000000', `0x${'00'.repeat(32)}`, Uint8Array.of(0), '0x4d1a2e2bb4f88f0250f26ffff098b0b30b26bf38'],
    ['0xdeadbeef00000000000000000000000000000000', `0x${'00'.repeat(32)}`, Uint8Array.of(0), '0xb928f69bb1d91cd65274e3c79d8986362984fda3'],
    ['0xdeadbeef00000000000000000000000000000000', '0x000000000000000000000000feed000000000000000000000000000000000000', Uint8Array.of(0), '0xd04116cdd17bebe565eb2422f2497e06cc1c9833'],
    ['0x0000000000000000000000000000000000000000', `0x${'00'.repeat(32)}`, Uint8Array.from([0xde, 0xad, 0xbe, 0xef]), '0x70f2b2914a2a4b783faefb75f459a580616fcb5e'],
  ];
  for (const [deployer, salt, initCode, expected] of vectors) {
    const out = deriveCreate2({ bitstring: '0', deployer, initCodeHash: hash(initCode), namespace: salt });
    assert.equal(out.address.toLowerCase(), expected);
  }
});

// Checked against @solana/web3.js on both vectors, including one whose first
// candidate sits on the curve and forces the bump down.
test('the Solana PDA matches @solana/web3.js, address and bump', () => {
  const a = deriveSolana('1001001000010000000100000000000000000000000000000000000000000000', TOKEN_PROGRAM);
  assert.equal(a.address, '9aSau9cm4EkvMRH9G6cNqXL3qDMJaRV6RvuoxujC8K1E');
  assert.equal(a.bump, 255);
  const b = deriveSolana('0', TOKEN_PROGRAM);
  assert.equal(b.address, '4ZezGfrgZ6k4bHjX7jRXprjnjyY4t58rTLFvdHHdbJTd');
  assert.equal(b.bump, 254);
});

// If the curve check silently returned false for everything, every derivation
// would return bump 255 and still look correct.
test('the curve check answers both ways', () => {
  const { bytes } = findProgramAddress([seedFromBitstring('0111')], TOKEN_PROGRAM);
  assert.equal(isOnCurve(bytes), false);
  assert.equal(isOnCurve(base58Decode(TOKEN_PROGRAM)), true);
});

test('base58 round-trips, including an all-zero value', () => {
  assert.equal(base58Encode(new Uint8Array(32)), '1'.repeat(32));
  assert.equal(base58Decode('1'.repeat(32)).length, 32);
  assert.equal(base58Encode(base58Decode(TOKEN_PROGRAM)), TOKEN_PROGRAM);
  assert.throws(() => base58Decode('0OIl'), /invalid character/);
});

test('only a measured shot is accepted, on either chain', () => {
  for (const bad of ['', '0x01', '012', 'abc', null]) {
    assert.throws(() => saltFromBitstring(bad), /measured shot/);
    assert.throws(() => deriveSolana(bad, TOKEN_PROGRAM), /measured shot/);
  }
});

test('one shot gives one address, and a different shot a different one', () => {
  assert.equal(deriveSolana('0111', TOKEN_PROGRAM).address, deriveSolana('0111', TOKEN_PROGRAM).address);
  assert.notEqual(deriveSolana('0110', TOKEN_PROGRAM).address, deriveSolana('0111', TOKEN_PROGRAM).address);
});
