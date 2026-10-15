# 2. Use case diagram

Who uses opc-guard, and what they can do with it. The system boundary is the `opc-guard`
box. Dashed arrows show `<<include>>` (always happens) and `<<extend>>` (happens only under a condition).

## Overview

![02-use-case-diagram diagram 1](rendered/02-use-case-diagram-0.svg)

<details>
<summary>Mermaid source (editable)</summary>

```mermaid
%%{init: {"theme": "neutral", "flowchart": {"curve": "basis", "nodeSpacing": 28, "rankSpacing": 60}}}%%
flowchart LR
    %% ---------- Actors ----------
    OP["Operator<br/>(solo founder)"]
    AP["Approver<br/>(human reviewer)"]
    AU["Auditor"]
    CO["Contributor"]
    CI["CI pipeline"]
    MO["Model provider<br/>(external)"]

    %% ---------- System boundary ----------
    subgraph SYS ["opc-guard"]
        direction TB
        UC1(["Write and validate manifest"])
        UC2(["Register tools and scopes"])
        UC3(["Run agent on a task"])
        UC4(["Approve irreversible tool call"])
        UC5(["Review run report"])
        UC6(["Verify audit chain"])
        UC7(["Run eval gate"])
        UC8(["Record run trace"])
        UC9(["Replay run trace"])
        UC10(["Add provider adapter"])
        UC11(["Set budget and pricing"])

        INC1(["Enforce tool policy"])
        INC2(["Guard tool results"])
        INC3(["Debit budget"])
        INC4(["Append audit event"])
        EXT1(["Escalate to larger tier"])
    end

    %% ---------- Primary associations ----------
    OP --- UC1
    OP --- UC2
    OP --- UC3
    OP --- UC5
    OP --- UC7
    OP --- UC8
    OP --- UC9
    OP --- UC11
    AP --- UC4
    AU --- UC6
    AU --- UC5
    CO --- UC10
    CI --- UC7
    CI --- UC6
    MO --- UC3

    %% ---------- Include / extend ----------
    UC3 -.->|"include"| INC1
    UC3 -.->|"include"| INC2
    UC3 -.->|"include"| INC3
    UC3 -.->|"include"| INC4
    UC3 -.->|"extend"| EXT1
    UC3 -.->|"extend"| UC4
    UC7 -.->|"include"| UC3
    UC9 -.->|"include"| INC4

    %% ---------- Styling ----------
    classDef actor fill:#eef4ff,stroke:#3b5bdb,color:#1b2a4a,stroke-width:1.5px
    classDef uc fill:#ffffff,stroke:#495057,color:#212529,stroke-width:1.2px
    classDef inc fill:#f1f3f5,stroke:#868e96,color:#495057,stroke-dasharray:4 3
    classDef sys fill:#fafafa,stroke:#adb5bd,color:#495057
    class OP,AP,AU,CO,CI,MO actor
    class UC1,UC2,UC3,UC4,UC5,UC6,UC7,UC8,UC9,UC10,UC11,EXT1 uc
    class INC1,INC2,INC3,INC4 inc
```

</details>

## Use case specifications

| ID | Use case | Primary actor | Trigger | Outcome |
|---|---|---|---|---|
| UC1 | Write and validate manifest | Operator | New or changed agent | Manifest accepted, or every error listed at once (`opc-guard validate`) |
| UC2 | Register tools and scopes | Operator | New capability needed | Tool in registry and granted scope in manifest |
| UC3 | Run agent on a task | Operator | `opc-guard run` | `RunResult` with status, cost, blocks, and audit path |
| UC4 | Approve irreversible tool call | Approver | Tool requires approval | Approval recorded; denied on timeout |
| UC5 | Review run report | Operator, Auditor | After a run | Model calls by tier, denials, approvals, guard hits |
| UC6 | Verify audit chain | Auditor, CI | Before trusting a log | `OK` or the first broken line |
| UC7 | Run eval gate | CI, Operator | Pull request or manual | Pass or fail on pass rate and cost regression |
| UC8 | Record run trace | Operator | Debugging or reproducing | Trace file with every model output |
| UC9 | Replay run trace | Operator, CI | Reproduce without cost | Same answer with zero live model calls |
| UC10 | Add provider adapter | Contributor | New model vendor | Adapter implements `Provider.complete` |
| UC11 | Set budget and pricing | Operator | Spend policy change | Limits in manifest, prices in `budget.py` |

## Scope notes

- **Model provider** is an external actor. It is only reached through UC3 and never sees the
  tool registry or policy rules.
- **Approver** may be a person at a terminal (`cli`), an automated stub for demos (`auto`),
  or a deny-all default. Production use should always involve a person.
- **Auditor** needs read access to logs but no write access. The hash chain makes after-the-fact edits detectable.
