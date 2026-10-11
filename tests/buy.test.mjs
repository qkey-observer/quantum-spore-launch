import test from 'node:test';
import assert from 'node:assert/strict';
import { buildBuyV2, buyV2Accounts, BUY_V2_DISCRIMINATOR, createIdempotentAta, defaultRecipients, devBuyInstructions, LEGACY_TOKEN_PROGRAM, quoteTokensForLamports, WSOL_MINT } from '../src/launch/pump-buy.mjs';
import { compileV0Message, parseLookupTable } from '../src/launch/solana-tx.mjs';
import { base58Encode } from '../src/derive/index.mjs';

const hex = bytes => [...bytes].map(b => b.toString(16).padStart(2, '0')).join('');

// Two real launches, with the fee recipients they chose from the pools. The
// other 25 accounts are derived, so matching these lists is what shows the
// derivations are right. `npm run verify:pump` re-checks against the chain;
// this pins them so the check still runs offline.
const LAUNCHES = [
  {
    mint: 'HwT68ZHTDkkvq8nouCkwvmYvn1g6v8uhPCf6B5gMpump',
    user: 'FD49Ex92TjwsmNgeyP1Sw4BifDkDz9FsDdusBvCbb5vg',
    feeRecipient: '9rPYyANsfQZw3DnDmKE3YCQF5E8oD89UXoHn9JFEhJUz',
    buybackFeeRecipient: '3BpXnfJaUTiwXnJNe7Ej1rcbzqTTQUvLShZaWazebsVR',
    accounts: ['4wTV1YmiEkRvAtNtsSGPtUrqRYQMe5SKy2uB4Jjaxnjf', 'HwT68ZHTDkkvq8nouCkwvmYvn1g6v8uhPCf6B5gMpump', WSOL_MINT, 'TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb', LEGACY_TOKEN_PROGRAM, 'ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL', '9rPYyANsfQZw3DnDmKE3YCQF5E8oD89UXoHn9JFEhJUz', 'Bvtgim23rfocUzxVX9j9QFxTbBnH8JZxnaGLCEkXvjKS', '3BpXnfJaUTiwXnJNe7Ej1rcbzqTTQUvLShZaWazebsVR', '6rVkF4HSgy1jrnC3HogfRgPHrq4CtLg5f11URpsC4i9D', '23JoPgHKSoJbJuNj8tKmRBmQRQDc5ti9Kvm1NUkrrbkv', 'Co8CwBjovtauu431DN7nLR3SvzqBPjSYokQUwHyXvb97', 'DddLLTRZMJanVjnGCp7JjBG1fCqo3AZYFMa5eAGQmvGA', 'FD49Ex92TjwsmNgeyP1Sw4BifDkDz9FsDdusBvCbb5vg', '6q9FJKnmzaHHGdrgqaPPKM5waJsHacEXH6NN53JZki1e', '8bGXUqEhsWm9SCraW92UYpfvBfyxtr5iZXd7yGq56ds6', '35EnEq23LDcS7RMmfePSDYCCJbycsqB3zEJwCH1BxkWM', 'EYBPdMFo5n7QphBfi9xuv7AZNSDCiqWemCypMtGK1EAP', 'FqGvrEAyDSmXGNZkNwkHuo31L33dGtZ8q4ZCqxw9byLK', 'Hq2wp8uJ9jCPsYgNHex8RtqdvMPfVGoYwjvF1ATiwn2Y', 'BT5aGWv78DjApSgbXBo5KJC4XHZM5bkMQjuvGsn3N85e', '3a4jR2RSYbVA3zijrRrD15WzGBTi42kgNEyX3rKPagaK', '8Wf5TiAheLUqBrKXeYg2JtAFFMWtKdG2BSFgqUcPVwTt', 'pfeeUxB6jkeY1Hxd7CsFCAjcbHA9rWtchMGdZ6VojVZ', '11111111111111111111111111111111', 'Ce6TQqeHC9p8KetsN6JsjHK7UTZk7nasjjnr7XxXp9F1', '6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P'],
  },
  {
    mint: 'B4hnwQSJvbhrhTYmsuvzjEWQFL3ddq47tGErygtcpump',
    user: 'Dvgpggrak5tRXWse22TdYtaZ4Rs2cHoBRUXcNB9vQLcb',
    feeRecipient: '7hTckgnGnLQR6sdH7YkqFTAA7VwTfYFaZ6EhEsU3saCX',
    buybackFeeRecipient: 'A7hAgCzFw14fejgCp387JUJRMNyz4j89JKnhtKU8piqW',
    accounts: ['4wTV1YmiEkRvAtNtsSGPtUrqRYQMe5SKy2uB4Jjaxnjf', 'B4hnwQSJvbhrhTYmsuvzjEWQFL3ddq47tGErygtcpump', WSOL_MINT, 'TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb', LEGACY_TOKEN_PROGRAM, 'ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL', '7hTckgnGnLQR6sdH7YkqFTAA7VwTfYFaZ6EhEsU3saCX', 'X5QPJcpph4mBAJDzc4hRziFftSbcygV59kRb2Fu6Je1', 'A7hAgCzFw14fejgCp387JUJRMNyz4j89JKnhtKU8piqW', 'qkYdTGRPHbWTWuBMz45bCiU6a23axRqf6sBHm9295WY', '9AT9PvPPQg7P9DRGY9bNdvEEeZVaDN3CDPurNzDFo9r2', 'FZFyu4ts6gdCjq4UsGqTxqQcozWCkNq2EJma7FZZhBtp', 'BGGMXSXnJvTp9YufDshyaoC22ZDwVySLuV29aMZpLCX4', 'Dvgpggrak5tRXWse22TdYtaZ4Rs2cHoBRUXcNB9vQLcb', 'D271cku3fyt8LRQ45jFcsJHBpTgNUDtmcUreQS9boCc3', 'HXkAde5cpAibazxZKSa18kL4ATmAmCo7CErGShmpwiMS', '8ETT8m6CD9g6jEHGffkU4yALzY8S72KsdLpNCUDjce2U', '2FFaLAy2ZaqbS2szoUcHLM3oVrJfMKjaoCRBFB9XXPQE', '2Fywgz8MEkRq58d4WqYtThEr1tYPK9YFgYmG6Rfr63DR', 'Hq2wp8uJ9jCPsYgNHex8RtqdvMPfVGoYwjvF1ATiwn2Y', 'H2HpunmeSVzu38Mx3WEk7eFKAui1o3JZJwQ9cBaTK6Gv', 'CnYmDNPn4tUqEfbWL7Wh1EJYa9oQfaMH4r53P7dErZN1', '8Wf5TiAheLUqBrKXeYg2JtAFFMWtKdG2BSFgqUcPVwTt', 'pfeeUxB6jkeY1Hxd7CsFCAjcbHA9rWtchMGdZ6VojVZ', '11111111111111111111111111111111', 'Ce6TQqeHC9p8KetsN6JsjHK7UTZk7nasjjnr7XxXp9F1', '6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P'],
  },
];

// The launchpad parameters as the Global account held them when this was built.
const GLOBAL = {
  feeRecipient: '62qc2CNXwrYqQScmEdiZFFAnJR262PxWEuNQtxfafNgV',
  feeRecipients: LAUNCHES.map(l => l.feeRecipient),
  buybackFeeRecipients: LAUNCHES.map(l => l.buybackFeeRecipient),
  initialVirtualTokenReserves: 1073000000000000n,
  initialVirtualSolReserves: 30000000000n,
  initialRealTokenReserves: 793100000000000n,
  feeBasisPoints: 95n,
  creatorFeeBasisPoints: 5n,
};

test('all 27 buy_v2 accounts are reproduced for two real launches', () => {
  for (const launch of LAUNCHES) {
    const derived = buyV2Accounts({ ...launch, creator: launch.user }).map(a => a.pubkey);
    assert.equal(derived.length, 27);
    assert.deepEqual(derived, launch.accounts, `accounts for ${launch.mint}`);
  }
});

test('the two accounts the IDL cannot derive are the ones read from Global', () => {
  // Everything else follows from the mint and the user. These two are chosen
  // from pools, which is why the builder reads state at all.
  const [launch] = LAUNCHES;
  const names = buyV2Accounts({ ...launch, creator: launch.user }).map((a, i) => [i, a.name]);
  assert.deepEqual(names.filter(([i]) => [6, 8].includes(i)), [[6, 'fee_recipient'], [8, 'buyback_fee_recipient']]);
});

test('a recipient the launchpad does not know is refused before the launch, not during it', () => {
  const [launch] = LAUNCHES;
  const base = { ...launch, creator: launch.user, amount: 1n, maxSolCost: 1n, global: GLOBAL };
  assert.doesNotThrow(() => buildBuyV2(base));
  assert.throws(() => buildBuyV2({ ...base, feeRecipient: base58Encode(new Uint8Array(32).fill(9)) }), /not one of the launchpad's fee recipients/);
  assert.throws(() => buildBuyV2({ ...base, buybackFeeRecipient: base58Encode(new Uint8Array(32).fill(9)) }), /not one of the launchpad's buyback fee recipients/);
  // Without Global there is nothing to check against, and the builder says so
  // by simply not claiming to have checked.
  assert.doesNotThrow(() => buildBuyV2({ ...base, global: null, feeRecipient: base58Encode(new Uint8Array(32).fill(9)) }));
});

test('the discriminator and the two u64 arguments are what the chain carries', () => {
  // The values are the ones a real launch sent: 34,199,203,154,141 token units
  // against a 1.01 SOL cap. Fed back in, the encoding has to come out as the
  // bytes that transaction carried.
  const [launch] = LAUNCHES;
  const built = buildBuyV2({ ...launch, creator: launch.user, amount: 34199203154141n, maxSolCost: 1010000000n, global: GLOBAL });
  assert.equal(hex(BUY_V2_DISCRIMINATOR), 'b817ee6167c5d33d');
  assert.equal(hex(built.data), 'b817ee6167c5d33d' + 'dd085b9f1a1f0000' + '8060333c00000000',
    'byte for byte the data a real launch sent');
});

test('the quote is an under-estimate, not a reproduction of anyone else\'s client', () => {
  // A real launch asked for 34,199,203,154,141 units with a 1.01 SOL cap. The
  // curve alone, fee-adjusted, prices a 1 SOL budget about 0.23% above that —
  // their client started from a different input, and there is no way to
  // recover which. That is fine and worth stating rather than papering over:
  // this quote only has to stay under the cap it sets, and the margin it holds
  // back is four times that gap.
  const quote = quoteTokensForLamports(1_000_000_000n, GLOBAL);
  const theirs = 34199203154141n;
  assert.ok(quote.beforeMargin > theirs, 'the raw curve price sits above what they asked for');
  const gap = Number((quote.beforeMargin - theirs) * 1_000_000n / theirs) / 10_000;
  assert.ok(gap < 0.5, `the gap is small and unexplained, ${gap}%`);
  assert.ok(quote.amount < quote.beforeMargin, 'and the margin is held back regardless');
});

test('the quote asks for less than the budget affords, and never more', () => {
  const quote = quoteTokensForLamports(1_000_000_000n, GLOBAL);
  assert.equal(quote.maxSolCost, 1_000_000_000n, 'the cap is exactly the budget');
  assert.equal(quote.feeBasisPoints, 100n, '0.95% platform plus 0.05% creator');
  assert.equal(quote.intoCurve, 990_000_000n, 'fees come off before the curve');
  assert.ok(quote.amount < quote.beforeMargin, 'a margin is held back');
  // The margin is what stops a launch reverting on slippage. 1% of the tokens
  // is a cheap price for that; a reverted launch cannot be retried at the same
  // moment, and the cap means the shortfall can never become an overspend.
  const held = Number((quote.beforeMargin - quote.amount) * 10_000n / quote.beforeMargin) / 100;
  assert.ok(held > 0.9 && held < 1.1, `about 1% held back, got ${held}%`);
  assert.throws(() => quoteTokensForLamports(0n, GLOBAL), /positive lamport budget/);
});

test('a bigger budget buys more, and the curve never sells more than it holds', () => {
  const small = quoteTokensForLamports(1_000_000n, GLOBAL);
  const large = quoteTokensForLamports(10_000_000_000n, GLOBAL);
  assert.ok(large.amount > small.amount);
  const absurd = quoteTokensForLamports(10_000_000_000_000n, GLOBAL);
  assert.ok(absurd.amount <= GLOBAL.initialRealTokenReserves, 'capped at the real reserves');
});

test('the buy is preceded by an idempotent account creation, because buy_v2 requires it', () => {
  const [launch] = LAUNCHES;
  const instructions = devBuyInstructions({ ...launch, creator: launch.user, amount: 1n, maxSolCost: 1n, global: GLOBAL });
  assert.equal(instructions.length, 2);
  const [ata, buy] = instructions;
  // Simulation says so in as many words: without this, buy_v2 fails with
  // "AnchorError caused by account: associated_base_user. AccountNotInitialized".
  assert.equal(hex(ata.data), '01', 'CreateIdempotent');
  assert.deepEqual(ata.accountNames, ['payer', 'associated_token_account', 'owner', 'mint', 'system_program', 'token_program']);
  assert.equal(ata.keys[1].pubkey, buy.keys[14].pubkey, 'it creates exactly the account the buy reads');
  assert.equal(ata.keys[0].isSigner, true);
});

test('a version 0 message moves what it can into the lookup table and keeps what it must', () => {
  const addr = fill => base58Encode(new Uint8Array(32).fill(fill));
  const payer = addr(1);
  const signerMint = addr(2);
  const inTable = addr(3);
  const notInTable = addr(4);
  const program = addr(5);
  const message = compileV0Message({
    payer, recentBlockhash: addr(0),
    lookupTables: [{ address: addr(6), addresses: [inTable, program] }],
    instructions: [{
      programId: program, data: Uint8Array.of(7),
      keys: [
        { pubkey: signerMint, isSigner: true, isWritable: true },
        { pubkey: inTable, isSigner: false, isWritable: true },
        { pubkey: notInTable, isSigner: false, isWritable: false },
      ],
    }],
  });
  assert.equal(message.bytes[0], 0x80, 'the version prefix');
  // A signer cannot be looked up, and neither can the program a top-level
  // instruction invokes — even when the table happens to contain it.
  assert.deepEqual(message.accounts.map(a => a.address), [payer, signerMint, notInTable, program]);
  assert.deepEqual(message.loaded, { writable: [inTable], readonly: [] });
  assert.equal(message.staticCount, 4);
});

test('a lookup table parses to whole addresses, and a malformed one is refused', () => {
  const header = new Uint8Array(56);
  const one = new Uint8Array(32).fill(5);
  assert.deepEqual(parseLookupTable(Uint8Array.from([...header, ...one])), [base58Encode(one)]);
  assert.deepEqual(parseLookupTable(header), []);
  assert.throws(() => parseLookupTable(new Uint8Array(20)), /too short/);
  assert.throws(() => parseLookupTable(new Uint8Array(56 + 31)), /address boundary/);
});

test('defaultRecipients takes the first of each pool, which the pools vouch for', () => {
  const picked = defaultRecipients(GLOBAL);
  assert.ok(GLOBAL.feeRecipients.includes(picked.feeRecipient));
  assert.ok(GLOBAL.buybackFeeRecipients.includes(picked.buybackFeeRecipient));
  assert.doesNotThrow(() => buildBuyV2({ ...LAUNCHES[0], creator: LAUNCHES[0].user, amount: 1n, maxSolCost: 1n, global: GLOBAL, ...picked }));
});

test('an associated token account creation refuses a missing or malformed owner', () => {
  const [launch] = LAUNCHES;
  assert.throws(() => createIdempotentAta({ payer: launch.user, owner: '', mint: launch.mint }), /needs a owner/);
  assert.throws(() => createIdempotentAta({ payer: launch.user, owner: 'not base58!', mint: launch.mint }), /invalid character|32 bytes/);
});
