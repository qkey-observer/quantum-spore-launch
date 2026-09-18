// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

import {QuantumChapelToken} from "./QuantumChapelToken.sol";

/// @notice Chapel rehearsal factory. CREATE2 salt is the measured keccak salt.
contract QuantumChapelFactory {
    event Launched(address indexed token, bytes32 indexed salt, string bitstring);

    function predict(bytes32 salt, string memory bitstring, string memory name, string memory symbol)
        public
        view
        returns (address token)
    {
        bytes memory bytecode = abi.encodePacked(
            type(QuantumChapelToken).creationCode,
            abi.encode(bitstring, name, symbol, salt)
        );
        bytes32 hash = keccak256(abi.encodePacked(bytes1(0xff), address(this), salt, keccak256(bytecode)));
        return address(uint160(uint256(hash)));
    }

    function launch(bytes32 salt, string memory bitstring, string memory name, string memory symbol)
        external
        returns (address token)
    {
        token = address(new QuantumChapelToken{salt: salt}(bitstring, name, symbol, salt));
        emit Launched(token, salt, bitstring);
    }
}
