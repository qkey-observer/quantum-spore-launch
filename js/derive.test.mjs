import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { planHash, saltFromBitstring } from './derive.mjs';

const vectors = JSON.parse(
  readFileSync(join(dirname(fileURLToPath(import.meta.url)), '../vectors/derive.json'), 'utf8'),
);

test('salt vectors match keccak256(utf8(bitstring))', () => {
  for (const row of vectors.salt) {
    assert.equal(saltFromBitstring(row.bitstring), row.salt, row.bitstring);
    assert.equal(saltFromBitstring(row.bitstring), saltFromBitstring(row.bitstring));
  }
});

test('short or non-bitstrings are rejected', () => {
  for (const bad of vectors.saltRejected) {
    assert.throws(() => saltFromBitstring(bad), /measured bitstring/);
  }
  assert.throws(() => saltFromBitstring('0'.repeat(257)), /measured bitstring/);
});

test('plan hash ignores key order but not values or array order', () => {
  for (const row of vectors.planHash) {
    assert.equal(planHash(row.plan), row.hash, row.name);
  }
  assert.notEqual(
    planHash({ chainId: 56, token: { name: 'QKEY', symbol: 'QKEY' }, tax: '0' }),
    planHash({ chainId: 56, token: { name: 'QKEY', symbol: 'QKEY' }, tax: '1' }),
  );
  assert.notEqual(planHash({ a: [1, 2] }), planHash({ a: [2, 1] }));
  assert.notEqual(planHash({ a: null }), planHash({}));
});
