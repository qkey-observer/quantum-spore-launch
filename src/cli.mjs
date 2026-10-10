#!/usr/bin/env node
// Derive the address a measured bitstring fixes. Arithmetic only.
import { deriveCreate2, deriveSolana, saltFromBitstring } from './derive/index.mjs';

const flag = name => { const i = process.argv.indexOf(`--${name}`); return i === -1 ? null : process.argv[i + 1]; };
const bitstring = flag('bitstring');
if (!bitstring) {
  console.error('usage: npm run derive -- --bitstring <01…> [--program <base58>] [--deployer 0x… --init-code-hash 0x…]');
  process.exit(1);
}
const program = flag('program');
const deployer = flag('deployer');
const initCodeHash = flag('init-code-hash');
console.log(`bitstring  ${bitstring}`);
console.log(`salt       ${saltFromBitstring(bitstring)}  (keccak256, for CREATE2)`);
if (program) {
  const out = deriveSolana(bitstring, program);
  console.log(`solana     ${out.address}  bump ${out.bump}`);
}
if (deployer && initCodeHash) {
  const out = deriveCreate2({ bitstring, deployer, initCodeHash });
  console.log(`evm        ${out.address}`);
}
if (!program && !(deployer && initCodeHash)) {
  console.log('(no target given — pass --program, or --deployer with --init-code-hash)');
}
