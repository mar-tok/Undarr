import { api, formatBytes, basename, esc, escAttr, formatDuration, formatDate } from "./helpers.js";

const HISTORY_PAGE_SIZES = [25, 50, 100, 200];
let historyPageSize = 25;
let historyPage = 0;
let historySortBy = "finished_at";
let historySortDir = "desc";
let historyStatusFilter = null;
let historyData = [];
let historyCheckboxesVisible = false;

const expandedHistoryIds = new Set();
const historyLogCache = new Map();
let historyGeneration = 0;

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
            arrow.textContent = historySortDir === "asc" ? "\u25B2" : "\u25BC";
            th.appendChild(arrow);
        }
    });
    const statusTh = document.getElementById("history-status-th");
    statusTh.textContent = historyStatusFilter
        ? historyStatusFilter.charAt(0).toUpperCase() + historyStatusFilter.slice(1)
        : "Status";
}

function buildDetailMessage(r) {
    const lines = [];
    if (r.status === "completed") {
        lines.push(r.error_message ? "Completed with warning." : "Completed successfully.");
        if (r.error_message) lines.push(r.error_message);
        if (r.new_size_bytes != null && r.old_size_bytes > 0) {
            const saved = r.old_size_bytes - r.new_size_bytes;
            const pct = Math.round((saved / r.old_size_bytes) * 100);
            lines.push("Saved: " + formatBytes(saved) + " (" + pct + "% smaller than original)");
        }
        lines.push("Duration: " + formatDuration(r.duration_seconds));
    } else {
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
    const isRuleSkipped = row && row.status === "skipped (rule)";
    const cached = historyLogCache.get(jobId);
    const colspan = historyCheckboxesVisible ? 7 : 6;
    const expandRow = document.createElement("tr");
    expandRow.className = "log-row";
    if (isRuleSkipped) {
        expandRow.innerHTML = `<td colspan="${colspan}">${detailHtml}</td>`;
    } else {
        expandRow.innerHTML = `<td colspan="${colspan}">${detailHtml}<button class="btn btn-copy-log" data-log-id="${jobId}" style="margin-bottom:8px">Copy to Clipboard</button><div class="log-expand" id="log-${jobId}">${cached != null ? esc(cached) : "Loading..."}</div></td>`;
    }
    clickedRow.after(expandRow);
    const copyBtn = expandRow.querySelector(".btn-copy-log");
    if (copyBtn) {
        copyBtn.addEventListener("click", (e) => {
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
    }
    if (!isRuleSkipped && cached == null) fetchLog(jobId);
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
        const text = data.log || "(empty)";
        historyLogCache.set(jobId, text);
        el.textContent = text;
    } catch {
        el.textContent = "(failed to load log)";
    }
}

export async function loadHistory() {
    const gen = ++historyGeneration;
    const rows = await api("GET", `/api/history?${buildHistoryQuery()}`);
    if (gen !== historyGeneration) return;
    const currentIds = new Set(rows.map(r => r.id));
    for (const key of historyLogCache.keys()) {
        if (!currentIds.has(key)) historyLogCache.delete(key);
    }
    historyData = rows;
    historyCheckboxesVisible = rows.length > 0;
    updateSortHeaders();
    const checkboxCol = document.getElementById("history-checkbox-col");
    const selectAll = document.getElementById("history-select-all");
    const requeueBtn = document.getElementById("btn-requeue-selected");
    checkboxCol.style.display = historyCheckboxesVisible ? "" : "none";
    document.getElementById("history-table").classList.toggle("has-checkboxes", historyCheckboxesVisible);
    requeueBtn.style.display = historyCheckboxesVisible ? "" : "none";
    requeueBtn.disabled = true;
    if (selectAll) selectAll.checked = false;
    const tbody = document.getElementById("history-body");
    tbody.innerHTML = rows.map((r, i) =>
        `<tr class="clickable${i % 2 ? " stripe" : ""}" data-job-id="${r.id}">
            ${historyCheckboxesVisible ? `<td><input type="checkbox" class="history-check" data-job-id="${r.id}"></td>` : ""}
            <td data-tooltip="${escAttr(r.file_path)}">${esc(basename(r.file_path))}</td>
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
        `<option value="${n}"${n === historyPageSize ? " selected" : ""}>${n}</option>`
    ).join("");
    pagEl.innerHTML = `
        <span class="number-wrap">
            <button class="number-btn" type="button" id="hist-prev" ${hasPrev ? "" : "disabled"}><img src="arrow-left.svg" alt="Previous"></button>
            <input type="number" id="hist-page" class="page-input" value="${historyPage + 1}" min="1">
            <button class="number-btn" type="button" id="hist-next" ${hasNext ? "" : "disabled"}><img src="arrow-right.svg" alt="Next"></button>
        </span>
        <select id="hist-page-size">${sizeOptions}</select>
    `;
    if (hasPrev) document.getElementById("hist-prev").addEventListener("click", () => { historyPage--; loadHistory(); });
    if (hasNext) document.getElementById("hist-next").addEventListener("click", () => { historyPage++; loadHistory(); });
    const pageInput = document.getElementById("hist-page");
    function sizePageInput() {
        pageInput.style.width = (String(pageInput.value).length + 1) + "ch";
    }
    sizePageInput();
    pageInput.addEventListener("input", sizePageInput);
    pageInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter") {
            const val = parseInt(pageInput.value);
            if (!isNaN(val) && val >= 1) {
                historyPage = val - 1;
                loadHistory();
            }
        }
    });
    pageInput.addEventListener("blur", () => {
        const val = parseInt(pageInput.value);
        if (!isNaN(val) && val >= 1 && val - 1 !== historyPage) {
            historyPage = val - 1;
            loadHistory();
        } else {
            pageInput.value = historyPage + 1;
        }
    });
    document.getElementById("hist-page-size").addEventListener("change", (e) => {
        historyPageSize = parseInt(e.target.value);
        historyPage = 0;
        loadHistory();
    });
}

export function reloadHistory() {
    historyPage = 0;
    return loadHistory();
}

function updateHistoryActions() {
    const checks = document.querySelectorAll("#history-body .history-check");
    const anyChecked = Array.from(checks).some(c => c.checked);
    document.getElementById("btn-requeue-selected").disabled = !anyChecked;
}

export function initHistory() {
    document.querySelectorAll("#history-table th.sortable").forEach(th => {
        th.addEventListener("click", () => {
            const col = th.dataset.sort;
            if (historySortBy === col) {
                if (historySortDir === "asc") {
                    historySortDir = "desc";
                } else if (col === "finished_at") {
                    historySortDir = "asc";
                } else {
                    historySortBy = "finished_at";
                    historySortDir = "desc";
                }
            } else {
                historySortBy = col;
                historySortDir = col === "finished_at" ? "desc" : "asc";
            }
            historyPage = 0;
            loadHistory();
        });
    });

    document.getElementById("history-status-th").addEventListener("click", (e) => {
        e.stopPropagation();
        const existing = document.querySelector(".status-dropdown");
        if (existing) { existing.remove(); return; }
        const th = document.getElementById("history-status-th");
        const dd = document.createElement("div");
        dd.className = "status-dropdown";
        const options = [null, "completed", "failed", "cancelled", "skipped", "skipped (rule)"];
        const labels = ["All", "Completed", "Failed", "Cancelled", "Skipped", "Skipped (rule)"];
        options.forEach((val, i) => {
            const btn = document.createElement("button");
            btn.textContent = labels[i];
            if (historyStatusFilter === val) btn.classList.add("active");
            btn.addEventListener("click", (ev) => {
                ev.stopPropagation();
                historyStatusFilter = val;
                historyPage = 0;
                dd.remove();
                loadHistory();
            });
            dd.appendChild(btn);
        });
        th.appendChild(dd);
        const closeDropdown = (ev) => {
            if (!dd.contains(ev.target) && ev.target !== th) {
                dd.remove();
                document.removeEventListener("click", closeDropdown);
            }
        };
        setTimeout(() => document.addEventListener("click", closeDropdown), 0);
    });

    document.getElementById("history-body").addEventListener("click", (e) => {
        const checkCell = e.target.closest("td");
        const checkInput = e.target.type === "checkbox" ? e.target
            : checkCell?.querySelector("input.history-check");
        if (checkInput) {
            if (e.target.type !== "checkbox") checkInput.checked = !checkInput.checked;
            updateHistoryActions();
            const checks = document.querySelectorAll("#history-body .history-check");
            const allChecked = checks.length > 0 && Array.from(checks).every(c => c.checked);
            document.getElementById("history-select-all").checked = allChecked;
            return;
        }
        const row = e.target.closest("tr.clickable");
        if (row) toggleLog(row);
    });

    document.getElementById("history-select-all").addEventListener("change", (e) => {
        const checked = e.target.checked;
        document.querySelectorAll("#history-body .history-check").forEach(c => { c.checked = checked; });
        updateHistoryActions();
    });

    document.getElementById("btn-requeue-selected").addEventListener("click", async () => {
        const checks = document.querySelectorAll("#history-body .history-check:checked");
        const ids = Array.from(checks).map(c => c.dataset.jobId);
        if (!ids.length) return;
        const btn = document.getElementById("btn-requeue-selected");
        btn.disabled = true;
        try {
            const result = await api("POST", "/api/queue/requeue", { ids });
            if (result.requeued > 0 && result.skipped > 0) {
                btn.textContent = `Queued ${result.requeued}, ${result.skipped} skipped`;
            } else if (result.requeued > 0) {
                btn.textContent = `Queued ${result.requeued}`;
            } else {
                btn.textContent = `${result.skipped} skipped (missing or already queued)`;
            }
            setTimeout(() => { btn.textContent = "Re-queue Selected"; }, 4000);
            document.getElementById("history-select-all").checked = false;
            document.querySelectorAll("#history-body .history-check").forEach(c => { c.checked = false; });
        } catch (err) {
            alert(err.message);
        }
        updateHistoryActions();
    });
}
