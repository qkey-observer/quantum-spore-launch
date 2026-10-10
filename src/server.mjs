// A read-only HTTP service over the derivation and treasury layers.
//
// GET only, a fixed set of routes, no query parameters, and an allowlist of
// hosts. There is no write path anywhere in this process — not disabled, not
// guarded by a flag: absent.
import { createServer } from 'node:http';
import { readFileSync } from 'node:fs';
import { deriveCreate2, deriveSolana } from './derive/index.mjs';
import { readTreasury } from './treasury.mjs';

export function loadConfig(path) {
  const config = JSON.parse(readFileSync(path, 'utf8'));
  if (!Array.isArray(config.sources)) throw new Error('Configuration needs a sources array.');
  for (const source of config.sources) {
    if (!['evm', 'solana'].includes(source.kind)) throw new Error(`Unknown source kind: ${source.kind}`);
    if (typeof source.rpcUrl !== 'string') throw new Error(`Source ${source.id} has no rpcUrl.`);
    if (/privatekey|mnemonic|secret|seedphrase/i.test(JSON.stringify(source))) {
      throw new Error('A source carries something that looks like a secret. This service never holds keys.');
    }
  }
  return config;
}

export function createApi(config, { fetchImpl = fetch, now = Date.now, ttlMs = 60_000 } = {}) {
  let cache = null;
  async function treasury() {
    if (cache && now() - cache.at < ttlMs) return cache.value;
    const value = await readTreasury(config.sources, { fetchImpl, now });
    cache = { at: now(), value };
    return value;
  }
  return {
    async handle(pathname) {
      if (pathname === '/health') return { status: 200, body: { status: 'ok', service: 'quantum-spore-service', readOnly: true } };
      if (pathname === '/treasury') return { status: 200, body: await treasury() };
      if (pathname === '/derivations') {
        const bitstring = config.exampleBitstring ?? null;
        if (!bitstring) return { status: 200, body: { bitstring: null, note: 'No measured shot is configured, so no address is derived.', derivations: [] } };
        const derivations = [];
        for (const target of config.derivationTargets ?? []) {
          derivations.push(target.kind === 'solana'
            ? deriveSolana(bitstring, target.programId)
            : deriveCreate2({ bitstring, deployer: target.deployer, initCodeHash: target.initCodeHash }));
        }
        return { status: 200, body: { bitstring, derivations } };
      }
      return { status: 404, body: { error: 'Endpoint not found.' } };
    },
  };
}

export function createHttpServer(api, { allowedHosts = null } = {}) {
  return createServer(async (request, response) => {
    const send = (status, body) => {
      response.writeHead(status, {
        'content-type': 'application/json; charset=utf-8',
        'cache-control': status === 200 ? 'public, max-age=0, s-maxage=60, stale-while-revalidate=120' : 'no-store',
        'x-content-type-options': 'nosniff',
        ...(status === 405 ? { allow: 'GET, HEAD' } : {}),
      });
      response.end(request.method === 'HEAD' ? undefined : JSON.stringify(body));
    };
    try {
      const host = (request.headers.host || '').toLowerCase();
      const permitted = allowedHosts ?? [`127.0.0.1:${request.socket.localPort}`, `localhost:${request.socket.localPort}`];
      if (!permitted.includes(host)) return send(403, { error: 'Request origin is not allowed.' });
      if (!['GET', 'HEAD'].includes(request.method)) { request.resume(); return send(405, { error: 'This service is read-only.' }); }
      const url = new URL(request.url, 'http://localhost');
      if (url.search) return send(400, { error: 'This service does not accept query parameters.' });
      const result = await api.handle(url.pathname);
      return send(result.status, result.body);
    } catch {
      return send(500, { error: 'Data is temporarily unavailable.' });
    }
  });
}
