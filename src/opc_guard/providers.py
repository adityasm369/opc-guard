"""Model provider adapters (ADR-005).

A provider takes (model, prompt, max_tokens) and returns a Completion with
the text and the token counts. Adapters here:

- MockProvider: offline, deterministic, zero cost. Used by examples and tests.
- AnthropicProvider: Messages API over urllib (no SDK dependency).
- RecordingProvider / ReplayProvider: capture a run's model outputs and replay
  them later, so a run can be reproduced in CI at zero cost (FR-9).
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from opc_guard.errors import ProviderError


@dataclass(frozen=True)
class Completion:
    text: str
    input_tokens: int
    output_tokens: int


def estimate_tokens(text: str) -> int:
    """Rough estimate (~4 chars per token). Only used by the mock provider."""
    return max(1, len(text) // 4)


class Provider(ABC):
    @abstractmethod
    def complete(self, model: str, prompt: str, max_tokens: int) -> Completion: ...


class MockProvider(Provider):
    """Calls a responder function instead of a model. Use only for demos and tests."""

    def __init__(self, responder: Callable[[str, str], str]):
        self.responder = responder

    def complete(self, model: str, prompt: str, max_tokens: int) -> Completion:
        text = self.responder(model, prompt)
        return Completion(text, estimate_tokens(prompt), estimate_tokens(text))


class AnthropicProvider(Provider):
    """Anthropic Messages API. Reads ANTHROPIC_API_KEY from the environment."""

    URL = "https://api.anthropic.com/v1/messages"
    API_VERSION = "2023-06-01"

    def __init__(self, api_key: str | None = None, timeout: float = 60.0):
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ProviderError("ANTHROPIC_API_KEY is not set")
        self.timeout = timeout

    def complete(self, model: str, prompt: str, max_tokens: int) -> Completion:
        body = json.dumps(
            {"model": model, "max_tokens": max_tokens, "messages": [{"role": "user", "content": prompt}]}
        ).encode("utf-8")
        req = urllib.request.Request(
            self.URL,
            data=body,
            method="POST",
            headers={
                "content-type": "application/json",
                "x-api-key": self.api_key,
                "anthropic-version": self.API_VERSION,
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise ProviderError(f"Anthropic API returned HTTP {exc.code}") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise ProviderError(f"Anthropic API unreachable: {exc}") from exc
        text = "".join(block.get("text", "") for block in payload.get("content", []) if block.get("type") == "text")
        usage = payload.get("usage", {})
        return Completion(text, int(usage.get("input_tokens", 0)), int(usage.get("output_tokens", 0)))


class RecordingProvider(Provider):
    """Wraps another provider and keeps every call so it can be saved as a trace."""

    def __init__(self, inner: Provider):
        self.inner = inner
        self.calls: list[dict[str, Any]] = []

    def complete(self, model: str, prompt: str, max_tokens: int) -> Completion:
        result = self.inner.complete(model, prompt, max_tokens)
        self.calls.append(
            {
                "model": model,
                "text": result.text,
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
            }
        )
        return result

    def save(self, path: Path, task: str, manifest_hash: str) -> None:
        trace = {"task": task, "manifest_sha256": manifest_hash, "calls": self.calls}
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(trace, indent=2), encoding="utf-8")


class ReplayProvider(Provider):
    """Returns recorded completions in order. Fails loudly if the run diverges."""

    def __init__(self, calls: list[dict[str, Any]]):
        self._calls = list(calls)
        self._i = 0

    @classmethod
    def from_file(cls, path: Path) -> "ReplayProvider":
        return cls(json.loads(path.read_text(encoding="utf-8"))["calls"])

    def complete(self, model: str, prompt: str, max_tokens: int) -> Completion:
        if self._i >= len(self._calls):
            raise ProviderError("replay trace exhausted: run made more model calls than recorded")
        call = self._calls[self._i]
        self._i += 1
        if call["model"] != model:
            raise ProviderError(f"replay divergence at call {self._i}: expected {call['model']}, got {model}")
        return Completion(call["text"], call["input_tokens"], call["output_tokens"])
