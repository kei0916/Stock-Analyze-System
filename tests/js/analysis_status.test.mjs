import test from "node:test";
import assert from "node:assert/strict";
import {
    buildBadgeText,
    buildBadgeViewModel,
    buildNotificationTitle,
    buildTitlePrefix,
    detectCompletions,
    formatElapsed,
    shouldWarnWorkerDown,
} from "../../src/stock_analyze_system/web/static/analysis_status.js";

const NOW = Date.parse("2026-05-13T12:00:00.000Z");

test("buildBadgeText returns null when there are no active jobs", () => {
    assert.equal(buildBadgeText([], NOW), null);
    assert.equal(buildBadgeText([{ job_id: 1, status: "completed" }], NOW), null);
});

test("buildBadgeText renders pending-only count", () => {
    const result = buildBadgeText([
        { job_id: 1, status: "pending", created_at: "2026-05-13T11:59:55.000Z" },
        { job_id: 2, status: "completed", created_at: "2026-05-13T11:59:54.000Z" },
    ], NOW);

    assert.deepEqual(result, { text: "待機中 1件", state: "normal" });
});

test("buildBadgeText renders one running job with elapsed time", () => {
    const result = buildBadgeText([
        { job_id: 1, status: "running", started_at: "2026-05-13T11:59:55.000Z" },
    ], NOW);

    assert.deepEqual(result, { text: "分析中 1件 · 5秒", state: "normal" });
});

test("buildBadgeText renders multiple running jobs with oldest elapsed time", () => {
    const result = buildBadgeText([
        { job_id: 1, status: "running", started_at: "2026-05-13T11:59:00.000Z" },
        { job_id: 2, status: "running", started_at: "2026-05-13T11:59:55.000Z" },
        { job_id: 3, status: "pending", created_at: "2026-05-13T11:59:58.000Z" },
    ], NOW);

    assert.deepEqual(result, { text: "分析中 2件 · 最長 1分0秒", state: "normal" });
});

test("buildTitlePrefix returns active job count prefix", () => {
    assert.equal(buildTitlePrefix([]), "");
    assert.equal(buildTitlePrefix([{ status: "completed" }]), "");
    assert.equal(
        buildTitlePrefix([{ status: "running" }, { status: "pending" }, { status: "failed" }]),
        "(2) ",
    );
});

test("detectCompletions fires only for prior running jobs that finished", () => {
    const prev = new Set([1, 2, 3]);
    const current = [
        { job_id: 1, status: "completed" },
        { job_id: 2, status: "failed" },
        { job_id: 3, status: "running" },
        { job_id: 4, status: "completed" },
    ];

    const { completions, currentRunning } = detectCompletions(prev, current);

    assert.deepEqual(completions.map((job) => job.job_id), [1, 2]);
    assert.deepEqual([...currentRunning], [3]);
});

test("detectCompletions also fires for prior pending jobs that finished between polls", () => {
    const prev = new Set([1]);
    const current = [{ job_id: 1, status: "completed" }];

    const { completions, currentActiveIds } = detectCompletions(prev, current);

    assert.deepEqual(completions.map((job) => job.job_id), [1]);
    assert.deepEqual([...currentActiveIds], []);
});

test("shouldWarnWorkerDown detects stale pending jobs only when no job is running", () => {
    assert.equal(
        shouldWarnWorkerDown(
            [{ status: "pending", created_at: "2026-05-13T11:59:20.000Z" }],
            NOW,
        ),
        true,
    );
    assert.equal(
        shouldWarnWorkerDown(
            [
                { status: "pending", created_at: "2026-05-13T11:59:20.000Z" },
                { status: "running", started_at: "2026-05-13T11:59:30.000Z" },
            ],
            NOW,
        ),
        false,
    );
    assert.equal(
        shouldWarnWorkerDown(
            [{ status: "pending", created_at: "2026-05-13T11:59:45.000Z" }],
            NOW,
        ),
        false,
    );
});

test("shouldWarnWorkerDown ignores missing or invalid pending timestamps", () => {
    assert.equal(shouldWarnWorkerDown([{ status: "pending" }], NOW), false);
    assert.equal(shouldWarnWorkerDown([{ status: "pending", created_at: "bad" }], NOW), false);
});

test("formatElapsed handles seconds, minutes, hours, missing, invalid, and future values", () => {
    assert.equal(formatElapsed("2026-05-13T11:59:55.000Z", NOW), "5秒");
    assert.equal(formatElapsed("2026-05-13T11:58:05.000Z", NOW), "1分55秒");
    assert.equal(formatElapsed("2026-05-13T09:50:00.000Z", NOW), "2時間10分");
    assert.equal(formatElapsed(null, NOW), "—");
    assert.equal(formatElapsed("bad", NOW), "—");
    assert.equal(formatElapsed("2026-05-13T12:00:05.000Z", NOW), "—");
});

test("buildNotificationTitle distinguishes completed and failed jobs", () => {
    assert.equal(
        buildNotificationTitle({ company_id: "US_AAPL", status: "completed" }),
        "US_AAPL の決算分析が完了しました",
    );
    assert.equal(
        buildNotificationTitle({ company_id: "US_AAPL", status: "failed" }),
        "US_AAPL の決算分析が失敗しました",
    );
});

test("buildBadgeViewModel hides the badge and resets its accessible label", () => {
    assert.deepEqual(buildBadgeViewModel(null, false), {
        hidden: true,
        state: null,
        text: "",
        ariaLabel: "分析キューの状態",
    });
});

test("buildBadgeViewModel renders normal and warning badge states", () => {
    assert.deepEqual(
        buildBadgeViewModel({ text: "分析中 1件 · 5秒", state: "normal" }, false),
        {
            hidden: false,
            state: "normal",
            text: "分析中 1件 · 5秒",
            ariaLabel: "分析中 1件 · 5秒",
        },
    );
    assert.deepEqual(
        buildBadgeViewModel({ text: "待機中 1件", state: "normal" }, true),
        {
            hidden: false,
            state: "warning",
            text: "分析ワーカーが応答していません",
            ariaLabel: "分析ワーカーが応答していません",
        },
    );
});
