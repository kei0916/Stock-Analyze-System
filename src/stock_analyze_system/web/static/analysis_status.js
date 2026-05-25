const ACTIVE_STATUSES = new Set(["pending", "running"]);
const DEFAULT_BADGE_LABEL = "分析キューの状態";
const WORKER_DOWN_LABEL = "分析ワーカーが応答していません";

export function buildBadgeViewModel(content, warning) {
    if (!content && !warning) {
        return {
            hidden: true,
            state: null,
            text: "",
            ariaLabel: DEFAULT_BADGE_LABEL,
        };
    }

    const text = warning ? WORKER_DOWN_LABEL : content.text;
    return {
        hidden: false,
        state: warning ? "warning" : (content.state || "normal"),
        text,
        ariaLabel: text,
    };
}

export function buildBadgeText(jobs, nowMs) {
    const running = jobs.filter((job) => job.status === "running");
    const pending = jobs.filter((job) => job.status === "pending");
    if (running.length + pending.length === 0) {
        return null;
    }

    if (running.length === 0) {
        return { text: `待機中 ${pending.length}件`, state: "normal" };
    }

    if (running.length === 1) {
        const elapsed = formatElapsed(running[0].started_at, nowMs);
        return { text: `分析中 1件 · ${elapsed}`, state: "normal" };
    }

    const oldestStartedAt = running
        .map((job) => job.started_at)
        .filter(Boolean)
        .sort()[0];
    return {
        text: `分析中 ${running.length}件 · 最長 ${formatElapsed(oldestStartedAt, nowMs)}`,
        state: "normal",
    };
}

export function buildTitlePrefix(jobs) {
    const active = jobs.filter((job) => ACTIVE_STATUSES.has(job.status));
    return active.length > 0 ? `(${active.length}) ` : "";
}

export function detectCompletions(prevActiveIds, currentJobs) {
    const currentRunning = new Set(
        currentJobs
            .filter((job) => job.status === "running")
            .map((job) => job.job_id),
    );
    const currentActiveIds = new Set(
        currentJobs
            .filter((job) => ACTIVE_STATUSES.has(job.status))
            .map((job) => job.job_id),
    );
    const completions = [];
    for (const job of currentJobs) {
        if (
            prevActiveIds.has(job.job_id)
            && !currentActiveIds.has(job.job_id)
            && ["completed", "failed"].includes(job.status)
        ) {
            completions.push(job);
        }
    }
    return { completions, currentRunning, currentActiveIds };
}

export function shouldWarnWorkerDown(jobs, nowMs, thresholdMs = 30000) {
    const pending = jobs.filter((job) => job.status === "pending");
    const running = jobs.filter((job) => job.status === "running");
    if (running.length > 0 || pending.length === 0) {
        return false;
    }

    const oldestCreatedAtMs = pending
        .map((job) => Date.parse(job.created_at))
        .filter((value) => Number.isFinite(value))
        .sort((a, b) => a - b)[0];
    if (oldestCreatedAtMs === undefined) {
        return false;
    }
    return nowMs - oldestCreatedAtMs > thresholdMs;
}

export function formatElapsed(timestamp, nowMs) {
    if (!timestamp) {
        return "—";
    }
    const startedAtMs = Date.parse(timestamp);
    const elapsedMs = nowMs - startedAtMs;
    if (!Number.isFinite(elapsedMs) || elapsedMs < 0) {
        return "—";
    }

    const seconds = Math.floor(elapsedMs / 1000);
    if (seconds < 60) {
        return `${seconds}秒`;
    }

    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = seconds % 60;
    if (minutes < 60) {
        return `${minutes}分${remainingSeconds}秒`;
    }

    const hours = Math.floor(minutes / 60);
    return `${hours}時間${minutes % 60}分`;
}

export function buildNotificationTitle(job) {
    const companyId = job.company_id || "対象銘柄";
    return job.status === "completed"
        ? `${companyId} の決算分析が完了しました`
        : `${companyId} の決算分析が失敗しました`;
}
