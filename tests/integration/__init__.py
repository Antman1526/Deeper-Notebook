"""v0.7.129 — real-SurrealDB integration tests.

Tests under this directory require a running SurrealDB instance. They
are SKIPPED by default in local `uv run pytest` runs to keep the
backend test suite hermetic (no external infrastructure required to
contribute).

To run locally:
  1. Start SurrealDB: `make database` (uses docker-compose)
  2. Run:  `SURREAL_INTEGRATION=1 uv run pytest tests/integration/ -v`

In CI:
  The `integration-surreal` job in `.github/workflows/test.yml` brings
  up SurrealDB as a service container and sets the env var.

What these tests catch (that the mocked unit tests in `tests/test_*.py`
cannot):
  * SurrealQL syntax regressions (e.g., a typo in `DELETE artifact WHERE`)
  * Schema-migration ordering issues
  * Edge-table direction inversions (in/out) at the DB level
  * Real connection-pool warmup behavior
  * Transaction-isolation behavior that mocks can't reproduce
"""
