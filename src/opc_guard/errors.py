"""Exception types. Every error the library raises on purpose derives from OpcGuardError."""


class OpcGuardError(Exception):
    """Base class for all opc-guard errors."""


class ConfigError(OpcGuardError):
    """A manifest, registry, or wiring problem. Raised before any run starts."""


class ManifestError(ConfigError):
    """Manifest failed validation. `.errors` lists every problem found."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("manifest invalid:\n  - " + "\n  - ".join(errors))


class ProviderError(OpcGuardError):
    """A model provider call failed or returned an unusable response."""


class AuditError(OpcGuardError):
    """The audit chain is broken or could not be written."""
