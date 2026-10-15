"""Policy decisions for a single tool call (FR-1, FR-2, FR-5).

Order of checks is deny-first: unknown tool, ungranted scope, bad arguments,
over-limit values. Only then is approval considered. Irreversible tools always
require approval, even if the manifest forgets to say so.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from opc_guard.manifest import Manifest
from opc_guard.tools import ToolSpec


@dataclass(frozen=True)
class Decision:
    allowed: bool
    reason: str
    needs_approval: bool = False


def decide(manifest: Manifest, spec: ToolSpec | None, tool_name: str, args: dict[str, Any]) -> Decision:
    if spec is None:
        return Decision(False, f"unknown tool '{tool_name}'")
    policy = manifest.tools.get(tool_name)
    if policy is None:
        return Decision(False, f"tool '{tool_name}' is not in the manifest")
    if spec.scope not in manifest.grants:
        return Decision(False, f"scope '{spec.scope}' is not granted")
    errors = spec.validate_args(args)
    if errors:
        return Decision(False, "invalid args: " + "; ".join(errors))
    for arg, cap in policy.limits.items():
        value = args.get(arg)
        # A cap bounds the value to [0, cap]. Negative values are denied too:
        # a refund of -500 is a charge, not a small refund.
        if isinstance(value, (int, float)) and not 0 <= value <= cap:
            return Decision(False, f"limit exceeded: {arg}={value} outside [0, {cap}]")
    needs = policy.requires_approval or spec.side_effect == "irreversible"
    return Decision(True, "allowed", needs_approval=needs)
