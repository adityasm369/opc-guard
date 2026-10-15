"""Manifest loading and validation.

A manifest is a TOML file that declares what one agent may do: which tools,
which scopes, which model tiers, and how much it may spend. It is read once,
validated in full, hashed, and never mutated during a run (ADR-004).
"""

from __future__ import annotations

import hashlib
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from opc_guard.budget import PRICING, BudgetConfig
from opc_guard.errors import ManifestError


@dataclass(frozen=True)
class Tier:
    name: str
    model: str


@dataclass(frozen=True)
class ToolPolicy:
    name: str
    requires_approval: bool = False
    limits: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class Manifest:
    id: str
    version: str
    description: str
    budget: BudgetConfig
    ladder: tuple[Tier, ...]
    grants: frozenset[str]
    tools: dict[str, ToolPolicy]
    approval_timeout: float
    min_pass_rate: float
    max_cost_regression_pct: float
    sha256: str
    path: Path | None = None


def _require(section: dict[str, Any], key: str, kind: type, errors: list[str], where: str) -> Any:
    if key not in section:
        errors.append(f"{where}: missing required key '{key}'")
        return None
    value = section[key]
    if not isinstance(value, kind) or (kind is not bool and isinstance(value, bool)):
        errors.append(f"{where}.{key}: expected {kind.__name__}, got {type(value).__name__}")
        return None
    return value


def parse_manifest(text: str, path: Path | None = None) -> Manifest:
    """Parse and validate manifest TOML. Raises ManifestError listing every problem."""
    errors: list[str] = []
    try:
        raw = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ManifestError([f"invalid TOML: {exc}"]) from exc

    agent = raw.get("agent", {})
    agent_id = _require(agent, "id", str, errors, "[agent]")
    version = _require(agent, "version", str, errors, "[agent]")
    description = agent.get("description", "")

    budget_raw = raw.get("budget", {})
    max_tokens = _require(budget_raw, "max_tokens", int, errors, "[budget]")
    max_steps = _require(budget_raw, "max_steps", int, errors, "[budget]")
    max_usd = budget_raw.get("max_usd")
    if not isinstance(max_usd, (int, float)) or isinstance(max_usd, bool):
        errors.append("[budget].max_usd: required number")
        max_usd = None
    max_wall = budget_raw.get("max_wall_seconds", 60)
    if not isinstance(max_wall, (int, float)) or isinstance(max_wall, bool):
        errors.append("[budget].max_wall_seconds: must be a number")
        max_wall = 60
    for name, value in (
        ("max_tokens", max_tokens),
        ("max_steps", max_steps),
        ("max_usd", max_usd),
        ("max_wall_seconds", max_wall),
    ):
        if value is not None and value <= 0:
            errors.append(f"[budget].{name}: must be > 0")

    tiers_raw = raw.get("tiers", {})
    ladder_names = tiers_raw.get("ladder")
    tiers: list[Tier] = []
    if not isinstance(ladder_names, list) or not ladder_names:
        errors.append("[tiers]: 'ladder' must be a non-empty list of tier names")
        ladder_names = []
    elif len(ladder_names) != len(set(ladder_names)):
        errors.append("[tiers].ladder: tier names must be unique")
    for name in ladder_names:
        tier_cfg = tiers_raw.get(name)
        if not isinstance(tier_cfg, dict) or "model" not in tier_cfg:
            errors.append(f"[tiers.{name}]: missing table with 'model'")
            continue
        model = tier_cfg["model"]
        if model not in PRICING:
            errors.append(f"[tiers.{name}].model: '{model}' has no entry in the pricing table")
        tiers.append(Tier(name=name, model=model))

    grants_raw = raw.get("grants", {})
    scopes = grants_raw.get("scopes", [])
    if not isinstance(scopes, list) or not all(isinstance(s, str) for s in scopes):
        errors.append("[grants].scopes: must be a list of strings")
        scopes = []

    tools: dict[str, ToolPolicy] = {}
    for tool_name, cfg in raw.get("tools", {}).items():
        if not isinstance(cfg, dict):
            errors.append(f"[tools.{tool_name}]: must be a table")
            continue
        limits = cfg.get("limits", {})
        if not isinstance(limits, dict) or not all(
            isinstance(v, (int, float)) and not isinstance(v, bool) for v in limits.values()
        ):
            errors.append(f"[tools.{tool_name}.limits]: values must be numbers")
            limits = {}
        tools[tool_name] = ToolPolicy(
            name=tool_name,
            requires_approval=bool(cfg.get("requires_approval", False)),
            limits=dict(limits),
        )

    approvals = raw.get("approvals", {})
    timeout = approvals.get("timeout_seconds", 120)
    if not isinstance(timeout, (int, float)) or isinstance(timeout, bool) or timeout <= 0:
        errors.append("[approvals].timeout_seconds: must be a number > 0")
        timeout = 120
    evals = raw.get("evals", {})
    min_pass = evals.get("min_pass_rate", 0.9)
    max_regress = evals.get("max_cost_regression_pct", 25)
    if not isinstance(min_pass, (int, float)) or isinstance(min_pass, bool) or not 0 <= min_pass <= 1:
        errors.append("[evals].min_pass_rate: must be a number between 0 and 1")
        min_pass = 0.9
    if not isinstance(max_regress, (int, float)) or isinstance(max_regress, bool) or max_regress < 0:
        errors.append("[evals].max_cost_regression_pct: must be a number >= 0")
        max_regress = 25

    if errors:
        raise ManifestError(errors)

    return Manifest(
        id=agent_id,
        version=version,
        description=description,
        budget=BudgetConfig(
            max_tokens=int(max_tokens),
            max_usd=float(max_usd),
            max_steps=int(max_steps),
            max_wall_seconds=float(max_wall),
        ),
        ladder=tuple(tiers),
        grants=frozenset(scopes),
        tools=tools,
        approval_timeout=float(timeout),
        min_pass_rate=float(min_pass),
        max_cost_regression_pct=float(max_regress),
        sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        path=path,
    )


def load_manifest(path: str | Path) -> Manifest:
    """Read a manifest file from disk and validate it."""
    p = Path(path)
    return parse_manifest(p.read_text(encoding="utf-8"), path=p)
