import { api, formatBytes, formatDuration, basename, esc, escAttr, renderCodecBar } from "./helpers.js";

let statsData = null;
let activeJobs = {};
let pendingCount = 0;
let knownLibraries = new Set();
let chartInstance = null;
let chartRange = "week";
let etaTarget = null;
let etaInterval = null;

function isVisible() {
    return document.getElementById("view-overview").classList.contains("active");
}

function formatEta(seconds) {
    if (seconds < 60) return "< 1m";
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    if (h > 0) return `~${h}h ${m}m`;
    return `~${m}m`;
}

function updateEtaDisplay() {
    const el = document.getElementById("overview-eta-sub");
    if (!el) return;
    if (!etaTarget) {
        el.textContent = "";
        return;
    }
    const remaining = Math.max(0, (etaTarget - Date.now()) / 1000);
    if (remaining <= 0) {
        el.textContent = "";
        etaTarget = null;
        return;
    }
    el.textContent = formatEta(remaining);
}

function startEtaCountdown() {
    if (etaInterval) clearInterval(etaInterval);
    if (!etaTarget) return;
    etaInterval = setInterval(updateEtaDisplay, 1000);
}

export function stopEtaCountdown() {
    if (etaInterval) {
        clearInterval(etaInterval);
        etaInterval = null;
    }
}

function renderStatCards() {
    const el = document.getElementById("overview-stats");
    const t = statsData ? statsData.totals : { completed: 0, failed: 0, skipped: 0, space_saved_bytes: 0 };
    const queueCount = pendingCount + Object.keys(activeJobs).length;

    if (t.eta_seconds != null && queueCount > 0) {
        etaTarget = Date.now() + t.eta_seconds * 1000;
    } else {
        etaTarget = null;
    }

    el.innerHTML = `
        <div class="stat-card" data-tooltip="Total size reduction across all completed transcodes. Original size minus new size.">
            <div class="stat-value">${formatBytes(t.space_saved_bytes)}</div>
            <div class="stat-label">Space Saved</div>
        </div>
        <div class="stat-card" data-tooltip="Files that completed transcoding successfully.">
            <div class="stat-value">${t.completed}</div>
            <div class="stat-label">Files Processed</div>
        </div>
        <div class="stat-card" data-tooltip="Active and pending jobs waiting to be processed.${etaTarget ? " ETA is based on average job duration per device, accounting for concurrent jobs and active progress." : ""}">
            <div class="stat-value">${queueCount}</div>
            <div class="stat-label">In Queue</div>
            <div class="stat-sub" id="overview-eta-sub">${etaTarget ? formatEta(t.eta_seconds) : ""}</div>
        </div>
        <div class="stat-card" data-tooltip="Jobs that failed due to FFmpeg errors, verification failures, or other issues.">
            <div class="stat-value">${t.failed}</div>
            <div class="stat-label">Errors</div>
        </div>`;

    startEtaCountdown();
}

function fillDays(daily, days) {
    const lookup = {};
    for (const d of daily) lookup[d.date] = d;
    const result = [];
    const now = new Date();
    for (let i = days - 1; i >= 0; i--) {
        const dt = new Date(now);
        dt.setDate(dt.getDate() - i);
        const key = dt.toISOString().slice(0, 10);
        result.push(lookup[key] || { date: key, completed: 0, failed: 0, space_saved_bytes: 0 });
    }
    return result;
}

function bucketByMonth(daily) {
    const months = {};
    for (const d of daily) {
        const key = d.date.slice(0, 7);
        months[key] = (months[key] || 0) + (d.space_saved_bytes || 0);
    }
    const sorted = Object.keys(months).sort();
    const monthNames = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
    return {
        labels: sorted.map(k => { const [y, m] = k.split("-"); return monthNames[+m - 1] + " " + y.slice(2); }),
        data: sorted.map(k => months[k]),
    };
}

function chartData(daily) {
    if (chartRange === "year") {
        return bucketByMonth(fillDays(daily, 365));
    }
    const days = chartRange === "month" ? 30 : 7;
    const filled = fillDays(daily, days);
    return { labels: filled.map(d => d.date.slice(5)), data: filled.map(d => d.space_saved_bytes || 0) };
}

function renderChart() {
    const el = document.getElementById("overview-chart");
    const daily = statsData?.daily || [];
    if (daily.length < 2) {
        el.innerHTML = "";
        chartInstance?.destroy();
        chartInstance = null;
        return;
    }

    if (!el.querySelector("canvas")) {
        el.innerHTML = `<div class="chart-header"><h3>Space Saved</h3>
            <div class="chart-range-btns">
                <button data-range="week" class="btn btn-sm active">Week</button>
                <button data-range="month" class="btn btn-sm">Month</button>
                <button data-range="year" class="btn btn-sm">Year</button>
            </div></div>
            <div class="chart-wrap"><canvas id="overview-chart-canvas"></canvas></div>`;
        el.querySelector(".chart-range-btns").addEventListener("click", e => {
            const btn = e.target.closest("button[data-range]");
            if (!btn || btn.dataset.range === chartRange) return;
            chartRange = btn.dataset.range;
            el.querySelectorAll(".chart-range-btns button").forEach(b => b.classList.toggle("active", b === btn));
            renderChart();
        });
    }

    const { labels, data } = chartData(daily);
    const wrap = el.querySelector(".chart-wrap");
    const emptyText = labels.length < 2 ? "Not enough data for this range yet."
        : data.every(v => !v) ? "No space saved in this range." : "";
    if (emptyText) {
        chartInstance?.destroy();
        chartInstance = null;
        wrap.innerHTML = `<p class="section-empty">${emptyText}</p>`;
        return;
    }
    if (!wrap.querySelector("canvas")) {
        wrap.innerHTML = '<canvas id="overview-chart-canvas"></canvas>';
    }
    const canvas = document.getElementById("overview-chart-canvas");

    chartInstance?.destroy();
    chartInstance = new Chart(canvas, {
        type: "bar",
        data: {
            labels,
            datasets: [{
                data,
                backgroundColor: "#da7722",
                borderRadius: 0,
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    displayColors: false,
                    callbacks: {
                        label: ctx => formatBytes(ctx.parsed.y),
                    },
                },
            },
            scales: {
                x: {
                    grid: { display: false },
                    ticks: { color: "#e0e0e0", maxRotation: 0, autoSkip: true, maxTicksLimit: 12 },
                    border: { color: "#333" },
                },
                y: {
                    grid: { color: "#333" },
                    ticks: {
                        color: "#e0e0e0",
                        callback: v => formatBytes(v),
                    },
                    border: { color: "#333" },
                    beginAtZero: true,
                },
            },
        },
    });
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

    const librarySizes = statsData.library_sizes || {};

    let html = `<h3>Libraries</h3><table class="overview-table"><thead><tr>
        <th style="width:30%">Library</th><th style="width:10%">Size</th><th style="width:12%">Progress</th><th style="width:8%">Skipped</th><th style="width:14%">Space Saved</th><th style="width:26%">Codecs</th>
    </tr></thead><tbody>`;
    let i = 0;
    for (const lib of libs) {
        const info = libMap[lib] || { completed: 0, failed: 0, processed: 0, skipped: 0, space_saved_bytes: 0, original_bytes: 0 };
        const total = fileCounts[lib] || 0;
        const processed = processedCounts[lib] || 0;
        const codec = renderCodecBar(composition[lib]);
        const progressText = total > 0 ? `${processed} / ${total}` : "-";

        const currentSize = librarySizes[lib] || 0;
        const sizeText = formatBytes(currentSize);

        const codecTip = codec.tooltip ? ` data-tooltip="${escAttr(codec.tooltip)}"` : "";
        html += `<tr${i++ % 2 ? ' class="stripe"' : ""}>
            <td>${esc(lib)}</td>
            <td>${sizeText}</td>
            <td>${progressText}</td>
            <td>${info.skipped || 0}</td>
            <td>${formatBytes(info.space_saved_bytes)}</td>
            <td class="codec-cell"${codecTip}>${codec.html}</td>
        </tr>`;
    }
    html += "</tbody></table>";
    el.innerHTML = html;
}

function renderDeviceCards() {
    const el = document.getElementById("overview-devices");
    const devices = statsData?.by_device || [];
    if (!devices.length) {
        el.innerHTML = "";
        return;
    }
    let html = '<h3>Devices</h3><div class="overview-stats">';
    for (const d of devices) {
        html += `<div class="stat-card device-card">
            <div class="device-label">${esc(d.device)}</div>
            <div class="device-stats">
                <div data-tooltip="Completed transcodes on this device"><span class="stat-value">${d.completed}</span><span class="stat-label">Jobs</span></div>
                <div data-tooltip="Cumulative processing time across all completed jobs"><span class="stat-value">${formatDuration(d.processing_seconds)}</span><span class="stat-label">Total Time</span></div>
                <div data-tooltip="Average encoding time per completed transcode on this device. Skipped and failed jobs are excluded."><span class="stat-value">${formatDuration(d.avg_duration_seconds)}</span><span class="stat-label">Avg Per Job</span></div>
            </div>
        </div>`;
    }
    html += "</div>";
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
    renderChart();
    renderActiveStrip();
    renderLibraryTable();
    renderDeviceCards();
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
