# Security Hardening Review Follow-ups Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the new web rate limiting and PDF fetch hardening production-ready by fixing the review findings at the root API/design level.

**Architecture:** Replace the split `allow()` / `add_*()` limiter API with an atomic lease-based limiter that owns admission, cleanup, and release semantics. Keep PDF hardening strict for network and out-of-root file access, but restore self-contained `data:` assets by treating them as safe inline content rather than external fetches.

**Tech Stack:** Python 3.10, FastAPI, Starlette, WeasyPrint, pytest, Ruff

---

### Task 1: Replace Split Rate-Limit API With Atomic Leases

**Files:**
- Modify: `src/stock_analyze_system/web/auth.py`
- Modify: `src/stock_analyze_system/web/routes/auth.py`
- Modify: `src/stock_analyze_system/web/routes/api.py`
- Modify: `src/stock_analyze_system/web/routes/jobs.py`
- Test: `tests/unit/web/test_auth.py`
- Test: `tests/unit/web/test_api.py`
- Test: `tests/unit/web/test_jobs.py`

- [ ] Add failing unit tests that prove:
  - parallel callers cannot both acquire capacity when `max_attempts=1`
  - expired buckets are deleted after trim
  - successful login releases only the current admission, not all historical state
- [ ] Run the new targeted tests and confirm the current implementation fails for the right reason.
- [ ] Introduce a new limiter API in `web/auth.py` built around one locked admission path.
  - `try_acquire(key) -> lease | None`
  - `release(lease) -> None`
  - cleanup of empty buckets happens inside trim/release
  - time source is injectable for deterministic tests
- [ ] Update login flow to use lease acquire/release semantics.
  - failed password keeps the lease consumed
  - successful password releases only the current lease
- [ ] Update heavy endpoints to use atomic acquire.
  - no separate `allow()` / `add_hit()` calls remain
- [ ] Run focused tests for auth, API, and jobs.
- [ ] Run Ruff on touched files.

### Task 2: Restore Safe `data:` Assets In PDF Conversion

**Files:**
- Modify: `src/stock_analyze_system/services/pdf_converter.py`
- Test: `tests/unit/services/test_pdf_converter.py`

- [ ] Add failing tests that prove:
  - `data:` URLs are allowed
  - `http:` remains blocked
  - `file:` outside `allowed_root` remains blocked
  - same-root relative assets continue to work
- [ ] Run the targeted PDF converter tests and confirm the new `data:` case fails on current code.
- [ ] Refactor the fetcher policy.
  - allow `data:` without path confinement
  - allow `file:` and relative paths only when they resolve under `allowed_root`
  - keep network-path and remote schemes rejected
- [ ] Run the focused PDF tests and Ruff on touched files.

### Task 3: Close Gaps Around Production Semantics

**Files:**
- Modify: `tests/unit/web/test_auth.py`
- Modify: `tests/unit/web/test_api.py`
- Modify: `tests/unit/web/test_jobs.py`
- Modify: `docs/superpowers/specs/2026-04-20-security-hardening-design.md`
- Modify: `docs/superpowers/refactoring-2026-04-18/current-status-2026-04-20.md`

- [ ] Extend route-level tests so they cover the new contract rather than only threshold counting.
- [ ] Update the security hardening spec to say `data:` is allowed for self-contained HTML and that the limiter uses atomic admission semantics.
- [ ] Record the review follow-up in current status with exact behavior fixed.
- [ ] Run the combined targeted test suite.
- [ ] Run `uv run pytest -q` and `uv run ruff check` for touched paths before closing out.
