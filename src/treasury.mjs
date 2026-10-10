// A treasury spread over several chains, added into one figure.
//
// The rule the whole file exists for: a sum missing one of its terms is not a
// smaller total, it is an unknown one. Dropping an unreadable source and
// reporting what is left understates the holding while looking entirely
// healthy, which is the failure mode worth engineering against.
import { assertChainId, createEvmClient, readBalance as readEvmBalance } from './chains/evm.mjs';
import { createSolanaClient, readCluster, readNativeBalance, readTokenBalance } from './chains/solana.mjs';

export function formatUnits(amount, decimals) {
  const negative = amount < 0n;
  const digits = (negative ? -amount : amount).toString().padStart(decimals + 1, '0');
  const whole = digits.slice(0, digits.length - decimals);
  const fraction = decimals === 0 ? '' : `.${digits.slice(digits.length - decimals).replace(/0+$/, '')}`;
  return `${negative ? '-' : ''}${whole}${fraction === '.' ? '' : fraction}`;
}

/**
 * Sources must agree on decimals before they can be added. Two assets with
 * different decimals are different units, and adding them produces a number
 * that means nothing while looking like a total.
 */
export function assertSummable(sources) {
  const decimals = new Set(sources.map(source => source.decimals ?? 18));
  if (decimals.size > 1) {
    throw new Error(`Sources disagree on decimals (${[...decimals].join(', ')}); they cannot be added into one figure.`);
  }
  return [...decimals][0] ?? 18;
}

async function readOne(source, { fetchImpl }) {
  if (source.kind === 'evm') {
    const allowCall = params => {
      const target = params?.[0]?.to;
      return typeof target === 'string' && source.token !== null
        && target.toLowerCase() === String(source.token).toLowerCase();
    };
    const call = createEvmClient({ rpcUrl: source.rpcUrl, fetchImpl, allowCall });
    await assertChainId(call, source.chainId);
    const { amount, block } = await readEvmBalance(call, {
      holder: source.holder, token: source.token ?? null, decimals: source.decimals ?? 18,
    });
    return { id: source.id, kind: 'evm', chainId: source.chainId, symbol: source.symbol,
      amount, decimals: source.decimals ?? 18, at: { block } };
  }
  if (source.kind === 'solana') {
    const call = createSolanaClient({ rpcUrl: source.rpcUrl, fetchImpl });
    const { cluster, genesisHash } = await readCluster(call);
    if (source.cluster && cluster !== source.cluster) {
      throw new Error(`Node is ${cluster}, not ${source.cluster}.`);
    }
    const reading = source.mint
      ? await readTokenBalance(call, source.holder, source.mint)
      : await readNativeBalance(call, source.holder);
    return { id: source.id, kind: 'solana', cluster, genesisHash, symbol: source.symbol,
      amount: reading.amount, decimals: reading.decimals, at: { slot: reading.slot } };
  }
  throw new Error(`Unknown source kind: ${source.kind}`);
}

/**
 * Every source is read, and the total is published only if every one of them
 * answered. A failure names which source failed and leaves the total null —
 * never a partial sum.
 */
export async function readTreasury(sources, { fetchImpl = fetch, now = Date.now } = {}) {
  if (!Array.isArray(sources) || sources.length === 0) throw new Error('At least one source is required.');
  const settled = await Promise.allSettled(sources.map(source => readOne(source, { fetchImpl })));
  const parts = [];
  const failures = [];
  settled.forEach((result, index) => {
    if (result.status === 'fulfilled') parts.push(result.value);
    else failures.push({ id: sources[index].id ?? String(index), reason: result.reason?.message ?? 'unreadable' });
  });
  const readAt = new Date(now()).toISOString();
  if (failures.length > 0) {
    return {
      readAt, complete: false, total: null, totalFormatted: null, decimals: null,
      parts: parts.map(part => ({ ...part, amount: part.amount.toString(), formatted: formatUnits(part.amount, part.decimals) })),
      failures,
      note: 'One or more sources could not be read, so the total is unknown rather than smaller. No partial sum is reported.',
    };
  }
  const reported = parts.map(part => ({
    ...part, amount: part.amount.toString(), formatted: formatUnits(part.amount, part.decimals),
  }));
  // Assets with different decimals are different units. There is no total to
  // report — but every source was read, and throwing those readings away to
  // signal one missing number helps nobody. The parts stand, the total does
  // not, and the reason says which it is.
  let decimals;
  try {
    decimals = assertSummable(parts);
  } catch (error) {
    return {
      readAt, complete: true, summable: false, total: null, totalFormatted: null, decimals: null,
      parts: reported, failures: [], note: error.message,
    };
  }
  const total = parts.reduce((sum, part) => sum + part.amount, 0n);
  return {
    readAt, complete: true, summable: true,
    total: total.toString(), totalFormatted: formatUnits(total, decimals), decimals,
    parts: reported, failures: [],
  };
}
