# Contributing

`verdict-strategy` ships the `verdict-edge` package (`edge_mining_framework`): a feature-rule evaluator, a fee-aware expected-value gate, and Verdict provider receipts.

## Setup

Python 3.10–3.12 and [uv](https://docs.astral.sh/uv/):

```bash
uv sync --extra dev
uv run pytest -q
uv run ruff check src tests
uv run ruff format --check .
uv run mypy src
```

`tests/test_core_conformance.py` runs only when verdict-core is installed. CI installs a pinned verdict-core revision; to run it locally:

```bash
uv pip install "git+https://github.com/mrnicholasbcarter-code/verdict-core.git@55880def0e778e614f9d7e34c79a98d36eed5b15"
```

## Expectations

- Keep the evaluator and gate deterministic and free of I/O and exchange SDKs.
- Add tests for every behavior change. Use `pytest.approx` for float comparisons.
- There is no enforced coverage threshold. Current coverage is about 92% (`uv run pytest --cov=edge_mining_framework`).
- Keep README claims matched to shipped behavior.

## Pull requests

One logical change per PR, with a description of what changed and how it was verified. CI (tests on 3.10–3.12, ruff, mypy, build, compat gate) must pass.

See [SECURITY.md](SECURITY.md) to report vulnerabilities privately.
