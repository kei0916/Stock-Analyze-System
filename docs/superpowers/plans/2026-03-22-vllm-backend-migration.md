# vLLM Backend Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** LLMバックエンドをOllama/vLLM切り替え可能にし、PageIndex全体でapi_baseを伝播させる。

**Architecture:** LiteLLMの抽象化レイヤーを活用し、settings.yamlの設定変更だけでOllama/vLLMを切り替える。PageIndex外部ライブラリには`api_base`パラメータを全LLM呼び出し関数に追加し、`opt`configオブジェクト経由で伝播させる。

**Tech Stack:** Python, LiteLLM, vLLM, AWQ (QuantTrio/Qwen3.5-27B-AWQ)

---

## File Structure

| ファイル | 責務 | 変更種別 |
|---|---|---|
| `src/stock_analyze_system/services/llm_client.py` | LLMクライアントラッパー | 修正（`base_url`プロパティ追加） |
| `/tmp/PageIndex/pageindex/config.yaml` | PageIndexデフォルト設定 | 修正（`api_base`追加） |
| `/tmp/PageIndex/pageindex/utils.py` | PageIndex LLMユーティリティ | 修正（`api_base`引数追加） |
| `/tmp/PageIndex/pageindex/page_index.py` | PageIndexメインロジック | 修正（22関数に`api_base`追加） |
| `src/stock_analyze_system/services/pageindex_service.py` | PageIndex統合サービス | 修正（`api_base`をPageIndexに渡す） |
| `config/settings.yaml.example` | 設定例ファイル | 修正（vLLM設定例追加） |
| `pyproject.toml` | プロジェクト設定 | 修正（vllmオプショナル依存追加） |
| `tests/unit/services/test_llm_client.py` | LlmClientテスト | 修正（vLLMテスト追加） |
| `tests/unit/services/test_pageindex_service.py` | PageIndexServiceテスト | 修正（api_baseテスト追加） |

---

### Task 1: LlmClient に base_url プロパティを追加

**Files:**
- Modify: `src/stock_analyze_system/services/llm_client.py:9-13`
- Test: `tests/unit/services/test_llm_client.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/services/test_llm_client.py` at the end of `TestResolveModel` class:

```python
class TestBaseUrlProperty:
    def test_base_url_returns_config_value(self):
        config = LlmConfig(base_url="http://localhost:8000/v1")
        client = LlmClient(config)
        assert client.base_url == "http://localhost:8000/v1"

    def test_base_url_ollama_default(self):
        config = LlmConfig()
        client = LlmClient(config)
        assert client.base_url == "http://localhost:11434"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd <repo-root> && python -m pytest tests/unit/services/test_llm_client.py::TestBaseUrlProperty -v`
Expected: FAIL with `AttributeError: 'LlmClient' object has no attribute 'base_url'`

- [ ] **Step 3: Write minimal implementation**

Add to `src/stock_analyze_system/services/llm_client.py` after `__init__` (line 13), before `resolve_model`:

```python
    @property
    def base_url(self) -> str:
        """LLMバックエンドのベースURLを返す"""
        return self._config.base_url
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd <repo-root> && python -m pytest tests/unit/services/test_llm_client.py::TestBaseUrlProperty -v`
Expected: PASS

- [ ] **Step 5: Add vLLM resolve_model tests**

Add to `tests/unit/services/test_llm_client.py` inside `TestResolveModel`:

```python
    def test_vllm_model_format(self):
        config = LlmConfig(
            model="openai/QuantTrio/Qwen3.5-27B-AWQ",
            model_quality="openai/QuantTrio/Qwen3.5-27B-AWQ",
        )
        client = LlmClient(config)
        assert client.resolve_model(quality=False) == "openai/QuantTrio/Qwen3.5-27B-AWQ"
        assert client.resolve_model(quality=True) == "openai/QuantTrio/Qwen3.5-27B-AWQ"
```

- [ ] **Step 6: Run all LlmClient tests**

Run: `cd <repo-root> && python -m pytest tests/unit/services/test_llm_client.py -v`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
cd <repo-root>
git add src/stock_analyze_system/services/llm_client.py tests/unit/services/test_llm_client.py
git commit -m "feat: add base_url property to LlmClient for vLLM support"
```

---

### Task 2: PageIndex utils.py に api_base 引数を追加

**Files:**
- Modify: `/tmp/PageIndex/pageindex/utils.py:31-55` (llm_completion)
- Modify: `/tmp/PageIndex/pageindex/utils.py:59-81` (llm_acompletion)
- Modify: `/tmp/PageIndex/pageindex/utils.py:577-585` (generate_node_summary)
- Modify: `/tmp/PageIndex/pageindex/utils.py:588-595` (generate_summaries_for_structure)
- Modify: `/tmp/PageIndex/pageindex/utils.py:621-631` (generate_doc_description)

Note: PageIndex is an external library at `/tmp/PageIndex/` and does not have its own test suite in this project. Changes will be verified via the integration test in Task 6.

- [ ] **Step 1: Add `api_base` to `llm_completion`**

In `/tmp/PageIndex/pageindex/utils.py`, change line 31:

```python
# Before:
def llm_completion(model, prompt, chat_history=None, return_finish_reason=False):

# After:
def llm_completion(model, prompt, chat_history=None, return_finish_reason=False, api_base=None):
```

And change the `litellm.completion` call at line 36-40:

```python
# Before:
            response = litellm.completion(
                model=model,
                messages=messages,
                temperature=0,
            )

# After:
            response = litellm.completion(
                model=model,
                messages=messages,
                temperature=0,
                api_base=api_base,
            )
```

- [ ] **Step 2: Add `api_base` to `llm_acompletion`**

Change line 59:

```python
# Before:
async def llm_acompletion(model, prompt):

# After:
async def llm_acompletion(model, prompt, api_base=None):
```

And change the `litellm.acompletion` call at line 67-70:

```python
# Before:
            response = await litellm.acompletion(
                model=model,
                messages=messages,
                temperature=0,
            )

# After:
            response = await litellm.acompletion(
                model=model,
                messages=messages,
                temperature=0,
                api_base=api_base,
            )
```

- [ ] **Step 3: Add `api_base` to `generate_node_summary`**

Change line 577:

```python
# Before:
async def generate_node_summary(node, model=None):

# After:
async def generate_node_summary(node, model=None, api_base=None):
```

And change the `llm_acompletion` call at line 584:

```python
# Before:
    response = await llm_acompletion(model, prompt)

# After:
    response = await llm_acompletion(model, prompt, api_base=api_base)
```

- [ ] **Step 4: Add `api_base` to `generate_summaries_for_structure`**

Change line 588:

```python
# Before:
async def generate_summaries_for_structure(structure, model=None):

# After:
async def generate_summaries_for_structure(structure, model=None, api_base=None):
```

And change the task creation at line 590:

```python
# Before:
    tasks = [generate_node_summary(node, model=model) for node in nodes]

# After:
    tasks = [generate_node_summary(node, model=model, api_base=api_base) for node in nodes]
```

- [ ] **Step 5: Add `api_base` to `generate_doc_description`**

Change line 621:

```python
# Before:
def generate_doc_description(structure, model=None):

# After:
def generate_doc_description(structure, model=None, api_base=None):
```

And change the `llm_completion` call at line 629:

```python
# Before:
    response = llm_completion(model, prompt)

# After:
    response = llm_completion(model, prompt, api_base=api_base)
```

- [ ] **Step 6: Add `api_base` to PageIndex `config.yaml`**

Add `api_base` to `/tmp/PageIndex/pageindex/config.yaml`:

```yaml
model: "gpt-4o-2024-11-20"
api_base: null
toc_check_page_num: 20
max_page_num_each_node: 10
max_token_num_each_node: 20000
if_add_node_id: "yes"
if_add_node_summary: "yes"
if_add_doc_description: "no"
if_add_node_text: "no"
```

- [ ] **Step 7: Verify import works**

Run: `cd /tmp/PageIndex && python -c "from pageindex.utils import llm_completion, llm_acompletion, generate_node_summary, generate_doc_description; print('OK')"`
Expected: `OK`

- [ ] **Step 8: Commit**

```bash
cd /tmp/PageIndex
git add pageindex/utils.py pageindex/config.yaml
git commit -m "feat: add api_base parameter to LLM functions for vLLM support"
```

---

### Task 3: PageIndex page_index.py の23関数に api_base を追加

**Files:**
- Modify: `/tmp/PageIndex/pageindex/page_index.py`

This task modifies 23 functions (22 intermediate + 1 entry point) to accept and propagate `api_base`. The pattern is mechanical but there are important caveats:

1. Add `api_base=None` to each function signature (after `model=None`)
2. Pass `api_base=api_base` to every `llm_completion`/`llm_acompletion` call inside the function
3. Pass `api_base=api_base` to every inter-function call that also takes `model`

**CRITICAL — positional argument hazard:** Several functions pass `model` positionally (not as keyword). When adding `api_base` between `model` and `logger` in signatures, ALL callers that pass `model` positionally MUST be converted to keyword form. Otherwise `logger` values silently end up in `api_base`. This task converts all positional `model` calls to keyword form.

For functions that use `opt` (like `find_toc_pages`, `check_toc`, `meta_processor`, `tree_parser`, `process_large_node_recursively`, `page_index_main`), access `opt.api_base` instead.

- [ ] **Step 1: Modify functions 1-7 (TOC detection & extraction)**

Each function gets `api_base=None` added after `model=None` and passes it to LLM calls:

**`toc_detector_single_page` (line 104):**
```python
# Before:
def toc_detector_single_page(content, model=None):
    # ...
    response = llm_completion(model=model, prompt=prompt)

# After:
def toc_detector_single_page(content, model=None, api_base=None):
    # ...
    response = llm_completion(model=model, prompt=prompt, api_base=api_base)
```

**`check_if_toc_extraction_is_complete` (line 124):**
```python
def check_if_toc_extraction_is_complete(content, toc, model=None, api_base=None):
    # ...
    response = llm_completion(model=model, prompt=prompt, api_base=api_base)
```

**`check_if_toc_transformation_is_complete` (line 142):**
```python
def check_if_toc_transformation_is_complete(content, toc, model=None, api_base=None):
    # ...
    response = llm_completion(model=model, prompt=prompt, api_base=api_base)
```

**`extract_toc_content` (line 159) — has 6+ inner LLM calls:**
```python
def extract_toc_content(content, model=None, api_base=None):
```
Inner calls to update (ALL of them):
- Line 167: `llm_completion(model=model, prompt=prompt, return_finish_reason=True)` → add `api_base=api_base`
- Line 169: `check_if_toc_transformation_is_complete(content, response, model)` → change to `check_if_toc_transformation_is_complete(content, response, model=model, api_base=api_base)` (**positional → keyword**)
- Line 178: `llm_completion(model=model, prompt=prompt, chat_history=chat_history, return_finish_reason=True)` → add `api_base=api_base`
- Line 180: `check_if_toc_transformation_is_complete(content, response, model)` → same keyword conversion
- Line 195: `llm_completion(model=model, prompt=prompt, chat_history=chat_history, return_finish_reason=True)` → add `api_base=api_base`
- Line 197: `check_if_toc_transformation_is_complete(content, response, model)` → same keyword conversion

**`detect_page_index` (line 201):**
```python
def detect_page_index(toc_content, model=None, api_base=None):
    # ...
    response = llm_completion(model=model, prompt=prompt, api_base=api_base)
```

**`toc_extractor` (line 221) — `model` is positional:**
```python
def toc_extractor(page_list, toc_page_list, model, api_base=None):
```
Inner call to update (only one LLM-related call):
- Line 232: `detect_page_index(toc_content, model=model)` → add `api_base=api_base`

**`toc_index_extractor` (line 242):**
```python
def toc_index_extractor(toc, content, model=None, api_base=None):
    # ...
    response = llm_completion(model=model, prompt=prompt, api_base=api_base)
```

- [ ] **Step 2: Modify functions 8-10 (TOC transformation & title checking)**

**`toc_transformer` (line 272) — has multiple inner LLM calls:**
```python
def toc_transformer(toc_content, model=None, api_base=None):
```
Inner calls to update:
- Line 294: `llm_completion(model=model, prompt=prompt, return_finish_reason=True)` → add `api_base=api_base`
- Line 295: `check_if_toc_transformation_is_complete(toc_content, last_complete, model)` → change to `check_if_toc_transformation_is_complete(toc_content, last_complete, model=model, api_base=api_base)` (**positional → keyword**)
- Line 323: `llm_completion(model=model, prompt=prompt, return_finish_reason=True)` → add `api_base=api_base`
- Line 329: `check_if_toc_transformation_is_complete(toc_content, last_complete, model)` → same keyword conversion

**`check_title_appearance` (line 13):**
```python
async def check_title_appearance(item, page_list, start_index=1, model=None, api_base=None):
    # ...
    response = await llm_acompletion(model=model, prompt=prompt, api_base=api_base)
```

**`check_title_appearance_in_start` (line 48):**
```python
async def check_title_appearance_in_start(title, page_text, model=None, api_base=None, logger=None):
    # ...
    response = await llm_acompletion(model=model, prompt=prompt, api_base=api_base)
```

- [ ] **Step 3: Modify functions 11-14 (concurrent title checking & TOC generation)**

**`check_title_appearance_in_start_concurrent` (line 74):**
```python
async def check_title_appearance_in_start_concurrent(structure, page_list, model=None, api_base=None, logger=None):
```
Update inner calls to `check_title_appearance_in_start(...)` to pass `api_base=api_base`.

**`add_page_number_to_toc` (line 460):**
```python
def add_page_number_to_toc(part, structure, model=None, api_base=None):
    # ...
    response = llm_completion(model=model, prompt=prompt, api_base=api_base)
```

**`generate_toc_continue` (line 506):**
```python
def generate_toc_continue(toc_content, part, model=None, api_base=None):
```
Update all inner `llm_completion(...)` calls to add `api_base=api_base`.

**`generate_toc_init` (line 541):**
```python
def generate_toc_init(part, model=None, api_base=None):
```
Update all inner `llm_completion(...)` calls to add `api_base=api_base`.

- [ ] **Step 4: Modify functions 15-18 (processing pipelines) — POSITIONAL ARGS**

**`process_no_toc` (line 575) — inner calls use positional `model`:**
```python
def process_no_toc(page_list, start_index=1, model=None, api_base=None, logger=None):
```
Convert positional calls to keyword:
- Line 585: `generate_toc_init(group_texts[0], model)` → `generate_toc_init(group_texts[0], model=model, api_base=api_base)`
- Line 587: `generate_toc_continue(toc_with_page_number, group_text, model)` → `generate_toc_continue(toc_with_page_number, group_text, model=model, api_base=api_base)`

**`process_toc_no_page_numbers` (line 596) — inner calls use positional `model`:**
```python
def process_toc_no_page_numbers(toc_content, toc_page_list, page_list, start_index=1, model=None, api_base=None, logger=None):
```
Convert positional calls to keyword:
- Line 599: `toc_transformer(toc_content, model)` → `toc_transformer(toc_content, model=model, api_base=api_base)`
- Line 611: `add_page_number_to_toc(group_text, toc_with_page_number, model)` → `add_page_number_to_toc(group_text, toc_with_page_number, model=model, api_base=api_base)`

**`process_toc_with_page_numbers` (line 621) — inner calls use positional `model`:**
```python
def process_toc_with_page_numbers(toc_content, toc_page_list, page_list, toc_check_page_num=None, model=None, api_base=None, logger=None):
```
Convert positional calls to keyword:
- Line 622: `toc_transformer(toc_content, model)` → `toc_transformer(toc_content, model=model, api_base=api_base)`
- Line 632: `toc_index_extractor(toc_no_page_number, main_content, model)` → `toc_index_extractor(toc_no_page_number, main_content, model=model, api_base=api_base)`
- Line 647: `process_none_page_numbers(toc_with_page_number, page_list, model=model)` → add `api_base=api_base`

**`process_none_page_numbers` (line 655):**
```python
def process_none_page_numbers(toc_items, page_list, start_index=1, model=None, api_base=None):
```
Inner call to update:
- Line 685: `add_page_number_to_toc(page_contents, item_copy, model)` → `add_page_number_to_toc(page_contents, item_copy, model=model, api_base=api_base)` (**positional → keyword**)

- [ ] **Step 5: Modify functions 19-22 (verification & fixing) — POSITIONAL ARGS**

**`single_toc_item_index_fixer` (line 739):**
```python
async def single_toc_item_index_fixer(section_title, content, model=None, api_base=None):
    # ...
    response = await llm_acompletion(model=model, prompt=prompt, api_base=api_base)
```

**`fix_incorrect_toc` (line 759):**
```python
async def fix_incorrect_toc(toc_with_page_number, page_list, incorrect_results, start_index=1, model=None, api_base=None, logger=None):
```
Update inner calls to `single_toc_item_index_fixer(...)`, `check_title_appearance(...)` to pass `api_base=api_base`.

**`fix_incorrect_toc_with_retries` (line 877) — CRITICAL positional call:**
```python
async def fix_incorrect_toc_with_retries(toc_with_page_number, page_list, incorrect_results, start_index=1, max_attempts=3, model=None, api_base=None, logger=None):
```
**MUST convert line 886 from positional to keyword** to prevent `logger` from being silently passed as `api_base`:
- Line 886: `await fix_incorrect_toc(current_toc, page_list, current_incorrect, start_index, model, logger)` → `await fix_incorrect_toc(current_toc, page_list, current_incorrect, start_index=start_index, model=model, api_base=api_base, logger=logger)`

**`verify_toc` (line 899):**
```python
async def verify_toc(page_list, list_result, start_index=1, N=None, model=None, api_base=None):
```
Update inner calls to `check_title_appearance(...)` to pass `api_base=api_base`.

- [ ] **Step 6: Update opt-based callers in page_index_main flow**

These functions access `opt.model` and need to also pass `opt.api_base`:

**`find_toc_pages` (line 340) — uses `opt` directly:**
Change line 350:
```python
# Before:
        detected_result = toc_detector_single_page(page_list[i][0],model=opt.model)

# After:
        detected_result = toc_detector_single_page(page_list[i][0], model=opt.model, api_base=opt.api_base)
```

**`check_toc` (line 695) — uses `opt` directly:**
Change lines 702 and 723:
```python
# Before:
        toc_json = toc_extractor(page_list, toc_page_list, opt.model)

# After:
        toc_json = toc_extractor(page_list, toc_page_list, opt.model, api_base=opt.api_base)
```

(Apply same change to line 723 `additional_toc_json = toc_extractor(...)`)

**`meta_processor` (line 958) — uses `opt` directly:**
Change lines 963, 965, 967:
```python
# Before:
        toc_with_page_number = process_toc_with_page_numbers(toc_content, toc_page_list, page_list, toc_check_page_num=opt.toc_check_page_num, model=opt.model, logger=logger)

# After:
        toc_with_page_number = process_toc_with_page_numbers(toc_content, toc_page_list, page_list, toc_check_page_num=opt.toc_check_page_num, model=opt.model, api_base=opt.api_base, logger=logger)
```

Apply same pattern to `process_toc_no_page_numbers(...)` (line 965) and `process_no_toc(...)` (line 967).

Change line 978:
```python
# Before:
    accuracy, incorrect_results = await verify_toc(page_list, toc_with_page_number, start_index=start_index, model=opt.model)

# After:
    accuracy, incorrect_results = await verify_toc(page_list, toc_with_page_number, start_index=start_index, model=opt.model, api_base=opt.api_base)
```

Change line 988:
```python
# Before:
        toc_with_page_number, incorrect_results = await fix_incorrect_toc_with_retries(toc_with_page_number, page_list, incorrect_results,start_index=start_index, max_attempts=3, model=opt.model, logger=logger)

# After:
        toc_with_page_number, incorrect_results = await fix_incorrect_toc_with_retries(toc_with_page_number, page_list, incorrect_results, start_index=start_index, max_attempts=3, model=opt.model, api_base=opt.api_base, logger=logger)
```

**`process_large_node_recursively` (line 999) — uses `opt`:**
Change line 1007:
```python
# Before:
        node_toc_tree = await check_title_appearance_in_start_concurrent(node_toc_tree, page_list, model=opt.model, logger=logger)

# After:
        node_toc_tree = await check_title_appearance_in_start_concurrent(node_toc_tree, page_list, model=opt.model, api_base=opt.api_base, logger=logger)
```

**`tree_parser` (line 1028) — uses `opt`:**
Change line 1050:
```python
# Before:
    toc_with_page_number = await check_title_appearance_in_start_concurrent(toc_with_page_number, page_list, model=opt.model, logger=logger)

# After:
    toc_with_page_number = await check_title_appearance_in_start_concurrent(toc_with_page_number, page_list, model=opt.model, api_base=opt.api_base, logger=logger)
```

**`page_index_main` (line 1065) — uses `opt`:**
Change line 1090:
```python
# Before:
            await generate_summaries_for_structure(structure, model=opt.model)

# After:
            await generate_summaries_for_structure(structure, model=opt.model, api_base=opt.api_base)
```

Change line 1096:
```python
# Before:
                doc_description = generate_doc_description(clean_structure, model=opt.model)

# After:
                doc_description = generate_doc_description(clean_structure, model=opt.model, api_base=opt.api_base)
```

- [ ] **Step 7: Update `page_index()` entry point (line 1110)**

```python
# Before:
def page_index(doc, model=None, toc_check_page_num=None, max_page_num_each_node=None, max_token_num_each_node=None,
               if_add_node_id=None, if_add_node_summary=None, if_add_doc_description=None, if_add_node_text=None):

# After:
def page_index(doc, model=None, api_base=None, toc_check_page_num=None, max_page_num_each_node=None, max_token_num_each_node=None,
               if_add_node_id=None, if_add_node_summary=None, if_add_doc_description=None, if_add_node_text=None):
```

The `locals()` dict at line 1113-1116 automatically picks up `api_base` — no other change needed in this function body.

- [ ] **Step 8: Verify syntax and import**

Run: `cd /tmp/PageIndex && python -m py_compile pageindex/page_index.py && python -c "from pageindex.page_index import page_index; print('OK')"`
Expected: `OK`

- [ ] **Step 9: Commit**

```bash
cd /tmp/PageIndex
git add pageindex/page_index.py
git commit -m "feat: propagate api_base through all LLM-calling functions in page_index.py"
```

---

### Task 4: pageindex_service.py から api_base を渡す

**Files:**
- Modify: `src/stock_analyze_system/services/pageindex_service.py:76-86`
- Test: `tests/unit/services/test_pageindex_service.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/services/test_pageindex_service.py` inside `TestBuildIndex`:

```python
    @patch("stock_analyze_system.services.pageindex_service.page_index")
    async def test_build_index_passes_api_base(self, mock_pi, service, llm_client):
        mock_pi.return_value = {"title": "Doc"}
        llm_client.base_url = "http://localhost:8000/v1"

        await service.build_index(Path("/fake/doc.pdf"))

        call_kwargs = mock_pi.call_args[1]
        assert call_kwargs["api_base"] == "http://localhost:8000/v1"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd <repo-root> && python -m pytest tests/unit/services/test_pageindex_service.py::TestBuildIndex::test_build_index_passes_api_base -v`
Expected: FAIL with `KeyError: 'api_base'`

- [ ] **Step 3: Write minimal implementation**

In `src/stock_analyze_system/services/pageindex_service.py`, change lines 76-86:

```python
# Before:
        async with _build_semaphore:
            tree = await asyncio.to_thread(
                page_index,
                str(pdf_path),
                model=model,
                toc_check_page_num=self._config.toc_check_pages,
                max_page_num_each_node=self._config.max_pages_per_node,
                max_token_num_each_node=self._config.max_tokens_per_node,
                if_add_node_summary=self._config.add_node_summary,
                if_add_node_text=self._config.add_node_text,
            )

# After:
        async with _build_semaphore:
            tree = await asyncio.to_thread(
                page_index,
                str(pdf_path),
                model=model,
                api_base=self._llm_client.base_url,
                toc_check_page_num=self._config.toc_check_pages,
                max_page_num_each_node=self._config.max_pages_per_node,
                max_token_num_each_node=self._config.max_tokens_per_node,
                if_add_node_summary=self._config.add_node_summary,
                if_add_node_text=self._config.add_node_text,
            )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd <repo-root> && python -m pytest tests/unit/services/test_pageindex_service.py::TestBuildIndex::test_build_index_passes_api_base -v`
Expected: PASS

- [ ] **Step 5: Run all PageIndexService tests**

Run: `cd <repo-root> && python -m pytest tests/unit/services/test_pageindex_service.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
cd <repo-root>
git add src/stock_analyze_system/services/pageindex_service.py tests/unit/services/test_pageindex_service.py
git commit -m "feat: pass api_base from PageIndexService to page_index()"
```

---

### Task 5: settings.yaml.example と pyproject.toml の更新

**Files:**
- Modify: `config/settings.yaml.example`
- Modify: `pyproject.toml:26-33`

- [ ] **Step 1: Update settings.yaml.example**

Replace the `llm:` section in `config/settings.yaml.example` (lines 16-21) with:

```yaml
llm:
  ## --- Ollama backend ---
  backend: ollama
  base_url: "http://localhost:11434"
  model: "ollama/qwen3.5:27b-q8_0"
  model_quality: "ollama/qwen3.5:27b-q8_0"
  temperature: 0.1
  max_tokens: 32768
  request_timeout: 1200
  ## --- vLLM backend (uncomment below, comment above) ---
  ## Requires: OPENAI_API_KEY=dummy in .env
  ## Start server: vllm serve QuantTrio/Qwen3.5-27B-AWQ --port 8000 --max-model-len 32768 --gpu-memory-utilization 0.9 --trust-remote-code
  # backend: vllm
  # base_url: "http://localhost:8000/v1"
  # model: "openai/QuantTrio/Qwen3.5-27B-AWQ"
  # model_quality: "openai/QuantTrio/Qwen3.5-27B-AWQ"
  # temperature: 0.1
  # max_tokens: 32768
  # request_timeout: 600
```

- [ ] **Step 2: Add vllm optional dependency to pyproject.toml**

After the `dev` section in `[project.optional-dependencies]` (line 33), add:

```toml
vllm = ["vllm>=0.16.0"]
```

- [ ] **Step 3: Verify pyproject.toml syntax**

Run: `cd <repo-root> && python -c "import tomllib; tomllib.load(open('pyproject.toml', 'rb')); print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
cd <repo-root>
git add config/settings.yaml.example pyproject.toml
git commit -m "feat: add vLLM config example and optional dependency"
```

---

### Task 6: 全テスト実行と最終検証

**Files:**
- No new files

- [ ] **Step 1: Run all unit tests**

Run: `cd <repo-root> && python -m pytest tests/ -v`
Expected: All PASS

- [ ] **Step 2: Verify PageIndex import with api_base**

Run: `cd <repo-root> && python -c "from pageindex import page_index; import inspect; sig = inspect.signature(page_index); print(list(sig.parameters.keys())); assert 'api_base' in sig.parameters"`
Expected: Prints parameter list containing `api_base`

- [ ] **Step 3: Verify Ollama backend still works (smoke test)**

Run: `cd <repo-root> && python -m stock_analyze_system rag health`
Expected: Health check returns OK with Ollama backend (if Ollama is running)

- [ ] **Step 4: Commit (if any fixups needed)**

```bash
cd <repo-root>
git add -A
git commit -m "fix: address test/integration issues from vLLM migration"
```
