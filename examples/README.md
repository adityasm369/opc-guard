# Examples

Both examples run offline with no API key. Run them from the repo root.

## support_triage: cheap-first routing and the eval gate

```bash
python3 examples/support_triage/run.py
```

Shows three layers: a deterministic answer with no model call, a small-tier lookup, and an
escalation to the large tier for a complaint. Each task prints its status, model calls,
escalations, cost, and whether its audit chain verified.

Run the eval gate against the shipped baseline:

```bash
PYTHONPATH=src python3 -m opc_guard eval \
  --agent examples/support_triage/agent.py:build \
  --dataset examples/support_triage/dataset.jsonl \
  --manifest examples/support_triage/manifest.toml \
  --baseline examples/support_triage/baseline.json
```

## refund_agent: approvals, caps, and injection

```bash
python3 examples/refund_agent/run.py                  # default: approvals deny
python3 examples/refund_agent/run.py --approver auto  # approve everything (demo only)
python3 examples/refund_agent/run.py --approver cli   # you are prompted in the terminal
```

Four scenarios, each hitting a different control:

| Scenario | Control that fires |
|---|---|
| Read-only lookup | none; completes |
| $20 refund | approval gate (denied by default) |
| $500 refund | policy cap, which denies even when approved |
| Order 9999 with an injected note | injection guard blocks the tool result |

## Record and replay

```bash
PYTHONPATH=src python3 -m opc_guard run --agent examples/refund_agent/agent.py:build \
  --task "Where is order 1042?" --record .opc-guard/trace.json
PYTHONPATH=src python3 -m opc_guard replay .opc-guard/trace.json --agent examples/refund_agent/agent.py:build
```

Replay makes zero model calls and fails if the run diverges from the recording.

## Live models

Add `--provider anthropic` to any example and set `ANTHROPIC_API_KEY`. Prices in
`src/opc_guard/budget.py` are placeholders, so the reported `usd` figures are not real
until you update them.

Audit logs are written to `.opc-guard/runs/` in the directory you run from. Inspect one with
`PYTHONPATH=src python3 -m opc_guard report .opc-guard/runs/<id>.jsonl`.
