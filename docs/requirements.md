# Requirements

The functional requirements below are the FR-numbers cited in the source docstrings
(e.g. `runner.py` implements FR-3; `audit.py` implements FR-7). Each maps to the module
that enforces it and the tests that prove it.

## Functional requirements

| ID | Requirement | Module | Key tests |
|---|---|---|---|
| FR-1 | Each agent runs under a versioned, validated, hashed TOML manifest. Invalid manifests are rejected before any run, with every problem listed at once. | `manifest.py` | `ManifestTests` |
| FR-2 | Tools are declared with a typed signature, side-effect class, and scope. Calls outside the manifest, outside granted scopes, or with invalid arguments are denied and logged. | `tools.py`, `policy.py` | `PolicyTests`, `test_unlisted_tool_denied` |
| FR-3 | Routing is cheapest-first: deterministic rules, then the smallest tier, escalating only when output is not a valid action. Escalations are recorded. | `runner.py` | `test_deterministic_rule_uses_no_model`, `test_invalid_small_output_escalates_to_large` |
| FR-4 | Tokens and dollars are debited per call from a versioned pricing table. Exhaustion stops the run; it never degrades silently. | `budget.py` | `test_token_budget_stops_run`, `test_usd_budget_stops_run` |
| FR-5 | Irreversible actions pause for explicit approval. Timeouts, exceptions, and non-True answers deny. Numeric caps bound arguments to `[0, cap]` even when approved. | `approvals.py`, `policy.py` | `ApprovalTests`, `test_limit_enforced_even_when_approved`, `test_negative_value_denied_by_limit` |
| FR-6 | Input/output guards scan for prompt-injection markers and redact secret/PII patterns. Tool results are untrusted: an injection match is blocked before the model sees it. | `guards.py`, `runner.py` | `GuardTests`, `test_injected_tool_result_is_blocked_and_not_shown_to_model` |
| FR-7 | Every run writes an append-only, hash-chained audit log: run start/end, manifest hash, each model call with cost, each tool decision, each approval, each guard hit. A failed write stops the run. | `audit.py` | `AuditTests`, `test_audit_failure_returns_status_not_exception` |
| FR-8 | An eval dataset runs against pass-rate and cost-regression thresholds from the manifest; regressions fail CI. | `evals.py` | `EvalTests`, `test_eval_gate_passes_on_shipped_support_dataset` |
| FR-9 | A run's model outputs can be recorded and replayed with zero live calls; divergence is a loud error. | `providers.py` | `ReplayTests` |
| FR-10 | CLI: `validate`, `run`, `replay`, `eval`, `audit verify`, `report`. | `cli.py` | `CliAndExamplesTests` |
| FR-11 | Wiring is checked at startup: every manifest tool exists in the registry, every limit key names a numeric argument of its tool, every tier model has pricing. A typo fails loudly instead of silently disabling a control. | `runner.py` | `test_typoed_limit_key_is_config_error`, `test_manifest_references_missing_tool_is_config_error` |

## Non-functional requirements

| Area | Requirement | How it is met |
|---|---|---|
| Security | Deny by default; fail closed on every ambiguous path; policy enforced in code the model never sees | ADR-001/002 in [architecture.md](architecture.md); [threat-model.md](threat-model.md) |
| Quality | Offline test suite covering every control; eval gate in CI | `tests/`, `.github/workflows/ci.yml` |
| Cost | Deterministic-first routing, hard budget caps, cost reported per task | `budget.py`, `runner.py`, `opc-guard report` |
| Reliability | Tool calls are never retried automatically (a retry can repeat a refund); provider errors stop the run | ADR-007 |
| Portability | Stdlib only; providers behind one interface | ADR-005/006 |
| Auditability | Hash-chained log; `audit verify` detects edits, deletions, reordering | `audit.py` |

## Out of scope (v0.1)

Hosted service, UI beyond the CLI, multi-tenant isolation, model training, compliance
certification (see [controls-mapping.md](controls-mapping.md)), and multi-provider tiers
(one provider per runner today — a local SLM and a frontier model cannot yet share a ladder).
