# Phase C Review Follow-up Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Phase C review で報告された 2 件の user-visible regression (P1/P2) を、DRY 化の主目的を崩さず最小差分で解消する。

**Architecture:** P1 は RAG API の `filing_type` 入力型を SEC 専用 enum から切り離し、EDINET 文字列も受け付ける互換型に戻す。P2 は `FilingService.list_filings()` の default limit を `None` に戻し、既存 caller の「全件表示」意味を回復する。どちらも service/repository の責務境界は維持し、cap や厳格型は必要な call site だけで明示する。

**Tech Stack:** FastAPI / Pydantic / Python 3.12 / pytest / pytest-asyncio。

---

## File Map

- Modify: `src/stock_analyze_system/web/routes/api.py`
  RAG API の `filing_type` 受け口を互換型へ変更し、`_require_latest_filing()` も `str` ベースに揃える。
- Modify: `src/stock_analyze_system/services/filing.py`
  `list_filings()` の default を `None` に戻す。
- Modify: `tests/unit/web/test_api.py`
  EDINET filing type の API 受理テストを追加する。
- Modify: `tests/unit/services/test_filing_service.py`
  `list_filings()` の default 引数が `None` で repo に委譲されることを固定する。
- Optional Modify: `tests/unit/cli/test_filings_cli.py`
  必要なら `list_filings()` 呼び出し引数を固定する spy test を追加する。
- Optional Modify: `src/stock_analyze_system/cli/helpers.py`, `tests/unit/cli/test_rag_cli.py`
  JP filing の RAG CLI 互換まで同じ patch で回復するなら、`--filing-type` の parser 制約も緩める。
- Modify: `docs/superpowers/refactoring-2026-04-18/phase-c-dry/report.md`
  P1/P2 follow-up 完了後に追記する。
- Modify: `docs/superpowers/refactoring-2026-04-18/master.md`
  full verification 後に Phase C を `✅ Done` に更新する。

---

### Task 1: P1 — RAG API の filing_type 互換性を回復

**Files:**
- Modify: `src/stock_analyze_system/web/routes/api.py`
- Test: `tests/unit/web/test_api.py`
- Optional Modify: `src/stock_analyze_system/cli/helpers.py`
- Optional Test: `tests/unit/cli/test_rag_cli.py`

- [ ] **Step 1: EDINET filing type を受け付ける failing test を追加**

`tests/unit/web/test_api.py` の `TestRagApi` に以下を追記:

```python
    def test_ask_accepts_edinet_filing_type(
        self, monkeypatch, auth_client, db_writer,
    ):
        mock_rag = AsyncMock()
        mock_rag.ask_question.return_value = SimpleNamespace(
            answer="JP annual report",
            source_pages=[3],
            source_sections=["Business"],
        )
        from stock_analyze_system.web.routes import api as api_module
        monkeypatch.setattr(api_module, "_get_rag_service", lambda services: mock_rag)

        async def seed():
            await db_writer(
                Company(
                    id="JP_7203", security_code="7203", name="Toyota",
                    market="TSE_PRIME", accounting_standard="IFRS",
                ),
                Filing(
                    company_id="JP_7203",
                    source="EDINET",
                    filing_type="annual_report",
                    period_type="annual",
                    fiscal_year=2024,
                    doc_id="S100TEST",
                ),
            )

        import anyio
        anyio.run(seed)

        resp = auth_client.post(
            "/api/stocks/JP_7203/rag/ask",
            json={"question": "summary?", "filing_type": "annual_report"},
        )
        assert resp.status_code == 200
        assert resp.json()["answer"] == "JP annual report"
```

- [ ] **Step 2: failing を確認**

Run: `uv run pytest tests/unit/web/test_api.py::TestRagApi::test_ask_accepts_edinet_filing_type -v`
Expected: FAIL with `422 Unprocessable Entity`

- [ ] **Step 3: `api.py` の受け口を SEC enum から切り離す**

`src/stock_analyze_system/web/routes/api.py` を以下の方針で更新:

```python
from typing import Literal, TypeAlias

RagFilingType: TypeAlias = Literal[
    "10-K", "10-Q", "20-F", "6-K",
    "annual_report", "quarterly_report",
]


class AskRequest(BaseModel):
    question: str
    filing_type: RagFilingType = "10-K"


async def _require_latest_filing(
    services: ServiceContainer, company_id: str, filing_type: str,
):
    filing = await services.filing_service.get_latest_filing(company_id, filing_type)
    ...


@router.post("/{company_id}/rag/index")
async def rag_index(
    company_id: str,
    filing_type: RagFilingType = "10-K",
    ...
):
    ...


@router.get("/{company_id}/rag/analyses")
async def rag_analyses(
    company_id: str,
    filing_type: RagFilingType = "10-K",
    ...
):
    ...
```

- [ ] **Step 4: RAG API tests を実行**

Run: `uv run pytest tests/unit/web/test_api.py -q`
Expected: PASS

- [ ] **Step 5: 追加の互換テストを入れる**

同ファイルに `rag_index` / `rag_analyses` でも `"annual_report"` を受け付ける短い test を追加:

```python
    def test_index_accepts_edinet_filing_type(...):
        ...
        resp = auth_client.post(
            "/api/stocks/JP_7203/rag/index",
            params={"filing_type": "annual_report"},
        )
        assert resp.status_code == 200

    def test_analyses_accepts_edinet_filing_type(...):
        ...
        resp = auth_client.get(
            "/api/stocks/JP_7203/rag/analyses",
            params={"filing_type": "annual_report"},
        )
        assert resp.status_code == 200
```

- [ ] **Step 6: P1 対象を再実行**

Run: `uv run pytest tests/unit/web/test_api.py::TestRagApi -q`
Expected: PASS

- [ ] **Step 7: CLI RAG parser も同一方針で直すか判断**

確認対象:

```python
# src/stock_analyze_system/cli/helpers.py
parser.add_argument(
    "--filing-type", default=FilingType.TEN_K,
    type=FilingType, choices=list(FilingType),
)
```

判断基準:
- web API のみが P1 の修正対象ならこの task では触らない
- JP filing の RAG 利用を CLI でも正式にサポートするなら、ここも `str` or 専用 choices に変更し、
  `tests/unit/cli/test_rag_cli.py` に `annual_report` の parse test を追加する

---

### Task 2: P2 — `list_filings()` の default truncation を解消

**Files:**
- Modify: `src/stock_analyze_system/services/filing.py`
- Test: `tests/unit/services/test_filing_service.py`
- Optional Test: `tests/unit/cli/test_filings_cli.py`

- [ ] **Step 1: default limit が `None` であることを示す failing test を追加**

`tests/unit/services/test_filing_service.py` に以下を追加:

```python
    async def test_list_filings_defaults_to_no_limit(self):
        repo = AsyncMock()
        repo.list_filings.return_value = []
        svc = FilingService(repo)

        await svc.list_filings("US_AAPL")

        repo.list_filings.assert_called_once_with("US_AAPL", limit=None)
```

- [ ] **Step 2: failing を確認**

Run: `uv run pytest tests/unit/services/test_filing_service.py::TestFilingService::test_list_filings_defaults_to_no_limit -v`
Expected: FAIL because actual call uses `limit=20`

- [ ] **Step 3: service default を `None` に戻す**

`src/stock_analyze_system/services/filing.py` の該当メソッドを以下に変更:

```python
    async def list_filings(self, company_id: str, limit: int | None = None):
        return await self._repo.list_filings(company_id, limit=limit)
```

- [ ] **Step 4: filing service tests を実行**

Run: `uv run pytest tests/unit/services/test_filing_service.py -q`
Expected: PASS

- [ ] **Step 5: caller regression を補強**

必要なら `tests/unit/cli/test_filings_cli.py` に spy test を追加:

```python
    async def test_list_does_not_pass_limit(self, capsys):
        svc = _make_services()
        svc.company_service.get_company.return_value = MagicMock(id="US_AAPL")
        svc.filing_service.list_filings.return_value = []
        args = argparse.Namespace(action="list", json=False, company_id="US_AAPL")

        await handle(args, svc)

        svc.filing_service.list_filings.assert_called_once_with("US_AAPL")
```

- [ ] **Step 6: P2 対象を再実行**

Run: `uv run pytest tests/unit/services/test_filing_service.py tests/unit/cli/test_filings_cli.py -q`
Expected: PASS

---

### Task 3: Follow-up verification と docs 更新

**Files:**
- Modify: `docs/superpowers/refactoring-2026-04-18/phase-c-dry/report.md`
- Modify: `docs/superpowers/refactoring-2026-04-18/master.md`

- [ ] **Step 1: 変更面の targeted tests をまとめて実行**

Run:

```bash
uv run pytest \
  tests/unit/web/test_api.py \
  tests/unit/services/test_filing_service.py \
  tests/unit/cli/test_filings_cli.py -q
```

Expected: PASS

- [ ] **Step 2: full suite を実行**

Run: `uv run pytest`
Expected: all green, or if unrelated pre-existing failures remain they are Phase C completion blocker として扱う

- [ ] **Step 3: changed files に ruff を実行**

Run:

```bash
uv run ruff check \
  src/stock_analyze_system/web/routes/api.py \
  src/stock_analyze_system/services/filing.py \
  tests/unit/web/test_api.py \
  tests/unit/services/test_filing_service.py \
  tests/unit/cli/test_filings_cli.py
```

Expected: `All checks passed!`

- [ ] **Step 4: report.md を更新**

`docs/superpowers/refactoring-2026-04-18/phase-c-dry/report.md` に以下を追記:

```markdown
### Review Follow-up: P1/P2 compatibility regressions — ✅ Done

- `web/routes/api.py` の RAG filing_type 受け口を EDINET 互換型へ変更
- `FilingService.list_filings()` の default limit を `None` に戻し、既存 caller の全件表示挙動を回復
- targeted tests / full pytest / ruff を再実施
```

- [ ] **Step 5: master.md を `✅ Done` に更新**

`docs/superpowers/refactoring-2026-04-18/master.md` の Phase C 行を以下へ変更:

```markdown
| 2 | C — 重複排除 (DRY) | 類似パターンの統合・共通ヘルパー抽出 | ✅ **Done** | [design.md](phase-c-dry/design.md) | [plan.md](phase-c-dry/plan.md) | [report.md](phase-c-dry/report.md) |
```

- [ ] **Step 6: commit**

```bash
git add \
  src/stock_analyze_system/web/routes/api.py \
  src/stock_analyze_system/services/filing.py \
  tests/unit/web/test_api.py \
  tests/unit/services/test_filing_service.py \
  tests/unit/cli/test_filings_cli.py \
  docs/superpowers/refactoring-2026-04-18/phase-c-dry/report.md \
  docs/superpowers/refactoring-2026-04-18/master.md
git commit -m "fix(phase-c): restore filing compatibility regressions"
```
