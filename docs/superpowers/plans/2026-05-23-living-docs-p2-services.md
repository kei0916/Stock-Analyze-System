---
title: Living Docs P2 — services モジュール実証
status: Draft
created: 2026-05-23
author: kei0916
phase: P2
related_specs:
  - docs/superpowers/specs/2026-05-19-living-docs-design.md
related_adrs: ["ADR-005"]
---

> # ⛔ STOP — P2 着手前必読
>
> このセクションを読まずに P2 を進めると、2026-05-22 に追加した可視化ページが
> 鮮度保証の対象外のまま放置され、ADR-005 の目的(鮮度保証)と矛盾します。
> **どのエージェント(Claude Code / Codex / Gemini / 人間)も、最後まで読んでから着手すること。**

# 0. P2 着手前の前提 — 可視化ページ統合の影響整理 (2026-05-22)

## 0.1 何が起きたか

2026-05-22 に Claude Design の可視化プロトタイプを `docs-site/` に統合した:

- 新規: `docs-site/src/pages/visualization.jsx` (ルート `/visualization`)
- 新規: `docs-site/src/components/visualization/` 配下に
  `App.jsx` / `shared.jsx` / `views/{StoryView,ModulesView,ProgressView}.jsx` /
  `data/{terms,content,content-progress,content-modules}.js` /
  `styles/visualization.css`
- 新規: `docs-site/static/fonts/{Inter,JetBrainsMono}-Variable.woff2`
- 修正: `docs-site/docusaurus.config.js` のナビバーに「プロジェクト可視化」項目を追加
- 修正: ルート `.gitignore` の `data/` → `/data/` (アンカー化)。
  以前は任意の階層の `data/` を巻き込んで無視していたため、新規 `docs-site/.../data/` が
  追跡不能だった。アンカー化でルート `./data/` のみ無視するよう修正(Living Docs P1 とは独立の修正)。

## 0.2 P2 で必ず対応すること

### A. spec / doc の整合(短時間で済む)

1. **spec §8 のディレクトリ図を更新**
   - 現状 `docs-site/src/{pages,css/custom.css}` しか挙げていない
   - 実態: `src/{pages, components/visualization/, css/custom.css}`, `static/fonts/` を追加済み
   - §8 の git 管理ポリシー表も同様に更新

2. **`current-work.md` "Recently Landed" への追記**
   - 「2026-05-22: プロジェクト可視化ページ (`/visualization`) を `docs-site/` に統合」

3. **`.gitignore` の `/data/` 化を P2 plan / commit message で「Living Docs と独立の修正」と明記**
   - spec §10 ロールバック節は P1 が*追加した*行しか想定していない
   - 既存行の*編集*なので混同を防ぐ注記が必要

### B. freshness 設計判断 — P2 の本質 (manifest.yml と Skill 草案に直接影響)

可視化の `content*.js` (`terms.js` 含む) は L1 生成物・L2・L3 の情報を手書きで再複製した
「第 4 のコピー」になっており、現状 ADR-005 の L1/L2/L3 モデルに居場所がない。
すなわち P2 で設計する `manifest.yml` / `maintaining-living-docs` Skill /
`make docs-check` の**対象外**として放置される。

具体的な陳腐化リスク:

- `content-progress.js` の roadmap は `currentIndex: 1` (P2 進行中) 固定
  → **P2 完了と同時に古くなる**
- `plansTimeline` は 2026-05-19 で停止しており P2/P3/P4 の plan が反映されない
- ADR 本文 (`PROGRESS.adrs`) は ADR-001..005 の現状を埋め込み済み
- 3 層 Living Docs 図 (`PROGRESS.livingDocs`) は spec(Draft) の現状を埋め込み済み
- 用語 `skill` の解説は「P2 で `maintaining-living-docs` Skill の草案を作る」と
  P2 計画そのものを内容化

**P2 はどちらかを明示的に選ぶ:**

- **(a) 非-living スナップショットとして明示(推奨・低コスト)**
  - 可視化ページに「YYYY-MM-DD 時点のスナップショット」表示を追加
    (data ファイル冒頭 or トップバー右側)
  - spec §12 非ゴールに
    「`docs-site/src/components/visualization/` 配下は鮮度保証の対象外」と 1 行
  - ADR-005 に小さな amendment を 1 行(任意。spec 注記で済むなら不要)

- **(b) governance に載せる**
  - `manifest.yml` に `content.js` / `content-progress.js` / `content-modules.js` /
    `terms.js` を登録
  - Skill 草案に「`services/` 配下を編集したら `content.js` の services 一覧を見直す」
    のチェックポイント追加
  - `make docs-check` に linkage チェック追加

ADR-005 が想定していなかった新ドキュメント面なので、(a)/(b) いずれを選んでも
spec か新規 ADR で位置づけを必ず残す。

### C. 注意のみ・対応不要 (誤って手を入れない)

- `scripts/gen_docs/coordinator.py` は `docs/generated` と `docs-site/docs` だけ
  `rm -rf` する。`docs-site/{src,static,docusaurus.config.js,sidebars.js}` は触らない
  → `make docs` / `make docs-clean` で消えない。**追加処理を入れないこと。**
- `docusaurus.config.js` は tracked / 手編集ファイル。navbar 追記は P2-P4 と
  通常コミットレベルで競合するだけで構造的な問題はない。
- `onBrokenLinks` を P3 以降 `throw` に上げても可視化ページは破綻させない
  (Docusaurus の `<Link>` を持たず、用語モーダルはすべて JS 制御)。
- Docusaurus 検索 (`@easyops-cn/docusaurus-search-local`) は `docs/` をインデックス。
  可視化ページの用語集は `src/` の JS 内なので**検索対象外** — 既知の制約。

## 0.3 着手前チェックリスト

- [ ] §0.2 A-1: spec §8 の図と表を更新
- [ ] §0.2 A-2: `current-work.md` "Recently Landed" 追記
- [ ] §0.2 A-3: P2 の commit message / PR 説明に `.gitignore` 編集の意図を明記
- [ ] §0.2 B: (a)/(b) の選択を明示し、選んだ方の対応を P2 スコープに組み込む
- [ ] §0.2 B: 選択結果を spec §12 か新規 ADR amendment として記録

# 1. P2 本体スコープ (spec §10 P2 行)

> spec line 397 の「成果物」と「終了基準」をそのまま展開する。

## 1.1 成果物

1. `src/stock_analyze_system/services/README.md` を Living Docs L2 スキーマ
   (spec §4) に従って作成
2. `docs/living-docs/manifest.yml` 骨格 — spec §6.5 のクロスリファレンス補完用
3. `maintaining-living-docs` Skill 草案 — superpowers fork のブランチで WIP
4. `make docs-check` の最小版 — README の `last_reviewed` 鮮度を warn-only で出す
5. edit-time フックの手動試行 — Skill の介入点(spec §7) を 1 PR で実走させて確認

## 1.2 終了基準

- `services/` を変更 → README 更新ループが回る
- `make docs-check` が README とコードの不整合を warning として検出する
- §0.3 の着手前チェックリストが全項目チェック済み

# 2. 関連

- spec: `docs/superpowers/specs/2026-05-19-living-docs-design.md`
- ADR: `docs/adr/005-living-docs-three-layer.md`
- 可視化統合の経緯: 2026-05-22 の作業セッション
  (`docs-site/src/components/visualization/` 追加 + 同日リファクタリング)
- 関連メモ: `[[project-living-docs]]`
