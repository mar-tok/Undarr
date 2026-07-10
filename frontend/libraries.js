import { api, esc, escAttr, getFormSnapshot, wrapNumberInputs, clearValidation, setError } from "./helpers.js";

let libraries = [];
let presets = [];
let editingLibraryName = null;
let creatingNewLibrary = false;
let librariesGeneration = 0;

const SKIP_FIELDS = ["video_codec", "audio_codec", "resolution_width", "resolution_height", "bitrate_kbps", "file_size_mb", "duration_seconds"];
const SKIP_OPS = ["equals", "not_equals", "less_than", "greater_than", "contains"];

export async function loadLibraries() {
    const gen = ++librariesGeneration;
    const [libs, pres] = await Promise.all([
        api("GET", "/api/libraries"),
        api("GET", "/api/presets"),
    ]);
    if (gen !== librariesGeneration) return;
    libraries = libs;
    presets = pres;
    renderLibraries();
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
    if (editCard) {
        attachLibFormCardListeners(editCard, creatingNewLibrary ? null : editingLibraryName);
        wrapNumberInputs(editCard);
    }
}

function renderLibraryViewCard(lib) {
    let propsHtml = "";
    propsHtml += `<dt>Preset</dt><dd>${esc(lib.preset)}</dd>`;
    propsHtml += `<dt>Watch</dt><dd>${lib.watch ? "Yes" : "No"}</dd>`;
    if (lib.scan_interval > 0) {
        propsHtml += `<dt>Scan</dt><dd>Every ${lib.scan_interval} ${esc(lib.scan_unit)}</dd>`;
    }
    propsHtml += `<dt>Paths</dt><dd>${esc(lib.paths.join(", "))}</dd>`;

    return `<div class="library-card" data-name="${escAttr(lib.name)}">
        <div class="library-card-header">
            <span class="library-card-name">${esc(lib.name)}</span>
            <div class="library-card-actions">
                <button class="btn" data-lib-action="scan" data-name="${escAttr(lib.name)}">Scan</button>
                <button class="btn" data-lib-action="edit" data-name="${escAttr(lib.name)}">Edit</button>
                <button class="btn btn-danger" data-lib-action="delete" data-name="${escAttr(lib.name)}">Delete</button>
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

    const presetOptionsHtml = presets.map(p =>
        `<option value="${escAttr(p.name)}"${p.name === preset ? " selected" : ""}>${esc(p.name)}</option>`).join("");

    const skipRulesHtml = (lib ? (lib.skip_rules || []) : []).map((rule, ri) => {
        const condsHtml = (rule.conditions || []).map(c => `
            <div class="skip-cond-row">
                <select class="cond-field">${SKIP_FIELDS.map(f => `<option value="${f}"${f === c.field ? " selected" : ""}>${f}</option>`).join("")}</select>
                <select class="cond-op">${SKIP_OPS.map(o => `<option value="${o}"${o === c.operator ? " selected" : ""}>${o}</option>`).join("")}</select>
                <input class="cond-value" value="${escAttr(c.value != null ? String(c.value) : "")}" placeholder="value">
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
            <input class="pattern-value" value="${escAttr(p)}" placeholder="e.g. *trailer*">
            <button class="btn btn-sm btn-remove-pattern" type="button">Remove</button>
        </div>
    `).join("");

    return `<div class="library-card editing">
        <div class="form-group">
            <label data-tooltip="A display name for this library.<br>Used for identification only. Does not affect file paths or processing.">Name</label>
            <input type="text" class="lc-name" value="${escAttr(name)}">
        </div>
        <div class="form-group">
            <label data-tooltip="The preset defines how files in this library are transcoded.<br>It controls the <em>encoder</em>, <em>quality</em>, <em>speed</em>, <em>container</em>, and any extra FFmpeg flags.">Preset</label>
            <select class="lc-preset">${presetOptionsHtml}</select>
        </div>
        <div class="form-group">
            <label data-tooltip="Directories to scan for media files.<br>All video files found in these paths (and subdirectories) will be evaluated for transcoding.">Paths (one per line)</label>
            <textarea class="lc-paths" placeholder="/media/movies">${esc(paths)}</textarea>
        </div>
        <div class="form-group">
            <label data-tooltip="Monitors this library's paths for newly added or modified files using filesystem events.<br>Unlike <em>Scan Interval</em>, file watching detects changes continuously."><input type="checkbox" role="switch" class="lc-watch"${watch ? " checked" : ""}> Watch for new files</label>
        </div>
        <div class="form-group">
            <label data-tooltip="How often to automatically re-scan this library's paths for new or changed files.<br>Already processed files are skipped.<br>Useful as a safety net alongside <em>Watch for new files</em>, catching files added while the app was down or on network mounts where filesystem events may not fire.<br>Set to 0 to disable (default). You can still scan manually.">Scan Interval</label>
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
            <label class="section-label" data-tooltip="Glob patterns matched against each file's path relative to the library root.<br>Case-insensitive. <code>*</code> matches any characters including directory separators.<br>Files matching any pattern are skipped before probing.<br><br>Examples:<br><code>*trailer*</code> (files with 'trailer' in the name)<br><code>*/Extras/*</code> (files inside an Extras folder)<br><code>*sample*</code> (files with 'sample' in the name)">Path Patterns</label>
            <div class="lc-path-patterns">${pathPatternsHtml}</div>
            <button class="btn lc-add-pattern" type="button" style="margin-top:6px">Add Pattern</button>
        </div>
        <div style="margin-top:12px">
            <label class="section-label" data-tooltip="Rules that prevent specific files from being queued.<br>Each rule can have multiple conditions, all of which must match (AND).<br>If any rule matches, the file is skipped (OR between rules).<br><br>Example: skip HEVC files below 3000 kbps by adding both conditions to one rule.">Skip Rules</label>
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
        <input class="cond-value" value="${escAttr(valVal != null ? String(valVal) : "")}" placeholder="value">
        <button class="btn btn-sm btn-remove-cond" type="button">Remove</button>
    `;
    row.querySelector(".btn-remove-cond").addEventListener("click", () => {
        const group = row.closest(".skip-rule-group");
        row.remove();
        if (!group.querySelector(".skip-cond-row")) {
            group.remove();
            renumberRuleGroups(group.parentElement);
        }
        condsEl.dispatchEvent(new Event("input", { bubbles: true }));
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
        rulesEl.dispatchEvent(new Event("input", { bubbles: true }));
    });
    const condsEl = group.querySelector(".skip-rule-conds");
    group.querySelector(".skip-add-cond").addEventListener("click", () => {
        addCondRow(condsEl, "video_codec", "equals", "");
        rulesEl.dispatchEvent(new Event("input", { bubbles: true }));
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
        <input class="pattern-value" value="${escAttr(value || "")}" placeholder="e.g. *trailer*">
        <button class="btn btn-sm btn-remove-pattern" type="button">Remove</button>
    `;
    row.querySelector(".btn-remove-pattern").addEventListener("click", () => { row.remove(); container.dispatchEvent(new Event("input", { bubbles: true })); });
    container.appendChild(row);
}

function collectPathPatterns(container) {
    return Array.from(container.querySelectorAll(".path-pattern-row"))
        .map(row => row.querySelector(".pattern-value").value.trim())
        .filter(v => v);
}

function attachLibFormCardListeners(card, originalName) {
    const isNew = originalName === null;
    const saveBtn = card.querySelector(".lc-save");
    saveBtn.disabled = true;
    const initialSnapshot = getFormSnapshot(card);
    function checkChanged() { saveBtn.disabled = getFormSnapshot(card) === initialSnapshot; }
    card.addEventListener("input", checkChanged);
    card.addEventListener("change", checkChanged);

    const rulesEl = card.querySelector(".lc-skip-rules");
    card.querySelectorAll(".skip-rule-group").forEach(group => {
        group.querySelector(".btn-remove-rule").addEventListener("click", () => {
            group.remove();
            renumberRuleGroups(rulesEl);
            checkChanged();
        });
        const condsEl = group.querySelector(".skip-rule-conds");
        group.querySelector(".skip-add-cond").addEventListener("click", () => {
            addCondRow(condsEl, "video_codec", "equals", "");
            checkChanged();
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
                checkChanged();
            });
        });
    });

    card.querySelector(".lc-add-rule").addEventListener("click", () => {
        addRuleGroup(rulesEl);
        checkChanged();
    });

    card.querySelectorAll(".btn-remove-pattern").forEach(btn => {
        btn.addEventListener("click", () => { btn.closest(".path-pattern-row").remove(); checkChanged(); });
    });

    card.querySelector(".lc-add-pattern").addEventListener("click", () => {
        addPathPatternRow(card.querySelector(".lc-path-patterns"), "");
        checkChanged();
    });

    card.querySelector(".lc-save").addEventListener("click", async () => {
        clearValidation(card);
        const nameEl = card.querySelector(".lc-name");
        const presetEl = card.querySelector(".lc-preset");
        const pathsEl = card.querySelector(".lc-paths");
        const name = nameEl.value.trim();
        const paths = pathsEl.value
            .split("\n").map(p => p.trim()).filter(Boolean);
        const preset = presetEl.value;
        const watch = card.querySelector(".lc-watch").checked;
        const scan_interval = parseInt(card.querySelector(".lc-scan-interval").value) || 0;
        const scan_unit = card.querySelector(".lc-scan-unit").value;
        const skip_rules = collectSkipRules(card.querySelector(".lc-skip-rules"));
        const path_patterns = collectPathPatterns(card.querySelector(".lc-path-patterns"));

        let valid = true;
        if (!name) { setError(nameEl, "Name is required"); valid = false; }
        if (!preset) { setError(presetEl, "Preset is required"); valid = false; }
        if (!paths.length) { setError(pathsEl, "At least one path is required"); valid = false; }
        card.querySelectorAll(".skip-cond-row").forEach(row => {
            const valInput = row.querySelector(".cond-value");
            if (!valInput.value.trim()) { setError(valInput, "Value is required"); valid = false; }
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
            setError(nameEl, e.message);
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
