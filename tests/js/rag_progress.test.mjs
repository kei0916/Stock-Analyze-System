import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { JSDOM } from "jsdom";

const DEFAULT_FILINGS = [
    { id: 31, filing_type: "10-K", period_type: "annual", fiscal_year: 2024, content_available: true },
    { id: 32, filing_type: "10-Q", period_type: "quarterly", fiscal_year: 2024, content_available: true },
];

async function waitFor(predicate, timeoutMs = 1000) {
    const start = Date.now();
    while (Date.now() - start < timeoutMs) {
        if (predicate()) return;
        await new Promise((resolve) => setTimeout(resolve, 5));
    }
    throw new Error("condition was not met before timeout");
}

function jsonResponse(body, status = 200) {
    return {
        ok: status >= 200 && status < 300,
        status,
        json: async () => body,
    };
}

function deferred() {
    let resolve;
    const promise = new Promise((res) => {
        resolve = res;
    });
    return { promise, resolve };
}

function createRagPanelDom({ loadingOption = false } = {}) {
    const selectContent = loadingOption ? '<option value="">読み込み中...</option>' : '';
    return new JSDOM(`<!doctype html><html><body>
        <section data-rag-panel data-company-id="US_AAPL">
            <div data-rag-analyses></div>
            <select data-rag-filing-select>${selectContent}</select>
            <div data-rag-history></div>
            <textarea data-rag-question></textarea>
            <button data-rag-ask>Ask</button>
            <div data-rag-answer hidden>
                <p data-rag-answer-text></p>
                <p data-rag-source-pages></p>
                <p data-rag-source-sections></p>
            </div>
            <button data-rag-analyze>Analyze</button>
            <div data-rag-analyze-progress hidden>
                <div data-progress-bar></div>
                <span data-progress-label></span>
                <span data-progress-count></span>
                <pre data-progress-error hidden></pre>
            </div>
            <div data-rag-rerun hidden><button data-rag-rerun-btn>Retry</button></div>
        </section>
    </body></html>`, {
        runScripts: "dangerously",
        url: "http://localhost/stocks/US_AAPL",
    });
}

async function loadAppInto(dom) {
    const script = await readFile(
        new URL("../../src/stock_analyze_system/web/static/app.js", import.meta.url),
        "utf8",
    );
    dom.window.eval(script);
    dom.window.document.dispatchEvent(new dom.window.Event("DOMContentLoaded"));
}

async function renderProgressForTerminalJob(terminalJob) {
    const dom = createRagPanelDom();
    const { window } = dom;
    const { document } = window;
    const filing = {
        ...DEFAULT_FILINGS[0],
        period_end: "2024-09-30",
        filed_at: "2024-11-01",
    };
    const jobPolls = [
        {
            job_id: 99,
            status: "running",
            progress_current: 3,
            progress_total: 4,
            current_analysis_type: "competitors",
        },
        terminalJob,
    ];

    window.fetch = async (url, options = {}) => {
        const path = String(url);
        if (path.includes("/rag/filing_options")) {
            return jsonResponse({ default: filing, annual_options: [filing] });
        }
        if (path.includes("/rag/analyses")) return jsonResponse([]);
        if (path.includes("/rag/history")) return jsonResponse([]);
        if (path.includes("/api/analysis-jobs/99")) return jsonResponse(jobPolls.shift());
        if (path.includes("/api/analysis-jobs") && options.method === "POST") {
            return jsonResponse({ job_id: 99, status: "pending", filing_id: 31 }, 201);
        }
        if (path.includes("/api/analysis-jobs")) return jsonResponse([]);
        throw new Error(`unexpected fetch: ${path}`);
    };
    window.setInterval = (callback) => {
        Promise.resolve().then(callback).then(() => Promise.resolve().then(callback));
        return 1;
    };
    window.clearInterval = () => {};

    await loadAppInto(dom);
    await waitFor(() => document.querySelector("[data-rag-filing-select]").value === "31");
    document.querySelector("[data-rag-analyze]").click();
    return { document };
}

test("completed job with full backend progress renders as completed", async () => {
    const { document } = await renderProgressForTerminalJob({
        job_id: 99,
        status: "completed",
        progress_current: 4,
        progress_total: 4,
        current_analysis_type: null,
        error_details: null,
    });

    await waitFor(() => document.querySelector("[data-progress-label]").textContent === "完了");
    assert.equal(document.querySelector("[data-progress-count]").textContent, "4 / 4");
});

test("completed job with partial backend progress stays visible", async () => {
    const { document } = await renderProgressForTerminalJob({
        job_id: 99,
        status: "completed",
        progress_current: 3,
        progress_total: 4,
        current_analysis_type: null,
        error_details: null,
    });

    await waitFor(() => (
        document.querySelector("[data-progress-label]").textContent === "完了 (一部失敗)"
    ));
    assert.equal(document.querySelector("[data-progress-count]").textContent, "3 / 4");
});

test("completed job with zero backend progress trusts terminal status", async () => {
    const { document } = await renderProgressForTerminalJob({
        job_id: 99,
        status: "completed",
        progress_current: 0,
        progress_total: 0,
        current_analysis_type: null,
        error_details: null,
    });

    await waitFor(() => document.querySelector("[data-progress-label]").textContent === "完了");
    assert.equal(document.querySelector("[data-progress-count]").textContent, "0 / 0");
});

test("failed job without error details renders as failure", async () => {
    const { document } = await renderProgressForTerminalJob({
        job_id: 99,
        status: "failed",
        progress_current: 0,
        progress_total: 4,
        current_analysis_type: null,
        error_details: {},
    });

    await waitFor(() => document.querySelector("[data-progress-label]").textContent === "失敗");
    assert.match(
        document.querySelector("[data-progress-error]").textContent,
        /分析に失敗しました/,
    );
});

test("cancelled job uses terminal job progress", async () => {
    const { document } = await renderProgressForTerminalJob({
        job_id: 99,
        status: "cancelled",
        progress_current: 0,
        progress_total: 4,
        current_analysis_type: null,
        error_details: null,
    });

    await waitFor(() => document.querySelector("[data-progress-label]").textContent === "失敗");
    assert.equal(document.querySelector("[data-progress-count]").textContent, "0 / 4");
});

test("failed job with full backend progress renders as partial failure", async () => {
    const { document } = await renderProgressForTerminalJob({
        job_id: 99,
        status: "failed",
        progress_current: 4,
        progress_total: 4,
        current_analysis_type: null,
        error_details: {
            failed_types: [{ type: "mda", message: "request timeout" }],
        },
    });

    await waitFor(() => (
        document.querySelector("[data-progress-label]").textContent === "完了 (一部失敗)"
    ));
    assert.equal(document.querySelector("[data-progress-count]").textContent, "4 / 4");
    assert.match(
        document.querySelector("[data-progress-error]").textContent,
        /mda: request timeout/,
    );
    assert.equal(document.querySelector("[data-rag-rerun]").hidden, false);
});

test("running poll with zero total keeps the analysis total", async () => {
    const dom = createRagPanelDom({ loadingOption: true });
    const { window } = dom;
    const filing = DEFAULT_FILINGS[0];

    window.fetch = async (url) => {
        const path = String(url);
        if (path.includes("/rag/filing_options")) return jsonResponse({ default: filing, annual_options: [filing] });
        if (path.includes("/rag/analyses")) return jsonResponse([]);
        if (path.includes("/rag/history")) return jsonResponse([]);
        if (path.includes("/api/analysis-jobs/77")) {
            return jsonResponse({
                job_id: 77,
                status: "running",
                filing_id: 31,
                progress_current: 0,
                progress_total: 0,
                current_analysis_type: "mda",
            });
        }
        if (path.includes("/api/analysis-jobs")) {
            assert.match(path, /filing_id=31/);
            return jsonResponse([{ job_id: 77, status: "running", filing_id: 31 }]);
        }
        throw new Error(`unexpected fetch: ${path}`);
    };
    window.setInterval = (callback) => {
        Promise.resolve().then(callback);
        return 1;
    };
    window.clearInterval = () => {};

    await loadAppInto(dom);

    await waitFor(() => window.document.querySelector("[data-progress-count]").textContent === "0 / 4");
    assert.equal(window.document.querySelector("[data-progress-bar]").style.width, "0%");
});

test("initial filing option load connects to active job and renders persisted progress", async () => {
    const dom = createRagPanelDom({ loadingOption: true });
    const { window } = dom;
    const filing = DEFAULT_FILINGS[0];

    window.fetch = async (url) => {
        const path = String(url);
        if (path.includes("/rag/filing_options")) return jsonResponse({ default: filing, annual_options: [filing] });
        if (path.includes("/rag/analyses")) return jsonResponse([]);
        if (path.includes("/rag/history")) return jsonResponse([]);
        if (path.includes("/api/analysis-jobs/77")) {
            return jsonResponse({
                job_id: 77,
                status: "running",
                filing_id: 31,
                progress_current: 2,
                progress_total: 4,
                current_analysis_type: null,
            });
        }
        if (path.includes("/api/analysis-jobs")) {
            assert.match(path, /filing_id=31/);
            return jsonResponse([{ job_id: 77, status: "running", filing_id: 31 }]);
        }
        throw new Error(`unexpected fetch: ${path}`);
    };
    window.setInterval = (callback) => {
        Promise.resolve().then(callback);
        return 1;
    };
    window.clearInterval = () => {};

    await loadAppInto(dom);

    await waitFor(() => window.document.querySelector("[data-progress-count]").textContent === "2 / 4");
    assert.equal(window.document.querySelector("[data-progress-bar]").style.width, "50%");
});

test("stale completed poll does not reload analyses for previously selected filing", async () => {
    const dom = createRagPanelDom();
    const { window } = dom;
    const intervalCallbacks = [];
    const analysisLoads = [];

    window.fetch = async (url, options = {}) => {
        const path = String(url);
        if (path.includes("/rag/filing_options")) return jsonResponse({ default: DEFAULT_FILINGS[0], annual_options: DEFAULT_FILINGS });
        if (path.includes("/rag/analyses")) {
            analysisLoads.push(path);
            return jsonResponse([]);
        }
        if (path.includes("/rag/history")) return jsonResponse([]);
        if (path.includes("/api/analysis-jobs/99")) {
            return jsonResponse({
                job_id: 99,
                status: "completed",
                filing_id: 31,
                progress_current: 4,
                progress_total: 4,
                current_analysis_type: null,
            });
        }
        if (path.includes("/api/analysis-jobs") && options.method === "POST") {
            return jsonResponse({ job_id: 99, status: "pending", filing_id: 31 }, 201);
        }
        if (path.includes("/api/analysis-jobs")) return jsonResponse([]);
        throw new Error(`unexpected fetch: ${path}`);
    };
    window.setInterval = (callback) => {
        intervalCallbacks.push(callback);
        return intervalCallbacks.length;
    };
    window.clearInterval = () => {};

    await loadAppInto(dom);
    await waitFor(() => window.document.querySelector("[data-rag-filing-select]").value === "31");
    await waitFor(() => analysisLoads.length > 0);
    analysisLoads.length = 0;

    window.document.querySelector("[data-rag-analyze]").click();
    await waitFor(() => intervalCallbacks.length === 1);

    const select = window.document.querySelector("[data-rag-filing-select]");
    select.value = "32";
    select.dispatchEvent(new window.Event("change"));
    await waitFor(() => analysisLoads.some((path) => path.includes("filing_id=32")));
    analysisLoads.length = 0;

    await intervalCallbacks[0]();

    assert.equal(
        analysisLoads.some((path) => path.includes("filing_id=31")),
        false,
    );
});

test("stale in-flight analyses response does not render after filing changes", async () => {
    const dom = createRagPanelDom();
    const { window } = dom;
    const intervalCallbacks = [];
    let filing31AnalysesCalls = 0;
    const delayedFiling31 = deferred();

    window.fetch = async (url, options = {}) => {
        const path = String(url);
        if (path.includes("/rag/filing_options")) return jsonResponse({ default: DEFAULT_FILINGS[0], annual_options: DEFAULT_FILINGS });
        if (path.includes("/rag/analyses") && path.includes("filing_id=31")) {
            filing31AnalysesCalls += 1;
            if (filing31AnalysesCalls === 1) return jsonResponse([]);
            return delayedFiling31.promise;
        }
        if (path.includes("/rag/analyses") && path.includes("filing_id=32")) {
            return jsonResponse([{
                analysis_type: "mda",
                result_json: { summary: "new filing analysis" },
                model_name: "model-new",
            }]);
        }
        if (path.includes("/rag/history")) return jsonResponse([]);
        if (path.includes("/api/analysis-jobs/99")) {
            return jsonResponse({
                job_id: 99,
                status: "completed",
                filing_id: 31,
                progress_current: 4,
                progress_total: 4,
                current_analysis_type: null,
            });
        }
        if (path.includes("/api/analysis-jobs") && options.method === "POST") {
            return jsonResponse({ job_id: 99, status: "pending", filing_id: 31 }, 201);
        }
        if (path.includes("/api/analysis-jobs")) return jsonResponse([]);
        throw new Error(`unexpected fetch: ${path}`);
    };
    window.setInterval = (callback) => {
        intervalCallbacks.push(callback);
        return intervalCallbacks.length;
    };
    window.clearInterval = () => {};

    await loadAppInto(dom);
    await waitFor(() => window.document.querySelector("[data-rag-filing-select]").value === "31");
    await waitFor(() => filing31AnalysesCalls === 1);

    window.document.querySelector("[data-rag-analyze]").click();
    await waitFor(() => intervalCallbacks.length === 1);

    const pollPromise = intervalCallbacks[0]();
    await waitFor(() => filing31AnalysesCalls === 2);

    const select = window.document.querySelector("[data-rag-filing-select]");
    select.value = "32";
    select.dispatchEvent(new window.Event("change"));
    const analysesBox = window.document.querySelector("[data-rag-analyses]");
    await waitFor(() => analysesBox.textContent.includes("経営者による分析"));

    delayedFiling31.resolve(jsonResponse([{
        analysis_type: "business_summary",
        result_json: { summary: "old filing analysis" },
        model_name: "model-old",
    }]));
    await pollPromise;

    assert.equal(select.value, "32");
    assert.match(analysesBox.textContent, /経営者による分析/);
    assert.doesNotMatch(analysesBox.textContent, /事業概要/);
});

test("stale active-job detection does not attach a previous filing poll", async () => {
    const dom = createRagPanelDom();
    const { window } = dom;
    const delayedFiling31Jobs = deferred();
    const intervalCallbacks = [];
    let filing31DetectStarted = false;

    window.fetch = async (url) => {
        const path = String(url);
        if (path.includes("/rag/filing_options")) {
            return jsonResponse({ default: DEFAULT_FILINGS[0], annual_options: DEFAULT_FILINGS });
        }
        if (path.includes("/rag/analyses")) return jsonResponse([]);
        if (path.includes("/rag/history")) return jsonResponse([]);
        if (path.includes("/api/analysis-jobs/88")) {
            return jsonResponse({
                job_id: 88,
                status: "running",
                filing_id: 32,
                progress_current: 2,
                progress_total: 4,
                current_analysis_type: "mda",
            });
        }
        if (path.includes("/api/analysis-jobs/77")) {
            return jsonResponse({
                job_id: 77,
                status: "running",
                filing_id: 31,
                progress_current: 1,
                progress_total: 4,
                current_analysis_type: "business_summary",
            });
        }
        if (path.includes("/api/analysis-jobs") && path.includes("filing_id=31")) {
            filing31DetectStarted = true;
            return delayedFiling31Jobs.promise;
        }
        if (path.includes("/api/analysis-jobs") && path.includes("filing_id=32")) {
            return jsonResponse([{ job_id: 88, status: "running", filing_id: 32 }]);
        }
        throw new Error(`unexpected fetch: ${path}`);
    };
    window.setInterval = (callback) => {
        intervalCallbacks.push(callback);
        return intervalCallbacks.length;
    };
    window.clearInterval = () => {};

    await loadAppInto(dom);
    await waitFor(() => window.document.querySelector("[data-rag-filing-select]").value === "31");
    await waitFor(() => filing31DetectStarted);

    const select = window.document.querySelector("[data-rag-filing-select]");
    select.value = "32";
    select.dispatchEvent(new window.Event("change"));
    await waitFor(() => intervalCallbacks.length === 1);

    delayedFiling31Jobs.resolve(jsonResponse([{ job_id: 77, status: "running", filing_id: 31 }]));
    await new Promise((resolve) => setTimeout(resolve, 20));

    assert.equal(intervalCallbacks.length, 1);
});

test("stale analysis creation response is ignored after filing changes", async () => {
    const dom = createRagPanelDom();
    const { window } = dom;
    const delayedPost = deferred();
    const intervalCallbacks = [];
    let postStarted = false;

    window.fetch = async (url, options = {}) => {
        const path = String(url);
        if (path.includes("/rag/filing_options")) {
            return jsonResponse({ default: DEFAULT_FILINGS[0], annual_options: DEFAULT_FILINGS });
        }
        if (path.includes("/rag/analyses")) return jsonResponse([]);
        if (path.includes("/rag/history")) return jsonResponse([]);
        if (path.includes("/api/analysis-jobs") && options.method === "POST") {
            postStarted = true;
            return delayedPost.promise;
        }
        if (path.includes("/api/analysis-jobs")) return jsonResponse([]);
        throw new Error(`unexpected fetch: ${path}`);
    };
    window.setInterval = (callback) => {
        intervalCallbacks.push(callback);
        return intervalCallbacks.length;
    };
    window.clearInterval = () => {};

    await loadAppInto(dom);
    await waitFor(() => window.document.querySelector("[data-rag-filing-select]").value === "31");

    window.document.querySelector("[data-rag-analyze]").click();
    await waitFor(() => postStarted);

    const select = window.document.querySelector("[data-rag-filing-select]");
    select.value = "32";
    select.dispatchEvent(new window.Event("change"));

    delayedPost.resolve(jsonResponse({ job_id: 99, status: "pending", filing_id: 31 }, 201));
    await new Promise((resolve) => setTimeout(resolve, 20));

    assert.equal(intervalCallbacks.length, 0);
    assert.equal(window.document.querySelector("[data-rag-analyze-progress]").hidden, true);
});

test("polling ignores overlapping interval ticks while a request is in flight", async () => {
    const dom = createRagPanelDom();
    const { window } = dom;
    const delayedPoll = deferred();
    const intervalCallbacks = [];
    let jobFetches = 0;

    window.fetch = async (url, options = {}) => {
        const path = String(url);
        if (path.includes("/rag/filing_options")) {
            return jsonResponse({ default: DEFAULT_FILINGS[0], annual_options: DEFAULT_FILINGS });
        }
        if (path.includes("/rag/analyses")) return jsonResponse([]);
        if (path.includes("/rag/history")) return jsonResponse([]);
        if (path.includes("/api/analysis-jobs/99")) {
            jobFetches += 1;
            if (jobFetches === 1) return delayedPoll.promise;
            return jsonResponse({
                job_id: 99,
                status: "running",
                filing_id: 31,
                progress_current: 3,
                progress_total: 4,
                current_analysis_type: "mda",
            });
        }
        if (path.includes("/api/analysis-jobs") && options.method === "POST") {
            return jsonResponse({ job_id: 99, status: "pending", filing_id: 31 }, 201);
        }
        if (path.includes("/api/analysis-jobs")) return jsonResponse([]);
        throw new Error(`unexpected fetch: ${path}`);
    };
    window.setInterval = (callback) => {
        intervalCallbacks.push(callback);
        return intervalCallbacks.length;
    };
    window.clearInterval = () => {};

    await loadAppInto(dom);
    await waitFor(() => window.document.querySelector("[data-rag-filing-select]").value === "31");
    window.document.querySelector("[data-rag-analyze]").click();
    await waitFor(() => intervalCallbacks.length === 1);

    const firstTick = intervalCallbacks[0]();
    const secondTick = intervalCallbacks[0]();
    await new Promise((resolve) => setTimeout(resolve, 0));

    assert.equal(jobFetches, 1);

    delayedPoll.resolve(jsonResponse({
        job_id: 99,
        status: "running",
        filing_id: 31,
        progress_current: 1,
        progress_total: 4,
        current_analysis_type: "business_summary",
    }));
    await firstTick;
    await secondTick;
});
