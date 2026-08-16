import { api, formatBytes, formatBytesLarge, basename, esc, escAttr, renderCodecBar } from "./helpers.js";

let statsData = null;
let activeJobs = {};
let pendingCount = 0;
let knownLibraries = new Set();

function isVisible() {
    return document.getElementById("view-overview").classList.contains("active");
}

function renderStatCards() {
    const el = document.getElementById("overview-stats");
    const t = statsData ? statsData.totals : { completed: 0, failed: 0, skipped: 0, space_saved_bytes: 0 };
    const queueCount = pendingCount + Object.keys(activeJobs).length;

    el.innerHTML = `
        <div class="stat-card" data-tooltip="Total size reduction across all completed transcodes. Original size minus new size.">
            <div class="stat-value">${formatBytesLarge(t.space_saved_bytes)}</div>
            <div class="stat-label">Space Saved</div>
        </div>
        <div class="stat-card" data-tooltip="Files that completed transcoding successfully.">
            <div class="stat-value">${t.completed}</div>
            <div class="stat-label">Files Processed</div>
        </div>
        <div class="stat-card" data-tooltip="Active and pending jobs waiting to be processed.">
            <div class="stat-value">${queueCount}</div>
            <div class="stat-label">In Queue</div>
        </div>
        <div class="stat-card" data-tooltip="Jobs that failed due to FFmpeg errors, verification failures, or other issues.">
            <div class="stat-value">${t.failed}</div>
            <div class="stat-label">Errors</div>
        </div>`;
}

function renderActiveStrip() {
    const el = document.getElementById("overview-active");
    const jobs = Object.values(activeJobs);
    if (!jobs.length) {
        el.style.display = "none";
        return;
    }
    el.style.display = "";
    let html = `<h3>Active Jobs</h3><table class="overview-table"><thead><tr>
        <th style="width:50%">File</th><th style="width:20%">Progress</th><th style="width:8%">FPS</th><th style="width:22%">Device</th>
    </tr></thead><tbody>`;
    jobs.forEach((j, i) => {
        const p = j.progress || {};
        const pctVal = p.percent != null ? Math.round(p.percent) : 0;
        const fps = p.fps ? Math.round(p.fps) : "-";
        const device = j.device_name || j.device || "-";
        html += `<tr${i % 2 ? ' class="stripe"' : ""}>
            <td data-tooltip="${escAttr(j.file_path)}">${esc(basename(j.file_path))}</td>
            <td><div class="progress-cell"><span>${pctVal}%</span><div class="progress-bar-wrap"><div class="progress-bar-fill" style="width:${pctVal}%"></div></div></div></td>
            <td>${fps}</td>
            <td>${esc(device)}</td>
        </tr>`;
    });
    html += "</tbody></table>";
    el.innerHTML = html;
}

function renderLibraryTable() {
    const el = document.getElementById("overview-libraries");
    if (!statsData) { el.innerHTML = ""; return; }
    const byLib = statsData.by_library || [];
    const fileCounts = statsData.file_counts || {};
    const processedCounts = statsData.processed_counts || {};
    const composition = statsData.composition || {};

    if (!byLib.length && !Object.keys(fileCounts).length) {
        el.innerHTML = '<p class="section-empty">Add a library to get started.</p>';
        return;
    }

    const allLibs = new Set([...byLib.map(l => l.library), ...Object.keys(fileCounts)]);
    const libs = new Set([...allLibs].filter(l => knownLibraries.has(l)));
    if (!libs.size) {
        el.innerHTML = '<p class="section-empty">Add a library to get started.</p>';
        return;
    }
    const libMap = {};
    byLib.forEach(l => { libMap[l.library] = l; });

    let html = `<h3>Libraries</h3><table class="overview-table"><thead><tr>
        <th style="width:40%">Library</th><th style="width:12%">Progress</th><th style="width:8%">Skipped</th><th style="width:14%">Space Saved</th><th style="width:26%">Codecs</th>
    </tr></thead><tbody>`;
    let i = 0;
    for (const lib of libs) {
        const info = libMap[lib] || { completed: 0, failed: 0, processed: 0, skipped: 0, space_saved_bytes: 0, original_bytes: 0 };
        const total = fileCounts[lib] || 0;
        const processed = processedCounts[lib] || 0;
        const codec = renderCodecBar(composition[lib]);
        const progressText = total > 0 ? `${processed} / ${total}` : "-";

        const codecTip = codec.tooltip ? ` data-tooltip="${escAttr(codec.tooltip)}"` : "";
        html += `<tr${i++ % 2 ? ' class="stripe"' : ""}>
            <td>${esc(lib)}</td>
            <td>${progressText}</td>
            <td>${info.skipped || 0}</td>
            <td>${formatBytes(info.space_saved_bytes)}</td>
            <td class="codec-cell"${codecTip}>${codec.html}</td>
        </tr>`;
    }
    html += "</tbody></table>";
    el.innerHTML = html;
}

function renderBiggestWins() {
    const el = document.getElementById("overview-wins");
    if (!statsData || !statsData.top_savings || !statsData.top_savings.length) {
        el.innerHTML = "";
        return;
    }
    const savings = statsData.top_savings.filter(t => knownLibraries.has(t.library_name));
    if (!savings.length) {
        el.innerHTML = "";
        return;
    }
    let html = `<h3>Top Reductions</h3><table class="overview-table"><thead><tr>
        <th style="width:45%">File</th><th style="width:30%">Size</th><th style="width:25%">Saved</th>
    </tr></thead><tbody>`;
    savings.forEach((t, i) => {
        const saved = t.old_size_bytes - t.new_size_bytes;
        const savedPct = Math.round(saved / t.old_size_bytes * 100);
        html += `<tr${i % 2 ? ' class="stripe"' : ""}>
            <td data-tooltip="${escAttr(t.file_path)}">${esc(basename(t.file_path))}</td>
            <td>${formatBytes(t.old_size_bytes)} → ${formatBytes(t.new_size_bytes)}</td>
            <td>${formatBytes(saved)} (${savedPct}%)</td>
        </tr>`;
    });
    html += "</tbody></table>";
    el.innerHTML = html;
}

function renderAll() {
    renderStatCards();
    renderActiveStrip();
    renderLibraryTable();
    renderBiggestWins();
}

export function initOverview() {}

export async function loadOverview() {
    try {
        const [stats, libs] = await Promise.all([
            api("GET", "/api/stats"),
            api("GET", "/api/libraries"),
        ]);
        statsData = stats;
        knownLibraries = new Set(libs.map(l => l.name));
    } catch {
        statsData = null;
    }
    renderAll();
}

export function onOverviewSSE(type, data) {
    if (type === "init") {
        activeJobs = {};
        (data.active || []).forEach(j => { activeJobs[j.id] = j; });
        pendingCount = (data.pending || []).length;
        if (isVisible()) {
            renderStatCards();
            renderActiveStrip();
        }
        return;
    }
    if (type === "job_queued") {
        pendingCount++;
        if (isVisible()) renderStatCards();
        return;
    }
    if (type === "queue_changed") {
        pendingCount = (data.pending || []).length;
        if (isVisible()) renderStatCards();
        return;
    }
    if (type === "job_started") {
        activeJobs[data.id] = data;
        pendingCount = Math.max(0, pendingCount - 1);
        if (isVisible()) {
            renderStatCards();
            renderActiveStrip();
        }
        return;
    }
    if (type === "job_progress") {
        if (activeJobs[data.id]) {
            activeJobs[data.id].progress = data;
            if (isVisible()) renderActiveStrip();
        }
        return;
    }
    if (type === "job_finished") {
        delete activeJobs[data.id];
        if (isVisible()) {
            loadOverview();
        }
        return;
    }
    if (type === "job_cancelled") {
        if (activeJobs[data.id]) {
            delete activeJobs[data.id];
        } else {
            pendingCount = Math.max(0, pendingCount - 1);
        }
        if (isVisible()) {
            renderStatCards();
            renderActiveStrip();
        }
        return;
    }
    if (type === "library_files_changed" || type === "scan_complete") {
        if (isVisible()) loadOverview();
    }
}
