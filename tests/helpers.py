"""Shared test helpers. Tests use only the standard library (unittest)."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from opc_guard import Runner, ToolRegistry, ToolSpec  # noqa: E402
from opc_guard.manifest import parse_manifest  # noqa: E402
from opc_guard.providers import MockProvider  # noqa: E402

BASE_MANIFEST = """
[agent]
id = "t"
version = "0.0.1"

[budget]
max_tokens = 100000
max_usd = 1.0
max_steps = 5
max_wall_seconds = 30

[tiers]
ladder = ["small", "large"]

[tiers.small]
model = "mock-small"

[tiers.large]
model = "mock-large"

[grants]
scopes = ["orders:read", "payments:write"]

[tools.read_thing]
requires_approval = false

[tools.write_thing]
requires_approval = false

[tools.write_thing.limits]
amount = 50

[approvals]
timeout_seconds = 2

[evals]
min_pass_rate = 0.5
max_cost_regression_pct = 10
"""


def manifest(overrides: str = "", extra: str = "", base: str = BASE_MANIFEST):
    """Build a manifest from the base text with simple string overrides appended."""
    text = base + extra
    for old, new in [p.split("=>", 1) for p in overrides.split(";;") if "=>" in p]:
        assert old in text, f"override target missing: {old!r}"
        text = text.replace(old, new)
    return parse_manifest(text)


def registry(read_fn=None, write_fn=None) -> ToolRegistry:
    reg = ToolRegistry()
    reg.register(
        ToolSpec(
            "read_thing",
            read_fn or (lambda x: f"value-{x}"),
            side_effect="read",
            scope="orders:read",
            args={"x": "str"},
            description="read",
        )
    )
    reg.register(
        ToolSpec(
            "write_thing",
            write_fn or (lambda amount: f"wrote {amount}"),
            side_effect="irreversible",
            scope="payments:write",
            args={"amount": "float"},
            description="write",
        )
    )
    return reg


def responder_from(actions: list[str]):
    """Mock responder that returns the given texts in order, then repeats the last one."""
    state = {"i": 0}

    def respond(model: str, prompt: str) -> str:
        i = min(state["i"], len(actions) - 1)
        state["i"] += 1
        return actions[i]

    return respond


def runner(m, reg, responses, **kwargs) -> Runner:
    kwargs.setdefault("runs_dir", tempfile.mkdtemp(prefix="opcg-test-"))
    return Runner(m, reg, MockProvider(responder_from(responses)), **kwargs)


FINAL_OK = '{"type": "final", "answer": "done"}'
