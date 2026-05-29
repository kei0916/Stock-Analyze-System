/* =====================================================================
   Terms Dictionary
   全モーダル解説の元データ。`TERMS[key]` で参照。
   ===================================================================== */
export const TERMS = {
  /* ------------------------------------------------------------------
     技術スタック (Tech Stack)
     ------------------------------------------------------------------ */
  fastapi: {
    label: "FastAPI",
    category: "tech",
    short: "Python の Web フレームワーク。型ヒントで API を高速に書ける。",
    detail: [
      "Python 製のモダンな Web フレームワーク。型ヒント (type hints) からリクエスト/レスポンスのバリデーション・ドキュメントを自動生成する。",
      "このシステムでは Web UI と HTTP API の両方を担当。HTML を Jinja2 でレンダリングするサーバーサイドレンダリング (SSR) 構成。",
      "起動コマンド: `stock-analyze serve` — 内部で uvicorn が立ち上がる。",
    ],
    links: [{ label: "公式ドキュメント", href: "https://fastapi.tiangolo.com/" }],
  },
  uvicorn: {
    label: "uvicorn",
    category: "tech",
    short: "FastAPI を動かす ASGI サーバー。",
    detail: [
      "ASGI (Asynchronous Server Gateway Interface) 仕様の Python サーバー。FastAPI アプリを実際に HTTP で受け付ける役割。",
      "`stock-analyze serve` を実行すると uvicorn がポートを開いてリクエストを待つ。",
    ],
  },
  sqlalchemy: {
    label: "SQLAlchemy",
    category: "tech",
    short: "Python の ORM。Python のクラスで DB テーブルを定義する。",
    detail: [
      "ORM (Object Relational Mapper) と呼ばれるライブラリ。SQL を直接書かず、Python のクラスとメソッドで DB を操作できる。",
      "本プロジェクトでは 2.x 系の非同期 API を使い、`models/` 配下にテーブル定義、`repositories/` 配下に CRUD を集約。",
    ],
  },
  aiosqlite: {
    label: "aiosqlite",
    category: "tech",
    short: "SQLite を非同期で扱うためのドライバ。",
    detail: [
      "標準の `sqlite3` モジュールは同期 API しかないため、async/await で使えるようにラップしたもの。",
      "FastAPI が非同期なので、DB アクセスも非同期にしてイベントループを止めないようにしている。",
    ],
  },
  jinja2: {
    label: "Jinja2",
    category: "tech",
    short: "Python の HTML テンプレートエンジン。",
    detail: [
      "`{{ value }}` や `{% for %}` のような構文で HTML を組み立てるテンプレートエンジン。",
      "サーバー側で HTML を生成して返す古典的な SSR 方式。React のようなクライアント SPA ではない。",
    ],
  },
  litellm: {
    label: "litellm",
    category: "tech",
    short: "色々な LLM を OpenAI 互換 API で統一して呼べるライブラリ。",
    detail: [
      "Anthropic / OpenAI / ローカルの llama.cpp / Ollama などをすべて同じインターフェイスで呼べる薄いラッパー。",
      "本プロジェクトでは RAG 分析のときに LLM を呼び出す層として使う。モデルを差し替えやすい。",
    ],
  },
  pageindex: {
    label: "PageIndex",
    category: "project",
    short: "PDF を意味単位で分割し、ページ範囲付きで引用できる RAG ライブラリ。",
    detail: [
      "10-K / 有価証券報告書のような長い PDF を「セクション → サブセクション → ページ範囲」のツリーに分解する。",
      "LLM に答えさせるとき、根拠ページを引用 (citation) させやすくなるのが特徴。",
      "本プロジェクトでは `services/pageindex/` 配下で任意連携。利用時は互換 PageIndex を別途導入。",
    ],
  },
  edgartools: {
    label: "edgartools",
    category: "tech",
    short: "SEC EDGAR (米国 SEC の filing DB) から filing を取ってくる Python ライブラリ。",
    detail: [
      "EDGAR の filing メタデータや 10-K/10-Q の本文を取得する非公式の SDK。",
      "本プロジェクトの ingestion 層で利用。",
    ],
  },
  pymupdf: {
    label: "pymupdf",
    category: "tech",
    short: "PDF からテキスト抽出する高速ライブラリ (MuPDF の Python バインディング)。",
    detail: ["10-K の PDF からテキストを抽出するときに使用。pypdf より高速で日本語対応も良い。"],
  },
  weasyprint: {
    label: "WeasyPrint",
    category: "tech",
    short: "HTML/CSS から PDF を生成するライブラリ。",
    detail: ["分析結果レポートを PDF 出力するときに使用。"],
  },
  pypdf: {
    label: "pypdf",
    category: "tech",
    short: "純 Python の PDF ライブラリ。PageIndex の互換用に同梱。",
    detail: [
      "PageIndex 内部で旧 `PyPDF2` 名でインポートしている箇所がある関係で、本体は `pypdf` を使いつつ `services/pageindex/compat.py` で別名を貼っている。",
    ],
  },
  yfinance: {
    label: "yfinance",
    category: "tech",
    short: "Yahoo Finance から株価・財務メタを取得する非公式ライブラリ。",
    detail: ["スクリーニング指標の enrichment ソースの一つ。日次バッチで利用。"],
  },
  httpx: {
    label: "httpx",
    category: "tech",
    short: "Python の非同期 HTTP クライアント (requests の async 版)。",
    detail: ["外部 API への通信は基本的に httpx の async インターフェイスを使う。"],
  },
  uv: {
    label: "uv",
    category: "tech",
    short: "Rust 製の高速 Python パッケージマネージャ。pip + venv の代替。",
    detail: [
      "本プロジェクトでは依存解決・仮想環境管理・スクリプト実行 (`uv run`) のすべてを uv で行う。",
      "`uv.lock` がロックファイル。",
    ],
  },
  infisical: {
    label: "Infisical",
    category: "tech",
    short: "シークレット (API キー等) を一元管理して環境変数として注入する OSS。",
    detail: [
      "`scripts/infisical-run` がラッパー。これ経由で起動すると Infisical からシークレットを取ってきて環境変数として渡してくれる。",
      "`.env` をリポジトリにコミットしなくていいのがメリット。",
    ],
  },
  ruff: {
    label: "Ruff",
    category: "tech",
    short: "Rust 製の超高速 Python リンタ + フォーマッタ。",
    detail: ["`uv run ruff check .` で lint、`uv run ruff format .` でフォーマット。"],
  },
  pytest: {
    label: "pytest",
    category: "tech",
    short: "Python のデファクトテストフレームワーク。",
    detail: ["`uv run pytest -q` で実行。マーカーで integration/benchmark を分けている。"],
  },

  /* ------------------------------------------------------------------
     概念 (Concepts)
     ------------------------------------------------------------------ */
  rag: {
    label: "RAG",
    category: "concept",
    short: "Retrieval-Augmented Generation。文書を検索 → LLM に渡して回答させる仕組み。",
    detail: [
      "LLM の知識だけに頼らず、外部文書 (このシステムでは 10-K 等) を検索して関連箇所だけを LLM のコンテキストに入れる手法。",
      "ハルシネーション (もっともらしいウソ) を減らし、根拠ページを引用できるのが利点。",
      "本プロジェクトでは PageIndex でセクション抽出 → litellm でモデル呼び出しの 2 段構成。",
    ],
  },
  llm: {
    label: "LLM",
    category: "concept",
    short: "Large Language Model。GPT や Claude のような大規模言語モデル。",
    detail: [
      "本プロジェクトの定型分析・自由質問はすべて LLM が回答を生成する。",
      "デフォルトはローカル実行 (llama.cpp + Qwen3) を想定。クラウド API も litellm 経由で差し替え可能。",
    ],
  },
  ormPattern: {
    label: "ORM",
    category: "concept",
    short: "Object Relational Mapper。DB のテーブルをプログラム言語のクラスとして扱う仕組み。",
    detail: [
      "SQL を直接書く代わりに、`session.add(Company(...))` のようにオブジェクト操作で DB を扱える。",
      "本プロジェクトは SQLAlchemy 2.x の宣言的 (declarative) スタイル。",
    ],
  },
  repositoryPattern: {
    label: "Repository パターン",
    category: "concept",
    short: "DB アクセスを 1 つの層 (repositories) に集約する設計パターン。",
    detail: [
      "services 層は DB の生クエリを書かず、`repositories/company.py` などを経由する。",
      "テストでリポジトリだけ差し替えれば services の単体テストがしやすい。",
    ],
  },
  ingestion: {
    label: "Ingestion",
    category: "concept",
    short: "外部データを取得して DB に取り込む処理層。",
    detail: [
      "本プロジェクトでは SEC EDGAR / EDINET / Yahoo Finance / Stooq から取得して DB に入れる部分が `ingestion/` 配下。",
      "整形・指標計算は services 層の責務で、ingestion は『生データを保存する』までに留める。",
    ],
  },
  asgi: {
    label: "ASGI",
    category: "concept",
    short: "Python の非同期 Web サーバー仕様。WSGI の async 版。",
    detail: ["FastAPI と uvicorn の橋渡しになるプロトコル。"],
  },

  /* ------------------------------------------------------------------
     データソース (Data Sources)
     ------------------------------------------------------------------ */
  secEdgar: {
    label: "SEC EDGAR",
    category: "source",
    short: "米国 SEC の電子開示システム。10-K (年次報告書) などをここから取る。",
    detail: [
      "米国証券取引委員会 (SEC) が運営する電子開示システム。米国上場企業はここに 10-K (年次) / 10-Q (四半期) / 8-K (臨時) を提出する義務がある。",
      "本プロジェクトでは edgartools 経由で filing 一覧と本文を取得。",
    ],
    links: [{ label: "EDGAR Search", href: "https://www.sec.gov/edgar/searchedgar/companysearch" }],
  },
  edinet: {
    label: "EDINET",
    category: "source",
    short: "日本の金融庁が運営する電子開示システム。有価証券報告書を取る。",
    detail: [
      "Electronic Disclosure for Investors' NETwork。日本の上場企業の有価証券報告書 (年次) ・四半期報告書を XBRL 形式で取得できる。",
    ],
  },
  yahooFinance: {
    label: "Yahoo Finance",
    category: "source",
    short: "株価・財務メタ・time series を提供するデータソース。",
    detail: ["スクリーニング cache の enrichment 元 (yfinance 経由)。"],
  },
  stooq: {
    label: "stooq.com",
    category: "source",
    short: "ヒストリカル株価を CSV でダウンロードできる無料データソース。",
    detail: ["週次バッチで長期株価を取得し、バリュエーション履歴に使う。"],
  },
  xbrl: {
    label: "XBRL",
    category: "source",
    short: "財務情報を機械可読にした XML ベースのフォーマット。",
    detail: [
      "eXtensible Business Reporting Language。各勘定科目に意味タグが付いており、企業をまたいで自動比較できる。",
      "EDINET / SEC のファイリングは XBRL で提供されている。",
    ],
  },

  /* ------------------------------------------------------------------
     財務用語 (Finance)
     ------------------------------------------------------------------ */
  per: {
    label: "PER",
    category: "finance",
    short: "株価収益率 (Price Earnings Ratio)。株価 ÷ EPS。",
    detail: [
      "現在の株価が、1 株あたり利益 (EPS) の何倍かを示す指標。",
      "業界平均より高い → 期待先行 / 割高、低い → 不人気 / 割安、という素朴な見方をする。",
    ],
  },
  pbr: {
    label: "PBR",
    category: "finance",
    short: "株価純資産倍率 (Price Book-value Ratio)。株価 ÷ BPS。",
    detail: [
      "1 株あたり純資産 (BPS) の何倍で取引されているか。",
      "1 倍を下回ると『解散価値より安い』と言われる古典的な目安。",
    ],
  },
  evEbitda: {
    label: "EV/EBITDA",
    category: "finance",
    short: "企業価値 ÷ EBITDA。資本構成に依らない収益力ベースの割安度指標。",
    detail: [
      "EV (Enterprise Value) = 時価総額 + 有利子負債 − 現預金。",
      "EBITDA = 営業利益 + 減価償却費。",
      "M&A や国際比較で PER より好まれる。",
    ],
  },
  psr: {
    label: "PSR",
    category: "finance",
    short: "株価売上高倍率 (Price Sales Ratio)。時価総額 ÷ 売上高。",
    detail: ["利益が出ていない成長企業のバリュエーションに使われる。"],
  },
  fcfYield: {
    label: "FCF Yield",
    category: "finance",
    short: "フリーキャッシュフロー利回り。FCF ÷ 時価総額。",
    detail: ["株主に配れるキャッシュの利回り。配当・自社株買いの原資。"],
  },
  roe: {
    label: "ROE",
    category: "finance",
    short: "自己資本利益率 (Return on Equity)。純利益 ÷ 自己資本。",
    detail: ["株主資本がどれだけ効率的に利益を生んでいるかの指標。日本企業の平均は 8〜10% 前後。"],
  },
  filing: {
    label: "Filing / 有価証券報告書",
    category: "finance",
    short: "上場企業が当局に提出する開示書類。10-K (米国) / 有報 (日本) など。",
    detail: [
      "投資判断のための一次情報。決算書・事業の状況・リスク要因・MD&A などが書かれている。",
      "本プロジェクトの分析対象はこの filing。",
    ],
  },
  cik: {
    label: "CIK",
    category: "finance",
    short: "Central Index Key。SEC が企業に振っている一意 ID。",
    detail: ["10 桁の数字 (例: AAPL は 0000320193)。EDGAR の検索キーになる。"],
  },

  /* ------------------------------------------------------------------
     プロジェクト固有 (Project-specific)
     ------------------------------------------------------------------ */
  watchlist: {
    label: "Watchlist",
    category: "project",
    short: "気になる銘柄を入れておくフォルダ。複数作れる。",
    detail: [
      "「半導体」「日本高配当」のようにテーマ別にグルーピングする使い方。",
      "Watchlist に入れただけでは自動分析は走らない。分析したいものは Target に昇格させる。",
    ],
  },
  target: {
    label: "Target / 分析ターゲット",
    category: "project",
    short: "定期分析・自動バリュエーション更新の対象に登録された銘柄。",
    detail: [
      "Watchlist が『気になるリスト』、Target は『追いかけるリスト』。",
      "Target に入った銘柄は日次ジョブで株価・バリュエーションが自動更新される。",
      "Screening の結果から `add-targets` で昇格させる流れが基本。",
    ],
  },
  screening: {
    label: "Screening",
    category: "project",
    short: "条件 (時価総額 ≥ X、ROE ≥ Y…) で銘柄を絞り込む処理。",
    detail: [
      "universe (全銘柄リスト) に対して filter をかけ、候補を絞る。",
      "結果から興味のあるものを Target に昇格させて分析パイプラインに乗せる、というのが本システムの定型フロー。",
    ],
  },
  universe: {
    label: "Universe",
    category: "project",
    short: "screening 対象の母集団 (全銘柄リスト)。",
    detail: [
      "SEC の company tickers JSON や EDINET の銘柄一覧から構築する。",
      "`screening universe refresh` で最新化する。",
    ],
  },
  worker: {
    label: "Worker / 分析ワーカー",
    category: "project",
    short: "RAG 分析ジョブをバックグラウンドで実行する別プロセス。",
    detail: [
      "Web サーバーとは別プロセスとして `stock-analyze worker` で起動する常駐デーモン。",
      "Web から登録された分析ジョブを polling し、LLM 推論を実行する。",
      "Worker が止まっていると Web トップバーに赤バッジが出て『分析ワーカーが応答していません』と表示される。",
    ],
  },
  analysisJob: {
    label: "Analysis Job",
    category: "project",
    short: "RAG 分析の 1 つの実行単位。pending → running → done で状態遷移する。",
    detail: [
      "Web からユーザが分析をリクエストすると、まず DB に Job レコードができる (pending)。",
      "Worker がそれを拾って running にし、LLM を呼び、結果を保存して done にする。",
      "Web は HTMX で状態をポーリング表示する。",
    ],
  },
  cli: {
    label: "CLI",
    category: "project",
    short: "コマンドラインインターフェイス。`stock-analyze ...` の事。",
    detail: [
      "argparse ベースのサブコマンド集 (`company`, `financial`, `screening`, `rag` …)。",
      "バッチ実行や cron からの呼び出し、開発時のデバッグの主な入口。",
    ],
  },
  servicesLayer: {
    label: "Services 層",
    category: "project",
    short: "ビジネスロジックを集約する層。CLI / Web / Discord から共通して呼ばれる。",
    detail: [
      "「指標を計算する」「分析を実行する」「universe を作る」といった処理がここに居る。",
      "DB は repositories 経由でしか触らない。外部 API は ingestion 経由でしか触らない。",
    ],
  },
  repositoriesLayer: {
    label: "Repositories 層",
    category: "project",
    short: "DB の CRUD だけを担当する薄い層。",
    detail: ["services から SQL を直接書かないようにする緩衝材。テスト時にここをモックする。"],
  },
  modelsLayer: {
    label: "Models 層",
    category: "project",
    short: "SQLAlchemy の ORM クラス (テーブル定義) が置かれる。",
    detail: ["スキーマ変更はここを起点に行う。"],
  },
  ingestionLayer: {
    label: "Ingestion 層",
    category: "project",
    short: "外部データソースから生データを取得する層。",
    detail: ["EDGAR / EDINET / Yahoo / Stooq などの外向け通信は全部ここに閉じる。"],
  },
  webLayer: {
    label: "Web 層",
    category: "project",
    short: "FastAPI + Jinja2 のサーバーサイドレンダリング UI。",
    detail: ["routes が薄く、ほぼ services を呼ぶだけになっているのが理想。"],
  },
  sectionExtractor: {
    label: "SectionExtractor",
    category: "project",
    short: "10-K から固定セクション (MD&A / Risk Factors …) を抽出するモジュール。",
    detail: [
      "SEC の 10-K は章立てが規定されているので、それを正規表現＋ヒューリスティクスで切り出す。",
      "切り出したテキストだけを LLM に渡すと、トークン数が減って分析品質が上がる。",
      "ADR-004 の決定。",
    ],
  },
};

export const TERM_CATEGORIES = {
  tech: { label: "技術スタック", color: "var(--accent)" },
  concept: { label: "概念", color: "var(--fg-2)" },
  source: { label: "データソース", color: "var(--accent)" },
  finance: { label: "金融用語", color: "var(--fg-2)" },
  project: { label: "プロジェクト固有", color: "var(--accent)" },
};

/* =====================================================================
   Additional Terms — Progress / ADR / Living Docs 文脈で出てくる語
   ===================================================================== */
Object.assign(TERMS, {
  adr: {
    label: "ADR",
    category: "concept",
    short: "Architecture Decision Record。重要な設計判断の Why を残す短文。",
    detail: [
      "Situation (状況) / Complication (問題) / Question (問い) / Decision (決定) / Consequences (結果) を 1〜2 ページにまとめる形式。",
      "本プロジェクトでは `docs/adr/` 配下に番号付きで蓄積。Accepted 後は基本不変 (L3)。",
    ],
  },
  livingDocs: {
    label: "Living Docs",
    category: "project",
    short: "ドキュメントの鮮度保証を運用可能にするための 3 層モデル。ADR-005 で採用。",
    detail: [
      "L1 (自動生成) / L2 (AI 維持) / L3 (アーカイブ) の 3 層に分け、層ごとに別の鮮度保証機構を使う。",
      "CI ブロックではなく warn-only の多層防御。Skill (Claude Code) + make docs-check + AGENTS.md で AI ツール横断の規律を確保する。",
    ],
  },
  skill: {
    label: "Skill",
    category: "concept",
    short: "Claude Code 用の再利用可能な作業手順テンプレート。",
    detail: [
      "「セッション開始時」「ファイル編集時」「コミット直前」といった節目で AI が呼び出す手順書のようなもの。",
      "Living Docs P2 で `maintaining-living-docs` Skill を草案中。",
    ],
  },
  qwen: {
    label: "Qwen3.6",
    category: "tech",
    short: "Alibaba 製のオープンソース大規模言語モデル。本プロジェクトは Q4_K_M 量子化版を使う。",
    detail: [
      "`Qwen3.6-27B-Q4_K_M.gguf` を llama.cpp 経由で動かす。",
      "ローカル GPU (RTX 4090 24 GiB) でほぼフル占有。`--ctx-size 131072 --parallel 1 --jinja --n-gpu-layers 99` が ADR-004 で確認された運用前提。",
      "`enable_thinking=false` を honor することは実機検証済み (旧 ctx 構成では reasoning_content 暴走バグあり)。",
    ],
  },
  llamacpp: {
    label: "llama.cpp",
    category: "tech",
    short: "C/C++ で書かれたローカル LLM 推論エンジン。GGUF 形式モデルを CPU/GPU で動かす。",
    detail: [
      "OpenAI 互換の HTTP サーバーモードを持ち、litellm から `openai/*` プロバイダとして叩ける。",
      "本プロジェクトのデフォルト LLM ホスト。",
    ],
  },
  regSK: {
    label: "Regulation S-K",
    category: "finance",
    short: "SEC の開示書類の章立てを定める米国規則。10-K の Item 番号はこれで法定。",
    detail: [
      "10-K の Item 1 (Business) / Item 1A (Risk Factors) / Item 7 (MD&A) など、すべて Reg S-K が定義している。",
      "ADR-004 はこの「章立てが法的に固定」という性質を使って LLM での TOC 抽出を撤廃した。",
    ],
  },
  toc: {
    label: "TOC",
    category: "concept",
    short: "Table of Contents。目次。",
    detail: [
      "PageIndex は元々 PDF から LLM を使って TOC を抽出していた。Qwen3.6 の reasoning_content 暴走バグで全停止し、ADR-004 で削除された。",
    ],
  },
  spof: {
    label: "SPOF",
    category: "concept",
    short: "Single Point of Failure。1 箇所が壊れると全体が止まる構造。",
    detail: [
      "TOC 抽出に LLM を居座らせる構造は SPOF だった。ADR-004 で LLM をパイプラインから外し、SPOF を解消した。",
    ],
  },
  docusaurus: {
    label: "Docusaurus",
    category: "tech",
    short: "Meta が OSS で出しているドキュメントサイトジェネレータ。",
    detail: ["Living Docs P1 で導入。`docs-site/` 配下が Docusaurus プロジェクト。"],
  },
  preCommitHook: {
    label: "pre-commit hook",
    category: "concept",
    short: "Git のコミット前に走るスクリプト。lint や docs-check を流すのに使う。",
    detail: ["Living Docs P4 で `make docs-check` を hook 化する想定。"],
  },
  claudeMd: {
    label: "CLAUDE.md",
    category: "project",
    short: "Claude Code がセッション開始時に必ず読むプロジェクト規約ファイル。",
    detail: ["`docs/living-docs/ai-rules.md` から同期される運用。"],
  },
  agentsMd: {
    label: "AGENTS.md",
    category: "project",
    short: "Claude Code 以外の AI (Codex 等) にも共通する規律を書くファイル。",
    detail: ["Living Docs ADR-005 が「AI ツールに閉じない規律」のために導入。"],
  },
  ixbrl: {
    label: "iXBRL",
    category: "source",
    short: "Inline XBRL。HTML 内に XBRL タグを埋め込んだ財務開示フォーマット。",
    detail: [
      "10-K / 20-F は iXBRL 形式で提出される。タグ付きデータ部分を抜き出せば機械的に section を切れる。",
      "edgartools の HTMLParser は iXBRL を含む混在 HTML から Item 単位の section を抽出できるため、ADR-004 では iXBRL 直叩きを fallback に入れず HTMLParser に統一した。",
    ],
  },
  bulkUpsert: {
    label: "bulk upsert",
    category: "concept",
    short: "複数行を 1 SQL で INSERT し、既存行は ON CONFLICT で UPDATE する操作。",
    detail: [
      "ADR-003 の `bulk_upsert_cache` は payload の key 集合ごとに INSERT を分けて、`excluded.col` での NULL 上書きを防ぐ実装。",
      "失敗時は per-row upsert に fallback する R7 パターン。",
    ],
  },
  ssr: {
    label: "SSR",
    category: "concept",
    short: "Server-Side Rendering。サーバーで HTML を完成形にして返す方式。",
    detail: ["本プロジェクトは Jinja2 で SSR。React / SPA ではない。"],
  },
  llmClient: {
    label: "LlmClient",
    category: "project",
    short: "litellm を薄くラップした内部クライアント。`completion()` がメインインターフェイス。",
    detail: [
      "quality flag で温度や max_tokens を切り替え、token guard で context overflow を防ぐ。",
      "ADR-004 後の `preflight` は PageIndex でなく LlmClient.completion で step 3 と同じ経路を probe する。",
    ],
  },
  filingTypeEnum: {
    label: "FilingType",
    category: "project",
    short: "10-K / 10-Q / 20-F / 6-K / annual_report / quarterly_report の enum。",
    detail: [
      "`models/enums.py` 定義。ADR-004 後の FilingSectionExtractor は SEC 由来の 4 種のみ扱い、EDINET の 2 種は別 ADR 待ち。",
    ],
  },
  semaphore: {
    label: "Semaphore",
    category: "concept",
    short: "並行実行数を制限する同期プリミティブ。",
    detail: ["旧 Yahoo enrichment は `max_concurrency=8` の Semaphore で並行 fetch していた (ADR-003 で batch API に置換)。"],
  },
  jobStatus: {
    label: "JobStatus",
    category: "project",
    short: "AnalysisJob の状態遷移。pending → running → done / failed。",
    detail: ["Worker が pending を picked して running に、完了で done または失敗で failed に。"],
  },
  daily: {
    label: "Daily batch",
    category: "project",
    short: "`stock-analyze jobs daily` の日次更新バッチ。",
    detail: ["filing / 財務データ / 株価キャッシュ / バリュエーション をまとめて最新化する cron 用エントリ。"],
  },
  pageindexEnabled: {
    label: "pageindex.enabled",
    category: "project",
    short: "PageIndex 統合を有効化する設定フラグ。`ask_question` 専用。",
    detail: [
      "ADR-004 Amendment で定型分析からは独立に。`enabled=false` でも定型分析 / preflight は動く。",
    ],
  },

  /* --- ADR 個別エントリ — PROGRESS.adrs と紐付く --------------------- */
  adr001: { label: "ADR-001", category: "concept", adrRef: "ADR-001",
    short: "Stooq を米国株のヒストリカル株価ソースに採用。",
    detail: ["クリックで Situation / Decision / Trade-offs を見られる。"] },
  adr002: { label: "ADR-002", category: "concept", adrRef: "ADR-002",
    short: "Filing コンテンツの DB / FS 不整合を自動リカバリ。",
    detail: ["クリックで詳細。"] },
  adr003: { label: "ADR-003", category: "concept", adrRef: "ADR-003",
    short: "Yahoo v7 batch API で Screening enrichment を 60 倍高速化。",
    detail: ["クリックで詳細。"] },
  adr004: { label: "ADR-004", category: "concept", adrRef: "ADR-004",
    short: "定型分析を SEC 固定セクション抽出に置き換え。LLM 依存の TOC 抽出を撤廃。",
    detail: ["クリックで詳細。"] },
  adr005: { label: "ADR-005", category: "concept", adrRef: "ADR-005",
    short: "認知負荷を低減する 3 層 Living Docs 体系を導入。",
    detail: ["クリックで詳細。"] },
});

