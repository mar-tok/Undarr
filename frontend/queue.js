import { api, formatBytes, basename, esc, formatDuration } from "./helpers.js";
import { deviceData, loadDeviceData, isDeviceDisabled } from "./devices.js";
import { loadHistory, reloadHistory } from "./history.js";
import { clearSearch } from "./search.js";

let queuePaused = false;
let activeJobs = {};
let pendingJobs = [];
let blockedJobs = [];
let failedJobs = [];
let hasUnseenFailures = false;

let _eventSource = null;
let _reconnectTimer = null;
let _renderTimer = null;

const expandedQueueIds = new Set();
const expandedIssueIds = new Set();

function updatePauseButton() {
    const btn = document.getElementById("btn-pause");
    btn.textContent = queuePaused ? "Resume Queue" : "Pause Queue";
}

function getAllIssueJobs() {
    const issues = [];
    blockedJobs.forEach(j => issues.push({ ...j, issue: j.block_reason || "Unknown issue", type: "blocked" }));
    pendingJobs.forEach(j => {
        if (!isDeviceDisabled(j.device)) return;
        const dev = deviceData.find(d => d.id === j.device);
        issues.push({ ...j, issue: `Requires ${dev ? dev.name : j.device}, which is disabled. Enable it in Settings > Devices.`, type: "blocked" });
    });
    failedJobs.forEach(j => issues.push({ ...j, issue: j.error_message || "Unknown error", type: "failed" }));
    return issues;
}

function updateQueueTabs() {
    const issues = getAllIssueJobs();
    const n = issues.length;
    const issuesTab = document.querySelector('#queue-tabs [data-qtab="issues"]');
    issuesTab.innerHTML = n
        ? `Issues <span data-tooltip="${n} job${n === 1 ? "" : "s"} need${n === 1 ? "s" : ""} attention.<br>Check the <em>Issues</em> tab to resolve."><img class="warning-icon-sm" src="warning-triangle-fill.svg" alt="Issues"></span>`
        : "Issues";
    const queueTab = document.querySelector('#queue-tabs [data-qtab="queue"]');
    const deviceBlocked = pendingJobs.some(j => isDeviceDisabled(j.device));
    queueTab.innerHTML = deviceBlocked
        ? `Queue <span data-tooltip="Some queued jobs are blocked by disabled devices.<br>Check the <em>Issues</em> tab to resolve."><img class="warning-icon-sm" src="warning-triangle-fill.svg" alt="Issues"></span>`
        : "Queue";
    const historyTab = document.querySelector('#queue-tabs [data-qtab="history"]');
    historyTab.innerHTML = hasUnseenFailures
        ? `History <span data-tooltip="One or more jobs failed.<br>Check <em>History</em> for details."><img class="warning-icon-sm" src="warning-triangle-fill.svg" alt="Failed"></span>`
        : "History";
}

function debouncedRenderQueue() {
    if (_renderTimer) return;
    _renderTimer = setTimeout(() => { _renderTimer = null; renderQueue(); }, 50);
}

function formatMediaInfo(info) {
    if (!info) return null;
    const parts = [];
    if (info.video_codec) {
        let v = info.video_codec.toUpperCase();
        if (info.resolution_width && info.resolution_height) v += ` ${info.resolution_width}x${info.resolution_height}`;
        parts.push(v);
    }
    if (info.audio_codec) parts.push(info.audio_codec.toUpperCase());
    if (info.bitrate_kbps) parts.push(info.bitrate_kbps + " kbps");
    if (info.duration_seconds) parts.push(formatDuration(info.duration_seconds));
    return parts.join(", ");
}

export function renderQueue() {
    const table = document.getElementById("queue-table");
    const tbody = document.getElementById("queue-body");
    const emptyMsg = document.getElementById("queue-empty");
    const controls = document.getElementById("queue-controls");
    const active = Object.values(activeJobs);
    const runnablePending = pendingJobs.filter(j => !isDeviceDisabled(j.device));
    const hasJobs = active.length || runnablePending.length;
    table.style.display = hasJobs ? "" : "none";
    emptyMsg.style.display = hasJobs ? "none" : "";
    controls.style.display = (hasJobs || queuePaused) ? "" : "none";
    document.getElementById("pending-count").textContent =
        runnablePending.length ? `${runnablePending.length} pending` : "";

    let html = "";
    let rowIdx = 0;
    active.forEach(j => {
        html += `<tr class="clickable${rowIdx++ % 2 ? " stripe" : ""}" data-job-id="${j.id}">
            <td>${esc(basename(j.file_path))}</td>
            <td>${esc(j.library_name || "")}</td>
            <td>${formatBytes(j.old_size_bytes)}</td>
            <td class="status-${j.status}">${esc(j.status)}</td>
        </tr>`;
    });
    runnablePending.forEach(j => {
        html += `<tr class="clickable${rowIdx++ % 2 ? " stripe" : ""}" data-job-id="${j.id}">
            <td>${esc(basename(j.file_path))}</td>
            <td>${esc(j.library_name || "")}</td>
            <td>${formatBytes(j.old_size_bytes)}</td>
            <td class="status-${j.status}">${esc(j.status)}</td>
        </tr>`;
    });
    tbody.innerHTML = html;
    for (const id of expandedQueueIds) {
        const row = tbody.querySelector(`tr[data-job-id="${id}"]`);
        if (row) expandQueueRow(row);
        else expandedQueueIds.delete(id);
    }

    updateQueueTabs();
}

function findQueueJob(jobId) {
    if (activeJobs[jobId]) return activeJobs[jobId];
    return pendingJobs.find(j => j.id === jobId) || null;
}

function expandQueueRow(clickedRow) {
    const jobId = clickedRow.dataset.jobId;
    const job = findQueueJob(jobId);
    if (!job) return;
    let lines = [job.file_path];
    if (job.preset_name) lines.push(`Preset: ${job.preset_name}`);
    const media = formatMediaInfo(job.media_info);
    if (media) lines.push(`Source: ${media}`);
    const expandRow = document.createElement("tr");
    expandRow.className = "detail-row";
    const cols = clickedRow.children.length;
    expandRow.innerHTML = `<td colspan="${cols}"><div class="job-detail">${lines.map(esc).join("\n")}</div></td>`;
    clickedRow.after(expandRow);
}

function toggleQueueDetail(clickedRow) {
    const jobId = clickedRow.dataset.jobId;
    const nextRow = clickedRow.nextElementSibling;
    if (nextRow && nextRow.classList.contains("detail-row")) {
        nextRow.remove();
        expandedQueueIds.delete(jobId);
        return;
    }
    expandedQueueIds.add(jobId);
    expandQueueRow(clickedRow);
}

export function renderIssues() {
    const table = document.getElementById("issues-table");
    const tbody = document.getElementById("issues-body");
    const emptyMsg = document.getElementById("issues-empty");
    const issues = getAllIssueJobs();
    const hasIssues = issues.length > 0;
    table.style.display = hasIssues ? "" : "none";
    emptyMsg.style.display = hasIssues ? "none" : "";
    let html = "";
    let rowIdx = 0;
    issues.forEach(j => {
        let actions = "";
        if (j.type === "failed") {
            actions = `<button class="btn-icon" data-action="retry-job" data-job-id="${j.id}" data-tooltip="Retry"><img src="retry.svg" alt="Retry"></button>`
                + `<button class="btn-icon" data-action="dismiss-job" data-job-id="${j.id}" data-tooltip="Dismiss"><img src="close.svg" alt="Dismiss"></button>`;
        } else {
            actions = `<button class="btn-icon" data-action="dismiss-job" data-job-id="${j.id}" data-tooltip="Dismiss"><img src="close.svg" alt="Dismiss"></button>`;
        }
        html += `<tr class="clickable${rowIdx++ % 2 ? " stripe" : ""}" data-job-id="${j.id}" data-issue-type="${j.type}">
            <td>${esc(basename(j.file_path))}</td>
            <td>${esc(j.library_name || "")}</td>
            <td>${formatBytes(j.old_size_bytes)}</td>
            <td class="status-${j.type}">${j.type}</td>
            <td class="issue-actions">${actions}</td>
        </tr>`;
    });
    tbody.innerHTML = html;
    for (const id of expandedIssueIds) {
        const row = tbody.querySelector(`tr[data-job-id="${id}"]`);
        if (row) expandIssueRow(row);
        else expandedIssueIds.delete(id);
    }
    updateQueueTabs();
}

function expandIssueRow(clickedRow) {
    const jobId = clickedRow.dataset.jobId;
    const allIssues = getAllIssueJobs();
    const job = allIssues.find(j => j.id === jobId);
    if (!job) return;
    const cols = clickedRow.children.length;
    let lines = [job.file_path];
    if (job.issue) lines.push(job.issue);
    const expandRow = document.createElement("tr");
    expandRow.className = "detail-row";
    expandRow.innerHTML = `<td colspan="${cols}"><button class="btn btn-copy-log" style="margin-bottom:8px">Copy to Clipboard</button><div class="job-detail">${lines.map(esc).join("\n")}</div></td>`;
    clickedRow.after(expandRow);
    expandRow.querySelector(".btn-copy-log").addEventListener("click", (e) => {
        e.stopPropagation();
        const btn = e.currentTarget;
        const ta = document.createElement("textarea");
        ta.value = lines.join("\n");
        ta.style.position = "fixed";
        ta.style.opacity = "0";
        document.body.appendChild(ta);
        ta.select();
        document.execCommand("copy");
        ta.remove();
        let msg = btn.nextElementSibling;
        if (msg && msg.classList.contains("copy-confirm")) msg.remove();
        msg = document.createElement("span");
        msg.className = "copy-confirm";
        msg.textContent = "Copied!";
        btn.after(msg);
        setTimeout(() => msg.remove(), 4000);
    });
}

function toggleIssueDetail(clickedRow) {
    const jobId = clickedRow.dataset.jobId;
    const nextRow = clickedRow.nextElementSibling;
    if (nextRow && nextRow.classList.contains("detail-row")) {
        nextRow.remove();
        expandedIssueIds.delete(jobId);
        return;
    }
    expandedIssueIds.add(jobId);
    expandIssueRow(clickedRow);
}

export function connectSSE() {
    if (_reconnectTimer) { clearTimeout(_reconnectTimer); _reconnectTimer = null; }
    if (_eventSource) { _eventSource.close(); _eventSource = null; }
    const es = _eventSource = new EventSource("/api/queue/events");

    es.addEventListener("init", async (e) => {
        const data = JSON.parse(e.data);
        activeJobs = {};
        data.active.forEach(j => activeJobs[j.id] = j);
        pendingJobs = data.pending;
        blockedJobs = data.blocked || [];
        queuePaused = !!data.paused;
        await loadDeviceData();
        try {
            failedJobs = await api("GET", "/api/history?status=failed&limit=500&exclude_dismissed=true");
        } catch { failedJobs = []; }
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
        debouncedRenderQueue();
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
        debouncedRenderQueue();
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
        if (job.status === "failed") hasUnseenFailures = true;
        renderQueue();
        renderIssues();
        if (document.getElementById("qtab-history").classList.contains("active")) {
            hasUnseenFailures = false;
            loadHistory().catch(() => {});
        }
    });

    es.onerror = () => {
        es.close();
        _eventSource = null;
        _reconnectTimer = setTimeout(connectSSE, 3000);
    };
}

export function loadQueueTab() {
    const active = document.querySelector("#queue-tabs .queue-tab.active");
    if (active && active.dataset.qtab === "history") { reloadHistory(); }
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
            clearSearch();
            document.querySelectorAll("#queue-tabs .queue-tab").forEach(t => t.classList.toggle("active", t === tab));
            document.querySelectorAll("#view-queue .queue-pane").forEach(p => p.classList.toggle("active", p.id === "qtab-" + tab.dataset.qtab));
            if (tab.dataset.qtab === "history") {
                hasUnseenFailures = false;
                updateQueueTabs();
                reloadHistory();
            }
        });
    });

    document.getElementById("queue-body").addEventListener("click", async (e) => {
        const row = e.target.closest("tr.clickable");
        if (row) toggleQueueDetail(row);
    });

    document.getElementById("issues-body").addEventListener("click", async (e) => {
        const btn = e.target.closest("[data-action]");
        if (btn) {
            const jobId = btn.dataset.jobId;
            const row = btn.closest("tr.clickable");
            const type = row ? row.dataset.issueType : null;
            if (btn.dataset.action === "retry-job") {
                try {
                    await api("POST", "/api/queue/retry", { ids: [jobId] });
                    failedJobs = failedJobs.filter(j => j.id !== jobId);
                    expandedIssueIds.delete(jobId);
                    renderIssues();
                } catch (err) { alert(err.message); }
            } else if (btn.dataset.action === "dismiss-job") {
                try {
                    if (type === "failed") {
                        await api("POST", "/api/history/dismiss", { ids: [jobId] });
                        failedJobs = failedJobs.filter(j => j.id !== jobId);
                    } else {
                        await api("DELETE", `/api/queue/${jobId}`);
                    }
                    expandedIssueIds.delete(jobId);
                    renderIssues();
                } catch (err) { alert(err.message); }
            }
            return;
        }
        const row = e.target.closest("tr.clickable");
        if (row) toggleIssueDetail(row);
    });
}
