---
title: Living Docs — 認知負荷を低減する 3 層ドキュメント体系
status: Draft
created: 2026-05-19
author: kei0916
related_adrs: ["ADR-005"]   # Accepted 後も ADR-XXX 形式の追記のみ可
related_specs:
  - docs/superpowers/specs/2026-03-29-maintainability-refactoring-design.md
scope: documentation-architecture, developer-workflow
---

# Living Docs — 認知負荷を低減する 3 層ドキュメント体系

> ⛔ **P2 着手前必読**: 2026-05-22 に `docs-site/src/components/visualization/`
> (プロジェクト可視化 SPA) を追加した。この影響で §8 のディレクトリ図 / git 管理ポリシー表の
> 更新と、可視化ページの freshness 取り扱い決定が P2 のスコープに入る。
> 詳細と着手前チェックリストは
> `docs/superpowers/plans/2026-05-23-living-docs-p2-services.md` の §0 を参照。
> どのエージェントもこの注記を見たら必ず先に上記 plan §0 を読むこと。

## 1. 背景と動機

Stock Analyze System は spec 20+ / plan 30+ / ADR 4+ という豊富なドキュメント
資産を持つが、ユーザ（プロジェクトオーナー兼開発者）は次の 4 つの認知負荷を
継続的に感じている:

1. 新規セッション開始時の **全体像把握** が遅い
2. 個別機能（モジュール）の **責務・依存・設計意図** をコードから読み解く負担
3. AI が生成したコード変更の **設計意図確認**（レビュー）が困難
4. 既存ドキュメントの **鮮度・整合性** に確信が持てない（特に最重要課題）

これらは「ドキュメントを増やす」では解決しない。本 spec は、層分離と
Skill/hook 駆動の鮮度保証によって、読み手（人間）が **信頼して** 短時間で
把握できる「生きたドキュメント体系」を設計する。

### 制約

- 主要読み手は人間（プロジェクトオーナー）、AI は従
- 著作フォーマットは Markdown（AI 編集容易）、閲覧は Docusaurus が生成する HTML
- 鮮度保証は Claude Code の Skill/hook **に加えて** repo-owned な `make docs-check` / pre-commit hook / AGENTS.md による多層防御で実現（Claude 以外の AI でも規律が効くようにする）
- CI ブロック方式は採用しない（warn のみ）
- 既存の spec / plan / ADR 資産には破壊的変更を加えない（後付け frontmatter も不可）

## 2. 全体アーキテクチャ

ドキュメントを責任の異なる 3 層に分け、それぞれ別の機構で鮮度を保証する。

```
┌─────────────────────────────────────────────────────────────┐
│  L1 自動生成 (regenerated on build, .gitignore)             │
│  - docs/generated/dependency-graph.md                       │
│  - docs/generated/module-index.md                           │
│  - docs/generated/adr-index.md                              │
│  - docs/generated/cli-reference.md                          │
│  - docs/generated/spec-plan-cross-ref.md                    │
│  - docs/generated/test-coverage-map.md                      │
└─────────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────────┐
│  L2 AI 維持 (Skill enforces freshness)                      │
│  - docs/system-overview.md  ← 全体地図 (唯一の入口)         │
│  - docs/current-work.md     ← 進行中の作業 (mutable)        │
│  - docs/living-docs/manifest.yml  ← 既存 ADR/spec/plan 補完 │
│  - docs/living-docs/ai-rules.md   ← CLAUDE.md/AGENTS.md 一次ソース │
│  - src/stock_analyze_system/README.md (パッケージルート)    │
│  - src/stock_analyze_system/<module>/README.md  (×7)        │
└─────────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────────┐
│  L3 アーカイブ (Accepted 後 immutable; lifecycle 例外あり)  │
│  - docs/superpowers/specs/*.md (既存 20+)                   │
│  - docs/superpowers/plans/*.md (既存 30+)                   │
│  - docs/adr/*.md (既存 4+)                                  │
└─────────────────────────────────────────────────────────────┘
            ↓ すべて Docusaurus に統合 ↓
   docs-site/ (build artifact in .gitignore, sources tracked)
   サイドバー: Start Here / Current State / Archive
```

**層分けの効果**:
- 「今のシステムを知りたい」 → L2 を読む
- 「なぜそうなった」 → L3 を辿る
- 「どこに何がある」 → L1 で検索

## 3. L1 自動生成層の仕様

**生成スクリプト**: `scripts/gen_docs.py`（`uv run scripts/gen_docs.py`）

**生成物（すべて `docs/generated/` 配下、`.gitignore` 対象）**:

| ファイル | 中身 | 生成元 |
|---------|------|--------|
| `module-index.md` | `src/stock_analyze_system/` 配下の全モジュール一覧（パス、ファイル数、LOC、README へのリンク） | `os.walk(src)` |
| `dependency-graph.md` | モジュール間依存の Mermaid グラフ | `ast.parse` で import 文を解析、自パッケージ内のみ抽出 |
| `cli-reference.md` | CLI コマンド一覧（コマンド名、ヘルプ要約） | `cli/app.py:build_parser()` を呼び、argparse の `subparsers` を走査して各 `register_parser` 由来のサブコマンドを列挙 |
| `adr-index.md` | ADR 番号・タイトル・Status・関連モジュール | 既存 ADR は frontmatter を持たないため、`# ADR-NNN: <title>` 見出しと `## Status` セクション（無ければ `Accepted` 仮定）を正規表現抽出 + `docs/living-docs/manifest.yml` の `adrs:` セクションで補完（後述§6.5） |
| `spec-plan-cross-ref.md` | spec ↔ plan ↔ ADR ↔ commit の対応表 | 一次ソースは新規 `docs/living-docs/manifest.yml`（後述§6.5）+ 補助として本文の見出しパターン (`# <title>` `**日付**:` `**対象ブランチ**:` 等) を正規表現抽出 + `git log -- docs/.../<file>` |
| `test-coverage-map.md` | 各モジュールのテストカバレッジ % + 主要テストファイル | `pytest --cov=... --cov-report=json` |

**再生成タイミング**（最終形。段階導入中は後述§10のフェーズに合わせて生成範囲を拡張）:

| ターゲット | 生成範囲 | 用途 |
|-----------|---------|------|
| `make docs-serve`（軽量） | P1: `module-index`, `dependency-graph`, `cli-reference`。P3 以降: + `adr-index`, `spec-plan-cross-ref` | 日常閲覧。AST/正規表現/argparse 走査のみで外部依存なし・数秒で完了 |
| `make docs-full`（重め） | P1/P2: `docs-serve` と同じ（coverage 未実装 warning のみ）。P3 以降: 上記 + `test-coverage-map.md` | リリース前・週次など。`pytest --cov` を伴うため数分かかる・flaky の影響を受ける |

- P1/P2 では未実装の生成物を Docusaurus サイドバーに出さない。空ファイル stub で「完成」と見せない
- pre-commit hook では `make docs-check`（warn-only）を実行する。L1 生成物は `.gitignore` 対象なので、`docs/generated/**` との diff 比較はしない。軽量検査では `module-index` / `dependency-graph` / `cli-reference` を一時ディレクトリに生成できることだけ確認し、stale な閲覧用コピーは `docs-site/docs/**` の clean 再生成で排除する
- CI（後述§7.5）では `make docs-full` を走らせ、生成失敗で警告を出す（block はしない）

**設計判断**:
- 生成物（`docs/generated/`）は git 管理しないことで「古い状態」が原理的に存在しなくなる
- `cli-reference.md` の生成は `cli.app` の import が必要 → 失敗時は warning のみで継続
- `test-coverage-map.md` を `docs-serve` から外したのは、閲覧速度と外部依存（pytest 環境）を切り離すため
- `scripts/gen_docs.py` 自体は L2（AI 維持）として扱う

## 4. L2 — per-module `README.md` スキーマ

**配置**: `src/stock_analyze_system/<module>/README.md` × 7 + パッケージルート 1 = 計 8 個

対象トップレベルモジュール（確定）: `cli`, `ingestion`, `models`,
`repositories`, `services`, `shared`, `web`

主要サブモジュール（実装フェーズで READMEを置くか親に統合するか決定）:
`ingestion/xbrl`, `services/pageindex`, `web/routes`

**必須セクション（順序固定）**:

```markdown
---
module: services
last_reviewed: 2026-05-19
related_adrs: ["ADR-004"]
related_specs:
  - docs/superpowers/specs/2026-05-11-analysis-worker-separation-design.md
---

# services — 解析・取得ロジックの調整層

## このページで分かること (30 秒)
<1〜2 文で、このモジュールが何をするか>

## 責務 (一行で)
<このモジュールが所有する責任>

## 公開・安定インターフェース
- 他モジュールが**安定 API として依存する**関数/クラスのみ列挙（網羅ではない）
- 私的・実装詳細・頻繁に変わる関数は L1 の `module-index.md` 側を参照
- 目安: 5〜10 項目以内。それ以上は本当に公開すべきか再検討

## 依存
| 依存先 | 用途 |
|--------|------|
| ... | ... |

## データフロー (主要 1〜2 パス)
<ASCII or Mermaid で図示>

## 主要な設計判断
- **ADR-XXX**: 判断と理由
- ...

## 既知の制約
- ...

## テスト境界
- 主要テストファイルへのリンク

## 触ったら README 更新を検討するファイル
- ファイル名のリスト（Skill のトリガ判定に使用）
```

**frontmatter 参照 ID の正規化**:
- `related_specs` / `related_plans` は repository root からの相対 path（例: `docs/superpowers/specs/2026-05-11-analysis-worker-separation-design.md`）で書く。basename のみ、拡張子なし、plan/spec の短縮名は使わない
- `related_adrs` はゼロ埋め 3 桁の文字列 ID（例: `"ADR-004"`）で書く。bare number の `004` は YAML 上も意味が曖昧になるため使わない
- `gen_docs.py` は上記 ID を manifest の `path` / `id` に解決し、存在しない参照を warning として出す

**設計判断**:
- `last_reviewed` は AI が「責務/提供 I/F/依存/主要判断 のいずれかを変えた時」必須更新
- 「触ったら更新検討」リストが Skill のトリガ集合
- 200〜400 行を目安とし、超えたらモジュール分割の合図

## 5. L2 — `docs/system-overview.md` スキーマ

**配置**: `docs/system-overview.md`（1 枚、唯一の入口）

**必須セクション**:

1. **30 秒サマリ** — システムの存在意義を 1〜2 文で
2. **システムマップ** — モジュール間の Mermaid 図
3. **エンドツーエンドのデータパス** — 主要 2〜3 パスを箇条書き
4. **主要な設計上の選択肢** — 表形式: 選択 / 採用 / ADR 番号
5. **モジュール一覧** — 表形式: モジュール / 責務 / README リンク
6. **アクティブな ADR (Status: Accepted)** — 番号・タイトル・リンク
7. **いま進行中の作業** — mutable な `docs/current-work.md`（L2、AI 維持）と git-derived 情報（active branches、open PR、最近の commit）の組み合わせで構成。**既存 plan のチェックボックスは更新しない**（L3 不変原則）
8. **始めるとき何を読むか** — 用途別の読書順

**設計判断**:
- セクション 6 は L1 `adr-index.md` を読み込んで半自動更新
- セクション 7 は L2 の `docs/current-work.md` + git CLI 出力で構成。一次ソースは `docs/current-work.md`（mutable、AI 維持）。git derived 情報は `gen_docs.py` で `git for-each-ref refs/heads/feat/*` 等から都度生成
- セクション 8 を冒頭近くに置く案も検討したが、まず文脈を掴むため後方配置

## 6. L3 アーカイブ層の運用方針

**対象（既存）**: `docs/superpowers/specs/*` (20+), `docs/superpowers/plans/*` (30+), `docs/adr/*` (4)

**原則**:

1. **lifecycle**: 新規 spec / plan は `status: Draft` の間だけレビュー修正・設計調整のため mutable。`status: Accepted` 以降は内容変更しない（誤字訂正のみ可）。frontmatter を持たない既存 spec / plan は Accepted 相当として扱う
2. **Accepted 後の例外**: spec / plan の frontmatter は lifecycle と参照整合性に限り、`status` / `related_adrs` / `related_specs` / `related_plans` の更新を許可する。本文の設計判断を変える場合は新 spec / plan / ADR を作る
3. **ADR の Status のみ更新可**: 新しい決定は新 ADR を立てて `Supersedes ADR-XXX` で連結
4. **L2 ↔ L3 双方向リンク**: L2 frontmatter の `related_adrs` / `related_specs` で参照、逆方向は L1 (`spec-plan-cross-ref.md`) で生成
5. **Docusaurus サイドバー配置**:
   ```
   ├── Start Here (system-overview.md)
   ├── Current State
   │   ├── Module READMEs (L2)
   │   └── Generated References (L1)
   └── Archive (L3)
       ├── ADRs
       ├── Specs (date-sorted)
       └── Plans (date-sorted)
   ```
6. **整合性違反検出**: L1 生成時に L2 → L3 リンク切れを warning 出力
7. **古い ad-hoc docs の片付け**: `docs/RAGtest_debug.md` `analysis-failures-root-cause.md` `docs/adr-004-e2e-verification.md` 等の散在ファイルを `docs/archive/2026-Q2/` に 1 回限りで移動する。`docs/adr-004-e2e-verification.md` は ADR 本体ではなく検証ログなので、L3 ADR (`docs/adr/*.md`) には含めない

### 6.5 既存 spec/plan に frontmatter を足さない方針と manifest

既存 spec/plan は `# <title>` `**日付**:` 形式で書かれており、YAML frontmatter を持たない。
L3 不変原則を守るため、後付けで frontmatter を足さない。代わりに以下を採用:

- **新規 spec/plan のみ** frontmatter を付与する（本 spec 自体が最初の例）
- **既存分の cross-ref は外部 manifest** `docs/living-docs/manifest.yml` で補完:
  ```yaml
  # docs/living-docs/manifest.yml (L2、AI 維持)
  adrs:
    - path: docs/adr/004-sec-filing-section-extractor.md
      id: ADR-004
      number: 4
      title: 定型分析を SEC 専用の固定セクション抽出に置き換える
      status: Accepted
      date: 2026-04-XX
      supersedes: []
      related_modules: [services, ingestion]
  specs:
    - path: docs/superpowers/specs/2026-05-11-analysis-worker-separation-design.md
      title: 定型分析ワーカーの別プロセス分離 — 設計仕様
      date: 2026-05-11
      related_adrs: []
      related_modules: [services, web, cli]
      related_plan: docs/superpowers/plans/2026-05-11-analysis-worker-separation.md
  plans:
    - path: docs/superpowers/plans/2026-05-11-analysis-worker-separation.md
      ...
  ```
- `gen_docs.py` は manifest を主、本文パターン解析（`# ADR-NNN:`, `# <title>`, `**日付**:`, `## Status` 等）を補助として cross-ref を生成
- manifest は AI 維持（新規 spec/plan/ADR を書いたら同 commit で追記） → Skill の Checkpoint 2 に追加
- manifest / frontmatter の参照ルールは以下に固定する:
  - spec / plan は repository root からの相対 path（`.md` 拡張子込み）を canonical identifier とする
  - ADR は `ADR-004` のような `ADR-` + ゼロ埋め 3 桁文字列を canonical identifier とする。manifest の `number: 4` は並び替え・表示用であり、参照キーには使わない
  - basename のみ（例: `2026-05-11-analysis-worker-separation`）や bare number（例: `004`）は無効とし、`docs-check` で warning を出す

## 7. Skill 設計 — `maintaining-living-docs`

新規スキルを `kei0916/superpowers` fork に追加する。

### Frontmatter
```yaml
---
name: maintaining-living-docs
description: Use when editing files under src/stock_analyze_system/ or when starting a session involving code changes — ensures L2 docs (per-module README + system-overview.md) stay synchronized with code via 3 checkpoints.
---
```

### 3 つの介入点

**① セッション開始時 (Checkpoint 1)**:
- コード変更を伴う作業の気配があれば `docs/system-overview.md` を必ず最初に読む
- 触る予定のモジュールを予測し、対応する `<module>/README.md` も先に読む

**② コード編集時 (Checkpoint 2)**:
- `src/<module>/` 配下のファイル編集前に、該当モジュールの README の「触ったら更新検討」リストを参照
- 編集後「責務/提供 I/F/依存/主要判断 のいずれかが変わったか？」を自問
- 変わった場合は `README.md` と `last_reviewed` を同じコミット内で更新

**③ コミット直前 (Checkpoint 3)**:
- 変更ファイル一覧から touched modules を導出
- 各モジュールについて README が当該コミットで更新されているか確認
- 触ったのに更新されていない場合: 意図的スキップ（→ commit OK）か忘れ（→ 戻って更新）を明示
- `superpowers:verification-before-completion` のチェックリストに「README 鮮度確認」を追加

### 既存/新規スキルとの結節点

| スキル/フロー | 統合点 |
|-----------|--------|
| brainstorming | spec を書く前に該当 module の README を参照、最新状態と矛盾しないか確認 |
| writing-plans | plan frontmatter に `affects_modules` を追加 → Skill が編集時に該当 README を読み込む |
| ADR 作成フロー（新規/将来スキル） | ADR 作成時、関連 module の README の `related_adrs` を同コミットで追記 |
| executing-plans | 各 task 実行時、対応 module の README を context として読み込む |
| verification-before-completion | チェックリストに「README 鮮度確認」を追加 |
| requesting-code-review | PR 概要に「更新した README」を含めることを義務化 |

### 7.5 repo-owned な強制機構（Skill だけに頼らない多層防御）

Skill は強力だが **Claude Code 限定**であり、Codex / Gemini / 手動 git 操作では発火しない。
「鮮度保証」と呼ぶには repo に閉じた強制機構が必要。以下を併用する:

| 機構 | 終了コード/強制レベル | 対象 |
|------|----------------------|------|
| `make docs-check` | **常に exit 0**、違反は stdout/stderr に warning 出力のみ | 触ったモジュールの README が `last_reviewed` 更新されているか・manifest が新規 spec/plan/ADR を参照しているか・L2 → L3 のリンク切れがないか・L1 の軽量生成物（`module-index`/`dependency-graph`/`cli-reference`）を一時ディレクトリに生成できるかを検査。`docs/generated/**` は ignored なので、repo 品質チェックでは差分比較対象にしない |
| `make docs-check-strict` | 違反があれば exit 1 | 自発的に「今 clean か」を確認したい時に手動実行。pre-commit や CI からは呼ばない |
| pre-commit hook (`.pre-commit-config.yaml`) | **block しない** | `make docs-check`（非 strict 版）を実行し、warning だけ表示。pre-commit framework の `verbose: true` + `pass_filenames: false` + 戻り値を常に 0 にラップするシェル one-liner で実装 |
| CI ワークフロー（任意） | warn-only | PR 時に `make docs-check` を annotations として表示。job は常に green。block はしない（仕様§2 制約に準拠） |
| `CLAUDE.md` への記載 | AI 行動規律 | Claude Code 用 |
| `AGENTS.md` への記載 | AI 行動規律 | Codex 等 Claude 以外用 |

→ Skill が一次防御、`make docs-check`（warn-only）が二次防御、CLAUDE.md/AGENTS.md が AI 共通の規律という三層構造。**block する経路は意図的に存在しない**ことが本仕様の契約。

## 8. Docusaurus 設定

**配置**: プロジェクトルート直下 `docs-site/`

### ディレクトリ構成と git 管理ポリシー
```
docs-site/                   # git 管理（設定のみ）
├── docusaurus.config.js     # tracked
├── sidebars.js              # tracked
├── src/{pages,css/custom.css}  # tracked
├── docs/                    # **完全 .gitignore**（gen_docs.py が毎回 clean 生成）
│   ├── overview.md
│   ├── modules/
│   ├── archive/{adr,specs,plans}/
│   └── generated/
├── build/                   # **完全 .gitignore**（Docusaurus ビルド出力）
└── package.json             # tracked
```

| パス | git | 一次ソース |
|------|-----|-----------|
| `docs-site/{config,src,sidebars.js,package.json}` | tracked | 直接編集 |
| `docs-site/docs/**` | **ignored** | `docs/system-overview.md`, `src/<mod>/README.md`, `docs/adr/`, `docs/superpowers/`, `docs/generated/` |
| `docs-site/build/**` | **ignored** | Docusaurus build |
| `docs/generated/**` | **ignored** | `scripts/gen_docs.py` |

### 集約方法（clean 再生成原則）
`scripts/gen_docs.py` は以下の順で実行:
1. `docs-site/docs/` を rm -rf（残骸を残さない）
2. `docs/generated/` を rm -rf
3. L1 を `docs/generated/` に生成
4. L2 を `docs-site/docs/{overview.md, modules/, current-work.md}` にコピー（サイドバー位置 frontmatter を注入）
5. L3 を `docs-site/docs/archive/` にシンボリックリンク or コピー（read-only）
6. L1 を `docs-site/docs/generated/` にコピー

**ソースの一次資料はあくまで `src/<module>/README.md` 等**（コード隣接、編集容易）。
`docs-site/docs/` は毎回完全再構築されるため、ここに直接編集を加えてはいけない。

### コマンド
- `make docs` — gen_docs.py + Docusaurus ビルド
- `make docs-serve` — 上記 + `npx docusaurus serve` (localhost:3000)
- `make docs-clean` — `docs-site/docs/`、`docs-site/build/`、`docs/generated/` を削除

### 設定方針
- 検索: `@easyops-cn/docusaurus-search-local`（無料・オフライン動作）
- Mermaid: `@docusaurus/theme-mermaid` 有効化
- `onBrokenLinks`: 初期は `warn`、安定後 `throw`
- ビルド失敗時の耐性: `cli-reference.md` 生成は `try/except` で警告のみ

## 9. 開発フローへの組み込み

### 日常作業ループ（Skill 自動誘導）
```
新しい作業を開始
  → system-overview.md を読む
  → 触る予定の <module>/README.md を読む
  → コード編集
  → README 更新検討（責務/I/F/依存/主要判断 が変わった?）
  → 変わった場合: README + last_reviewed を更新
  → commit (pre-commit Skill が触ったモジュールの README 更新を確認)
  → 完了
```

### CLAUDE.md / AGENTS.md への記載（AI 共通の行動規律）

本プロジェクトは Claude Code（superpowers fork）と Codex（および将来 Gemini 等）の
複数 AI を使用する。AI 限定の規律は repo の以下 2 ファイルに重複記載する:

- `CLAUDE.md`（プロジェクトルート、Claude Code 用）
- `AGENTS.md`（プロジェクトルート、Codex / その他用）

両ファイルに含める内容:
- セッション開始時の必読ファイル: `docs/system-overview.md` → 触る予定の `<module>/README.md`
- コード編集時のチェックポイント: 責務 / 公開 I/F / 依存 / 主要判断 が変わったら同コミットで README 更新
- pre-commit / `make docs-check` の存在と意味
- L1/L2/L3 の意味と読み分け
- AI 共通の "Living Docs 規約" の不変条文（番号付き、後方互換性を持って増やす）

両ファイルは **tracked な生成コピー** として repo に置く。新規セッション開始時に生成を待たず読めることを優先する。
`docs/living-docs/ai-rules.md` を一次資料とし、`scripts/gen_docs.py` は CLAUDE.md / AGENTS.md を更新できるが、未生成状態を許容しない。
`make docs-check` は `ai-rules.md` と CLAUDE.md / AGENTS.md の同期ずれを warning として出す（strict 版では exit 1）。

## 10. 段階的導入計画

| Phase | 期間 | 成果物 | 終了基準 |
|------|------|--------|---------|
| P1: 基盤 | 1〜2 日 | `scripts/gen_docs.py` (module-index + dependency-graph + cli-reference のみ)、Docusaurus 最小構成（clean 再生成方式。未実装生成物はサイドバー非表示）、`docs/system-overview.md` 骨格、`docs/current-work.md` 骨格、**`.gitignore` 更新** (`docs-site/docs/`, `docs-site/build/`, `docs/generated/` の追加)、Makefile に `docs`/`docs-serve`/`docs-full`/`docs-clean` ターゲット追加（`docs-full` は P3 まで coverage 未実装 warning のみ） | `make docs-serve` でローカル閲覧できる |
| P2: 1モジュール実証 | 1 日 | `services/README.md` 作成、`docs/living-docs/manifest.yml` 骨格、`maintaining-living-docs` Skill 草案、`make docs-check` の最小版、edit-time フックの手動試行 | `services` を変更 → README 更新ループが回り `make docs-check` が違反を検出する |
| P3: 残り展開 | 2〜3 日 | 残り 6 モジュール (`cli`, `ingestion`, `models`, `repositories`, `shared`, `web`) + パッケージルートの README を AI 主導で生成→人間レビュー。L1 生成物を追加 (`adr-index`, `spec-plan-cross-ref`, `test-coverage-map`)。manifest に既存 spec/plan を全件登録 | Docusaurus サイドバーに全 module が並ぶ、リンク切れゼロ |
| P4: 強制機構の本番化 | 1〜2 日 | `maintaining-living-docs` を superpowers fork に commit、既存スキル結節点を実装、pre-commit hook 接続、`docs/living-docs/ai-rules.md` を一次ソースとして tracked な CLAUDE.md / AGENTS.md を整備 | 連続 3 PR で Skill が忘れず発火、`make docs-check` の warning 出力ゼロ（確認用に `make docs-check-strict` も通る） |

### ロールバック方針
- どのフェーズも以下を削除すれば既存状態に戻る:
  - `docs-site/`
  - `scripts/gen_docs.py`, `Makefile` の追加ターゲット
  - `docs/living-docs/`, `docs/current-work.md`, `docs/system-overview.md`
  - 本仕様で新規作成した root ファイル: `CLAUDE.md`, `AGENTS.md`, `.pre-commit-config.yaml`（`Makefile` が既存でなかった場合は `Makefile` 自体も削除。既存だった場合は追加ターゲットのみ削除）
  - 本仕様で**新規作成した** README に限定: `src/stock_analyze_system/README.md`,
    `src/stock_analyze_system/{cli,ingestion,models,repositories,services,shared,web}/README.md`
  - `.gitignore` の追加行（後述 P1 成果物）
- **既存の README には触らない**:
  - `src/stock_analyze_system/web/static/design-preview/README.md` 等の既存資産は対象外
- Skill は superpowers fork のブランチで開発、安定するまで master に merge しない
- 既存の `docs/superpowers/{specs,plans}/` と `docs/adr/` には触らない（L3 不変原則の自己適用）

## 11. 成功指標

- 新規セッション開始から「触る予定の機能の責務・依存・関連 ADR」を把握するまでの時間が **5 分以内**
- README とコードの実質的な不一致が **連続 3 PR で 0 件**
- レビュー時に「なぜこの実装なのか」を spec/ADR まで辿るのに **クリック 2 回以内**

## 12. 非ゴール

- 既存 spec/plan/ADR の書き直し（L3 不変原則）
- 多言語化（日本語のみ）
- 公開ドキュメントサイトのホスティング（ローカル `make docs-serve` のみ）
- CI ブロック方式の鮮度保証（採用しないと明示）

## 13. オープン課題（実装フェーズで決定）

- 主要サブモジュール（`ingestion/xbrl`, `services/pageindex`, `web/routes`）にも README を置くか、親モジュールに統合するか
- pre-commit framework 上での warning 表示形式と実行タイミング（`pre-commit run` 手動時も含めるか）
- `cli-reference.md` 生成が import 失敗した場合の UI 表示（warning バナー or 省略）
- Docusaurus サイドバー自動展開の深さ（深さ 2 で十分か、3 必要か）
- manifest.yml の運用（手動メンテ前提 vs 簡易バックフィルスクリプトを 1 回だけ流すか）
