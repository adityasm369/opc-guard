"""Pricing table and per-run budget ledger (FR-4).

PRICING values are USD per 1M tokens: (input, output).

IMPORTANT: the Claude entries below are PLACEHOLDERS, not real prices. Replace
them with current values from the provider's pricing page and bump
PRICING_VERSION. The mock entries are for offline demos only.
"""

from __future__ import annotations

from dataclasses import dataclass, field

PRICING_VERSION = "2026-10-01-placeholder"

PRICING: dict[str, tuple[float, float]] = {
    "claude-haiku-5-5": (1.00, 5.00),
    "claude-sonnet-5-5": (3.00, 15.00),
    "claude-opus-5-5": (15.00, 75.00),
    "mock-small": (0.10, 0.40),
    "mock-large": (3.00, 15.00),
}


@dataclass(frozen=True)
class BudgetConfig:
    max_tokens: int
    max_usd: float
    max_steps: int
    max_wall_seconds: float = 60.0


@dataclass
class Ledger:
    """Tracks spend for one run. Exhaustion stops the run; it never degrades silently."""

    config: BudgetConfig
    pricing: dict[str, tuple[float, float]] = field(default_factory=lambda: PRICING)
    tokens: int = 0
    usd: float = 0.0
    calls: int = 0

    def record(self, model: str, input_tokens: int, output_tokens: int) -> float:
        """Debit one model call. Returns the USD cost of that call."""
        if model not in self.pricing:
            raise KeyError(f"no pricing for model '{model}'")
        price_in, price_out = self.pricing[model]
        cost = (input_tokens * price_in + output_tokens * price_out) / 1_000_000
        self.tokens += input_tokens + output_tokens
        self.usd += cost
        self.calls += 1
        return cost

    def exhausted(self) -> str | None:
        """Return the name of the exhausted budget, or None if spend is still allowed."""
        if self.tokens >= self.config.max_tokens:
            return "token_budget"
        if self.usd >= self.config.max_usd:
            return "usd_budget"
        return None
