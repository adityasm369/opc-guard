# 1. Class diagram

Static structure of `src/opc_guard/`. Shows the core domain types, the provider hierarchy,
and the evaluation types. Private helpers and internal state are omitted for clarity.

## Core domain

![01-class-diagram diagram 1](rendered/01-class-diagram-0.svg)

<details>
<summary>Mermaid source (editable)</summary>

```mermaid
%%{init: {"theme": "neutral", "themeVariables": {"fontSize": "14px"}}}%%
classDiagram
    direction LR

    class Runner {
        +Manifest manifest
        +ToolRegistry tools
        +Provider provider
        +Callable approver
        +str system_prompt
        +Path runs_dir
        +run(task) RunResult
    }

    class Manifest {
        +str id
        +str version
        +BudgetConfig budget
        +tuple~Tier~ ladder
        +frozenset~str~ grants
        +dict~str, ToolPolicy~ tools
        +float approval_timeout
        +float min_pass_rate
        +float max_cost_regression_pct
        +str sha256
    }

    class BudgetConfig {
        <<frozen dataclass>>
        +int max_tokens
        +float max_usd
        +int max_steps
        +float max_wall_seconds
    }

    class Tier {
        <<frozen dataclass>>
        +str name
        +str model
    }

    class ToolPolicy {
        <<frozen dataclass>>
        +str name
        +bool requires_approval
        +dict limits
    }

    class Ledger {
        +BudgetConfig config
        +dict pricing
        +int tokens
        +float usd
        +int calls
        +record(model, input_tokens, output_tokens) float
        +exhausted() str
    }

    class ToolRegistry {
        -dict _tools
        +register(spec) None
        +get(name) ToolSpec
        +names() list
    }

    class ToolSpec {
        <<frozen dataclass>>
        +str name
        +Callable fn
        +str side_effect
        +str scope
        +dict args
        +str description
        +validate_args(args) list
    }

    class Decision {
        <<frozen dataclass>>
        +bool allowed
        +str reason
        +bool needs_approval
    }

    class RunResult {
        +str run_id
        +str status
        +str answer
        +int tokens
        +float usd
        +int model_calls
        +int escalations
        +int blocked
        +int steps
        +str audit_path
        +bool completed
    }

    class AuditLog {
        +Path path
        +str run_id
        +int seq
        +str prev_hash
        +append(event_type, data) dict
    }

    class PolicyModule {
        <<module: policy.py>>
        +decide(manifest, spec, tool_name, args) Decision
    }

    class GuardsModule {
        <<module: guards.py>>
        +redact(text) tuple
        +scan_injection(text) list
    }

    Runner --> Manifest : reads, validated at load
    Runner o-- ToolRegistry : dispatches through
    Runner ..> Ledger : creates per run
    Runner ..> AuditLog : creates per run
    Runner ..> RunResult : returns
    Runner ..> PolicyModule : asks for decision
    Runner ..> GuardsModule : guards input and output
    Manifest *-- "1" BudgetConfig
    Manifest *-- "1..*" Tier : ladder
    Manifest *-- "0..*" ToolPolicy : tools
    ToolRegistry *-- "0..*" ToolSpec
    Ledger --> BudgetConfig : enforces
    PolicyModule ..> Decision : produces
    PolicyModule ..> ToolSpec : checks
    PolicyModule ..> Manifest : checks
```

</details>

## Providers

![01-class-diagram diagram 2](rendered/01-class-diagram-1.svg)

<details>
<summary>Mermaid source (editable)</summary>

```mermaid
%%{init: {"theme": "neutral"}}%%
classDiagram
    direction TB

    class Provider {
        <<abstract>>
        +complete(model, prompt, max_tokens) Completion
    }

    class Completion {
        <<frozen dataclass>>
        +str text
        +int input_tokens
        +int output_tokens
    }

    class MockProvider {
        -Callable responder
        +complete(model, prompt, max_tokens) Completion
    }

    class AnthropicProvider {
        +str URL
        +str API_VERSION
        -str api_key
        -float timeout
        +complete(model, prompt, max_tokens) Completion
    }

    class RecordingProvider {
        +Provider inner
        +list calls
        +complete(model, prompt, max_tokens) Completion
        +save(path, task, manifest_hash) None
    }

    class ReplayProvider {
        -list _calls
        -int _i
        +from_file(path) ReplayProvider
        +complete(model, prompt, max_tokens) Completion
    }

    Provider <|-- MockProvider
    Provider <|-- AnthropicProvider
    Provider <|-- RecordingProvider
    Provider <|-- ReplayProvider
    Provider ..> Completion : returns
    RecordingProvider o-- Provider : wraps
```

</details>

## Approvals and evaluation

![01-class-diagram diagram 3](rendered/01-class-diagram-2.svg)

<details>
<summary>Mermaid source (editable)</summary>

```mermaid
%%{init: {"theme": "neutral"}}%%
classDiagram
    direction LR

    class ApprovalFunctions {
        <<module: approvals.py>>
        +deny_all(tool, args) bool
        +auto_approve(tool, args) bool
        +cli_approver(tool, args) bool
        +request_with_timeout(approver, tool, args, timeout) bool
    }

    class Case {
        <<frozen dataclass>>
        +str id
        +str task
        +dict expect
    }

    class CaseResult {
        +str id
        +bool passed
        +str status
        +float usd
        +int blocked
        +int escalations
        +str reason
    }

    class EvalReport {
        +int cases
        +float pass_rate
        +float total_usd
        +float mean_usd
        +int blocked
        +int escalations
        +list results
        +summary() dict
    }

    class EvalModule {
        <<module: evals.py>>
        +load_dataset(path) list
        +run_eval(make_runner, cases) EvalReport
        +gate(report, min_pass_rate, max_cost_regression_pct, baseline) list
    }

    EvalReport *-- "0..*" CaseResult
    EvalModule ..> Case : loads
    EvalModule ..> EvalReport : produces
    EvalModule ..> Runner : drives
```

</details>

## Error hierarchy

![01-class-diagram diagram 4](rendered/01-class-diagram-3.svg)

<details>
<summary>Mermaid source (editable)</summary>

```mermaid
%%{init: {"theme": "neutral"}}%%
classDiagram
    direction TB

    class OpcGuardError {
        <<exception>>
    }
    class ConfigError {
        <<exception>>
    }
    class ManifestError {
        <<exception>>
        +list errors
    }
    class ProviderError {
        <<exception>>
    }
    class AuditError {
        <<exception>>
    }

    OpcGuardError <|-- ConfigError
    ConfigError <|-- ManifestError
    OpcGuardError <|-- ProviderError
    OpcGuardError <|-- AuditError
```

</details>

## Notes

- **Immutability:** `Manifest`, `Tier`, `ToolPolicy`, `BudgetConfig`, `ToolSpec`, and `Decision` are frozen. Enforces ADR-004 (no policy mutation during a run).
- **Per-run state:** `Ledger` and `AuditLog` are created inside `Runner.run()`. Each run starts with a fresh budget and a fresh hash chain.
- **Dependency direction:** the runner depends on abstractions (`Provider`, `Callable` approver). Providers never import the runner.
- **Modules shown as classes** (`PolicyModule`, `GuardsModule`, `EvalModule`, `ApprovalFunctions`) are free functions in the source. They are drawn as stereotyped classes for diagram consistency.
