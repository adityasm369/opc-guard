# Controls mapping

This maps what opc-guard does to common AI risk frameworks. It is a starting point for your
own assessment. It is not a certification, and it does not replace legal or compliance review.

| Framework area | Requirement (paraphrased) | opc-guard control | Gap |
|---|---|---|---|
| NIST AI RMF: Govern | Accountable owner and documented policy | Manifest is the policy, versioned and hashed | No org-level process; the operator is the owner |
| NIST AI RMF: Map | Context and intended use recorded | `[agent].description`, manifest hash per run | No formal impact assessment |
| NIST AI RMF: Measure | Test and monitor performance | Eval dataset, pass rate, cost gate, audit `report` | Dataset coverage is up to you |
| NIST AI RMF: Manage | Controls against identified risks | Policy, approvals, limits, guards (see threat model) | Heuristic guards only |
| ISO/IEC 42001 | Operational control and records | Hash-chained audit log, run records | Not an AIMS; no management review process |
| Human oversight (EU AI Act Art. 14, where applicable) | Ability to intervene | Approval gate, kill via budget or timeout, deny-by-default | Depends on the operator reading approvals |
| Logging and traceability | Records of automated actions | Audit events for every model and tool call | Local file only; needs off-host copy |
| Data protection | Minimize and protect personal data | Redaction in logs and answers; hashes instead of raw args | Redaction is pattern-based; the model still sees raw tool data |

Before you rely on any row, verify it against the framework text and your own context.
