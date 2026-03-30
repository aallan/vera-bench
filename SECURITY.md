# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in VeraBench, please report it responsibly.

**Do not open a public issue.** Instead, use one of these channels:

1. **GitHub private vulnerability reporting** (preferred) — go to the [Security tab](https://github.com/aallan/vera-bench/security/advisories/new) and click "Report a vulnerability". This keeps the report within GitHub and allows coordinated disclosure.

2. **Email** — send details to **alasdair@babilim.co.uk** if you prefer.

In either case, include:

- A description of the vulnerability
- Steps to reproduce
- Any relevant code or output

You should receive a response within 72 hours. We will work with you to understand the issue and coordinate a fix before any public disclosure.

## Scope

Security issues in the following areas are in scope:

- The benchmark harness (command injection via problem definitions, path traversal)
- Subprocess execution (sandbox escape, untrusted code execution)
- API key handling (credential leaks in logs, results files, or temp directories)
- CI pipeline security (workflow injection, secret exposure)

Issues in the Vera compiler itself should be reported to the [Vera repository](https://github.com/aallan/vera/security/advisories/new).

## CI Security Practices

The project uses automated security scanning on every push and pull request:

- **`ruff check --select S vera_bench/`** (lint job) — Bandit-equivalent security rules applied to the harness source. Detects patterns such as unsafe `subprocess` use, hardcoded secrets, and insecure HTTP calls. All subprocess calls use `check=False` and `noqa: S603` annotations where the command is trusted (the `vera` binary found via `shutil.which()`).
- **`pip-audit --skip-editable`** (dependency-audit job) — Scans all installed packages against the [OSV vulnerability database](https://osv.dev) for known CVEs.
- **Gitleaks** (security job) — Full-history secret scanning on every push and PR.

### Workflow hardening

All CI jobs use least-privilege permissions (`permissions: contents: read`). The security job additionally requires `security-events: write` for GitHub advisory integration. All `actions/checkout` steps set `persist-credentials: false` to prevent the `GITHUB_TOKEN` from being stored in `.git/config` for the lifetime of the runner.
