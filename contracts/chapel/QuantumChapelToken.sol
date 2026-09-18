// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

/// @notice Chapel (BSC testnet) marker only. Not a genius.fun token.
/// Proves CREATE2(salt = keccak256(utf8(bitstring))) produced this contract.
contract QuantumChapelToken {
    string public bitstring;
    string public name;
    string public symbol;
    bytes32 public saltUsed;

    constructor(
        string memory bitstring_,
        string memory name_,
        string memory symbol_,
        bytes32 saltUsed_
    ) {
        bitstring = bitstring_;
        name = name_;
        symbol = symbol_;
        saltUsed = saltUsed_;
    }
}
