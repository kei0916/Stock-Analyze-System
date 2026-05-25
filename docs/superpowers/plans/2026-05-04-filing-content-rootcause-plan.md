# Filing 本体取得 & UI 整合化 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** SEC HTML / EDINET PDF を fetch して `Filing.storage_path` を埋める `FilingContentService` を導入し、Web UI の「決算分析🔍」が選択中の filing_id をそのまま解析できるようにする。

**Architecture:** 既存の `FilingSyncService` (メタデータ sync) と並行する責務として `FilingContentService` (本体取得 + storage_path 確定) を新設。CLI `filings download` のバルクと、Web/CLI からの on-demand (`RagService._ensure_filing_content`) の両ルートで同一サービスを呼ぶ。Web API は `filing_id` を受け取れるよう改修し、フロントは選択中の filing をそのまま POST する。

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy async, httpx, pytest + pytest-httpx, weasyprint (既存), vanilla JS

**Spec:** `docs/superpowers/specs/2026-05-04-filing-content-rootcause-design.md`

---

## ファイル構造

### 新規作成
| ファイル | 責務 |
|---|---|
| `src/stock_analyze_system/services/filing_content.py` | `FilingContentService`, `FetchSummary` |
| `tests/unit/services/test_filing_content_service.py` | `FilingContentService` 単体テスト |
| `tests/integration/test_filings_download_e2e.py` | `filings download` end-to-end |

### 修正
| ファイル | 変更内容 |
|---|---|
| `src/stock_analyze_system/exceptions.py` | `ContentFetchError`, `ContentNotFoundError` 追加 (IngestionError 配下) |
| `src/stock_analyze_system/ingestion/sec_edgar.py` | `get_primary_document_url` 追加 |
| `src/stock_analyze_system/ingestion/edinet.py` | `download_pdf` 追加 |
| `src/stock_analyze_system/repositories/filing.py` | `update_storage` / `get_latest_with_content` / `get_latest_indexed` 追加 |
| `src/stock_analyze_system/services/filing.py` | `get_latest_with_content` / `get_latest_indexed` 委譲メソッド追加 |
| `src/stock_analyze_system/services/rag_service.py` | `_ensure_filing_content` ヘルパ + 4 メソッドにガード追加 + `run_full_analysis_stream` に `fetching` イベント |
| `src/stock_analyze_system/cli/container.py` | `FilingContentService` の DI 配線 + `ServiceContainer` フィールド追加 |
| `src/stock_analyze_system/cli/filings.py` | `_handle_download` を sync + fetch に拡張 |
| `src/stock_analyze_system/cli/rag.py` | `_handle_index` / `_handle_analyze` / `_handle_ask` 冒頭に進捗ログ追加 |
| `src/stock_analyze_system/web/routes/api.py` | `filing_id` 対応 + `_resolve_filing` ヘルパ + `/rag/filing_options` 改修 + `_filing_to_option` 拡張 |
| `src/stock_analyze_system/web/static/app.js` | analyze/ask が filing_id 送信、fetching イベント、未取得注記 |
| `tests/unit/ingestion/test_sec_edgar.py` | `get_primary_document_url` テスト追加 |
| `tests/unit/ingestion/test_edinet.py` | `download_pdf` テスト追加 |
| `tests/unit/repositories/test_filing_repo.py` | 3 メソッドのテスト追加 |
| `tests/unit/services/test_rag_service.py` | `_ensure_filing_content` 経路のテスト追加 |
| `tests/unit/web/test_api.py` | filing_id 解決 / filing_options のテスト追加 |

---

## Task 1: クライアント新メソッド & 例外

**Files:**
- Modify: `src/stock_analyze_system/exceptions.py`
- Modify: `src/stock_analyze_system/ingestion/sec_edgar.py`
- Modify: `src/stock_analyze_system/ingestion/edinet.py`
- Modify: `tests/unit/ingestion/test_sec_edgar.py`
- Modify: `tests/unit/ingestion/test_edinet.py`

- [ ] **Step 1.1: 例外クラス追加**

`src/stock_analyze_system/exceptions.py` の `ApiResponseError` 直後 (l.25付近) に追加:

```python
class ContentFetchError(IngestionError):
    """Filing 本体 (HTML/PDF) 取得失敗の汎用エラー。"""


class ContentNotFoundError(ContentFetchError):
    """Filing 本体が source 側に存在しない (404 等)。"""
```

`IngestionError` 派生にすることで既存のリトライ・ログハンドリングの階層と整合する。

- [ ] **Step 1.2: SecEdgarClient テストを書く**

`tests/unit/ingestion/test_sec_edgar.py` の末尾に追記:

```python
class TestGetPrimaryDocumentUrl:
    async def test_returns_full_url_for_known_accession(self, httpx_mock):
        """submissions JSON から該当 accession の primaryDocument を URL に組み立てる"""
        httpx_mock.add_response(json={
            "filings": {
                "recent": {
                    "form": ["10-K"],
                    "filingDate": ["2024-11-01"],
                    "reportDate": ["2024-09-28"],
                    "accessionNumber": ["0000320193-24-000123"],
                    "primaryDocument": ["aapl-20240928.htm"],
                    "primaryDocDescription": ["10-K"],
                },
                "files": [],
            },
        })
        async with SecEdgarClient(email="t@example.com", rate=100) as client:
            url = await client.get_primary_document_url(
                "0000320193", "0000320193-24-000123",
            )
        assert url == (
            "https://www.sec.gov/Archives/edgar/data/320193/"
            "000032019324000123/aapl-20240928.htm"
        )

    async def test_raises_when_accession_not_found(self, httpx_mock):
        httpx_mock.add_response(json={
            "filings": {
                "recent": {
                    "form": ["10-K"], "filingDate": ["2024-11-01"],
                    "reportDate": ["2024-09-28"],
                    "accessionNumber": ["0000320193-24-000123"],
                    "primaryDocument": ["aapl-20240928.htm"],
                    "primaryDocDescription": ["10-K"],
                },
                "files": [],
            },
        })
        async with SecEdgarClient(email="t@example.com", rate=100) as client:
            with pytest.raises(ValueError, match="not found"):
                await client.get_primary_document_url(
                    "0000320193", "9999999999-99-999999",
                )
```

`SecEdgarClient` import が既にあること、`pytest` import が既にあることを確認 (なければ追記)。

- [ ] **Step 1.3: テストを実行して失敗することを確認**

```bash
uv run python -m pytest tests/unit/ingestion/test_sec_edgar.py::TestGetPrimaryDocumentUrl -v
```

Expected: `AttributeError: 'SecEdgarClient' object has no attribute 'get_primary_document_url'`

- [ ] **Step 1.4: SecEdgarClient.get_primary_document_url を実装**

`src/stock_analyze_system/ingestion/sec_edgar.py` の `search_efts` メソッド直前あたりに追加:

```python
async def get_primary_document_url(self, cik: str, accession_no: str) -> str:
    """submissions JSON から指定 accession の primaryDocument の完全 URL を返す。

    Raises:
        ValueError: 該当 accession_no が submissions に存在しない場合。
    """
    cik_padded = cik.zfill(10)
    data = await self.get_submissions(cik_padded)
    recent = data.get("filings", {}).get("recent", {})
    accessions = recent.get("accessionNumber", [])
    primary_docs = recent.get("primaryDocument", [])
    cik_num = cik_padded.lstrip("0") or "0"
    for acc, doc in zip(accessions, primary_docs):
        if acc == accession_no:
            acc_clean = acc.replace("-", "")
            return (
                f"https://www.sec.gov/Archives/edgar/data/"
                f"{cik_num}/{acc_clean}/{doc}"
            )
    raise ValueError(
        f"accession {accession_no} not found in submissions for CIK {cik_padded}",
    )
```

- [ ] **Step 1.5: テストを実行して通ることを確認**

```bash
uv run python -m pytest tests/unit/ingestion/test_sec_edgar.py::TestGetPrimaryDocumentUrl -v
```

Expected: 2 tests PASS

- [ ] **Step 1.6: EdinetClient テストを書く**

`tests/unit/ingestion/test_edinet.py` の末尾に追記:

```python
class TestDownloadPdf:
    async def test_raises_without_api_key(self):
        async with EdinetClient(api_key="") as client:
            with pytest.raises(ValueError, match="API key"):
                await client.download_pdf("S100TEST")

    async def test_returns_pdf_bytes(self, httpx_mock):
        pdf_bytes = b"%PDF-1.7 fake pdf body"
        httpx_mock.add_response(content=pdf_bytes)

        async with EdinetClient(api_key="test_key") as client:
            result = await client.download_pdf("S100TEST")

        assert result == pdf_bytes

    async def test_uses_type_2_param(self, httpx_mock):
        httpx_mock.add_response(content=b"x")

        async with EdinetClient(api_key="test_key") as client:
            await client.download_pdf("S100TEST")

        request = httpx_mock.get_requests()[0]
        assert request.url.params.get("type") == "2"
        assert request.url.params.get("Subscription-Key") == "test_key"
```

- [ ] **Step 1.7: テストを実行して失敗することを確認**

```bash
uv run python -m pytest tests/unit/ingestion/test_edinet.py::TestDownloadPdf -v
```

Expected: `AttributeError: 'EdinetClient' object has no attribute 'download_pdf'`

- [ ] **Step 1.8: EdinetClient.download_pdf を実装**

`src/stock_analyze_system/ingestion/edinet.py` の `download_xbrl_zip` の直後に追加:

```python
async def download_pdf(self, doc_id: str) -> bytes:
    """EDINET 書類本文を PDF (type=2) としてバイト列で取得する。

    Raises:
        ValueError: API key 未設定の場合。
        httpx.HTTPStatusError: 404 / その他のステータスエラー (呼び出し側で
            ContentNotFoundError へ変換する想定)。
    """
    if not self._api_key:
        raise ValueError("EDINET API key is required for document download")

    url = f"{self._base_url}/documents/{doc_id}"
    params = {"type": 2, "Subscription-Key": self._api_key}
    resp = await self._get(url, params=params)
    return resp.content
```

- [ ] **Step 1.9: テストを実行して通ることを確認**

```bash
uv run python -m pytest tests/unit/ingestion/test_edinet.py::TestDownloadPdf -v
```

Expected: 3 tests PASS

- [ ] **Step 1.10: 既存テストへの回帰がないことを確認**

```bash
uv run python -m pytest tests/unit/ingestion/ tests/unit/test_exceptions.py -v
```

Expected: 全て PASS

- [ ] **Step 1.11: コミット**

```bash
git add src/stock_analyze_system/exceptions.py \
        src/stock_analyze_system/ingestion/sec_edgar.py \
        src/stock_analyze_system/ingestion/edinet.py \
        tests/unit/ingestion/test_sec_edgar.py \
        tests/unit/ingestion/test_edinet.py
git commit -m "feat(ingestion): add primary doc URL lookup, EDINET PDF download, content errors"
```

---

## Task 2: FilingRepository 新メソッド

**Files:**
- Modify: `src/stock_analyze_system/repositories/filing.py`
- Modify: `src/stock_analyze_system/services/filing.py`
- Modify: `tests/unit/repositories/test_filing_repo.py`

- [ ] **Step 2.1: テストを書く**

`tests/unit/repositories/test_filing_repo.py` の末尾に追記:

```python
async def test_update_storage_sets_path_and_hash(session):
    session.add(Company(
        id="US_AAPL", ticker="AAPL", name="Apple",
        market="NASDAQ", accounting_standard="US-GAAP",
    ))
    await session.flush()
    f = Filing(
        company_id="US_AAPL", source="SEC", filing_type="10-K",
        period_type="annual", fiscal_year=2024,
    )
    session.add(f)
    await session.flush()

    repo = FilingRepository(session)
    await repo.update_storage(
        f.id, storage_path="/data/filings/SEC/US_AAPL/2024/annual/10-K/AC-1",
        content_hash="abc123",
    )
    await session.refresh(f)
    assert f.storage_path == "/data/filings/SEC/US_AAPL/2024/annual/10-K/AC-1"
    assert f.content_hash == "abc123"


async def test_get_latest_with_content_returns_latest_with_storage(session):
    session.add(Company(
        id="US_AAPL", ticker="AAPL", name="Apple",
        market="NASDAQ", accounting_standard="US-GAAP",
    ))
    await session.flush()
    session.add(Filing(
        company_id="US_AAPL", source="SEC", filing_type="10-K",
        period_type="annual", fiscal_year=2023,
        storage_path="/data/old", period_end=__import__("datetime").date(2023, 9, 30),
    ))
    session.add(Filing(
        company_id="US_AAPL", source="SEC", filing_type="10-K",
        period_type="annual", fiscal_year=2024,
        storage_path=None, period_end=__import__("datetime").date(2024, 9, 28),
    ))
    session.add(Filing(
        company_id="US_AAPL", source="SEC", filing_type="10-Q",
        period_type="quarterly", fiscal_year=2024,
        storage_path="/data/q1", period_end=__import__("datetime").date(2024, 6, 30),
    ))
    await session.flush()

    repo = FilingRepository(session)
    result = await repo.get_latest_with_content("US_AAPL")
    assert result is not None
    # 期末日が新しい /data/q1 (2024-06-30) > /data/old (2023-09-30)
    assert result.storage_path == "/data/q1"


async def test_get_latest_with_content_returns_none_when_empty(session):
    session.add(Company(
        id="US_AAPL", ticker="AAPL", name="Apple",
        market="NASDAQ", accounting_standard="US-GAAP",
    ))
    await session.flush()
    repo = FilingRepository(session)
    assert await repo.get_latest_with_content("US_AAPL") is None


async def test_get_latest_indexed_returns_latest_with_index(session):
    from stock_analyze_system.models.document_index import DocumentIndex

    session.add(Company(
        id="US_AAPL", ticker="AAPL", name="Apple",
        market="NASDAQ", accounting_standard="US-GAAP",
    ))
    await session.flush()
    f1 = Filing(
        company_id="US_AAPL", source="SEC", filing_type="10-K",
        period_type="annual", fiscal_year=2023,
        period_end=__import__("datetime").date(2023, 9, 30),
    )
    f2 = Filing(
        company_id="US_AAPL", source="SEC", filing_type="10-K",
        period_type="annual", fiscal_year=2024,
        period_end=__import__("datetime").date(2024, 9, 28),
    )
    session.add_all([f1, f2])
    await session.flush()
    # f1 のみ index あり
    session.add(DocumentIndex(
        filing_id=f1.id, company_id="US_AAPL",
        index_json="{}", model_name="m", page_count=10, node_count=5,
    ))
    await session.flush()

    repo = FilingRepository(session)
    result = await repo.get_latest_indexed("US_AAPL")
    assert result is not None
    assert result.id == f1.id


async def test_get_latest_indexed_returns_none_when_no_indices(session):
    session.add(Company(
        id="US_AAPL", ticker="AAPL", name="Apple",
        market="NASDAQ", accounting_standard="US-GAAP",
    ))
    await session.flush()
    repo = FilingRepository(session)
    assert await repo.get_latest_indexed("US_AAPL") is None
```

- [ ] **Step 2.2: テストを実行して失敗することを確認**

```bash
uv run python -m pytest tests/unit/repositories/test_filing_repo.py -v -k "update_storage or with_content or indexed"
```

Expected: 5 tests FAIL with `AttributeError`.

- [ ] **Step 2.3: FilingRepository に 3 メソッドを実装**

`src/stock_analyze_system/repositories/filing.py` の `bulk_upsert` 直前に追加:

```python
async def update_storage(
    self, filing_id: int, storage_path: str, content_hash: str,
) -> None:
    """指定 filing の storage_path / content_hash を更新する (idempotent)。"""
    from sqlalchemy import update
    stmt = (
        update(Filing)
        .where(Filing.id == filing_id)
        .values(storage_path=storage_path, content_hash=content_hash)
    )
    await self._session.execute(stmt)
    await self._session.flush()


async def get_latest_with_content(self, company_id: str) -> Filing | None:
    """storage_path が NULL でない filing のうち、period_end → fiscal_year の
    順で最新を返す。"""
    stmt = (
        select(Filing)
        .where(
            Filing.company_id == company_id,
            Filing.storage_path.isnot(None),
        )
        .order_by(
            Filing.period_end.desc().nulls_last(),
            Filing.filed_at.desc().nulls_last(),
            Filing.fiscal_year.desc(),
        )
        .limit(1)
    )
    result = await self._session.execute(stmt)
    return result.scalar_one_or_none()


async def get_latest_indexed(self, company_id: str) -> Filing | None:
    """document_index に登録がある filing のうち、period_end → fiscal_year の
    順で最新を返す。"""
    from stock_analyze_system.models.document_index import DocumentIndex
    stmt = (
        select(Filing)
        .join(DocumentIndex, DocumentIndex.filing_id == Filing.id)
        .where(Filing.company_id == company_id)
        .order_by(
            Filing.period_end.desc().nulls_last(),
            Filing.filed_at.desc().nulls_last(),
            Filing.fiscal_year.desc(),
        )
        .limit(1)
    )
    result = await self._session.execute(stmt)
    return result.scalar_one_or_none()
```

- [ ] **Step 2.4: FilingService に委譲メソッドを追加**

`src/stock_analyze_system/services/filing.py` の `list_filings` 直前に追加:

```python
async def get_latest_with_content(self, company_id: str):
    return await self._repo.get_latest_with_content(company_id)

async def get_latest_indexed(self, company_id: str):
    return await self._repo.get_latest_indexed(company_id)
```

- [ ] **Step 2.5: テストを実行して通ることを確認**

```bash
uv run python -m pytest tests/unit/repositories/test_filing_repo.py tests/unit/services/test_filing_service.py -v
```

Expected: 全て PASS。

- [ ] **Step 2.6: コミット**

```bash
git add src/stock_analyze_system/repositories/filing.py \
        src/stock_analyze_system/services/filing.py \
        tests/unit/repositories/test_filing_repo.py
git commit -m "feat(repo): add filing storage updater and content/index latest queries"
```

---

## Task 3: FilingContentService

**Files:**
- Create: `src/stock_analyze_system/services/filing_content.py`
- Create: `tests/unit/services/test_filing_content_service.py`

- [ ] **Step 3.1: テストを書く**

`tests/unit/services/test_filing_content_service.py`:

```python
"""FilingContentService 単体テスト"""
from __future__ import annotations

import hashlib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from stock_analyze_system.config import FilingsConfig
from stock_analyze_system.exceptions import ContentNotFoundError
from stock_analyze_system.services.filing_content import (
    FetchSummary,
    FilingContentService,
)


def make_filing(**overrides):
    base = dict(
        id=1,
        company_id="US_AAPL",
        source="SEC",
        filing_type="10-K",
        period_type="annual",
        fiscal_year=2024,
        accession_no="0000320193-24-000123",
        doc_id=None,
        storage_path=None,
        content_hash=None,
        company=SimpleNamespace(cik="0000320193", edinet_code=None),
    )
    base.update(overrides)
    return SimpleNamespace(**base)


@pytest.fixture
def filing_repo():
    repo = AsyncMock()
    repo.update_storage.return_value = None
    return repo


@pytest.fixture
def sec_client():
    client = AsyncMock()
    client.get_primary_document_url.return_value = (
        "https://www.sec.gov/Archives/edgar/data/320193/"
        "000032019324000123/aapl-20240928.htm"
    )
    client.get_filing_html.return_value = "<html><body>aapl 10-K</body></html>"
    return client


@pytest.fixture
def edinet_client():
    client = AsyncMock()
    client.download_pdf.return_value = b"%PDF-1.7 fake"
    return client


@pytest.fixture
def service(filing_repo, sec_client, edinet_client, tmp_path):
    cfg = FilingsConfig(base_path=str(tmp_path))
    return FilingContentService(
        filing_repo=filing_repo,
        sec_client=sec_client,
        edinet_client=edinet_client,
        config=cfg,
    )


class TestEnsureContentSEC:
    async def test_writes_html_and_updates_storage(
        self, service, filing_repo, sec_client, tmp_path,
    ):
        filing = make_filing()
        result = await service.ensure_content(filing)

        # raw/<filename> に HTML が書かれる
        target_dir = tmp_path / "SEC/US_AAPL/2024/annual/10-K/0000320193-24-000123"
        html_files = list((target_dir / "raw").glob("*.htm*"))
        assert len(html_files) == 1
        assert html_files[0].read_text() == "<html><body>aapl 10-K</body></html>"

        # update_storage が呼ばれ filing が反映される
        filing_repo.update_storage.assert_awaited_once()
        kwargs = filing_repo.update_storage.await_args.kwargs
        assert kwargs["filing_id"] == 1
        assert kwargs["storage_path"] == str(target_dir)
        assert kwargs["content_hash"] == hashlib.sha256(
            b"<html><body>aapl 10-K</body></html>",
        ).hexdigest()

        # 戻り値は更新後の filing
        assert result.storage_path == str(target_dir)

    async def test_noop_when_already_present(
        self, service, filing_repo, sec_client, tmp_path,
    ):
        target_dir = tmp_path / "SEC/US_AAPL/2024/annual/10-K/0000320193-24-000123"
        (target_dir / "raw").mkdir(parents=True)
        (target_dir / "raw" / "aapl-20240928.htm").write_text("present")

        filing = make_filing(storage_path=str(target_dir))
        await service.ensure_content(filing)

        sec_client.get_filing_html.assert_not_called()
        filing_repo.update_storage.assert_not_called()

    async def test_re_fetches_when_storage_path_set_but_file_missing(
        self, service, sec_client, tmp_path,
    ):
        target_dir = tmp_path / "SEC/US_AAPL/2024/annual/10-K/0000320193-24-000123"
        target_dir.mkdir(parents=True)  # ディレクトリだけ作って中身なし

        filing = make_filing(storage_path=str(target_dir))
        await service.ensure_content(filing)

        sec_client.get_filing_html.assert_awaited_once()

    async def test_raises_value_error_when_accession_missing(self, service):
        filing = make_filing(accession_no=None)
        with pytest.raises(ValueError, match="accession"):
            await service.ensure_content(filing)


class TestEnsureContentEdinet:
    async def test_writes_pdf_and_updates_storage(
        self, service, filing_repo, edinet_client, tmp_path,
    ):
        filing = make_filing(
            source="EDINET", filing_type="annual_report",
            accession_no=None, doc_id="S100ABCD",
            company=SimpleNamespace(cik=None, edinet_code="E02144"),
        )
        await service.ensure_content(filing)

        target_dir = tmp_path / "EDINET/US_AAPL/2024/annual/annual_report/S100ABCD"
        assert (target_dir / "converted.pdf").read_bytes() == b"%PDF-1.7 fake"

        filing_repo.update_storage.assert_awaited_once()
        kwargs = filing_repo.update_storage.await_args.kwargs
        assert kwargs["storage_path"] == str(target_dir)

    async def test_raises_value_error_when_doc_id_missing(self, service):
        filing = make_filing(
            source="EDINET", accession_no=None, doc_id=None,
        )
        with pytest.raises(ValueError, match="doc_id"):
            await service.ensure_content(filing)

    async def test_converts_404_to_content_not_found(
        self, service, edinet_client,
    ):
        import httpx
        edinet_client.download_pdf.side_effect = httpx.HTTPStatusError(
            "404", request=httpx.Request("GET", "http://x"),
            response=httpx.Response(404),
        )
        filing = make_filing(
            source="EDINET", accession_no=None, doc_id="S100MISS",
        )
        with pytest.raises(ContentNotFoundError):
            await service.ensure_content(filing)


class TestFetchForCompany:
    async def test_aggregates_results(
        self, service, filing_repo, sec_client,
    ):
        filings = [
            make_filing(id=1, accession_no="A-1"),
            make_filing(id=2, accession_no="A-2", storage_path="/already/set"),
            make_filing(id=3, accession_no=None),  # 欠落で失敗
        ]
        # 既存の storage_path 判定: id=2 はパス + ファイルが必要なので
        # ensure_content 側で再 fetch される (テストではそれで OK)
        # ここでは「storage_path None の filing を対象にする」という
        # 集計を確認するため、id=2 は明示的に storage_path 設定済みとして
        # filter で skip 扱いになる前提を作る。
        # = list_filings は 3 件返すが、対象は id=1, 3 のみ。
        filing_repo.list_filings.return_value = filings

        summary = await service.fetch_for_company("US_AAPL")

        assert summary.fetched == 1   # id=1 成功
        assert summary.skipped == 1   # id=2 storage_path 設定済みでスキップ
        assert len(summary.failed) == 1  # id=3 failure
        assert summary.failed[0][0] == 3
```

- [ ] **Step 3.2: テストを実行して失敗することを確認**

```bash
uv run python -m pytest tests/unit/services/test_filing_content_service.py -v
```

Expected: `ModuleNotFoundError: No module named 'stock_analyze_system.services.filing_content'`

- [ ] **Step 3.3: FilingContentService を実装**

`src/stock_analyze_system/services/filing_content.py`:

```python
"""Filing 本体 (HTML/PDF) のフェッチ・保存サービス"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

import httpx

from stock_analyze_system.exceptions import ContentFetchError, ContentNotFoundError
from stock_analyze_system.services.filing import FilingService

if TYPE_CHECKING:
    from stock_analyze_system.config import FilingsConfig
    from stock_analyze_system.ingestion.edinet import EdinetClient
    from stock_analyze_system.ingestion.sec_edgar import SecEdgarClient
    from stock_analyze_system.repositories.filing import FilingRepository

logger = logging.getLogger(__name__)


@dataclass
class FetchSummary:
    """fetch_for_company の集計結果"""
    fetched: int = 0
    skipped: int = 0
    failed: list[tuple[int, str]] = field(default_factory=list)


class FilingContentService:
    """SEC HTML / EDINET PDF を fetch し、storage_path を確定するサービス"""

    def __init__(
        self,
        filing_repo: FilingRepository,
        sec_client: SecEdgarClient,
        edinet_client: EdinetClient,
        config: FilingsConfig,
    ):
        self._repo = filing_repo
        self._sec = sec_client
        self._edinet = edinet_client
        self._base_path = Path(config.base_path)

    async def ensure_content(self, filing):
        """filing.storage_path が空 (または実体不在) なら fetch & save。
        既に揃っていれば no-op。常に最新の filing を返す。"""
        if filing.storage_path and self._content_exists(Path(filing.storage_path)):
            return filing

        target_dir = self._compute_target_dir(filing)
        target_dir.mkdir(parents=True, exist_ok=True)

        source = (filing.source or "").upper()
        if source == "SEC":
            data = await self._fetch_sec(filing, target_dir)
        elif source == "EDINET":
            data = await self._fetch_edinet(filing, target_dir)
        else:
            raise NotImplementedError(f"unsupported filing source: {source!r}")

        content_hash = hashlib.sha256(data).hexdigest()
        await self._repo.update_storage(
            filing_id=filing.id,
            storage_path=str(target_dir),
            content_hash=content_hash,
        )
        filing.storage_path = str(target_dir)
        filing.content_hash = content_hash
        return filing

    async def fetch_for_company(self, company_id: str) -> FetchSummary:
        """企業の storage_path 未設定 filing を直列で fetch する。"""
        all_filings = await self._repo.list_filings(company_id)
        summary = FetchSummary()
        for filing in all_filings:
            if filing.storage_path:
                summary.skipped += 1
                continue
            try:
                await self.ensure_content(filing)
                summary.fetched += 1
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "content fetch failed for filing %d: %s", filing.id, exc,
                )
                summary.failed.append((filing.id, str(exc)))
        return summary

    # ---- private helpers ----

    def _content_exists(self, path: Path) -> bool:
        if (path / "converted.pdf").exists():
            return True
        raw = path / "raw"
        if raw.exists():
            for pattern in ("*.html", "*.htm"):
                if any(raw.glob(pattern)):
                    return True
        return False

    def _compute_target_dir(self, filing) -> Path:
        source = (filing.source or "").upper()
        if source == "SEC":
            key = filing.accession_no
            if not key:
                raise ValueError(
                    f"filing {filing.id} missing accession_no; cannot fetch SEC content",
                )
        elif source == "EDINET":
            key = filing.doc_id
            if not key:
                raise ValueError(
                    f"filing {filing.id} missing doc_id; cannot fetch EDINET content",
                )
        else:
            raise NotImplementedError(f"unsupported filing source: {source!r}")

        return FilingService.get_storage_path(
            base_path=str(self._base_path),
            source=source,
            company_id=filing.company_id,
            fiscal_year=filing.fiscal_year,
            period_type=str(filing.period_type),
            filing_type=str(filing.filing_type),
            key=key,
        )

    async def _fetch_sec(self, filing, target_dir: Path) -> bytes:
        cik = getattr(filing.company, "cik", None) if hasattr(filing, "company") else None
        if not cik:
            raise ValueError(
                f"filing {filing.id} company has no CIK; cannot fetch SEC content",
            )
        try:
            url = await self._sec.get_primary_document_url(cik, filing.accession_no)
            html = await self._sec.get_filing_html(url)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                raise ContentNotFoundError(
                    f"SEC primary document not found for {filing.accession_no}",
                ) from exc
            raise ContentFetchError(
                f"SEC fetch failed for {filing.accession_no}: {exc}",
            ) from exc

        filename = self._sanitize_filename(url.rsplit("/", 1)[-1] or "filing.htm")
        raw_dir = target_dir / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)
        out_path = raw_dir / filename
        body = html.encode("utf-8")
        out_path.write_bytes(body)
        return body

    async def _fetch_edinet(self, filing, target_dir: Path) -> bytes:
        try:
            data = await self._edinet.download_pdf(filing.doc_id)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                raise ContentNotFoundError(
                    f"EDINET PDF not found for doc {filing.doc_id}",
                ) from exc
            raise ContentFetchError(
                f"EDINET fetch failed for {filing.doc_id}: {exc}",
            ) from exc
        out_path = target_dir / "converted.pdf"
        out_path.write_bytes(data)
        return data

    @staticmethod
    def _sanitize_filename(name: str) -> str:
        cleaned = name.replace("..", "_").replace("/", "_").replace("\\", "_")
        return cleaned or "filing.htm"
```

- [ ] **Step 3.4: テストを実行して通ることを確認**

```bash
uv run python -m pytest tests/unit/services/test_filing_content_service.py -v
```

Expected: 8 tests PASS.

- [ ] **Step 3.5: コミット**

```bash
git add src/stock_analyze_system/services/filing_content.py \
        tests/unit/services/test_filing_content_service.py
git commit -m "feat(services): add FilingContentService for SEC/EDINET body fetch"
```

---

## Task 4: DI 配線 (cli/container.py)

**Files:**
- Modify: `src/stock_analyze_system/cli/container.py`
- Modify: `tests/integration/test_service_assembly.py` (assembly テストがある場合)

- [ ] **Step 4.1: ServiceContainer フィールド追加とアセンブル**

`src/stock_analyze_system/cli/container.py` を編集:

(a) TYPE_CHECKING import に追加:

```python
    from stock_analyze_system.services.filing_content import FilingContentService
```

(b) `ServiceContainer` dataclass に必須フィールドを追加 (Optional ではない):

```python
@dataclass
class ServiceContainer:
    company_service: CompanyService
    financial_service: FinancialService
    valuation_service: ValuationService
    filing_service: FilingService
    watchlist_service: WatchlistService
    target_service: AnalysisTargetService
    job_service: JobService
    financial_sync: FinancialSyncService
    filing_sync: FilingSyncService
    filing_content_service: FilingContentService  # ★ 追加: 必須
    screening_universe_service: ScreeningUniverseService | None = None
    ...
```

(c) `setup_services` 内、`filing_sync = FilingSyncService(...)` の直後に追加:

```python
    from stock_analyze_system.services.filing_content import FilingContentService

    filing_content_service = FilingContentService(
        filing_repo=filing_repo,
        sec_client=sec_client,
        edinet_client=edinet_client,
        config=config.filings,
    )
```

(d) `return ServiceContainer(...)` に新フィールドを渡す:

```python
    return ServiceContainer(
        company_service=company_svc,
        ...
        filing_sync=filing_sync,
        filing_content_service=filing_content_service,  # ★
        ...
    )
```

(e) `RagService(...)` の組み立てに `filing_content_service` を追加:

```python
        rag_service = RagService(
            pageindex_service=pageindex_service,
            analysis_repo=analysis_repo,
            llm_client=llm_client,
            qa_history_repo=qa_history_repo,
            filing_content_service=filing_content_service,  # ★
        )
```

- [ ] **Step 4.2: 既存 assembly テストを通す**

```bash
uv run python -m pytest tests/integration/test_service_assembly.py -v
```

通らない場合: `ServiceContainer` の必須フィールド追加で初期化エラーになっている可能性。テスト側がモック組み立てなら新フィールドを補う。

- [ ] **Step 4.3: 全 unit テストでも回帰がないことを確認**

```bash
uv run python -m pytest tests/unit -x --tb=short
```

Expected: 全 PASS。新たに失敗するのは Task 6 で改修する `RagService` 関連のみ。新たな失敗が無いこと、既存の合格テスト数が維持されていることを確認。

- [ ] **Step 4.4: コミット**

```bash
git add src/stock_analyze_system/cli/container.py
# 必要なら整合のため tests/integration/test_service_assembly.py も
git commit -m "feat(di): wire FilingContentService into ServiceContainer"
```

---

## Task 5: cli/filings.py download 拡張

**Files:**
- Modify: `src/stock_analyze_system/cli/filings.py`
- Modify: `tests/unit/cli/test_filings_cli.py` (既存に追記)

- [ ] **Step 5.1: テストを書く**

`tests/unit/cli/test_filings_cli.py` の末尾に追記 (既存ファイル先頭の import / fixture を流用)。先に既存ファイルを開き、`_handle_download` 系テストの書き方を確認してから以下を追加:

```python
class TestDownloadFetchesContent:
    async def test_download_invokes_sync_then_fetch(self, capsys):
        from argparse import Namespace
        from unittest.mock import AsyncMock, MagicMock

        from stock_analyze_system.cli.filings import _handle_download
        from stock_analyze_system.services.filing_content import FetchSummary

        services = MagicMock()
        services.company_service.get_company = AsyncMock(return_value=MagicMock(
            id="US_AAPL", cik="0000320193", edinet_code=None,
        ))
        services.filing_sync.update_from_sec = AsyncMock(return_value=3)
        services.filing_content_service.fetch_for_company = AsyncMock(
            return_value=FetchSummary(fetched=2, skipped=1, failed=[]),
        )

        args = Namespace(company_id="US_AAPL", json=False)
        await _handle_download(args, services)

        services.filing_sync.update_from_sec.assert_awaited_once_with(
            "US_AAPL", "0000320193",
        )
        services.filing_content_service.fetch_for_company.assert_awaited_once_with(
            "US_AAPL",
        )
        out = capsys.readouterr().out
        assert "Synced 3" in out
        assert "Fetched content: 2 new" in out

    async def test_download_exits_non_zero_when_fetch_fails(self):
        from argparse import Namespace
        from unittest.mock import AsyncMock, MagicMock

        import pytest

        from stock_analyze_system.cli.filings import _handle_download
        from stock_analyze_system.services.filing_content import FetchSummary

        services = MagicMock()
        services.company_service.get_company = AsyncMock(return_value=MagicMock(
            id="US_AAPL", cik="0000320193", edinet_code=None,
        ))
        services.filing_sync.update_from_sec = AsyncMock(return_value=1)
        services.filing_content_service.fetch_for_company = AsyncMock(
            return_value=FetchSummary(fetched=0, skipped=0, failed=[(42, "boom")]),
        )

        args = Namespace(company_id="US_AAPL", json=False)
        with pytest.raises(SystemExit) as excinfo:
            await _handle_download(args, services)
        assert excinfo.value.code == 1
```

- [ ] **Step 5.2: テストを実行して失敗することを確認**

```bash
uv run python -m pytest tests/unit/cli/test_filings_cli.py::TestDownloadFetchesContent -v
```

Expected: テストは fail (`fetch_for_company` が呼ばれない / 出力に "Fetched content" が出ない)。

- [ ] **Step 5.3: `_handle_download` を改修**

`src/stock_analyze_system/cli/filings.py` の `_handle_download` を全置換:

```python
async def _handle_download(args: argparse.Namespace, services: ServiceContainer) -> None:
    company = await require_company(services.company_service, args.company_id)
    if company.cik:
        synced = await services.filing_sync.update_from_sec(args.company_id, company.cik)
    elif company.edinet_code:
        synced = await services.filing_sync.update_from_edinet(
            args.company_id, company.edinet_code,
        )
    else:
        print(
            f"No CIK or EDINET code for '{args.company_id}'. Cannot download filings.",
            file=sys.stderr,
        )
        sys.exit(1)
    print(f"Synced {synced} filing metadata record(s) for '{args.company_id}'.")

    summary = await services.filing_content_service.fetch_for_company(args.company_id)
    print(
        f"Fetched content: {summary.fetched} new, "
        f"{summary.skipped} already-present, {len(summary.failed)} failed."
    )
    if summary.failed:
        for filing_id, msg in summary.failed:
            print(f"  filing_id={filing_id}: {msg}", file=sys.stderr)
        sys.exit(1)
```

- [ ] **Step 5.4: テストを実行して通ることを確認**

```bash
uv run python -m pytest tests/unit/cli/test_filings_cli.py -v
```

Expected: 全 PASS。

- [ ] **Step 5.5: 統合 E2E テストを書く** (httpx mock + SQLite)

`tests/integration/test_filings_download_e2e.py`:

```python
"""filings download コマンドの end-to-end 統合テスト"""
from __future__ import annotations

import pytest

from stock_analyze_system.cli.container import setup_services
from stock_analyze_system.config import AppConfig
from stock_analyze_system.models.base import Base
from stock_analyze_system.models.company import Company
from stock_analyze_system.models.filing import Filing
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import Session


@pytest.fixture
async def engine_with_aapl():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    from stock_analyze_system.models.base import get_session
    async with get_session(engine) as session:
        session.add(Company(
            id="US_AAPL", ticker="AAPL", name="Apple",
            market="NASDAQ", accounting_standard="US-GAAP", cik="0000320193",
        ))
        session.add(Filing(
            company_id="US_AAPL", source="SEC", filing_type="10-K",
            period_type="annual", fiscal_year=2024,
            accession_no="0000320193-24-000123",
        ))
    yield engine
    await engine.dispose()


async def test_filings_download_writes_storage_path(
    engine_with_aapl, httpx_mock, tmp_path,
):
    from stock_analyze_system.cli.filings import _handle_download
    from stock_analyze_system.models.base import get_session
    from argparse import Namespace

    # SEC submissions JSON
    httpx_mock.add_response(json={
        "filings": {
            "recent": {
                "form": ["10-K"],
                "filingDate": ["2024-11-01"],
                "reportDate": ["2024-09-28"],
                "accessionNumber": ["0000320193-24-000123"],
                "primaryDocument": ["aapl-20240928.htm"],
                "primaryDocDescription": ["10-K"],
            },
            "files": [],
        },
    })
    # update_from_sec が同じ submissions JSON を呼ぶ可能性に備えて再追加
    httpx_mock.add_response(json={
        "filings": {
            "recent": {
                "form": ["10-K"],
                "filingDate": ["2024-11-01"],
                "reportDate": ["2024-09-28"],
                "accessionNumber": ["0000320193-24-000123"],
                "primaryDocument": ["aapl-20240928.htm"],
                "primaryDocDescription": ["10-K"],
            },
            "files": [],
        },
    })
    # primary document HTML
    httpx_mock.add_response(text="<html>10-K body</html>")

    config = AppConfig()
    config.filings.base_path = str(tmp_path)
    config.sec_edgar.email = "test@example.com"

    async with get_session(engine_with_aapl) as session:
        services = await setup_services(session, config)
        args = Namespace(company_id="US_AAPL", json=False)
        await _handle_download(args, services)
        await session.commit()

    # storage_path が DB に書かれていること
    async with get_session(engine_with_aapl) as session:
        from sqlalchemy import select
        result = await session.execute(
            select(Filing).where(Filing.company_id == "US_AAPL"),
        )
        filing = result.scalar_one()
        assert filing.storage_path is not None
        assert "0000320193-24-000123" in filing.storage_path
        # raw 配下に HTML があること
        from pathlib import Path
        html_files = list((Path(filing.storage_path) / "raw").glob("*.htm*"))
        assert len(html_files) == 1
```

httpx_mock の追加レスポンス順は実際の呼び出し順 (sync が submissions を 1 回, fetch が submissions + HTML を 1 回ずつ) に従う。`update_from_sec` のキャッシュ等でズレた場合は `httpx_mock.non_mocked_hosts` を確認する。

- [ ] **Step 5.6: 統合テストを実行**

```bash
uv run python -m pytest tests/integration/test_filings_download_e2e.py -v
```

Expected: PASS。

- [ ] **Step 5.7: コミット**

```bash
git add src/stock_analyze_system/cli/filings.py \
        tests/unit/cli/test_filings_cli.py \
        tests/integration/test_filings_download_e2e.py
git commit -m "feat(cli): extend filings download to fetch HTML/PDF and persist storage_path"
```

---

## Task 6: RagService の自動 fetch ガード + 進捗ログ

**Files:**
- Modify: `src/stock_analyze_system/services/rag_service.py`
- Modify: `src/stock_analyze_system/cli/rag.py`
- Modify: `tests/unit/services/test_rag_service.py`

- [ ] **Step 6.1: テストを書く**

`tests/unit/services/test_rag_service.py` の `service` フィクスチャ周辺を更新し、`filing_content_service` を受け取れるように:

```python
@pytest.fixture
def filing_content_service():
    svc = AsyncMock()
    # デフォルトは「呼ばれたら storage_path を埋めて返す」
    async def _ensure(filing):
        filing.storage_path = "/data/auto/fetched"
        return filing
    svc.ensure_content.side_effect = _ensure
    return svc


@pytest.fixture
def service(pageindex_service, analysis_repo, llm_client, filing_content_service):
    return RagService(
        pageindex_service=pageindex_service,
        analysis_repo=analysis_repo,
        llm_client=llm_client,
        filing_content_service=filing_content_service,
    )
```

ファイル末尾に新規テストを追加:

```python
class TestEnsureFilingContent:
    async def test_run_analysis_auto_fetches_when_storage_missing(
        self, service, filing_content_service, pageindex_service,
    ):
        filing = MagicMock()
        filing.id = 1
        filing.company_id = "US_AAPL"
        filing.storage_path = None  # 未取得

        await service.run_analysis(filing, "business_summary")

        filing_content_service.ensure_content.assert_awaited_once()
        pageindex_service.get_or_create_index.assert_called_once()

    async def test_ask_question_auto_fetches_when_storage_missing(
        self, service, filing_content_service, pageindex_service,
    ):
        filing = MagicMock()
        filing.id = 1
        filing.company_id = "US_AAPL"
        filing.storage_path = None

        await service.ask_question(filing, "test?")
        filing_content_service.ensure_content.assert_awaited_once()


class TestRunFullAnalysisStream:
    async def test_emits_fetching_then_indexing_when_storage_missing(
        self, service, filing_content_service,
    ):
        filing = MagicMock()
        filing.id = 1
        filing.company_id = "US_AAPL"
        filing.storage_path = None

        events = [evt async for evt in service.run_full_analysis_stream(filing)]
        kinds = [e["event"] for e in events]
        # fetching → indexing → started → ... → complete
        assert kinds[0] == "fetching"
        assert kinds[1] == "indexing"
        assert kinds[2] == "started"
        assert kinds[-1] == "complete"
        filing_content_service.ensure_content.assert_awaited_once()

    async def test_skips_fetch_when_storage_already_set(
        self, service, filing_content_service,
    ):
        filing = MagicMock()
        filing.id = 1
        filing.company_id = "US_AAPL"
        filing.storage_path = "/already/set"

        events = [evt async for evt in service.run_full_analysis_stream(filing)]
        kinds = [e["event"] for e in events]
        assert "fetching" not in kinds
        filing_content_service.ensure_content.assert_not_called()

    async def test_emits_error_when_fetch_fails(
        self, service, filing_content_service,
    ):
        filing = MagicMock()
        filing.id = 1
        filing.company_id = "US_AAPL"
        filing.storage_path = None
        filing_content_service.ensure_content.side_effect = RuntimeError("boom")

        events = [evt async for evt in service.run_full_analysis_stream(filing)]
        kinds = [e["event"] for e in events]
        assert kinds == ["fetching", "error", "complete"]
        assert "boom" in events[1]["message"]

    async def test_emits_error_when_no_content_service(
        self, pageindex_service, analysis_repo, llm_client,
    ):
        # filing_content_service=None で初期化
        from stock_analyze_system.services.rag_service import RagService
        service = RagService(
            pageindex_service=pageindex_service,
            analysis_repo=analysis_repo,
            llm_client=llm_client,
            filing_content_service=None,
        )
        filing = MagicMock()
        filing.id = 1
        filing.storage_path = None

        events = [evt async for evt in service.run_full_analysis_stream(filing)]
        assert events[0]["event"] == "error"
        assert "filings download" in events[0]["message"]
        assert events[-1]["event"] == "complete"
```

- [ ] **Step 6.2: テストを実行して失敗することを確認**

```bash
uv run python -m pytest tests/unit/services/test_rag_service.py -v
```

Expected: 新規テストは `RagService.__init__` が `filing_content_service` を受け付けない / `ensure_content` が呼ばれない等で fail。

- [ ] **Step 6.3: RagService を改修**

`src/stock_analyze_system/services/rag_service.py` を編集:

(a) `__init__` に引数追加:

```python
def __init__(
    self,
    pageindex_service: PageIndexService,
    analysis_repo: AnalysisRepository,
    llm_client: LlmClient,
    qa_history_repo: RagQaHistoryRepository | None = None,
    filing_content_service: "FilingContentService | None" = None,
):
    self._pageindex = pageindex_service
    self._analysis_repo = analysis_repo
    self._llm_client = llm_client
    self._qa_history_repo = qa_history_repo
    self._content_service = filing_content_service
```

`TYPE_CHECKING` ブロックに以下を追加:

```python
    from stock_analyze_system.services.filing_content import FilingContentService
```

(b) ヘルパメソッドを追加:

```python
async def _ensure_filing_content(self, filing):
    if filing.storage_path:
        return filing
    if self._content_service is None:
        raise FileNotFoundError(
            "Filing content not available; run `stock-analyze filings download` first.",
        )
    return await self._content_service.ensure_content(filing)
```

(c) `run_analysis`, `run_full_analysis`, `ask_question`, `build_index` の冒頭にガード追加:

```python
async def run_analysis(self, filing, analysis_type: str) -> AnalysisResult:
    if analysis_type not in ANALYSIS_TYPES:
        raise ValueError(...)
    spec = ANALYSIS_TYPES[analysis_type]
    logger.info("Running %s analysis for filing %d", analysis_type, filing.id)
    filing = await self._ensure_filing_content(filing)
    tree = await self._pageindex.get_or_create_index(filing)
    pdf_path = Path(filing.storage_path) / "converted.pdf"
    qr = await self._pageindex.query(tree, spec["prompt"], pdf_path)
    return await self._save_analysis(filing, analysis_type, qr)

async def build_index(self, filing) -> dict:
    filing = await self._ensure_filing_content(filing)
    return await self._pageindex.get_or_create_index(filing)

async def run_full_analysis(self, filing) -> list[AnalysisResult]:
    filing = await self._ensure_filing_content(filing)
    tree = await self._pageindex.get_or_create_index(filing)
    pdf_path = Path(filing.storage_path) / "converted.pdf"
    ...

async def ask_question(self, filing, question: str) -> QueryResult:
    logger.info("RAG Q&A for filing %d: %s", filing.id, question[:50])
    filing = await self._ensure_filing_content(filing)
    tree = await self._pageindex.get_or_create_index(filing)
    ...
```

(d) `run_full_analysis_stream` の `if not filing.storage_path:` ブロック (l.116-125) を以下に置換:

```python
async def run_full_analysis_stream(self, filing) -> AsyncIterator[dict]:
    if not filing.storage_path:
        if self._content_service is None:
            yield {
                "event": "error", "analysis_type": None,
                "message": (
                    "ファイリング本体の自動取得に失敗しました。"
                    "`stock-analyze filings download <company_id>` を実行してください。"
                ),
            }
            yield {"event": "complete"}
            return
        yield {"event": "fetching", "filing_id": filing.id}
        try:
            filing = await self._content_service.ensure_content(filing)
        except Exception as exc:  # noqa: BLE001
            logger.exception("content fetch failed for filing %d", filing.id)
            yield {
                "event": "error", "analysis_type": None,
                "message": f"本体取得に失敗しました: {exc}",
            }
            yield {"event": "complete"}
            return

    yield {"event": "indexing"}
    try:
        tree = await self._pageindex.get_or_create_index(filing)
    except Exception as exc:  # noqa: BLE001
        logger.exception("index build failed for filing %d", filing.id)
        yield {"event": "error", "analysis_type": None, "message": str(exc)}
        yield {"event": "complete"}
        return
    pdf_path = Path(filing.storage_path) / "converted.pdf"

    types = list(ANALYSIS_TYPE_NAMES)
    total = len(types)
    yield {"event": "started", "total": total}
    # ...以下、既存処理...
```

- [ ] **Step 6.4: cli/rag.py の進捗ログ追加**

`src/stock_analyze_system/cli/rag.py` の `_handle_index`, `_handle_analyze`, `_handle_ask` の各ハンドラで `filing` を取得した直後に追記:

```python
if not filing.storage_path:
    print(
        f"Filing content not present; fetching from {filing.source}...",
        flush=True,
    )
```

3 箇所すべてに追加。`_handle_index` のみ `--all_companies` ループ内 (各 filing 取得直後) にも入れる。

- [ ] **Step 6.5: テストを実行して通ることを確認**

```bash
uv run python -m pytest tests/unit/services/test_rag_service.py tests/unit/cli/test_rag_cli.py -v
```

Expected: 全 PASS。

- [ ] **Step 6.6: 全 unit テストの回帰確認**

```bash
uv run python -m pytest tests/unit -x --tb=short
```

Expected: Task 8 改修対象 (web/test_api.py の filing_options 等) を除き、すべて PASS。

- [ ] **Step 6.7: コミット**

```bash
git add src/stock_analyze_system/services/rag_service.py \
        src/stock_analyze_system/cli/rag.py \
        tests/unit/services/test_rag_service.py
git commit -m "feat(rag): auto-fetch filing content on demand and emit fetching event"
```

---

## Task 7: Web API の filing_id 対応 + filing_options 改修

**Files:**
- Modify: `src/stock_analyze_system/web/routes/api.py`
- Modify: `tests/unit/web/test_api.py`

- [ ] **Step 7.1: テストを書く**

`tests/unit/web/test_api.py` の末尾に追加 (既存の `auth_client` / `db_writer` fixture を使う):

```python
class TestRagAnalyzeFilingId:
    def test_uses_filing_id_when_provided(
        self, auth_client, db_writer, monkeypatch,
    ):
        from datetime import date
        import asyncio

        from stock_analyze_system.web.routes import api as api_module

        async def _seed():
            await db_writer(
                Company(
                    id="US_AAPL", ticker="AAPL", name="Apple",
                    market="NASDAQ", accounting_standard="US-GAAP",
                ),
                Filing(
                    id=42, company_id="US_AAPL", source="SEC",
                    filing_type="10-K", period_type="annual",
                    fiscal_year=2023, accession_no="A-OLD",
                    storage_path="/tmp/old", period_end=date(2023, 9, 30),
                ),
                Filing(
                    company_id="US_AAPL", source="SEC",
                    filing_type="10-Q", period_type="quarterly",
                    fiscal_year=2024, accession_no="A-Q1",
                    period_end=date(2024, 6, 30),
                ),
            )
        asyncio.get_event_loop().run_until_complete(_seed())

        called_with: dict = {}

        async def _stream():
            yield '{"event":"complete"}\n'

        mock_rag = AsyncMock()
        def _capture(filing):
            called_with["filing_id"] = filing.id
            return _stream()
        mock_rag.run_full_analysis_stream.side_effect = _capture
        monkeypatch.setattr(
            api_module, "_get_rag_service", lambda services: mock_rag,
        )

        resp = auth_client.post(
            "/api/stocks/US_AAPL/rag/analyze?filing_id=42",
        )
        assert resp.status_code == 200
        assert called_with["filing_id"] == 42

    def test_returns_404_when_filing_id_belongs_to_other_company(
        self, auth_client, db_writer,
    ):
        import asyncio

        async def _seed():
            await db_writer(
                Company(
                    id="US_AAPL", ticker="AAPL", name="Apple",
                    market="NASDAQ", accounting_standard="US-GAAP",
                ),
                Company(
                    id="US_MSFT", ticker="MSFT", name="MS",
                    market="NASDAQ", accounting_standard="US-GAAP",
                ),
                Filing(
                    id=99, company_id="US_MSFT", source="SEC",
                    filing_type="10-K", period_type="annual", fiscal_year=2024,
                    accession_no="MSFT-1",
                ),
            )
        asyncio.get_event_loop().run_until_complete(_seed())

        resp = auth_client.post(
            "/api/stocks/US_AAPL/rag/analyze?filing_id=99",
        )
        assert resp.status_code == 404


class TestFilingOptionsDefault:
    def test_default_prefers_indexed_filing(
        self, auth_client, db_writer,
    ):
        from datetime import date
        import asyncio
        from stock_analyze_system.models.document_index import DocumentIndex

        async def _seed():
            await db_writer(
                Company(
                    id="US_AAPL", ticker="AAPL", name="Apple",
                    market="NASDAQ", accounting_standard="US-GAAP",
                ),
                Filing(
                    id=1, company_id="US_AAPL", source="SEC",
                    filing_type="10-K", period_type="annual",
                    fiscal_year=2023, accession_no="A-1",
                    storage_path="/tmp/idx", period_end=date(2023, 9, 30),
                ),
                Filing(
                    id=2, company_id="US_AAPL", source="SEC",
                    filing_type="10-Q", period_type="quarterly",
                    fiscal_year=2024, accession_no="A-2",
                    period_end=date(2024, 6, 30),
                ),
                DocumentIndex(
                    filing_id=1, company_id="US_AAPL",
                    index_json="{}", model_name="m",
                    page_count=1, node_count=1,
                ),
            )
        asyncio.get_event_loop().run_until_complete(_seed())

        resp = auth_client.get("/api/stocks/US_AAPL/rag/filing_options")
        assert resp.status_code == 200
        body = resp.json()
        assert body["default"] is not None
        assert body["default"]["id"] == 1
        assert body["default"]["content_available"] is True
        assert body["default"]["is_fallback_default"] is False

    def test_default_falls_back_to_unfetched_latest(
        self, auth_client, db_writer,
    ):
        from datetime import date
        import asyncio

        async def _seed():
            await db_writer(
                Company(
                    id="US_AAPL", ticker="AAPL", name="Apple",
                    market="NASDAQ", accounting_standard="US-GAAP",
                ),
                Filing(
                    id=10, company_id="US_AAPL", source="SEC",
                    filing_type="10-Q", period_type="quarterly",
                    fiscal_year=2024, accession_no="A-Q",
                    period_end=date(2024, 6, 30),
                ),
            )
        asyncio.get_event_loop().run_until_complete(_seed())

        resp = auth_client.get("/api/stocks/US_AAPL/rag/filing_options")
        body = resp.json()
        assert body["default"]["id"] == 10
        assert body["default"]["content_available"] is False
        assert body["default"]["is_fallback_default"] is True
```

`db_writer` は async なので `asyncio.get_event_loop().run_until_complete(...)` パターンを使うが、もし既存テストで TestClient lifespan の中から呼ぶ書き方が確立しているなら合わせる (例: `seeded_filing` fixture のパターン)。

- [ ] **Step 7.2: テストを実行して失敗することを確認**

```bash
uv run python -m pytest tests/unit/web/test_api.py::TestRagAnalyzeFilingId tests/unit/web/test_api.py::TestFilingOptionsDefault -v
```

Expected: 全て fail (`filing_id` 受け取り未実装、`/rag/filing_options` の default ロジック未改修)。

- [ ] **Step 7.3: api.py を改修**

`src/stock_analyze_system/web/routes/api.py` を以下のとおり改修:

(a) `_filing_to_option` を拡張:

```python
def _filing_to_option(filing, *, fallback: bool = False) -> dict:
    return {
        "id": filing.id,
        "filing_type": filing.filing_type,
        "period_type": filing.period_type,
        "fiscal_year": filing.fiscal_year,
        "period_end": filing.period_end.isoformat() if filing.period_end else None,
        "filed_at": filing.filed_at.isoformat() if filing.filed_at else None,
        "content_available": bool(filing.storage_path),
        "is_fallback_default": fallback,
    }
```

(b) `_resolve_filing` ヘルパを追加 (`_require_latest_filing` を置換):

```python
async def _resolve_filing(
    services: ServiceContainer,
    company_id: str,
    filing_id: int | None,
    filing_type: FilingType,
):
    if filing_id is not None:
        filing = await services.filing_service.get_filing_by_id(filing_id)
        if filing is None or filing.company_id != company_id:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                detail=f"filing_id={filing_id} not found for {company_id}",
            )
        return filing
    filing = await services.filing_service.get_latest_filing(company_id, filing_type)
    if filing is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=f"No {filing_type} filings for {company_id}",
        )
    return filing
```

`_require_latest_filing` の関数定義は削除する (新ヘルパが置き換える)。

(c) `AskRequest` に `filing_id` を追加:

```python
class AskRequest(BaseModel):
    question: str
    filing_id: int | None = None
    filing_type: FilingType = FilingType.TEN_K
```

(d) `rag_ask`, `rag_index`, `rag_analyze` のシグネチャと中身を更新:

```python
@router.post("/{company_id}/rag/ask")
async def rag_ask(
    request: Request,
    company_id: str,
    payload: AskRequest,
    services: ServiceContainer = Depends(get_services),
):
    rag = _get_rag_service(services)
    filing = await _resolve_filing(
        services, company_id, payload.filing_id, payload.filing_type,
    )
    _enforce_heavy_request_limit(
        request, scope=f"rag-ask:{company_id}", detail="Too many RAG requests",
    )
    result = await rag.ask_question(filing, payload.question)
    return {
        "answer": result.answer,
        "source_pages": result.source_pages,
        "source_sections": result.source_sections,
    }


@router.post("/{company_id}/rag/index")
async def rag_index(
    request: Request,
    company_id: str,
    filing_id: int | None = None,
    filing_type: FilingType = FilingType.TEN_K,
    services: ServiceContainer = Depends(get_services),
):
    rag = _get_rag_service(services)
    filing = await _resolve_filing(services, company_id, filing_id, filing_type)
    _enforce_heavy_request_limit(
        request, scope=f"rag-index:{company_id}", detail="Too many index requests",
    )
    tree = await rag.build_index(filing)
    structure = tree.get("structure") if isinstance(tree, dict) else None
    return {"node_count": len(structure) if structure else 0}


@router.post("/{company_id}/rag/analyze")
async def rag_analyze(
    request: Request,
    company_id: str,
    filing_id: int | None = None,
    filing_type: FilingType = FilingType.TEN_K,
    services: ServiceContainer = Depends(get_services),
):
    rag = _get_rag_service(services)
    filing = await _resolve_filing(services, company_id, filing_id, filing_type)
    _enforce_heavy_request_limit(
        request,
        scope=f"rag-analyze:{company_id}",
        detail="Too many analyze requests",
    )

    async def stream():
        try:
            async for event in rag.run_full_analysis_stream(filing):
                yield json.dumps(event, ensure_ascii=False) + "\n"
        except Exception as exc:  # noqa: BLE001
            logger.exception("rag analyze stream failed for %s", company_id)
            yield json.dumps(
                {"event": "error", "message": f"内部エラー: {exc}"},
                ensure_ascii=False,
            ) + "\n"
            yield json.dumps({"event": "complete"}, ensure_ascii=False) + "\n"

    return StreamingResponse(stream(), media_type="application/x-ndjson")
```

(e) `/rag/filing_options` の default 選定を改修:

```python
@router.get("/{company_id}/rag/filing_options")
async def rag_filing_options(
    company_id: str,
    years: int = 10,
    services: ServiceContainer = Depends(get_services),
):
    since_year = date.today().year - years
    annuals = await services.filing_service.list_by_types(
        company_id, [str(t) for t in ANNUAL_FILING_TYPES],
        since_year=since_year,
    )

    default_filing = None
    if services.rag_service is not None:
        default_filing = await services.filing_service.get_latest_indexed(company_id)
    if default_filing is None:
        default_filing = await services.filing_service.get_latest_with_content(company_id)
    fallback_used = False
    if default_filing is None:
        default_filing = await services.filing_service.get_latest_any_type(company_id)
        fallback_used = True

    return {
        "default": (
            _filing_to_option(default_filing, fallback=fallback_used)
            if default_filing else None
        ),
        "annual_options": [_filing_to_option(f) for f in annuals],
    }
```

- [ ] **Step 7.4: テストを実行して通ることを確認**

```bash
uv run python -m pytest tests/unit/web/test_api.py -v
```

Expected: 全 PASS。既存の `filing_type` ベースのテストも後方互換で通ること。

- [ ] **Step 7.5: コミット**

```bash
git add src/stock_analyze_system/web/routes/api.py \
        tests/unit/web/test_api.py
git commit -m "feat(web/api): accept filing_id on rag endpoints and pick smart default"
```

---

## Task 8: フロントエンド (app.js) 改修

**Files:**
- Modify: `src/stock_analyze_system/web/static/app.js`

JavaScript はユニットテストがないため、変更は最小限に留めて手動検証 (Task 9) に委ねる。

- [ ] **Step 8.1: 分析ボタンが filing_id を送るように修正**

`src/stock_analyze_system/web/static/app.js:1006-1075` の `analyzeButton` クリックハンドラ内、l.1013-1017 を以下に置換:

```js
const url = analyzeButton.dataset.analyzeUrl;
const filingId = filingSelect ? filingSelect.value : "";
const fullUrl = filingId
    ? `${url}?filing_id=${encodeURIComponent(filingId)}`
    : url;
```

(`filingType` 計算と `?filing_type=` 付与のコードを削除)

- [ ] **Step 8.2: Q&A ボタンが filing_id を送るように修正**

l.911-919 (の現状の Q&A 送信ロジック) を以下に置換:

```js
const askPayload = { question: value };
const filingId = filingSelect ? filingSelect.value : "";
if (filingId) askPayload.filing_id = Number(filingId);
const data = await fetchJson(`/api/stocks/${companyId}/rag/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(askPayload),
});
```

`selectedFilingType()` ヘルパは Q&A 経路で不要になるので削除して構わないが、他で使われていないか念のため確認 (`grep -n selectedFilingType app.js`)。使われていなければ関数定義 (l.897-901) を削除。

- [ ] **Step 8.3: filing 選択肢ラベルに content_available を反映**

`formatFilingOptionLabel` の実装 (現状未読 — `grep -n formatFilingOptionLabel app.js` で位置を確認) を以下のロジックに修正:

- 末尾に `[本体未取得]` (content_available=false の場合)
- 更に `（取得待ち）` (is_fallback_default=true の場合)

実装パターン:

```js
function formatFilingOptionLabel(filing, isDefault) {
    const parts = [`${filing.filing_type}`, `FY${filing.fiscal_year}`];
    if (filing.period_end) parts.push(filing.period_end);
    if (isDefault) parts.push("(default)");
    if (filing.content_available === false) {
        parts.push("[本体未取得]");
        if (filing.is_fallback_default) parts.push("（取得待ち）");
    }
    return parts.join(" · ");
}
```

(既存の関数中身に上記を統合する。)

- [ ] **Step 8.4: 未取得注記を分析ボタン下に表示**

`_tab_analysis.html:11-15` を編集し、分析ボタンの直後に注記要素を追加:

`src/stock_analyze_system/web/templates/stocks/_tab_analysis.html` を編集:

```html
                <button class="btn btn--primary btn--sm" type="button" data-rag-analyze
                        data-analyze-url="/api/stocks/{{ company.id }}/rag/analyze">
                    決算分析🔍
                </button>
            </div>
        </header>
        <div class="panel__body">
            <p class="subtle" data-rag-filing-meta hidden style="font-size: var(--text-xs); margin-bottom: var(--space-2);"></p>
            <p class="subtle" data-rag-content-warning hidden style="font-size: var(--text-xs); color: var(--warn); margin-bottom: var(--space-2);">
                ⚠ この決算は本体未取得です。「決算分析🔍」を押すと自動取得しますが時間がかかる場合があります。
            </p>
```

`app.js` 側、`updateFilingMeta` (l.776-789) を拡張し、未取得時に注記を表示:

```js
function updateFilingMeta(filingId) {
    if (!filingMeta) return;
    const f = filingById.get(String(filingId));
    if (!f) {
        filingMeta.hidden = true;
        filingMeta.textContent = "";
        if (warningBox) warningBox.hidden = true;
        return;
    }
    const parts = [`filing_id=${f.id}`, `${f.filing_type}`, `FY${f.fiscal_year}`];
    if (f.period_end) parts.push(`期末: ${f.period_end}`);
    if (f.filed_at)   parts.push(`提出: ${f.filed_at}`);
    filingMeta.textContent = parts.join(" · ");
    filingMeta.hidden = false;
    if (warningBox) {
        warningBox.hidden = f.content_available !== false;
    }
}
```

`warningBox` は `panel.querySelector("[data-rag-content-warning]")` で取得して保持する。

- [ ] **Step 8.5: NDJSON `fetching` イベントを表示**

`applyEvent` (l.958-1003) の最初の分岐に追加:

```js
function applyEvent(evt, state) {
    if (evt.event === "fetching") {
        showIndeterminate("決算本体をダウンロード中…");
    } else if (evt.event === "indexing") {
        showIndeterminate("インデックス構築中…");
    } else if (evt.event === "started") {
        ...  // 既存
    }
    ...
}
```

- [ ] **Step 8.6: 手動でブラウザで動作確認**

開発サーバ起動 (memory: `infisical run --` 経由):

```bash
infisical run -- uv run python -m stock_analyze_system serve --reload
```

ブラウザで以下を順に確認:

1. 任意企業 (例: AAPL) の RAG タブを開き、選択肢に `[本体未取得]` のマークが付く filing が混じることを確認。
2. 未取得 filing を選ぶと、分析ボタンの下に黄色注記が出る。
3. 「決算分析🔍」を押すと、進捗ラベルが `決算本体をダウンロード中…` → `インデックス構築中…` → 各分析タイプ → 完了 と推移する。
4. 取得済み filing を選んだ場合は、進捗ラベルがいきなり `インデックス構築中…` から始まる (fetching が出ない)。

- [ ] **Step 8.7: コミット**

```bash
git add src/stock_analyze_system/web/static/app.js \
        src/stock_analyze_system/web/templates/stocks/_tab_analysis.html
git commit -m "feat(web/ui): send filing_id, surface fetching progress and unfetched warning"
```

---

## Task 9: 手動 E2E

このタスクはコマンド/UI の手動シナリオで、コミットは生まれない (修正がある場合のみ)。

- [ ] **Step 9.1: 既存 storage_path を持たない 1 件で `filings download` を実行**

```bash
uv run python -m stock_analyze_system filings download US_AAPL
```

期待: 出力に `Synced N filing metadata record(s) for 'US_AAPL'.` と `Fetched content: M new, K already-present, 0 failed.` が現れる。`data/filings/SEC/US_AAPL/.../raw/*.htm*` が生成される。

- [ ] **Step 9.2: `rag index` で PageIndex 構築**

```bash
uv run python -m stock_analyze_system rag index US_AAPL
```

期待: `converted.pdf` が生成され、index nodes が出力される。

- [ ] **Step 9.3: Web から FY2024 10-K の分析を実行**

ブラウザで AAPL の RAG タブを開き、FY2024 10-K (取得済み) を選択して「決算分析🔍」をクリック。

期待: 4 タイプの分析が完走、保存済み定型分析リストに 4 件が表示される。

- [ ] **Step 9.4: Web から未取得 filing の分析を実行 (自動 fetch)**

`[本体未取得]` ラベル付きの filing (例: 最新 10-Q) を選択して「決算分析🔍」をクリック。

期待: NDJSON ストリームが `fetching` → `indexing` → `started` → `phase` × N → `done` × N → `complete` の順で流れ、最終的に分析結果が表示される。データベース側で当該 filing の `storage_path` が NULL → 値ありに更新されている。

- [ ] **Step 9.5: 失敗ケースの確認 (任意)**

EDINET の type=2 が無い書類 (修正報告書等) があれば手動で `filings download` を JP 企業に対して実行し、出力に `failed: 1` が出ること、CLI の exit code が 1 になることを確認。

```bash
uv run python -m stock_analyze_system filings download JP_7203
echo "exit: $?"
```

- [ ] **Step 9.6: 手動 E2E の結果メモを残す (任意)**

スペックの末尾、または `docs/superpowers/specs/2026-05-04-filing-content-rootcause-design.md` の手動検証セクション付近に、実行ログの抜粋・スクリーンショット・観測したエッジケースを 1〜2 段落でメモすると後続実装者の助けになる。

---

## 実装後チェックリスト

- [ ] `uv run python -m pytest tests/ -x --tb=short` が全パス。
- [ ] `uv run ruff check src/stock_analyze_system tests/` が pass。
- [ ] 新規ファイル / 修正ファイルの import 順、型ヒント、async 化が既存パターンに一致。
- [ ] `git log --oneline` で 7 つのコミットが正しい順序で並ぶ (Task 1〜7。Task 8 は UI コミット、Task 9 は手動)。
- [ ] スペック `2026-05-04-filing-content-rootcause-design.md` のセクション 12「段階分け」と実コミットが対応。

---

## 既知の前提・注意

- pytest-httpx は既に dev 依存に入っている前提 (既存テスト `tests/unit/ingestion/test_edinet.py` で使用)。なければ `pyproject.toml` に追記。
- `tests/integration/test_filings_download_e2e.py` は既存 `tests/integration/test_service_assembly.py` の隣に配置。pytest 設定で integration マーカー必須なら `pytestmark = pytest.mark.integration` を追加。
- `infisical run --` は memory 通り Web サーバ起動時に必須 (WEB_PASSWORD 等)。CLI 単体実行 (`filings download`) は infisical 不要だが、SEC_EDGAR_EMAIL 等は config から読み込まれるため `.env` または設定ファイルが必要。
- `docs/superpowers/specs/2026-05-04-filing-content-rootcause-design.md` の §6.1 に書いた `RagService.__init__` 引数順 (positional / kw-only) は既存呼び出し元と一致させる。テスト失敗が発生したら順序を再確認。
