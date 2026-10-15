"""Run the support triage agent on a few demo tasks and show what happened.

Usage (from the repo root):
  python examples/support_triage/run.py                 # offline, mock models
  python examples/support_triage/run.py --provider anthropic
  python examples/support_triage/run.py --task "Where is order 3003?"
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / "src"))

from agent import build  # noqa: E402
from opc_guard.audit import verify  # noqa: E402

DEMO_TASKS = [
    "What are your opening hours?",
    "Where is order 1042?",
    "Status of order 3003 please",
    "I have a complaint, my package arrived broken",
    "Tell me a joke",
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--provider", default="mock", choices=["mock", "anthropic"])
    parser.add_argument("--task", action="append", help="task to run (repeatable); default: built-in demo set")
    parser.add_argument("--runs-dir", default=str(Path.cwd() / ".opc-guard" / "runs"))
    args = parser.parse_args()

    tasks = args.task or DEMO_TASKS
    for task in tasks:
        runner = build(provider_name=args.provider, runs_dir=args.runs_dir)
        result = runner.run(task)
        chain = verify(Path(result.audit_path)) if result.audit_path else None
        print(f"\nTASK    {task}")
        print(f"ANSWER  {result.answer}")
        print(
            f"STATUS  {result.status}  model_calls={result.model_calls}  "
            f"escalations={result.escalations}  usd={result.usd:.6f}  "
            f"audit={'intact' if chain and chain.ok else 'BROKEN'}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
