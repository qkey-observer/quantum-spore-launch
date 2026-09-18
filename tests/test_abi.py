from quantum_launch.abi_util import LAUNCH_DEPLOYMENT, selector


def test_predict_selector_matches_the_pons_v2_wired_deployer() -> None:
    # Same LaunchDeployment tuple as Pons V2 notes (selector 0x2bc63e61).
    sig = f"predictLaunchAddresses({LAUNCH_DEPLOYMENT})"
    assert "0x" + selector(sig).hex() == "0x2bc63e61"
