# ADR 002: Filing Content Auto-Recovery on DB-Filesystem Mismatch

## Decision
`storage_path` が NULL だがファイルシステムに実体が存在する場合、
再ダウンロードせずに DB を自動復元する。

## Context
- PageIndex 構築 (build_index) は LLM クエリを伴う重い処理で失敗しやすい
- `ensure_content()` → `update_storage()` → `build_index()` の同一トランザクション内で
  `build_index` が失敗すると rollback され、`storage_path` の更新が巻き戻される
- ファイルシステム上のファイルは残るため、DB・ファイル不整合が発生
- 再ダウンロードを試みると、SEC submissions JSON に未反映の新規 accession で
  `get_primary_document_url()` が ValueError を返す場合がある

## Alternatives Considered
1. `build_index` を別トランザクションで実行 → 理想だが実装コスト大、既存セッション
   管理への影響範囲が広い
2. rollback 時にファイルシステムもクリーンアップ → 失敗時のファイル残存を許容する
   方針との整合性が必要
3. 現状の症状緩和（選択）→ 最小侵入、即座にユーザー影響を解消

## Consequences
- ユーザーは再ダウンロード失敗を経由せずに分析を再開できる
- 不整合の根本原因（同一トランザクション内の重い処理）は解消されていない
- 将来的に Alternative 1 または 2 で根本修正すべき
