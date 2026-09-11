import { api, esc, escAttr, wrapNumberInputs, clearValidation, setError } from "./helpers.js";
import { loadDeviceData } from "./devices.js";
import { openDirBrowser } from "./dir-browser.js";
import { renderQueue, renderIssues, clearFailedJobs } from "./queue.js";
import { loadHistory } from "./history.js";
import { loadSchedule, initSchedule } from "./schedule.js";
import { initNotifications, loadNotifications } from "./notifications.js";
import { initLogs, loadLogs, stopLogRefresh } from "./logs.js";

let settingsOriginal = {};
let settingsSaveBtn = null;

function checkSettingsChanged() {
    const cacheDir = document.getElementById("set-cache-dir").value;
    const priority = document.getElementById("set-process-priority").value;
    const ratio = document.getElementById("set-max-size-ratio").value;
    const queueOrder = document.getElementById("set-queue-order").value;
    const allowDupDel = document.getElementById("set-allow-dup-deletion").checked;
    settingsSaveBtn.disabled =
        cacheDir === settingsOriginal.cache_dir &&
        priority === settingsOriginal.process_priority &&
        ratio === settingsOriginal.max_size_ratio &&
        queueOrder === settingsOriginal.queue_order &&
        allowDupDel === settingsOriginal.allow_duplicate_deletion;
}

export async function loadSettings() {
    const s = await api("GET", "/api/settings");
    document.getElementById("set-cache-dir").value = s.cache_dir;
    document.getElementById("set-process-priority").value = s.process_priority;
    const ratioPercent = String(Math.round(s.max_size_ratio * 100));
    document.getElementById("set-max-size-ratio").value = ratioPercent;
    document.getElementById("set-queue-order").value = s.queue_order;
    document.getElementById("set-allow-dup-deletion").checked = !!s.allow_duplicate_deletion;
    settingsOriginal = { cache_dir: s.cache_dir, process_priority: s.process_priority, max_size_ratio: ratioPercent, queue_order: s.queue_order, allow_duplicate_deletion: !!s.allow_duplicate_deletion };
    settingsSaveBtn.disabled = true;
    loadSchedule(s);
    if (document.getElementById("stab-logs").classList.contains("active")) loadLogs(true);
}

async function loadDevices() {
    const container = document.getElementById("devices-grid");
    try {
        const devices = await api("GET", "/api/devices");
        if (!devices || devices.length === 0) {
            container.innerHTML = '<p class="section-empty">No devices detected.</p>';
            return;
        }
        let html = "";
        for (const dev of devices) {
            const encoderChips = dev.encoders.map(e =>
                `<span class="device-encoder">${esc(e)}</span>`
            ).join("");
            const typeTip = dev.type === "cpu"
                ? "Software encoding using the CPU.<br>Slower but widely compatible. No special hardware required."
                : `Hardware-accelerated encoding using <em>${dev.name}</em>.<br>Faster than CPU, but may have session limits and fewer quality options.`;
            html += `<div class="device-card">
                <div class="device-header">
                    <span class="device-name">${esc(dev.name)}</span>
                    <span class="device-type" data-tooltip="${typeTip}">${esc(dev.type)}</span>
                </div>
                <div class="device-encoders">${encoderChips || '<span class="section-empty">No verified encoders</span>'}</div>
                <div class="device-config">
                    <label data-tooltip="How many files this device can transcode at the same time.<br>Set to 0 to disable this device. Jobs that need it will be blocked until re-enabled.">Max concurrent jobs</label>
                    <input type="number" class="device-max-jobs" data-device="${escAttr(dev.id)}"
                           min="0" max="16" value="${dev.max_jobs}">
                </div>
                <div class="device-actions">
                    <button class="btn btn-primary device-save" data-device="${escAttr(dev.id)}">Save</button>
                </div>
            </div>`;
        }
        container.innerHTML = html;
        wrapNumberInputs(container);

        container.querySelectorAll(".device-card").forEach(card => {
            const input = card.querySelector(".device-max-jobs");
            const btn = card.querySelector(".device-save");
            let original = input.value;
            btn.disabled = true;
            input.addEventListener("input", () => { btn.disabled = input.value === original; });
            btn.addEventListener("click", async () => {
                const deviceId = btn.dataset.device;
                const val = parseInt(input.value);
                if (isNaN(val) || val < 0) { alert("Max jobs must be 0 or greater"); return; }
                try {
                    await api("PATCH", `/api/devices/${deviceId}`, { max_jobs: val });
                    original = input.value;
                    btn.disabled = true;
                    await loadDeviceData();
                    renderQueue();
                    renderIssues();
                } catch (e) {
                    alert(e.message);
                }
            });
        });
    } catch {
        container.innerHTML = '<p class="section-empty">Failed to load devices.</p>';
    }
}

export function switchSettingsTab(tabId) {
    if (!document.getElementById("stab-" + tabId)) tabId = "general";
    document.querySelectorAll("#view-settings .settings-tab").forEach(t => t.classList.toggle("active", t.dataset.stab === tabId));
    document.querySelectorAll("#view-settings .settings-pane").forEach(p => p.classList.toggle("active", p.id === "stab-" + tabId));
    if (tabId === "devices") loadDevices();
    if (tabId === "notifications") loadNotifications();
    if (tabId === "logs") loadLogs(true);
    if (tabId !== "logs") stopLogRefresh();
    history.replaceState(null, "", "#settings/" + tabId);
}

export function initSettings() {
    settingsSaveBtn = document.getElementById("btn-save-settings");
    settingsSaveBtn.disabled = true;

    document.querySelectorAll("#view-settings .settings-tab").forEach(tab => {
        tab.addEventListener("click", () => switchSettingsTab(tab.dataset.stab));
    });

    document.getElementById("set-cache-dir").addEventListener("input", checkSettingsChanged);

    document.getElementById("btn-browse-cache").addEventListener("click", () => {
        const cacheEl = document.getElementById("set-cache-dir");
        const startPath = cacheEl.value.trim() || null;
        openDirBrowser(startPath, (path) => { cacheEl.value = path; checkSettingsChanged(); });
    });

    document.getElementById("set-process-priority").addEventListener("change", checkSettingsChanged);

    document.getElementById("set-queue-order").addEventListener("change", checkSettingsChanged);

    const ratioInput = document.getElementById("set-max-size-ratio");
    ratioInput.addEventListener("input", () => { clearValidation(ratioInput.parentElement); checkSettingsChanged(); });

    document.getElementById("btn-save-settings").addEventListener("click", async () => {
        const form = document.getElementById("view-settings");
        clearValidation(form);
        const cacheEl = document.getElementById("set-cache-dir");
        const cacheDir = cacheEl.value.trim() || "/tmp/undarr";
        const priority = document.getElementById("set-process-priority").value;
        const ratioEl = document.getElementById("set-max-size-ratio");
        const ratio = parseInt(ratioEl.value);
        if (isNaN(ratio) || ratio < 1 || ratio > 100) { setError(ratioEl, "Max size ratio must be between 1 and 100%"); return; }
        const queueOrder = document.getElementById("set-queue-order").value;
        const allowDupDel = document.getElementById("set-allow-dup-deletion").checked;
        if (allowDupDel && !settingsOriginal.allow_duplicate_deletion) {
            if (!confirm('You enabled "Allow duplicate deletion." While deleting from Undarr is possible, your media service may not detect the change automatically.\n\nFor reliable library updates, remove duplicates through your media service instead.\n\nEnable deletion anyway?')) return;
        }
        try {
            await api("PATCH", "/api/settings", { cache_dir: cacheDir, process_priority: priority, max_size_ratio: ratio / 100, queue_order: queueOrder, allow_duplicate_deletion: allowDupDel });
            loadSettings();
        } catch (e) {
            setError(cacheEl, e.message);
        }
    });

    document.getElementById("set-allow-dup-deletion").addEventListener("change", checkSettingsChanged);

    initSchedule();
    initNotifications();
    initLogs();

    document.getElementById("btn-purge-history").addEventListener("click", async () => {
        if (!confirm("This will permanently delete all job history and processed file records. This cannot be undone.\n\nAll files will be treated as unprocessed, meaning the next scan will re-evaluate every file in every library.\n\nHistory takes up negligible disk space. There is no performance reason to purge it, and you lose the ability to review past jobs and errors.\n\nOnly do this if you have a specific reason to.\n\nContinue?")) return;
        try {
            await api("DELETE", "/api/history?clear_processed=true");
            loadHistory();
            clearFailedJobs();
        } catch (e) {
            alert(e.message);
        }
    });
}
