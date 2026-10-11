// Build pump.fun's `buy_v2` — the dev buy that real launches send in the same
// transaction as the create.
//
// This exists because a launch without it hands the first buy to whoever is
// watching the mempool: the creator ends up holding none of their own token.
// Every launch sampled on chain bundled one.
//
// Two of the 27 accounts cannot be derived. `fee_recipient` and
// `buyback_fee_recipient` are chosen from pools the program keeps in its Global
// account, and the IDL gives them no seeds — so this file reads Global rather
// than guessing, and the choice is checked against those pools before it is
// used. Every other account is derived, and all 27 were reproduced against two
// real launches (`npm run verify:pump`).
import { base58Decode } from '../derive/index.mjs';
import { addressOf, encodeU64, parseLookupTable, SYSTEM_PROGRAM } from './solana-tx.mjs';
import { bondingCurveFor, PUMP_PROGRAM_ID } from '../derive/pump.mjs';
import { associatedTokenAddress, PROGRAMS } from './pump-create.mjs';
import { findProgramAddress } from '../derive/index.mjs';

export const BUY_V2_DISCRIMINATOR = Uint8Array.of(0xb8, 0x17, 0xee, 0x61, 0x67, 0xc5, 0xd3, 0x3d);
export const FEE_PROGRAM = 'pfeeUxB6jkeY1Hxd7CsFCAjcbHA9rWtchMGdZ6VojVZ';
export const WSOL_MINT = 'So11111111111111111111111111111111111111112';
/** Wrapped SOL is a legacy SPL mint, so its token accounts belong to that program. */
export const LEGACY_TOKEN_PROGRAM = 'TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA';

const utf8 = value => new TextEncoder().encode(value);
const pda = (seeds, programId) => findProgramAddress(seeds, programId).address;
const quoteAccount = owner => associatedTokenAddress(owner, WSOL_MINT, LEGACY_TOKEN_PROGRAM);

// Byte offsets into the Global account, after Anchor's 8-byte discriminator.
// Taken from the IDL's own Global struct rather than counted by hand.
const GLOBAL = {
  feeRecipient: 41,
  initialVirtualTokenReserves: 73,
  initialVirtualSolReserves: 81,
  initialRealTokenReserves: 89,
  feeBasisPoints: 105,
  creatorFeeBasisPoints: 154,
  feeRecipients: 162,
  buybackFeeRecipients: 741,
};

/**
 * Read the launchpad's own parameters: the fee recipient pools, the curve's
 * starting reserves and the fee rates. Everything a buy needs that is state
 * rather than arithmetic, in one account read.
 */
export async function readGlobalState(call) {
  const address = pda([utf8('global')], PUMP_PROGRAM_ID);
  const info = await call('getAccountInfo', [address, { encoding: 'base64' }]);
  if (!info?.value) throw new Error('The pump global account could not be read.');
  if (info.value.owner !== PUMP_PROGRAM_ID) throw new Error('The global account is not owned by the pump program.');
  const raw = Buffer.from(info.value.data[0], 'base64');
  if (raw.length < 1087) throw new Error(`The global account is ${raw.length} bytes, which is shorter than its known layout.`);
  const { base58Encode } = await import('../derive/index.mjs');
  const key = offset => base58Encode(new Uint8Array(raw.subarray(offset, offset + 32)));
  const pool = (offset, count) => Array.from({ length: count }, (_, i) => key(offset + i * 32));
  return {
    address,
    feeRecipient: key(GLOBAL.feeRecipient),
    feeRecipients: pool(GLOBAL.feeRecipients, 7),
    buybackFeeRecipients: pool(GLOBAL.buybackFeeRecipients, 8),
    initialVirtualTokenReserves: raw.readBigUInt64LE(GLOBAL.initialVirtualTokenReserves),
    initialVirtualSolReserves: raw.readBigUInt64LE(GLOBAL.initialVirtualSolReserves),
    initialRealTokenReserves: raw.readBigUInt64LE(GLOBAL.initialRealTokenReserves),
    feeBasisPoints: raw.readBigUInt64LE(GLOBAL.feeBasisPoints),
    creatorFeeBasisPoints: raw.readBigUInt64LE(GLOBAL.creatorFeeBasisPoints),
  };
}

/**
 * How many tokens a lamport budget buys on a curve that has not traded yet.
 *
 * The answer is deliberately an under-estimate. `buy_v2` takes a token amount
 * and a spending cap, and the program prices the tokens itself: ask for more
 * than the cap covers and the whole transaction reverts. Asking for slightly
 * fewer tokens than the budget affords costs a fraction of a percent of supply
 * and removes that failure, which at a launch is the trade worth making —
 * a reverted launch is not retryable at the same moment, and the cap means the
 * shortfall can never become an overspend.
 */
export function quoteTokensForLamports(lamports, global, { marginBps = 100n } = {}) {
  const budget = BigInt(lamports);
  if (budget <= 0n) throw new Error('A dev buy needs a positive lamport budget.');
  const fees = global.feeBasisPoints + global.creatorFeeBasisPoints;
  const intoCurve = (budget * (10_000n - fees)) / 10_000n;
  const { initialVirtualSolReserves: vSol, initialVirtualTokenReserves: vTokens, initialRealTokenReserves: real } = global;
  // Constant product, rounded against the buyer: the reserve after the trade is
  // rounded up by one so the tokens out can never be rounded in our favour.
  const tokensOut = vTokens - (vSol * vTokens) / (vSol + intoCurve) - 1n;
  const capped = tokensOut < real ? tokensOut : real;
  const amount = (capped * (10_000n - marginBps)) / 10_000n;
  if (amount <= 0n) throw new Error('That budget is too small to buy any whole token unit.');
  return { amount, maxSolCost: budget, intoCurve, feeBasisPoints: fees, beforeMargin: capped };
}

/** The 27 accounts `buy_v2` reads or writes, in the order the program expects. */
export function buyV2Accounts({ mint, user, creator, feeRecipient, buybackFeeRecipient }) {
  const curve = bondingCurveFor(mint).address;
  const creatorVault = pda([utf8('creator-vault'), base58Decode(creator)], PUMP_PROGRAM_ID);
  const userVolume = pda([utf8('user_volume_accumulator'), base58Decode(user)], PUMP_PROGRAM_ID);
  return [
    { name: 'global', pubkey: pda([utf8('global')], PUMP_PROGRAM_ID), isSigner: false, isWritable: false },
    { name: 'base_mint', pubkey: mint, isSigner: false, isWritable: false },
    { name: 'quote_mint', pubkey: WSOL_MINT, isSigner: false, isWritable: false },
    { name: 'base_token_program', pubkey: PROGRAMS.token2022, isSigner: false, isWritable: false },
    { name: 'quote_token_program', pubkey: LEGACY_TOKEN_PROGRAM, isSigner: false, isWritable: false },
    { name: 'associated_token_program', pubkey: PROGRAMS.associatedToken, isSigner: false, isWritable: false },
    { name: 'fee_recipient', pubkey: feeRecipient, isSigner: false, isWritable: true },
    { name: 'associated_quote_fee_recipient', pubkey: quoteAccount(feeRecipient), isSigner: false, isWritable: true },
    { name: 'buyback_fee_recipient', pubkey: buybackFeeRecipient, isSigner: false, isWritable: true },
    { name: 'associated_quote_buyback_fee_recipient', pubkey: quoteAccount(buybackFeeRecipient), isSigner: false, isWritable: true },
    { name: 'bonding_curve', pubkey: curve, isSigner: false, isWritable: true },
    { name: 'associated_base_bonding_curve', pubkey: associatedTokenAddress(curve, mint), isSigner: false, isWritable: true },
    { name: 'associated_quote_bonding_curve', pubkey: quoteAccount(curve), isSigner: false, isWritable: true },
    { name: 'user', pubkey: user, isSigner: true, isWritable: true },
    { name: 'associated_base_user', pubkey: associatedTokenAddress(user, mint), isSigner: false, isWritable: true },
    { name: 'associated_quote_user', pubkey: quoteAccount(user), isSigner: false, isWritable: true },
    { name: 'creator_vault', pubkey: creatorVault, isSigner: false, isWritable: true },
    { name: 'associated_creator_vault', pubkey: quoteAccount(creatorVault), isSigner: false, isWritable: true },
    { name: 'sharing_config', pubkey: pda([utf8('sharing-config'), base58Decode(mint)], FEE_PROGRAM), isSigner: false, isWritable: false },
    { name: 'global_volume_accumulator', pubkey: pda([utf8('global_volume_accumulator')], PUMP_PROGRAM_ID), isSigner: false, isWritable: false },
    { name: 'user_volume_accumulator', pubkey: userVolume, isSigner: false, isWritable: true },
    { name: 'associated_user_volume_accumulator', pubkey: quoteAccount(userVolume), isSigner: false, isWritable: true },
    // The fee program's config for this launchpad: the seed is the pump
    // program's own id, as a raw 32-byte key rather than text.
    { name: 'fee_config', pubkey: pda([utf8('fee_config'), base58Decode(PUMP_PROGRAM_ID)], FEE_PROGRAM), isSigner: false, isWritable: false },
    { name: 'fee_program', pubkey: FEE_PROGRAM, isSigner: false, isWritable: false },
    { name: 'system_program', pubkey: SYSTEM_PROGRAM, isSigner: false, isWritable: false },
    { name: 'event_authority', pubkey: pda([utf8('__event_authority')], PUMP_PROGRAM_ID), isSigner: false, isWritable: false },
    { name: 'program', pubkey: PUMP_PROGRAM_ID, isSigner: false, isWritable: false },
  ];
}

export function buildBuyV2({ mint, user, creator = user, amount, maxSolCost, feeRecipient, buybackFeeRecipient, global = null }) {
  for (const [field, value] of Object.entries({ mint, user, creator, feeRecipient, buybackFeeRecipient })) {
    if (typeof value !== 'string' || !value) throw new Error(`buy_v2 needs a ${field}.`);
    addressOf(value);
  }
  // Checked against the pools when they are available, because a recipient the
  // program does not recognise fails the whole transaction — and at a launch
  // that failure arrives too late to do anything about.
  if (global) {
    if (!global.feeRecipients.includes(feeRecipient) && feeRecipient !== global.feeRecipient) {
      throw new Error(`${feeRecipient} is not one of the launchpad's fee recipients.`);
    }
    if (!global.buybackFeeRecipients.includes(buybackFeeRecipient)) {
      throw new Error(`${buybackFeeRecipient} is not one of the launchpad's buyback fee recipients.`);
    }
  }
  if (BigInt(amount) <= 0n) throw new Error('A dev buy needs a positive token amount.');
  if (BigInt(maxSolCost) <= 0n) throw new Error('A dev buy needs a positive spending cap.');

  const accounts = buyV2Accounts({ mint, user, creator, feeRecipient, buybackFeeRecipient });
  return {
    programId: PUMP_PROGRAM_ID,
    keys: accounts.map(({ pubkey, isSigner, isWritable }) => ({ pubkey, isSigner, isWritable })),
    accountNames: accounts.map(account => account.name),
    data: Uint8Array.from([...BUY_V2_DISCRIMINATOR, ...encodeU64(amount), ...encodeU64(maxSolCost)]),
  };
}

/** The recipients a launch would use: the first of each pool, which is a valid choice. */
export const defaultRecipients = global => ({
  feeRecipient: global.feeRecipients[0],
  buybackFeeRecipient: global.buybackFeeRecipients[0],
});

// The address lookup table live launches use. A create and a dev buy together
// name more accounts than a legacy transaction can hold, and this table is how
// the launches observed on chain fit them: both samples used this one, and
// nothing else. It is read and checked rather than trusted — the table is
// someone else's account and may change, so a launch that cannot find its
// constants in it should fail loudly instead of sending a broken transaction.
export const LAUNCH_LOOKUP_TABLE = 'Hyif6eWb8x88RVrvjPfabsgRYnwkVnyByEXTVTXbUcyP';

export async function readLookupTable(call, address = LAUNCH_LOOKUP_TABLE) {
  const info = await call('getAccountInfo', [address, { encoding: 'base64' }]);
  if (!info?.value) throw new Error(`Address lookup table ${address} does not exist.`);
  const addresses = parseLookupTable(Buffer.from(info.value.data[0], 'base64'));
  return { address, addresses, owner: info.value.owner };
}

/**
 * The associated-token-program instruction that creates a token account only if
 * it is missing.
 *
 * `buy_v2` does not create the buyer's account for the new mint — it requires
 * it, and says so: without this the simulation fails with
 * `AnchorError caused by account: associated_base_user. AccountNotInitialized`.
 * A launch that bundles its own first buy therefore has to create that account
 * in the same transaction, between the create and the buy.
 *
 * Idempotent on purpose: an account that already exists must not turn a launch
 * into a failed transaction.
 */
export function createIdempotentAta({ payer, owner, mint, tokenProgram = PROGRAMS.token2022 }) {
  for (const [field, value] of Object.entries({ payer, owner, mint })) {
    if (typeof value !== 'string' || !value) throw new Error(`An associated token account needs a ${field}.`);
    addressOf(value);
  }
  return {
    programId: PROGRAMS.associatedToken,
    keys: [
      { pubkey: payer, isSigner: true, isWritable: true },
      { pubkey: associatedTokenAddress(owner, mint, tokenProgram), isSigner: false, isWritable: true },
      { pubkey: owner, isSigner: false, isWritable: false },
      { pubkey: mint, isSigner: false, isWritable: false },
      { pubkey: SYSTEM_PROGRAM, isSigner: false, isWritable: false },
      { pubkey: tokenProgram, isSigner: false, isWritable: false },
    ],
    accountNames: ['payer', 'associated_token_account', 'owner', 'mint', 'system_program', 'token_program'],
    // CreateIdempotent is instruction 1 of the associated token program.
    data: Uint8Array.of(1),
  };
}

/** Everything a bundled dev buy needs, in the order the transaction must send it. */
export function devBuyInstructions({ mint, user, creator = user, amount, maxSolCost, feeRecipient, buybackFeeRecipient, global = null }) {
  return [
    createIdempotentAta({ payer: user, owner: user, mint }),
    buildBuyV2({ mint, user, creator, amount, maxSolCost, feeRecipient, buybackFeeRecipient, global }),
  ];
}
