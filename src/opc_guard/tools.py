"""Tool registry and argument validation.

Tools are plain Python callables registered in code. The manifest decides
which of them an agent may use; the registry decides what they are.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from opc_guard.errors import ConfigError

SIDE_EFFECTS = ("read", "write", "irreversible")
_TYPES: dict[str, tuple[type, ...]] = {
    "str": (str,),
    "int": (int,),
    "float": (int, float),
    "bool": (bool,),
}


@dataclass(frozen=True)
class ToolSpec:
    name: str
    fn: Callable[..., Any]
    side_effect: str
    scope: str
    args: dict[str, str] = field(default_factory=dict)  # arg name -> one of _TYPES
    description: str = ""

    def __post_init__(self) -> None:
        if self.side_effect not in SIDE_EFFECTS:
            raise ConfigError(f"tool '{self.name}': side_effect must be one of {SIDE_EFFECTS}")
        for arg, typ in self.args.items():
            if typ not in _TYPES:
                raise ConfigError(f"tool '{self.name}': arg '{arg}' has unknown type '{typ}'")

    def validate_args(self, args: dict[str, Any]) -> list[str]:
        errors = []
        for name, typ in self.args.items():
            if name not in args:
                errors.append(f"missing arg '{name}'")
            elif not isinstance(args[name], _TYPES[typ]) or (typ != "bool" and isinstance(args[name], bool)):
                errors.append(f"arg '{name}' must be {typ}")
        for name in args:
            if name not in self.args:
                errors.append(f"unexpected arg '{name}'")
        return errors


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        if spec.name in self._tools:
            raise ConfigError(f"tool '{spec.name}' already registered")
        self._tools[spec.name] = spec

    def get(self, name: str) -> ToolSpec | None:
        return self._tools.get(name)

    def names(self) -> list[str]:
        return sorted(self._tools)
