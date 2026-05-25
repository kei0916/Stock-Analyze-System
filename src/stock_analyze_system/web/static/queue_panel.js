// Queue panel の DOM 生成と整形ヘルパ。`app.js` から動的 import される。
// 全ての文字列値は textContent / dataset / encodeURIComponent 経由でセットし、
// stored XSS を防ぐ。

// queue API は pending/running/failed のみ表示対象
// (`fetchAnalysisJobs(["pending","running","failed"])`)
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
// HTML string rendering 経路を app.js 側からも完全に追放する。
export function replaceQueueRows(listEl, jobs, doc = document) {
    listEl.replaceChildren();
    for (const job of jobs) {
        listEl.appendChild(renderQueueRow(job, doc));
    }
}
