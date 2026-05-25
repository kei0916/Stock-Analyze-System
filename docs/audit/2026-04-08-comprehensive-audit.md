# 総合コード監査レポート

**実施日**: 2026-04-08
**対象**: Stock_Analyze_System プロジェクト全体 (`src/stock_analyze_system/`)
**監査観点**: Dead Code, Consistency, Test Coverage, Security, Architecture

---

## 修正済み

### CRITICAL

| # | 問題 | ファイル | 対応 |
|---|------|---------|------|
| 1 | メソッド名不一致: `search_company_filings()` を `search_filings()` で呼び出し (実行時AttributeError) | filing_sync.py, financial_sync.py, テスト2件 | コミット `0210a49` 以降で修正 |

### HIGH (セキュリティ)

| # | 問題 | ファイル | 対応 |
|---|------|---------|------|
| 2 | litellm `>=1.82` がマルウェア版 v1.82.7/v1.82.8 を許容 | pyproject.toml | `>=1.83,!=1.82.7,!=1.82.8` に変更 |
| 3 | `ElementTree.parse()` で外部取得XBRL解析 (XXE脆弱性) | edinet_xbrl_parser.py (2箇所) | `defusedxml.ElementTree.parse()` に置換 |
| 4 | `zf.extractall()` にサイズ/パス検証なし (ZIP爆弾/スリップ) | edinet.py | 500MB上限 + パストラバーサル検証追加 |

### MEDIUM

| # | 問題 | ファイル | 対応 |
|---|------|---------|------|
| 5 | `datetime.now()` でタイムゾーン未指定 | verification_report.py | `datetime.now(timezone.utc)` に統一 |
| 6 | `_derive_fcf` 不要ラッパー、`_filing_repo` デッドステート、不要コメント等 | financial_sync.py, rag_service.py 他 | /simplify で修正 |

---

## 未修正 (今後対応推奨)

### Dead Code / 未実装feature残骸

| # | 問題 | ファイル | 推奨対応 |
|---|------|---------|----------|
| 7 | `ScreeningCache` モデル定義済み・未使用 | models/screening.py | Phase 5実装時に使用、または削除 |
| 8 | `CompetitorGroup`, `CompetitorGroupMember` モデル定義済み・未使用 | models/competitor_group.py | 実装予定がなければ削除 |
| 9 | `ScreeningRepository` クラス定義済み・未使用 | repositories/screening.py | Phase 5実装時に使用、または削除 |
| 10 | `WatchlistItem.tags` カラム定義済み・未参照 | models/watchlist.py:24 | CLI/サービスで利用するか、削除 |

### 型注釈 / コード品質

| # | 問題 | ファイル | 推奨対応 |
|---|------|---------|----------|
| 11 | `RagService.__init__` 全パラメータ型注釈なし | services/rag_service.py:34 | TYPE_CHECKING ガード付きで型追加 |
| 12 | `PageIndexService.__init__` 3パラメータ型注釈なし | services/pageindex_service.py:133 | 同上 |
| 13 | `FinancialService.compute_metrics(fd: Any)` 曖昧な型 | services/financial.py:54 | FinancialData 型に変更 |
| 14 | `JobService.__init__` 全パラメータ `Any` 型 | services/job.py:37-56 | TYPE_CHECKING ガード付きで型追加 |
| 15 | `screening_service: object \| None` 不正確な型 | cli/container.py:35 | ScreeningService 実装後に更新 |

### Enum / 定数の未活用

| # | 問題 | ファイル | 推奨対応 |
|---|------|---------|----------|
| 16 | `duration_ok()` が raw string `"annual"`/`"quarterly"` で比較 | ingestion/xbrl/period_filter.py:23-28 | `PeriodType` enum を受け取るよう変更 |
| 17 | FMP API呼び出しで raw string `"annual"` 使用 | ingestion/fmp.py:63 | `PeriodType.ANNUAL` に変更 |
| 18 | EDINET会計基準正規化が `std.upper().replace("_", "-")` の文字列操作 | services/financial_sync.py:140 | `AccountingStandard` enum へのマッピング辞書に変更 |

### エラーハンドリング不一致

| # | 問題 | ファイル | 推奨対応 |
|---|------|---------|----------|
| 19 | `yahoo_finance.py` 4メソッドで `except Exception` (過度に広い) | ingestion/yahoo_finance.py:48,100,109,120 | 具体的な例外型に絞る |
| 20 | `fmp.py` `is_available()` で `except Exception` | ingestion/fmp.py:88 | ApiConnectionError 等に限定 |
| 21 | `llm_client.py` `health_check()` で `except Exception` (ログなし) | services/llm_client.py:76 | logger.warning 追加 |
| 22 | services間で catch する例外セットが不統一 | job.py vs filing_sync.py vs financial_sync.py | 共通例外セットを定義 |

### アーキテクチャ / DRY

| # | 問題 | ファイル | 推奨対応 |
|---|------|---------|----------|
| 23 | upsert filter-key が3箇所に重複定義 | financial_sync.py, financial.py, repositories/financial.py | 定数を1箇所に集約 |
| 24 | JSON parse (try/loads/except) パターンが複数箇所に散在 | rag_service.py, pageindex_service.py | `shared/json_utils.py` に `safe_json_loads()` 抽出 |
| 25 | `json.dumps(ensure_ascii=False)` が5+箇所に散在 | rag_service.py, pageindex_service.py, formatters.py 他 | `shared/json_utils.py` に `safe_json_dumps()` 抽出 |
| 26 | 日付フォーマット `"%Y-%m-%d"` が6+箇所に散在 | sec_edgar.py, edinet.py, yahoo_finance.py 他 | `shared/dates.py` に定数・ヘルパー抽出 |
| 27 | SEC Edgar API URLs がソースにハードコード | ingestion/sec_edgar.py:13-15 | `AppConfig` に移動 |
| 28 | `ticker` vs `symbol` パラメータ名不統一 (同一概念) | yahoo_finance.py vs fmp.py | 片方に統一 |

### セキュリティ (LOW)

| # | 問題 | ファイル | 推奨対応 |
|---|------|---------|----------|
| 29 | Web service デフォルト `0.0.0.0` バインド | config/settings.yaml.example:30 | `127.0.0.1` に変更 |
| 30 | Web service 認証機構が未実装 (config にはpassword項目あり) | cli/serve.py | Web実装時に認証を実装 |

### テストカバレッジギャップ (主要な未テストメソッド)

| # | メソッド | ファイル |
|---|---------|---------|
| 31 | `CompanyService.list_companies()` | services/company.py |
| 32 | `WatchlistService.list_watchlists()`, `get_watchlist()`, `list_items()`, `add_item()` | services/watchlist.py |
| 33 | `ValuationService.get_history()`, `get_latest()` | services/valuation.py |
| 34 | `PdfConverter.convert()`, `get_or_convert()` エラーパス | services/pdf_converter.py |
| 35 | `PageIndexService.build_index()`, `query()` 例外パス | services/pageindex_service.py |
| 36 | `SecEdgarClient.get_filing_html()` | ingestion/sec_edgar.py |
| 37 | `EdinetClient.download_xbrl_zip()` 例外パス | ingestion/edinet.py |
| 38 | `container.setup_services()` | cli/container.py |
| 39 | `RagService.ask_questions()` 例外パス | services/rag_service.py |

---

## 総合評価

- **アーキテクチャ**: 良好。Service/Repository層分離、DI、集約Config が適切に設計されている
- **セキュリティ**: HIGH項目は全て修正済み。残りはLOWのみ
- **コード品質**: 基本的にクリーン。未実装feature残骸とenum未活用が主な改善点
- **テスト**: 537テスト通過。主要フローはカバー済みだが、エラーパスと一部公開メソッドに未テストあり
- **DRY**: shared/ モジュール拡張 (json_utils, dates) で更に改善可能
