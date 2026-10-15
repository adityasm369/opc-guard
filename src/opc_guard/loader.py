"""Load an agent factory from a 'path/to/file.py:function' or 'package.module:function' spec."""

from __future__ import annotations

import importlib
import importlib.util
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from opc_guard.errors import ConfigError


def load_factory(spec: str) -> Callable[..., Any]:
    if ":" not in spec:
        raise ConfigError(f"agent spec must look like 'file.py:function', got '{spec}'")
    target, func_name = spec.rsplit(":", 1)
    if target.endswith(".py") or "/" in target:
        path = Path(target).resolve()
        if not path.exists():
            raise ConfigError(f"agent file not found: {path}")
        mod_name = f"_opc_agent_{path.stem}"
        module_spec = importlib.util.spec_from_file_location(mod_name, path)
        if module_spec is None or module_spec.loader is None:
            raise ConfigError(f"cannot load agent file: {path}")
        module = importlib.util.module_from_spec(module_spec)
        sys.modules[mod_name] = module
        module_spec.loader.exec_module(module)
    else:
        module = importlib.import_module(target)
    factory = getattr(module, func_name, None)
    if not callable(factory):
        raise ConfigError(f"'{func_name}' not found or not callable in {target}")
    return factory
