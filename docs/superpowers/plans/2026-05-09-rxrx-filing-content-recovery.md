# RXRX Filing Content Auto-Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** DB の `storage_path` が `NULL` だがファイルシステムに実体が存在する場合、再ダウンロードせずに DB を自動復元し、決算分析を正常に実行できるようにする。

**Architecture:** `FilingContentService.ensure_content()` に、計算された `target_dir` の存在チェックを追加。ファイルが既存なら `SHA-256` ハッシュを計算して `update_storage` で DB を復元。これにより SEC submissions 未反映時の再ダウンロード失敗を回避する。

**Tech Stack:** Python 3.12, pytest, SQLite, FastAPI, pathlib, hashlib

---

## Background

RXRX（Recursion Pharmaceuticals, CIK: 1698907）の決算分析で「本体が取得できませんでした」と表示される問題が発生した。

### Root Cause

1. **DB・ファイルシステムの不整合**
   - DB 上では RXRX の最新四半期決算（10-Q 2026-03-31、accession_no: `0001601830-26-000078`）の `storage_path` が `NULL`
   - ファイルシステム上には `data/filings/SEC/US_RXRX/2026/quarterly/10-Q/0001601830-26-000078/raw/rxrx-20260331.htm` が存在（766KB の XBRL HTML）

2. **発生シナリオ（推定）**
   - 以前に分析・ダウンロードを試行
   - `ensure_content()` が SEC から HTML をフェッチし、ファイルシステムに保存
   - `update_storage()` で DB の `storage_path` を更新（`flush` まで実行）
   - その後の PageIndex 構築 (`build_index`) で例外が発生
   - `get_session` の `rollback()` が呼ばれ、DB の更新が巻き戻される
   - ファイルシステム上のファイルは残ったまま → **不整合が発生**

3. **SEC API 未反映**
   - `get_primary_document_url()` が `ValueError` を返す
   - SEC EDGAR の `submissions` JSON にまだこの accession number が反映されていない

---

## ADR_REQUIRED 判定基準

本変更は以下の条件に該当するため **ADR_REQUIRED = true** と判定する。

| # | 条件 | 該当理由 |
|---|------|---------|
| 1 | 既存ワークフローに新しいフォールバックパスを追加 | `storage_path=NULL` 時にファイルシステム探索という新しい分岐パスを追加する |
| 2 | 外部システムの一時的障害を内部で吸収する | SEC submissions 未反映を回避するための症状治療である |
| 3 | トランザクション境界や永続化タイミングを変更する | DB・ファイル不整合の根本原因がトランザクション・ファイルシステムの分離にある |
| 4 | コードレビューで「これは本当の修正か？」という議論が発生しうる | 自動修復は一時的回避策であり根本修正（別トランザクション化 or ロールバック時クリーンアップ）が必要である |

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `docs/adr/002-filing-content-auto-recovery.md` | Create | ワークアラウンドの意思決定記録 |
| `src/stock_analyze_system/services/filing_content.py` | Modify | `ensure_content` に自動修復ロジック追加 + `_compute_dir_hash` ヘルパー追加 |
| `tests/unit/services/test_filing_content_service.py` | Modify | 自動修復パスの失敗テスト追加 |
| `docs/superpowers/plans/2026-05-09-rxrx-filing-content-recovery.md` | Create | 本計画書 |

---

## Task 0: ADR — Filing Content Auto-Recovery

**Files:**
- Create: `docs/adr/002-filing-content-auto-recovery.md`

- [x] **Step 0: Write ADR**

```markdown
# ADR 002: Filing Content Auto-Recovery on DB-Filesystem Mismatch

## Decision
`storage_path` が NULL だがファイルシステムに実体が存在する場合、
再ダウンロードせずに DB を自動復元する。

## Context
- PageIndex 構築 (build_index) は LLM クエリを伴う重い処理で失敗しやすい
- `ensure_content()` → `update_storage()` → `build_index()` の同一トランザクション内で
  `build_index` が失敗すると rollback され、`storage_path` の更新が巻き戻される
- ファイルシステム上のファイルは残るため、DB・ファイル不整合が発生
- 再ダウンロードを試みると、SEC submissions JSON に未反映の新規 accession で
  `get_primary_document_url()` が ValueError を返す場合がある

## Alternatives Considered
1. `build_index` を別トランザクションで実行 → 理想だが実装コスト大、既存セッション
   管理への影響範囲が広い
2. rollback 時にファイルシステムもクリーンアップ → 失敗時のファイル残存を許容する
   方針との整合性が必要
3. 現状の症状緩和（選択）→ 最小侵入、即座にユーザー影響を解消

## Consequences
- ユーザーは再ダウンロード失敗を経由せずに分析を再開できる
- 不整合の根本原因（同一トランザクション内の重い処理）は解消されていない
- 将来的に Alternative 1 または 2 で根本修正すべき
```

- [x] **Step 0b: Commit ADR**

```bash
git add docs/adr/002-filing-content-auto-recovery.md
git commit -m "docs(adr): add filing content auto-recovery decision

ADR: docs/adr/002-filing-content-auto-recovery.md

Refs: RXRX 10-Q analysis failure"
```

---

## Task 1: Write the failing test

**Files:**
- Modify: `tests/unit/services/test_filing_content_service.py:110`（既存クラス `TestEnsureContentSEC` 内に追加）

- [x] **Step 1: Add failing test for auto-recovery path**

```python
async def test_recovers_storage_path_when_file_exists_but_db_is_null(
    self, service, filing_repo, sec_client, tmp_path,
):
    """DB の storage_path が NULL だがファイルシステムに実体がある場合、DB を復元する"""
    target_dir = tmp_path / "SEC/US_AAPL/2024/annual/10-K/0000320193-24-000123"
    (target_dir / "raw").mkdir(parents=True)
    html_content = "<html><body>recovered</body></html>"
    (target_dir / "raw" / "aapl-20240928.htm").write_text(html_content)

    filing = make_filing(storage_path=None)
    result = await service.ensure_content(filing)

    sec_client.get_filing_html.assert_not_called()
    filing_repo.update_storage.assert_awaited_once()
    kwargs = filing_repo.update_storage.await_args.kwargs
    assert kwargs["filing_id"] == 1
    assert kwargs["storage_path"] == str(target_dir)
    assert kwargs["content_hash"] == hashlib.sha256(html_content.encode()).hexdigest()
    assert result.storage_path == str(target_dir)
```

- [x] **Step 2: Run test to verify it fails**

```bash
<repo-root>/.venv/bin/pytest tests/unit/services/test_filing_content_service.py::TestEnsureContentSEC::test_recovers_storage_path_when_file_exists_but_db_is_null -v
```

Expected: FAIL with `AssertionError` (update_storage not called)

---

## Task 2: Implement auto-recovery logic

**Files:**
- Modify: `src/stock_analyze_system/services/filing_content.py:61-86`

- [x] **Step 3: Add `_compute_dir_hash` helper**

`FilingContentService` クラス内、`_sanitize_filename` の直後に追加：

```python
def _compute_dir_hash(self, target_dir: Path) -> str:
    """target_dir 内の既存ファイルから SHA-256 ハッシュを計算する。
    raw/ 内の HTML を優先し、次に直下の HTML、最後に converted.pdf を対象とする。
    """
    raw_dir = target_dir / "raw"
    files: list[Path] = []
    if raw_dir.exists():
        files.extend(sorted(raw_dir.glob("*.html")))
        files.extend(sorted(raw_dir.glob("*.htm")))
    if not files:
        files.extend(sorted(target_dir.glob("*.html")))
        files.extend(sorted(target_dir.glob("*.htm")))
    if not files:
        pdf = target_dir / "converted.pdf"
        if pdf.exists():
            files = [pdf]
    if not files:
        return ""

    hasher = hashlib.sha256()
    for f in files:
        hasher.update(f.read_bytes())
    return hasher.hexdigest()
```

- [x] **Step 4: Modify `ensure_content` to check target_dir before downloading**

```python
async def ensure_content(self, filing):
    """filing.storage_path が空 (または実体不在) なら fetch & save。
    既に揃っていれば no-op。常に最新の filing を返す。"""
    if filing_content_exists(filing.storage_path):
        return filing

    target_dir = self._compute_target_dir(filing)

    # DB・ファイル不整合の自動修復: storage_path=NULL だが
    # target_dir にファイルが既存する場合、DB を復元して再ダウンロードを回避
    if filing_content_exists(str(target_dir)):
        content_hash = self._compute_dir_hash(target_dir)
        await self._repo.update_storage(
            filing_id=filing.id,
            storage_path=str(target_dir),
            content_hash=content_hash,
        )
        filing.storage_path = str(target_dir)
        filing.content_hash = content_hash
        return filing

    target_dir.mkdir(parents=True, exist_ok=True)
    # ... existing download logic continues unchanged
```

- [x] **Step 5: Run all tests to verify pass**

```bash
<repo-root>/.venv/bin/pytest tests/unit/services/test_filing_content_service.py -v
```

Expected: ALL PASS (including new test)

---

## Task 3: Commit

- [x] **Step 6: Commit changes**

```bash
git add src/stock_analyze_system/services/filing_content.py tests/unit/services/test_filing_content_service.py
git commit -m "fix(filing-content): auto-recover storage_path when file exists but DB is null

When PageIndex build fails after a successful file fetch, the DB transaction
rolls back leaving storage_path=NULL while the file remains on disk.
Subsequent analysis attempts then fail with 'content not available' because
ensure_content() tries to re-download from SEC, which may not yet reflect
the accession in submissions JSON.

This adds a recovery path: if the computed target_dir already contains
valid filing content, restore storage_path and content_hash in the DB
without re-downloading.

ADR: docs/adr/002-filing-content-auto-recovery.md

Refs: RXRX 10-Q analysis failure (accession 0001601830-26-000078)"
```

---

## Task 4: Manual verification (RXRX)

- [ ] **Step 7: Verify RXRX analysis works**

```bash
# CLI から RXRX の決算分析を実行
<repo-root>/.venv/bin/python -m stock_analyze_system rag analyze US_RXRX
```

Expected: `filing_content_exists` が `True` を返し、インデックス構築・分析が正常に進行。  
Web UI からの分析でも「本体が取得できませんでした」が表示されなくなる。

---

## Self-Review Checklist

1. **Spec coverage:** RXRX の不整合問題（DB NULL + ファイル存在）を自動修復する仕様を満たしている。
2. **Placeholder scan:** コードステップにはすべて実装コードが含まれている。TODO/TBD なし。
3. **Type consistency:** `_compute_dir_hash` は `Path` を受け取り `str` を返す。`ensure_content` は `filing` オブジェクトをそのまま返す。既存のシグネチャと整合。

---

## ADR

`docs/adr/002-filing-content-auto-recovery.md` を参照。
