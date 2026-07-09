import { api, esc, escAttr } from "./helpers.js";

export function loadSettings() {
    api("GET", "/api/settings").then(s => {
        document.getElementById("set-cache-dir").value = s.cache_dir;
    });
    api("GET", "/api/devices").then(renderDevices);
}

function renderDevices(devices) {
    const grid = document.getElementById("device-grid");
    let html = "";
    for (const dev of devices) {
        const typeTip = dev.type === "cpu"
            ? "Software encoding using the CPU.<br>Slower but widely compatible. No special hardware required."
            : `Hardware-accelerated encoding using <em>${dev.name}</em>.<br>Faster than CPU, but may have session limits and fewer quality options.`;
        html += `<div class="device-card">
            <div class="device-card-header">
                <span class="device-card-name">${esc(dev.name)}</span>
                <span class="device-type" data-tooltip="${typeTip}">${esc(dev.type)}</span>
            </div>
            <div class="device-encoders">${dev.encoders.map(esc).join(", ")}</div>
            <div class="form-group">
                <label data-tooltip="How many files this device can transcode at the same time.<br>Set to 0 to disable this device. Jobs that need it will be blocked until re-enabled.">Max Concurrent Jobs (0 = disabled)</label>
                <input type="number" class="dc-max-jobs" data-id="${escAttr(dev.id)}" value="${dev.max_jobs}" min="0">
            </div>
            <button class="btn dc-save" data-id="${escAttr(dev.id)}">Save</button>
        </div>`;
    }
    grid.innerHTML = html;
}

export function initSettings() {
    document.getElementById("device-grid").addEventListener("click", (e) => {
        const btn = e.target.closest(".dc-save");
        if (!btn) return;
        const id = btn.dataset.id;
        const input = document.querySelector(`.dc-max-jobs[data-id="${CSS.escape(id)}"]`);
        api("PATCH", `/api/devices/${encodeURIComponent(id)}`, { max_jobs: parseInt(input.value) })
            .catch(err => alert(err.message));
    });

    document.getElementById("btn-save-settings").addEventListener("click", () => {
        const dir = document.getElementById("set-cache-dir").value.trim() || "/tmp/undarr";
        api("PATCH", "/api/settings", { cache_dir: dir })
            .catch(err => alert(err.message));
    });
}
