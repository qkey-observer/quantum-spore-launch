// Read-only EVM access.
//
// The allowlist is the point. An RPC client that forwards any method is an open
// proxy, and one reachable from a public API is someone else's node to abuse.
const READ_METHODS = new Set(['eth_chainId', 'eth_blockNumber', 'eth_getBalance', 'eth_getCode', 'eth_call']);
const BALANCE_OF = '0x70a08231';

export function isEvmAddress(value) {
  return typeof value === 'string' && /^0x[0-9a-fA-F]{40}$/.test(value);
}

function assertAddress(value, name) {
  if (!isEvmAddress(value)) throw new Error(`${name} is not an EVM address.`);
  return value;
}

/** QUANTITY is minimally encoded; a padded word is a different thing and decoded separately. */
export function parseQuantity(value) {
  if (typeof value !== 'string' || !/^0x(0|[1-9a-fA-F][0-9a-fA-F]*)$/.test(value)) {
    throw new Error('Node returned a malformed quantity.');
  }
  return BigInt(value);
}

export function parseUint256Word(value) {
  if (typeof value !== 'string' || !/^0x[0-9a-fA-F]{64}$/.test(value)) {
    throw new Error('Node returned a malformed 32-byte word.');
  }
  return BigInt(value);
}

export function createEvmClient({ rpcUrl, fetchImpl = fetch, timeoutMs = 8000, allowCall = () => false }) {
  if (typeof rpcUrl !== 'string') throw new Error('An EVM RPC URL is required.');
  const parsed = new URL(rpcUrl);
  if (parsed.protocol !== 'https:' && !(parsed.protocol === 'http:' && ['localhost', '127.0.0.1', '[::1]'].includes(parsed.hostname))) {
    throw new Error('An EVM RPC URL must be HTTPS, or a local node.');
  }
  let id = 0;
  return async function call(method, params = []) {
    if (!READ_METHODS.has(method)) throw new Error(`RPC method not allowed: ${method}`);
    // eth_call is the one method that can reach arbitrary contract code, so it
    // is narrowed further: only the reads this service was configured to make.
    if (method === 'eth_call' && !allowCall(params)) throw new Error('This eth_call is not on the allowlist.');
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const response = await fetchImpl(rpcUrl, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ jsonrpc: '2.0', id: ++id, method, params }),
        signal: controller.signal,
      });
      if (!response.ok) throw new Error(`EVM node returned HTTP ${response.status}.`);
      const body = await response.json();
      if (body.error) throw new Error(`EVM node refused ${method}.`);
      if (!('result' in body)) throw new Error(`EVM node returned no result for ${method}.`);
      return body.result;
    } finally {
      clearTimeout(timer);
    }
  };
}

/** Proven before anything else is read: a URL repointed at another chain is caught here. */
export async function assertChainId(call, expected) {
  const actual = parseQuantity(await call('eth_chainId'));
  if (actual !== BigInt(expected)) throw new Error(`Node is chain ${actual}, not ${expected}.`);
  return actual;
}

export function balanceOfCalldata(holder) {
  return `${BALANCE_OF}${assertAddress(holder, 'Holder').slice(2).toLowerCase().padStart(64, '0')}`;
}

/** Native or ERC-20, both pinned to one block so the figures agree with each other. */
export async function readBalance(call, { holder, token = null, decimals = 18 }) {
  assertAddress(holder, 'Holder');
  const blockTag = await call('eth_blockNumber');
  const amount = token === null
    ? parseQuantity(await call('eth_getBalance', [holder, blockTag]))
    : parseUint256Word(await call('eth_call', [{ to: assertAddress(token, 'Token'), data: balanceOfCalldata(holder) }, blockTag]));
  return { amount, decimals, block: String(parseQuantity(blockTag)) };
}
