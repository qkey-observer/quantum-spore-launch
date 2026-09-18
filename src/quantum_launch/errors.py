"""Fail-closed errors. Missing values stay missing; they are never replaced with zero."""


class QuantumLaunchError(Exception):
    """Base error. Message is safe to print (no keys, no seed phrases)."""


class RecordError(QuantumLaunchError):
    """Spore/job record failed a self-check."""


class MeasureError(QuantumLaunchError):
    """IBM job did not yield ordered per-shot bitstrings or billed time."""


class PredictError(QuantumLaunchError):
    """CREATE2 prediction failed or collided."""


class LaunchError(QuantumLaunchError):
    """Signing, broadcast, receipt or code-verification failed."""


class SignerError(QuantumLaunchError):
    """Signer could not be loaded. The key material is never included in the message."""


class CostError(QuantumLaunchError):
    """A billed-time or rate figure is missing or invented."""
