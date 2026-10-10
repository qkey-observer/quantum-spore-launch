import test from 'node:test';
import assert from 'node:assert/strict';
import { assertSummable, formatUnits, readTreasury } from '../src/treasury.mjs';

const EVM = { id: 'a', kind: 'evm', chainId: 56, rpcUrl: 'https://a.test', holder: `0x${'a'.repeat(40)}`, token: null, symbol: 'X', decimals: 18 };
const EVM_B = { ...EVM, id: 'b', rpcUrl: 'https://b.test' };

function node({ chainId = '0x38', balance = '0x1' } = {}) {
  return async (url, options) => {
    const { method } = JSON.parse(options.body);
    const results = { eth_chainId: chainId, eth_blockNumber: '0x64', eth_getBalance: balance };
    if (!(method in results)) throw new Error(`unexpected ${method}`);
    return new Response(JSON.stringify({ jsonrpc: '2.0', id: 1, result: results[method] }), { status: 200 });
  };
}

test('amounts format without floating point', () => {
  assert.equal(formatUnits(20404567318780902800n, 18), '20.4045673187809028');
  assert.equal(formatUnits(1n, 18), '0.000000000000000001');
  assert.equal(formatUnits(0n, 9), '0');
});

// The rule the module exists for: a sum missing a term is unknown, not smaller.
test('an unreadable source makes the total unknown, never a partial sum', async () => {
  const fetchImpl = async (url, options) => {
    if (url === 'https://b.test') throw new Error('node down');
    return node({ balance: '0xde0b6b3a7640000' })(url, options);
  };
  const out = await readTreasury([EVM, EVM_B], { fetchImpl });
  assert.equal(out.complete, false);
  assert.equal(out.total, null);
  assert.equal(out.parts.length, 1, 'the readable part is still reported');
  assert.deepEqual(out.failures.map(f => f.id), ['b']);
  assert.match(out.note, /unknown rather than smaller/);
});

test('a chain answering for the wrong chain id is a failure, not a reading', async () => {
  const out = await readTreasury([EVM], { fetchImpl: node({ chainId: '0x1' }) });
  assert.equal(out.complete, false);
  assert.equal(out.total, null);
  assert.match(out.failures[0].reason, /chain 1, not 56/);
});

// Different decimals are different units. There is no total — but the readings
// are good, and throwing them away to signal one missing number helps nobody.
test('mismatched decimals drop the total and keep every part', async () => {
  const out = await readTreasury([EVM, { ...EVM_B, decimals: 6 }], { fetchImpl: node({ balance: '0xa' }) });
  assert.equal(out.complete, true);
  assert.equal(out.summable, false);
  assert.equal(out.total, null);
  assert.equal(out.parts.length, 2);
  assert.match(out.note, /disagree on decimals/);
  assert.throws(() => assertSummable([{ decimals: 18 }, { decimals: 6 }]), /cannot be added/);
});

test('sources that agree are added, and the parts sum to the total', async () => {
  const out = await readTreasury([EVM, EVM_B], { fetchImpl: node({ balance: '0xde0b6b3a7640000' }) });
  assert.equal(out.complete, true);
  assert.equal(out.summable, true);
  assert.equal(out.totalFormatted, '2');
  assert.equal(out.parts.reduce((sum, p) => sum + BigInt(p.amount), 0n).toString(), out.total);
});
