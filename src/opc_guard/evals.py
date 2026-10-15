"""Eval dataset, runner, and CI gate (FR-8).

Dataset format (JSONL, one case per line):
  {"id": "...", "task": "...", "expect": {"status": "completed", "contains": "..."}}

Each case runs on a fresh Runner so budgets and state never leak between cases.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from opc_guard.errors import ConfigError
from opc_guard.runner import Runner, RunResult


@dataclass(frozen=True)
class Case:
    id: str
    task: str
    expect: dict[str, Any]


@dataclass
class CaseResult:
    id: str
    passed: bool
    status: str
    usd: float
    blocked: int
    escalations: int
    reason: str = ""


@dataclass
class EvalReport:
    cases: int
    pass_rate: float
    total_usd: float
    mean_usd: float
    blocked: int
    escalations: int
    results: list[CaseResult] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if k != "results"}


def load_dataset(path: str | Path) -> list[Case]:
    cases: list[Case] = []
    for lineno, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        row = json.loads(line)
        for key in ("id", "task", "expect"):
            if key not in row:
                raise ConfigError(f"{path}:{lineno}: missing '{key}'")
        cases.append(Case(row["id"], row["task"], row["expect"]))
    if not cases:
        raise ConfigError(f"{path}: dataset is empty")
    return cases


def _judge(result: RunResult, expect: dict[str, Any]) -> tuple[bool, str]:
    want_status = expect.get("status", "completed")
    if result.status != want_status:
        return False, f"status {result.status} != {want_status}"
    needle = expect.get("contains")
    if needle is not None and str(needle).lower() not in (result.answer or "").lower():
        return False, f"answer missing '{needle}'"
    if "max_blocked" in expect and result.blocked > expect["max_blocked"]:
        return False, f"blocked {result.blocked} > {expect['max_blocked']}"
    return True, ""


def run_eval(make_runner: Callable[[], Runner], cases: list[Case]) -> EvalReport:
    results: list[CaseResult] = []
    for case in cases:
        result = make_runner().run(case.task)
        passed, reason = _judge(result, case.expect)
        results.append(
            CaseResult(case.id, passed, result.status, result.usd, result.blocked, result.escalations, reason)
        )
    passed_count = sum(r.passed for r in results)
    total_usd = sum(r.usd for r in results)
    return EvalReport(
        cases=len(results),
        pass_rate=round(passed_count / len(results), 4),
        total_usd=round(total_usd, 6),
        mean_usd=round(total_usd / len(results), 6),
        blocked=sum(r.blocked for r in results),
        escalations=sum(r.escalations for r in results),
        results=results,
    )


def gate(report: EvalReport, *, min_pass_rate: float, max_cost_regression_pct: float,
         baseline: dict[str, Any] | None) -> list[str]:
    """Return the list of gate failures. Empty list means the gate passes."""
    failures = []
    if report.pass_rate < min_pass_rate:
        failures.append(f"pass_rate {report.pass_rate} < min {min_pass_rate}")
    if baseline and baseline.get("mean_usd", 0) > 0:
        base = baseline["mean_usd"]
        regression = (report.mean_usd - base) / base * 100
        if regression > max_cost_regression_pct:
            failures.append(
                f"mean_usd regressed {regression:.1f}% (limit {max_cost_regression_pct}%): "
                f"{report.mean_usd} vs baseline {base}"
            )
    return failures
