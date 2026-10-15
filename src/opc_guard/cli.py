"""Command-line interface.

  opc-guard validate MANIFEST
  opc-guard run --agent FILE.py:build --task TEXT [--provider NAME] [--approver deny|cli|auto]
  opc-guard eval --agent FILE.py:build --dataset FILE.jsonl --manifest MANIFEST [--baseline FILE] [--out FILE] [--write-baseline FILE]
  opc-guard replay TRACE.json --agent FILE.py:build
  opc-guard audit verify AUDIT.jsonl
  opc-guard report AUDIT.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from opc_guard import __version__
from opc_guard.approvals import auto_approve, cli_approver, deny_all
from opc_guard.audit import verify
from opc_guard.errors import ConfigError, OpcGuardError
from opc_guard.evals import gate, load_dataset, run_eval
from opc_guard.loader import load_factory
from opc_guard.manifest import load_manifest
from opc_guard.providers import RecordingProvider, ReplayProvider

APPROVERS = {"deny": deny_all, "cli": cli_approver, "auto": auto_approve}


def _cmd_validate(args: argparse.Namespace) -> int:
    m = load_manifest(args.manifest)
    print(f"OK  {m.id} v{m.version}  tiers={[t.name + ':' + t.model for t in m.ladder]}")
    print(f"    budget: {m.budget.max_tokens} tokens, ${m.budget.max_usd}, {m.budget.max_steps} steps")
    print(f"    tools: {sorted(m.tools)}  scopes: {sorted(m.grants)}")
    print(f"    sha256: {m.sha256[:16]}...")
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    factory = load_factory(args.agent)
    runner = factory(provider_name=args.provider, approver=APPROVERS[args.approver], runs_dir=args.runs_dir)
    recorder = None
    if args.record:
        recorder = RecordingProvider(runner.provider)
        runner.provider = recorder
    result = runner.run(args.task)
    if recorder is not None:
        recorder.save(Path(args.record), args.task, runner.manifest.sha256)
    print(json.dumps(result.to_dict(), indent=2))
    return 0 if result.completed else 2


def _cmd_eval(args: argparse.Namespace) -> int:
    manifest = load_manifest(args.manifest)
    cases = load_dataset(args.dataset)
    factory = load_factory(args.agent)
    report = run_eval(lambda: factory(provider_name=args.provider, approver=deny_all, runs_dir=args.runs_dir), cases)
    summary = report.summary()
    baseline: dict[str, Any] | None = None
    if args.baseline:
        baseline = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    failures = gate(
        report,
        min_pass_rate=manifest.min_pass_rate,
        max_cost_regression_pct=manifest.max_cost_regression_pct,
        baseline=baseline,
    )
    for r in report.results:
        mark = "PASS" if r.passed else "FAIL"
        extra = f"  ({r.reason})" if r.reason else ""
        print(f"{mark}  {r.id:<22} status={r.status:<10} usd={r.usd:.6f} esc={r.escalations}{extra}")
    print(f"\npass_rate={report.pass_rate}  mean_usd={report.mean_usd}  total_usd={report.total_usd}  blocked={report.blocked}")
    if args.out:
        Path(args.out).write_text(
            json.dumps({**summary, "results": [r.__dict__ for r in report.results]}, indent=2),
            encoding="utf-8",
        )
    if args.write_baseline:
        Path(args.write_baseline).write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(f"baseline written: {args.write_baseline}")
    if failures:
        print("GATE FAILED:\n  - " + "\n  - ".join(failures))
        return 1
    print("GATE PASSED")
    return 0


def _cmd_replay(args: argparse.Namespace) -> int:
    trace = json.loads(Path(args.trace).read_text(encoding="utf-8"))
    factory = load_factory(args.agent)
    runner = factory(provider_name="replay", approver=deny_all, runs_dir=args.runs_dir, replay_calls=trace["calls"])
    result = runner.run(trace["task"])
    print(json.dumps(result.to_dict(), indent=2))
    return 0 if result.completed else 2


def _cmd_audit_verify(args: argparse.Namespace) -> int:
    res = verify(Path(args.path))
    if res.ok:
        print(f"OK  chain intact, {res.events} events")
        return 0
    print(f"FAIL after {res.events} valid events: {res.error}")
    return 1


def _cmd_report(args: argparse.Namespace) -> int:
    events = [json.loads(line) for line in Path(args.path).read_text(encoding="utf-8").splitlines() if line.strip()]
    counts = Counter(e["type"] for e in events)
    model_usd = sum(e["data"].get("usd", 0) for e in events if e["type"] == "model_call")
    tiers = Counter(e["data"]["tier"] for e in events if e["type"] == "model_call")
    finished = [e["data"] for e in events if e["type"] == "run_finished"]
    print(f"run: {events[0]['run_id'] if events else '?'}")
    print(f"status: {finished[-1]['status'] if finished else 'unfinished'}")
    print(f"model calls by tier: {dict(tiers)}  usd={model_usd:.6f}")
    print(f"tool denials: {counts['tool_denied']}  approvals: {counts['approval']}  guard hits: {counts['guard_hit']}")
    print(f"events: {dict(counts)}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="opc-guard", description="Policy-enforced agent runtime for a team of one.")
    p.add_argument("--version", action="version", version=f"opc-guard {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    v = sub.add_parser("validate", help="validate a manifest")
    v.add_argument("manifest")
    v.set_defaults(func=_cmd_validate)

    r = sub.add_parser("run", help="run an agent on one task")
    r.add_argument("--agent", required=True, help="file.py:function returning a Runner")
    r.add_argument("--task", required=True)
    r.add_argument("--provider", default="mock", help="mock | anthropic")
    r.add_argument("--approver", choices=sorted(APPROVERS), default="deny")
    r.add_argument("--runs-dir", default=".opc-guard/runs")
    r.add_argument("--record", help="save model outputs to a trace file for later replay")
    r.set_defaults(func=_cmd_run)

    e = sub.add_parser("eval", help="run eval dataset and apply the CI gate")
    e.add_argument("--agent", required=True)
    e.add_argument("--dataset", required=True)
    e.add_argument("--manifest", required=True)
    e.add_argument("--provider", default="mock")
    e.add_argument("--baseline")
    e.add_argument("--write-baseline")
    e.add_argument("--out")
    e.add_argument("--runs-dir", default=".opc-guard/runs")
    e.set_defaults(func=_cmd_eval)

    rp = sub.add_parser("replay", help="replay a recorded trace with no model calls")
    rp.add_argument("trace")
    rp.add_argument("--agent", required=True)
    rp.add_argument("--runs-dir", default=".opc-guard/runs")
    rp.set_defaults(func=_cmd_replay)

    a = sub.add_parser("audit", help="audit log operations")
    asub = a.add_subparsers(dest="audit_command", required=True)
    av = asub.add_parser("verify", help="verify the hash chain")
    av.add_argument("path")
    av.set_defaults(func=_cmd_audit_verify)

    rep = sub.add_parser("report", help="summarize one run's audit log")
    rep.add_argument("path")
    rep.set_defaults(func=_cmd_report)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (OpcGuardError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1 if isinstance(exc, ConfigError) else 3
