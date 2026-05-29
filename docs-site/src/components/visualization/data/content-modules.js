/* =====================================================================
   Per-module documentation
   各モジュールの 概要 / 機能詳細 / 他モジュールとの関係 / 関連 ADR

   各 features[] は次の形:
     { name, role, functions: string[], intent: string }
   name クリックでモーダルが開き、functions と intent が表示される。
   ===================================================================== */
export const MODULES = [
  /* ---------------------- cli/ --------------------------------- */
  {
    id: "cli",
    name: "CLI",
    path: "src/stock_analyze_system/cli/",
    files: 18,
    summary:
      "argparse ベースのサブコマンド集。`stock-analyze ...` の実体。バッチ実行 / cron / 開発デバッグの主な入口。",
    description: [
      "`stock-analyze` エントリポイント (`__main__.main_entry`) から呼ばれ、`cli/app.py` がサブコマンドを束ねる。",
      "各サブコマンドは services を直接呼ぶ薄いラッパー。出力整形は `cli/formatters.py` 経由で tabulate に渡す。",
      "Web/Worker と同じ services 層を共有するため、CLI から触れる機能と Web から触れる機能は基本的に同等。",
    ],
    features: [
      {
        name: "container.py",
        role: "DI コンテナ。session / repositories / services / clients を組み立てて各 CLI ハンドラに渡す。",
        functions: [
          "DB セッションファクトリを生成 (aiosqlite / sqlalchemy AsyncSession)",
          "全 Repository instance を組み立てる (Repository graph の root)",
          "Repository を inject した services instance を組み立てる",
          "httpx Client / litellm / Google API クライアントを services に注入",
          "CLI ハンドラ呼び出し前に container.build() で 1 度だけ wiring",
        ],
        intent:
          "CLI ハンドラから直接 SQLAlchemy や httpx を import すると、Web (FastAPI Depends) と CLI で別々の組み立て方が並んでしまう。同じ services を両者から呼べるよう、CLI 用の compose root を 1 ファイルに集約した。これにより、ハンドラ自身は『services を受け取って業務を呼ぶだけ』の薄いラッパーに保てる。",
      },
      {
        name: "serve.py",
        role: "`stock-analyze serve` — uvicorn 起動。",
        functions: [
          "argparse で --host / --port / --reload / --workers を受け取る",
          "web.app:create_app() を渡して uvicorn を起動",
          "起動前に Infisical / .env を load しておく",
          "dev (--reload) と prod の設定差分を吸収",
        ],
        intent:
          "`uvicorn web.app:app` を直接叩くと環境変数 load の順序や log 設定が CLI 経由と揃わない。Web を起動する経路は必ずこのコマンドに通す、というルールを成立させるために置いている。",
      },
      {
        name: "worker.py",
        role: "`stock-analyze worker` — RAG ジョブの常駐 polling。",
        functions: [
          "analysis_queue をポーリングし pending → running → done|failed に進める",
          "SIGTERM / SIGINT で in-flight ジョブの完了を待ってから停止",
          "lease 期限切れジョブの再投入",
          "heartbeat を書き込み Web の Worker 死活表示に反映",
        ],
        intent:
          "Web プロセスから LLM 推論を呼ばないという ADR-004 の方針を支える実体。FastAPI のリクエスト時間と GPU を占有する推論時間を別プロセスに分離することで、Web のレスポンス SLA を Worker の負荷と切り離す。",
      },
      {
        name: "rag.py",
        role: "RAG 関連サブコマンド (`health` / `index` / `analyze` / `ask` / `show`)。",
        functions: [
          "`rag health` で Ollama / LM Studio / litellm への疎通確認",
          "`rag index` で PageIndex を 1 filing 単位で構築",
          "`rag analyze` で 4 種定型分析を 1 銘柄に対し直接実行",
          "`rag ask` で自由質問 (PageIndex 経由)",
          "`rag show` で過去の company_analyses をキャッシュ表示",
        ],
        intent:
          "Web/Worker と同じ services を CLI から叩ける窓口。新しい LLM モデルや filing を入手したときに、Web UI を経由せずに動作確認とプロンプト改修を素早く回せるようにしてある。",
      },
      {
        name: "screening.py",
        role: "screening 関連 (`universe refresh` / `refresh` / `run` / `add-targets` / `fields`)。",
        functions: [
          "`universe refresh` で universe の組み換え (流動性 / Market)",
          "`refresh` で screening cache を Yahoo batch 経由 enrichment",
          "`run` でフィルタ式を評価しランキング表示",
          "`add-targets` で結果上位を AnalysisTarget に昇格",
          "`fields` で利用可能なフィルタ列の一覧",
        ],
        intent:
          "Web の screening 画面でやることを CLI でも完全再現できるようにしておく。cron による夜間バッチと、ユーザーの手動確認の両方を同じ呼び出し面で済ませる狙い。",
      },
      {
        name: "jobs.py",
        role: "`jobs sync` / `jobs daily` / `jobs valuations` の日次バッチ系。",
        functions: [
          "`jobs sync` で SEC / EDINET から filing メタを差分同期",
          "`jobs daily` で株価更新 → valuations 再計算 → screening cache 更新",
          "`jobs valuations` で価格変動ありの銘柄だけ valuation を作り直す",
          "`--json` で構造化出力 (cron 監視向け)",
        ],
        intent:
          "cron からの夜間バッチ実行を前提に、ステップごとに失敗してもパイプライン全体は止めない設計。人間向けの tabulate と、機械可読の JSON を 1 フラグで切り替えられるようにしてある。",
      },
      {
        name: "stooq.py",
        role: "Stooq からのヒストリカル株価ダウンロード。",
        functions: [
          "Stooq EOD CSV を 1 req/s で取得 (HTTP レート制限遵守)",
          "--skip-existing で既存日付をスキップ",
          "--dry-run で取得計画のみ表示",
          "認証エラー / 404 では fail-fast (silent skip しない)",
        ],
        intent:
          "ADR-001 で「個別株 EOD は Stooq に寄せる」と決めたため、その実行を CLI 1 コマンドで再現可能にしておく。夜間バッチで欠損が静かに広がる事故を防ぐため、失敗時は明示的に noisy に止まる方を選んでいる。",
      },
      {
        name: "filings.py",
        role: "filing 一覧・ダウンロード。",
        functions: [
          "同期済み filing の一覧表示 (会社 × 種別 × 期間)",
          "個別 filing の HTML を再ダウンロード",
          "storage_path の存在確認とリペア起動",
        ],
        intent:
          "Web の filings タブで「壊れている」と表示された filing を、開発者が CLI 経由で直接調査するための診断窓口。Web UI に診断機能を盛り込まないことで、Web 側はシンプルに保つ。",
      },
      {
        name: "valuation.py",
        role: "PER レンジ / 偏差分析 (z-score)。",
        functions: [
          "10 年月次の PER レンジ (min/max/median) を表示",
          "CompetitorGroup ベースの z-score 偏差分析",
          "--period quarterly で四半期切替",
          "通貨換算オプション",
        ],
        intent:
          "services/valuation.py の戻り値をそのまま見るための薄いラッパー。--json 出力構造は services が返す dict と 1:1 にし、外部ツール (Notebooks 等) との繋ぎ口としても使えるようにしている。",
      },
      {
        name: "company.py / financial.py / quotes.py / target.py / watchlist.py",
        role: "それぞれ services の同名モジュールへのラッパー。",
        functions: [
          "対応する service メソッドへの 1:1 マッピング",
          "引数を argparse から受け取り services に渡すだけの薄さ",
          "`--json` で構造化出力",
          "tabulate 経由の人間向けテーブル",
        ],
        intent:
          "「CLI で操作可能なドメイン操作」を services 関数の集合と一致させる。CLI 固有のビジネスロジックを書かせないことで、Web と CLI の機能セットが乖離していくのを構造的に防ぐ。",
      },
      {
        name: "formatters.py / helpers.py",
        role: "tabulate 経由のテーブル整形・JSON 出力 (`--json` フラグ対応)。",
        functions: [
          "tabulate の column フォーマット定義 (右寄せ / 桁区切り)",
          "`--json` フラグの共通ハンドリング",
          "NO_COLOR 環境変数への対応",
          "shared/formatters.py の数値フォーマッタを CLI 用にラップ",
        ],
        intent:
          "shared/formatters.py が『数値そのものの整形』を担うのに対し、ここは『CLI 出力のテーブル構造』を扱う。両者の責任を切り分けて、Web 側でも shared/formatters.py を再利用できるようにする。",
      },
    ],
    deps: {
      calls: ["services", "shared"],
      calledBy: ["user shell", "cron (scripts/cron-*.sh)"],
      note: "DB / 外部 API には直接アクセスしない (必ず services 経由)。",
    },
    adrs: [],
    terms: ["cli", "servicesLayer", "infisical", "daily"],
  },

  /* ---------------------- web/ --------------------------------- */
  {
    id: "web",
    name: "Web (FastAPI)",
    path: "src/stock_analyze_system/web/",
    files: 11,
    summary:
      "FastAPI + Jinja2 の SSR Web UI と内部 API。POST /api/analysis-jobs で Worker 向けジョブを作るだけで、LLM は呼ばない。",
    description: [
      "`web/app.py` が FastAPI アプリを組み立て、`routes/*.py` がエンドポイントを登録する。",
      "認証は password-only セッション (`web/auth.py` + itsdangerous)。Worker 死活は ヘルスチェック経由でトップバーに表示。",
      "テンプレートは `web/templates/`、静的アセットは `web/static/`。",
    ],
    features: [
      {
        name: "app.py",
        role: "FastAPI アプリ組み立て + middleware + 例外ハンドラ。",
        functions: [
          "create_app() で FastAPI インスタンスを生成",
          "routes/* の include_router で URL を登録",
          "Session middleware (itsdangerous) と CORS を組み込む",
          "404 / 500 / HTTPException ハンドラで Jinja2 エラーページを返す",
          "lifespan で DB セッションファクトリと httpx Client pool を作る",
        ],
        intent:
          "合成と横断的関心 (auth / error / lifespan) だけをここに置き、各 route ファイルは『ドメイン 1 つ + 関数いくつか』に収まるようにする。エラー応答の体裁を 1 か所に集約することで、各 route は `raise HTTPException` を書くだけで一貫した UI に着地する。",
      },
      {
        name: "auth.py",
        role: "セッション認証 (Cookie + itsdangerous)、password-only。",
        functions: [
          "GET /login / POST /login のフォーム処理",
          "itsdangerous の signed cookie でセッション ID を発行",
          "`Depends(require_user)` を全 route に必須化する依存関数",
          "POST /logout でセッション失効",
        ],
        intent:
          "個人向けツールでマルチユーザーは想定しないため、ユーザー名なしの password-only に意図的に切り詰めている。本格的な OAuth / SSO は将来差し込みやすいよう、依存性 `require_user` で要件を表現する形にした。",
      },
      {
        name: "dependencies.py",
        role: "FastAPI Depends で services を渡す DI 層。",
        functions: [
          "get_db / get_company_service / get_screening_service など",
          "lifespan で生成した services を request scope に渡す",
          "request 毎に async session を yield / close",
          "認証必須依存 (require_user) の合成",
        ],
        intent:
          "FastAPI Depends を通して services を渡すことで、各 route 関数のシグネチャを見れば必要な依存が読み取れるようにする (DI as documentation)。テスト時はここを差し替えるだけで services を mock できる。",
      },
      {
        name: "routes/dashboard.py",
        role: "GET / · ダッシュボード。Target / Worker 状態。",
        functions: [
          "現在の AnalysisTarget の一覧と直近の進捗",
          "Worker の heartbeat と pending ジョブ数",
          "最終同期時刻 / 銘柄数 / 直近の失敗",
          "Quick actions (Sync / Screen / RAG) へのリンク",
        ],
        intent:
          "起動直後に『今何が動いていて、何が止まっているか』を 1 画面で把握できることを最優先。新規ユーザー向けのウェルカム文言は意図的に排し、状態表示と既存リソースへの導線だけに絞っている。",
      },
      {
        name: "routes/stocks.py",
        role: "GET /stocks/{id} · 5 タブの銘柄詳細。",
        functions: [
          "5 タブ (財務 / バリュエーション / 指標 / 分析 / ファイリング) のサーバ側レンダリング",
          "タブ切替は HTMX で部分入替 (URL は query param で同期)",
          "Chart.js に渡す系列を Jinja2 で JSON 埋め込み",
          "Filing 一覧から POST /api/analysis-jobs へ繋ぐ",
        ],
        intent:
          "1 銘柄の分析体験を 1 URL に集約する。タブを path ではなく query にしたのは、同じ URL に深掘り状態を載せておくことで、ブラウザバック / 共有リンクで戻ったときに同じビューを再現できるようにするため。",
      },
      {
        name: "routes/screening.py",
        role: "GET /screening · 条件絞り込み + Target 昇格。",
        functions: [
          "フィルタ条件 form と保存済みフィルタの呼び出し",
          "HTMX で結果テーブルだけ swap (full reload なし)",
          "結果行の選択 → POST で AnalysisTarget 昇格",
          "結果列の入れ替え (`screening fields` と対称)",
        ],
        intent:
          "入力 → 結果テーブル更新を full-reload なしで回せることが要件。結果のテンプレートを独立した partial に切り出すことで、HTMX 部分入替と CLI の `screening run` の出力が同じ構造を共有する。",
      },
      {
        name: "routes/analysis_jobs.py",
        role: "POST /api/analysis-jobs · pending を作るだけ。Worker が拾う。",
        functions: [
          "filing_id + analysis_type のバリデーション",
          "ANALYSIS_FILING_TYPES (10-K/10-Q/20-F/6-K) の whitelist チェック",
          "同一 filing + 同一 type の duplicate pending を抑止",
          "202 Accepted を即返却 (LLM は呼ばない)",
        ],
        intent:
          "Web プロセスから LLM を呼ばないという ADR-004 方針を route レベルで強制する境界。長時間処理を request-response に乗せないことで、Web のレスポンス時間と Worker の GPU 占有を完全に分離する。",
      },
      {
        name: "routes/jobs.py",
        role: "GET /jobs · 分析ジョブの進捗ポーリング。",
        functions: [
          "自分の AnalysisJob 一覧 (pending / running / done / failed)",
          "HTMX による定期 polling で行を更新",
          "failed 行を expand してエラー文 / pipeline / model を表示",
          "skipped / extraction_error / index_build_error の区別表示",
        ],
        intent:
          "Worker と Web の間に WebSocket や pub/sub を持たない選択。1 銘柄あたり走るジョブはせいぜい数件のため、polling で十分という割り切り。インフラを増やさないことで運用負担を抑える。",
      },
      {
        name: "routes/api.py",
        role: "JSON API。ANALYSIS_FILING_TYPES の制約あり (ADR-004 amendment)。",
        functions: [
          "Watchlist / Target / Screening / Filing の GET エンドポイント",
          "POST /api/analysis-jobs の薄い JSON 版",
          "ANALYSIS_FILING_TYPES を共通定数で参照しレスポンスにも明記",
          "認証必須 + pagination",
        ],
        intent:
          "ADR-004 amendment の whitelist 制約を API レベルで強制することで、フロントエンドや外部 CLI から同じ制約が読み取れるようにする。クライアントごとの実装差を防ぐ。",
      },
      {
        name: "routes/rag.py / targets.py / watchlists.py / auth.py",
        role: "残りのドメインルート。",
        functions: [
          "各ドメインの GET / POST / DELETE ハンドラ",
          "Jinja2 テンプレートのレンダリング",
          "form / query の validation (pydantic)",
          "成功 / 失敗で flash メッセージ更新",
        ],
        intent:
          "1 ファイル 1 ドメインのページオブジェクト的構成。500 行を超えたら分割するという暗黙ルールで route の肥大化を防ぎ、ドメインが増えてもこの層が太らないようにしている。",
      },
      {
        name: "static/app.js",
        role: "クライアント側の最小スクリプト。skipped / extraction_error / index_build_error を区別表示。",
        functions: [
          "htmx:afterSwap で toast 表示と focus 移動",
          "AnalysisJob 結果の skipped / extraction_error / index_build_error の文言マッピング",
          "dark/light テーマの localStorage 同期",
          "Alpine.js の起動と最小限の状態",
        ],
        intent:
          "状態管理は SSR 側に寄せる方針なので、ここに業務ロジックを置かない。クライアントは『描画の補助』だけに留めることで、JS バンドルを増やさず、F5 で全部リセットされても何も壊れない状態を維持する。",
      },
    ],
    deps: {
      calls: ["services", "shared"],
      calledBy: ["browser"],
      note: "Worker とは DB 経由でのみ通信する (shared-nothing)。",
    },
    adrs: ["ADR-004"],
    terms: ["webLayer", "fastapi", "jinja2", "ssr", "worker", "analysisJob", "pageindexEnabled"],
  },

  /* ---------------------- services/ ---------------------------- */
  {
    id: "services",
    name: "Services",
    path: "src/stock_analyze_system/services/",
    files: 29,
    summary:
      "業務ロジックの集約点。指標計算 / Filing 同期 / RAG パイプライン / Screening などをここに置き、CLI / Web / Worker から共通で呼ばれる。",
    description: [
      "DB アクセスは必ず repositories 経由、外部 API アクセスは必ず ingestion 経由。services 自身は httpx も sqlalchemy session も直接触らない (理想)。",
      "ADR-004 で RAG パイプラインの section 抽出段が PageIndex → FilingSectionExtractor に置き換わったのが直近の最大の変更。",
    ],
    features: [
      {
        name: "rag_service.py",
        role: "定型 4 種分析 + ask_question (自由質問) を束ねる主役。step 3 は LlmClient 直叩き。",
        functions: [
          "filing → section dict (extractor) → prompt → LlmClient → 結果 dict",
          "business_summary / risk_factors / mda / competitors の 4 種を順序実行",
          "step ごとに company_analyses に書き戻し、途中で落ちても部分回復",
          "ask_question は PageIndex 経由で引用つき回答",
          "skipped / extraction_error / index_build_error を JobStatus に明示",
        ],
        intent:
          "PageIndex / extractor のどちらを使うかを切り替えられるよう、section dict を作る側と prompt を組む側を完全分離した。LLM の 1 step 失敗で全 step を捨てない設計は、ローカル LLM の不安定さを前提とした実用上の妥協点。",
      },
      {
        name: "filing_section_extractor.py",
        role: "10-K / 10-Q / 20-F / 6-K の HTML を edgartools で section dict に分解 (LLM ゼロ)。",
        functions: [
          "edgartools の Item parser で Reg S-K 項目を抽出",
          "TOC anchor から section の本文 HTML を取得",
          "filing_type ごとの section スキーマ定義 (10-K vs 20-F 等)",
          "本文を {section_id: text} の dict で返す",
        ],
        intent:
          "ADR-004 の中核。PageIndex (LLM 駆動 TOC) は遅く高コストだったため、決定論的に取れるところは決定論で取り、LLM はあくまで要約・抽出にだけ使う構造にした。filing 種別の固定スキーマに責任を絞ることで、保守性とテスト可能性を担保。",
      },
      {
        name: "analysis_worker.py",
        role: "Worker プロセスの本体。pending → running → done の状態遷移を実行。",
        functions: [
          "analysis_queue から 1 件 lease",
          "rag_service の 4 step を順に呼ぶ",
          "失敗時は JobStatus.failed + error_text",
          "cancel signal で in-flight ジョブを安全に終了",
          "heartbeat 書き込みで Web に死活を露出",
        ],
        intent:
          "状態遷移ロジックをここに閉じることで、CLI worker / 将来の k8s worker / debug 用 in-process 実行 のいずれもこの関数を呼ぶだけで済む。Worker の物理形態を切り替えても挙動を 1 か所で管理できる。",
      },
      {
        name: "analysis_queue.py",
        role: "ジョブの polling / lease ロジック。",
        functions: [
          "pending を 1 件 lease (SELECT ... FOR UPDATE SKIP LOCKED 相当)",
          "lease 期限切れジョブの再投入",
          "重複 pending の検出",
          "queue の意味論 (pending / running / done / failed の遷移条件)",
        ],
        intent:
          "DB をキューとして使う設計。Redis / RabbitMQ を持ち込まないことで構築コストとオペレーションを抑え、shared-nothing を維持する。複数 Worker を将来並列起動できるよう、行ロックでの安全な lease を成立させる。",
      },
      {
        name: "llm_client.py",
        role: "litellm の薄いラッパー。`completion(prompt, quality=True)` がメイン I/F。",
        functions: [
          "litellm.completion() の呼び出し集約",
          "quality=True で大きめモデル、False で速いモデルへ振り分け",
          "retry / timeout / トークン使用量ログ",
          "Ollama / LM Studio / OpenAI を ENV で切替",
        ],
        intent:
          "services から見て LLM プロバイダ差を吸収する単一窓口。呼び出し側 (rag_service) のコードは LLM の物理を意識せずに済み、Ollama → LM Studio → クラウドの差し替えが ENV 変更だけで完結する。",
      },
      {
        name: "prompts.py",
        role: "business_summary / risk_factors / mda / competitors 4 種の prompt 定義。",
        functions: [
          "4 種のプロンプトテンプレート文字列",
          "section dict から必要箇所を埋め込むレンダラ",
          "JSON 出力 schema の指定 (downstream の parse 用)",
          "prompt_version の管理",
        ],
        intent:
          "プロンプトの変更で挙動が変わる箇所を 1 ファイルに集約し、git diff だけで A/B 比較できるようにする。company_analysis テーブルの prompt_version とペアで運用し、過去結果との互換性を追跡可能にする。",
      },
      {
        name: "pageindex/",
        role: "ask_question 用に残された PageIndex 統合 (定型分析からは独立)。",
        functions: [
          "PageIndex API クライアント",
          "1 filing 単位のインデックス構築 / 状態管理",
          "ask_question 経由の引用つき検索",
          "構築失敗時のリトライと状態書き戻し",
        ],
        intent:
          "ADR-004 で定型分析からは外したが、自由質問では PageIndex の page-range 引用が UX 上強い。両者のパイプラインを切り離すことで、定型分析の安定性と自由質問の表現力を独立に進化させられる。",
      },
      {
        name: "screening.py + screening_universe.py + screening_metrics.py",
        role: "screening フィルタ / universe 構築 / metric enrichment の 3 役割を分けて持つ。",
        functions: [
          "universe.py が universe メンバーシップを組み立てる (Market / 流動性)",
          "metrics.py が PER / PBR / PSR / FCF Yield 等を最新値で enrich",
          "screening.py が filter 式を評価しランキング化",
          "結果は ScreeningCache に永続化",
        ],
        intent:
          "3 役割を 1 ファイルに混ぜると、Yahoo batch (ADR-003) のような I/O 局所最適化と filter の純粋関数化が両立しなくなる。役割を物理ファイルで分けることで、各層を独立に変えられるようにする。",
      },
      {
        name: "valuation.py / metrics.py",
        role: "PER/PBR/EV-EBITDA の 10 年履歴と PER レンジ / z-score 偏差。",
        functions: [
          "valuation.py: 10 年月次のバリュエーション履歴と PER レンジ (min/max/median)",
          "metrics.py: TTM / Forward の各指標を最新値で算出",
          "CompetitorGroup ベースの z-score 偏差分析",
          "通貨換算と単位スケール",
        ],
        intent:
          "『同じ銘柄を時系列で見る (valuation)』と『同じ時点で複数銘柄を見る (metrics)』を別ファイルに切り分け、画面 (バリュエーションタブ / 指標タブ) と 1:1 対応させる。読み手が認知負荷少なく辿れる構造にする狙い。",
      },
      {
        name: "filing_sync.py / filing_content.py",
        role: "Filing メタ + 本文の取得・保存。ADR-002 の自動リカバリ。",
        functions: [
          "SEC / EDINET から filing メタを取得し DB upsert",
          "本文 HTML をローカル保存し storage_path を記録",
          "storage_path が欠損 / 壊れている場合の自動再取得",
          "本文取得失敗時の状態遷移",
        ],
        intent:
          "『Filing が落ちている』は RAG パイプライン最大の躓きポイント。ADR-002 で『無ければ作り直す』を sync 側に持たせ、上位サービス (rag_service) から見て filing は常にあるという前提を成立させる。",
      },
      {
        name: "job.py",
        role: "sync / daily / valuations の上位ジョブを組み立てる。",
        functions: [
          "sync (filing 同期) / daily (株価 + valuations + screening) / valuations (再計算)",
          "ステップごとの成否ログを集約",
          "部分失敗でもパイプラインは継続",
          "CLI / cron からの実行を想定した戻り値構造",
        ],
        intent:
          "cron 呼び出しの実体をここに集約。CLI サブコマンド ↔ このファイルの関数 を 1:1 にしておくことで、cron スクリプトを書き換えずに挙動を CLI で再現できるようにしている。",
      },
      {
        name: "google_sheets_quotes.py / quotes.py",
        role: "株価キャッシュ 2 系統。",
        functions: [
          "Yahoo / Stooq 由来の現在値を quotes.py が QuotePrice テーブルに upsert",
          "Google Sheets API 経由の現在値取得 (sheets)",
          "TTL ベースの自動再取得",
          "source カラムで由来を区別",
        ],
        intent:
          "Yahoo の rate limit / API キー切れに当たったときの逃げ道として、ユーザーが Google Sheets を二次ソースに使える経路を残している。両者を等価に扱えるよう、書き込み先テーブルと repository を共通化。",
      },
      {
        name: "company.py / watchlist.py / analysis_target.py",
        role: "ドメインの基本 CRUD ファサード。",
        functions: [
          "各ドメインの CRUD を repository 経由で提供",
          "Target 昇格などの業務ルールを集約",
          "ドメインを跨ぐ検証 (会社不在で Target を作らない 等)",
          "Web / CLI から呼ばれる単一の API 面",
        ],
        intent:
          "CLI / Web / Worker が同じ業務ルールに従うように、repository より上に必ず services を挟む方針の表現。1 ドメイン 1 ファイルにして、ドメイン増加時にファイルを増やすだけで済むようにしている。",
      },
    ],
    deps: {
      calls: ["repositories", "ingestion", "shared", "(LLM via litellm)"],
      calledBy: ["cli", "web", "worker"],
      note: "DB セッション・外部 API は直接触らない。LLM だけ litellm 経由で例外的に services 内から呼ぶ。",
    },
    adrs: ["ADR-002", "ADR-004"],
    terms: ["servicesLayer", "rag", "sectionExtractor", "worker", "llmClient", "litellm", "pageindexEnabled"],
  },

  /* ---------------------- ingestion/ --------------------------- */
  {
    id: "ingestion",
    name: "Ingestion",
    path: "src/stock_analyze_system/ingestion/",
    files: 9,
    summary:
      "外部データソースとの境界層。SEC EDGAR / EDINET / Yahoo / Stooq などの fetch をここに閉じる。",
    description: [
      "外向き HTTP / SDK 呼び出しはすべてここに集約する。services は ingestion の関数を呼ぶだけで、httpx を直接 import しない。",
      "ADR-001 (Stooq) / ADR-002 (filing リカバリ) / ADR-003 (Yahoo batch) がこの層の設計判断。",
    ],
    features: [
      {
        name: "base.py",
        role: "共通の HTTP ヘッダー / リトライ / User-Agent / 例外正規化。",
        functions: [
          "shared.clients から httpx Client を受け取って共通設定で初期化",
          "User-Agent (SEC が要件化) の埋め込み",
          "リトライ (指数バックオフ + jitter)",
          "HTTP / Timeout / DNS 例外を UpstreamError に正規化",
        ],
        intent:
          "『外部 API は ingestion を通る』という制約を成立させる土台。services 側から見た失敗を 1 つの例外型に揃えることで、上位の error handling を統一できる。",
      },
      {
        name: "sec_edgar.py",
        role: "edgartools 経由で filing メタ + 本文取得。daily filings バッチ対応。",
        functions: [
          "edgartools の Company / Filings インタフェース呼び出し",
          "daily filings の差分取得",
          "本文 HTML / iXBRL 取得",
          "CIK ↔ ticker 解決",
        ],
        intent:
          "SEC が要求する UA / レート制限 / robots を edgartools に委譲する。SDK が壊れても他の ingestion ファイルに波及しないよう、SEC 関連は完全にこのファイルに閉じる構成。",
      },
      {
        name: "edinet.py + edinet_xbrl_parser.py",
        role: "EDINET の有報・四半期報告と XBRL → FinancialData マッピング。",
        functions: [
          "EDINET API での書類一覧 / 取得",
          "iXBRL を XBRL に展開",
          "EDINET タクソノミ → 共通 FinancialData の正規化",
          "連結優先 (個別フォールバック)",
        ],
        intent:
          "米国 SEC とは別タクソノミなので、FinancialData の正規化責任を edinet 側に持たせる。services から見れば日米で同じ FinancialData を読むだけ、という抽象を提供する。",
      },
      {
        name: "yahoo_finance.py",
        role: "v7 batch API (`/v7/finance/quote`, 1000 銘柄/req) と per-ticker `Ticker.info` の両方を持つ。",
        functions: [
          "/v7/finance/quote で 1000 銘柄/req の batch quote",
          "yfinance の Ticker.info で銘柄詳細 (sector / industry 等)",
          "semaphore で同時接続制限",
          "失敗銘柄の per-ticker fallback",
        ],
        intent:
          "ADR-003 で『screening の現在値 enrichment は v7 batch を使う』と決めたため、batch を 1st citizen にしつつ、銘柄個別の詳細情報には従来通り Ticker.info を使う 2 モード設計にしている。",
      },
      {
        name: "stooq.py",
        role: "Stooq EOD CSV を 1 req/s で取得。skip-existing / dry-run / API キー失効時の fail-fast 付き。",
        functions: [
          "Stooq CSV のダウンロードと parse",
          "1 req/s のレート制限",
          "skip-existing / dry-run のオプション",
          "認証失効 / 404 で fail-fast",
        ],
        intent:
          "ADR-001 で『個別株 EOD は Stooq に寄せる』と決めた。夜間バッチで EOD が静かに欠損するのが最大のリスクなので、明示的に noisy に落ちる方針を組み込んでいる。",
      },
      {
        name: "fmp.py",
        role: "Financial Modeling Prep の補助ソース (limited usage)。",
        functions: [
          "FMP の補助 endpoint (一部の指標 / カレンダー)",
          "rate / cost を考慮した最小限の呼び出し",
        ],
        intent:
          "SEC / Yahoo で取れないニッチデータの補完目的。常時依存しないことで FMP の API 変更にも耐え、いつでも切り離せる状態を保つ。",
      },
      {
        name: "xbrl/",
        role: "XBRL 解析の共通ロジック。",
        functions: [
          "concept / context / unit の解析",
          "連結 / 個別の判定",
          "会計期間の正規化 (FY / Q / instant)",
          "SEC / EDINET 両用のヘルパ",
        ],
        intent:
          "SEC と EDINET でタクソノミは違うが『会計事実 + 期間 + 単位』という三項関係は共通。ここで共通中間形式に正規化し、上位 (services) からは単一の形で扱えるようにする。",
      },
    ],
    deps: {
      calls: ["external HTTP (httpx)", "shared.clients"],
      calledBy: ["services"],
      note: "DB は触らない。取得結果を返すだけで、保存は services 側で行う。",
    },
    adrs: ["ADR-001", "ADR-002", "ADR-003"],
    terms: ["ingestionLayer", "secEdgar", "edinet", "xbrl", "ixbrl", "yahooFinance", "stooq", "edgartools", "bulkUpsert", "semaphore"],
  },

  /* ---------------------- repositories/ ------------------------ */
  {
    id: "repositories",
    name: "Repositories",
    path: "src/stock_analyze_system/repositories/",
    files: 15,
    summary:
      "DB CRUD だけを担当する薄い層。SQLAlchemy セッションは services から直接触らせず、ここに集約する。",
    description: [
      "`base.py` で共通の async session 操作と filter helper を提供。各 repository はそれを継承する。",
      "ADR-003 の bulk_upsert_cache (Yahoo enrichment) はここの screening.py 内に居る。",
    ],
    features: [
      {
        name: "base.py",
        role: "Generic Repository。session 管理、get_by_id / list / 共通 filter 群。",
        functions: [
          "Generic Repository[Model, ID] の親クラス",
          "async session を constructor で受け取る (DI フレンドリー)",
          "get_by_id / list / count / 共通 filter helper",
          "upsert helper",
        ],
        intent:
          "Repository パターンの SoT。session を repository が自前で作らせないことで、services が同一トランザクションで複数 repository を呼べるようにする。",
      },
      {
        name: "company.py",
        role: "Company マスタの CRUD。CIK / EDINET コードのユニーク制約を扱う。",
        functions: [
          "ticker / cik / edinet_code いずれかでの lookup",
          "Market 別 list",
          "UNIQUE 違反を専用例外に変換",
          "company_id 解決の共通インタフェース",
        ],
        intent:
          "Company は他のほぼ全テーブルから FK で参照される基盤。重複作成を防ぐ unique 制約違反を repository レベルで吸収し、上位は誤りを早期に検出できるようにする。",
      },
      {
        name: "filing.py",
        role: "Filing メタの CRUD。`storage_path` 復元の query 等。",
        functions: [
          "company × filing_type × period の lookup",
          "storage_path が欠損している filing の一覧",
          "最新 filing の取得",
          "同期日時の更新",
        ],
        intent:
          "filing_sync が『無ければ作る、壊れていれば直す』を素早く判断できるよう、ピンポイントの query メソッドを揃える。services 側で複雑な SQL を書かせない。",
      },
      {
        name: "financial.py",
        role: "FinancialData のクエリ + 期間フィルタ。",
        functions: [
          "期間 (FY / Q) フィルタつき list",
          "連結優先のクエリ",
          "TTM 集計用 query",
          "最新 N 期間の取得",
        ],
        intent:
          "『最新の TTM 売上を 1 行取りたい』が頻出ユースケース。Python 側で 4 期間を集計するコードを書かず、SQL の集計関数で完結させてホットパスのレイテンシを抑える。",
      },
      {
        name: "valuation.py",
        role: "Valuation の時系列クエリ。10 年履歴の組み立てを支える。",
        functions: [
          "月次 10 年の時系列クエリ",
          "min/max/median のウィンドウ集計",
          "最新値の取得",
          "通貨換算前提のクエリ",
        ],
        intent:
          "画面の PER レンジが SQL のウィンドウ集計 1 本で完結するようにしておく。アプリ側で 120 行をループする集計コードを services に置きたくないため、ここで完結させる。",
      },
      {
        name: "price_history.py",
        role: "Stooq 由来の日次 OHLCV。バルク insert に対応。",
        functions: [
          "日次 OHLCV の bulk insert (executemany)",
          "期間範囲 query",
          "欠損日の検出",
          "company × date の UNIQUE 制約",
        ],
        intent:
          "Stooq からの日次バッチは 1 銘柄あたり数千行になるため、ORM の 1 行 INSERT では破綻する。bulk insert を必須にし、夜間バッチが現実的な時間で終わるようにする。",
      },
      {
        name: "quote_price.py",
        role: "現在株価キャッシュ。",
        functions: [
          "1 銘柄 1 行への upsert",
          "source (yahoo / sheets / stooq) ごとの last_updated",
          "TTL 切れの検出",
        ],
        intent:
          "現在値は『どこから来たか』が運用上重要なので、source カラムで由来を明示。これにより一次ソースを運用中に切り替えても、過去値の出自を追跡できる。",
      },
      {
        name: "screening.py",
        role: "screening cache の CRUD + `bulk_upsert_cache` (ADR-003)。",
        functions: [
          "ScreeningCache の CRUD",
          "bulk_upsert_cache (1000+ 銘柄を 1 トランザクションで upsert)",
          "filter 評価用の columnar 読み出し",
          "universe × 指標の組合せでの index lookup",
        ],
        intent:
          "1000+ 銘柄を毎回 N+1 で取り直すと screening が破綻する。ADR-003 で Yahoo v7 batch を採用したのに合わせ、書き込み側もここで bulk upsert にし、フィルタ評価との両端で線形時間に揃える。",
      },
      {
        name: "analysis_job.py",
        role: "Job の状態遷移 + lease。Worker が picked するクエリの主役。",
        functions: [
          "pending を 1 件 lease (SKIP LOCKED 相当)",
          "running → done|failed の遷移",
          "lease 期限切れの再投入",
          "状態 × 期間 でのクエリ (Web の /jobs 表示)",
        ],
        intent:
          "services/analysis_queue.py から見て『DB キュー』のインタフェースを満たす最小機能だけを置く。これ以上のキュー意味論はここに持ち込まないことで、repository と queue 意味論のレイヤ分離を保つ。",
      },
      {
        name: "analysis.py",
        role: "company_analyses (RAG 結果) の CRUD。`pipeline` 列で extractor/PageIndex 期を区別。",
        functions: [
          "company × analysis_type × pipeline の latest 取得",
          "pipeline (extractor / NULL) 別の絞り込み",
          "prompt_version / model_name の検索",
          "結果 payload の保存",
        ],
        intent:
          "ADR-004 移行で過去結果が混在するため、pipeline カラムで世代を判別する。UI 側で『古いパイプラインの結果』を明示し、ユーザーが結果の鮮度を誤読しないようにする。",
      },
      {
        name: "document_index.py",
        role: "PageIndex のインデックス構築状態。",
        functions: [
          "filing × index_type の状態管理",
          "building / ready / failed の遷移",
          "TTL ベースの再構築判定",
        ],
        intent:
          "RAG インデックスを『ファイル』ではなく『DB の行』で管理。インデックスの有無 / 古さ / 再構築要否を SQL でクエリ可能にし、UI からも CLI からも同じ状態を見られるようにする。",
      },
      {
        name: "rag_qa_history.py",
        role: "自由質問の Q&A 履歴。",
        functions: [
          "filing × question の履歴 CRUD",
          "時系列 / 会社別のリスト",
          "citations (page range) の永続化",
        ],
        intent:
          "自由質問は再現性が低いため、引用 page range も含めて履歴を残しトレース可能にする。同じ質問の重複実行も履歴ベースで抑止できる。",
      },
      {
        name: "watchlist.py / target.py",
        role: "Watchlist / AnalysisTarget の CRUD。",
        functions: [
          "Watchlist グループのメンバー管理",
          "AnalysisTarget の昇格 / 一括削除",
          "ユーザー × 銘柄の絞り込み",
        ],
        intent:
          "Watchlist (気になるメモ) と AnalysisTarget (分析対象) を別概念として扱い、UI も別画面に分けている。両者を 1 つのテーブルに混ぜないことで意味的な混乱を避ける。",
      },
    ],
    deps: {
      calls: ["models", "SQLAlchemy session"],
      calledBy: ["services", "ingestion"],
      note: "ビジネスロジックはここに書かない (services の責務)。",
    },
    adrs: ["ADR-003", "ADR-004"],
    terms: ["repositoriesLayer", "repositoryPattern", "ormPattern", "sqlalchemy", "aiosqlite", "bulkUpsert", "jobStatus"],
  },

  /* ---------------------- models/ ------------------------------ */
  {
    id: "models",
    name: "Models",
    path: "src/stock_analyze_system/models/",
    files: 17,
    summary:
      "SQLAlchemy 2.x declarative の ORM テーブル定義。スキーマの一次定義はここ。",
    description: [
      "`base.py` の Declarative Base が起動時に idempotent な `ALTER TABLE` を実行し、カラム追加 (例: `company_analyses.pipeline`) に対応する。",
      "`enums.py` の `FilingType` / `JobStatus` / `Market` などは models 全体で参照される。",
    ],
    features: [
      {
        name: "base.py",
        role: "Declarative Base + 起動時 idempotent ALTER TABLE。",
        functions: [
          "SQLAlchemy 2.x DeclarativeBase",
          "起動時 ALTER TABLE ADD COLUMN IF NOT EXISTS",
          "共通 mixin (id / created_at / updated_at)",
          "全テーブルへの metadata 集約",
        ],
        intent:
          "軽い個人運用が前提なので Alembic を導入せず、新しいカラム追加だけ起動時 ALTER で吸収する単純化を選択。Base 自体は標準形なので、運用が育てば Alembic に乗せ替えやすい状態を維持する。",
      },
      {
        name: "enums.py",
        role: "FilingType / JobStatus / Market 列挙。",
        functions: [
          "FilingType (10-K / 10-Q / 20-F / 6-K / 有報 / 四半期)",
          "JobStatus (pending / running / done / failed)",
          "Market (US / JP)",
          "Pipeline (extractor / pageindex)",
        ],
        intent:
          "文字列リテラルを散らさず Enum で型安全にする。ADR-004 amendment の whitelist (ANALYSIS_FILING_TYPES) のような制約を、コード上の 1 箇所にまとめて参照できるようにする。",
      },
      {
        name: "company.py",
        role: "企業マスタ。Filing 等と 1:N。",
        functions: [
          "ticker / cik / edinet_code / market / sector",
          "Filing / FinancialData / Valuation との 1:N relationship",
          "UNIQUE 制約 (CIK / EDINET コード)",
        ],
        intent:
          "1 会社 = 1 行を強制 (US は CIK、JP は EDINET コードがキー)。これにより relationship 越しの集計と join が機械的になり、ドメインモデルが安定する。",
      },
      {
        name: "filing.py",
        role: "10-K / 有報メタ。`storage_path` がローカル本文の場所。",
        functions: [
          "company_id / filing_type / period / accession_number",
          "storage_path (本文ファイルへの相対 path)",
          "filed_at / fetched_at",
        ],
        intent:
          "本文 (数 MB) を DB に詰めず、ファイルシステムに置いて storage_path で参照する設計。DB を軽く保ち、本文の再取得・再パースを安価にする。",
      },
      {
        name: "financial_data.py",
        role: "売上 / 利益 / CF などの数値。",
        functions: [
          "company_id × period × 連結/個別",
          "売上 / 営業利益 / 純利益 / 営業 CF / 投資 CF / FCF / EBITDA",
          "通貨 / 単位スケール",
        ],
        intent:
          "1 行 = 1 (会社 × 期間 × 指標) ではなく、1 行 = 1 (会社 × 期間) にして列展開する形。PER 等の計算が JOIN なしで 1 行から完結し、画面表示までのコードが短くなる。",
      },
      {
        name: "valuation.py",
        role: "PER/PBR/EV-EBITDA の時点スナップショット。",
        functions: [
          "date (月末) × company_id",
          "PER / PBR / EV-EBITDA / PSR / FCF Yield",
          "通貨 / 為替レート",
          "source の参照 (どの financial_data に基づくか)",
        ],
        intent:
          "10 年 × 月次 = 120 行/銘柄を前提に、列を増やしても row サイズが小さく済む構成にする。月末スナップショットに固定することで、画面の時系列描画と SQL のウィンドウ集計を簡素化。",
      },
      {
        name: "quote_price.py / price_history.py",
        role: "現在値キャッシュ / 過去 OHLCV。",
        functions: [
          "QuotePrice: 1 銘柄 1 行の現在値 + source",
          "PriceHistory: 1 銘柄 N 行の日次 OHLCV",
          "company × date の UNIQUE 制約",
        ],
        intent:
          "『最新値』と『履歴』はアクセスパターンが違うため別テーブル。screening の hot path で履歴テーブルを touch しないようにし、書き込みと読み出しの I/O を分離する。",
      },
      {
        name: "screening.py",
        role: "screening_universe + screening_cache の 2 テーブル定義。",
        functions: [
          "ScreeningUniverse: universe メンバーシップ",
          "ScreeningCache: universe × 指標の cached value",
          "rebuilt_at / source の管理",
        ],
        intent:
          "universe (誰が含まれるか) と cache (各指標の最新値) を分離。universe の組み換え (流動性閾値変更等) と enrichment の TTL を独立に進化させられる。",
      },
      {
        name: "watchlist.py / analysis_target.py",
        role: "Watchlist グループと Target。",
        functions: [
          "Watchlist: ユーザー視点のフォルダ",
          "WatchlistMember: 銘柄リンク",
          "AnalysisTarget: 分析ファネル先頭",
        ],
        intent:
          "『気になる』と『分析対象』を別概念にして、UI でも別画面に切り出す。Watchlist は ad-hoc な手書き、AnalysisTarget は screening からの自動昇格を主にする想定。",
      },
      {
        name: "analysis_job.py",
        role: "Worker が拾うジョブキュー。pending/running/done/failed。",
        functions: [
          "id / company_id / filing_id / analysis_type",
          "status (pending / running / done / failed)",
          "lease_until / claimed_by",
          "error_text / result_json",
        ],
        intent:
          "結果も同じ行に残す (result_json) ことで『ジョブ実行履歴』と『分析結果』を 1 テーブルで満たし、運用上のデバッグが SQL 1 本で終わるようにする。",
      },
      {
        name: "company_analysis.py",
        role: "RAG 結果キャッシュ。`pipeline` 列で extractor/NULL を区別 (ADR-004)。",
        functions: [
          "company_id / analysis_type / pipeline / model_name / prompt_version",
          "payload (構造化された LLM 出力)",
          "created_at / source_filing_id",
        ],
        intent:
          "ADR-004 で pipeline カラムを追加。世代を識別できないと、prompt 改修や extractor → PageIndex 切戻し時に過去結果が混入して比較不能になる。世代をデータ側に明示するための一手。",
      },
      {
        name: "document_index.py",
        role: "PageIndex 構築状態。",
        functions: [
          "filing_id / status / built_at / version / source",
        ],
        intent:
          "RAG インデックスを DB の行として管理することで、UI や CLI から状態を SQL で問い合わせられる。インデックスの再構築要否を決定論的に判定可能にする。",
      },
      {
        name: "rag_qa_history.py",
        role: "自由質問の履歴。",
        functions: [
          "filing_id / question / answer / citations (page range)",
          "created_at / model_name",
        ],
        intent:
          "自由質問は決定論的に再現できないため、引用 page range も含めて履歴に残す。監査・再利用・重複抑止に使う。",
      },
      {
        name: "competitor_group.py",
        role: "z-score 偏差分析用のグループ定義。",
        functions: [
          "グループ id / name",
          "companies (M:N)",
          "rebuilt_at",
        ],
        intent:
          "同業他社の z-score を継続的に再計算するため、グループを永続化する。screening の結果から動的に作るのではなく、人が明示的に管理して比較対象を安定させる。",
      },
    ],
    deps: {
      calls: ["—"],
      calledBy: ["repositories"],
      note: "models は他の層に依存しない。`enums.py` だけ shared 的に各層から import される。",
    },
    adrs: ["ADR-004"],
    terms: ["modelsLayer", "ormPattern", "sqlalchemy", "filingTypeEnum", "jobStatus", "analysisJob"],
  },

  /* ---------------------- shared/ ------------------------------ */
  {
    id: "shared",
    name: "Shared",
    path: "src/stock_analyze_system/shared/",
    files: 6,
    summary:
      "層に属さない共通ユーティリティ。フォーマッタ / 時刻ヘルパ / クライアント設定 / JSON ガードなど。",
    description: [
      "副作用を持たない pure な関数を中心に置く。ここに業務ロジックが入り込むとアンチパターン。",
      "`json_utils.py` は LLM の応答に対する `safe_json_loads` などの防衛コード。",
    ],
    features: [
      {
        name: "formatters.py",
        role: "`fmt_number` / `fmt_pct` / `fmt_large` / `fmt_ratio` 等の表示用フォーマッタ。CLI / Web で共通使用。",
        functions: [
          "fmt_number(n) → '1,234,567' (3桁区切り)",
          "fmt_pct(0.158) → '15.8%' (1 decimal)",
          "fmt_large(2.5e9) → '2.50B' (k/M/B/T)",
          "fmt_ratio(15.823) → '15.82' (2 decimals)",
          "fmt_signed: 符号付き表示 (常に + / -)",
        ],
        intent:
          "CLI / Web で数値表示を完全一致させるため、絶対にここに集約する。Web のテンプレートでは Jinja filter として利用することを想定し、Python レベルで 1 つの正解を持つ。",
      },
      {
        name: "financial.py",
        role: "通貨換算や指標の補助計算など、純粋な数値ヘルパ。",
        functions: [
          "通貨換算 (currency × rate → 目標通貨)",
          "単位スケール変換 (千 → 百万 → 十億)",
          "安全な除算 (ゼロ割回避)",
          "TTM 集計の pure 関数",
        ],
        intent:
          "副作用ゼロの pure 関数だけを置く。DB / 外部 API を絶対 import しないことで、ここを services から自由に呼べ、ユニットテストもデータ不要で書ける状態を保つ。",
      },
      {
        name: "clients.py",
        role: "httpx / litellm / Google API 等の共通クライアントファクトリ。User-Agent / timeout / retry を一元管理。",
        functions: [
          "httpx.AsyncClient ファクトリ (UA / timeout / proxy)",
          "litellm の global 設定",
          "Google API 認証クライアント",
          "プールサイズ / 接続再利用の設定",
        ],
        intent:
          "クライアント生成を 1 か所に集めて、運用上の設定変更 (SEC UA 強化 / proxy 追加 等) を CLI / Web / Worker に同時反映できるようにする。",
      },
      {
        name: "json_utils.py",
        role: "safe_json_loads などの防衛ロード。LLM の不正 JSON に対する garbage-in-garbage-out 抑制。",
        functions: [
          "safe_json_loads: 例外を None に変換",
          "コードブロック (```json ... ```) の剥がし",
          "JSON schema validation",
          "末尾カンマ / コメント等のサニタイズ",
        ],
        intent:
          "LLM の応答には `json ` prefix や trailing コメントが混入することが多い。防衛コードを services 側に散らさず、shared に集約することで services の業務ロジックを読みやすく保つ。",
      },
      {
        name: "time_utils.py",
        role: "JST / UTC 変換などの時刻ヘルパ。",
        functions: [
          "now_jst() / now_utc()",
          "JST ↔ UTC 変換",
          "取引日カレンダー判定",
          "to_period(year, q) などの期間 helper",
        ],
        intent:
          "タイムゾーンを忘れる類のバグを防ぐため、必ずここを通す。JST 固定 (国内向け運用) なのでロジックは単純で済む構造に切り詰めている。",
      },
    ],
    deps: {
      calls: ["—"],
      calledBy: ["all layers"],
      note: "ここから他層を呼ぶことはない。",
    },
    adrs: [],
    terms: ["llmClient", "litellm"],
  },
];
