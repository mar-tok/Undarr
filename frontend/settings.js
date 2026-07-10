import { api, esc, escAttr, wrapNumberInputs } from "./helpers.js";

let settingsOriginal = {};
let settingsSaveBtn = null;

function checkSettingsChanged() {
    const cacheDir = document.getElementById("set-cache-dir").value;
    settingsSaveBtn.disabled = cacheDir === settingsOriginal.cache_dir;
}

export function loadSettings() {
    api("GET", "/api/settings").then(s => {
        document.getElementById("set-cache-dir").value = s.cache_dir;
        settingsOriginal = { cache_dir: s.cache_dir };
        settingsSaveBtn.disabled = true;
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
            <button class="btn btn-primary dc-save" data-id="${escAttr(dev.id)}">Save</button>
        </div>`;
    }
    grid.innerHTML = html;
    wrapNumberInputs(grid);

    grid.querySelectorAll(".device-card").forEach(card => {
        const input = card.querySelector(".dc-max-jobs");
        const btn = card.querySelector(".dc-save");
        let original = input.value;
        btn.disabled = true;
        input.addEventListener("input", () => { btn.disabled = input.value === original; });
        btn.addEventListener("click", async () => {
            const deviceId = btn.dataset.id;
            const val = parseInt(input.value);
            if (isNaN(val) || val < 0) { alert("Max jobs must be 0 or greater"); return; }
            try {
                await api("PATCH", `/api/devices/${deviceId}`, { max_jobs: val });
                original = input.value;
                btn.disabled = true;
            } catch (e) {
                alert(e.message);
            }
        });
    });
}

export function initSettings() {
    settingsSaveBtn = document.getElementById("btn-save-settings");
    settingsSaveBtn.disabled = true;

    document.getElementById("set-cache-dir").addEventListener("input", checkSettingsChanged);

    document.getElementById("btn-save-settings").addEventListener("click", () => {
        const dir = document.getElementById("set-cache-dir").value.trim() || "/tmp/undarr";
        api("PATCH", "/api/settings", { cache_dir: dir })
            .then(loadSettings)
            .catch(err => alert(err.message));
    });
}
