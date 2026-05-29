# PR1: prevent stored XSS in analysis queue rows — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** ダッシュボードの analysis queue panel における stored XSS リスクを、`renderQueueRow` を HTML template literal から DOM API 化することで根絶する。

**Architecture:** queue 関連の純粋関数 (`QUEUE_BADGE` / `formatQueueElapsed` / `renderQueueRow`) を新規 ES module `queue_panel.js` に切り出し、`app.js` (IIFE) から既存パターン (`analysis_status.js` と同じ動的 `await import('/static/queue_panel.js?v=...')`) で読み込む。test は `jsdom` (devDependency 済み) を使った node:test で書く。

**Tech Stack:** vanilla JS, ES modules, jsdom, `node --test`, `npm test`

**ADR:** Not required — Simple bug fix (XSS escape via DOM API). 設計境界 / 責務 / 依存は変わらない。

**Spec reference:** `docs/superpowers/specs/2026-05-17-additional-refactoring-a1-a17-design.md` §5 (PR1)

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `src/stock_analyze_system/web/static/queue_panel.js` | **Create** | `QUEUE_BADGE` constant / `formatQueueElapsed(iso, now)` / `renderQueueRow(job, doc)` / `replaceQueueRows(listEl, jobs, doc)` を ES module として export。`replaceQueueRows` は app.js から呼ばれる唯一の sink、内部で `listEl.replaceChildren()` + 各 job を `renderQueueRow` で生成して `appendChild` する |
| `tests/js/queue_panel.test.mjs` | **Create** | XSS regression (`company_id` / `current_analysis_type`) / `encodeURIComponent` / dataset / badge mapping (label/cls) / `replaceQueueRows` (XSS-bearing job 混在で safe) / `formatQueueElapsed` の 7 件 |
| `src/stock_analyze_system/web/static/app.js` | **Modify** | (1) line 1706 の `QUEUE_BADGE` (3 key)・line 1712-1719 の `formatQueueElapsed`・line 1721-1740 の `renderQueueRow` を削除、(2) line 1753-1773 の `fetchQueue` を「先頭で `listEl.replaceChildren()` → 空時はそのまま return → 非空時のみ `await loadQueuePanelModule()` + `queueMod.replaceQueueRows(listEl, jobs)`」に書き換え (import 失敗時にも古い行が残らない構造)、(3) `queue_panel.js` を `encodeURIComponent(ASSET_VERSION || "1")` パターンで動的 import |

base.html は変更不要 (既存 `analysis_status.js` と同じ動的 import 経路を使う)。

---

## Tasks

### Task 1: queue_panel.js とテストを test-first で作成

**Files:**
- Create: `src/stock_analyze_system/web/static/queue_panel.js`
- Create: `tests/js/queue_panel.test.mjs`

このタスクは app.js を変更しない。新 module と test だけを追加する (TDD: 失敗テスト → 最小実装 → green)。

- [ ] **Step 1.1: 失敗テスト (XSS company_id) を書く**

Create `tests/js/queue_panel.test.mjs`:

```js
import test from "node:test";
import assert from "node:assert/strict";
import { JSDOM } from "jsdom";
import {
    renderQueueRow,
    formatQueueElapsed,
} from "../../src/stock_analyze_system/web/static/queue_panel.js";

const FIXED_NOW = Date.parse("2026-05-13T12:00:00.000Z");

function makeDoc() {
    return new JSDOM("<!doctype html><html><body></body></html>").window.document;
}

test("renderQueueRow escapes company_id HTML", () => {
    const doc = makeDoc();
    const li = renderQueueRow({
        job_id: 1,
        status: "pending",
        company_id: "<img src=x onerror=alert(1)>",
        current_analysis_type: null,
        progress_current: 0,
        progress_total: 4,
        created_at: "2026-05-13T11:59:55.000Z",
    }, doc);
    doc.body.appendChild(li);
    assert.equal(doc.querySelector("img"), null,
        "<img> tag must not be parsed from injected company_id");
    assert.equal(
        doc.querySelector(".event-row__id").textContent,
        "<img src=x onerror=alert(1)>",
    );
});
```

- [ ] **Step 1.2: テストを実行して fail を確認**

Run:
```bash
npm test
```

Expected: Module `queue_panel.js` not found → ERR_MODULE_NOT_FOUND。

- [ ] **Step 1.3: queue_panel.js を最小実装 (DOM 化)**

Create `src/stock_analyze_system/web/static/queue_panel.js`:

```js
// Queue panel の DOM 生成と整形ヘルパ。`app.js` から動的 import される。
// 全ての文字列値は textContent / dataset / encodeURIComponent 経由でセットし、
// stored XSS を防ぐ。

// 現行 `app.js:1706-1710` の QUEUE_BADGE を 1 字も変えずに移植。
// queue API は pending/running/failed のみ表示対象 (`fetchAnalysisJobs(["pending","running","failed"])`)
// なので completed/cancelled は意図的にここに無い。
export const QUEUE_BADGE = {
    pending: { label: "PENDING", cls: "badge--mono" },
    running: { label: "RUNNING", cls: "badge--up" },
    failed: { label: "FAILED", cls: "badge--down" },
};

export function formatQueueElapsed(createdAtIso, now = Date.now()) {
    if (!createdAtIso) return "—";
    const ms = now - new Date(createdAtIso).getTime();
    if (ms < 0) return "00:00";
    const m = Math.floor(ms / 60000);
    const s = Math.floor((ms % 60000) / 1000);
    return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

export function renderQueueRow(job, doc = document) {
    const li = doc.createElement("li");
    li.className = "event-row";

    const badge = QUEUE_BADGE[job.status] ?? { label: job.status, cls: "" };
    const badgeEl = doc.createElement("span");
    badgeEl.className = `badge ${badge.cls}`.trim();
    badgeEl.textContent = badge.label;
    li.appendChild(badgeEl);

    const link = doc.createElement("a");
    link.href = `/stocks/${encodeURIComponent(job.company_id)}`;
    link.className = "event-row__id";
    link.textContent = job.company_id;
    li.appendChild(link);

    const typeEl = doc.createElement("span");
    typeEl.className = "event-row__meta";
    typeEl.textContent = job.current_analysis_type ?? "—";
    li.appendChild(typeEl);

    const progressEl = doc.createElement("span");
    progressEl.className = "event-row__meta";
    progressEl.textContent = `${job.progress_current}/${job.progress_total}`;
    li.appendChild(progressEl);

    const timeEl = doc.createElement("span");
    timeEl.className = "event-row__time";
    timeEl.textContent = formatQueueElapsed(job.created_at);
    li.appendChild(timeEl);

    if (job.status === "failed" || job.status === "pending") {
        const btn = doc.createElement("button");
        btn.className = "btn-icon";
        btn.dataset.action = job.status === "failed" ? "dismiss" : "cancel";
        btn.dataset.jobId = String(job.job_id);
        btn.title = job.status === "failed" ? "非表示" : "キャンセル";
        btn.textContent = "×";
        li.appendChild(btn);
    }

    return li;
}

// app.js から呼ばれる唯一の sink。listEl を一旦 clear した上で、
// 全 job を DOM API で生成して appendChild する。これにより
// `listEl.innerHTML = jobs.map(renderQueueRow).join("")` 系の
// HTML 文字列流し込みを app.js 側からも完全に追放する。
export function replaceQueueRows(listEl, jobs, doc = document) {
    listEl.replaceChildren();
    for (const job of jobs) {
        listEl.appendChild(renderQueueRow(job, doc));
    }
}
```

**事前確認の verify は不要** (本 plan 作成時に `grep -n "const QUEUE_BADGE" src/stock_analyze_system/web/static/app.js` で確認済み: line 1706-1710 で上記 3 key 構成)。実装前に念のため再 grep し、現行値と差分があれば実装側を採用すること。

- [ ] **Step 1.4: テストを実行して pass を確認**

Run:
```bash
npm test
```

Expected: `tests/js/queue_panel.test.mjs > renderQueueRow escapes company_id HTML` が pass。既存 `tests/js/analysis_status.test.mjs` も pass を維持。

- [ ] **Step 1.5: 残りのテストを追加**

`tests/js/queue_panel.test.mjs` に以下 6 件を追記:

```js
test("renderQueueRow escapes current_analysis_type", () => {
    const doc = makeDoc();
    const li = renderQueueRow({
        job_id: 2,
        status: "running",
        company_id: "US_AAPL",
        current_analysis_type: "<script>alert(1)</script>",
        progress_current: 1,
        progress_total: 4,
        created_at: "2026-05-13T11:59:55.000Z",
    }, doc);
    doc.body.appendChild(li);
    assert.equal(doc.querySelector("script"), null,
        "<script> must not be parsed from current_analysis_type");
    const typeEls = li.querySelectorAll(".event-row__meta");
    assert.equal(typeEls[0].textContent, "<script>alert(1)</script>");
});

test("renderQueueRow encodes company_id in href", () => {
    const doc = makeDoc();
    const li = renderQueueRow({
        job_id: 3,
        status: "pending",
        company_id: "US_A/B?C",
        current_analysis_type: null,
        progress_current: 0,
        progress_total: 4,
        created_at: "2026-05-13T11:59:55.000Z",
    }, doc);
    const href = li.querySelector("a").getAttribute("href");
    assert.equal(href, "/stocks/US_A%2FB%3FC");
});

test("renderQueueRow sets data-job-id via dataset on failed/pending only", () => {
    const doc = makeDoc();
    const failed = renderQueueRow({
        job_id: 42, status: "failed", company_id: "US_X",
        current_analysis_type: null, progress_current: 0, progress_total: 4,
        created_at: "2026-05-13T11:59:55.000Z",
    }, doc);
    const dismissBtn = failed.querySelector("button[data-action='dismiss']");
    assert.equal(dismissBtn.dataset.jobId, "42");

    const completed = renderQueueRow({
        job_id: 43, status: "completed", company_id: "US_X",
        current_analysis_type: null, progress_current: 4, progress_total: 4,
        created_at: "2026-05-13T11:59:55.000Z",
    }, doc);
    assert.equal(completed.querySelector("button"), null,
        "completed rows have no action button");
});

test("formatQueueElapsed is now-injectable", () => {
    assert.equal(
        formatQueueElapsed("2026-05-13T11:59:00.000Z", FIXED_NOW),
        "01:00",
    );
    assert.equal(formatQueueElapsed(null, FIXED_NOW), "—");
});

test("QUEUE_BADGE mapping matches current app.js labels and css classes", () => {
    // visual regression を防ぐため、現行値を固定 (Finding 1)。
    // 値を変えるときは spec / UI screenshot レビューも一緒に変えること。
    assert.deepEqual(QUEUE_BADGE.pending, { label: "PENDING", cls: "badge--mono" });
    assert.deepEqual(QUEUE_BADGE.running, { label: "RUNNING", cls: "badge--up" });
    assert.deepEqual(QUEUE_BADGE.failed, { label: "FAILED", cls: "badge--down" });
    // queue API は pending/running/failed のみ表示対象。それ以外は未定義であるべき。
    assert.equal(QUEUE_BADGE.completed, undefined);
    assert.equal(QUEUE_BADGE.cancelled, undefined);
});

test("replaceQueueRows escapes all rows and replaces existing children", () => {
    const doc = makeDoc();
    const listEl = doc.createElement("ul");
    // 既存ノード (前回 fetch の残り想定) を入れておく
    const stale = doc.createElement("li");
    stale.id = "stale";
    listEl.appendChild(stale);
    doc.body.appendChild(listEl);

    replaceQueueRows(listEl, [
        {
            job_id: 1, status: "pending",
            company_id: "<img src=x onerror=alert(1)>",
            current_analysis_type: null,
            progress_current: 0, progress_total: 4,
            created_at: "2026-05-13T11:59:55.000Z",
        },
        {
            job_id: 2, status: "running",
            company_id: "US_AAPL",
            current_analysis_type: "<script>alert(1)</script>",
            progress_current: 1, progress_total: 4,
            created_at: "2026-05-13T11:59:55.000Z",
        },
    ], doc);

    // 古い行が消えていること
    assert.equal(doc.getElementById("stale"), null);
    // XSS が DOM tree に侵入していないこと (sink 経路を 1 箇所に閉じる Finding 2 検証)
    assert.equal(doc.querySelector("img"), null);
    assert.equal(doc.querySelector("script"), null);
    // 2 行追加されていること
    assert.equal(listEl.children.length, 2);
});

// import statement に replaceQueueRows と QUEUE_BADGE を追加するのを忘れずに
// (file 先頭の import を更新する)
```

ファイル先頭の import を以下に更新:

```js
import {
    QUEUE_BADGE,
    renderQueueRow,
    formatQueueElapsed,
    replaceQueueRows,
} from "../../src/stock_analyze_system/web/static/queue_panel.js";
```

- [ ] **Step 1.6: 全テストを実行して pass を確認**

Run:
```bash
npm test
```

Expected: 全 7 件 (`queue_panel.test.mjs`) + 既存 `analysis_status.test.mjs` が pass。

- [ ] **Step 1.7: queue_panel.js / queue_panel.test.mjs を commit**

```bash
git add src/stock_analyze_system/web/static/queue_panel.js tests/js/queue_panel.test.mjs
git commit -m "$(cat <<'EOF'
feat(web): add queue_panel ES module with DOM-API row renderer

`renderQueueRow` / `formatQueueElapsed` / `QUEUE_BADGE` / `replaceQueueRows`
を ES module 化し、全ての値を `textContent` / `dataset` / `encodeURIComponent`
経由でセットする DOM API ベース実装に切り替えた。jsdom + node:test で
XSS / encode / dataset / badge mapping / multi-row replace の 7 件を test 化。

`app.js` への組み込みは次のコミットで行う。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: app.js を queue_panel.js を使う形に書き換える

**Files:**
- Modify: `src/stock_analyze_system/web/static/app.js`
  - 削除: line 1700 付近の `QUEUE_BADGE` 定義
  - 削除: line 1712-1719 の `formatQueueElapsed`
  - 削除: line 1721-1740 の `renderQueueRow`
  - 変更: line 1753-1773 の `fetchQueue` で `innerHTML = ...` を DOM append に置換
  - 追加: queue_panel.js を動的 import するセクション (analysis_status.js と同じパターン)

- [ ] **Step 2.1: app.js の QUEUE_BADGE / formatQueueElapsed / renderQueueRow の元定義範囲を確認**

Run:
```bash
grep -n "QUEUE_BADGE\s*=\|function formatQueueElapsed\|function renderQueueRow" src/stock_analyze_system/web/static/app.js
```

Expected: 各 1 行ずつヒット。実際の行番号を控える (本 plan の line 番号は HEAD `dd98f64` 時点。実装時に行番号がズレている可能性あり)。

- [ ] **Step 2.2: 既存 analysis_status.js の dynamic import パターンを参照する**

Run:
```bash
grep -n "import.*analysis_status" src/stock_analyze_system/web/static/app.js
```

Expected: 1 行ヒット (`await import('/static/analysis_status.js?v=${version}')` 系)。これと同じパターンで queue_panel.js を読み込む。`asset_version` の取得方法 (line 2-4 の `document.currentScript.dataset.assetVersion`) を踏襲。

- [ ] **Step 2.3: app.js の queue 関連コードを queue_panel.js を使う形に書き換える**

3 つの編集を行う:

**(a) `QUEUE_BADGE` / `formatQueueElapsed` / `renderQueueRow` の定義を削除**:

`Edit` ツールで該当 3 ブロックを削除。削除前後に他の関数が依存していないか確認 (closure 内の `applyEvent` / `jobToEvents` 等は queue panel と無関係なので影響なし。`fetchQueue` のみが renderQueueRow を呼ぶ)。

**(b) `fetchQueue` (line 1753-1773 付近) を以下に置換** (Finding 3 対応: 空時 clear が import に依存しない構造):

```js
async function fetchQueue() {
    try {
        const jobs = await fetchAnalysisJobs(["pending", "running", "failed"]);
        if (!jobs) return;
        const listEl = document.getElementById("llm-queue-list");
        const emptyEl = document.getElementById("llm-queue-empty");
        const countEl = document.getElementById("llm-queue-count");
        if (!listEl) return;

        // (1) 必ず先頭で clear。import 失敗 / その後の例外があっても
        // 古い queue 行が残らないようにする (Finding 3)。
        listEl.replaceChildren();

        if (jobs.length === 0) {
            if (emptyEl) emptyEl.style.display = "";
            if (countEl) countEl.textContent = "";
            return;
        }

        // (2) 非空時のみ module load + 描画。sink は replaceQueueRows 1 箇所に閉じる (Finding 2)。
        const queueMod = await loadQueuePanelModule();
        queueMod.replaceQueueRows(listEl, jobs);
        if (emptyEl) emptyEl.style.display = "none";
        if (countEl) countEl.textContent = `${jobs.length} 件`;
    } catch (e) {
        // ignore transient errors
    }
}
```

**(c) queue_panel.js の動的 import loader を `initQueuePanel` の手前あたりに 1 つ定義** (重複 import を避けるため module を cache、既存 `analysis_status.js` の dynamic import パターン (app.js:1810-1811) に揃える):

```js
let _queuePanelModule = null;
async function loadQueuePanelModule() {
    if (_queuePanelModule) return _queuePanelModule;
    // Finding 4: 既存パターン (app.js:1810) と同じく ASSET_VERSION を encodeURIComponent
    const version = encodeURIComponent(ASSET_VERSION || "1");
    _queuePanelModule = await import(`/static/queue_panel.js?v=${version}`);
    return _queuePanelModule;
}
```

`ASSET_VERSION` は app.js 冒頭 (line 2-4) で既に定義されているのでそのまま使える。

- [ ] **Step 2.4: 構文 / 動作確認のため npm test を実行**

Run:
```bash
npm test
```

Expected: 全テスト pass (`app.js` を直接テストする test はないが、`queue_panel.test.mjs` が壊れていないことと既存 `analysis_status.test.mjs` が pass することを確認)。

- [ ] **Step 2.5: dev server を起動して queue panel を手動 verify**

Run (別端末で):
```bash
scripts/infisical-run uv run stock-analyze serve
```

ブラウザで `http://localhost:8000/` を開き (queue API は **pending / running / failed のみ** 表示対象 — completed/cancelled は queue から消える仕様):

1. ダッシュボードの「分析キュー」パネルが表示されること (空 or 既存 job が見える)
2. queue にジョブを入れて pending → running の遷移が **従来と同じ見た目で** 表示されること (badge 色 `PENDING/badge--mono` → `RUNNING/badge--up`、レイアウト / 経過時間 / 「N 件」表示)
3. 完了 (completed/cancelled) すると **queue から消え**、件数が減り、空になれば empty 表示 (`#llm-queue-empty`) に切り替わること (Finding 5 検証ポイント)
4. failed ジョブの「×」(dismiss) と pending ジョブの「×」(cancel) ボタンが機能すること
5. DevTools の Network タブで `/static/queue_panel.js?v=...` が 1 回だけ load されること (cache 機構 = loadQueuePanelModule の一意性確認)

Expected: 見た目・挙動とも修正前と完全に同じ。差分があれば QUEUE_BADGE の label/cls か progress 表示フォーマットの移植漏れを疑う。

- [ ] **Step 2.6: コードレビュー観点で git diff --check を確認**

Run:
```bash
git diff --check
```

Expected: exit 0 (whitespace 問題なし)。

- [ ] **Step 2.7: commit**

```bash
git add src/stock_analyze_system/web/static/app.js
git commit -m "$(cat <<'EOF'
fix(web): wire app.js to queue_panel module and drop HTML string renderer (A1)

`app.js` の `renderQueueRow` / `formatQueueElapsed` / `QUEUE_BADGE` を削除し、
queue_panel.js から dynamic import (asset version は encodeURIComponent 経由)
で取得する。`fetchQueue` は (a) 先頭で `listEl.replaceChildren()` を呼び
import 失敗時にも古い行が残らない構造に変更、(b) 非空時のみ
`queueMod.replaceQueueRows(listEl, jobs)` を呼ぶ — HTML 文字列流し込み sink を
1 箇所に集約することで stored XSS 経路を完全に断つ。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: PR1 の merge gate を満たすことを確認

- [ ] **Step 3.1: 全 unit test を実行**

Run:
```bash
npm test
```

Expected: 全 test pass (queue_panel.test.mjs **7 件** + analysis_status.test.mjs 既存件数)。

- [ ] **Step 3.2: Security PR の必須 verify — app.js から旧 sink が消えたことを git grep で確認 (Finding 2)**

`grep -r` は no-match で exit 1 を返すため、shell の `|| test $? -eq 1` で「no match を成功」と扱う。`git grep` を使うことで directory 引数を `-- pathspec` として安全に渡せる。

Run:
```bash
# (a) queue panel まわりの HTML 流し込み sink が残っていないこと
git grep -nE -- 'innerHTML[[:space:]]*=[[:space:]]*.*(renderQueueRow|jobs\.map|join\(""\))' -- src/stock_analyze_system/web/static || test $? -eq 1
echo "(a) exit=$?"

# (b) app.js に queue 関連の重複定義や直接呼び出しが残っていないこと
#     (`queue_panel.js` への import 行は対象 path ではないので含まれない)
git grep -nE -- 'renderQueueRow|formatQueueElapsed[[:space:]]*\(|QUEUE_BADGE' -- src/stock_analyze_system/web/static/app.js || test $? -eq 1
echo "(b) exit=$?"
```

Expected:
- (a): no output / `(a) exit=0` (旧 sink が消えていること)
- (b): no output / `(b) exit=0` (重複定義が残っていないこと)

何かヒットしたら Task 2 で削除漏れなので戻る。

- [ ] **Step 3.3: git diff --check で whitespace 確認**

Run:
```bash
git diff --check $(git merge-base master HEAD)..HEAD
```

Expected: exit 0。

- [ ] **Step 3.4: PR を作成 (オプション、merge 準備のみ)**

PR タイトル: `fix(web): prevent stored XSS in analysis queue rows`

PR body の Test plan:
```markdown
## Summary
- queue panel の `renderQueueRow` を HTML template literal から DOM API 化
- `company_id` / `current_analysis_type` を `textContent` で escape、href は `encodeURIComponent`、data-job-id は `dataset` 経由
- queue 関連コードを `queue_panel.js` ES module に切り出し、jsdom で XSS regression test 化
- app.js の sink は `queueMod.replaceQueueRows(listEl, jobs)` 1 箇所に集約 (HTML 文字列流し込み経路を完全に排除)

## Test plan
- [x] `npm test` (queue_panel.test.mjs 7 件 / analysis_status.test.mjs 既存件数)
- [x] grep verify: app.js / web/static に旧 sink (`innerHTML = ...renderQueueRow...`) が残っていないこと
- [x] dev server で queue panel が従来と同じ見た目・挙動で表示されること (completed 後に queue から消えることを含む)
- [x] `git diff --check` clean

## ADR
Not required — Simple bug fix (XSS escape via DOM API)
```

PR 作成は user の指示があれば実施。それまでは local branch に commit 2 件積んだ状態で待機。

---

## Self-review checklist

- **Spec coverage** (spec §5):
  - ✅ §5.4 `queue_panel.js` 新規作成 (Task 1.3) + `replaceQueueRows` sink 集約 (Finding 2 拡張)
  - ✅ §5.4 `app.js` 側の DOM 化 (Task 2.3): `replaceChildren()` 先頭で sink を 1 箇所に閉じる構造
  - ✅ §5.5 test 4 件 (XSS company_id / XSS current_analysis_type / encodeURIComponent / dataset) + 追加 3 件 (formatQueueElapsed / QUEUE_BADGE mapping / replaceQueueRows multi-row + stale clear) = 合計 **7 件** (Task 1.5)
  - ✅ §5.6 手動 verification (Task 2.5): queue API の表示対象が pending/running/failed のみであることに合わせて文言修正済み
  - ✅ §5.7 module 化方式は **(b) 動的 import + `encodeURIComponent(ASSET_VERSION || "1")`** に確定 (app.js:1810-1811 と同パターン)
  - ✅ §5.6 merge gate に **grep verification** (Task 3.2) を追加: security PR として旧 sink 残存を自動検出
- **Placeholder scan**: 各 step に具体的なコマンド / コード / 期待出力あり、TBD なし
- **Type consistency**: `renderQueueRow(job, doc)` / `formatQueueElapsed(iso, now)` / `replaceQueueRows(listEl, jobs, doc)` / `QUEUE_BADGE` の signature が Task 1.3 と Task 1.5 / Task 2.3 で一貫
- **ADR compliance**: ADR 不要 (header に記載)
- **Out of scope (spec §5.8) の遵守**: `app.js` 全体の module 化はせず `queue_panel.js` だけ切り出し ✓
- **Review fixes applied (2026-05-17 review)**:
  - Finding 1 (QUEUE_BADGE 値): 現行 3 key (`PENDING/badge--mono` 等) に修正、`QUEUE_BADGE mapping` test 追加
  - Finding 2 (sink 除去 verify): `replaceQueueRows` を export して app.js sink を 1 箇所に集約 + Step 3.2 で grep gate
  - Finding 3 (空時 clear): `listEl.replaceChildren()` を fetchQueue 先頭、import は非空時のみ
  - Finding 4 (encodeURIComponent): 既存 app.js:1810 と同じ pattern に修正
  - Finding 5 (手動 verify): completed が queue から消える挙動 / 件数更新を verify 対象に
  - Finding 6 (Co-Authored-By): user 確認待ち (現状 plan の commit message は変更せず、push back 中)
