from eth_account import Account

from quantum_launch.errors import SignerError
from quantum_launch.keys import LocalSigner, load_signer
import pytest


def test_local_signer_repr_does_not_contain_the_key() -> None:
    account = Account.create()
    key = account.key.hex()
    signer = LocalSigner(key)
    text = repr(signer) + str(signer)
    assert key not in text
    assert key.lower() not in text.lower()
    assert signer.address == account.address


def test_env_loader_reads_key_and_still_does_not_echo_it() -> None:
    account = Account.create()
    key = "0x" + account.key.hex()
    signer = load_signer({"QKEY_LAUNCH_PRIVATE_KEY": key})
    assert signer.address == account.address
    assert key[2:] not in repr(signer)


def test_missing_signer_is_explicit() -> None:
    with pytest.raises(SignerError, match="no signer configured"):
        load_signer({})
