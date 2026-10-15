"""opc-guard: policy-enforced runtime for agents run by a team of one."""

from opc_guard.errors import ConfigError, OpcGuardError, ProviderError
from opc_guard.manifest import Manifest, load_manifest
from opc_guard.runner import DeterministicRule, RunResult, Runner
from opc_guard.tools import ToolRegistry, ToolSpec

__version__ = "0.1.0"

__all__ = [
    "ConfigError",
    "DeterministicRule",
    "Manifest",
    "OpcGuardError",
    "ProviderError",
    "RunResult",
    "Runner",
    "ToolRegistry",
    "ToolSpec",
    "load_manifest",
]
