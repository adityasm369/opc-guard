# Diagrams

Each file shows a pre-rendered SVG (in `rendered/`) with the editable Mermaid source in a
collapsible section beneath it. GitHub also renders the Mermaid source natively. If you
edit a source block, re-render its SVG with
[`@mermaid-js/mermaid-cli`](https://github.com/mermaid-js/mermaid-cli):
`mmdc -i diagram.mmd -o rendered/diagram.svg`.

Suggested reading order:

| # | File | Answers | Read when |
|---|---|---|---|
| 1 | [Use case diagram](02-use-case-diagram.md) | Who uses the system and for what | First — orient yourself |
| 2 | [Activity diagram](04-activity-diagram.md) | The full control flow of one run, every stop condition and denial path | You want to understand runtime behavior |
| 3 | [Sequence diagrams](03-sequence-diagram.md) | Which component talks to which, in order; plus the approval-timeout and injection security paths | You are debugging or extending the runner |
| 4 | [Class diagram](01-class-diagram.md) | The static types: core domain, providers, approvals/evals, errors | You are writing code against the library |

All four are drawn from the actual modules in `src/opc_guard/`, not from an aspirational
design. If the code and a diagram disagree, the code wins — and please fix the diagram.
