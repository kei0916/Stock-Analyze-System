# Comprehensive Security Audit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Execute a whole-project security audit that maps every major trust boundary, validates existing controls, finds exploitable weaknesses, and converts each validated weakness into an actionable remediation task with tests.

**Architecture:** The audit runs in evidence-first phases: baseline capture, attack-surface inventory, manual control review, targeted safe probes, optional automated scans, finding classification, and remediation planning. No production data is modified, no secret value is printed, and no code remediation starts until the finding report and priority order are approved.

**Tech Stack:** Python 3.10, FastAPI, SQLAlchemy async, SQLite, WeasyPrint, defusedxml, httpx, litellm, PageIndex, pytest, ruff, optional pip-audit/bandit/semgrep/gitleaks. Project commands that need config/secrets must run through `scripts/infisical-run`.

---

## Operating Rules

- Do not print or commit secret values. Refer to secrets only by key name.
- Do not use `.env` for project commands. Use `scripts/infisical-run <command>`.
- Do not run destructive payloads, real external exploitation, or real API quota-burning loops.
- Do not modify application code during this audit plan. Code fixes belong to the remediation phase after approval.
- If a scan needs network access or a missing tool installation, request approval before running it.
- Keep unrelated dirty worktree files untouched.

## Report Templates

Use these templates exactly when creating the audit deliverables.

### Finding Record Structure

```markdown
### SEC-20260421-001: Example finding title

**Severity:** Critical | High | Medium | Low | Info
**Status:** Open | Needs Reproduction | Accepted Risk | Fixed Later
**Affected Area:** Web | CLI | Secrets | Parser | RAG | Dependency | Persistence | Ops
**Affected Files:** `path/to/file.py:line`
**Attack Preconditions:** actor and access level required to trigger the issue.
**Impact:** confidentiality, integrity, availability, or operational impact.
**Evidence:** command, test, code path, or reasoning used to validate the issue.
**Root Cause:** missing validation, unsafe default, trust boundary violation, or equivalent.
**Recommended Fix:** concrete repair that removes or meaningfully reduces the risk.
**Regression Test:** exact test name or behavior to add during remediation.
**Production Notes:** how severity changes between localhost, LAN, and Internet exposure.
```

When adding a real finding, allocate the next sequential ID and replace every
example sentence with concrete evidence before committing the report.

### Remediation Task Record Structure

```markdown
### P0-1: Example remediation title

**Finding:** SEC-20260421-001
**Goal:** one sentence describing the security property restored by the fix.
**Files Expected To Change:**
- `src/path/to/file.py`
- `tests/path/to/test_file.py`

**Test First:**
- Add `tests/path/to/test_file.py::test_specific_regression`.
- Expected failure before fix: the vulnerable behavior is still observable.

**Implementation Sketch:**
- Minimal safe design change that closes the root cause.

**Verification:**
- `scripts/infisical-run uv run pytest <targeted tests> -q`
- `scripts/infisical-run uv run pytest -q` for P0/P1 security fixes.
```

When adding a real remediation task, replace the example file paths and
verification command with exact project paths and exact test selectors.

---

## Task 1: Baseline, Scope Lock, And Evidence Files

**Files:**
- Create: `docs/security/audit-2026-04-21.md`
- Create: `docs/security/remediation-plan-2026-04-21.md`
- Read: `docs/superpowers/specs/2026-04-21-security-audit-design.md`
- Read: `docs/superpowers/specs/2026-04-20-security-hardening-design.md`
- Read: `docs/superpowers/refactoring-2026-04-18/current-status-2026-04-21.md`
- Read: `docs/superpowers/refactoring-2026-04-18/infisical-local-commands.md`

- [ ] **Step 1: Capture branch and commit**

Run:

```bash
git branch --show-current
git log --oneline -5
git status --short
```

Expected: record the current branch, latest commits, and all dirty/untracked files in `docs/security/audit-2026-04-21.md`. Mark pre-existing unrelated files as out-of-scope rather than deleting or editing them.

- [ ] **Step 2: Create the audit report skeleton**

Create `docs/security/audit-2026-04-21.md` with:

```markdown
# Security Audit Report - 2026-04-21

## Baseline

- Branch:
- Commit:
- Dirty worktree:
- Command rule: application and test commands use `scripts/infisical-run`.
- Scope spec: `docs/superpowers/specs/2026-04-21-security-audit-design.md`

## Executive Summary

Pending: Tasks 2-13 have not run yet.

## Attack Surface Inventory

Pending: Task 2 has not run yet.

## Findings

No validated findings yet.

## Validation Commands

Pending: no audit commands have run yet.

## Residual Risks

Pending: triage has not run yet.
```

- [ ] **Step 3: Create the remediation report skeleton**

Create `docs/security/remediation-plan-2026-04-21.md` with:

```markdown
# Security Remediation Plan - 2026-04-21

## Priority Summary

- P0: none yet
- P1: none yet
- P2: none yet

## P0 - Immediate Fixes

No validated P0 findings yet.

## P1 - High Priority Fixes

No validated P1 findings yet.

## P2 - Defense In Depth / Operational Fixes

No validated P2 findings yet.

## Accepted Or Deferred Risks

None yet.
```

- [ ] **Step 4: Verify Infisical wrapper invariant without printing secrets**

Run:

```bash
scripts/infisical-run bash -lc 'test "$STOCK_ANALYZE_LOAD_DOTENV" = "0" && for key in SEC_EDGAR_EMAIL EDINET_API_KEY FMP_API_KEY WEB_PASSWORD WEB_SESSION_SECRET PAGEINDEX_API_KEY OPENAI_API_KEY; do test -n "${!key+x}" || { echo "$key missing"; exit 1; }; done; echo infisical-wrapper-ok'
```

Expected: `infisical-wrapper-ok`. Record only key presence, not values.

- [ ] **Step 5: Commit baseline docs**

Run:

```bash
git add docs/security/audit-2026-04-21.md docs/security/remediation-plan-2026-04-21.md
git commit -m "docs(security): start comprehensive audit evidence"
```

Expected: one docs-only commit.

---

## Task 2: Attack Surface Inventory And Trust Boundary Map

**Files:**
- Modify: `docs/security/audit-2026-04-21.md`
- Read: `src/stock_analyze_system/web/app.py`
- Read: `src/stock_analyze_system/web/routes/*.py`
- Read: `src/stock_analyze_system/cli/*.py`
- Read: `scripts/*.py`
- Read: `scripts/infisical-run`
- Read: `src/stock_analyze_system/ingestion/**/*.py`
- Read: `src/stock_analyze_system/services/**/*.py`
- Read: `src/stock_analyze_system/repositories/**/*.py`

- [ ] **Step 1: List Web routes**

Run:

```bash
rg -n "@router\\.(get|post|put|delete|patch)|APIRouter\\(" src/stock_analyze_system/web/routes src/stock_analyze_system/web/app.py
```

Expected: all FastAPI route declarations and router prefixes.

- [ ] **Step 2: List CLI entry points and scripts**

Run:

```bash
rg -n "def register_parser|async def _handle|async def handle|if __name__ == .__main__.|argparse|typer|click" src/stock_analyze_system/cli scripts
```

Expected: every CLI command handler and standalone script entry.

- [ ] **Step 3: List filesystem and network side effects**

Run:

```bash
rg -n "httpx|AsyncClient|requests|weasyprint|ZipFile|extractall|open\\(|write_text|write_bytes|unlink|mkdir|glob|Path\\(|sqlite|create_async_engine|litellm|acompletion|page_index|get_page_tokens" src scripts
```

Expected: every meaningful network, parser, filesystem, DB, and LLM side-effect candidate.

- [ ] **Step 4: Build the inventory table**

Add a table under `## Attack Surface Inventory`:

```markdown
| ID | Entry Point | Input Source | Auth Required | Trust Boundary | Side Effects | OWASP Mapping | Notes |
|---|---|---|---|---|---|---|---|
| WEB-001 | `/login` POST | Browser form password | No | Browser -> Web | session cookie, rate limiter | A07 | login brute force and session issuance |
| WEB-002 | `/jobs/sync` POST | Browser form company_id | Yes | Browser -> jobs/service/external APIs | DB, network, logs | A01/A04/A09 | heavy endpoint |
```

Expected: include all Web routes, all CLI commands, all scripts, external clients, parser/converter paths, RAG/LLM methods, and repository write paths.

- [ ] **Step 5: Commit inventory**

Run:

```bash
git add docs/security/audit-2026-04-21.md
git commit -m "docs(security): map attack surface inventory"
```

Expected: one docs-only commit.

---

## Task 3: Authentication, Session, Authorization, And CSRF Audit

**Files:**
- Modify: `docs/security/audit-2026-04-21.md`
- Modify: `docs/security/remediation-plan-2026-04-21.md`
- Read: `src/stock_analyze_system/web/auth.py`
- Read: `src/stock_analyze_system/web/app.py`
- Read: `src/stock_analyze_system/web/routes/auth.py`
- Read: `src/stock_analyze_system/web/routes/jobs.py`
- Read: `src/stock_analyze_system/web/routes/api.py`
- Read: `src/stock_analyze_system/web/routes/targets.py`
- Read: `src/stock_analyze_system/web/routes/watchlists.py`
- Read: `tests/unit/web/test_auth.py`
- Read: `tests/unit/web/test_app.py`
- Read: `tests/unit/web/test_jobs.py`
- Read: `tests/unit/web/test_api.py`

- [ ] **Step 1: Run existing auth and Web tests**

Run:

```bash
scripts/infisical-run uv run pytest tests/unit/web/test_auth.py tests/unit/web/test_app.py tests/unit/web/test_jobs.py tests/unit/web/test_api.py tests/unit/web/test_targets.py tests/unit/web/test_watchlists.py -q
```

Expected: tests pass. Record failures as audit evidence if any fail.

- [ ] **Step 2: Verify unauthenticated route protection**

Run:

```bash
rg -n "PUBLIC_PATHS|PUBLIC_PREFIXES|AuthMiddleware|require_user|Depends\\(require_user\\)|@router\\.(get|post)" src/stock_analyze_system/web
```

Expected: determine whether middleware protects every non-public route, including JSON APIs and state-changing form routes.

- [ ] **Step 3: Audit session cookie issuance and deletion**

Read `routes/auth.py` and record:

```markdown
| Control | Expected | Actual | Finding |
|---|---|---|---|
| Signed cookie | `SessionSigner` signs authenticated user |  |  |
| HttpOnly | enabled |  |  |
| Secure | configurable; required for HTTPS |  |  |
| SameSite | at least `lax` |  |  |
| Max-Age | bounded |  |  |
| Logout deletes cookie | yes |  |  |
```

Expected: if `Secure` is disabled by default, classify according to localhost-only vs production exposure.

- [ ] **Step 4: Audit rate limiter semantics**

Run:

```bash
rg -n "class InMemoryRateLimiter|try_acquire|release|_trim|heavy_rate_limiter|login_rate_limiter" src tests
```

Expected: confirm atomic acquisition, release-only-on-success login behavior, bucket pruning, and heavy endpoint non-release semantics.

- [ ] **Step 5: CSRF threat analysis for each state-changing route**

Run:

```bash
rg -n "@router\\.post|Form\\(|set_cookie|delete_cookie|SameSite|csrf|CSRF" src/stock_analyze_system/web tests/unit/web
```

Expected: list every state-changing POST and whether it has explicit CSRF token, SameSite reliance, origin/referrer checks, or no defense.

- [ ] **Step 6: Classify auth/session/CSRF findings**

For each validated issue, add a finding using the Finding Template. Likely attack classes to explicitly evaluate:

```markdown
- unauthenticated access bypass
- public-path confusion
- static path abuse
- session cookie theft impact
- session fixation
- missing CSRF token on authenticated POST
- rate-limit bypass under concurrency
- rate-limit memory growth
- proxy header spoofing when trust is enabled
```

Expected: every meaningful gap is either a finding or documented as safe with evidence.

- [ ] **Step 7: Commit auth audit evidence**

Run:

```bash
git add docs/security/audit-2026-04-21.md docs/security/remediation-plan-2026-04-21.md
git commit -m "docs(security): audit auth session and csrf controls"
```

Expected: docs-only commit.

---

## Task 4: Web Input Validation, XSS, Redirect, And Template Injection Audit

**Files:**
- Modify: `docs/security/audit-2026-04-21.md`
- Modify: `docs/security/remediation-plan-2026-04-21.md`
- Read: `src/stock_analyze_system/web/routes/*.py`
- Read: `src/stock_analyze_system/web/templates/**/*.html`
- Read: `src/stock_analyze_system/web/static/app.js`
- Read: `tests/unit/web/*.py`

- [ ] **Step 1: Find user-controlled render paths**

Run:

```bash
rg -n "render\\(|TemplateResponse|HTMLResponse|RedirectResponse|include_query_params|request\\.query_params|Form\\(|BaseModel|json\\(|innerHTML|insertAdjacentHTML|textContent|safe|tojson" src/stock_analyze_system/web
```

Expected: identify every user-controlled value that reaches HTML, redirect URLs, JavaScript, or JSON.

- [ ] **Step 2: Review templates for unsafe rendering**

Run:

```bash
rg -n "\\|safe|autoescape|script|onclick|onload|href=|src=|data-|innerHTML|hx-|x-" src/stock_analyze_system/web/templates src/stock_analyze_system/web/static
```

Expected: determine whether any variable is rendered unsafely or used in script/URL context without encoding.

- [ ] **Step 3: Check redirect and error-message reflection**

Run:

```bash
rg -n "error=|next=|redirect|RedirectResponse|include_query_params|detail=|HTTPException" src/stock_analyze_system/web/routes tests/unit/web
```

Expected: identify reflected error messages, open redirect candidates, and stack/detail leakage.

- [ ] **Step 4: Check request body and parameter limits**

Run:

```bash
rg -n "company_id|ticker|market|question|watchlist_id|description|investment_thesis|limit|years|filing_type|Form\\(|BaseModel" src/stock_analyze_system/web src/stock_analyze_system/services tests/unit/web
```

Expected: identify missing length, enum, format, and size limits for route inputs, especially RAG questions and form fields.

- [ ] **Step 5: Classify Web input findings**

Explicitly evaluate:

```markdown
- reflected XSS through query error messages
- stored XSS through company/watchlist/analysis fields
- DOM XSS through `app.js`
- open redirect
- HTML attribute injection
- unbounded request body or question length DoS
- invalid enum/path conversion behavior leaking internals
```

Expected: add findings or safe notes with file/line evidence.

- [ ] **Step 6: Commit Web input audit evidence**

Run:

```bash
git add docs/security/audit-2026-04-21.md docs/security/remediation-plan-2026-04-21.md
git commit -m "docs(security): audit web input and template controls"
```

Expected: docs-only commit.

---

## Task 5: SQL, Repository, Persistence, And Data Integrity Audit

**Files:**
- Modify: `docs/security/audit-2026-04-21.md`
- Modify: `docs/security/remediation-plan-2026-04-21.md`
- Read: `src/stock_analyze_system/repositories/*.py`
- Read: `src/stock_analyze_system/models/*.py`
- Read: `src/stock_analyze_system/models/base.py`
- Read: `src/stock_analyze_system/services/*.py`
- Read: `tests/unit/repositories/*.py`
- Read: `tests/unit/models/*.py`

- [ ] **Step 1: Find raw SQL or dynamic query construction**

Run:

```bash
rg -n "text\\(|execute\\(|select\\(|where\\(|order_by\\(|getattr\\(|filter_by\\(|sqlite_insert|on_conflict|raw|literal|f\\\".*SELECT|\\.format\\(" src/stock_analyze_system/repositories src/stock_analyze_system/services src/stock_analyze_system/models
```

Expected: distinguish safe SQLAlchemy expression construction from unsafe raw SQL or dynamic column access.

- [ ] **Step 2: Map write paths and natural keys**

Run:

```bash
rg -n "upsert|bulk_upsert|bulk_add|save_index|add_item|delete_item|register|sync|create_|remove_|delete\\(" src/stock_analyze_system/repositories src/stock_analyze_system/services tests/unit/repositories tests/unit/services
```

Expected: identify every DB write path and its uniqueness or authorization assumptions.

- [ ] **Step 3: Verify transaction boundaries**

Run:

```bash
rg -n "get_session|commit|rollback|flush|async_sessionmaker|expire_on_commit|create_async_engine" src tests
```

Expected: confirm service/CLI/Web session lifetimes and rollback behavior under exceptions.

- [ ] **Step 4: Review cross-company and cache integrity**

Manually inspect repository/service methods for:

```markdown
- fetching by primary key without company scope
- document index writes associated with wrong company/filing
- filing lookup by globally unique accession/doc_id
- stale cached index after filing content changes
- upsert conflict target mismatch
- watchlist/target write paths without ownership model
```

Expected: findings only when a realistic actor can exploit the behavior in this single-user/local app model or when production exposure changes severity.

- [ ] **Step 5: Commit persistence audit evidence**

Run:

```bash
git add docs/security/audit-2026-04-21.md docs/security/remediation-plan-2026-04-21.md
git commit -m "docs(security): audit persistence and data integrity"
```

Expected: docs-only commit.

---

## Task 6: File, Archive, XML, PDF, HTML, And SSRF Audit

**Files:**
- Modify: `docs/security/audit-2026-04-21.md`
- Modify: `docs/security/remediation-plan-2026-04-21.md`
- Read: `src/stock_analyze_system/services/pdf_converter.py`
- Read: `src/stock_analyze_system/ingestion/edinet.py`
- Read: `src/stock_analyze_system/ingestion/edinet_xbrl_parser.py`
- Read: `src/stock_analyze_system/ingestion/xbrl/parser.py`
- Read: `src/stock_analyze_system/services/pageindex_service.py`
- Read: `tests/unit/services/test_pdf_converter.py`
- Read: `tests/unit/ingestion/test_edinet.py`
- Read: `tests/unit/ingestion/test_edinet_xbrl_parser.py`

- [ ] **Step 1: Run existing parser and PDF tests**

Run:

```bash
scripts/infisical-run uv run pytest tests/unit/services/test_pdf_converter.py tests/unit/ingestion/test_edinet.py tests/unit/ingestion/test_edinet_xbrl_parser.py tests/unit/ingestion/test_sec_xbrl_parser.py tests/unit/ingestion/xbrl -q
```

Expected: tests pass. Record failures as audit evidence.

- [ ] **Step 2: Inspect URL and path handling**

Run:

```bash
rg -n "urlsplit|urlparse|as_uri|resolve\\(|relative_to|url2pathname|allowed_root|data:|file:|http:|https:|ftp:|weasyprint|URLFetcher" src tests
```

Expected: prove allowed and rejected URL classes for WeasyPrint and external clients.

- [ ] **Step 3: Inspect archive extraction and parser safety**

Run:

```bash
rg -n "ZipFile|extractall|infolist|file_size|filename|defusedxml|ElementTree|fromstring|parse\\(|xml|BeautifulSoup|lxml|PyMuPDF|fitz|PdfReader" src tests
```

Expected: identify ZIP slip, ZIP bomb, XML entity, decompression, and parser boundary controls.

- [ ] **Step 4: Evaluate exploit classes**

For each parser/converter, explicitly evaluate:

```markdown
- SSRF through external HTML assets
- local file read through `file://` and relative traversal
- symlink escape under allowed root
- network-path URL such as `//127.0.0.1/x`
- `data:` asset abuse with extremely large inline payload
- ZIP slip through absolute path and `..`
- ZIP bomb through compressed-size ratio, file count, and total uncompressed size
- XML external entity and billion laughs
- parser crash leading to persistent job failure
- leftover temporary files or sensitive extracted paths
```

Expected: add finding or safe note for each class. If current tests do not cover a class, add a remediation test proposal.

- [ ] **Step 5: Commit file/parser audit evidence**

Run:

```bash
git add docs/security/audit-2026-04-21.md docs/security/remediation-plan-2026-04-21.md
git commit -m "docs(security): audit file parser and ssrf controls"
```

Expected: docs-only commit.

---

## Task 7: External HTTP Client, API Key, Retry, And Quota Audit

**Files:**
- Modify: `docs/security/audit-2026-04-21.md`
- Modify: `docs/security/remediation-plan-2026-04-21.md`
- Read: `src/stock_analyze_system/ingestion/base.py`
- Read: `src/stock_analyze_system/ingestion/sec_edgar.py`
- Read: `src/stock_analyze_system/ingestion/edinet.py`
- Read: `src/stock_analyze_system/ingestion/fmp.py`
- Read: `src/stock_analyze_system/ingestion/yahoo_finance.py`
- Read: `tests/unit/ingestion/*.py`

- [ ] **Step 1: Inventory outbound requests**

Run:

```bash
rg -n "_get\\(|_post\\(|client\\.request|httpx\\.AsyncClient|base_url|params=|headers=|api_key|apikey|Subscription-Key|User-Agent|follow_redirects|timeout|retry|backoff" src/stock_analyze_system/ingestion src/stock_analyze_system/services tests/unit/ingestion
```

Expected: list every outbound URL, auth mechanism, timeout, retry behavior, and redirect policy.

- [ ] **Step 2: Check URL construction and SSRF risk**

Run:

```bash
rg -n "base_url|rstrip\\(\"/\"\\)|f\"\\{self\\._base_url\\}|ticker|doc_id|cik|edinet_code|security_code|query" src/stock_analyze_system/ingestion src/stock_analyze_system/services
```

Expected: determine whether user-controlled identifiers can alter host, path structure, query parameters, or redirect targets.

- [ ] **Step 3: Check secret leakage through URL/query/logs**

Run:

```bash
rg -n "apikey|Subscription-Key|api_key|SEC_EDGAR_EMAIL|EDINET_API_KEY|FMP_API_KEY|logger\\.|raise .*key|Error Message|response\\.text|response\\.json|url" src tests docs -g '!docs/security/audit-2026-04-21.md'
```

Expected: identify whether API keys can appear in logs, exceptions, test output, or report text.

- [ ] **Step 4: Evaluate exploit classes**

Explicitly evaluate:

```markdown
- attacker-controlled outbound host
- redirect to unexpected host
- query parameter injection through ticker/doc_id
- API key in URL logs or exception messages
- retry amplification after 429/503
- no circuit breaker for repeated external failures
- missing timeout on long responses
- quota exhaustion from Web jobs
```

Expected: add findings or safe notes.

- [ ] **Step 5: Commit external-client audit evidence**

Run:

```bash
git add docs/security/audit-2026-04-21.md docs/security/remediation-plan-2026-04-21.md
git commit -m "docs(security): audit external http clients"
```

Expected: docs-only commit.

---

## Task 8: Secrets, Config, Infisical, And Local Operations Audit

**Files:**
- Modify: `docs/security/audit-2026-04-21.md`
- Modify: `docs/security/remediation-plan-2026-04-21.md`
- Read: `src/stock_analyze_system/config.py`
- Read: `scripts/infisical-run`
- Read: `.infisical.json`
- Read: `config/settings.yaml`
- Read: `config/settings.yaml.example`
- Read: `docs/superpowers/refactoring-2026-04-18/infisical-local-commands.md`
- Read: `tests/unit/test_config.py`
- Read: `tests/unit/test_infisical_run_script.py`

- [ ] **Step 1: Run config and wrapper tests**

Run:

```bash
scripts/infisical-run uv run pytest tests/unit/test_config.py tests/unit/test_infisical_run_script.py -q
```

Expected: tests pass and wrapper forces dotenv off.

- [ ] **Step 2: Inspect secret loading and dataclass representation**

Run:

```bash
rg -n "repr=False|os\\.environ|getenv|_load_dotenv|STOCK_ANALYZE_LOAD_DOTENV|WEB_PASSWORD|WEB_SESSION_SECRET|EDINET_API_KEY|FMP_API_KEY|SEC_EDGAR_EMAIL|PAGEINDEX_API_KEY|OPENAI_API_KEY" src config scripts tests docs -g '!docs/security/audit-2026-04-21.md'
```

Expected: identify every secret source, fallback, and possible output path.

- [ ] **Step 3: Search for accidental secret material by key pattern only**

Run:

```bash
rg -n "(sk-[A-Za-z0-9_-]{20,}|OPENAI_API_KEY\\s*=|FMP_API_KEY\\s*=|EDINET_API_KEY\\s*=|WEB_PASSWORD\\s*=|WEB_SESSION_SECRET\\s*=|PAGEINDEX_API_KEY\\s*=|SEC_EDGAR_EMAIL\\s*=)" . -g '!data/**' -g '!.venv/**' -g '!coverage.json'
```

Expected: no real secret values. If a match exists, do not copy the value into docs; record file path and key name only.

- [ ] **Step 4: Validate command-path safety**

Run:

```bash
rg -n "uv run|python -m|stock-analyze|infisical|STOCK_ANALYZE_LOAD_DOTENV|\\.env" README.md docs scripts config pyproject.toml
```

Expected: identify docs or scripts that still instruct direct `.env` or non-Infisical app/test execution.

- [ ] **Step 5: Evaluate exploit classes**

Explicitly evaluate:

```markdown
- secret value committed in repo
- secret printed by tests or CLI
- secret included in exception or log message
- `.env` loaded accidentally despite Infisical policy
- config dataclass repr leaking secret
- checked-in `.infisical.json` contains only project metadata
- scripts bypass wrapper and run app commands with dotenv
```

Expected: add findings or safe notes.

- [ ] **Step 6: Commit secrets/config audit evidence**

Run:

```bash
git add docs/security/audit-2026-04-21.md docs/security/remediation-plan-2026-04-21.md
git commit -m "docs(security): audit secrets and config handling"
```

Expected: docs-only commit.

---

## Task 9: RAG, LLM, Prompt Injection, And Context Leakage Audit

**Files:**
- Modify: `docs/security/audit-2026-04-21.md`
- Modify: `docs/security/remediation-plan-2026-04-21.md`
- Read: `src/stock_analyze_system/services/pageindex_service.py`
- Read: `src/stock_analyze_system/services/rag_service.py`
- Read: `src/stock_analyze_system/services/llm_client.py`
- Read: `src/stock_analyze_system/services/prompts.py`
- Read: `src/stock_analyze_system/web/routes/api.py`
- Read: `src/stock_analyze_system/cli/rag.py`
- Read: `tests/unit/services/test_pageindex_service.py`
- Read: `tests/unit/services/test_rag_service.py`
- Read: `tests/unit/services/test_llm_client.py`
- Read: `tests/unit/web/test_api.py`

- [ ] **Step 1: Run existing RAG/LLM tests**

Run:

```bash
scripts/infisical-run uv run pytest tests/unit/services/test_pageindex_service.py tests/unit/services/test_rag_service.py tests/unit/services/test_llm_client.py tests/unit/web/test_api.py tests/unit/cli/test_rag_cli.py -q
```

Expected: tests pass. Record failures as audit evidence.

- [ ] **Step 2: Inventory prompts and LLM calls**

Run:

```bash
rg -n "prompt|system|user|completion\\(|acompletion|llm_acompletion|question|context|summary|guardrail|DOCUMENT_GUARDRAIL|thinking|max_tokens|temperature|api_base|base_url" src/stock_analyze_system/services src/stock_analyze_system/web/routes/api.py src/stock_analyze_system/cli/rag.py tests/unit/services
```

Expected: list every prompt construction and LLM invocation.

- [ ] **Step 3: Check context and output boundaries**

Run:

```bash
rg -n "json_dumps_ja|extract_json|extract_json_object|source_pages|source_sections|confidence|answer|analysis|save_|index_json|cache_indices|node\\[\"summary\"\\]|node\\.get\\(\"text\"" src tests
```

Expected: identify where untrusted document text is stored, summarized, cached, and returned to users.

- [ ] **Step 4: Evaluate prompt attack classes**

Explicitly evaluate:

```markdown
- malicious filing text says "ignore previous instructions"
- filing text asks model to reveal system prompt or secrets
- filing text instructs model to fabricate citations
- question asks for unrelated secret/config data
- tree search selects attacker-chosen nodes because of injected text
- summary cache stores injected instructions for later answers
- model output JSON parsing fallback selects first nodes and leaks unrelated context
- health check or error path returns backend details to UI
- unbounded question/context size causes LLM DoS
```

Expected: add findings, residual risks, and test proposals. Mark prompt guardrails as defense-in-depth, not absolute protection.

- [ ] **Step 5: Commit RAG/LLM audit evidence**

Run:

```bash
git add docs/security/audit-2026-04-21.md docs/security/remediation-plan-2026-04-21.md
git commit -m "docs(security): audit rag and llm boundaries"
```

Expected: docs-only commit.

---

## Task 10: DoS, Concurrency, Resource Exhaustion, And Runtime Limits Audit

**Files:**
- Modify: `docs/security/audit-2026-04-21.md`
- Modify: `docs/security/remediation-plan-2026-04-21.md`
- Read: `src/stock_analyze_system/web/auth.py`
- Read: `src/stock_analyze_system/web/routes/jobs.py`
- Read: `src/stock_analyze_system/web/routes/api.py`
- Read: `src/stock_analyze_system/services/job.py`
- Read: `src/stock_analyze_system/services/pageindex_service.py`
- Read: `src/stock_analyze_system/ingestion/base.py`
- Read: `src/stock_analyze_system/repositories/base.py`
- Read: `tests/benchmarks/*.py`

- [ ] **Step 1: Inventory explicit limits**

Run:

```bash
rg -n "limit|rate|timeout|max_|Semaphore|sleep|backoff|retry|window|attempt|batch_size|daily_limit|chunk|32766|to_thread|gather|create_task|wait_for" src tests config docs/superpowers/specs/2026-04-21-security-audit-design.md
```

Expected: list all explicit resource controls and missing-limit candidates.

- [ ] **Step 2: Check heavy endpoint behavior**

Run:

```bash
rg -n "heavy_rate_limiter|try_acquire|sync_company|run_daily_update|rag_ask|rag_index|build_index|ask_question|get_or_create_index" src tests
```

Expected: verify which expensive operations are rate-limited and whether rate limits are per-client, per-company, global, or in-memory only.

- [ ] **Step 3: Review parser and LLM resource ceilings**

Run:

```bash
rg -n "max_text_chars|max_tokens|max_pages|max_page|max_size|file_size|timeout|wait_for|request_timeout|Httpx|Timeout|ZipFile|write_pdf|get_page_tokens" src tests config
```

Expected: identify missing file count, inline `data:` size, PDF page count, ZIP compressed ratio, prompt length, and request body limits.

- [ ] **Step 4: Evaluate DoS attack classes**

Explicitly evaluate:

```markdown
- unauthenticated login rate-limit memory growth
- authenticated heavy endpoint repeated job execution
- multi-process bypass of in-memory limiter
- large RAG question body
- huge self-contained `data:` URL in filing HTML
- ZIP with many tiny files
- ZIP high compression ratio under total uncompressed limit
- PDF conversion CPU/memory spike
- PageIndex build monopolizes LLM/backend
- retry amplification after external API failure
- SQLite variable limit in bulk upserts
```

Expected: add findings or safe notes with exploit preconditions.

- [ ] **Step 5: Commit DoS audit evidence**

Run:

```bash
git add docs/security/audit-2026-04-21.md docs/security/remediation-plan-2026-04-21.md
git commit -m "docs(security): audit resource exhaustion risks"
```

Expected: docs-only commit.

---

## Task 11: Dependency, Supply Chain, Static Assets, And Tooling Audit

**Files:**
- Modify: `docs/security/audit-2026-04-21.md`
- Modify: `docs/security/remediation-plan-2026-04-21.md`
- Read: `pyproject.toml`
- Read: `uv.lock`
- Read: `src/stock_analyze_system/web/static/**/*`
- Read: `.infisical.json`
- Read: `.gitignore`

- [ ] **Step 1: Inspect dependency declarations**

Run:

```bash
sed -n '1,220p' pyproject.toml
test -f uv.lock && sed -n '1,80p' uv.lock || true
rg -n "pageindex|tool\\.uv\\.sources|editable|path =|dependencies =|optional-dependencies|vendor|static" pyproject.toml uv.lock src/stock_analyze_system/web/static docs
```

Expected: identify unpinned broad dependency ranges, local editable dependencies, deprecated packages, and static asset provenance.

- [ ] **Step 2: Run available local security tools without installation**

Run:

```bash
command -v pip-audit || true
command -v bandit || true
command -v semgrep || true
command -v gitleaks || true
```

Expected: list installed tools. Do not install missing tools in this task.

- [ ] **Step 3: Run installed scans only**

If `pip-audit` exists, run:

```bash
scripts/infisical-run pip-audit
```

If `bandit` exists, run:

```bash
bandit -r src scripts -x .venv
```

If `semgrep` exists, run:

```bash
semgrep --config auto src scripts
```

If `gitleaks` exists, run:

```bash
gitleaks detect --no-git --redact
```

Expected: record tool version, command, result summary, and false-positive decisions. If tools are missing, record that they were not run and add a tooling gate item.

- [ ] **Step 4: Request approval for missing high-value scans**

If one or more tools are missing, ask for approval before installation or network-backed scans. Suggested commands after approval:

```bash
pip install pip-audit bandit semgrep
scripts/infisical-run pip-audit
bandit -r src scripts -x .venv
semgrep --config auto src scripts
```

Expected: do not run these until approved.

- [ ] **Step 5: Evaluate supply-chain attack classes**

Explicitly evaluate:

```markdown
- vulnerable dependency with reachable code path
- editable local PageIndex path risk
- missing or untracked lockfile risk
- deprecated parser library risk
- browser asset provenance unknown
- package with broad version range and breaking security semantics
- secret scanner false negative due ignored paths
```

Expected: add findings or safe notes.

- [ ] **Step 6: Commit dependency audit evidence**

Run:

```bash
git add docs/security/audit-2026-04-21.md docs/security/remediation-plan-2026-04-21.md
git commit -m "docs(security): audit dependency and supply chain risks"
```

Expected: docs-only commit.

---

## Task 12: Logging, Error Handling, Observability, And Information Disclosure Audit

**Files:**
- Modify: `docs/security/audit-2026-04-21.md`
- Modify: `docs/security/remediation-plan-2026-04-21.md`
- Read: `src/stock_analyze_system/logging_config.py`
- Read: `src/stock_analyze_system/exceptions.py`
- Read: `src/stock_analyze_system/**/*.py`
- Read: `tests/unit/**/*.py`

- [ ] **Step 1: Inventory logging and exception output**

Run:

```bash
rg -n "logger\\.|logging\\.|print\\(|raise .*\\(|HTTPException\\(|detail=|logger\\.exception|logger\\.warning|logger\\.info|str\\(e\\)|repr\\(|traceback|exc_info" src scripts tests
```

Expected: identify user-visible and log-visible error paths.

- [ ] **Step 2: Check sensitive values in logs and errors**

Run:

```bash
rg -n "api_key|apikey|Subscription-Key|password|session_secret|secret|token|OPENAI_API_KEY|WEB_PASSWORD|WEB_SESSION_SECRET|EDINET_API_KEY|FMP_API_KEY|PAGEINDEX_API_KEY|SEC_EDGAR_EMAIL|url|params|prompt|context" src scripts tests docs -g '!docs/security/audit-2026-04-21.md'
```

Expected: identify accidental leakage paths. Do not copy values into docs.

- [ ] **Step 3: Evaluate observability gaps**

Explicitly evaluate:

```markdown
- authentication failures logged without secret data
- rate-limit events visible enough for investigation
- parser rejections logged safely
- job failures show generic UI error and detailed server log
- external API failures do not include keys
- LLM failures do not reveal prompts or secrets
- logs resist newline/control-character injection from input
```

Expected: add findings or safe notes.

- [ ] **Step 4: Commit logging audit evidence**

Run:

```bash
git add docs/security/audit-2026-04-21.md docs/security/remediation-plan-2026-04-21.md
git commit -m "docs(security): audit logging and disclosure risks"
```

Expected: docs-only commit.

---

## Task 13: Safe Targeted Probe Suite Design

**Files:**
- Modify: `docs/security/audit-2026-04-21.md`
- Modify: `docs/security/remediation-plan-2026-04-21.md`
- Read: `tests/unit/web/*.py`
- Read: `tests/unit/services/test_pdf_converter.py`
- Read: `tests/unit/ingestion/*.py`
- Read: `tests/unit/services/test_pageindex_service.py`

- [ ] **Step 1: Map missing regression tests**

For every validated or suspected finding, add a row:

```markdown
| Finding | Missing Test | Test File | Pre-fix Expected Failure | Fix Owner Area |
|---|---|---|---|---|
| SEC-20260421-001 | `test_specific_regression` | `tests/unit/path/test_file.py` | vulnerable behavior remains observable | Web/Auth |
```

Expected: every High/Critical and every actionable Medium has a proposed regression test.

- [ ] **Step 2: Design safe local probes for highest-risk classes**

Add probe designs for:

```markdown
- unauthenticated Web route access
- CSRF form submission without token
- reflected/stored XSS payload rendered in templates
- WeasyPrint remote URL rejection
- `file://` and symlink path escape rejection
- ZIP slip and ZIP bomb rejection
- RAG prompt injection guardrail presence
- API key not appearing in repr/log-like strings
- rate limiter atomic capacity with concurrent callers
- large request body limit behavior
```

Expected: probes are described but not implemented unless remediation is approved.

- [ ] **Step 3: Commit probe design**

Run:

```bash
git add docs/security/audit-2026-04-21.md docs/security/remediation-plan-2026-04-21.md
git commit -m "docs(security): design targeted security probes"
```

Expected: docs-only commit.

---

## Task 14: Finding Triage And Remediation Plan Completion

**Files:**
- Modify: `docs/security/audit-2026-04-21.md`
- Modify: `docs/security/remediation-plan-2026-04-21.md`

- [ ] **Step 1: Normalize findings**

Run:

```bash
rg -n "^### SEC-|Severity:|Status:|Affected Area:|Recommended Fix:|Regression Test:" docs/security/audit-2026-04-21.md
```

Expected: every finding has all required fields.

- [ ] **Step 2: Assign remediation priorities**

Use this mapping:

```markdown
- P0: Critical, or High with unauthenticated/LAN exploitability, secret exposure, arbitrary file read/write, auth bypass, reliable external-content SSRF.
- P1: High, or Medium with easy exploitability and clear production impact.
- P2: Low/Info, defense-in-depth, documentation, operational hardening, accepted localhost-only risks.
```

Expected: every finding appears in exactly one remediation bucket or accepted-risk bucket.

- [ ] **Step 3: Convert each finding to remediation tasks**

For each finding, fill the Remediation Task Template with:

```markdown
- exact source files expected to change.
- exact test file and test behavior.
- minimal implementation sketch.
- targeted verification command.
- whether full `scripts/infisical-run uv run pytest -q` is required.
```

Expected: a developer can start P0/P1 fixes without rereading the whole audit.

- [ ] **Step 4: Write executive summary**

Update `docs/security/audit-2026-04-21.md` with:

```markdown
## Executive Summary

- Total findings:
- Critical:
- High:
- Medium:
- Low:
- Info:
- Most important risk:
- First remediation recommendation:
- Commands run:
- Commands not run and why:
```

Expected: summary is specific and matches finding counts.

- [ ] **Step 5: Commit triage**

Run:

```bash
git add docs/security/audit-2026-04-21.md docs/security/remediation-plan-2026-04-21.md
git commit -m "docs(security): triage audit findings"
```

Expected: docs-only commit.

---

## Task 15: Final Verification, Review Package, And Handoff

**Files:**
- Modify: `docs/security/audit-2026-04-21.md`
- Modify: `docs/security/remediation-plan-2026-04-21.md`

- [ ] **Step 1: Run final safe verification commands**

Run:

```bash
scripts/infisical-run uv run pytest tests/unit/web/test_auth.py tests/unit/web/test_app.py tests/unit/web/test_jobs.py tests/unit/web/test_api.py tests/unit/services/test_pdf_converter.py tests/unit/ingestion/test_edinet.py tests/unit/services/test_pageindex_service.py tests/unit/test_config.py tests/unit/test_infisical_run_script.py -q
```

Expected: targeted security-relevant tests pass or failures are documented as existing issues.

- [ ] **Step 2: Run full test suite if no blocking environment issue exists**

Run:

```bash
scripts/infisical-run uv run pytest -q
```

Expected: full suite passes. If it fails for unrelated existing issues, document exact failing tests and why they are unrelated.

- [ ] **Step 3: Check report consistency**

Run:

```bash
rg -n "Pending:|No validated findings yet|TBD|TODO|Example finding title|Example remediation title|SEC-20260421-001" docs/security/audit-2026-04-21.md docs/security/remediation-plan-2026-04-21.md
```

Expected: no placeholder text remains except intentionally documented zero-finding sections.

- [ ] **Step 4: Commit final audit package**

Run:

```bash
git add docs/security/audit-2026-04-21.md docs/security/remediation-plan-2026-04-21.md
git commit -m "docs(security): finalize comprehensive audit report"
```

Expected: final docs-only commit.

- [ ] **Step 5: Present execution handoff**

Final response must include:

```markdown
- audit report path
- remediation plan path
- total finding counts by severity
- commands run
- commands skipped and why
- recommended first remediation task
- whether code remediation approval is needed
```

Expected: user can choose P0/P1 remediation execution next.

---

## Self-Review Checklist For The Executor

Before claiming the audit is complete:

- [ ] Every spec track from `2026-04-21-security-audit-design.md` maps to at least one task in this plan.
- [ ] Every major attack class listed in Tasks 3-13 is either validated as safe, recorded as a finding, or explicitly deferred with reason.
- [ ] Every High/Critical finding has a regression test proposal.
- [ ] No secret values appear in docs.
- [ ] App/test commands used `scripts/infisical-run`.
- [ ] Missing automated tools or network-gated scans are disclosed.
- [ ] The final remediation plan is actionable without re-running discovery.
