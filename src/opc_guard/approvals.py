"""Approval callbacks (FR-5).

An approver is any callable (tool_name, args) -> bool. Approvals time out and
deny by default. `auto_approve` exists for demos and tests only.
"""

from __future__ import annotations

import json
import threading
from typing import Any, Callable

Approver = Callable[[str, dict[str, Any]], bool]


def deny_all(tool: str, args: dict[str, Any]) -> bool:
    return False


def auto_approve(tool: str, args: dict[str, Any]) -> bool:
    """DEMO/TEST ONLY. Approves everything."""
    return True


def cli_approver(tool: str, args: dict[str, Any]) -> bool:
    answer = input(f"Approve {tool} {json.dumps(args, sort_keys=True)}? [y/N] ")
    return answer.strip().lower() in ("y", "yes")


def request_with_timeout(approver: Approver, tool: str, args: dict[str, Any], timeout: float) -> bool:
    """Ask the approver; any exception, timeout, or non-True answer means deny.

    The approver runs on a daemon thread so that one still blocked after the
    timeout (e.g. cli_approver waiting on input) can never keep the process
    from exiting. An answer arriving after the timeout is discarded: the
    denial was already recorded, and acting on a late approval would make the
    audit log disagree with what happened.
    """
    result: list[bool] = []
    done = threading.Event()

    def ask() -> None:
        try:
            result.append(approver(tool, args) is True)
        except Exception:
            result.append(False)
        finally:
            done.set()

    thread = threading.Thread(target=ask, name="opc-guard-approval", daemon=True)
    thread.start()
    if not done.wait(timeout):
        return False
    return bool(result and result[0])
