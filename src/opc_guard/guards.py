"""Input and output guards (FR-6).

Guards are heuristics. They reduce risk and create an audit trail; they do not
make an agent safe on their own. Enforcement comes from the policy layer and
the tool gateway (see docs/threat-model.md).
"""

from __future__ import annotations

import re

_SECRET_PATTERNS: dict[str, re.Pattern[str]] = {
    "api_key": re.compile(r"\b(?:sk-[A-Za-z0-9_\-]{16,}|AKIA[0-9A-Z]{16})\b"),
    "email": re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"),
    "card_number": re.compile(r"\b(?:\d[ -]?){13,16}\b"),
    "ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
}

_INJECTION_PATTERNS: dict[str, re.Pattern[str]] = {
    "ignore_instructions": re.compile(r"ignore\s+(?:all\s+|any\s+|the\s+)?(?:previous|prior|above)\s+instructions", re.I),
    "disregard_prompt": re.compile(r"disregard\s+(?:the\s+)?(?:system|previous|prior)\s+(?:prompt|instructions)", re.I),
    "role_override": re.compile(r"\byou\s+are\s+now\b", re.I),
    "prompt_exfiltration": re.compile(r"reveal\s+(?:your\s+)?(?:system\s+)?prompt", re.I),
    "chat_template_token": re.compile(r"<\|?(?:im_start|im_end|system)\|?>", re.I),
}


def redact(text: str) -> tuple[str, list[str]]:
    """Replace secret and PII matches with placeholders. Returns (text, kinds_found)."""
    kinds: list[str] = []
    for kind, pattern in _SECRET_PATTERNS.items():
        if pattern.search(text):
            kinds.append(kind)
            text = pattern.sub(f"[REDACTED:{kind}]", text)
    return text, kinds


def scan_injection(text: str) -> list[str]:
    """Return the names of prompt-injection patterns found in text."""
    return [kind for kind, pattern in _INJECTION_PATTERNS.items() if pattern.search(text)]
