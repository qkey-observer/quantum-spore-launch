// The only file in this repository that can change anything on a chain.
// Everything else reads or computes. Keeping the write path in one short file
// is what makes "this does not send" a claim you can check rather than trust.
const DEFAULT_RPC = 'https://api.mainnet-beta.solana.com';

async function call(rpc, method, params) {
  const res = await fetch(rpc, {
    method: 'POST', headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ jsonrpc: '2.0', id: 1, method, params }),
    signal: AbortSignal.timeout(20_000),
  });
  if (!res.ok) throw new Error(`${new URL(rpc).host} answered ${res.status} to ${method}`);
  const body = await res.json();
  if (body.error) throw new Error(`${method}: ${body.error.message}`);
  return body.result;
}

export const latestBlockhash = async (rpc = DEFAULT_RPC) =>
  (await call(rpc, 'getLatestBlockhash', [{ commitment: 'finalized' }])).value;

/**
 * Ask the cluster what the transaction would do. Read-only: nothing is
 * submitted, no account changes, and an unsigned transaction is fine because
 * signature checking is switched off.
 */
export async function simulate(transactionBase64, { rpc = DEFAULT_RPC, signed = false } = {}) {
  const { value } = await call(rpc, 'simulateTransaction', [transactionBase64, {
    encoding: 'base64', sigVerify: signed, replaceRecentBlockhash: !signed, commitment: 'processed',
  }]);
  return { ok: value.err === null, err: value.err, logs: value.logs ?? [], unitsConsumed: value.unitsConsumed };
}

/**
 * Throw unless every signature slot is filled. Checked locally and before
 * anything touches the network, so an unsigned transaction is refused for the
 * reason it is actually wrong rather than by whatever the cluster says first.
 */
export function assertSigned(transactionBase64) {
  const raw = Buffer.from(transactionBase64, 'base64');
  const signatureCount = raw[0];
  if (!signatureCount) throw new Error('This transaction carries no signature slots at all.');
  for (let i = 0; i < signatureCount; i++) {
    if (raw.subarray(1 + i * 64, 65 + i * 64).every(byte => byte === 0)) {
      throw new Error(`Signature ${i + 1} of ${signatureCount} is still blank — this transaction is not signed.`);
    }
  }
  return signatureCount;
}

/**
 * Submit a transaction that is already signed. There is no key here and no
 * signing step: whatever arrives is sent as it is, or refused.
 */
export async function send(transactionBase64, { rpc = DEFAULT_RPC, skipPreflight = false } = {}) {
  assertSigned(transactionBase64);
  const signature = await call(rpc, 'sendTransaction', [transactionBase64, {
    encoding: 'base64', skipPreflight, preflightCommitment: 'processed', maxRetries: 3,
  }]);
  return { signature, explorer: `https://solscan.io/tx/${signature}` };
}

export { DEFAULT_RPC };
