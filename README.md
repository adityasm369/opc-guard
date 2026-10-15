# opc-guard

A policy-enforced runtime for agents run by a team of one. Each agent is described by a
TOML manifest. Every model call and tool call goes through enforcement in code, not in the
prompt. Every decision is written to a hash-chained audit log. Spend is capped, and the
cheapest model that can do the job is tried first.

Standard library only (Python 3.11+). No API key is needed to run the examples.

## Quickstart (about 2 minutes)

```bash
git clone <this repo> opc-guard && cd opc-guard
python3 examples/support_triage/run.py     # offline, scripted models, zero cost
python3 examples/refund_agent/run.py       # shows approvals, caps, and injection blocking
python3 -m unittest discover -s tests -t tests   # 65 tests
```

Optional install, which puts `opc-guard` on your PATH:

```bash
pip install -e .
opc-guard validate examples/refund_agent/manifest.toml
```

Without installing, prefix commands with `PYTHONPATH=src`.

## Live models

```bash
export ANTHROPIC_API_KEY=...
python3 examples/support_triage/run.py --provider anthropic
python3 examples/refund_agent/run.py --provider anthropic --approver cli
```

The same manifest is used for offline and live runs. Offline, the mock imitates the tiers.

## What it enforces

| Control | Where | Behavior |
|---|---|---|
| Manifest validation | `manifest.py` | Every problem is reported at once. Invalid manifests never run. |
| Startup wiring check | `runner.py` | Manifest tools must exist, limit keys must name numeric tool args, tier models must have pricing. A typo'd limit key is a startup error, never a silently disabled cap. |
| Tool allowlist and scopes | `policy.py` | Tools not in the manifest, or with ungranted scopes, are denied. |
| Argument validation | `tools.py`, `policy.py` | Wrong types and unexpected args are denied. |
| Policy caps | `[tools.X.limits]` | Values are bounded to `[0, cap]`, even when approved. Negative values are denied too — a refund of −500 is a charge. |
| Approvals | `approvals.py` | Irreversible tools always need approval. Timeouts and errors deny. |
| Budgets | `budget.py` | Token, dollar, step, and wall-clock limits stop the run. |
| Cheap-first routing | `runner.py` | Deterministic rules first, then the small tier, escalating on invalid output. |
| Injection guard | `guards.py` | Tool results matching injection patterns are blocked and never shown to the model. |
| Secret and PII redaction | `guards.py` | Matches are redacted in tool results, final answers, and logs. |
| Audit chain | `audit.py` | Edits, deletions, and reordering are detected by `opc-guard audit verify`. |
| Eval gate | `evals.py` | Pass-rate and cost-regression thresholds fail CI. |
| Record and replay | `providers.py` | A run can be captured and replayed with zero model calls. |

The guards are heuristics. They reduce risk and leave a trail. They are not a complete
defense. See [docs/threat-model.md](docs/threat-model.md) for what is and is not covered.

## Commands

```bash
opc-guard validate MANIFEST
opc-guard run --agent FILE.py:build --task "..." [--provider mock|anthropic] [--approver deny|cli|auto] [--record TRACE.json]
opc-guard replay TRACE.json --agent FILE.py:build
opc-guard eval --agent FILE.py:build --dataset DATA.jsonl --manifest MANIFEST [--baseline B.json] [--write-baseline B.json]
opc-guard audit verify RUN.jsonl
opc-guard report RUN.jsonl
```

Exit codes: `0` ok, `1` config or gate failure, `2` run did not complete, `3` runtime or I/O error.

## Build your own agent (about 60 lines)

1. Write `manifest.toml`: budget, tiers, scopes, per-tool approval and limits. Copy
   `examples/refund_agent/manifest.toml` as a starting point.
2. In `agent.py`, register tools as `ToolSpec` objects. Pick the side effect (`read`,
   `write`, `irreversible`) and the scope honestly. Irreversible tools are always approval-gated.
3. Write a `build(provider_name, approver, runs_dir, replay_calls)` factory that returns a
   `Runner`. Copy `examples/support_triage/agent.py`.
4. Add a `dataset.jsonl` of cases, then run
   `opc-guard eval --agent agent.py:build --dataset dataset.jsonl --manifest manifest.toml`.

## Layout

```
src/opc_guard/   library: manifest, policy, runner, guards, audit, budget, providers, evals, cli
examples/        two runnable agents, each with run.py and a manifest
tests/           unittest suite (stdlib only): unit, runner behavior, eval, replay, CLI, examples
docs/            requirements, threat model, architecture, controls mapping
docs/diagrams/   UML diagrams (class, use case, sequence, activity) with rendered SVGs
```

Start with [docs/requirements.md](docs/requirements.md) for what the system guarantees,
and [docs/diagrams/](docs/diagrams/README.md) for how it works visually.

## Known limitations (read before relying on this)

- **Prices are placeholders.** `src/opc_guard/budget.py` has example numbers. Replace them
  with current provider prices before trusting any cost figure.
- **Live provider path is lightly tested.** The auth-failure path is verified. A successful
  live call has not been run in this repo. Run `--provider anthropic` once with your key.
- **Guards are heuristic.** Prompt injection in particular cannot be fully detected by pattern matching.
- **Single process, single machine.** There is no multi-tenant isolation, and the audit log
  is a local file.
- **Not a compliance certification.** See [docs/controls-mapping.md](docs/controls-mapping.md).
- **No license chosen yet.** `pyproject.toml` says `UNLICENSED` as a placeholder.

## Security

See [SECURITY.md](SECURITY.md) for how to report a vulnerability.
