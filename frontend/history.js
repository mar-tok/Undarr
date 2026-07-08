import { api, formatBytes, basename, esc, formatDuration, formatDate } from "./helpers.js";

const HISTORY_PAGE_SIZES = [25, 50, 100, 200];
let historyPageSize = 50;
let historyPage = 0;
let historySortBy = "finished_at";
let historySortDir = "desc";
let historyStatusFilter = null;
let historyData = [];

const expandedHistoryIds = new Set();

function buildHistoryQuery() {
    const params = new URLSearchParams();
    params.set("limit", historyPageSize);
    params.set("offset", historyPage * historyPageSize);
    params.set("sort_by", historySortBy);
    params.set("sort_dir", historySortDir);
    if (historyStatusFilter) params.set("status", historyStatusFilter);
    return params.toString();
}

function updateSortHeaders() {
    document.querySelectorAll("#history-table th.sortable").forEach(th => {
        const col = th.dataset.sort;
        const existing = th.querySelector(".sort-arrow");
        if (existing) existing.remove();
        if (col === historySortBy) {
            const arrow = document.createElement("span");
            arrow.className = "sort-arrow";
            arrow.textContent = historySortDir === "asc" ? " ▲" : " ▼";
            th.appendChild(arrow);
        }
    });
}

function buildDetailMessage(r) {
    const lines = [];
    if (r.status === "completed") {
        lines.push("Completed successfully.");
        if (r.new_size_bytes != null && r.old_size_bytes > 0) {
            const saved = r.old_size_bytes - r.new_size_bytes;
            const pct = Math.round((saved / r.old_size_bytes) * 100);
            lines.push("Saved: " + formatBytes(saved) + " (" + pct + "% smaller than original)");
        }
        lines.push("Duration: " + formatDuration(r.duration_seconds));
    } else if (r.error_message) {
        lines.push(r.error_message);
    }
    lines.push("Path: " + r.file_path);
    if (r.preset_name) lines.push("Preset: " + r.preset_name);
    if (r.device_name) lines.push("Device: " + r.device_name);
    return lines.map(esc).join("<br>");
}

function expandHistoryRow(clickedRow) {
    const jobId = clickedRow.dataset.jobId;
    const row = historyData.find(r => r.id === jobId);
    const detail = row ? buildDetailMessage(row) : "";
    const detailHtml = detail ? `<div class="history-detail">${detail}</div>` : "";
    const expandRow = document.createElement("tr");
    expandRow.className = "log-row";
    expandRow.innerHTML = `<td colspan="6">${detailHtml}<button class="btn btn-copy-log" data-log-id="${jobId}" style="margin-bottom:8px">Copy to Clipboard</button><div class="log-expand" id="log-${jobId}">Loading...</div></td>`;
    clickedRow.after(expandRow);
    expandRow.querySelector(".btn-copy-log").addEventListener("click", (e) => {
        e.stopPropagation();
        const logEl = document.getElementById("log-" + jobId);
        if (!logEl) return;
        const btn = e.currentTarget;
        const ta = document.createElement("textarea");
        ta.value = logEl.textContent;
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
    fetchLog(jobId);
}

function toggleLog(clickedRow) {
    const jobId = clickedRow.dataset.jobId;
    const nextRow = clickedRow.nextElementSibling;
    if (nextRow && nextRow.classList.contains("log-row")) {
        nextRow.remove();
        expandedHistoryIds.delete(jobId);
        return;
    }
    expandedHistoryIds.add(jobId);
    expandHistoryRow(clickedRow);
}

async function fetchLog(jobId) {
    const el = document.getElementById("log-" + jobId);
    if (!el) return;
    try {
        const data = await api("GET", `/api/history/${jobId}/log`);
        el.textContent = data.log || "(empty)";
    } catch {
        el.textContent = "(failed to load log)";
    }
}

export async function loadHistory() {
    const rows = await api("GET", `/api/history?${buildHistoryQuery()}`);
    historyData = rows;
    updateSortHeaders();
    const table = document.getElementById("history-table");
    const emptyMsg = document.getElementById("history-empty");
    table.style.display = rows.length ? "" : "none";
    emptyMsg.style.display = rows.length ? "none" : "";
    const tbody = document.getElementById("history-body");
    tbody.innerHTML = rows.map((r, i) =>
        `<tr class="clickable${i % 2 ? " stripe" : ""}" data-job-id="${r.id}">
            <td title="${esc(r.file_path)}">${esc(basename(r.file_path))}</td>
            <td>${esc(r.library_name)}</td>
            <td>${formatBytes(r.old_size_bytes)}</td>
            <td>${formatBytes(r.new_size_bytes)}</td>
            <td>${formatDate(r.finished_at)}</td>
            <td class="status-${r.status.replace(/\s+/g, "-")}">${esc(r.status)}</td>
        </tr>`
    ).join("");
    for (const id of expandedHistoryIds) {
        const row = tbody.querySelector(`tr[data-job-id="${id}"]`);
        if (row) expandHistoryRow(row);
        else expandedHistoryIds.delete(id);
    }

    const pagEl = document.getElementById("history-pagination");
    const hasPrev = historyPage > 0;
    const hasNext = rows.length === historyPageSize;
    const sizeOptions = HISTORY_PAGE_SIZES.map(n =>
        `<option value="${n}"${n === historyPageSize ? " selected" : ""}>${n} / page</option>`
    ).join("");
    pagEl.innerHTML = `<button class="btn btn-sm" id="hist-prev"${hasPrev ? "" : " disabled"}>Prev</button>
        <span class="hist-page-label">Page ${historyPage + 1}</span>
        <button class="btn btn-sm" id="hist-next"${hasNext ? "" : " disabled"}>Next</button>
        <select id="hist-page-size">${sizeOptions}</select>`;
    if (hasPrev) document.getElementById("hist-prev").addEventListener("click", () => { historyPage--; loadHistory(); });
    if (hasNext) document.getElementById("hist-next").addEventListener("click", () => { historyPage++; loadHistory(); });
    document.getElementById("hist-page-size").addEventListener("change", (e) => {
        historyPageSize = parseInt(e.target.value);
        historyPage = 0;
        loadHistory();
    });
}

export function initHistory() {
    document.querySelectorAll("#history-table th.sortable").forEach(th => {
        th.addEventListener("click", () => {
            const col = th.dataset.sort;
            if (historySortBy === col) {
                historySortDir = historySortDir === "asc" ? "desc" : "asc";
            } else {
                historySortBy = col;
                historySortDir = col === "finished_at" ? "desc" : "asc";
            }
            historyPage = 0;
            loadHistory();
        });
    });

    document.getElementById("history-status-filter").addEventListener("change", (e) => {
        historyStatusFilter = e.target.value;
        historyPage = 0;
        loadHistory();
    });

    document.getElementById("history-body").addEventListener("click", (e) => {
        const row = e.target.closest("tr.clickable");
        if (row) toggleLog(row);
    });
}
