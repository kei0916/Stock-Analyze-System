import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { JSDOM } from "jsdom";

async function loadAppInto(dom) {
    const script = await readFile(
        new URL("../../src/stock_analyze_system/web/static/app.js", import.meta.url),
        "utf8",
    );
    dom.window.eval(script);
    dom.window.document.dispatchEvent(new dom.window.Event("DOMContentLoaded"));
}

test("stock detail tabs honor #tab hash on initial load", async () => {
    const dom = new JSDOM(`<!doctype html><html><body>
        <div data-tabs data-default-tab="financial">
            <button data-tab-target="financial">Financial</button>
            <button data-tab-target="analysis">Analysis</button>
            <section data-tab-panel="financial">Financial panel</section>
            <section data-tab-panel="analysis" hidden>Analysis panel</section>
        </div>
    </body></html>`, {
        runScripts: "dangerously",
        url: "http://localhost/stocks/US_AAPL#tab=analysis",
    });

    await loadAppInto(dom);

    const financialPanel = dom.window.document.querySelector(
        "[data-tab-panel='financial']",
    );
    const analysisPanel = dom.window.document.querySelector(
        "[data-tab-panel='analysis']",
    );

    assert.equal(financialPanel.hidden, true);
    assert.equal(analysisPanel.hidden, false);
});
