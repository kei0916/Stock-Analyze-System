# ADR-004: 定型分析を SEC 専用の固定セクション抽出に置き換える

## Situation

定型分析 (`business_summary` / `mda` / `risk_factors` / `competitors` の 4 種) は現在 PageIndex に依存している。PageIndex は PDF から TOC を LLM (Qwen3.6) で抽出し、論理ページと物理ページの対応を LLM で当て、その上にツリーインデックスを構築する。`docs/analysis-failures-root-cause.md` で確定したとおり、Qwen3.6 は `--jinja` 経由でも `enable_thinking=false` を honor せず `reasoning_content` に思考を出すため、PageIndex の sync な JSON-mode 呼び出しが空応答を返し、TOC 抽出が全停止する。直近16ジョブ中11件 (RXRX 10-K, TEM 10-K/10-Q, GRRR 6-K, ABCL 10-K, TSM 20-F) が `Processing failed` で失敗した。

## Complication

`docs/analysis-failures-root-cause.md` §8 のコミット7 (元 P2 2モデル構成案) で「PageIndex の TOC 抽出だけ non-reasoning モデルへ分離」する案を立てたが、これは:

- 2台目 llama-server の運用が必要 (systemd / メモリ管理 / 監視が二重化)
- TOC 抽出に LLM が居座る SPOF 構造は残る (alt モデルが別の理由で壊れれば同じことが起きる)
- SEC 提出書類が **Regulation S-K で章立てが法的に固定** という最大の構造的利点を一切使っていない

10-K / 10-Q は Item 番号が法的に決まっており、iXBRL の `*TextBlock` ファクトや HTML 構造から **LLM を呼ばずに deterministic に章抽出できる**。20-F も SEC タクソノミの別系統で同様。`FilingType` enum (`src/stock_analyze_system/models/enums.py`) で取り扱う対象は `10-K` / `10-Q` / `20-F` / `6-K` のみ。

## Question

`RagService` の定型分析 4 種の **章抽出ステップ** を、LLM 依存の PageIndex から SEC ファイリング種別ごとの固定セクション抽出器に置き換えるべきか?

## Answer

**置き換える。** 新サービス `FilingSectionExtractor` を `services/` に追加し、`RagService` の **stream 版 (`run_full_analysis_stream`) と非 stream 版 (`run_full_analysis`) の両方** の「章テキスト取得段」を差し替える。`ask_question` (自由質問) 系の PageIndex 経路は残す。

### スコープの明確化 (重要)

本 ADR の置換対象は **章テキストの取得段だけ**。各 analysis_type の構造化 JSON 生成は `services/prompts.py` の prompt を使った LLM 呼び出し (`_pageindex.query(...)` または後継の同等関数) のまま残る。

| ステップ | 現状 | 本 ADR 後 |
|---|---|---|
| 1. TOC 抽出 + 物理ページマッピング | PageIndex (LLM 多数回) | **`FilingSectionExtractor` (LLM 呼び出しゼロ)** |
| 2. 4 種ごとに該当章テキストを取得 | PageIndex tree クエリ (LLM 呼ぶ) | **抽出済み section dict から直接取得 (LLM ゼロ)** |
| 3. 各章テキストを LLM に渡して構造化 JSON 生成 | `_pageindex.query()` → LLM 1回 | **`_llm_client.completion(prompt + section_text, quality=True)` → LLM 1回** (変わらず) |

合計の LLM 呼び出し回数: 現状 (数十回 / build) → 本 ADR 後 (4 回 / build、analysis_type ごとに1回)。**SPOF が消えるのは step 1-2 のみで、step 3 は LLM 必須のまま。**

**step 3 の `reasoning_content` 暴走リスク (旧 §4.5) は実機検証で再現せず**
(`docs/step3-reasoning-runaway-verification.md`):

- 現行 `LlmClient.completion` は `litellm.acompletion(...)` を呼ぶ際 `response_format` を渡しておらず、`extra_body.chat_template_kwargs.enable_thinking=False` を Qwen3.6-27B-Q4_K_M (`--jinja`) が **完全に honor** することを実機で確認
- 最大 58K prompt token (RXRX 2025 10-K `risk_factors` フルテキスト) でも `reasoning_content` は 0 chars、`finish_reason=stop`、`content` は仕様通り JSON
- 旧構成 (`--ctx-size 32768 --parallel 4` = slot ctx 8192) では先に context overflow で `BadRequestError` となり runaway 自体に到達不能であったため、**新運用 `--ctx-size 131072 --parallel 1` (slot ctx 131072)** に切り替えて再検証
- `_analyze_section` の `_is_empty_llm_response` ガードは defense-in-depth として残置 (chat template 更新 / 他 filing 差異への保険)

### 決定の核

- **新サービス**: `src/stock_analyze_system/services/filing_section_extractor.py`
  - 入力: `Filing` (filing_type / storage_path / `raw/*.htm` パス)
  - 出力: `services/prompts.py` の `ANALYSIS_TYPE_NAMES` と完全一致するキーの dict:
    ```python
    {
        "business_summary": str,
        "risk_factors": str,
        "mda": str,
        "competitors": str,
    }
    ```
    既存のキャッシュ (`company_analyses.analysis_type` 列、`web/static/app.js` 等) が文字列依存しているため、キーは絶対に変えない。
  - LLM 呼び出しゼロ (本サービス内で完結)
- **fallback chain (実装範囲)**: ADR 当初は 4 段 (iXBRL TextBlock 直叩き / HTML 構造 / 正規表現 / 全文) を掲げたが、実装は以下の 3 段に集約する。`edgartools` の `HTMLParser` が iXBRL を含む混在 HTML から Item 単位の section を抽出するため、iXBRL `*TextBlock` ファクトを直接読む独立段は **設けない**。
  1. `edgartools.documents.HTMLParser` で section dict を得て、filing 種別ごとの mapping で lookup
  2. 1 が空かつ `_REGEX_FALLBACK` にパターンが定義されているとき、`doc.text()` を正規表現で切り出す (例: 10-Q の MD&A、TEM の U+2009 thin space で parser が `part_i_item_2` を取り逃す real-world ケースを救出)
  3. 1-2 双方が空かつ `_FULL_TEXT_FALLBACK` に対象 analysis_type が登録されているとき、全文 (`doc.text()`) を 1 section として返す (`6-K` の `business_summary` / `mda` 用)
- **filing 種別ごとの戦略** (対象は `FilingType` enum に含まれる 4 種のみ):
  - `10-K`: Item 1 → `business_summary` + `competitors`、Item 1A → `risk_factors`、Item 7 → `mda`。**注: Competition subsection の分離は未実装**。`competitors` は Item 1 全体を流用 (step 3 LLM 入力が冗長になる代わりに、Competition の位置検出に追加複雑性を導入しない)
  - `10-Q`: Part I Item 2 → `mda`、Part II Item 1A → `risk_factors`、`business_summary` / `competitors` は四半期報告に該当章が無いため **構造上空** (worker は失敗ではなく `skipped` として扱う)
  - `20-F`: Item 4 → `business_summary` + `competitors`、Item 3 → `risk_factors`、Item 5 → `mda`。**注: ADR 当初は Item 4B (Competition) / Item 3D (Risk Factors) の subsection 分離を意図していたが、edgartools は parent Item までしか分離しないため未実装**。実用上 Item 3 の大半が 3D Risk Factors、Item 4 の中心が 4B Business Overview で構成されるため、step 3 prompt にそのまま渡しても LLM が抽出できる
  - `6-K`: 章構造が規定されないため fallback 3 段目で `business_summary` / `mda` のみ best-effort、`risk_factors` / `competitors` は構造上空 (`skipped`)
- **依存追加** (`pyproject.toml` に明示済み):
  - `edgartools>=5.31.2` (MIT, 第一候補・実装の中核)
  - `beautifulsoup4>=4.14.3` (MIT, edgartools の transitive だが direct dependency として明記)
  - `arelle` は **採用見送り**: `edgartools.documents.HTMLParser` が iXBRL を含む解析で十分機能したため、別段の高精度 iXBRL fallback は不要と判断
- **`RagService` 改修スコープ**:
  - `run_full_analysis_stream` と `run_full_analysis` の双方で、`get_or_create_index` + `_pageindex.query(tree, spec["prompt"], pdf_path)` の組を、`FilingSectionExtractor.extract(filing)[atype]` で取った section text を `_llm_client.completion(spec["prompt"] + section_text, quality=True)` に渡すパターンへ統一。両者で空セクションの扱いも同一 (`skipped` + placeholder 保存) にし、stream / 非 stream の挙動分岐を防ぐ
  - CLI 経路 (`cli/rag.py` の `rag analyze` ハンドラから `rag.run_full_analysis` を呼ぶ) は非 stream 版経由で自動的に新実装に追従
- **`RagService.preflight`**: PageIndex 委譲を **やめ**、`LlmClient.completion("Reply ok.", quality=True, max_tokens=10)` で step 3 と同じ呼び出し経路 (model / chat template / timeout) を probe する。PageIndex JSON-mode probe (`PageIndexService.preflight`) は `ask_question` 専用に残す
- **既存 PageIndex 経路**: `ask_question` と CLI の `rag ask` 系統はそのまま。`pageindex/diagnostics.py` 等の観測性 / 診断インフラ (ブランチ `fix/analysis-failures-root-cause` の commits 1-6) は ask_question 経路で活き続ける
- **進捗イベント語彙**: stream 版は section 取得段の event 名を `indexing` → **`extracting`** に変更。worker は extractor 失敗を `error_details.index_build_error` ではなく **`error_details.extraction_error`** キーに分離 (UI が PageIndex 失敗と区別できるように)
- **キャッシュ識別**: `company_analyses` に `pipeline` 列を追加し、新規行は `'extractor'` を記録、既存 (PageIndex 時代) 行は NULL のまま残す。cache lookup は `pipeline = 'extractor'` で filter し、PageIndex 時代の結果が extractor 結果として再利用されることを防ぐ。自然キーは `(company_id, filing_id, analysis_type, pipeline)` とし、既存 SQLite DB は `create_db_engine` 起動時に legacy 3列 unique constraint を持つ table を rebuild して、legacy NULL 行と extractor 行の共存を保証する
- **空 LLM 応答の扱い**: `_analyze_section` で `llm_client.completion` の戻り値が空文字列 (Qwen3.6 reasoning_content 暴走の典型症状) のときは raise し、worker が `failed_types` に積む。空応答を `safe_json_loads` 経由で raw answer として成功キャッシュさせない

### Consequences

**正の効果**:
- 定型分析の LLM 呼び出しが数十回 → 4 回に減少 (step 3 のみ)。Qwen3.6 思考バグや llama-server 不調が定型分析の章抽出に影響しなくなる
- 処理時間が数十分から数十秒〜数分に短縮 (step 1-2 が秒オーダー)
- 章抽出失敗時の診断が決定論的 (どの fallback 段で抜けたかが残る)
- iXBRL 経路が成立すれば SEC が機械可読を意図したタグそのままなので精度上限が高い

**負の効果**:
- 新規依存 (`edgartools`, `arelle`, `beautifulsoup4`) — `MEMORY/feedback_litellm_security.md` 同様にサプライチェーンを継続監視
- 6-K / 古い 10-K / 一部 20-F は fallback 4 段目に落ちる可能性があり、`business_summary` / `risk_factors` 等が空 placeholder になる (`mda` / `competitors` も同様)。UI 側で「該当章が filing に無い」表示を追加する必要
- 定型分析と Q&A で実装パスが 2 系統に分かれる — メンテ対象が増える
- step 3 の LLM 呼び出しは残るが、`reasoning_content` 暴走リスクは **実機検証
  済み (2026-05-17) で再現せず** (詳細 `docs/step3-reasoning-runaway-verification.md`)。
  別 ADR は不要と判断。ただし新運用 `--ctx-size 131072 --parallel 1` が前提条件で
  あり、旧 `--ctx-size 32768 --parallel 4` (slot ctx 8192) では実 10-K セクションが
  ctx overflow するため不可
- 新 LLM 構成は GPU メモリをほぼ全量占有する (RTX 4090 24 GiB のうち約 24,036 MiB
  使用、残 37 MiB)。worker は直列化前提のためスループット影響なし
- ブランチ `fix/analysis-failures-root-cause` の **コミット 7 (元 P2 / 2モデル構成案) は本 ADR で superseded** されるため未着手のまま閉じる

### Alternatives 考慮

- **2 モデル構成 (`fix/analysis-failures-root-cause` のコミット 7 案)**: 2台目 llama-server の運用負荷と TOC 抽出に LLM SPOF が残る点で却下
- **チャンク + ベクトル検索 RAG**: 章境界が失われ Item 単位の集中分析ができなくなる、SEC の構造利点を捨てるため却下
- **長文コンテキスト LLM (Claude / Gemini 200K) に PDF 丸投げ**: ローカル LLM 運用方針と合わず、外部 API 依存で却下
- **`sec-api.io` 等の商用 API**: コスト + 外部送信、サプライチェーン信頼性で却下
- **8-K 対応を本 ADR に含める**: `FilingType` enum (`src/stock_analyze_system/models/enums.py`) に `8-K` が無く ingest もされていない。enum / ingest 拡張が前提のため別 ADR で扱う

## Status

Accepted (2026-05-16). Implementation merged on branch `feat/sec-section-extractor`. Files of record:

- `src/stock_analyze_system/services/filing_section_extractor.py` — `FilingSectionExtractor` with `_SECTION_KEY_MAP` (per-form Item lookup), `_REGEX_FALLBACK` (10-Q MD&A rescue), `_FULL_TEXT_FALLBACK` (6-K)
- `src/stock_analyze_system/services/rag_service.py` — `run_full_analysis_stream` / `run_full_analysis` / `run_analysis` route through extractor + `LlmClient.completion`; `preflight` uses a step-3-equivalent LLM probe (not PageIndex); `ask_question` keeps PageIndex
- `src/stock_analyze_system/services/analysis_worker.py` — handles `extracting` / `skipped` events; categorises extractor failures under `error_details.extraction_error` (separate from legacy `index_build_error`)
- `src/stock_analyze_system/models/company_analysis.py` + `src/stock_analyze_system/models/base.py` — `pipeline` column + `(company_id, filing_id, analysis_type, pipeline)` natural key; idempotent SQLite ALTER/rebuild on startup
- `src/stock_analyze_system/web/static/app.js` — UI renders `skipped` (適用外) and `extraction_error` (章抽出失敗) distinctly from PageIndex `index_build_error`
- Unit tests in `tests/unit/services/test_filing_section_extractor.py` and `tests/unit/services/test_rag_service.py` cover mappings, fallback chain, structural absence, empty LLM responses, and pipeline cache discrimination

Verified end-to-end on real filings (extractor side, sans real LLM): RXRX 10-K, TEM 10-Q (MD&A via regex fallback), TSM 20-F, GRRR 6-K.

### Known limitations explicitly left out of scope

- **10-K Item 1 Competition subsection** is not separated; `competitors` reuses the full Item 1 text. Step-3 LLM input is therefore redundant with `business_summary`. A future ADR can introduce a Competition-header regex if step-3 token budgets become a constraint.
- **20-F Item 4B / Item 3D subsections** are not separated for the same reason (edgartools does not detect them). `competitors` and `risk_factors` fall back to the parent Item 4 / Item 3 texts.
- **Step 3 `reasoning_content` runaway**: verified on 2026-05-17 to **not reproduce** under the new llama-server config (`--ctx-size 131072 --parallel 1 --jinja --n-gpu-layers 99`). Qwen3.6-27B-Q4_K_M honors `extra_body.chat_template_kwargs.enable_thinking=False` even at ~58K prompt tokens; `reasoning_content` stays empty and `content` returns the requested JSON. Full evidence in `docs/step3-reasoning-runaway-verification.md`. The `_analyze_section` empty-response guard remains as defense-in-depth. **Prerequisite**: do not roll back to the previous `--ctx-size 32768 --parallel 4` config (slot ctx 8192) — real 10-K sections (mda ~9K / risk_factors ~58K tokens) overflow that slot and produce `BadRequestError` instead of useful output.

### Amendment 2026-05-17 — Scope clarification and PageIndex independence

ADR-004 適用後の運用で 2 点の暗黙仕様が混乱を招いていたため、明文化する。

#### A. 対象 filing は SEC のみ

`FilingType` enum (`10-K` / `10-Q` / `20-F` / `6-K` / `annual_report` / `quarterly_report`) のうち、本 ADR の `FilingSectionExtractor` は **SEC source の HTML 入力 4 種 (`10-K` / `10-Q` / `20-F` / `6-K`) のみ** を扱う。EDINET の `annual_report` / `quarterly_report` は `converted.pdf` のみ保存され `_SECTION_KEY_MAP` のいずれにも該当しないため、UI / API の分析候補からも除外する。EDINET PDF への対応は別 ADR で扱う。

- `web/routes/api.py` の `ANALYSIS_FILING_TYPES` から `FilingType.ANNUAL_REPORT` を削除し、`FilingType.SIX_K` を追加する
- `POST /api/analysis-jobs` は filing が `source == "SEC"` かつ ADR-004 サポート 4 種であることを 422 で validate する

#### B. 定型分析は `pageindex.enabled` から独立

定型分析の章抽出は LLM 非依存・PageIndex 非依存。`pageindex.enabled` の意味を以下に再定義:

| 機能 | `pageindex.enabled=true` | `pageindex.enabled=false` |
|---|---|---|
| 定型分析 (`run_full_analysis` / `run_full_analysis_stream` / `run_analysis`) | 動く | **動く (本 amendment による)** |
| `preflight` (step-3 LLM probe) | 動く | 動く (LlmClient 直叩き、PageIndex 非依存) |
| `ask_question` (自由質問) | 動く | `PageIndexDisabledError` を返す |
| `build_index` / `get_index_status` | 動く | `PageIndexDisabledError` を返す |

- `RagService` は `setup_services` で常に構築される。シグネチャは `pageindex_service: PageIndexService | None`
- worker の `rag_service is None` ガードは削除する (常時構築前提のため、失敗状態として捕捉する意味がない)
- `ClientBundle.llm` も常に構築する。`PdfConverter` は `ask_question` 経路でのみ必要なので引き続き条件付き

#### C. ストレージ判定は source-aware (運用上の注意)

`FilingContentService.ensure_content` / `fetch_for_company` は filing.source が `SEC` の場合 `storage_path/raw/*.htm` のみを「コンテンツあり」とみなす (`filing_content_exists_for_source`)。EDINET は従来通り `converted.pdf` で真。これは extractor が必ず raw HTML を要求する ADR-004 の要請から導かれる。

**運用上の注意 (PR5 アップグレード後の初回起動)**:
- 通常運用では `_fetch_sec` が raw HTML を書いてから `PdfConverter.get_or_convert` が converted.pdf を併置するため、SEC × raw HTML 欠落 状態は出現しない
- ただし以下のケースで SEC ディレクトリに `converted.pdf` のみが残ることがある:
  - 容量節約で `raw/` 配下を pruning した運用
  - 手動 import / seed fixture
  - 過去の不完全な fetch
- これらの SEC dir に対しては `ensure_content` / `fetch_for_company` が初回呼び出し時に EDGAR から再 fetch して `raw/` を再生成し、`content_hash` を上書きする
- 大量の SEC 行で同時に再 fetch が走る場合は EDGAR の rate-limit (IP-based) に注意。必要に応じて `fetch_for_company` を 1 社ずつ手動で順次回す

ダッシュボードの "LLM分析 (extractor)" 件数は `pipeline = 'extractor'` 行のみを集計する (legacy PageIndex `pipeline IS NULL` 行は legacy 件数として併記)。アップグレード直後に extractor 件数が 0 でも legacy 件数が表示されていればデータは残っており、再分析で extractor 行が増える。

#### D. SQLite uq_analysis_key 拡張のスキーマ移行

`models.base._rebuild_company_analyses_pipeline_key` はレガシー `(company_id, filing_id, analysis_type)` の UNIQUE を `(company_id, filing_id, analysis_type, pipeline)` に拡張するため、SQLite の table-rebuild recipe (https://www.sqlite.org/lang_altertable.html) に従い `CREATE → INSERT...SELECT → DROP → RENAME` する。

migration は `create_db_engine` の `engine.begin()` 内 (transaction context) で走るため、SQLite 仕様により `PRAGMA foreign_keys=OFF/ON` は no-op になる。代わりに以下の2つの不変条件で安全性を担保する:

1. **inbound FK 不在**: 本プロジェクトには `company_analyses` を FK 参照する他テーブルが存在しない (`grep "ForeignKey('company_analyses` で確認)。よって DROP/RENAME 時に dangling child は発生しない。
2. **rebuild 末尾の `PRAGMA foreign_key_check`**: 上の不変条件 1 が将来破られた場合に migration が `RuntimeError` で fail する。

`test_pipeline_key_rebuild_runs_foreign_key_check` が check 結果を pin している。将来 `company_analyses` を FK 参照するテーブルを追加するときは、この migration を rebuild ベースから ALTER ベース (SQLite 3.35+ の `ALTER TABLE ... DROP CONSTRAINT`) に書き換えるか、専用の autocommit connection で 12-step を回す必要がある。
