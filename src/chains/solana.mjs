// Read-only Solana access.
//
// Solana's RPC is nothing like the EVM's: no chain id, no blocks to pin a read
// to, and a token balance lives in a separate account owned by the holder
// rather than in a mapping inside the mint. Both differences are handled here
// rather than leaking into the code that adds balances together.
//
// Nothing in this file can write. The method allowlist is the enforcement, not
// a convention — an RPC client that can be handed any method is an open proxy
// wearing a library's name.
const READ_METHODS = new Set([
  'getBalance',
  'getSlot',
  'getGenesisHash',
  'getTokenAccountsByOwner',
  'getTokenAccountBalance',
  'getAccountInfo',
]);

// Mainnet-beta identifies itself by the hash of its genesis block. It is the
// closest thing Solana has to a chain id, and checking it is what stops a URL
// repointed at devnet from being read as mainnet.
export const GENESIS_HASHES = Object.freeze({
  'mainnet-beta': '5eykt4UsFv8P8NJdTREpY1vzqKqZKvdpKuc147dw2N9d',
  devnet: 'EtWTRABZaYq6iMfeYKouRu166VU2xqa1wcaWoxPkrZBG',
  testnet: '4uhcVJyU9pJkvQyS88uRDiswHXSCkY3zQawwpjk2NsNY',
});

export const SPL_TOKEN_PROGRAM = 'TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA';
const BASE58 = /^[1-9A-HJ-NP-Za-km-z]{32,44}$/;

export function isSolanaAddress(value) {
  return typeof value === 'string' && BASE58.test(value);
}

function assertAddress(value, name) {
  if (!isSolanaAddress(value)) throw new Error(`${name} is not a Solana address.`);
  return value;
}

export function createSolanaClient({ rpcUrl, fetchImpl = fetch, timeoutMs = 8000 }) {
  if (typeof rpcUrl !== 'string') throw new Error('A Solana RPC URL is required.');
  const parsed = new URL(rpcUrl);
  if (parsed.protocol !== 'https:' && !(parsed.protocol === 'http:' && ['localhost', '127.0.0.1', '[::1]'].includes(parsed.hostname))) {
    throw new Error('A Solana RPC URL must be HTTPS, or a local node.');
  }
  let id = 0;
  return async function call(method, params = []) {
    if (!READ_METHODS.has(method)) throw new Error(`RPC method not allowed: ${method}`);
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const response = await fetchImpl(rpcUrl, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ jsonrpc: '2.0', id: ++id, method, params }),
        signal: controller.signal,
      });
      if (!response.ok) throw new Error(`Solana node returned HTTP ${response.status}.`);
      const body = await response.json();
      if (body.error) throw new Error(`Solana node refused ${method}.`);
      if (!('result' in body)) throw new Error(`Solana node returned no result for ${method}.`);
      return body.result;
    } finally {
      clearTimeout(timer);
    }
  };
}

/** The cluster, proven rather than assumed, so a repointed URL is caught. */
export async function readCluster(call) {
  const hash = await call('getGenesisHash');
  const named = Object.entries(GENESIS_HASHES).find(([, value]) => value === hash);
  return { genesisHash: hash, cluster: named ? named[0] : 'unknown' };
}

/** Native SOL, in lamports. A slot stands in for the block a read is pinned to. */
export async function readNativeBalance(call, owner) {
  assertAddress(owner, 'Owner');
  const [balance, slot] = await Promise.all([call('getBalance', [owner]), call('getSlot')]);
  const lamports = typeof balance === 'object' && balance !== null ? balance.value : balance;
  if (!Number.isSafeInteger(lamports) || lamports < 0) throw new Error('Solana node returned an invalid balance.');
  return { amount: BigInt(lamports), decimals: 9, slot: String(slot) };
}

/**
 * An SPL balance is the sum of the owner's token accounts for that mint, not a
 * single lookup. Most owners have exactly one, but nothing stops them having
 * several, and reading only the first would quietly understate the holding.
 */
export async function readTokenBalance(call, owner, mint, { maxAccounts = 64 } = {}) {
  assertAddress(owner, 'Owner');
  assertAddress(mint, 'Mint');
  const [accounts, slot] = await Promise.all([
    call('getTokenAccountsByOwner', [owner, { mint }, { encoding: 'jsonParsed' }]),
    call('getSlot'),
  ]);
  const list = accounts?.value;
  if (!Array.isArray(list)) throw new Error('Solana node returned an invalid token account list.');
  // Measured against mainnet: one owner can hold five figures of token accounts
  // for a single mint, and the response is megabytes. A treasury does not look
  // like that, so an address that does is refused rather than summed — the
  // caller is reading something other than what it thinks it is.
  if (list.length > maxAccounts) {
    throw new Error(`Owner holds ${list.length} token accounts for this mint, past the ${maxAccounts} a treasury read expects.`);
  }
  let total = 0n;
  let decimals = null;
  for (const entry of list) {
    const info = entry?.account?.data?.parsed?.info?.tokenAmount;
    if (!info || typeof info.amount !== 'string' || !Number.isInteger(info.decimals)) {
      throw new Error('Solana node returned an unreadable token amount.');
    }
    if (decimals !== null && decimals !== info.decimals) {
      throw new Error('Token accounts for one mint disagree on decimals.');
    }
    decimals = info.decimals;
    total += BigInt(info.amount);
  }
  // No token account is a real zero: the owner holds none of this mint. The
  // decimals still have to come from somewhere, so the mint itself is asked.
  if (decimals === null) decimals = await readMintDecimals(call, mint);
  return { amount: total, decimals, slot: String(slot), accounts: list.length };
}

export async function readMintDecimals(call, mint) {
  const info = await call('getAccountInfo', [assertAddress(mint, 'Mint'), { encoding: 'jsonParsed' }]);
  const decimals = info?.value?.data?.parsed?.info?.decimals;
  if (!Number.isInteger(decimals) || decimals < 0 || decimals > 36) {
    throw new Error('Mint account did not report usable decimals.');
  }
  return decimals;
}
