import { api, formatBytes, basename, esc } from "./helpers.js";
import { loadHistory } from "./history.js";

let queuePaused = false;
let activeJobs = {};
let pendingJobs = [];
let blockedJobs = [];
let failedJobs = [];

let eventSource = null;

function updatePauseButton() {
    const btn = document.getElementById("btn-pause");
    btn.textContent = queuePaused ? "Resume Queue" : "Pause Queue";
}

function getAllIssueJobs() {
    const issues = [];
    blockedJobs.forEach(j => issues.push({ ...j, issue: j.block_reason || "Unknown issue", type: "blocked" }));
    failedJobs.forEach(j => issues.push({ ...j, issue: j.error_message || "Unknown error", type: "failed" }));
    return issues;
}

function renderQueue() {
    const table = document.getElementById("queue-table");
    const tbody = document.getElementById("queue-body");
    const emptyMsg = document.getElementById("queue-empty");
    const controls = document.getElementById("queue-controls");
    const active = Object.values(activeJobs);
    const hasJobs = active.length || pendingJobs.length;
    table.style.display = hasJobs ? "" : "none";
    emptyMsg.style.display = hasJobs ? "none" : "";
    controls.style.display = (hasJobs || queuePaused) ? "" : "none";
    document.getElementById("pending-count").textContent =
        pendingJobs.length ? `${pendingJobs.length} pending` : "";

    let html = "";
    active.concat(pendingJobs).forEach(j => {
        html += `<tr>
            <td title="${esc(j.file_path)}">${esc(basename(j.file_path))}</td>
            <td>${esc(j.library_name || "")}</td>
            <td>${formatBytes(j.old_size_bytes)}</td>
            <td class="status-${j.status}">${esc(j.status)}</td>
        </tr>`;
    });
    tbody.innerHTML = html;
}

function renderIssues() {
    const table = document.getElementById("issues-table");
    const tbody = document.getElementById("issues-body");
    const emptyMsg = document.getElementById("issues-empty");
    const issues = getAllIssueJobs();
    const hasIssues = issues.length > 0;
    table.style.display = hasIssues ? "" : "none";
    emptyMsg.style.display = hasIssues ? "none" : "";
    let html = "";
    issues.forEach(j => {
        const actions = j.type === "failed"
            ? `<button class="btn-icon" data-action="retry-job" data-job-id="${j.id}" data-tooltip="Retry"><img src="retry.svg" alt="Retry"></button>`
                + `<button class="btn-icon" data-action="dismiss-job" data-job-id="${j.id}" data-tooltip="Dismiss"><img src="close.svg" alt="Dismiss"></button>`
            : "";
        html += `<tr>
            <td title="${esc(j.file_path)}">${esc(basename(j.file_path))}</td>
            <td>${esc(j.library_name || "")}</td>
            <td>${formatBytes(j.old_size_bytes)}</td>
            <td class="status-${j.type}">${j.type}</td>
            <td>${esc(j.issue)}</td>
            <td class="issue-actions">${actions}</td>
        </tr>`;
    });
    tbody.innerHTML = html;
}

export function connectSSE() {
    if (eventSource) eventSource.close();
    const es = eventSource = new EventSource("/api/queue/events");

    es.addEventListener("init", (e) => {
        const data = JSON.parse(e.data);
        activeJobs = {};
        data.active.forEach(j => activeJobs[j.id] = j);
        pendingJobs = data.pending;
        blockedJobs = data.blocked || [];
        queuePaused = !!data.paused;
        updatePauseButton();
        renderQueue();
        renderIssues();
    });

    es.addEventListener("queue_paused", (e) => {
        const data = JSON.parse(e.data);
        queuePaused = !!data.paused;
        updatePauseButton();
        renderQueue();
    });

    es.addEventListener("job_queued", (e) => {
        const job = JSON.parse(e.data);
        pendingJobs.push(job);
        renderQueue();
    });

    es.addEventListener("job_blocked", (e) => {
        const job = JSON.parse(e.data);
        blockedJobs.push(job);
        renderIssues();
    });

    es.addEventListener("job_unblocked", (e) => {
        const job = JSON.parse(e.data);
        blockedJobs = blockedJobs.filter(j => j.id !== job.id);
        pendingJobs.push(job);
        renderQueue();
        renderIssues();
    });

    es.addEventListener("job_started", (e) => {
        const job = JSON.parse(e.data);
        pendingJobs = pendingJobs.filter(j => j.id !== job.id);
        activeJobs[job.id] = job;
        renderQueue();
    });

    es.addEventListener("job_finished", (e) => {
        const job = JSON.parse(e.data);
        delete activeJobs[job.id];
        pendingJobs = pendingJobs.filter(j => j.id !== job.id);
        blockedJobs = blockedJobs.filter(j => j.id !== job.id);
        failedJobs = failedJobs.filter(f => f.id !== job.id);
        if (job.status === "failed") {
            failedJobs.unshift(job);
        }
        renderQueue();
        renderIssues();
    });

    es.onerror = () => {
        es.close();
        setTimeout(connectSSE, 3000);
    };
}

export function initQueue() {
    document.getElementById("btn-pause").addEventListener("click", async () => {
        try {
            const result = await api("POST", "/api/queue/pause", { paused: !queuePaused });
            queuePaused = result.paused;
            updatePauseButton();
        } catch (e) {
            alert(e.message);
        }
    });

    document.querySelectorAll("#queue-tabs .queue-tab").forEach(tab => {
        tab.addEventListener("click", () => {
            document.querySelectorAll("#queue-tabs .queue-tab").forEach(t => t.classList.toggle("active", t === tab));
            document.querySelectorAll("#view-queue .queue-pane").forEach(p => p.classList.toggle("active", p.id === "qtab-" + tab.dataset.qtab));
            if (tab.dataset.qtab === "history") loadHistory();
        });
    });

    document.getElementById("issues-body").addEventListener("click", async (e) => {
        const btn = e.target.closest("[data-action]");
        if (!btn) return;
        const jobId = btn.dataset.jobId;
        if (btn.dataset.action === "retry-job") {
            try {
                await api("POST", "/api/queue/retry", { ids: [jobId] });
                failedJobs = failedJobs.filter(j => j.id !== jobId);
                renderIssues();
            } catch (err) { alert(err.message); }
        } else if (btn.dataset.action === "dismiss-job") {
            try {
                await api("POST", "/api/history/dismiss", { ids: [jobId] });
                failedJobs = failedJobs.filter(j => j.id !== jobId);
                renderIssues();
            } catch (err) { alert(err.message); }
        }
    });
}
