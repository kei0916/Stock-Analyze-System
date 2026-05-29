---
last_reviewed: 2026-05-23
scope: in-flight-work
mutable: true
---

# Current Work

> このファイルは mutable な L2 ドキュメントで、進行中の作業を AI が随時更新する。
> 既存 plan のチェックボックスは更新しない（L3 不変原則）。完了した作業はここから削除し、
> 必要なら spec/plan に新しいエントリとして残す。

## In Flight

### A1-A17 Refactoring Continuation
- PR1 (A1 queue XSS) merge 済み (`742eec2`)
- PR2 (A2/A3/A4/A15 ADR-004 alignment) 実装済み (`996875f`..`3ee447a`)
- 2026-05-23 local continuation: A5/A6/A7/A14, A8/A9/A10, A11/A12/A13/A16/A17 を working tree で実装
- Verification: `uv run pytest tests/unit -q` -> 1306 passed / `npm test` -> 36 passed / `git diff --check` clean
- Remaining before integration: commit split review + PR3/PR4/PR5 integration/E2E gates

### Living Docs P2 (services README 実証)
- **⛔ 着手前必読**: `docs/superpowers/plans/2026-05-23-living-docs-p2-services.md` §0
  (可視化ページ統合 2026-05-22 の影響 — spec §8 更新と freshness 設計判断が P2 スコープに入る)
- services モジュールの README を Living Docs 方式で実証する
- `maintaining-living-docs` Skill 草案と P2 plan を作成する
- 関連: `docs/superpowers/specs/2026-05-19-living-docs-design.md`

## Next Up

- Living Docs P3: 残り 6 モジュール展開 + adr-index/spec-plan-cross-ref/test-coverage-map 生成器
- Living Docs P4: Skill 本番化、pre-commit hook、CLAUDE.md/AGENTS.md 整備

## Recently Landed (last ~7 days)

- 2026-05-22: プロジェクト可視化ページ (`/visualization`) を `docs-site/` に統合
  (`src/pages/visualization.jsx`, `src/components/visualization/`, `static/fonts/`)。
  ルート `.gitignore` を `data/` → `/data/` にアンカー化(Living Docs と独立の修正)。
  P2 着手前必読事項を `docs/superpowers/plans/2026-05-23-living-docs-p2-services.md` §0 にまとめた
- Living Docs P1 基盤: L1 生成器 3 種、Docusaurus viewer、Makefile docs targets を追加 (`3f95613`..`1a745a5`)
- A1-A17 リファクタリング PR1 (queue + XSS prevention) merge 済み (`742eec2`)
- ADR-004 の amendments（SEC 専用化、pageindex.enabled 分離）
