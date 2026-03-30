# Contributing to VeraBench

Thank you for your interest in contributing to VeraBench. This document provides guidelines and information for contributors.

## How to Contribute

### Reporting Issues

If you find a bug, incorrect test case, or have a suggestion:

1. Check the [existing issues](https://github.com/aallan/vera-bench/issues) to see if it has already been reported.
2. If not, [open a new issue](https://github.com/aallan/vera-bench/issues/new).
3. Provide as much context as possible, including problem IDs and error output where relevant.

### Adding New Problems

New benchmark problems are welcome. For each new problem, you must produce:

1. A `.vera` canonical solution in `solutions/vera/` that passes `vera check` and `vera verify`.
2. A JSON problem definition in `problems/tier{N}/` with all required fields.
3. A Python baseline in `solutions/python/`.
4. A TypeScript baseline in `solutions/typescript/`.

See [CLAUDE.md](CLAUDE.md) for problem structure, tier definitions, and Vera gotchas.

### Code Contributions

For contributions to the benchmark harness:

1. Fork the repository.
2. Create a feature branch from `main`:
   ```bash
   git checkout -b feature/your-feature-name
   ```
3. Make your changes, following the coding standards below.
4. Add or update tests as appropriate.
5. Ensure all checks pass:
   ```bash
   ruff check .
   ruff format --check .
   pytest -v
   vera-bench validate
   ```
6. Commit your changes with a clear commit message.
7. Push to your fork and open a pull request.

## Development Setup

### Prerequisites

* Python 3.11+
* Git
* [Vera](https://github.com/aallan/vera) compiler on PATH

### Installation

```bash
git clone https://github.com/aallan/vera-bench.git
cd vera-bench
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,llm]"
```

### Running Tests

```bash
pytest                          # run all tests
pytest -v                       # verbose output
pytest --cov=vera_bench         # with coverage
vera-bench validate             # validate all 50 problems
```

### Linting

```bash
ruff check .                    # lint
ruff format --check .           # format check
ruff check --select S vera_bench/  # security lint
```

## Coding Standards

### Python Code

- Python 3.11+, type hints everywhere.
- `ruff` for linting and formatting (line length 88).
- `click` for CLI, `rich` for terminal output.
- JSONL for results files.
- Subprocess calls to `vera` must have timeouts.

### Problem Definitions

- Follow the existing JSON schema (see any file in `problems/`).
- De Bruijn index notes are critical — document slot ordering in the `notes` field.
- Every canonical `.vera` solution must pass `vera check` and `vera verify`.
- Test cases must have correct expected values verified against the canonical solution.

### Commit Messages

- Use the imperative mood ("Add feature" not "Added feature").
- Keep the first line under 72 characters.
- Reference related issues with `#issue-number`.

### Pull Requests

- Keep pull requests focused on a single change.
- Update relevant documentation and tests.
- Fill in the pull request template.
- Ensure CI passes before requesting review.

## Branch Protection

The `main` branch is protected:

- Pull request required for all changes.
- CI must pass (validate, test, lint, security, dependency-audit).
- No direct pushes.

## Code of Conduct

This project follows the [Contributor Covenant Code of Conduct](CODE_OF_CONDUCT.md). By participating, you are expected to uphold this code.

## License

By contributing to VeraBench, you agree that your contributions will be licensed under the [MIT License](LICENSE).

## Questions?

If you have questions about contributing, [open an issue](https://github.com/aallan/vera-bench/issues).
