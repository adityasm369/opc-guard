"""Eval gate, record/replay, CLI, and the shipped examples end to end."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT, FINAL_OK, manifest, registry, runner

from opc_guard.cli import main
from opc_guard.errors import ConfigError
from opc_guard.evals import Case, EvalReport, gate, load_dataset, run_eval
from opc_guard.providers import RecordingProvider, ReplayProvider
from opc_guard.runner import Runner

TOOL_READ = '{"type": "tool", "tool": "read_thing", "args": {"x": "a"}}'


class EvalTests(unittest.TestCase):
    def test_pass_rate_and_gate_failure(self):
        cases = [Case("a", "t", {}), Case("b", "t", {"contains": "zzz"})]

        def make():
            return runner(manifest(), registry(), [FINAL_OK])

        report = run_eval(make, cases)
        self.assertEqual(report.pass_rate, 0.5)
        failures = gate(report, min_pass_rate=0.9, max_cost_regression_pct=10, baseline=None)
        self.assertTrue(any("pass_rate" in f for f in failures))

    def test_cost_regression_fails_gate(self):
        report = EvalReport(cases=1, pass_rate=1.0, total_usd=2.0, mean_usd=2.0, blocked=0, escalations=0)
        failures = gate(report, min_pass_rate=0.5, max_cost_regression_pct=10, baseline={"mean_usd": 1.0})
        self.assertTrue(any("regressed" in f for f in failures))

    def test_no_baseline_means_no_cost_check(self):
        report = EvalReport(cases=1, pass_rate=1.0, total_usd=9.0, mean_usd=9.0, blocked=0, escalations=0)
        self.assertEqual(gate(report, min_pass_rate=0.5, max_cost_regression_pct=10, baseline=None), [])

    def test_empty_dataset_rejected(self):
        p = Path(tempfile.mkdtemp()) / "d.jsonl"
        p.write_text("\n")
        with self.assertRaises(ConfigError):
            load_dataset(p)

    def test_dataset_missing_field_rejected(self):
        p = Path(tempfile.mkdtemp()) / "d.jsonl"
        p.write_text(json.dumps({"id": "x", "task": "t"}) + "\n")
        with self.assertRaises(ConfigError):
            load_dataset(p)


class ReplayTests(unittest.TestCase):
    def test_record_then_replay_reproduces_outcome(self):
        from helpers import responder_from
        from opc_guard.providers import MockProvider

        rec = RecordingProvider(MockProvider(responder_from([TOOL_READ, FINAL_OK])))
        from opc_guard.approvals import deny_all

        live = Runner(manifest(), registry(), rec, runs_dir=tempfile.mkdtemp()).run("task")
        trace = Path(tempfile.mkdtemp()) / "trace.json"
        rec.save(trace, "task", "hash")

        replayed = Runner(
            manifest(), registry(), ReplayProvider.from_file(trace), runs_dir=tempfile.mkdtemp()
        ).run("task")
        self.assertEqual(live.answer, replayed.answer)
        self.assertEqual(live.model_calls, replayed.model_calls)

    def test_replay_divergence_is_an_error_not_silent(self):
        from opc_guard.errors import ProviderError

        p = ReplayProvider([{"model": "mock-large", "text": "x", "input_tokens": 1, "output_tokens": 1}])
        with self.assertRaises(ProviderError):
            p.complete("mock-small", "prompt", 10)


class CliAndExamplesTests(unittest.TestCase):
    def test_validate_example_manifest(self):
        self.assertEqual(main(["validate", str(ROOT / "examples/support_triage/manifest.toml")]), 0)

    def test_validate_bad_manifest_returns_1(self):
        p = Path(tempfile.mkdtemp()) / "bad.toml"
        p.write_text("[agent]\n")
        self.assertEqual(main(["validate", str(p)]), 1)

    def test_audit_verify_cli(self):
        r = runner(manifest(), registry(), [FINAL_OK]).run("t")
        self.assertEqual(main(["audit", "verify", r.audit_path]), 0)

    def _run_example(self, *args):
        env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
        return subprocess.run(
            [sys.executable, *args], cwd=ROOT, capture_output=True, text=True, timeout=120, env=env
        )

    def test_support_triage_example_runs_offline(self):
        proc = self._run_example("examples/support_triage/run.py", "--runs-dir", tempfile.mkdtemp())
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("We're open 9am to 6pm", proc.stdout)
        self.assertIn("Order status: shipped", proc.stdout)
        self.assertIn("escalations=1", proc.stdout)
        self.assertNotIn("BROKEN", proc.stdout)

    def test_refund_example_default_denies_and_blocks_injection(self):
        proc = self._run_example("examples/refund_agent/run.py", "--runs-dir", tempfile.mkdtemp())
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("DENIED: approval not granted", proc.stdout)
        self.assertIn("DENIED: limit exceeded", proc.stdout)
        self.assertIn("BLOCKED: tool result matched", proc.stdout)
        self.assertNotIn("issued for order 1042", proc.stdout)

    def test_refund_example_auto_approve_issues_only_within_cap(self):
        proc = self._run_example(
            "examples/refund_agent/run.py", "--approver", "auto", "--runs-dir", tempfile.mkdtemp()
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("refund R-1042-20 issued", proc.stdout)
        self.assertIn("DENIED: limit exceeded", proc.stdout)

    def test_eval_gate_passes_on_shipped_support_dataset(self):
        proc = self._run_example(
            "-m", "opc_guard", "eval",
            "--agent", "examples/support_triage/agent.py:build",
            "--dataset", "examples/support_triage/dataset.jsonl",
            "--manifest", "examples/support_triage/manifest.toml",
            "--baseline", "examples/support_triage/baseline.json",
            "--runs-dir", tempfile.mkdtemp(),
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("GATE PASSED", proc.stdout)


if __name__ == "__main__":
    unittest.main()
