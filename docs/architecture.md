# Architecture

## Run sequence

```
task
 │
 ├─ deterministic rules ──► answer (0 model calls)
 │
 └─ loop (max_steps, max_wall_seconds, budget)
     ├─ model: tier[0] ──invalid?──► tier[1] ──invalid?──► escalation_exhausted
     │        └─ debit budget, audit model_call
     ├─ final ──► output guard (redact) ──► completed
     └─ tool ──► policy.decide
                   ├─ deny ──► audit tool_denied, return "DENIED: ..." to model
                   ├─ needs approval ──► approver (timeout = deny) ──► audit approval
                   ├─ execute (exceptions → tool_error)
                   └─ result guard: injection → BLOCKED; secrets → redacted
                       └─ audit tool_result, feed back to model
```

Every arrow that changes state writes an audit event first. If that write fails, the run
ends with `audit_failure`.

## Modules

| Module | Responsibility |
|---|---|
| `manifest.py` | Parse, validate, and hash TOML manifests |
| `policy.py` | Pure function: tool call → allow/deny and approval need |
| `approvals.py` | Approver callables with timeouts that deny |
| `tools.py` | `ToolSpec`, registry, argument validation |
| `guards.py` | Redaction and injection pattern scanning |
| `budget.py` | Pricing table and per-run ledger |
| `audit.py` | Hash-chained JSONL writer and verifier |
| `providers.py` | Mock, Anthropic (urllib), recording, and replay providers |
| `runner.py` | Orchestration loop |
| `evals.py` | Dataset loader, judge, runner, and gate |
| `loader.py` | Loads `file.py:build` factories |
| `cli.py` | Command-line entry point |

## Decisions

- **ADR-001 Policy in code, not prompt.** The model never sees enforcement rules and cannot change them.
- **ADR-002 Fail closed.** Unknown tools, unclear approvals, exhausted budgets, and audit
  failures all stop or deny. Nothing defaults to allow.
- **ADR-003 Hash-chained audit.** Each event hashes its content and the previous hash.
- **ADR-004 Immutable manifests during a run.** The file is read once and its hash recorded.
- **ADR-005 Normalized provider results.** Every provider returns text and token counts.
  Cost is computed in one place (`budget.py`).
- **ADR-006 Standard library only.** No runtime dependencies, so the audit and policy code
  is easy to read and review.
- **ADR-007 Tool calls are never retried automatically.** A retry can repeat a side effect.
- **ADR-008 Misconfiguration fails at startup, not at enforcement time.** The runner
  refuses to start if a manifest tool is missing from the registry, a limit key does not
  name a numeric tool argument, or a tier model has no pricing. A typo must never become
  a silently disabled control.
