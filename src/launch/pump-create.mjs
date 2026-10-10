// Build pump.fun's `create_v2` instruction — the one a launch actually sends
// today.
//
// Every discriminator, account and argument below was read off the chain, not
// out of documentation. The program publishes its own Anchor IDL at
// AYgC53tU5BbP2NAnv5nConJxAdpQZctvmZK88pu69xRs (the account Anchor derives from
// the program id with the seed "anchor:idl"), and that IDL is where the names,
// seeds and types come from. The derivations are then checked against real
// launches: `npm run verify:pump` reproduces all 16 accounts of two of them.
//
// Reading the IDL rather than a guide was not pedantry. `sha256("global:create")`
// — the discriminator Anchor would generate for an instruction called `create` —
// is 181ec828051c0777, and that instruction still exists in the IDL with 14
// accounts, the legacy token program and a Metaplex metadata account. Live
// launches do not use it. They use `create_v2`: a different discriminator, 16
// accounts, Token-2022, no Metaplex account, four extra arguments. A tool built
// from the name alone would have produced a transaction that fails.
import { findProgramAddress } from '../derive/index.mjs';
import { addressOf, base58Encode, compileMessage, encodeString, encodeU64, SYSTEM_PROGRAM, unsignedTransaction } from './solana-tx.mjs';
import { bondingCurveFor, PUMP_PROGRAM_ID } from '../derive/pump.mjs';

export const CREATE_V2_DISCRIMINATOR = Uint8Array.of(0xd6, 0x90, 0x4c, 0xec, 0x5f, 0x8b, 0x31, 0xb4);
export const IDL_ACCOUNT = 'AYgC53tU5BbP2NAnv5nConJxAdpQZctvmZK88pu69xRs';

export const PROGRAMS = {
  pump: PUMP_PROGRAM_ID,
  mayhem: 'MAyhSmzXzV1pTf7LsNkrNwkWKTo4ougAJ1PPg47MD4e',
  token2022: 'TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb',
  associatedToken: 'ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL',
  system: SYSTEM_PROGRAM,
};

const utf8 = value => new TextEncoder().encode(value);
const pda = (seeds, programId) => findProgramAddress(seeds, programId).address;

/** An associated token account is itself a PDA of the ATA program. */
export const associatedTokenAddress = (owner, mint, tokenProgram = PROGRAMS.token2022) =>
  pda([addressOf(owner), addressOf(tokenProgram), addressOf(mint)], PROGRAMS.associatedToken);

/**
 * Every account `create_v2` reads or writes, derived rather than looked up, so
 * a launch can be prepared offline for a mint that does not exist yet.
 */
export function createV2Accounts({ mint, user }) {
  const bondingCurve = bondingCurveFor(mint).address;
  const solVault = pda([utf8('sol-vault')], PROGRAMS.mayhem);
  const mayhemState = pda([utf8('mayhem-state'), addressOf(mint)], PROGRAMS.mayhem);
  return [
    { name: 'mint', pubkey: typeof mint === 'string' ? mint : base58Encode(mint), isSigner: true, isWritable: true },
    { name: 'mint_authority', pubkey: pda([utf8('mint-authority')], PROGRAMS.pump), isSigner: false, isWritable: false },
    { name: 'bonding_curve', pubkey: bondingCurve, isSigner: false, isWritable: true },
    { name: 'associated_bonding_curve', pubkey: associatedTokenAddress(bondingCurve, mint), isSigner: false, isWritable: true },
    { name: 'global', pubkey: pda([utf8('global')], PROGRAMS.pump), isSigner: false, isWritable: false },
    { name: 'user', pubkey: user, isSigner: true, isWritable: true },
    { name: 'system_program', pubkey: PROGRAMS.system, isSigner: false, isWritable: false },
    { name: 'token_program', pubkey: PROGRAMS.token2022, isSigner: false, isWritable: false },
    { name: 'associated_token_program', pubkey: PROGRAMS.associatedToken, isSigner: false, isWritable: false },
    { name: 'mayhem_program_id', pubkey: PROGRAMS.mayhem, isSigner: false, isWritable: true },
    { name: 'global_params', pubkey: pda([utf8('global-params')], PROGRAMS.mayhem), isSigner: false, isWritable: false },
    { name: 'sol_vault', pubkey: solVault, isSigner: false, isWritable: true },
    { name: 'mayhem_state', pubkey: mayhemState, isSigner: false, isWritable: true },
    // The IDL gives this one no seeds. It is the sol vault's token account for
    // the new mint, which is what both sampled launches passed.
    { name: 'mayhem_token_vault', pubkey: associatedTokenAddress(solVault, mint), isSigner: false, isWritable: true },
    { name: 'event_authority', pubkey: pda([utf8('__event_authority')], PROGRAMS.pump), isSigner: false, isWritable: false },
    { name: 'program', pubkey: PROGRAMS.pump, isSigner: false, isWritable: false },
  ];
}

const METADATA_LIMITS = { name: 32, symbol: 10, uri: 200 };

export function buildCreateV2({
  mint, user, name, symbol, uri, creator = user,
  isMayhemMode = false, isCashbackEnabled = false, creatorFeeBps = 0, isHolderReward = false,
}) {
  for (const [field, value] of Object.entries({ mint, user, name, symbol, uri })) {
    if (typeof value !== 'string' || !value) throw new Error(`create_v2 needs a ${field}.`);
  }
  // Checked here rather than left to the program: a rejected transaction after
  // a launch window opens costs more than an error before it.
  for (const [field, limit] of Object.entries(METADATA_LIMITS)) {
    const value = { name, symbol, uri }[field];
    if (utf8(value).length > limit) throw new Error(`${field} is longer than ${limit} bytes, which pump.fun rejects.`);
  }
  if (!/^https?:\/\//.test(uri)) throw new Error('uri should be the http(s) address of the metadata JSON.');
  addressOf(creator);

  const accounts = createV2Accounts({ mint, user });
  const data = Uint8Array.from([
    ...CREATE_V2_DISCRIMINATOR,
    ...encodeString(name), ...encodeString(symbol), ...encodeString(uri),
    ...addressOf(creator),
    isMayhemMode ? 1 : 0, isCashbackEnabled ? 1 : 0, ...encodeU64(creatorFeeBps), isHolderReward ? 1 : 0,
  ]);
  return {
    programId: PROGRAMS.pump,
    keys: accounts.map(({ pubkey, isSigner, isWritable }) => ({ pubkey, isSigner, isWritable })),
    accountNames: accounts.map(a => a.name),
    data,
  };
}

/**
 * The whole launch transaction, unsigned. Two signatures are required and
 * neither is produced here: the fee payer's, and the mint's — which on this
 * launchpad means the bitstring. Signing happens wherever those keys are, and
 * that is deliberately not this process.
 */
export function buildLaunchTransaction({ recentBlockhash, ...args }) {
  if (!recentBlockhash) throw new Error('A transaction needs a recent blockhash; it expires in about a minute.');
  const instruction = buildCreateV2(args);
  const message = compileMessage({ payer: args.user, instructions: [instruction], recentBlockhash });
  return {
    ...unsignedTransaction(message),
    instruction,
    accounts: message.accounts,
    mint: typeof args.mint === 'string' ? args.mint : base58Encode(args.mint),
    warning: 'Unsigned. The mint signature comes from the bitstring, so anyone who has the bitstring before this lands can launch it themselves.',
  };
}
