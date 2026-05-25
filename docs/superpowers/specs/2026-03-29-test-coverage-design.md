# Test Coverage Strengthening Design

**Date**: 2026-03-29
**Scope**: プロジェクト全体のテストカバレッジ強化（85% → ~95%）
**Approach**: リスク/複雑度順（データ同期パイプライン → インジェスション → 残りギャップ）

---

## 背景

前回のメンテナビリティリファクタリングで397テスト・85%カバレッジの基盤がある。
安全に将来のリファクタリングを行うため、未テストの重要パスを網羅する。

## 対象と優先度

| 優先度 | モジュール | 現カバレッジ | 未テスト行数 | 主要ギャップ |
|--------|-----------|------------|------------|-------------|
| P1 | `xbrl/period_filter.py` | 58% | 22 | テストゼロ、純粋関数 |
| P1 | `xbrl/taxonomy.py` | 70% | 19 | ランタイム関数未テスト |
| P1 | `financial_sync.py` | 59% | 36 | SEC/EDINETパース未テスト |
| P1 | `filing_sync.py` | 56% | 31 | EDINETパス全体未テスト |
| P2 | `job.py` | 70% | 26 | daily_update全体未テスト |
| P2 | `yahoo_finance.py` | 39% | 73 | 四半期パース・履歴未テスト |
| P3 | `edinet.py` | 70% | 17 | download_xbrl_zip未テスト |
| P3 | `repositories/watchlist.py` | 68% | 9 | CRUD直接テストなし |
| P3 | `models/base.py` | 68% | 12 | create_db_engine未テスト |

## テスト方針

- **純粋関数**: 直接テスト（モック不要）
- **サービス層**: AsyncMockでリポジトリ・クライアントをモック
- **外部API依存**: yfinance等はモックでDataFrame模擬
- **既存パターン踏襲**: `_make_sync_svc()` ファクトリパターン、`pytest-asyncio` auto mode
- **テストファイル配置**: 既存の `tests/unit/` ディレクトリ構造に従う

## 各タスク設計

### Task 1: period_filter.py (0% → ~95%)
- `days_between`: 正常・不正日付・DURATION_UNKNOWN返却
- `duration_ok`: annual/quarterly/unknown mode
- `merge_near_dates`: 単一日付、クラスタマージ、値移行、競合ログ

### Task 2: taxonomy.py runtime functions (70% → ~95%)
- `detect_taxonomy`: us-gaap優先、ifrs優先、空facts
- `detect_currency`: USD/非USD検出、pure/shares除外
- `pick_unit`: share系/非share系
- `find_unit_data`: 全フォールバックパス（USD/shares → /shares → shares → USD）

### Task 3: financial_sync.py (59% → ~90%)
- `_parse_and_upsert_sec`: パーサーモック、レコードループ、例外処理
- `_parse_and_upsert_edinet`: EDINET全フロー、docIDなし、パーサー例外
- `update_from_edinet`: 空docs返却

### Task 4: filing_sync.py (56% → ~90%)
- `update_from_edinet`: EDINET登録フロー、docIDスキップ、既存スキップ、fiscal_year抽出
- `update_from_sec`: SEC例外処理、空リスト、accessionNumberなし

### Task 5: job.py (70% → ~90%)
- `sync_company`: EDINETパス（非USマーケット）、バリュエーション例外
- `run_daily_update`: 正常フロー、企業フィルタ、sync失敗時エラー集約

### Task 6: yahoo_finance.py (39% → ~85%)
- `_fetch_quarterly`: DataFrame模擬、_yf_val内部関数、NaN処理、FCF導出
- `_fetch_history`: 正常・空DataFrame
- 各publicメソッドの例外ハンドラ

### Task 7: edinet.py + watchlist repo
- `download_xbrl_zip`: APIキーなし例外、zip展開モック
- `search_company_filings`: 例外継続
- WatchlistRepository: list_items, add_item, delete_item

### Task 8: base.py + CLI残り
- `create_db_engine`: WAL/FK有効化確認
- CLI error paths（minor）
