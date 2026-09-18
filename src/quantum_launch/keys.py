"""Load a signer from env, keystore, or an external process. Never log key material."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Protocol

from .errors import SignerError

ENV_KEY = "QKEY_LAUNCH_PRIVATE_KEY"
ENV_KEYSTORE = "QKEY_LAUNCH_KEYSTORE"
ENV_KEYSTORE_PASSWORD = "QKEY_LAUNCH_KEYSTORE_PASSWORD"
ENV_KEY_FILE = "QKEY_LAUNCH_KEY_FILE"


class Signer(Protocol):
    address: str

    def sign_transaction(self, tx: dict[str, Any]) -> bytes: ...


class LocalSigner:
    def __init__(self, key_hex: str):
        from eth_account import Account

        cleaned = key_hex.strip()
        if cleaned.startswith("0x"):
            cleaned = cleaned[2:]
        if len(cleaned) != 64 or any(c not in "0123456789abcdefABCDEF" for c in cleaned):
            raise SignerError("launch key is not a 32-byte hex value")
        self._account = Account.from_key(bytes.fromhex(cleaned))
        self.address = self._account.address

    def sign_transaction(self, tx: dict[str, Any]) -> bytes:
        signed = self._account.sign_transaction(tx)
        raw = getattr(signed, "raw_transaction", None) or getattr(signed, "rawTransaction")
        return bytes(raw)

    def __repr__(self) -> str:
        return f"<LocalSigner {self.address}>"

    def __str__(self) -> str:
        return self.__repr__()


class ExternalSigner:
    """Clef / hardware-bridge JSON-RPC: account_signTransaction."""

    def __init__(self, url: str, address: str):
        if not url.startswith(("http://", "https://")):
            raise SignerError("external signer URL must be http(s)")
        from eth_utils import to_checksum_address

        self.url = url
        self.address = to_checksum_address(address)

    def sign_transaction(self, tx: dict[str, Any]) -> bytes:
        from .rpc import Rpc

        # Reuse HTTP POST; Clef methods are not in READ_METHODS, so call raw.
        import json
        from urllib.request import Request, urlopen

        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "account_signTransaction",
            "params": [tx],
        }
        req = Request(self.url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
        try:
            with urlopen(req, timeout=120) as resp:
                parsed = json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            raise SignerError("external signer request failed") from exc
        if parsed.get("error"):
            raise SignerError("external signer returned an error")
        raw = (parsed.get("result") or {}).get("raw") or (parsed.get("result") or {}).get("rawTransaction")
        if not isinstance(raw, str) or not raw.startswith("0x"):
            raise SignerError("external signer did not return raw transaction bytes")
        return bytes.fromhex(raw[2:])

    def __repr__(self) -> str:
        return f"<ExternalSigner {self.address} {self.url}>"


def load_signer(
    env: dict[str, str] | None = None,
    *,
    keystore: str | None = None,
    key_file: str | None = None,
    signer_url: str | None = None,
    signer_address: str | None = None,
) -> Signer:
    env = env if env is not None else dict(os.environ)
    if signer_url:
        if not signer_address:
            raise SignerError("external signer requires the public address (--signer-address)")
        return ExternalSigner(signer_url, signer_address)
    keystore_path = keystore or env.get(ENV_KEYSTORE)
    if keystore_path:
        password = env.get(ENV_KEYSTORE_PASSWORD)
        if not password:
            raise SignerError("QKEY_LAUNCH_KEYSTORE_PASSWORD is required with a keystore")
        return _from_keystore(keystore_path, password)
    path = key_file or env.get(ENV_KEY_FILE)
    if path:
        text = Path(path).read_text(encoding="utf-8").strip()
        return LocalSigner(text)
    raw = env.get(ENV_KEY)
    if raw:
        return LocalSigner(raw)
    raise SignerError(
        "no signer configured. Set QKEY_LAUNCH_PRIVATE_KEY, a keystore, "
        "QKEY_LAUNCH_KEY_FILE, or --signer-url (Clef / hardware bridge). "
        "Keys are never accepted as argv flags."
    )


def _from_keystore(path: str, password: str) -> LocalSigner:
    from eth_account import Account

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    try:
        private = Account.decrypt(payload, password)
    except Exception as exc:
        raise SignerError("keystore decrypt failed") from exc
    signer = LocalSigner(private.hex())
    return signer


def assert_initiator(signer: Signer, initiator: str) -> None:
    if signer.address.lower() != initiator.lower():
        raise SignerError("signer address is not the frozen plan initiator")
