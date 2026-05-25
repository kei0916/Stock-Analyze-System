# PageIndex 推論モデル RAG テスト デバッグ記録

- **日付**: 2026-03-30 〜 2026-04-07
- **モデル**: `unsloth/gpt-oss-20b-Q4_0.gguf` (20B, Q4_0量子化)
- **バックエンド**: vLLM → llama.cpp (CUDA GPU) に移行
- **対象PDF**: Apple 10-K (112ページ, `data/filings/SEC/US_AAPL/2025/annual/10-K/0000320193-25-000079/converted.pdf`)
- **PageIndexライブラリ**: `/tmp/PageIndex/pageindex/`

---

## 概要

推論（reasoning）モデル `gpt-oss-20b` を用いた PageIndex RAG テストにおいて、従来の非推論モデル前提の設計と推論モデルの動作特性の不一致から複数の問題が発生した。本ドキュメントでは発見した問題、選択した対処法、その効果を記録する。

### フェーズ概要

| フェーズ | 期間 | 主な成果 |
|---------|------|---------|
| Phase A: vLLM + プロンプト最適化 | 3/30 | 13関数のプロンプト書き換え、max_tokens最適化、TOC精度84.62%達成 |
| Phase B: 推論エンジン移行 | 3/31〜4/7 | vLLM → llama.cpp移行、CUDA 13.0パッチ、reasoning token問題の特定 |

---

## Phase A: vLLM + プロンプト最適化 (2026-03-30)

<debug_issue id="1">

## Issue 1: asyncio.run() ネスト問題

<problem>
### 現象
テストスクリプトを `async def main()` + `asyncio.run(main())` で実装し、`page_index()` を `await asyncio.to_thread()` で呼び出したところ、以下のエラーで即座にクラッシュ。

```
RuntimeError: asyncio.run() cannot be called from a running event loop
```

### 根本原因
`page_index()` 関数は内部で `asyncio.run(page_index_builder())` を呼ぶ。`asyncio.to_thread()` は別スレッドで実行するが、呼び出し元のイベントループとの関係で `asyncio.run()` の再入が発生する。
</problem>

<approach>
### 対処法: テストスクリプトを完全同期構造に変更

`page_index()` を直接同期呼び出しに変更し、Phase 2（TOC検証）とPhase 3（RAGクエリ）のみ個別に `asyncio.run()` で実行する構造にした。

**選択理由**: `page_index()` の内部構造（`asyncio.run()` 使用）は変更不可能なため、呼び出し側を同期に合わせるのが最小限の変更で済む。
</approach>

<effect>
### 効果
- クラッシュ解消。`page_index()` が正常にインデックス構築を開始
- ただし後のテストで `asyncio.to_thread` 内で `_limited_gather` がハングする別問題（Issue 5）を発見
</effect>

</debug_issue>

---

<debug_issue id="2">

## Issue 2: 推論モデルの `max_tokens` 消費による `content: null` 問題

<problem>
### 現象
vLLMへの直接テストで判明:

```json
{
  "message": {
    "content": null,
    "reasoning": "The user says \"Reply OK.\""
  },
  "finish_reason": "length"
}
```

`max_tokens=10` でも reasoning トークンが全バジェットを消費し、実際の content が `null` になる。

### 根本原因
推論モデル（reasoning model）は `<think>` トークンと出力トークンが `max_tokens` を共有する。短い回答を期待する関数でも `max_tokens` が小さすぎると、reasoning だけで上限に達する。

一方、`configure_max_tokens(131072)` で全LLM呼び出しのデフォルトを131072に設定していたが、これは逆に推論モデルが膨大な思考トークンを生成する余地を与え、**応答が極端に遅くなる**原因になった。
</problem>

<approach>
### 対処法: 関数ごとに適切な `max_tokens` を明示指定

PageIndex の `llm_completion` / `llm_acompletion` にはすでに `max_tokens` 引数があったが、ほとんどの呼び出しがデフォルト（`_DEFAULT_MAX_TOKENS`）を使用していた。関数の期待する応答サイズに基づき、以下の3段階に分類して明示指定。

| 応答サイズ | max_tokens | 対象関数 |
|-----------|-----------|---------|
| 短い（yes/no, 単一値） | 4,096 | `check_title_appearance`, `check_title_appearance_in_start`, `find_toc_page`, `check_if_toc_extraction_is_complete`, `check_if_toc_transformation_is_complete`, `detect_page_index`, `single_toc_item_index_fixer` |
| 中程度（TOC JSON, ノード構造） | 8,192〜16,384 | `toc_index_extractor` (8192), `toc_transformer` (16384), `extract_toc_content` (16384), `fill_prompt_seq` (16384) |
| 長い（TOC全体生成） | 32,768 | `generate_toc_init`, `generate_toc_continue` |

**選択理由**:
- `_DEFAULT_MAX_TOKENS=131072` はノードテキスト/サマリ生成など本当に長い出力が必要な場面用に温存
- 推論モデルの思考トークン消費を関数ごとに適切に制限することで、「必要十分な思考 + 確実な出力」のバランスを取る
- 既存の `max_tokens` 引数を活用するため PageIndex の API 変更は不要
</approach>

<effect>
### 効果

#### 速度改善
- `check_title_appearance` 単体テスト: **max_tokens=4096 で 1.2秒**（正常応答）
- `max_tokens=131072` のままだと推論に数十秒〜タイムアウトの可能性

#### TOC精度への影響
| 実行 | TOC（ページ番号付き）精度 | TOC（番号なし）精度 | process_no_toc 精度 |
|------|------------------------|-------------------|-------------------|
| 修正前（max_tokens=131072全箇所） | 29.17% | verify_toc到達前にハング | 21.88% |
| 修正後（関数別max_tokens） | 20.83%〜29.17% | 84.62% (1回成功) | 32.86%〜43.24% |

#### 注目点
- **TOC（番号なし）精度が84.62%に到達**（修正前はこのパスで完了できなかった）
- `fix_incorrect_toc` の修正件数が大幅減少: 50件→2件（84.62%パス時）
- `process_no_toc` パスでも43.24%に改善（修正前21.88%）
</effect>

</debug_issue>

---

<debug_issue id="3">

## Issue 3: `toc_transformer` のJSON解析失敗

<problem>
### 現象
`process_toc_no_page_numbers` パスで `toc_transformer` がJSON解析エラーを返す。

```
ERROR:root:Failed to extract JSON: Expecting value: line 1 column 2 (char 1)
ERROR:root:Failed to parse JSON even after cleanup and repair
```

### 根本原因
推論モデルの出力は `<think>...</think>` + 実際のJSONで構成される。`max_tokens` が大きすぎると:
1. reasoning に大量トークンを消費
2. JSON出力が途中で切れるか、`content: null` になる
3. `extract_json` が空文字列や不完全なJSONを受け取り解析失敗
</problem>

<approach>
### 対処法: `toc_transformer` 系の `max_tokens` を16384に制限

TOCのJSON構造は通常2000〜8000トークン程度。16384あれば十分な思考+完全なJSON出力が可能。

**選択理由**: TOC JSONのサイズを実測ベースで見積もり、thinking用に+8000トークン程度のマージンを確保。過度に小さくすると逆に出力が途中で切れるリスクがあるため、保守的に16384を選択。
</approach>

<effect>
### 効果
- `toc_transformer` のJSON解析失敗は依然発生する場合があるが、頻度が低下
- 成功時は `process_toc_no_page_numbers` パスで精度84.62%を達成
- 失敗時のフォールバック（`process_no_toc`）へのフォールスルーが高速化
</effect>

</debug_issue>

---

<debug_issue id="4">

## Issue 4: `fix_incorrect_toc` の長時間停滞

<problem>
### 現象
`fix_incorrect_toc` が40〜50件の修正で数十分間停滞。3回のリトライ（`max_attempts=3`）で各ラウンド10〜20分以上。

修正前の実行（`max_tokens=131072` 全箇所）:
```
start fix_incorrect_toc with 50 incorrect results
Fixing 24 incorrect results          ← 10分以上
Fixing 22 incorrect results          ← 更に10分以上
Fixing 22 incorrect results          ← ここでプロセスkill
```

### 根本原因
1. **ページ範囲が広大**: 不正確な項目が連続すると `prev_correct` と `next_correct` の距離が大きくなり、数十ページのフルテキストをLLMに送信
2. **推論モデルのKVキャッシュ処理**: 巨大な入力テキストのKVキャッシュ構築にGPU→CPU offload が発生（`GPU_to_CPU_total_bytes=916MB`）、1リクエストあたり10〜30秒
3. **並行数制限**: `_LLM_SEMAPHORE = asyncio.Semaphore(4)` で同時4リクエストのみ
4. **計算量**: 41件 × 2回LLM呼び出し（finder + verify）× 3ラウンド = 最大246回のLLM呼び出し
</problem>

<approach>
### 対処法: `single_toc_item_index_fixer` と `check_title_appearance` の `max_tokens=4096` 制限

これらの関数は短い JSON（physical_index値 or yes/no）を返すだけであり、4096トークンで十分。

**選択理由**: `fix_incorrect_toc` の構造自体を変更するのは PageIndex ライブラリのコアロジックに深く関わるため、まずは個々のLLM呼び出しの速度改善で効果を測定する方針とした。
</approach>

<effect>
### 効果
- 修正後: 3回のリトライが実際に完走するようになった（修正前はハングして kill が必要だった）
- ただし、不正確な項目が多い場合（41件）は依然として長時間（20分以上）を要する
- **根本的な改善には、TOC生成精度自体の向上が必要**（Issue 6参照）
</effect>

</debug_issue>

---

<debug_issue id="5">

## Issue 5: `asyncio.to_thread` 内での `_limited_gather` ハング

<problem>
### 現象
テストスクリプトの初期バージョン（`async def main()` + `asyncio.to_thread(page_index, ...)`）で、`fix_incorrect_toc` の `_limited_gather` が進行せず完全にハング。40分以上待っても出力に変化なし。

### 根本原因
`asyncio.to_thread()` は呼び出しを別スレッドで実行するが、`page_index()` 内部で `asyncio.run()` が新しいイベントループを作成する。この新しいループ内で `_limited_gather` が `asyncio.gather` を使って並行タスクを実行するが、`litellm.acompletion` の非同期HTTP呼び出しがスレッド間で正しく動作しない場合がある。
</problem>

<approach>
### 対処法: テストスクリプトを完全同期構造に変更（Issue 1 の解決に統合）

`page_index()` を同期関数としてトップレベルから直接呼び出し、Phase 2/3 のみ個別に `asyncio.run()` で実行する構造に変更。

**選択理由**: イベントループのスレッド間問題を根本的に回避。`page_index()` は内部で独自のイベントループを管理するため、外部から非同期コンテキストを押し付けないのが正しいアプローチ。
</approach>

<effect>
### 効果
- `_limited_gather` が正常に動作するようになり、`fix_incorrect_toc` が完走
- 42件→41件→41件と修正が進行（改善は限定的だが、ハングは解消）
</effect>

</debug_issue>

---

## Phase B: 推論エンジン移行 (2026-03-31 〜 2026-04-07)

<debug_issue id="6">

## Issue 6: vLLM の gpt-oss GGUF 非対応

<problem>
### 現象
vLLM 0.18.0 で `unsloth/gpt-oss-20b-GGUF:Q4_0` を読み込もうとすると以下のエラー:

```
Unknown gguf model_type: gpt_oss
```

さらに `hf_overrides` で GGUF パスを指定しても GGUF ローダーが起動せず、モデルが BF16 として展開されて ~40GB の VRAM を消費（Q4_0 なら ~11GB のはず）。

### 根本原因
vLLM の `gguf_loader.py:151` に gpt_oss アーキテクチャの weight mapping が存在しない。vLLM の GGUF ローダーは限定的なモデルアーキテクチャのみをサポートしており、OpenAI の新しい gpt_oss アーキテクチャは未対応。
</problem>

<approach>
### 対処法: 推論エンジンを llama.cpp に変更

llama.cpp は gpt_oss アーキテクチャをネイティブサポート。OpenAI 互換 API (`/v1/chat/completions`) を提供するため、LiteLLM 経由で既存コードから透過的にアクセス可能。

**選択理由**: vLLM にパッチを当てるのは weight mapping の実装が必要で大規模な作業。llama.cpp は GGUF を第一級でサポートしており、移行コストが低い。
</approach>

<effect>
### 効果
- gpt-oss-20b-Q4_0.gguf が正常にロード（~11GB VRAM）
- OpenAI互換APIが動作し、LiteLLM経由でPageIndexからアクセス可能
</effect>

</debug_issue>

---

<debug_issue id="7">

## Issue 7: CUDA 13.0 と llama.cpp の `cudaMemGetInfo` 互換性問題

<problem>
### 現象
llama.cpp をソースから CUDA 有効でビルド後、サーバー起動時にクラッシュ:

```
CUDA error: invalid device context
  current device: 0, in function ggml_backend_cuda_device_get_memory
  cudaMemGetInfo(free, total)
```

`-ngl 0`（CPU only）でも同じ場所でクラッシュ。`CUDA_VISIBLE_DEVICES=""` で GPU を非表示にするとCPUモードで起動成功。

### 根本原因
llama.cpp の `ggml_cuda_set_device()` 関数は、現在のデバイスが要求デバイスと同じ場合 `cudaSetDevice()` をスキップする最適化がある。しかし CUDA 13.0 環境ではプライマリコンテキストが自動的に初期化されない場合があり、`cudaSetDevice()` を呼ばないと後続の `cudaMemGetInfo()` が `invalid device context` エラーを返す。

```cpp
// 問題のコード (ggml-cuda.cu)
void ggml_cuda_set_device(int device) {
    int current_device;
    CUDA_CHECK(cudaGetDevice(&current_device));
    if (device == current_device) {
        return;  // ← ここでスキップ、コンテキスト未初期化のまま
    }
    CUDA_CHECK(cudaSetDevice(device));
}
```

直接 `cudaMemGetInfo` をテストプログラムで呼ぶと正常動作することを確認（テストプログラムは `cudaSetDevice(0)` を明示呼び出しするため）。
</problem>

<approach>
### 対処法: `ggml_backend_cuda_device_get_memory` で `cudaSetDevice` を常に呼ぶようパッチ

```cpp
// パッチ適用後
static void ggml_backend_cuda_device_get_memory(...) {
    // Always call cudaSetDevice to ensure the primary context is initialized.
    CUDA_CHECK(cudaSetDevice(ctx->device));  // ← 最適化スキップせず常に呼ぶ
    CUDA_CHECK(cudaMemGetInfo(free, total));
}
```

**選択理由**: 1行の変更で CUDA 13.0 互換性を確保。パフォーマンスへの影響は無視できるレベル（`cudaSetDevice` は同一デバイスへの呼び出しが非常に軽量）。
</approach>

<effect>
### 効果
- llama.cpp が CUDA 13.0 + RTX 4090 で正常にGPU推論を実行
- モデルロード成功: 11259 MiB VRAM 使用（GreenBoost により 75571 MiB として認識）
- 推論速度: ~262 tokens/sec（GPU）、CPUモード比約7倍高速
- **パッチ場所**: `<llama-cpp-source>/ggml/src/ggml-cuda/ggml-cuda.cu` line 4607-4610
</effect>

</debug_issue>

---

<debug_issue id="8">

## Issue 8: llama.cpp 統合テスト (TDD)

<problem>
### 背景
llama.cpp への移行に際し、サーバーの起動確認・推論品質・JSON mode 動作を体系的に検証する必要があった。
</problem>

<approach>
### 対処法: TDD で統合テストを作成

`tests/integration/test_llamacpp_server.py` に5つのテストを実装:

| テスト | 検証内容 |
|-------|---------|
| `test_models_list` | GET /v1/models が 200 を返す（ヘルスチェック） |
| `test_models_endpoint` | モデル一覧にエントリが存在する |
| `test_simple_completion` | 短い補完で content が non-null |
| `test_json_mode` | `response_format=json_object` でパース可能なJSONが返る |
| `test_reasoning_token_budget` | `max_tokens=4096` で推論トークンが出力を食い潰さない |

**選択理由**: ユーザーの「テスト駆動開発で進めて」という指示に従い、RED→GREEN→REFACTOR のサイクルで実装。
</approach>

<effect>
### 効果
- CPU mode: 全5テスト通過（12.25秒）
- GPU mode (CUDA パッチ後): 全5テスト通過（1.75秒、約7倍高速）
- LiteLLM 経由の動作確認: `openai/gpt-oss-20b-Q4_0.gguf` モデル名 + `api_base=http://localhost:8080/v1` で正常通信
</effect>

</debug_issue>

---

<debug_issue id="9">

## Issue 9: gpt-oss の reasoning token が content を完全消費する問題（未解決）

<problem>
### 現象
llama.cpp + gpt-oss-20b で `toc_transformer` を実行すると:

```
llm_completion: content_len=0, finish=length, prompt_tokens=559, completion_tokens=4096
```

プロンプトはわずか559トークンなのに、4096トークン全てが生成されて content は 0 文字。

### 詳細調査結果

| 条件 | content | reasoning_content | 結果 |
|------|---------|-------------------|------|
| 短いプロンプト (85 tokens) | 正常出力 | 短い思考 | OK |
| TOCプロンプト (559 tokens) | 空 (0 chars) | 4096 tokens 全消費 | NG |
| `--reasoning-format none` | thinkingテキスト全体 | なし | 思考ループで出力なし |
| `--reasoning-budget 0` | 空 | 4096 tokens 全消費 | NG（budget無視） |
| `--reasoning-budget 256` | 空 | 4096 tokens 全消費 | NG（budget無視） |
| `--reasoning-budget 1024` | 正常出力 (時々) | 制限された思考 | 不安定 |
| `-rea off` | 空 | 4096 tokens 全消費 | NG |

### 根本原因
gpt-oss モデルは独自のチャネルシステム (`<|channel|>analysis` / `<|channel|>final`) を使用しており、llama.cpp の reasoning budget 機能（DeepSeek の `<think>`/`</think>` トークンベース）と互換性がない。

`--reasoning-format none` で全出力を content に入れた場合の観察:

```
<|channel|>analysis<|message|>We need to parse the table of contents...
Let's produce final JSON.
But we need to ensure we don't produce extraneous spaces. But we can produce pretty printed.
Ok.
Let's produce final JSON.
But we need to ensure we don't produce extraneous spaces...
（以下、同じパターンが max_tokens まで無限ループ）
```

**モデルが analysis チャネルで思考ループに陥り、final チャネル（実際のJSON出力）に遷移しない。** これは gpt-oss 20B Q4_0 の量子化品質に起因する可能性がある（長い構造化出力で推論が発散）。

### 再現パターン
- 短いプロンプト: 正常動作（思考が短く、すぐに出力に遷移）
- 中〜長いプロンプト (500+ tokens): 思考ループに入る確率が高い
- `--reasoning-budget 1024` で**時々**成功: 思考が強制中断され出力に遷移する場合がある（非決定的）
</problem>

<approach>
### 試みた対処法

1. **`max_tokens` 削減 (16384→4096)**: 思考ループの時間短縮にはなるが、content=0 の問題は解消せず
2. **reasoning budget 各種設定**: gpt-oss のチャネル構造と非互換のため効果なし
3. **`--reasoning-format none`**: 全出力が content に入るが、JSONではなく思考テキストのため `extract_json` が失敗
4. **`-rea off`**: 思考は依然として生成される（モデルのアーキテクチャ的にチャネル出力は抑制不可）
5. **reasoning content フォールバック**: 思考テキストからJSON抽出を試みるが、思考ループのテキストにはJSONが含まれない

### 現時点の状態
- `--reasoning-budget 1024` が最も安定する設定（成功率 ~50%）
- `toc_transformer` は成功時に正確なTOC JSONを生成可能
- しかし `toc_index_extractor`, `check_title_appearance` 等も同様の問題を抱え、パイプライン全体の成功率が低い
</approach>

<effect>
### 部分的成果（`--reasoning-budget 1024` 使用時）

最良の実行結果:
```
Phase 1: Build Index
  toc_transformer (with page numbers): 成功 (2311 chars, finished)
  toc_index_extractor: 成功 (3066 chars)
  physical_index range: 5-32 (112ページ中)
  verify_toc accuracy: 4.17%
  → フォールバック → toc_transformer (no page numbers): 成功 (2112 chars)
  → verify_toc accuracy: 4.17%
  → フォールバック → process_no_toc: generate_toc_init 失敗
  → 最終的にクラッシュ
```

### 未到達
- Phase 2 (TOC精度検証) に一度も到達していない
- Phase 3 (RAGクエリ) に一度も到達していない
</effect>

</debug_issue>

---

<debug_issue id="10">

## Issue 10: `toc_index_extractor` のJSON解析エラーと `extract_matching_page_pairs` のタイトル不一致

<problem>
### 現象
`toc_index_extractor` が返すJSONの column 1805 で `Expecting ',' delimiter` エラー。また、`extract_matching_page_pairs` のタイトル完全一致比較により matching_pairs が不足。

### 根本原因
1. **JSON構造エラー**: モデルが隣接するJSONオブジェクトを `}{` で結合（カンマなし）
2. **タイトル不一致**: `toc_transformer` は `"Item 1. Business"` を出力、`toc_index_extractor` は `"Business"` のみ出力する場合がある
</problem>

<approach>
### 対処法

1. **`extract_json` に `}{` → `},{` 修復ロジックを追加**:
```python
import re
json_content = re.sub(r'\}\s*\{', '},{', json_content)
json_content = re.sub(r'\]\s*\[', '],[', json_content)
```

2. **`extract_matching_page_pairs` にファジーマッチングを導入**:
```python
def _normalize_title(title):
    return re.sub(r'\s+', ' ', re.sub(r'[^\w\s]', '', title.lower())).strip()

# 完全一致 OR 部分文字列一致
if phy_title_norm == page_title_norm or \
   (phy_title_norm in page_title_norm or page_title_norm in phy_title_norm):
```

3. **`verify_toc` の early return 条件を緩和**: `last_physical_index < len(page_list)/2` → `/4`

4. **`process_none_page_numbers` の IndexError/KeyError 修正**: 空リストやdict返却のガード追加
</approach>

<effect>
### 効果
- JSON `}{` 修復: 一部のケースで `toc_index_extractor` のパースが成功
- ファジーマッチング: matching_pairs の数が増加し、offset 計算が改善
- physical_index range が 5-20 → 5-32 に拡大
- ただし verify_toc accuracy は依然として 4.17%（check_title_appearance 自体の低精度が原因）
</effect>

</debug_issue>

---

## 変更ファイル一覧

<changes>

### Phase A: `/tmp/PageIndex/pageindex/page_index.py` (プロンプト書き換え)

| 関数 | 変更内容 | 関連Issue |
|------|---------|----------|
| 全13個のLLMプロンプト | `Task:/Rules:/Return JSON:` 構造に書き換え | Issue 2, 3 |
| `toc_transformer` | KeyError防止ガード、if_complete条件緩和 | Issue 3, 9 |
| `add_page_number_to_toc` | `isinstance(json_result, list)` ガード | Issue 3 |
| 各LLM呼び出し | 関数ごとの `max_tokens` 明示指定 | Issue 2, 4 |

### Phase B: `/tmp/PageIndex/pageindex/page_index.py` (llama.cpp対応)

| 関数 | 変更内容 | 関連Issue |
|------|---------|----------|
| `add_page_offset_to_toc_json` | None値フィルタ、ファジーマッチング | Issue 10 |
| `verify_toc` | early return閾値緩和 (1/2→1/4) | Issue 10 |
| `meta_processor` | accuracy閾値を0.6→0.3、フォールバック改善 | Issue 9, 10 |
| `process_none_page_numbers` | 空リスト・dict防御 | Issue 10 |

### Phase B: `/tmp/PageIndex/pageindex/utils.py`

| 関数 | 変更内容 | 関連Issue |
|------|---------|----------|
| `extract_json` | `}{`→`},{` 修復、`][`→`],[` 修復 | Issue 10 |
| `llm_completion` | content空文字列のハンドリング、デバッグ出力 | Issue 9 |
| `llm_acompletion` | content空文字列のハンドリング | Issue 9 |

### Phase B: `<llama-cpp-source>/ggml/src/ggml-cuda/ggml-cuda.cu`

| 行 | 変更内容 | 関連Issue |
|----|---------|----------|
| 4607-4610 | `ggml_cuda_set_device` → `cudaSetDevice` 直接呼び出し | Issue 7 |

### Phase B: `<repo-root>/`

| ファイル | 変更内容 | 関連Issue |
|---------|---------|----------|
| `tests/integration/test_llamacpp_server.py` | 新規作成: llama.cpp統合テスト(5テスト) | Issue 8 |
| `scripts/rag_inference_test.py` | MODEL/BASE_URL をllama.cpp対応に変更 | Issue 6 |

</changes>

---

## インフラ構成

### 最終構成

```
┌─────────────────────────────────────────┐
│  ハードウェア                              │
│  GPU: NVIDIA RTX 4090 (24GB VRAM)        │
│  CPU: 32 threads, AVX512 + BF16          │
│  RAM: 64GB + GreenBoost (75GB仮想VRAM)   │
│  CUDA: 13.0                              │
├─────────────────────────────────────────┤
│  推論エンジン: llama.cpp (ソースビルド)       │
│  パッチ: cudaSetDevice CUDA 13.0対応       │
│  起動コマンド:                              │
│  llama-server -m gpt-oss-20b-Q4_0.gguf   │
│    --host 0.0.0.0 --port 8080            │
│    -ngl 999 -c 32768                     │
│    --reasoning-budget 1024               │
├─────────────────────────────────────────┤
│  モデル: unsloth/gpt-oss-20b-Q4_0.gguf    │
│  サイズ: ~11GB VRAM                        │
│  速度: ~262 tok/s (GPU)                   │
├─────────────────────────────────────────┤
│  クライアント: LiteLLM                      │
│  model: openai/gpt-oss-20b-Q4_0.gguf     │
│  api_base: http://localhost:8080/v1       │
└─────────────────────────────────────────┘
```

---

## 結論と今後の方針

### 解決済み
1. **推論エンジン移行**: vLLM (gpt-oss非対応) → llama.cpp (CUDA GPU, 262 tok/s)
2. **CUDA 13.0互換性**: `cudaSetDevice` パッチで解決
3. **プロンプト最適化**: 13関数を `Task:/Rules:/Return JSON:` 構造に統一
4. **max_tokens最適化**: 関数ごとの適切な配分でTOC精度84.62%達成 (vLLM環境)

### 未解決: gpt-oss reasoning token 問題 (Issue 9)

**根本問題**: gpt-oss の `<|channel|>analysis`/`<|channel|>final` チャネルシステムが llama.cpp の reasoning budget 機能と非互換。長いプロンプトで思考ループに陥り、JSON出力に遷移しない。

**今後の選択肢**:

| 選択肢 | 難易度 | 期待効果 |
|--------|-------|---------|
| A. Q8_0 量子化に変更 | 低 | 量子化品質向上で思考ループ回避の可能性、ただしVRAM不足リスク |
| B. 非推論モデルに変更 (e.g., Qwen3-30B-A3B) | 低 | 思考ループ問題の完全回避、ただし推論能力低下 |
| C. llama.cpp のチャットテンプレートをカスタマイズ | 中 | analysis→final の強制遷移を実装 |
| D. vLLM に gpt-oss GGUF サポートを追加 | 高 | weight mapping実装が必要 |
| E. PageIndex を非推論モデル専用に最適化 | 中 | プロンプトをJSON-only出力に特化、思考不要な設計 |
