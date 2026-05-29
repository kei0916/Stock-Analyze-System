# Comprehensive Security Audit Design

**Date:** 2026-04-21
**Scope:** Whole project security audit: Web UI/API, CLI, secret management,
external ingestion, file parsing/conversion, RAG/LLM, persistence, dependencies,
and local operational workflows.

## Goal

プロジェクト全体の攻撃面を体系的に棚卸しし、実コード・設定・運用手順・依存関係を
多角的に検証する。成果物は「脆弱性候補の列挙」ではなく、再現可能な根拠、
重大度、影響範囲、回帰テスト案、修正優先順位まで含む実行可能な監査レポートにする。

## Standards And References

- OWASP Application Security Verification Standard 5.0.0
- OWASP Top 10:2021
- OWASP Cheat Sheet Series
  - Authentication
  - Session Management
  - SSRF Prevention
  - File Upload / File Handling
  - Input Validation
  - Logging
- Python packaging / dependency security practices
- Project-specific rule: application and test commands must run through
  `scripts/infisical-run <command>` so `.env` fallback stays disabled.

## Non-Goals

- Internet-facing penetration testing against a deployed instance.
- Destructive exploitation, credential disclosure, or intentional data loss.
- Immediate code remediation during the audit phase.
- Full replacement of the current single-password Web authentication model.
- Formal compliance certification.
- Infrastructure, cloud, or OS hardening outside this repository unless a repo
  setting directly depends on it.

## Current Security Context

Recent hardening already added:

- localhost default Web bind host.
- signed session cookie with optional `Secure` flag.
- authenticated Web routes through middleware.
- in-memory atomic rate limiter for login and heavy endpoints.
- CSP and basic browser security headers.
- local static asset delivery.
- constrained WeasyPrint fetcher that allows local files under an allowed root
  and self-contained `data:` assets.
- RAG prompt guardrails that treat document text as untrusted data.
- Infisical wrapper that forces `STOCK_ANALYZE_LOAD_DOTENV=0`.

The audit must verify these controls as implemented, not assume they are
correct because the design exists.

## Threat Model

### Assets

- Infisical-managed secrets:
  `SEC_EDGAR_EMAIL`, `EDINET_API_KEY`, `FMP_API_KEY`, `WEB_PASSWORD`,
  `WEB_SESSION_SECRET`, `PAGEINDEX_API_KEY`, `OPENAI_API_KEY`.
- Authenticated Web session cookies.
- Local SQLite database and persisted analysis data.
- Filing HTML/PDF/XBRL content under `data/filings`.
- Local logs under `data/logs`.
- LLM prompts, RAG context, cached PageIndex trees, and generated analyses.
- External API quota and availability for EDINET, SEC EDGAR, FMP, Yahoo Finance,
  PageIndex/OpenAI-compatible backends.

### Adversaries

- Unauthenticated local or LAN user reaching the Web UI.
- Authenticated but careless or malicious local user.
- Malicious or malformed filing content from external sources.
- Compromised or unexpected external API response.
- Malicious prompt content embedded in filings.
- Dependency or supply-chain compromise.
- Accidental secret leakage through logs, docs, shell history, or test output.

### Trust Boundaries

- Browser to FastAPI Web app.
- Web app to service/repository layer.
- Local process to Infisical secret injection.
- Application to external HTTP APIs.
- Application to local filesystem.
- HTML/PDF/XBRL/ZIP parsers to untrusted filing content.
- RAG/PageIndex to LLM backend.
- Tests/scripts to local developer environment.

## Audit Design

### Track 0: Baseline And Evidence Control

Record branch, commit, dirty worktree, local command rules, and existing security
documents before testing. Keep audit evidence in docs and avoid logging or
printing secret values. If a command requires secrets, run it through
`scripts/infisical-run`. Plain git/file inspection commands do not need
Infisical.

Expected output:

- baseline snapshot with commit, branch, dirty files, and known unrelated changes.
- list of prior security hardening controls and their source files.

### Track 1: Attack Surface Inventory

Create a table of every externally or semi-externally reachable entry point:

- FastAPI routes under `src/stock_analyze_system/web/routes`.
- Web middleware and app factory.
- CLI commands under `src/stock_analyze_system/cli`.
- scripts under `scripts`.
- ingestion clients under `src/stock_analyze_system/ingestion`.
- PDF/HTML/XBRL/ZIP parsers and converters.
- RAG and LLM service methods.
- persistence and cache write paths.

For each entry, record:

- input source.
- authentication requirement.
- authorization assumptions.
- trust boundary crossed.
- filesystem, network, database, or LLM side effects.
- applicable OWASP categories.

### Track 2: Authentication, Session, And Access Control

Review:

- login/logout flows.
- session signing and expiration.
- cookie flags: `HttpOnly`, `Secure`, `SameSite`, `Path`, `Max-Age`.
- public path list and static path exemptions.
- unauthenticated access behavior for HTML and JSON routes.
- login brute-force protection.
- trust proxy header behavior.
- CSRF exposure on all state-changing routes.
- session fixation and logout semantics.

The audit should include route-level tests or manual probes for missing auth,
unexpected public paths, and state-changing POST requests without anti-CSRF
controls.

### Track 3: Input Validation And Injection

Review:

- SQL query construction and ORM filter paths.
- route path parameters such as `company_id`, `filing_type`, `watchlist_id`,
  `market`, `ticker`, `doc_id`, and `edinet_code`.
- form fields and JSON bodies.
- Jinja rendering and auto-escaping assumptions.
- query string error messages and redirects.
- YAML config loading.
- log message construction with attacker-controlled values.
- command or shell invocation in scripts.

The audit should distinguish true injection from safe ORM parameterization.
Potential findings need a concrete input, expected impact, and regression test.

### Track 4: File, Archive, Parser, And SSRF Controls

Review:

- `PdfConverter` URL fetch policy.
- handling of `data:`, `file:`, relative, network-path, and remote schemes.
- allowed-root enforcement and symlink/path traversal edge cases.
- EDINET ZIP extraction, ZIP slip checks, compression bomb limits, and cleanup.
- XML/XBRL parsing with `defusedxml`.
- filing storage paths and `storage_path` trust assumptions.
- PDF/PageIndex parsing of untrusted documents.

This track must verify that valid self-contained filings still work while
network access and out-of-root file reads remain blocked.

### Track 5: Secrets And Configuration

Review:

- Infisical wrapper behavior.
- `STOCK_ANALYZE_LOAD_DOTENV=0` enforcement.
- `.env` fallback behavior when not using wrapper.
- whether secret dataclass fields use `repr=False`.
- logs, exceptions, docs, tests, and CLI output for secret leakage.
- API keys sent as query parameters and whether request logging could expose them.
- checked-in files for accidental secrets or unsafe examples.
- `.infisical.json` safety for commit.

Secret values must never be printed in reports. Findings should identify the
key name and leakage path, not the value.

### Track 6: Dependency And Supply Chain

Review:

- `pyproject.toml` dependency ranges.
- `uv.lock` if present and intended to be tracked.
- editable local `pageindex` source path.
- known CVEs through dependency audit tooling when available.
- vendored/static browser assets.
- use of maintained replacements for deprecated libraries.
- transitive dependency risk from `litellm`, `weasyprint`, `pymupdf`,
  `python-multipart`, `uvicorn[standard]`, and PageIndex.

Automated tools may include `pip-audit`, `bandit`, `semgrep`, and `gitleaks`.
Installing tools or performing network-backed vulnerability lookups requires
explicit user approval if not already available locally.

### Track 7: RAG, LLM, And Prompt Injection

Review:

- prompt construction in `PageIndexService`.
- document guardrails in search, summary, and answer generation.
- context truncation and token budget controls.
- malicious filing text that attempts system prompt override, tool use, or data
  exfiltration.
- cache poisoning through stored PageIndex trees.
- excessive prompt size or repeated RAG calls causing DoS.
- LLM health check and error output for sensitive details.

Findings must avoid treating prompt guardrails as absolute security controls.
The report should classify residual risk explicitly.

### Track 8: DoS And Resource Exhaustion

Review:

- login and heavy endpoint rate limiter semantics.
- in-memory limiter limitations under multi-process deployment.
- long-running jobs and direct Web-triggered sync.
- retry/backoff behavior for external APIs.
- large filing conversion, ZIP extraction, PDF parsing, and PageIndex builds.
- SQLite variable limits and bulk upsert sizes.
- request timeout configuration for HTTP and LLM calls.
- concurrency controls around PageIndex and LLM requests.

Each DoS finding should state whether it is exploitable by unauthenticated,
authenticated, local-only, or external-content actors.

### Track 9: Logging, Error Handling, And Observability

Review:

- user-visible errors vs server logs.
- exception messages containing secrets, file paths, prompt content, or API URLs.
- log injection risks.
- coverage of authentication failure, rate limit, parser rejection, and job
  failure events.
- whether security-relevant failures are actionable without exposing sensitive
  data.

### Track 10: Persistence And Data Integrity

Review:

- uniqueness constraints and upsert conflict targets.
- transaction boundaries and rollback behavior.
- cache overwrite semantics.
- document index association with filings and companies.
- stale or poisoned analysis data.
- repository methods that may allow cross-company reads or writes.

## Severity Rubric

- **Critical:** unauthenticated remote code execution, secret disclosure, arbitrary
  file read/write, or full authentication bypass.
- **High:** authenticated or local-network path to secret disclosure, SSRF,
  persistent XSS, major data corruption, or reliable heavy-resource DoS.
- **Medium:** constrained auth/session weakness, CSRF on meaningful state change,
  limited file/path issue, prompt injection with bounded impact, or dependency
  CVE requiring plausible exposure.
- **Low:** hardening gap, information exposure with low sensitivity, weak default
  that is safe in current localhost-only assumptions, or missing defense-in-depth.
- **Info:** documentation drift, operational risk, or future production concern.

Every finding must include:

- severity.
- affected file and line reference.
- attack precondition.
- impact.
- evidence or PoC.
- recommended fix.
- regression test idea.

## Deliverables

- `docs/superpowers/specs/2026-04-21-security-audit-design.md`
  - this design spec.
- `docs/superpowers/plans/2026-04-21-security-audit.md`
  - step-by-step execution plan, produced after this spec is approved.
- `docs/security/audit-2026-04-21.md`
  - final audit report with findings and evidence.
- `docs/security/remediation-plan-2026-04-21.md`
  - prioritized fix plan grouped by P0/P1/P2.
- optional targeted tests or PoC files only after user approves remediation work.

## Execution Gates

1. Spec review gate: user reviews this document before an implementation plan is
   written.
2. Plan gate: user approves the step-by-step audit plan before broad scans or
   probes are run.
3. Tooling gate: request approval before installing tools or running commands
   that need network access.
4. Finding gate: report findings before code remediation.
5. Remediation gate: implement fixes only after priority order is approved.

## Testing And Tooling Strategy

Use a layered approach:

- static review with `rg`, source reading, and route inventory.
- targeted pytest for already-testable controls.
- local safe PoC tests for auth, CSRF, path traversal, parser rejection,
  rate limiting, and prompt injection behavior.
- dependency and secret scans where tooling is available.
- no destructive tests against real external APIs.

All app/test commands that depend on project configuration must use:

```bash
scripts/infisical-run <command>
```

Examples:

```bash
scripts/infisical-run uv run pytest tests/unit/web/test_auth.py -q
scripts/infisical-run uv run pytest -q
```

## Risks And Constraints

- The application is currently designed primarily for localhost operation. The
  audit must identify which findings become higher severity if hosted on LAN or
  the Internet.
- In-memory rate limiting is not a distributed production control.
- Prompt injection cannot be fully eliminated with prompt wording alone.
- External dependency CVE results can change over time and must be timestamped.
- Some automated scans may produce false positives; findings require manual
  validation before remediation.
- The current worktree may contain unrelated uncommitted files. Audit commits
  must add only explicitly scoped files.

## Acceptance Criteria

- The audit plan covers all major trust boundaries in this repository.
- Findings are reproducible or explicitly marked as design/operational risks.
- No secret values are printed or committed.
- `.env` is not required for any app/test command used by the audit.
- Each High or Critical finding has a concrete remediation path and regression
  test proposal.
- The final report is actionable enough to start P0/P1 fixes without repeating
  the audit.
