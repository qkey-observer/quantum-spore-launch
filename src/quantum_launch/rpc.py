"""Minimal JSON-RPC client. No retries that could hide a wrong chain."""

from __future__ import annotations

import json
from typing import Any
from urllib.request import Request, urlopen

from .errors import PredictError

READ_METHODS = frozenset({
    "eth_chainId",
    "eth_getBlockByNumber",
    "eth_getTransactionByHash",
    "eth_getCode",
    "eth_call",
    "eth_getTransactionCount",
    "eth_gasPrice",
    "eth_maxPriorityFeePerGas",
    "eth_estimateGas",
    "eth_getTransactionReceipt",
    "eth_sendRawTransaction",
    "eth_blockNumber",
    "eth_getBalance",
})


class Rpc:
    def __init__(self, url: str, timeout_s: float = 20.0):
        if not url.startswith(("http://", "https://")):
            raise PredictError("RPC URL must be http(s)")
        self.url = url
        self.timeout_s = timeout_s
        self._id = 0

    def request(self, method: str, params: list[Any] | None = None) -> Any:
        if method not in READ_METHODS:
            raise PredictError(f"RPC method not allowed: {method}")
        self._id += 1
        payload = {"jsonrpc": "2.0", "id": self._id, "method": method, "params": params or []}
        body = json.dumps(payload).encode("utf-8")
        req = Request(self.url, data=body, headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urlopen(req, timeout=self.timeout_s) as resp:
                raw = resp.read()
        except Exception as exc:
            raise PredictError("RPC request failed") from exc
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise PredictError("RPC returned non-JSON") from exc
        if parsed.get("error"):
            raise PredictError("RPC error")
        return parsed.get("result")

    def chain_id(self) -> int:
        value = self.request("eth_chainId")
        return int(value, 16)

    def block_number(self) -> int:
        return int(self.request("eth_blockNumber"), 16)

    def get_block(self, number: int | str = "latest") -> dict[str, Any]:
        tag = number if isinstance(number, str) else hex(number)
        block = self.request("eth_getBlockByNumber", [tag, False])
        if not isinstance(block, dict):
            raise PredictError("RPC block missing")
        return block

    def get_code(self, address: str, block: int | str = "latest") -> str:
        tag = block if isinstance(block, str) else hex(block)
        code = self.request("eth_getCode", [address, tag])
        if not isinstance(code, str) or not code.startswith("0x"):
            raise PredictError("eth_getCode returned a malformed result")
        return code

    def call(self, to: str, data: str, block: int | str = "latest") -> str:
        tag = block if isinstance(block, str) else hex(block)
        result = self.request("eth_call", [{"to": to, "data": data}, tag])
        if not isinstance(result, str) or not result.startswith("0x"):
            raise PredictError("eth_call returned a malformed result")
        return result

    def nonce(self, address: str, block: str = "pending") -> int:
        return int(self.request("eth_getTransactionCount", [address, block]), 16)

    def gas_price(self) -> int:
        return int(self.request("eth_gasPrice"), 16)

    def estimate_gas(self, tx: dict[str, Any]) -> int:
        return int(self.request("eth_estimateGas", [tx]), 16)

    def send_raw(self, raw_hex: str) -> str:
        tx_hash = self.request("eth_sendRawTransaction", [raw_hex])
        if not isinstance(tx_hash, str) or not tx_hash.startswith("0x"):
            raise PredictError("eth_sendRawTransaction returned a malformed hash")
        return tx_hash

    def receipt(self, tx_hash: str) -> dict[str, Any] | None:
        result = self.request("eth_getTransactionReceipt", [tx_hash])
        if result is None:
            return None
        if not isinstance(result, dict):
            raise PredictError("malformed receipt")
        return result

    def get_transaction(self, tx_hash: str) -> dict[str, Any] | None:
        result = self.request("eth_getTransactionByHash", [tx_hash])
        if result is None:
            return None
        if not isinstance(result, dict):
            raise PredictError("malformed transaction")
        return result

    def balance(self, address: str) -> int:
        return int(self.request("eth_getBalance", [address, "latest"]), 16)
