# Security policy

## Reporting a vulnerability

Please do not open a public issue for a security problem. Contact the maintainer privately
with a description, reproduction steps, and the affected version. Replace this paragraph
with a real contact address or a GitHub private advisory link before publishing.

## Scope

In scope: policy bypass (a denied tool call executes), approval bypass, budget bypass,
audit chain forgery or undetected edits, secret leakage through logs or answers, and
injection patterns that reach the model unflagged.

Out of scope: vulnerabilities in model providers, and risks the threat model lists as
accepted residual risk (see `docs/threat-model.md`).

## Handling secrets

Keys come from environment variables. Never commit `.env` files or put keys in manifests,
traces, or datasets. `.gitignore` excludes `.opc-guard/` and `.env`.
