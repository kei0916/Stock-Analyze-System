import test from "node:test";
import assert from "node:assert/strict";
import { JSDOM } from "jsdom";
import {
    QUEUE_BADGE,
    renderQueueRow,
    formatQueueElapsed,
    replaceQueueRows,
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
