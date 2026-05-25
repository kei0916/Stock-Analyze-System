# Infisical Local Command Standard (2026-04-21)

## Rule

Local project commands must run through Infisical, not repo-local `.env`.

Use the wrapper:

```bash
scripts/infisical-run <command>
```

This wrapper expands to:

```bash
env STOCK_ANALYZE_LOAD_DOTENV=0 infisical run --env=dev --path=/ -- <command>
```

It also changes to the repository root before execution, so it can be called from
subdirectories.

## Examples

Run the test suite:

```bash
scripts/infisical-run uv run pytest -q
```

Run targeted tests:

```bash
scripts/infisical-run uv run pytest tests/unit/test_config.py -q
```

Start the web app:

```bash
scripts/infisical-run uv run stock-analyze serve
```

Run a CLI command:

```bash
scripts/infisical-run uv run stock-analyze company search Apple
```

## Overrides

The wrapper defaults to Infisical environment `dev` and path `/`.

Override them only when needed:

```bash
INFISICAL_ENV=staging scripts/infisical-run uv run pytest -q
INFISICAL_PATH=/apps/backend scripts/infisical-run uv run pytest -q
```

## Compatibility

`load_config()` still supports repo-local `.env` as a backward-compatible fallback.
Normal development and operation should not rely on that fallback. The wrapper
forces `STOCK_ANALYZE_LOAD_DOTENV=0`, ignoring any inherited value, so only
Infisical-injected process environment variables are used.
