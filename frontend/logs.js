import { api, formatBytes } from "./helpers.js";

let autoScroll = false;
let refreshTimer = null;
let cachedLines = [];

export function initLogs() {
    const scrollEl = document.getElementById("log-auto-scroll");
    const refreshEl = document.getElementById("log-auto-refresh");
    const searchEl = document.getElementById("log-search");

    scrollEl.checked = localStorage.getItem("log-auto-scroll") === "true";
    autoScroll = scrollEl.checked;
    scrollEl.addEventListener("change", e => {
        autoScroll = e.target.checked;
        localStorage.setItem("log-auto-scroll", e.target.checked);
    });

    document.getElementById("log-level-filter").addEventListener("change", () => loadLogs(true));

    refreshEl.checked = localStorage.getItem("log-auto-refresh") !== "false";
    refreshEl.addEventListener("change", e => {
        localStorage.setItem("log-auto-refresh", e.target.checked);
        if (e.target.checked) startAutoRefresh();
        else stopAutoRefresh();
    });

    searchEl.addEventListener("input", () => renderLines());

    document.getElementById("btn-download-log").addEventListener("click", () => {
        window.open("/api/logs/download", "_blank");
    });
}

function startAutoRefresh() {
    stopAutoRefresh();
    refreshTimer = setInterval(loadLogs, 5000);
}

function stopAutoRefresh() {
    if (refreshTimer) {
        clearInterval(refreshTimer);
        refreshTimer = null;
    }
}

export function stopLogRefresh() {
    stopAutoRefresh();
}

function renderLines(toEnd = false) {
    const search = document.getElementById("log-search").value.toLowerCase();
    const output = document.getElementById("log-output");
    let cls = "";
    const filtered = [];
    for (const line of cachedLines) {
        const m = line.match(/^\d{4}-\d{2}-\d{2} \S+\s+(\w+)/);
        if (m) {
            if (m[1] === "ERROR") cls = "log-error";
            else if (m[1] === "WARNING") cls = "log-warning";
            else cls = "";
        }
        if (search && !line.toLowerCase().includes(search)) continue;
        const safe = line.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
        filtered.push(cls ? `<span class="${cls}">${safe}</span>` : safe);
    }
    output.innerHTML = filtered.join("\n");
    if (autoScroll || toEnd) output.scrollTop = output.scrollHeight;
}

export async function loadLogs(toEnd = false) {
    const level = document.getElementById("log-level-filter").value;
    const params = new URLSearchParams({ lines: "500" });
    if (level) params.set("level", level);

    if (document.getElementById("log-auto-refresh").checked && !refreshTimer) startAutoRefresh();

    try {
        const data = await api("GET", "/api/logs?" + params);
        cachedLines = data.lines;
        document.getElementById("log-file-size").textContent = formatBytes(data.size);
        renderLines(toEnd);
    } catch (e) {
        document.getElementById("log-output").textContent = "Failed to load logs: " + e.message;
    }
}
