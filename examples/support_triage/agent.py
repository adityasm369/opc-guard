"""Support triage agent.

Layers, cheapest first:
  1. Deterministic rule: opening hours cost zero model calls.
  2. Small tier (Haiku-class): order-status lookups via one read-only tool.
  3. Large tier (Sonnet-class): only when the small tier returns an invalid action.

`build()` is the factory the CLI calls. Offline, the provider is a scripted mock
that imitates the two tiers; pass provider_name="anthropic" with
ANTHROPIC_API_KEY set to use the real API.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "src"))

from opc_guard import Runner, ToolRegistry, ToolSpec, load_manifest  # noqa: E402
from opc_guard.approvals import Approver, deny_all  # noqa: E402
from opc_guard.providers import AnthropicProvider, MockProvider, Provider, ReplayProvider  # noqa: E402

SYSTEM_PROMPT = (
    "You are a support agent for a small online shop. Use lookup_order for order questions. "
    "Never invent order details."
)

ORDERS = {
    "1042": "shipped 2026-10-10 via DHL",
    "2001": "processing, ships in 2 days",
    "3003": "delivered 2026-10-08",
}


# ----------------------------------------------------------------- tools


def lookup_order(order_id: str) -> str:
    return ORDERS.get(order_id, "order not found")


def build_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            name="lookup_order",
            fn=lookup_order,
            side_effect="read",
            scope="orders:read",
            args={"order_id": "str"},
            description="Look up an order's status by order id",
        )
    )
    return registry


# ------------------------------------------------------ deterministic rules


def opening_hours(task: str) -> str | None:
    if "opening hours" in task.lower():
        return "We're open 9am to 6pm, Monday to Friday."
    return None


# ----------------------------------------------------- scripted mock model


def _task(prompt: str) -> str:
    m = re.search(r"^TASK: (.*)$", prompt, re.M)
    return m.group(1) if m else ""


def _last_tool_result(prompt: str) -> str | None:
    lines = [ln for ln in prompt.splitlines() if ln.startswith("TOOL_RESULT ")]
    if not lines:
        return None
    return lines[-1].split(": ", 1)[1] if ": " in lines[-1] else ""


def _small_tier(prompt: str) -> str:
    task = _task(prompt)
    result = _last_tool_result(prompt)
    if result is not None:
        return json.dumps({"type": "final", "answer": f"Order status: {result}."})
    if "complaint" in task.lower():
        # The small tier is not trusted with complaints: it answers in prose,
        # which is not a valid action, so the runner escalates.
        return "Probably a refund? Not sure, sorry."
    m = re.search(r"\b(\d{4,})\b", task)
    if m:
        return json.dumps({"type": "tool", "tool": "lookup_order", "args": {"order_id": m.group(1)}})
    return json.dumps({"type": "final", "answer": "Please share your order number so I can check it."})


def _large_tier(prompt: str) -> str:
    if "complaint" in _task(prompt).lower():
        return json.dumps(
            {"type": "final", "answer": "Sorry about the broken package. I've logged a complaint for the team to review."}
        )
    return json.dumps({"type": "final", "answer": "Thanks for reaching out. A person will follow up."})


def _mock_responder(model: str, prompt: str) -> str:
    return _small_tier(prompt) if "haiku" in model else _large_tier(prompt)


# ----------------------------------------------------------- factory


def make_provider(name: str, replay_calls: list[dict[str, Any]] | None = None) -> Provider:
    if name == "mock":
        return MockProvider(_mock_responder)
    if name == "anthropic":
        return AnthropicProvider()
    if name == "replay":
        return ReplayProvider(replay_calls or [])
    raise ValueError(f"unknown provider '{name}' (use mock, anthropic, replay)")


def build(
    provider_name: str = "mock",
    approver: Approver = deny_all,
    runs_dir: str = ".opc-guard/runs",
    replay_calls: list[dict[str, Any]] | None = None,
) -> Runner:
    manifest = load_manifest(HERE / "manifest.toml")
    return Runner(
        manifest,
        build_registry(),
        make_provider(provider_name, replay_calls),
        approver=approver,
        deterministic=[opening_hours],
        system_prompt=SYSTEM_PROMPT,
        runs_dir=runs_dir,
    )
