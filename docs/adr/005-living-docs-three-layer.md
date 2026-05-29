# ADR-005: 認知負荷を低減する 3 層 Living Docs 体系を導入する

## Situation

Stock Analyze System は spec 20+ / plan 30+ / ADR 4+ の豊富なドキュメント
資産を持つが、(1) 新規セッション開始時の全体像把握、(2) 個別モジュールの
責務・依存・設計意図の把握、(3) コード変更レビュー時の意図確認、(4) 既存
ドキュメントの鮮度・整合性、の 4 領域で継続的な認知負荷が発生している。
特に「ドキュメントを信用してよいか」の鮮度問題が最大の障害になっている。

## Complication

「ドキュメントを増やす」では解決しない。一方でドキュメントとコードの
鮮度を CI ブロックで強制すると、雛形修正やリファクタ時のノイズ・摩擦が
大きく、運用が破綻する。鮮度保証を「警告止まり」にすると意味がなく、
「ブロック」にすると現実的に回らない、というジレンマがある。さらに本
プロジェクトは Claude Code（superpowers）と Codex 等の複数 AI を併用
するため、ある AI ツールに閉じた解（Skill のみ）では不十分。

## Question

ドキュメント体系の構造・配置・鮮度保証機構をどう設計すれば、人間が
信頼して短時間で把握でき、かつ運用が破綻しないか。

## Answer

**Decision**: ドキュメントを 3 層に分離し、層ごとに別の鮮度保証機構を採用する。
詳細仕様は `docs/superpowers/specs/2026-05-19-living-docs-design.md`。

- **L1 自動生成** (`docs/generated/`、`.gitignore`): 依存グラフ・モジュール
  index・ADR index 等を `scripts/gen_docs.py` で都度生成。古くなりようがない
- **L2 AI 維持** (`src/<module>/README.md`, `docs/system-overview.md`,
  `docs/current-work.md`, `docs/living-docs/{manifest.yml,ai-rules.md}`):
  Claude Code Skill `maintaining-living-docs` の 3 チェックポイント
  （セッション開始・編集時・コミット直前）で鮮度を維持
- **L3 アーカイブ** (既存 `docs/superpowers/{specs,plans}/`, `docs/adr/`):
  Draft 中のみ mutable、Accepted 後は frontmatter の lifecycle/参照整合性
  以外不変。既存の frontmatter-less spec/plan/ADR は L2 の `manifest.yml`
  で cross-ref 補完する（後付け frontmatter は禁止）

鮮度保証は多層防御:
1. **Skill** が一次防御（Claude Code 限定）
2. **`make docs-check`**（常に exit 0、warn-only）が二次防御
3. **CLAUDE.md / AGENTS.md**（tracked、`ai-rules.md` から同期）が AI 共通の規律
4. **block する経路は意図的に存在しない**（warn のみ）

**Consequences**:
- (+) 「現状を表すドキュメント」と「歴史」が責任分離され、人間が
  信頼して読む対象が明確になる
- (+) 鮮度保証が AI ツールに閉じない（AGENTS.md と `make docs-check` で
  Codex 経由でも規律が効く）
- (+) 既存資産（spec/plan/ADR）に破壊的変更が不要
- (−) L2 が増えた分、AI が更新を忘れた時の鮮度違反が表面化するまでに
  時間がかかる可能性（warn のみで block しないため）
- (−) Docusaurus・pre-commit framework・`scripts/gen_docs.py` という
  新規依存と維持対象が増える
- (−) `manifest.yml` を AI に維持させる新しい運用負荷（既存 spec/plan に
  frontmatter を足さない方針のトレードオフ）

**Alternatives considered**:
- *案 A: 軽量 Skill 駆動のみ*（per-module README + Skill だけ）— 自動
  生成層と repo-owned 強制機構が無く、Claude 以外の AI で規律が効かない
  ため却下
- *案 C: 単一 `CURRENT_STATE.md` + 変更日記*— ファイル肥大化と
  コンフリクト多発、モジュール境界が薄まるため却下
- *CI ブロック方式*— 雛形修正・リファクタ時の摩擦が大きく、ノイズが
  鮮度違反を埋もれさせるため却下（warn-only 多層防御を採用）
- *既存 spec/plan に frontmatter を後付け*— L3 不変原則と衝突するため
  却下（`manifest.yml` で外部補完）

## Status

Accepted
