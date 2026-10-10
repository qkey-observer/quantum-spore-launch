import test from 'node:test';
import assert from 'node:assert/strict';
import { ed25519 } from '@noble/curves/ed25519.js';
import { base58Encode } from '../src/derive/index.mjs';
import { mintKeypairFromBitstring } from '../src/derive/pump.mjs';
import { buildCreateV2, buildLaunchTransaction, CREATE_V2_DISCRIMINATOR } from '../src/launch/pump-create.mjs';
import { compileMessage, encodeString, encodeU64 } from '../src/launch/solana-tx.mjs';
import { assertSigned } from '../src/launch/broadcast.mjs';

const hex = bytes => [...bytes].map(b => b.toString(16).padStart(2, '0')).join('');
const addr = fill => base58Encode(new Uint8Array(32).fill(fill));

// A real pump.fun launch, captured whole. `npm run verify:pump` re-checks the
// builder against whatever the chain is doing today; this pins one launch so
// the check still runs with no network and never drifts.
const LAUNCH = {
  "signature": "5AZzWSKDSts4Jef8qNkexob7qhnCPfjUUTsCzQnugGxCPZaX3CmJHUh52i3CAZzM7srUWDZb5nzRZ3744PCa6vSn",
  "slot": 455154205,
  "mint": "896UhWBoT3wBmvL2mjNg7K1sE8rFoC5T6pgHrCRJw7M9",
  "user": "GFFXprJs71rieaFoD3VM9Vxyycjv4JcvGbcnohE1AJeN",
  "name": "Harold Puddington",
  "symbol": "HAROLD",
  "uri": "https://gold-cheerful-marten-173.mypinata.cloud/ipfs/QmVptzeFNdgzA7v63xfsxCfx5LxaMT5EHhDKTR9Rg4Quqv",
  "creator": "Dsytm7MSipmgHEEhiHb7T8iERUhwHK28H9HR9xMAJAU7",
  "isMayhemMode": false,
  "isCashbackEnabled": false,
  "creatorFeeBps": "0",
  "isHolderReward": false,
  "accounts": [
    "896UhWBoT3wBmvL2mjNg7K1sE8rFoC5T6pgHrCRJw7M9",
    "TSLvdd1pWpHVjahSpsvCXUbgwsL3JAcvokwaKt1eokM",
    "8VRV1Kf2NG6eFgwWEeGwTJbSW3s7PjRGTs5VTLrApPZy",
    "G8rG3JJ5hTsyRfbjcqrk2i95RdTL7VyPHk6KiX1JY1CD",
    "4wTV1YmiEkRvAtNtsSGPtUrqRYQMe5SKy2uB4Jjaxnjf",
    "GFFXprJs71rieaFoD3VM9Vxyycjv4JcvGbcnohE1AJeN",
    "11111111111111111111111111111111",
    "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb",
    "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL",
    "MAyhSmzXzV1pTf7LsNkrNwkWKTo4ougAJ1PPg47MD4e",
    "13ec7XdrjF3h3YcqBTFDSReRcUFwbCnJaAQspM4j6DDJ",
    "BwWK17cbHxwWBKZkUYvzxLcNQ1YVyaFezduWbtm2de6s",
    "GBW98L8DmXKwtDyQtGpYtBrgqXg6kSP3oUiyKEx2mjn2",
    "42Qr57DdzEy8KM7KDbqobvyGagxgmkmpdWsoYLeuVvQx",
    "Ce6TQqeHC9p8KetsN6JsjHK7UTZk7nasjjnr7XxXp9F1",
    "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P",
    "mGzw6zwvig3GitrCM6sGJXdRWeWz81X2vyzVH3Upump",
    "H4bBf5HTUeqfGAPchhmDQcy6CCftraubY2aBwh9PcQNf",
    "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb",
    "6z6GDdfb2AjR9ZhJmAUQ5cipJCVxQvLJhB2H8mCwTFBP",
    "594cV4ieWZoZ8okejdEYDwRa1trEDNBPJSSrfCWzWtDP",
    "591v7K7B9P4o6e4viL3YGzmZywogpbE3andVvvJi983z",
    "DxLGoe97cPAiUwm7cGc8JEk4Qj4cHKcCVJvJGMNjuCf8",
    "4dwzUro9NwP3AXX5RCiKwzJXizsppuQokmfgRidFhXrm"
  ],
  "dataHex": "d6904cec5f8b31b4110000004861726f6c642050756464696e67746f6e060000004841524f4c446300000068747470733a2f2f676f6c642d636865657266756c2d6d617274656e2d3137332e6d7970696e6174612e636c6f75642f697066732f516d5670747a65464e64677a413776363378667378436678354c78614d5435454868444b54523952673451757176bf5b9cae795c46cf7cf4e5509e919bc251ca439704820f36a8b379a1691cd2e00000000000000000000000"
};

test('a real launch is reproduced byte for byte, accounts and data', () => {
  const built = buildCreateV2({
    mint: LAUNCH.mint, user: LAUNCH.user, name: LAUNCH.name, symbol: LAUNCH.symbol,
    uri: LAUNCH.uri, creator: LAUNCH.creator,
    isMayhemMode: LAUNCH.isMayhemMode, isCashbackEnabled: LAUNCH.isCashbackEnabled,
    creatorFeeBps: LAUNCH.creatorFeeBps, isHolderReward: LAUNCH.isHolderReward,
  });
  assert.equal(hex(built.data), LAUNCH.dataHex);
  // Anchor ignores accounts past the ones an instruction declares, and this
  // launch — a bot that bundled a swap into the same transaction — appended
  // eight. The sixteen that the program reads are what has to match.
  assert.equal(LAUNCH.accounts.length, 24, 'this fixture is deliberately one with trailing extras');
  assert.deepEqual(built.keys.map(k => k.pubkey), LAUNCH.accounts.slice(0, 16));
  // The creator is a separate argument from the payer, and this launch used
  // two different ones — so a builder that conflated them would fail here.
  assert.notEqual(LAUNCH.creator, LAUNCH.user);
});

test('the discriminator is create_v2, not the one Anchor would generate for "create"', () => {
  // sha256("global:create")[0..8] is 181ec828051c0777 and belongs to a
  // different, 14-account instruction that live launches no longer use.
  assert.equal(hex(CREATE_V2_DISCRIMINATOR), 'd6904cec5f8b31b4');
  assert.notEqual(hex(CREATE_V2_DISCRIMINATOR), '181ec828051c0777');
});

test('every account is derived, so a mint that does not exist yet can be prepared', () => {
  const built = buildCreateV2({ mint: LAUNCH.mint, user: addr(9), name: 'n', symbol: 's', uri: 'https://x/y' });
  assert.equal(built.keys.length, 16);
  assert.deepEqual(built.accountNames.slice(0, 6), ['mint', 'mint_authority', 'bonding_curve', 'associated_bonding_curve', 'global', 'user']);
  // Only the mint and the user sign; everything else is derived or constant.
  assert.deepEqual(built.keys.filter(k => k.isSigner).map((k, i) => built.accountNames[built.keys.indexOf(k)]), ['mint', 'user']);
});

test('metadata that pump.fun would reject is refused before a transaction is built', () => {
  const base = { mint: LAUNCH.mint, user: addr(9), name: 'n', symbol: 's', uri: 'https://x/y' };
  assert.throws(() => buildCreateV2({ ...base, name: 'x'.repeat(33) }), /name is longer than 32/);
  assert.throws(() => buildCreateV2({ ...base, symbol: 'x'.repeat(11) }), /symbol is longer than 10/);
  assert.throws(() => buildCreateV2({ ...base, uri: 'x'.repeat(201) }), /uri is longer than 200/);
  assert.throws(() => buildCreateV2({ ...base, uri: 'ipfs://x' }), /http/);
  assert.throws(() => buildCreateV2({ ...base, name: '' }), /needs a name/);
});

test('borsh encoding: a string is its byte length then its bytes, a u64 is little endian', () => {
  assert.equal(hex(encodeString('ab')), '02000000' + '6162');
  assert.equal(hex(encodeString('é')), '02000000' + 'c3a9', 'the length counts bytes, not characters');
  assert.equal(hex(encodeU64(1)), '0100000000000000');
  assert.equal(hex(encodeU64(255)), 'ff00000000000000');
});

test('message accounts are ordered the way the format requires, fee payer first', () => {
  const message = compileMessage({
    payer: addr(1), recentBlockhash: addr(0),
    instructions: [{
      programId: addr(5),
      data: Uint8Array.of(1),
      keys: [
        { pubkey: addr(2), isSigner: false, isWritable: false },
        { pubkey: addr(3), isSigner: false, isWritable: true },
        { pubkey: addr(4), isSigner: true, isWritable: false },
      ],
    }],
  });
  assert.deepEqual(message.accounts.map(a => a.address), [addr(1), addr(4), addr(3), addr(2), addr(5)]);
  assert.equal(message.header.numRequiredSignatures, 2);
  assert.equal(message.header.numReadonlySignedAccounts, 1);
  assert.equal(message.header.numReadonlyUnsignedAccounts, 2, 'the program id counts as a readonly account');
});

test('an account used twice keeps the stronger flags', () => {
  const message = compileMessage({
    payer: addr(1), recentBlockhash: addr(0),
    instructions: [
      { programId: addr(5), data: Uint8Array.of(1), keys: [{ pubkey: addr(2), isSigner: false, isWritable: false }] },
      { programId: addr(5), data: Uint8Array.of(2), keys: [{ pubkey: addr(2), isSigner: false, isWritable: true }] },
    ],
  });
  const seen = message.accounts.filter(a => a.address === addr(2));
  assert.equal(seen.length, 1, 'listed once');
  assert.equal(seen[0].isWritable, true, 'writable in one instruction is writable in the message');
});

test('what prepare produces is unsigned, and says which signatures are missing', () => {
  const tx = buildLaunchTransaction({
    mint: LAUNCH.mint, user: LAUNCH.user, name: 'n', symbol: 's', uri: 'https://x/y', recentBlockhash: addr(0),
  });
  assert.equal(tx.signaturesPresent, 0);
  assert.deepEqual(tx.signatureSlots, [LAUNCH.user, LAUNCH.mint], 'fee payer first, then the mint');
  const raw = Buffer.from(tx.transactionBase64, 'base64');
  assert.equal(raw[0], 2);
  assert.ok(raw.subarray(1, 129).every(b => b === 0), 'both signature slots are blank');
  assert.throws(() => assertSigned(tx.transactionBase64), /Signature 1 of 2 is still blank/);
  assert.match(tx.warning, /anyone who has the bitstring/);
});

test('a transaction with no blockhash is refused rather than built and later rejected', () => {
  assert.throws(() => buildLaunchTransaction({ mint: LAUNCH.mint, user: LAUNCH.user, name: 'n', symbol: 's', uri: 'https://x/y' }), /recent blockhash/);
});

test('signing fills the slots with signatures that verify over the message', () => {
  const bits = '1001001000010000000100000000000000000000000000000000000000000000';
  const mintKey = mintKeypairFromBitstring(bits);
  const payerSecret = new Uint8Array(32).fill(3);
  const payer = base58Encode(ed25519.getPublicKey(payerSecret));
  const tx = buildLaunchTransaction({ mint: mintKey.address, user: payer, name: 'n', symbol: 's', uri: 'https://x/y', recentBlockhash: addr(0) });

  const raw = Buffer.from(tx.transactionBase64, 'base64');
  const message = raw.subarray(1 + 64 * 2);
  const secrets = { [payer]: payerSecret, [mintKey.address]: mintKey.secret };
  tx.signatureSlots.forEach((signer, i) => raw.set(ed25519.sign(message, secrets[signer]), 1 + i * 64));

  assert.equal(assertSigned(raw.toString('base64')), 2);
  tx.signatureSlots.forEach((signer, i) => {
    const signature = raw.subarray(1 + i * 64, 65 + i * 64);
    assert.ok(ed25519.verify(signature, message, ed25519.getPublicKey(secrets[signer])), `signature ${i} verifies`);
  });
});

test('assertSigned accepts a filled slot and rejects an empty transaction', () => {
  assert.throws(() => assertSigned(Buffer.from(Uint8Array.of(0)).toString('base64')), /no signature slots/);
  const one = Buffer.concat([Buffer.from([1]), Buffer.alloc(64, 7), Buffer.alloc(10, 1)]);
  assert.equal(assertSigned(one.toString('base64')), 1);
});

// The CLI is where a mistyped argument actually shows up, so its refusals are
// worth pinning: each one must be a single readable line, must not reach the
// network, and must exit non-zero.
test('the CLI refuses bad arguments with one readable line and no network call', async () => {
  const { spawnSync } = await import('node:child_process');
  const { fileURLToPath } = await import('node:url');
  const run = args => {
    const result = spawnSync(process.execPath, ['bin/launch.mjs', ...args], {
      // fileURLToPath, not url.pathname: this repository's own path has
      // non-ASCII characters, which pathname hands back percent-encoded.
      cwd: fileURLToPath(new URL('..', import.meta.url)),
      // No network for any of these. A validation failure that still fetched a
      // blockhash would pass this test while wasting a round trip, so point the
      // RPC at a closed port: reaching it at all turns into a visible failure.
      env: { ...process.env, SOLANA_RPC_URL: 'http://127.0.0.1:1' },
      encoding: 'utf8',
    });
    return { status: result.status, output: `${result.stdout}${result.stderr}` };
  };
  const good = ['--bitstring', '1001', '--payer', addr(9), '--name', 'n', '--symbol', 's', '--uri', 'https://x/y'];

  for (const [args, expected] of [
    [['prepare', ...good.with(3, '\u4f60\u7684\u94b1\u5305\u5730\u5740')], /--payer is not a Solana address/],
    [['prepare', ...good.with(1, '<01\u2026>')], /must be 0s and 1s only/],
    [['prepare', '--bitstring', '1001', '--payer', '--name'], /--payer looks like the next flag/],
    [['send', '--in', 'does-not-exist.json'], /No such file/],
    [['nonsense'], /usage:/],
  ]) {
    const { status, output } = run(args);
    assert.equal(status, 1, `${args.join(' ')} should exit 1, got ${status}: ${output}`);
    assert.match(output, expected);
    assert.ok(!/\n\s+at /.test(output), `no stack trace in: ${output}`);
    assert.ok(!/ECONNREFUSED|127\.0\.0\.1:1/.test(output), `must not have reached the network: ${output}`);
  }
});
