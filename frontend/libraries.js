import { api, esc } from "./helpers.js";

let libraries = [];
let editingLibraryName = null;
let creatingNewLibrary = false;

const SKIP_FIELDS = ["video_codec", "audio_codec", "resolution_width", "resolution_height", "bitrate_kbps", "file_size_mb", "duration_seconds"];
const SKIP_OPS = ["equals", "not_equals", "less_than", "greater_than", "contains"];

export function loadLibraries() {
    return api("GET", "/api/libraries").then(data => {
        libraries = data;
        renderLibraries();
    });
}

function renderLibraries() {
    const grid = document.getElementById("library-grid");
    let html = "";
    if (creatingNewLibrary) {
        html += renderLibraryFormCard(null);
    }
    html += libraries.map(lib => {
        if (editingLibraryName === lib.name) return renderLibraryFormCard(lib);
        return renderLibraryViewCard(lib);
    }).join("");
    grid.innerHTML = html;

    const editCard = grid.querySelector(".library-card.editing");
    if (editCard) attachLibFormCardListeners(editCard, creatingNewLibrary ? null : editingLibraryName);
}

function renderLibraryViewCard(lib) {
    let propsHtml = "";
    propsHtml += `<dt>Preset</dt><dd>${esc(lib.preset)}</dd>`;
    propsHtml += `<dt>Watch</dt><dd>${lib.watch ? "Yes" : "No"}</dd>`;
    if (lib.scan_interval > 0) {
        propsHtml += `<dt>Scan</dt><dd>Every ${lib.scan_interval} ${esc(lib.scan_unit)}</dd>`;
    }
    propsHtml += `<dt>Paths</dt><dd>${esc(lib.paths.join(", "))}</dd>`;

    return `<div class="library-card" data-name="${esc(lib.name)}">
        <div class="library-card-header">
            <span class="library-card-name">${esc(lib.name)}</span>
            <div class="library-card-actions">
                <button class="btn" data-lib-action="scan" data-name="${esc(lib.name)}">Scan</button>
                <button class="btn" data-lib-action="edit" data-name="${esc(lib.name)}">Edit</button>
                <button class="btn btn-danger" data-lib-action="delete" data-name="${esc(lib.name)}">Delete</button>
            </div>
        </div>
        <dl class="library-card-props">${propsHtml}</dl>
    </div>`;
}

function renderLibraryFormCard(lib) {
    const name = lib ? lib.name : "";
    const paths = lib ? lib.paths.join("\n") : "";
    const preset = lib ? lib.preset : "";
    const watch = lib ? lib.watch : true;
    const scanInterval = lib ? (lib.scan_interval || 0) : 0;
    const scanUnit = lib ? (lib.scan_unit || "minutes") : "minutes";

    const skipRulesHtml = (lib ? (lib.skip_rules || []) : []).map((rule, ri) => {
        const condsHtml = (rule.conditions || []).map(c => `
            <div class="skip-cond-row">
                <select class="cond-field">${SKIP_FIELDS.map(f => `<option value="${f}"${f === c.field ? " selected" : ""}>${f}</option>`).join("")}</select>
                <select class="cond-op">${SKIP_OPS.map(o => `<option value="${o}"${o === c.operator ? " selected" : ""}>${o}</option>`).join("")}</select>
                <input class="cond-value" value="${esc(c.value != null ? String(c.value) : "")}" placeholder="value">
                <button class="btn btn-sm btn-remove-cond" type="button">Remove</button>
            </div>
        `).join("");
        return `<div class="skip-rule-group">
            <div class="skip-rule-header">
                <span class="skip-rule-label">Rule ${ri + 1}</span>
                <span class="skip-rule-actions">
                    <button class="btn btn-sm btn-remove-rule" type="button">Remove Rule</button>
                </span>
            </div>
            <div class="skip-rule-conds">${condsHtml}</div>
            <button class="btn skip-add-cond" type="button">Add Condition</button>
        </div>`;
    }).join("");

    const pathPatternsHtml = (lib ? (lib.path_patterns || []) : []).map(p => `
        <div class="path-pattern-row">
            <input class="pattern-value" value="${esc(p)}" placeholder="e.g. *trailer*">
            <button class="btn btn-sm btn-remove-pattern" type="button">Remove</button>
        </div>
    `).join("");

    return `<div class="library-card editing">
        <div class="form-group">
            <label>Name</label>
            <input type="text" class="lc-name" value="${esc(name)}">
        </div>
        <div class="form-group">
            <label>Preset</label>
            <input type="text" class="lc-preset" value="${esc(preset)}" placeholder="Preset name">
        </div>
        <div class="form-group">
            <label>Paths (one per line)</label>
            <textarea class="lc-paths" placeholder="/media/movies">${esc(paths)}</textarea>
        </div>
        <div class="form-group">
            <label><input type="checkbox" class="lc-watch"${watch ? " checked" : ""}> Watch for new files</label>
        </div>
        <div class="form-group">
            <label>Scan Interval</label>
            <div style="display:flex;gap:8px">
                <input type="number" class="lc-scan-interval" value="${scanInterval}" min="0" style="width:80px">
                <select class="lc-scan-unit">
                    <option value="minutes"${scanUnit === "minutes" ? " selected" : ""}>minutes</option>
                    <option value="hours"${scanUnit === "hours" ? " selected" : ""}>hours</option>
                    <option value="days"${scanUnit === "days" ? " selected" : ""}>days</option>
                </select>
            </div>
        </div>
        <div>
            <label class="section-label">Path Patterns</label>
            <div class="lc-path-patterns">${pathPatternsHtml}</div>
            <button class="btn lc-add-pattern" type="button" style="margin-top:6px">Add Pattern</button>
        </div>
        <div style="margin-top:12px">
            <label class="section-label">Skip Rules</label>
            <div class="lc-skip-rules">${skipRulesHtml}</div>
            <button class="btn lc-add-rule" type="button" style="margin-top:6px">Add Rule</button>
        </div>
        <div class="form-actions">
            <button class="btn lc-cancel">Cancel</button>
            <button class="btn btn-primary lc-save">Save</button>
        </div>
    </div>`;
}

function addCondRow(condsEl, fieldVal, opVal, valVal) {
    const row = document.createElement("div");
    row.className = "skip-cond-row";
    row.innerHTML = `
        <select class="cond-field">${SKIP_FIELDS.map(f => `<option value="${f}"${f === fieldVal ? " selected" : ""}>${f}</option>`).join("")}</select>
        <select class="cond-op">${SKIP_OPS.map(o => `<option value="${o}"${o === opVal ? " selected" : ""}>${o}</option>`).join("")}</select>
        <input class="cond-value" value="${esc(valVal != null ? String(valVal) : "")}" placeholder="value">
        <button class="btn btn-sm btn-remove-cond" type="button">Remove</button>
    `;
    row.querySelector(".btn-remove-cond").addEventListener("click", () => {
        const group = row.closest(".skip-rule-group");
        row.remove();
        if (!group.querySelector(".skip-cond-row")) {
            group.remove();
            renumberRuleGroups(group.parentElement);
        }
    });
    condsEl.appendChild(row);
}

function addRuleGroup(rulesEl) {
    const idx = rulesEl.querySelectorAll(".skip-rule-group").length + 1;
    const group = document.createElement("div");
    group.className = "skip-rule-group";
    group.innerHTML = `
        <div class="skip-rule-header">
            <span class="skip-rule-label">Rule ${idx}</span>
            <span class="skip-rule-actions">
                <button class="btn btn-sm btn-remove-rule" type="button">Remove Rule</button>
            </span>
        </div>
        <div class="skip-rule-conds"></div>
        <button class="btn skip-add-cond" type="button">Add Condition</button>
    `;
    group.querySelector(".btn-remove-rule").addEventListener("click", () => {
        group.remove();
        renumberRuleGroups(rulesEl);
    });
    const condsEl = group.querySelector(".skip-rule-conds");
    group.querySelector(".skip-add-cond").addEventListener("click", () => {
        addCondRow(condsEl, "video_codec", "equals", "");
    });
    addCondRow(condsEl, "video_codec", "equals", "");
    rulesEl.appendChild(group);
}

function renumberRuleGroups(container) {
    if (!container) return;
    container.querySelectorAll(".skip-rule-group").forEach((g, i) => {
        const label = g.querySelector(".skip-rule-label");
        if (label) label.textContent = `Rule ${i + 1}`;
    });
}

function collectSkipRules(container) {
    return Array.from(container.querySelectorAll(".skip-rule-group")).map(group => ({
        conditions: Array.from(group.querySelectorAll(".skip-cond-row")).map(row => ({
            field: row.querySelector(".cond-field").value,
            operator: row.querySelector(".cond-op").value,
            value: row.querySelector(".cond-value").value,
        }))
    })).filter(rule => rule.conditions.length > 0);
}

function addPathPatternRow(container, value) {
    const row = document.createElement("div");
    row.className = "path-pattern-row";
    row.innerHTML = `
        <input class="pattern-value" value="${esc(value || "")}" placeholder="e.g. *trailer*">
        <button class="btn btn-sm btn-remove-pattern" type="button">Remove</button>
    `;
    row.querySelector(".btn-remove-pattern").addEventListener("click", () => { row.remove(); });
    container.appendChild(row);
}

function collectPathPatterns(container) {
    return Array.from(container.querySelectorAll(".path-pattern-row"))
        .map(row => row.querySelector(".pattern-value").value.trim())
        .filter(v => v);
}

function attachLibFormCardListeners(card, originalName) {
    const isNew = originalName === null;

    const rulesEl = card.querySelector(".lc-skip-rules");
    card.querySelectorAll(".skip-rule-group").forEach(group => {
        group.querySelector(".btn-remove-rule").addEventListener("click", () => {
            group.remove();
            renumberRuleGroups(rulesEl);
        });
        const condsEl = group.querySelector(".skip-rule-conds");
        group.querySelector(".skip-add-cond").addEventListener("click", () => {
            addCondRow(condsEl, "video_codec", "equals", "");
        });
        group.querySelectorAll(".btn-remove-cond").forEach(btn => {
            btn.addEventListener("click", () => {
                const row = btn.closest(".skip-cond-row");
                const grp = row.closest(".skip-rule-group");
                row.remove();
                if (!grp.querySelector(".skip-cond-row")) {
                    grp.remove();
                    renumberRuleGroups(rulesEl);
                }
            });
        });
    });

    card.querySelector(".lc-add-rule").addEventListener("click", () => {
        addRuleGroup(rulesEl);
    });

    card.querySelectorAll(".btn-remove-pattern").forEach(btn => {
        btn.addEventListener("click", () => { btn.closest(".path-pattern-row").remove(); });
    });

    card.querySelector(".lc-add-pattern").addEventListener("click", () => {
        addPathPatternRow(card.querySelector(".lc-path-patterns"), "");
    });

    card.querySelector(".lc-save").addEventListener("click", async () => {
        const name = card.querySelector(".lc-name").value.trim();
        const preset = card.querySelector(".lc-preset").value.trim();
        const paths = card.querySelector(".lc-paths").value
            .split("\n").map(p => p.trim()).filter(Boolean);
        const watch = card.querySelector(".lc-watch").checked;
        const scan_interval = parseInt(card.querySelector(".lc-scan-interval").value) || 0;
        const scan_unit = card.querySelector(".lc-scan-unit").value;
        const skip_rules = collectSkipRules(card.querySelector(".lc-skip-rules"));
        const path_patterns = collectPathPatterns(card.querySelector(".lc-path-patterns"));

        if (!name || !preset || paths.length === 0) {
            alert("Name, preset, and at least one path are required.");
            return;
        }

        let valid = true;
        card.querySelectorAll(".skip-cond-row").forEach(row => {
            const valInput = row.querySelector(".cond-value");
            if (!valInput.value.trim()) { alert("Value is required"); valid = false; }
        });
        if (!valid) return;

        try {
            if (isNew) {
                await api("POST", "/api/libraries", { name, paths, preset, watch, skip_rules, path_patterns, scan_interval, scan_unit });
                creatingNewLibrary = false;
            } else {
                await api("PUT", `/api/libraries/${encodeURIComponent(originalName)}`, { name, paths, preset, watch, skip_rules, path_patterns, scan_interval, scan_unit });
                editingLibraryName = null;
            }
            loadLibraries();
        } catch (e) {
            alert(e.message);
        }
    });

    card.querySelector(".lc-cancel").addEventListener("click", () => {
        if (isNew) {
            creatingNewLibrary = false;
        } else {
            editingLibraryName = null;
        }
        renderLibraries();
    });
}

function scanResultMessage(result) {
    const parts = [];
    if (result.queued > 0) parts.push(`Queued ${result.queued} file${result.queued !== 1 ? "s" : ""}.`);
    if (result.skipped > 0) parts.push(`Skipped ${result.skipped} file${result.skipped !== 1 ? "s" : ""} (matched rules).`);
    return parts.length ? parts.join(" ") : "No new files found.";
}

function setScanningBadge(name, show) {
    const card = document.querySelector(`.library-card[data-name="${CSS.escape(name)}"]`);
    if (!card) return;
    const header = card.querySelector(".library-card-header");
    const existing = header.querySelector(".scanning-badge");
    if (show && !existing) {
        const badge = document.createElement("span");
        badge.className = "scanning-badge";
        badge.textContent = "SCANNING";
        const nameEl = header.querySelector(".library-card-name");
        nameEl.after(badge);
    } else if (!show && existing) {
        existing.remove();
    }
}

export function initLibraries() {
    document.getElementById("library-grid").addEventListener("click", async (e) => {
        const btn = e.target.closest("[data-lib-action]");
        if (!btn) return;
        const name = btn.dataset.name;
        if (btn.dataset.libAction === "scan") {
            setScanningBadge(name, true);
            try {
                const result = await api("POST", `/api/libraries/${encodeURIComponent(name)}/scan`);
                setScanningBadge(name, false);
                alert(scanResultMessage(result));
            } catch (err) {
                setScanningBadge(name, false);
                alert("Scan failed: " + err.message);
            }
        } else if (btn.dataset.libAction === "edit") {
            editingLibraryName = name;
            creatingNewLibrary = false;
            renderLibraries();
        } else if (btn.dataset.libAction === "delete") {
            if (!confirm(`Delete library "${name}"?`)) return;
            try {
                await api("DELETE", `/api/libraries/${encodeURIComponent(name)}`);
                if (editingLibraryName === name) editingLibraryName = null;
                loadLibraries();
            } catch (err) {
                alert(err.message);
            }
        }
    });

    document.getElementById("btn-new-library").addEventListener("click", () => {
        creatingNewLibrary = !creatingNewLibrary;
        if (creatingNewLibrary) editingLibraryName = null;
        renderLibraries();
    });
}
