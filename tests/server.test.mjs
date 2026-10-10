import test from 'node:test';
import assert from 'node:assert/strict';
import { once } from 'node:events';
import { writeFileSync, unlinkSync } from 'node:fs';
import { createApi, createHttpServer, loadConfig } from '../src/server.mjs';

const config = { sources: [{ id: 'a', kind: 'evm', chainId: 56, rpcUrl: 'https://a.test', holder: `0x${'a'.repeat(40)}`, token: null, symbol: 'X', decimals: 18 }] };

test('configuration carrying anything key-shaped is refused', () => {
  const path = `/tmp/qs-${Date.now()}.json`;
  for (const bad of [{ privateKey: '0xabc' }, { mnemonic: 'a b c' }, { seedPhrase: 'x' }]) {
    writeFileSync(path, JSON.stringify({ sources: [{ id: 'a', kind: 'evm', rpcUrl: 'https://a.test', ...bad }] }));
    assert.throws(() => loadConfig(path), /never holds keys/);
  }
  unlinkSync(path);
});

test('the service exposes fixed read routes and nothing else', async () => {
  const api = createApi(config, { fetchImpl: async () => { throw new Error('offline'); } });
  const server = createHttpServer(api);
  server.listen(0, '127.0.0.1'); await once(server, 'listening');
  const base = `http://127.0.0.1:${server.address().port}`;
  try {
    assert.equal((await (await fetch(`${base}/health`)).json()).readOnly, true);
    assert.equal((await fetch(`${base}/nope`)).status, 404);
    // No write verb reaches anything, and a query string is refused outright
    // rather than parsed — the service takes no input from the caller.
    assert.equal((await fetch(`${base}/treasury`, { method: 'POST', body: '{}' })).status, 405);
    assert.equal((await fetch(`${base}/treasury?rpc=https://evil.test`)).status, 400);
    const bad = await fetch(`${base}/nope`);
    assert.equal(bad.headers.get('cache-control'), 'no-store', 'an error must not be cached');
  } finally { server.close(); }
});

test('a request from an unexpected host is refused', async () => {
  const api = createApi(config, { fetchImpl: async () => { throw new Error('offline'); } });
  const server = createHttpServer(api, { allowedHosts: ['qkey.example'] });
  server.listen(0, '127.0.0.1'); await once(server, 'listening');
  try {
    assert.equal((await fetch(`http://127.0.0.1:${server.address().port}/health`)).status, 403);
  } finally { server.close(); }
});

// The package's own start script used to load a module full of exports and
// exit, so `npm start` printed nothing and served nothing while appearing to
// work. This asserts the file actually starts a service when it is run.
test('running the entrypoint starts a service that answers', async () => {
  const { spawn } = await import('node:child_process');
  const { fileURLToPath } = await import('node:url');
  const { dirname, resolve } = await import('node:path');
  const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
  const port = 8900 + Math.floor(Math.random() * 90);

  const child = spawn(process.execPath, [resolve(root, 'src/server.mjs')], {
    env: { ...process.env, PORT: String(port), HOST: '127.0.0.1' },
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  try {
    // The banner arrives over several chunks, so it is accumulated rather than
    // matched against whichever one happened to carry the first line.
    let output = '';
    const started = await new Promise((resolveStart, rejectStart) => {
      const timer = setTimeout(() => rejectStart(new Error(`the entrypoint never reported a listening service. Output: ${output}`)), 8000);
      child.stdout.on('data', chunk => {
        output += String(chunk);
        if (output.includes('listening on') && output.includes('read-only')) { clearTimeout(timer); resolveStart(output); }
      });
      child.on('exit', code => { clearTimeout(timer); rejectStart(new Error(`entrypoint exited with ${code} instead of serving`)); });
    });
    assert.match(started, /read-only/, 'it says what it is on startup');
    assert.match(started, /routes/, 'and what it serves');

    const health = await fetch(`http://127.0.0.1:${port}/health`);
    assert.equal(health.status, 200);
    assert.equal((await health.json()).readOnly, true);
    assert.equal((await fetch(`http://127.0.0.1:${port}/nope`)).status, 404);
    // Read-only is not a claim the startup banner makes on its own.
    assert.equal((await fetch(`http://127.0.0.1:${port}/health`, { method: 'POST' })).status, 405);
  } finally {
    child.kill('SIGTERM');
  }
});
