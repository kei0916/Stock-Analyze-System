/* =====================================================================
   Progress / Design Intent
   ADRs / current-work / design intent narratives
   ===================================================================== */
export const PROGRESS = {
  /* --- Roadmap: 全体俯瞰 (P1 → P4) --------------------------------- */
  roadmap: {
    title: "Living Docs ロードマップ",
    sub: "ADR-005 で採択した 4 フェーズ計画。今は P2 を走っている。",
    currentIndex: 1,           // 0-indexed; P2 = idx 1
    phases: [
      {
        id: "P1",
        title: "基盤",
        sub: "L1 ジェネレータ / Docusaurus / Makefile",
        status: "done",
        date: "2026-05-19 マージ済",
        bullets: [
          "L1 自動生成ジェネレータ 3 種を追加",
          "Docusaurus viewer 起動",
          "Makefile docs targets 整備",
        ],
      },
      {
        id: "P2",
        title: "services 実証",
        sub: "services モジュール README + Skill 草案",
        status: "active",
        date: "2026-05-23 進行中",
        bullets: [
          "services の README を Living Docs 方式で書く",
          "maintaining-living-docs Skill の草案を作る",
          "P2 plan のチェックボックスを Run",
        ],
      },
      {
        id: "P3",
        title: "横展開",
        sub: "残り 6 モジュール + 自動 index",
        status: "next",
        date: "予定",
        bullets: [
          "ingestion / repositories / models / cli / web / shared の README",
          "adr-index ジェネレータ",
          "spec-plan-cross-ref ジェネレータ",
          "test-coverage-map ジェネレータ",
        ],
      },
      {
        id: "P4",
        title: "本番化",
        sub: "Skill 本番 + hook + 規律ファイル",
        status: "future",
        date: "予定",
        bullets: [
          "maintaining-living-docs Skill を本番化",
          "pre-commit hook を整備",
          "CLAUDE.md / AGENTS.md を整備",
        ],
      },
    ],
  },

  /* --- Now phase header (roadmap と整合) ---------------------------- */
  phase: {
    label: "Living Docs P2",
    sub: "services モジュールの README を Living Docs 方式で実証中",
    lastReviewed: "2026-05-23",
    branch: "feat/sec-section-extractor",
  },

  /* --- 進捗 (docs/current-work.md ベース) ---------------------------- */
  inFlight: [
    {
      title: "A1-A17 Refactoring Continuation",
      bullets: [
        "PR1 (A1 queue XSS) merge 済み (`742eec2`)",
        "PR2 (A2/A3/A4/A15 ADR-004 alignment) 実装済み (`996875f`..`3ee447a`)",
        "2026-05-23 local continuation: A5/A6/A7/A14, A8/A9/A10, A11/A12/A13/A16/A17 を working tree で実装",
        "Verification: `uv run pytest tests/unit -q` -> 1306 passed / `npm test` -> 36 passed / `git diff --check` clean",
        "Remaining before integration: commit split review + PR3/PR4/PR5 integration/E2E gates",
      ],
      ref: "docs/current-work.md",
    },
    {
      title: "Living Docs P2 (services README 実証)",
      bullets: [
        "着手前必読: docs/superpowers/plans/2026-05-23-living-docs-p2-services.md §0",
        "services モジュールの README を Living Docs 方式で実証する",
        "`maintaining-living-docs` Skill 草案と P2 plan を作成する",
      ],
      ref: "docs/superpowers/specs/2026-05-19-living-docs-design.md",
    },
  ],
  nextUp: [
    {
      title: "Living Docs P3",
      bullets: [
        "残り 6 モジュールへの README 展開",
        "adr-index / spec-plan-cross-ref / test-coverage-map ジェネレータ実装",
      ],
    },
    {
      title: "Living Docs P4",
      bullets: [
        "maintaining-living-docs Skill の本番化",
        "pre-commit hook 整備",
        "CLAUDE.md / AGENTS.md の整備",
      ],
    },
  ],
  recentlyLanded: [
    {
      title: "2026-05-22: プロジェクト可視化ページ",
      detail: "`/visualization` を docs-site に統合し、P2 着手前 freshness 設計事項を plan §0 に記録",
    },
    {
      title: "Living Docs P1 基盤",
      detail: "L1 ジェネレータ 3 種 / Docusaurus viewer / Makefile docs targets を追加",
      hash: "3f95613..1a745a5",
    },
    {
      title: "A1-A17 リファクタリング PR1",
      detail: "queue + XSS prevention",
      hash: "742eec2",
    },
    {
      title: "ADR-004 amendments",
      detail: "SEC 専用化 + pageindex.enabled 分離",
    },
  ],

  /* --- ADRs --------------------------------------------------------- */
  adrs: [
    {
      id: "ADR-001",
      title: "Stooq を米国株のヒストリカル株価ソースに採用",
      status: "Accepted",
      date: "2026-03",
      domain: "ingestion",
      summary: "10,000 銘柄 × 10 年の OHLCV を日次取得したいが、Yahoo は逐次 5 時間級。Stooq の EOD CSV を 1 req/s で叩く方針。",
      decision: "stooq.com を一次ソースに採用。User-Agent で識別、API キー失効はグローバル fail-fast。",
      tradeoffs: [
        "+ ヒストリカル取得が時間オーダーに収まる",
        "+ Yahoo にはレート/利用規約ペナルティが少ない",
        "− T+1 遅延を許容（ファンダ分析では問題ない）",
        "− API キーの手動再取得が必要になる場合がある",
      ],
      relatedTerms: ["stooq", "yahooFinance"],
    },
    {
      id: "ADR-002",
      title: "Filing コンテンツの DB / FS 不整合を自動リカバリ",
      status: "Accepted",
      date: "2026-03",
      domain: "ingestion",
      summary: "PageIndex 構築失敗で rollback され `storage_path` が NULL に巻き戻る一方、FS にはファイルが残る不整合が頻発。",
      decision: "`storage_path` が NULL でも FS に実体がある場合は、再ダウンロードせず DB を自動復元する症状緩和を採用。",
      tradeoffs: [
        "+ ユーザは再ダウンロード失敗ループを回避して分析を再開できる",
        "− 根本原因（同一トランザクション内の重い処理）は未解消",
        "→ 将来的に build_index を別トランザクション化する余地",
      ],
      relatedTerms: ["pageindex", "filing"],
    },
    {
      id: "ADR-003",
      title: "Yahoo v7 batch API で Screening enrichment を 60 倍高速化",
      status: "Accepted",
      date: "2026-05",
      domain: "ingestion / screening",
      summary: "`yfinance.Ticker.info` を 10,376 銘柄に並列 8 で投げて 8 分かかっていた。",
      decision: "`/v7/finance/quote?symbols=...` の 1000 銘柄まとめ取りに切り替え。11 batches × 0.7s ≈ 8 秒。",
      tradeoffs: [
        "+ 約 60 倍の速度改善 (8min → 8s)",
        "+ HTTP リクエスト数大幅減でレートリミットリスク減",
        "+ DB commit が 10,376 件 → 1 件に",
        "− v7 は sector / industry / ROE 等を返さない → これらは SEC + quote 経由に役割分担",
        "− `bulk_upsert_cache` は ON CONFLICT 列を payload に合わせて分割するロジックが必要",
      ],
      relatedTerms: ["yahooFinance", "screening"],
    },
    {
      id: "ADR-004",
      title: "定型分析を SEC 固定セクション抽出に置き換える",
      status: "Accepted",
      date: "2026-05",
      domain: "rag / services",
      summary: "PageIndex の LLM ベース TOC 抽出が Qwen3.6 の reasoning_content 暴走で全停止 (16 件中 11 失敗)。SEC は Reg S-K で章立て法定済み。",
      decision: "新サービス `FilingSectionExtractor` を追加し、edgartools.HTMLParser で 10-K/10-Q/20-F/6-K を決定論的に section dict 化。RagService の section 取得段だけを差し替え、LLM での構造化 (step 3) は維持。",
      tradeoffs: [
        "+ 定型分析の LLM 呼び出しを 数十回 → 4 回 に削減",
        "+ Qwen 思考バグや llama-server 不調が章抽出に影響しなくなる",
        "+ 処理時間: 数十分 → 数十秒〜数分",
        "− 新規依存 (edgartools / beautifulsoup4) のサプライチェーン継続監視が必要",
        "− 6-K / 古い 10-K は fallback で空セクションになることがある (UI で「該当章なし」表示)",
        "− 定型と Q&A で実装パスが 2 系統に",
      ],
      relatedTerms: ["rag", "sectionExtractor", "pageindex", "litellm", "edgartools"],
      amendments: [
        { date: "2026-05-17", note: "対象 filing を SEC 4 種に限定。EDINET PDF は別 ADR で扱う。" },
        { date: "2026-05-17", note: "定型分析を `pageindex.enabled` から独立。`ask_question` だけが PageIndex を要求。" },
      ],
    },
    {
      id: "ADR-005",
      title: "認知負荷を低減する 3 層 Living Docs 体系を導入",
      status: "Accepted",
      date: "2026-05",
      domain: "docs / process",
      summary: "spec 20+ / plan 30+ / ADR 4+ のドキュメント資産があるが、新規セッション開始時の全体像把握とドキュメント鮮度が継続的な負荷に。",
      decision: "ドキュメントを 3 層に分け、層ごとに別の鮮度保証機構を採用。L1 自動生成 / L2 AI 維持 / L3 アーカイブ。",
      tradeoffs: [
        "+ 「現状」と「歴史」が責任分離され、信頼して読む対象が明確化",
        "+ AGENTS.md と make docs-check で Claude Code 以外の AI でも規律が効く",
        "+ 既存資産 (spec/plan/ADR) を破壊しない",
        "− L2 鮮度違反が warn-only なので表面化に時間がかかる可能性",
        "− Docusaurus / gen_docs.py / manifest.yml の維持対象が増える",
      ],
      relatedTerms: [],
    },
  ],

  /* --- Plans タイムライン (ファイル名から抽出) ---------------------- */
  plansTimeline: [
    { date: "2026-03-21", title: "Phase 1 Foundation",            kind: "phase" },
    { date: "2026-03-21", title: "Phase 2 Ingestion",             kind: "phase" },
    { date: "2026-03-22", title: "Phase 3 Services",              kind: "phase" },
    { date: "2026-03-22", title: "Phase 4 CLI",                   kind: "phase" },
    { date: "2026-03-22", title: "Phase 6 LLM / RAG",             kind: "phase" },
    { date: "2026-03-22", title: "vLLM Backend Migration (検討)",  kind: "design" },
    { date: "2026-03-29", title: "Maintainability Refactoring",   kind: "refactor" },
    { date: "2026-03-29", title: "Test Coverage",                 kind: "quality" },
    { date: "2026-04-07", title: "Qwen3.5 Model Migration",       kind: "design" },
    { date: "2026-04-08", title: "Phase 7 Web UI",                kind: "phase" },
    { date: "2026-04-18", title: "Test Coverage Strengthening",   kind: "quality" },
    { date: "2026-04-20", title: "Security Hardening",            kind: "security" },
    { date: "2026-04-21", title: "Security Audit",                kind: "security" },
    { date: "2026-04-26", title: "Screening Implementation",      kind: "feature" },
    { date: "2026-04-28", title: "SEC EDGAR Daily Filings",       kind: "feature" },
    { date: "2026-04-29", title: "Google Sheets Quote Provider",  kind: "feature" },
    { date: "2026-04-30", title: "Screening Metrics",             kind: "feature" },
    { date: "2026-05-02", title: "Web UI Design System",          kind: "design" },
    { date: "2026-05-04", title: "Filing Content Root-cause",     kind: "refactor" },
    { date: "2026-05-06", title: "JSON-safe PDF Fetcher",         kind: "fix" },
    { date: "2026-05-06", title: "Review Contract Hardening",     kind: "quality" },
    { date: "2026-05-07", title: "Screening SEC Universe",        kind: "feature" },
    { date: "2026-05-09", title: "Stooq Price History",           kind: "feature" },
    { date: "2026-05-09", title: "Yahoo Batch API",               kind: "perf", adr: "ADR-003" },
    { date: "2026-05-10", title: "Background Analysis Queue",     kind: "design" },
    { date: "2026-05-11", title: "Analysis Worker Separation",    kind: "design" },
    { date: "2026-05-17", title: "PR1 Queue + XSS Prevention",    kind: "security" },
    { date: "2026-05-17", title: "PR2 Rag ADR Alignment",         kind: "refactor", adr: "ADR-004" },
    { date: "2026-05-19", title: "Living Docs P1 Foundation",     kind: "docs",   adr: "ADR-005" },
    { date: "2026-05-23", title: "Living Docs P2 Services",       kind: "docs",   adr: "ADR-005" },
  ],

  /* --- Design Intent narratives -------------------------------------
     設計上の太い意図を、文章で短くまとめる。
     ------------------------------------------------------------------ */
  intents: [
    {
      n: "01",
      title: "外部 LLM に依存しない、ローカル完結のファンダ分析",
      body: [
        "ローカル llama.cpp で Qwen3.6-27B を回せる前提で、API 鍵 / クラウド依存をシステムの中心に置かない。",
        "litellm を経由することでクラウド API へのスイッチは「設定だけ」で可能。コア設計はローカル前提。",
        "結果: ネットワーク不調 / API 値上げ / 規約変更が分析パイプラインを止めない。",
      ],
      terms: ["llm", "litellm"],
    },
    {
      n: "02",
      title: "「ユーザ操作」と「重い推論」を別プロセスに",
      body: [
        "Web は同期的に応答する操作画面、Worker は分単位の LLM 推論を回す常駐デーモン。",
        "Web から POST /api/analysis-jobs で pending を作るだけ → Worker が拾う。両者は DB だけで連携する shared-nothing 構成。",
        "Web プロセスのレイテンシが LLM 推論に巻き込まれない。Worker 落ちは Web のヘルスチェックで赤バッジになる。",
      ],
      terms: ["worker", "analysisJob"],
    },
    {
      n: "03",
      title: "Filing 解析の SPOF を LLM から外す (ADR-004)",
      body: [
        "10-K の章立ては Regulation S-K で法的に固定されている — LLM で TOC を抽出する必要はそもそもない。",
        "FilingSectionExtractor で edgartools.HTMLParser を使って決定論的に section dict 化。LLM はその先の「構造化 JSON 生成」だけに残す。",
        "LLM 呼び出しが数十回 → 4 回。Qwen の thinking バグや llama-server 不調が定型分析の章抽出に影響しなくなる。",
      ],
      terms: ["sectionExtractor", "rag"],
    },
    {
      n: "04",
      title: "Repository パターンで services を DB から独立させる",
      body: [
        "services は SQLAlchemy セッションを直接触らず、repositories 経由でしか DB にアクセスしない。",
        "services の単体テストは repositories だけモックすれば書ける。",
        "DB スキーマの変更影響は repositories 層で吸収できる構造。",
      ],
      terms: ["repositoryPattern", "repositoriesLayer", "servicesLayer"],
    },
    {
      n: "05",
      title: "外部 API 通信は ingestion に閉じる",
      body: [
        "EDGAR / EDINET / Yahoo / Stooq への HTTP は全部 ingestion/ 配下に限定。",
        "services は ingestion の関数を呼ぶだけで、httpx を直接インポートしない。",
        "外部 API のスキーマ変更や障害切り替えが ingestion 内に閉じ込められる。",
      ],
      terms: ["ingestionLayer"],
    },
    {
      n: "06",
      title: "Yahoo enrichment は per-ticker から batch に転換 (ADR-003)",
      body: [
        "10,376 銘柄を 1 件ずつ叩いて 8 分。これを `/v7/finance/quote` の 1000 銘柄まとめ取りに切り替えて 8 秒。",
        "bulk upsert は ON CONFLICT 列を payload 単位で動的に決める実装にして、既存値の NULL 上書きを防ぐ。",
        "失敗時は per-row フォールバックに切り替えるため「全件失敗」が発生しない (R7 パターン)。",
      ],
      terms: ["yahooFinance", "screening"],
    },
    {
      n: "07",
      title: "ドキュメントの 3 層化で「鮮度」を運用可能にする (ADR-005)",
      body: [
        "L1 (自動生成) / L2 (AI 維持) / L3 (アーカイブ) で責任分離。古くなりにくい層と、更新を AI に委ねる層を分ける。",
        "鮮度保証は warn-only の多層防御。CI ブロックにはしない (摩擦が大きすぎてノイズに埋もれる)。",
        "AGENTS.md と make docs-check で Claude Code に閉じない規律を確保。",
      ],
      terms: [],
    },
  ],

  /* --- Living Docs 3 層モデル (ADR-005 図解) ------------------------- */
  livingDocs: [
    {
      layer: "L1",
      name: "自動生成",
      path: "docs/generated/ (.gitignore)",
      what: "依存グラフ / モジュール index / ADR index / test-coverage map",
      freshness: "scripts/gen_docs.py で都度生成 — 古くなりようがない",
    },
    {
      layer: "L2",
      name: "AI 維持",
      path: "src/<module>/README.md, docs/system-overview.md, docs/current-work.md",
      what: "モジュール責務・依存・設計意図 / 現状フェーズ",
      freshness: "maintaining-living-docs Skill の 3 チェックポイント (開始 / 編集時 / コミット直前)",
    },
    {
      layer: "L3",
      name: "アーカイブ",
      path: "docs/superpowers/specs, docs/superpowers/plans, docs/adr/",
      what: "spec / plan / ADR の歴史",
      freshness: "Accepted 後は frontmatter / 参照整合性以外不変。後付け frontmatter 禁止。",
    },
  ],
};
