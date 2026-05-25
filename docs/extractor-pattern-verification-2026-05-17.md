# FilingSectionExtractor 全パターン検証 (2026-05-17)

`docs/refactoring-candidates-2026-05-17.md` §1 fix B (worker 内 `IndexBuildError`
ハンドラ削除) の **前提条件**として、`FilingSectionExtractor.extract()` の
想定可能な全パターンを実機で確認したログ。A1 以降は raw HTML 欠落を
`ExtractionInputMissingError` として fail-fast するため、本書も「入力欠落は
期待例外、それ以外は unexpected raise なし」という前提に更新する。

## 1. 検証スクリプト

`scripts/verify_extractor_all_patterns.py` を実行。`data/stock_analyze.db` から
storage_path 付きの 4 種 filing 全件 (24) + 合成エッジケース (11) = **35 case** を
順次走らせ、各 case で:

- raise されるか / 投げる例外の type / 入力欠落として期待される raise か
- 4 種 analysis_type (`business_summary` / `risk_factors` / `mda` / `competitors`)
  ごとの section char count
- `is_structurally_empty(filing_type, analysis_type)` との突き合わせで「構造上空が
  期待される」か「想定外の欠落」か
- 既知の実データ欠落 allowlist 以外で `missing_unexpectedly` が出ていないか

を観測。raw 結果は `data/extractor_verification.json` に保存。allowlist 外の
欠落または unexpected raise が 1 件でもあれば非ゼロ終了する。

## 2. サマリ

| 指標 | 値 |
|---|---:|
| 総 case 数 | 35 |
| 実 filing | 24 |
| 合成 edge case | 11 |
| **unexpected raise** | **0** |
| **期待された入力欠落 raise** | storage/raw 欠落系 edge case |
| 実 filing で既知 allowlist の欠落が出た case | 3 |
| 合成 edge で期待通り空になった case | 5 |
| allowlist 外の欠落 | **0** |

→ raw HTML 欠落は `ExtractionInputMissingError` として明示し、それ以外の
入力では unexpected raise / allowlist 外の欠落が出ないことを確認する前提に
変更した。

## 3. 実 filing 結果 (24 件)

| filing_id | company | FY | type | bus | risk | mda | comp | 備考 |
|---:|---|---:|---|---:|---:|---:|---:|---|
| 2   | US_AAPL | 2025 | 10-K | 16,054   | 68,163  | 18,018  | 16,054   | ✓ |
| 6   | US_AAPL | 2024 | 10-K | 15,767   | 68,887  | 15,358  | 15,767   | ✓ |
| 258 | US_ABCL | 2025 | 10-K | 388,504  | **0**   | 51,933  | 388,504  | ⚠ risk_factors 欠落 |
| 250 | US_NTRA | 2025 | 10-K | 112,946  | 173,102 | 43,393  | 112,946  | ✓ |
| 199 | US_RXRX | 2025 | 10-K | 239,543  | 327,714 | 37,272  | 239,543  | ✓ |
| 203 | US_RXRX | 2024 | 10-K | 325,391  | 321,468 | 34,732  | 325,391  | ✓ |
| 216 | US_SDGR | 2025 | 10-K | 280,604  | 313,962 | 85,799  | 280,604  | ✓ |
| 161 | US_TEM  | 2025 | 10-K | **0**    | **0**   | **0**   | **0**    | ⚠ 全章欠落 |
| 162 | US_TEM  | 2024 | 10-K | **0**    | **0**   | **0**   | **0**    | ⚠ 全章欠落 |
| 267 | US_TWST | 2025 | 10-K | 46,083   | 149,023 | 37,627  | 46,083   | ✓ |
| 190 | US_TXG  | 2025 | 10-K | 35,252   | 272,242 | 55,126  | 35,252   | ✓ |
| 182 | US_WRBY | 2025 | 10-K | 29,963   | 196,974 | 45,682  | 29,963   | ✓ |
| 257 | US_ABCL | 2026 | 10-Q | 0        | 293,751 | 36,404  | 0        | ✓ (10-Q は bus/comp が構造上空) |
| 174 | US_MU   | 2026 | 10-Q | 0        | 105,584 | 30,107  | 0        | ✓ |
| 249 | US_NTRA | 2026 | 10-Q | 0        | 1,130   | 32,765  | 0        | ✓ (risk が短い) |
| 215 | US_SDGR | 2026 | 10-Q | 0        | 316,195 | 52,097  | 0        | ✓ |
| 197 | US_TEM  | 2026 | 10-Q | 0        | 1,552   | 73,864  | 0        | ✓ |
| 163 | US_TEM  | 2025 | 10-Q | 0        | 9,186   | 114,522 | 0        | ✓ |
| 164 | US_TEM  | 2025 | 10-Q | 0        | 8,863   | 103,963 | 0        | ✓ |
| 165 | US_TEM  | 2025 | 10-Q | 0        | 1,562   | 75,419  | 0        | ✓ |
| 166 | US_TEM  | 2024 | 10-Q | 0        | 366,533 | 89,578  | 0        | ✓ |
| 265 | US_TWST | 2026 | 10-Q | 0        | 856     | 28,290  | 0        | ✓ |
| 95  | US_TSM  | 2024 | 20-F | 54,159   | 60,280  | 39,374  | 54,159   | ✓ |
| 223 | US_GRRR | 2026 | 6-K  | 5,227    | 0       | 5,227   | 0        | ✓ (6-K は risk/comp が構造上空) |

### 3.1 既知の欠落 3 件 — 副次的に発見した data quality 問題

これらは **本検証の本筋 (B 修正の前提) とは独立**だが、production では LLM 失敗
として現れる可能性があり、別件として記録する。検証スクリプトでは
label + analysis_type 単位で allowlist 化し、新しい欠落が増えた場合は非ゼロ終了
させる:

- **US_ABCL FY2025 10-K (filing_id=258)**: `risk_factors` が 0 chars。
  `business_summary` / `mda` / `competitors` は数十万字取れているので、
  HTML は読めている。`_SECTION_KEY_MAP["10-K"]["risk_factors"]` の lookup
  キー `("Item 1A", "risk_factors")` が edgartools の section dict に
  hit しない可能性。
- **US_TEM FY2025 10-K (filing_id=161)** および **US_TEM FY2024 10-K
  (filing_id=162)**: 全 4 章が 0 chars。`raw/*.htm` 自体は存在するが
  edgartools の `HTMLParser` が section を一つも返さない。`docs/adr/004-...`
  で言及した TEM の thin space 問題が annual report 側にも波及している
  可能性が高い。`_REGEX_FALLBACK` は 10-Q `mda` 専用なので annual には
  効かない。

いずれも `extract()` は raise せず空 dict を返すため、worker 側では
`failed_types`/`analysis_error` で UI に反映される。**修正は別 ADR / 別 issue
で扱う**。本リファクタリングのスコープ外。

## 4. エッジケース結果 (11 件)

| case | filing_type | storage_path | raise | sections |
|---|---|---|---|---|
| storage_path=None | 10-K | `None` | `ExtractionInputMissingError` (expected) | n/a |
| storage_path='' | 10-K | `""` | `ExtractionInputMissingError` (expected) | n/a |
| storage_path nonexistent | 10-K | `/nonexistent/path/abc` | `ExtractionInputMissingError` (expected) | n/a |
| storage_path に raw/ 無 | 10-K | `<tmp>/no_raw_subdir` | `ExtractionInputMissingError` (expected) | n/a |
| raw/ 空 | 10-K | `<tmp>/empty_raw` | `ExtractionInputMissingError` (expected) | n/a |
| raw/ に PDF のみ | 10-K | `<tmp>/pdf_only` | `ExtractionInputMissingError` (expected) | n/a |
| raw/ malformed HTML | 10-K | `<tmp>/malformed` | ✗ | 全空 (edgartools "All detection strategies failed") |
| raw/ 空 HTML | 10-K | `<tmp>/empty_htm` | ✗ | 全空 |
| 未知 filing_type='8-K' | 8-K | 実 RXRX 10-K HTML | ✗ | 全空 (`_SECTION_KEY_MAP` に 8-K 無) |
| 未知 filing_type='S-1' | S-1 | 実 RXRX 10-K HTML | ✗ | 全空 |
| filing_type='' | '' | 実 RXRX 10-K HTML | ✗ | 全空 |

入力欠落 6 件は期待例外として分類し、raw HTML が存在する edge case は
unexpected raise なしで graceful fall-through する設計。

## 5. `_run_job` の例外フロー再検証

`src/stock_analyze_system/services/analysis_worker.py:198-273` を grep + 検証
結果と突き合わせ:

| `_run_job` 内の操作 | 投げうる例外 |
|---|---|
| `setup_services(...)` | 通常 raise なし (構成系) |
| `filing_service.get_filing_by_id(...)` | `ValueError` (filing 未存在時、`_run_job` 内で明示 raise) |
| `rag.preflight()` | dict を返す (raise なし); 失敗時は呼び出し側が `ExtractionFailedError` |
| `rag.run_full_analysis_stream(filing)` | **完全に catch されて event 経由**: ファイリング fetch 失敗 / extractor の `ExtractionInputMissingError` / per-type 失敗いずれも `{"event": "error", ...}` で yield |
| stream 後の `extraction_error`/`failed_types` 集計 | `ExtractionFailedError` / `AnalysisFailedError` |

→ `IndexBuildError` を raise する経路 (`pageindex/service.py:244,328`) は `_run_job`
の call tree に **存在しない**。

## 6. 結論

✅ **fix B (worker 内 `IndexBuildError` ハンドラ削除) は安全**。

- `FilingSectionExtractor.extract()` は raw HTML 欠落を期待例外として明示し、worker 側は stream error event として扱うことを確認
- 既知 3 件以外の `missing_unexpectedly` は検証スクリプトの失敗条件に含める
- `IndexBuildError` の raise 元 (`PageIndexService._build_tree` / `_build_root`)
  は `_run_job` から到達不能 (ADR-004 と commit `c4b3f03` で経路除去済)
- `IndexBuildError` クラス自体は `ask_question` 経路 (`PageIndexService.query`)
  でまだ使用されているため、**`exceptions.py` の定義は残す**。削除するのは
  worker 内の `except IndexBuildError` ブロック + `import IndexBuildError`
  だけ

## 7. 副次的に必要なフォローアップ (本リファクタとは別件)

- [ ] **US_ABCL FY2025 10-K `risk_factors` 0 chars の原因特定** —
  `_SECTION_KEY_MAP["10-K"]["risk_factors"]` lookup 失敗 or edgartools 解析欠落?
- [ ] **US_TEM FY2024/2025 10-K の全章 0 chars** — annual 側にも thin space
  問題があるか、別要因か。`_REGEX_FALLBACK` を annual 10-K にも追加する必要性
  検討
- [ ] 上記が確認できたら `docs/adr/004-sec-filing-section-extractor.md` の
  Known limitations を追記

## 8. 関連参照

- 検証スクリプト: `scripts/verify_extractor_all_patterns.py`
- raw 結果: `data/extractor_verification.json` (gitignored)
- ログ: `/tmp/extractor_verify.log`
- ADR: `docs/adr/004-sec-filing-section-extractor.md`
- リファクタリング候補一覧: `docs/refactoring-candidates-2026-05-17.md`
