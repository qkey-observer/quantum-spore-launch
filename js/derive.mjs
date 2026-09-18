// Public JS derivation. Must stay byte-for-byte with src/quantum_launch/derive.py
// and vectors/derive.json (canonical, planHash, saltFromBitstring).
import { keccak256, toHex } from 'viem';

export function canonical(value) {
  if (Array.isArray(value)) return `[${value.map(canonical).join(',')}]`;
  if (value && typeof value === 'object') {
    return `{${Object.keys(value).sort().map(k => `${JSON.stringify(k)}:${canonical(value[k])}`).join(',')}}`;
  }
  return JSON.stringify(value ?? null);
}

export function planHash(plan) {
  return keccak256(toHex(canonical(plan)));
}

export function saltFromBitstring(bitstring) {
  if (!/^[01]{2,256}$/.test(bitstring)) throw new Error(`Not a measured bitstring: ${bitstring}`);
  return keccak256(toHex(bitstring));
}
