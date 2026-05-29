/* =====================================================================
   Content / Backend internals
   3 つの View が共有する、バックエンド設計の構造データ。
   ===================================================================== */

export const CONTENT = {
  /* --- メタ ---------------------------------------------------------- */
  meta: {
    name: "Stock Analyze System",
    nameJa: "株式分析システム",
    tagline: "米国・日本株のファンダメンタルズ + LLM 分析を回すローカル Web アプリ",
    repo: "kei0916/Stock-Analyze-System",
    branch: "feat/sec-section-extractor",
    python: "Python 3.10+",
    db: "SQLite (aiosqlite)",
    llm: "Qwen3.6-27B-Q4_K_M / llama.cpp",
  },

  /* --- 章 (Story view 用) -------------------------------------------- */
  chapters: [
    { id: "what",     n: "01", title: "このシステムは何？" },
    { id: "surfaces", n: "02", title: "プロセス構成" },
    { id: "flow",     n: "03", title: "データフロー" },
    { id: "rag",      n: "04", title: "RAG パイプライン" },
    { id: "layers",   n: "05", title: "コードの 7 層" },
    { id: "services", n: "06", title: "Services の中身" },
    { id: "models",   n: "07", title: "DB スキーマ" },
    { id: "stack",    n: "08", title: "技術スタック" },
    { id: "start",    n: "09", title: "起動・開発フロー" },
  ],

  /* --- 3 つのプロセス (旧 surfaces, backend 視点に振り直し) ---------- */
  surfaces: [
    {
      id: "web",
      name: "Web (FastAPI)",
      sub: "stock-analyze serve",
      who: "ユーザの操作受付",
      what: "FastAPI + Jinja2 SSR。`/api/analysis-jobs` への POST で Analysis Job を作るだけで、LLM 推論は呼ばない。",
      examples: [
        "GET  /                  ダッシュボード",
        "GET  /stocks/{id}       銘柄詳細 (5 タブ)",
        "POST /api/analysis-jobs ジョブ登録のみ",
        "GET  /jobs              ジョブ進捗 polling",
      ],
    },
    {
      id: "worker",
      name: "Worker",
      sub: "stock-analyze worker",
      who: "RAG 推論の常駐デーモン",
      what: "Web から登録された pending ジョブを polling し、FilingSectionExtractor → LlmClient → DB 書き戻しを直列に回す。",
      examples: [
        "pending ジョブを 1 件取り出す",
        "filing_section_extractor で 4 種抽出",
        "_llm_client.completion (4 回) で構造化 JSON",
        "company_analyses に保存 → done",
      ],
    },
    {
      id: "cli",
      name: "CLI",
      sub: "stock-analyze ...",
      who: "バッチ・cron・運用",
      what: "argparse ベースのサブコマンド集。services を直接呼ぶ。Web/Worker と同じレイヤを共有。",
      examples: [
        "stock-analyze jobs daily --market us",
        "stock-analyze screening run --gte roe=0.15",
        "stock-analyze rag analyze US_AAPL",
        "scripts/cron-*.sh から定期実行",
      ],
    },
  ],

  /* --- データフロー -------------------------------------------------- */
  flow: [
    {
      step: 1,
      from: "外部 API",
      to: "ingestion/*",
      label: "fetch",
      sources: ["secEdgar", "edinet", "yahooFinance", "stooq"],
      desc: "httpx + 各 SDK で生データを取る。失敗時は ADR-002 の自動リカバリで DB / FS 不整合を救う。",
    },
    {
      step: 2,
      from: "ingestion",
      to: "repositories → models → DB",
      label: "persist",
      desc: "正規化して SQLAlchemy 2.x の async セッションで bulk upsert。`bulk_upsert_cache` は ON CONFLICT 列を payload に絞る (ADR-003 の Yahoo batch 由来)。",
    },
    {
      step: 3,
      from: "services",
      to: "派生データ",
      label: "compute",
      desc: "metrics.py で PER/ROE 等を計算、valuation.py で 10 年履歴を組み立て、screening.py で filter 実行。LLM 不要。",
    },
    {
      step: 4,
      from: "services → web/cli",
      to: "UI",
      label: "render",
      desc: "Web は Jinja2 で HTML を返す。CLI は tabulate で表整形。Worker は DB を更新するだけで UI は持たない。",
    },
  ],

  /* --- RAG パイプライン (ADR-004 後の構成) -------------------------- */
  ragPipeline: [
    {
      step: 1,
      name: "Filing 取得",
      file: "ingestion/sec_edgar.py",
      llm: false,
      desc: "edgartools 経由で 10-K / 10-Q / 20-F / 6-K の HTML を取得し、storage_path に保存。",
    },
    {
      step: 2,
      name: "Section 抽出",
      file: "services/filing_section_extractor.py",
      llm: false,
      desc: "Regulation S-K の Item 番号は法的に固定なので、edgartools の HTMLParser で決定論的に section dict を作る。LLM 呼び出しゼロ。",
      detail: "fallback: ① HTMLParser → ② 正規表現 (10-Q MD&A 救済) → ③ 全文 (6-K)",
    },
    {
      step: 3,
      name: "LLM で構造化 JSON 生成",
      file: "services/rag_service.py + llm_client.py",
      llm: true,
      desc: "業務種別ごとに 4 回 (business_summary / mda / risk_factors / competitors)、prompt + section_text を litellm 経由で Qwen3.6 に投げる。",
      detail: "ADR-004 後: 数十回 → 4 回に削減。reasoning_content 暴走は実機検証で再現せず。",
    },
    {
      step: 4,
      name: "結果保存",
      file: "models/company_analysis.py",
      llm: false,
      desc: "company_analyses に pipeline='extractor' で書き戻す。古い PageIndex 時代の結果 (pipeline=NULL) と区別。",
    },
  ],

  /* --- ディレクトリ / 層 --------------------------------------------- */
  layers: [
    { id: "cli",          path: "cli/",          term: "cli",                role: "argparse サブコマンド集",                       inbound: "shell",            outbound: "services" },
    { id: "web",          path: "web/",          term: "webLayer",           role: "FastAPI ルート + Jinja2 + 静的アセット",        inbound: "browser",          outbound: "services" },
    { id: "services",     path: "services/",     term: "servicesLayer",      role: "業務ロジック (29 ファイル)",                    inbound: "cli / web / worker", outbound: "repositories, ingestion, llm_client" },
    { id: "ingestion",    path: "ingestion/",    term: "ingestionLayer",     role: "外部 API 取得 (6 ソース)",                       inbound: "services",         outbound: "external APIs" },
    { id: "repositories", path: "repositories/", term: "repositoriesLayer",  role: "DB CRUD のみの薄いレイヤ",                      inbound: "services / ingestion", outbound: "DB" },
    { id: "models",       path: "models/",       term: "modelsLayer",        role: "ORM 17 テーブル + enums",                       inbound: "repositories",     outbound: "—" },
    { id: "shared",       path: "shared/",       term: null,                 role: "formatters / config / logging",                 inbound: "全層",              outbound: "—" },
  ],

  /* --- Services 内の主要モジュール (29 ファイルからカテゴリ別) ------ */
  services: [
    {
      category: "RAG / 分析",
      items: [
        { file: "rag_service.py",              role: "定型 4 種 + 自由質問 (ask_question)", lines: 22686 },
        { file: "filing_section_extractor.py", role: "SEC HTML → section dict (LLM ゼロ)", lines: 8313, term: "sectionExtractor" },
        { file: "analysis_worker.py",          role: "ジョブ runner 本体", lines: 10492, term: "worker" },
        { file: "analysis_queue.py",           role: "pending → running → done の polling 制御", lines: 4438 },
        { file: "llm_client.py",               role: "litellm wrapper (quality flag / token guard)", lines: 3278, term: "litellm" },
        { file: "prompts.py",                  role: "4 種類の prompt 定義", lines: 3413 },
        { file: "pageindex/",                  role: "自由質問 (ask_question) 用の PageIndex 統合", term: "pageindex" },
      ],
    },
    {
      category: "Filing / 開示書類",
      items: [
        { file: "filing.py",         role: "Filing メタ操作", lines: 3086 },
        { file: "filing_sync.py",    role: "EDGAR/EDINET から取得→DB 反映", lines: 7277 },
        { file: "filing_content.py", role: "本文ダウンロード + 自動リカバリ (ADR-002)", lines: 8558 },
        { file: "pdf_converter.py",  role: "HTML → PDF (WeasyPrint)", lines: 3368 },
      ],
    },
    {
      category: "財務 / バリュエーション",
      items: [
        { file: "financial.py",       role: "財務データ集計", lines: 4950 },
        { file: "financial_sync.py",  role: "XBRL → 財務テーブル変換", lines: 5971 },
        { file: "metrics.py",         role: "PER/ROE/ROIC/成長率 計算", lines: 7181 },
        { file: "valuation.py",       role: "10 年バリュエーション履歴", lines: 8601 },
      ],
    },
    {
      category: "Screening",
      items: [
        { file: "screening.py",          role: "filter エンジン + sort", lines: 13073, term: "screening" },
        { file: "screening_universe.py", role: "SEC universe 構築", lines: 7693, term: "universe" },
        { file: "screening_metrics.py",  role: "Yahoo/SEC からの metric enrichment", lines: 5658 },
        { file: "screening_payload.py",  role: "API payload 整形", lines: 2467 },
      ],
    },
    {
      category: "Company / Watchlist / Target",
      items: [
        { file: "company.py",         role: "企業マスタ CRUD (CIK / EDINET コード)", lines: 6606 },
        { file: "watchlist.py",       role: "Watchlist 作成・銘柄追加", lines: 2271, term: "watchlist" },
        { file: "analysis_target.py", role: "Target 管理", lines: 1576, term: "target" },
      ],
    },
    {
      category: "Quote / Job",
      items: [
        { file: "quotes.py",                role: "株価キャッシュ", lines: 6672 },
        { file: "quote_symbols.py",         role: "ticker → quote symbol マッピング", lines: 835 },
        { file: "google_sheets_quotes.py",  role: "Google Sheets quote provider", lines: 6728 },
        { file: "job.py",                   role: "ジョブ管理 (sync / daily / valuations)", lines: 17227 },
      ],
    },
  ],

  /* --- Models (17 テーブル) ------------------------------------------ */
  models: [
    { file: "company.py",          name: "Company",           desc: "企業マスタ。CIK / EDINET コードと market を保持。" },
    { file: "filing.py",           name: "Filing",            desc: "10-K / 有報 のメタ。`storage_path` がローカル本文の場所。" },
    { file: "financial_data.py",   name: "FinancialData",     desc: "売上 / 利益 / CF 等の生財務データ。" },
    { file: "valuation.py",        name: "Valuation",         desc: "PER/PBR/EV-EBITDA の時点スナップショット。" },
    { file: "quote_price.py",      name: "QuotePrice",        desc: "現在株価キャッシュ (yfinance / Google Sheets)。" },
    { file: "price_history.py",    name: "PriceHistory",      desc: "Stooq から取った日次 OHLCV。" },
    { file: "screening.py",        name: "Screening*",        desc: "screening_universe + screening_cache の 2 テーブル。" },
    { file: "watchlist.py",        name: "Watchlist",         desc: "ユーザ作成のグループ + 銘柄。" },
    { file: "analysis_target.py",  name: "AnalysisTarget",    desc: "日次更新の対象銘柄。" },
    { file: "analysis_job.py",     name: "AnalysisJob",       desc: "Worker が拾う job キュー。pending/running/done/failed。" },
    { file: "company_analysis.py", name: "CompanyAnalysis",   desc: "RAG 分析結果。`pipeline` 列で extractor / NULL (旧 PageIndex) を区別。" },
    { file: "rag_qa_history.py",   name: "RagQaHistory",      desc: "自由質問の履歴。" },
    { file: "document_index.py",   name: "DocumentIndex",     desc: "PageIndex の構築状態キャッシュ。" },
    { file: "competitor_group.py", name: "CompetitorGroup",   desc: "z-score 偏差分析用のグループ。" },
    { file: "enums.py",            name: "(enums)",           desc: "FilingType / JobStatus / Market などの列挙。" },
    { file: "base.py",             name: "(base)",            desc: "Declarative Base + idempotent ALTER 起動時実行。" },
  ],

  /* --- Ingestion ソース --------------------------------------------- */
  ingestionSources: [
    { file: "sec_edgar.py",         name: "SEC EDGAR",          desc: "edgartools 経由で filing メタ + HTML。daily filings バッチ対応。", term: "secEdgar" },
    { file: "edinet.py",            name: "EDINET",             desc: "日本の有報・四半期報告を XBRL で取得。", term: "edinet" },
    { file: "edinet_xbrl_parser.py", name: "EDINET XBRL Parser", desc: "EDINET XBRL → FinancialData マッピング。", term: "xbrl" },
    { file: "yahoo_finance.py",     name: "Yahoo Finance",      desc: "v7 batch endpoint で 1000 銘柄 / req (ADR-003)。", term: "yahooFinance" },
    { file: "stooq.py",             name: "stooq.com",          desc: "10 年ヒストリカル OHLCV を CSV で取得 (ADR-001)。", term: "stooq" },
    { file: "fmp.py",               name: "FMP (補助)",          desc: "Financial Modeling Prep。limited usage。" },
  ],

  /* --- 技術スタック -------------------------------------------------- */
  stack: [
    { category: "Web / API",      items: ["fastapi", "uvicorn", "jinja2", "httpx"] },
    { category: "DB / ORM",       items: ["sqlalchemy", "aiosqlite"] },
    { category: "LLM / RAG",      items: ["litellm", "pageindex", "pymupdf", "pypdf"] },
    { category: "外部データ",      items: ["edgartools", "yfinance"] },
    { category: "出力 / レポート", items: ["weasyprint"] },
    { category: "開発ツール",      items: ["uv", "ruff", "pytest", "infisical"] },
  ],

  /* --- 起動 / 開発フロー --------------------------------------------- */
  startup: [
    {
      step: 1,
      title: "依存をインストール",
      cmd: "uv sync",
      note: "pyproject.toml + uv.lock を読み、`.venv/` に環境構築。",
    },
    {
      step: 2,
      title: "Web サーバー (端末 1)",
      cmd: "scripts/infisical-run uv run stock-analyze serve",
      note: "Infisical 経由で secrets を環境変数注入し uvicorn 起動。",
    },
    {
      step: 3,
      title: "分析ワーカー (端末 2)",
      cmd: "scripts/infisical-run uv run stock-analyze worker",
      note: "Web と別プロセス必須。停止中だと Web トップバーが赤バッジになる。",
    },
    {
      step: 4,
      title: "テスト & lint",
      cmd: "uv run pytest -q && uv run ruff check .",
      note: "benchmark マークはデフォルト除外。-m integration で結合テストのみ。",
    },
  ],
};
