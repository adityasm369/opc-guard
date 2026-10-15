"""The orchestrator: one agent run from task to result.

Loop per step:
  1. Stop if the wall-clock or budget is exhausted.
  2. Ask the model for an action, starting at the cheapest tier and escalating
     when the output is not a valid action (FR-3).
  3. Final answer: run the output guard, return.
  4. Tool call: policy decision -> approval if needed -> execute -> guard the
     result -> feed it back to the model.

Every decision is written to the hash-chained audit log. Any failure to write
the audit log stops the run (FR-7).
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from opc_guard.approvals import Approver, deny_all, request_with_timeout
from opc_guard.audit import AuditLog
from opc_guard.budget import PRICING, Ledger
from opc_guard.errors import AuditError, ConfigError, ProviderError
from opc_guard.guards import redact, scan_injection
from opc_guard.manifest import Manifest
from opc_guard.policy import decide
from opc_guard.providers import Provider
from opc_guard.tools import ToolRegistry

DeterministicRule = Callable[[str], "str | None"]

DEFAULT_SYSTEM_PROMPT = "You are a business agent. Act only through the listed tools."


class _Stop(Exception):
    def __init__(self, status: str):
        self.status = status


@dataclass
class _Outcome:
    ok: bool
    blocked: bool
    text: str


@dataclass
class RunResult:
    run_id: str
    status: str
    answer: str | None
    tokens: int = 0
    usd: float = 0.0
    model_calls: int = 0
    escalations: int = 0
    blocked: int = 0
    steps: int = 0
    audit_path: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def completed(self) -> bool:
        return self.status == "completed"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _sha(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def _preview(text: str, limit: int = 200) -> str:
    redacted, _ = redact(text)
    return redacted[:limit]


def parse_action(text: str) -> dict[str, Any] | None:
    """Extract the first JSON object from model output and validate its shape."""
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        obj = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict):
        return None
    if obj.get("type") == "final" and isinstance(obj.get("answer"), str):
        return obj
    if obj.get("type") == "tool" and isinstance(obj.get("tool"), str):
        args = obj.get("args", {})
        if isinstance(args, dict):
            return {"type": "tool", "tool": obj["tool"], "args": args}
    return None


class Runner:
    def __init__(
        self,
        manifest: Manifest,
        tools: ToolRegistry,
        provider: Provider,
        *,
        approver: Approver = deny_all,
        deterministic: Sequence[DeterministicRule] = (),
        system_prompt: str = DEFAULT_SYSTEM_PROMPT,
        runs_dir: str | Path = ".opc-guard/runs",
        pricing: dict[str, tuple[float, float]] | None = None,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.manifest = manifest
        self.tools = tools
        self.provider = provider
        self.approver = approver
        self.deterministic = tuple(deterministic)
        self.system_prompt = system_prompt
        self.runs_dir = Path(runs_dir)
        self.pricing = pricing or PRICING
        self.clock = clock
        self._check_wiring()

    def _check_wiring(self) -> None:
        missing = [name for name in self.manifest.tools if self.tools.get(name) is None]
        if missing:
            raise ConfigError(f"manifest references tools not in registry: {missing}")
        for name, policy in self.manifest.tools.items():
            spec = self.tools.get(name)
            assert spec is not None  # the missing-tools check above already raised
            for arg in policy.limits:
                if spec.args.get(arg) not in ("int", "float"):
                    # A typo'd or non-numeric limit key would otherwise never fire,
                    # silently disabling the cap. Fail loudly at startup instead.
                    raise ConfigError(
                        f"manifest limit [tools.{name}.limits].{arg} does not match "
                        f"a numeric argument of tool '{name}' (args: {spec.args})"
                    )
        for tier in self.manifest.ladder:
            if tier.model not in self.pricing:
                raise ConfigError(f"no pricing for model '{tier.model}' (tier '{tier.name}')")

    # ------------------------------------------------------------------ public

    def run(self, task: str) -> RunResult:
        run_id = uuid.uuid4().hex[:12]
        log_path = self.runs_dir / f"{run_id}.jsonl"
        try:
            log = AuditLog(log_path, run_id)
            return self._run(task, run_id, log, log_path)
        except AuditError:
            return RunResult(run_id=run_id, status="audit_failure", answer=None)

    # ----------------------------------------------------------------- internal

    def _run(self, task: str, run_id: str, log: AuditLog, log_path: Path) -> RunResult:
        budget = Ledger(self.manifest.budget, self.pricing)
        counters = {"escalations": 0, "blocked": 0, "steps": 0}
        log.append(
            "run_started",
            {
                "agent": self.manifest.id,
                "agent_version": self.manifest.version,
                "manifest_sha256": self.manifest.sha256,
                "task_preview": _preview(task),
            },
        )

        def finish(status: str, answer: str | None) -> RunResult:
            log.append("run_finished", {"status": status, "usd": round(budget.usd, 6), "tokens": budget.tokens})
            return RunResult(
                run_id=run_id,
                status=status,
                answer=answer,
                tokens=budget.tokens,
                usd=round(budget.usd, 6),
                model_calls=budget.calls,
                escalations=counters["escalations"],
                blocked=counters["blocked"],
                steps=counters["steps"],
                audit_path=str(log_path),
            )

        for rule in self.deterministic:
            answer = rule(task)
            if answer is not None:
                log.append("deterministic_answer", {"rule": getattr(rule, "__name__", "rule")})
                return finish("completed", answer)

        transcript = [f"TASK: {task}"]
        started = self.clock()
        try:
            for _ in range(self.manifest.budget.max_steps):
                if self.clock() - started > self.manifest.budget.max_wall_seconds:
                    raise _Stop("timeout")
                exhausted = budget.exhausted()
                if exhausted:
                    raise _Stop(exhausted)
                counters["steps"] += 1
                action = self._decide(log, budget, counters, transcript)

                if action["type"] == "final":
                    answer, kinds = redact(action["answer"])
                    if kinds:
                        log.append("guard_hit", {"stage": "output", "kinds": kinds})
                    return finish("completed", answer)

                outcome = self._call_tool(log, action["tool"], action["args"])
                if outcome.blocked:
                    counters["blocked"] += 1
                transcript.append(f"ACTION: {json.dumps(action, sort_keys=True)}")
                transcript.append(f"TOOL_RESULT {action['tool']}: {outcome.text}")
            raise _Stop("max_steps_exceeded")
        except _Stop as stop:
            return finish(stop.status, None)

    def _prompt(self, transcript: list[str]) -> str:
        tool_lines = []
        for name in sorted(self.manifest.tools):
            spec = self.tools.get(name)
            if spec is None:
                continue
            sig = ", ".join(f"{k}: {v}" for k, v in spec.args.items())
            tool_lines.append(f"- {name}({sig}): {spec.description}")
        return (
            f"{self.system_prompt}\n\nAvailable tools:\n" + "\n".join(tool_lines) + "\n\n"
            'Reply with ONLY a JSON object: {"type":"tool","tool":"<name>","args":{...}} '
            'or {"type":"final","answer":"..."}.\n\n' + "\n".join(transcript)
        )

    def _decide(self, log: AuditLog, budget: Ledger, counters: dict[str, int], transcript: list[str]) -> dict[str, Any]:
        """Ask the model for the next action, escalating tiers on invalid output (FR-3)."""
        prompt = self._prompt(transcript)
        for tier in self.manifest.ladder:
            if budget.exhausted():
                raise _Stop(budget.exhausted() or "budget_exhausted")
            try:
                completion = self.provider.complete(tier.model, prompt, max_tokens=1024)
            except ProviderError as exc:
                log.append("provider_error", {"tier": tier.name, "error": str(exc)[:200]})
                raise _Stop("provider_error") from exc
            usd = budget.record(tier.model, completion.input_tokens, completion.output_tokens)
            log.append(
                "model_call",
                {
                    "tier": tier.name,
                    "model": tier.model,
                    "input_tokens": completion.input_tokens,
                    "output_tokens": completion.output_tokens,
                    "usd": round(usd, 6),
                },
            )
            action = parse_action(completion.text)
            if action is not None:
                return action
            counters["escalations"] += 1
            log.append("escalate", {"from_tier": tier.name, "reason": "invalid_action"})
        raise _Stop("escalation_exhausted")

    def _call_tool(self, log: AuditLog, name: str, args: dict[str, Any]) -> _Outcome:
        spec = self.tools.get(name)
        args_hash = _sha(args)
        log.append("tool_requested", {"tool": name, "args_sha256": args_hash, "args_preview": _preview(json.dumps(args, sort_keys=True))})

        decision = decide(self.manifest, spec, name, args)
        if not decision.allowed:
            log.append("tool_denied", {"tool": name, "reason": decision.reason})
            return _Outcome(False, True, f"DENIED: {decision.reason}")

        if decision.needs_approval:
            approved = request_with_timeout(self.approver, name, args, self.manifest.approval_timeout)
            log.append("approval", {"tool": name, "approved": approved, "args_sha256": args_hash})
            if not approved:
                log.append("tool_denied", {"tool": name, "reason": "approval not granted"})
                return _Outcome(False, True, "DENIED: approval not granted")

        assert spec is not None  # decide() already rejected unknown tools
        try:
            result = spec.fn(**args)
        except Exception as exc:  # tool bugs must not crash the run
            log.append("tool_error", {"tool": name, "error_type": type(exc).__name__})
            return _Outcome(False, False, f"ERROR: {type(exc).__name__}")

        text = str(result)
        injections = scan_injection(text)
        if injections:
            log.append("guard_hit", {"stage": "tool_result", "tool": name, "kinds": injections})
            return _Outcome(False, True, "BLOCKED: tool result matched a prompt-injection pattern")

        text, secret_kinds = redact(text)
        if secret_kinds:
            log.append("guard_hit", {"stage": "tool_result", "tool": name, "kinds": secret_kinds})
        log.append("tool_result", {"tool": name, "result_sha256": _sha(text), "ok": True})
        return _Outcome(True, False, text)
