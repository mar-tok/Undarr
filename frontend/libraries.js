import { api, esc, escAttr, formatBytes, getFormSnapshot, wrapNumberInputs, clearValidation, setError } from "./helpers.js";
import { loadDeviceData, isEncoderDisabled, disabledDeviceTooltip } from "./devices.js";
import { parsePresetData } from "./presets.js";
import { openDirBrowser } from "./dir-browser.js";

let libraries = [];
let presets = [];
let editingLibraryName = null;
let creatingNewLibrary = false;
let librariesGeneration = 0;
let unavailableLibraries = {};
let missingPathsByLibrary = {};

const SCAN_UNITS = [
    { value: "seconds", label: "seconds" },
    { value: "minutes", label: "minutes" },
    { value: "hours", label: "hours" },
    { value: "days", label: "days" },
];

const SKIP_FIELDS = ["video_codec", "audio_codec", "resolution_width", "resolution_height", "bitrate_kbps", "file_size_mb", "duration_seconds", "hdr_type"];
const SKIP_OPS = ["equals", "not_equals", "less_than", "greater_than", "contains"];

async function loadLibraries() {
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

export async function loadLibraryView() {
    await loadDeviceData();
    await loadLibraries();
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

    const editCard = grid.querySelector(".lib-card.editing");
    if (editCard) {
        attachLibFormCardListeners(editCard, creatingNewLibrary ? null : editingLibraryName);
        wrapNumberInputs(editCard);
    }
}

function renderLibraryViewCard(lib) {
    const preset = presets.find(p => p.name === lib.preset);
    const encoder = preset ? (parsePresetData(preset).encoder || "") : "";
    const disabled = encoder && isEncoderDisabled(encoder);
    let propsHtml = "";
    propsHtml += `<dt>Preset</dt><dd>${lib.preset ? esc(lib.preset) : "(none)"}</dd>`;
    const libMissing = missingPathsByLibrary[lib.name] || [];
    lib.paths.forEach((p, i) => {
        const pathMissing = libMissing.includes(p);
        if (pathMissing) {
            propsHtml += `<dt>${i === 0 ? "Paths" : ""}</dt><dd class="lib-path-cell path-missing" data-tooltip="This path is not accessible.<br>Files on this path are not being scanned."><img class="path-warning-icon" src="warning-triangle-fill.svg" alt="Missing"><span class="path-text-rtl">${esc(p)}</span></dd>`;
        } else {
            propsHtml += `<dt>${i === 0 ? "Paths" : ""}</dt><dd class="lib-path-cell" title="${escAttr(p)}">${esc(p)}</dd>`;
        }
    });
    if (!lib.paths.length) propsHtml += `<dt>Paths</dt><dd>0</dd>`;
    propsHtml += `<dt>Watch</dt><dd>${lib.watch ? "Yes" : "No"}</dd>`;
    if (lib.scan_interval > 0) {
        propsHtml += `<dt>Scan</dt><dd>Every ${lib.scan_interval} ${esc(lib.scan_unit)}</dd>`;
    }
    if (lib.new_file_delay) {
        propsHtml += `<dt>Delay</dt><dd>${esc(String(lib.new_file_delay))} ${esc(lib.new_file_delay_unit || "minutes")}</dd>`;
    }

    let warnHtml = "";
    if (!lib.preset) {
        warnHtml = `<span data-tooltip="No preset assigned.<br>Files in this library will not be transcoded.<br>Assign a preset to enable processing."><img class="warning-icon" src="warning-triangle-fill.svg" alt="No preset"></span>`;
    } else if (disabled) {
        warnHtml = `<span data-tooltip="${disabledDeviceTooltip(encoder, "library")}"><img class="warning-icon" src="warning-triangle-fill.svg" alt="Device disabled"></span>`;
    }

    const descHtml = lib.description ? `<div class="lib-card-desc">${esc(lib.description)}</div>` : "";
    const libUnavailable = unavailableLibraries[lib.name];
    const statusBadge = libUnavailable
        ? `<span class="lib-unavailable-badge" data-tooltip="${escAttr(libUnavailable)}">UNAVAILABLE</span>`
        : lib.paused ? `<span class="lib-paused-badge">PAUSED</span>` : "";

    return `<div class="lib-card" data-name="${escAttr(lib.name)}">
        <div class="lib-card-header">
            <span class="lib-card-name">${esc(lib.name)}</span>${statusBadge}
            <div class="lib-card-actions">
                ${warnHtml}<button class="btn-icon" data-action="edit-library" data-name="${escAttr(lib.name)}" data-tooltip="Edit"><img src="pencil.svg" alt="Edit"></button>
                <button class="btn-icon" data-action="delete-library" data-name="${escAttr(lib.name)}" data-tooltip="Delete"><img src="trash.svg" alt="Delete"></button>
                <div class="lib-menu-wrapper">
                    <button class="btn-icon" data-action="lib-menu" data-name="${escAttr(lib.name)}" data-tooltip="Actions"><img src="three-dots-vertical.svg" alt="Actions"></button>
                </div>
            </div>
        </div>
        ${descHtml}
        <dl class="lib-card-props">${propsHtml}</dl>
    </div>`;
}

function renderLibraryFormCard(lib) {
    const name = lib ? lib.name : "";
    const paths = lib ? lib.paths : [];
    const preset = lib ? lib.preset : (presets[0]?.name || "");
    const watch = lib ? lib.watch : true;
    const description = lib ? (lib.description || "") : "";
    const scanInterval = lib ? (lib.scan_interval || 0) : 0;
    const scanUnit = lib ? (lib.scan_unit || "minutes") : "minutes";
    const newFileDelay = lib ? (lib.new_file_delay || 0) : 0;
    const newFileDelayUnit = lib ? (lib.new_file_delay_unit || "minutes") : "minutes";

    const presetOptionsHtml = `<option value=""${!preset ? " selected" : ""}>(none)</option>` + presets.map(p =>
        `<option value="${escAttr(p.name)}"${p.name === preset ? " selected" : ""}>${esc(p.name)}</option>`
    ).join("");

    const scanUnitOptionsHtml = SCAN_UNITS.map(u =>
        `<option value="${escAttr(u.value)}"${u.value === scanUnit ? " selected" : ""}>${esc(u.label)}</option>`
    ).join("");

    const delayUnitOptionsHtml = SCAN_UNITS.map(u =>
        `<option value="${escAttr(u.value)}"${u.value === newFileDelayUnit ? " selected" : ""}>${esc(u.label)}</option>`
    ).join("");

    const skipRulesHtml = (lib ? (lib.skip_rules || []) : []).map((rule, ri) => {
        const condsHtml = (rule.conditions || []).map(c => `
            <div class="skip-cond-row">
                <select class="cond-field">${SKIP_FIELDS.map(f => `<option value="${f}"${f === c.field ? " selected" : ""}>${f}</option>`).join("")}</select>
                <select class="cond-op">${SKIP_OPS.map(o => `<option value="${o}"${o === c.operator ? " selected" : ""}>${o}</option>`).join("")}</select>
                <input class="cond-value" value="${escAttr(c.value != null ? String(c.value) : "")}" placeholder="value">
                <button class="btn-icon btn-remove-cond" type="button"><img src="close.svg" alt="Remove"></button>
            </div>
        `).join("");
        return `<div class="skip-rule-group">
            <div class="skip-rule-header">
                <span class="skip-rule-label">Rule ${ri + 1}</span>
                <span class="skip-rule-actions">
                    <button class="btn-icon btn-move-rule-up" type="button"><img src="arrow-up.svg" alt="Move up"></button>
                    <button class="btn-icon btn-move-rule-down" type="button"><img src="arrow-down.svg" alt="Move down"></button>
                    <button class="btn-icon btn-remove-rule" type="button"><img src="trash.svg" alt="Remove rule"></button>
                </span>
            </div>
            <div class="skip-rule-conds">${condsHtml}</div>
            <button class="btn skip-add-cond" type="button">Add Condition</button>
        </div>`;
    }).join("");

    const pathPatternsHtml = (lib ? (lib.path_patterns || []) : []).map(p => `
        <div class="path-pattern-row">
            <input class="pattern-value" value="${escAttr(p)}" placeholder="e.g. *trailer*">
            <button class="btn-icon btn-remove-pattern" type="button"><img src="close.svg" alt="Remove"></button>
        </div>
    `).join("");

    return `<div class="lib-card editing">
        <div class="form-group">
            <label data-tooltip="A display name for this library.<br>Used for identification only. Does not affect file paths or processing.">Name</label>
            <input type="text" class="lc-name" value="${escAttr(name)}">
        </div>
        <div class="form-group">
            <label data-tooltip="The preset defines how files in this library are transcoded.<br>It controls the <em>encoder</em>, <em>quality</em>, <em>speed</em>, <em>container</em>, and any extra FFmpeg flags.">Preset</label>
            <select class="lc-preset">${presetOptionsHtml}</select>
        </div>
        <div class="form-group">
            <label data-tooltip="A personal note for your own reference.<br>Displayed on the library card. Does not affect processing.">Description</label>
            <input type="text" class="lc-desc" value="${escAttr(description)}" placeholder="Optional note about this library">
        </div>
        <div class="form-group">
            <label data-tooltip="Directories to scan for media files.<br>All video files found in these paths (and subdirectories) will be evaluated for transcoding.">Paths</label>
            <div class="path-chips lc-path-chips">${paths.length ? paths.map(p =>
                `<span class="path-chip" data-path="${escAttr(p)}"><button class="browse-chip" type="button">${esc(p)}</button><button class="remove-chip" type="button"><img src="close.svg" alt="Remove"></button></span>`
            ).join("") : `<span class="path-empty">No paths added.</span>`}</div>
            <div class="path-manual-row">
                <input class="lc-path-input" placeholder="/media/movies">
                <button class="btn lc-add-path" type="button">Add</button>
                <button class="btn lc-browse-path" type="button">Browse</button>
            </div>
        </div>
        <div class="toggle-row">
            <input type="checkbox" role="switch" class="lc-watch"${watch ? " checked" : ""}>
            <label data-tooltip="Monitors this library's paths for newly added or modified files using filesystem events.<br>Detected files are queued for processing after the <em>New File Delay</em> expires (immediately if delay is 0).<br>Unlike <em>Scan Interval</em>, file watching detects changes continuously.">Watch for new files</label>
        </div>
        ${!lib ? `<div class="toggle-row">
            <input type="checkbox" role="switch" class="lc-mark-processed">
            <label data-tooltip="Marks all files currently in this library's paths as already processed.<br>They will not be queued for transcoding until a <em>Force Rescan</em>.<br>Only new files added after this library is created will be picked up.<br><br>Use this when importing a library that has already been transcoded, or one you don't want to process yet.">Mark existing files as processed</label>
        </div>` : ""}
        <div class="form-row form-row-4">
            <div class="form-group">
                <label data-tooltip="How often to automatically re-scan this library's paths for new or changed files.<br>Already processed files are skipped unless they have been modified since.<br>Useful as a safety net alongside <em>Watch for new files</em>, catching files added while the app was down or on network mounts where filesystem events may not fire.<br>Set to 0 to disable (default). You can still scan manually.">Scan Interval</label>
                <input type="number" class="lc-scan-interval" min="0" value="${scanInterval}" placeholder="0">
            </div>
            <div class="form-group">
                <label data-tooltip="The time unit for the scan interval.<br>For example, an interval of 30 with unit <em>minutes</em> scans every 30 minutes.">Scan Unit</label>
                <select class="lc-scan-unit">${scanUnitOptionsHtml}</select>
            </div>
        </div>
        <div class="form-row form-row-4">
            <div class="form-group">
                <label data-tooltip="How long to wait after a file is first detected or last modified before queuing it.<br>The timer resets if the file changes again during the wait.<br>Set to 0 to process files immediately (default).">New File Delay</label>
                <input type="number" class="lc-new-file-delay" min="0" value="${newFileDelay}" placeholder="0">
            </div>
            <div class="form-group">
                <label data-tooltip="The time unit for the new file delay.">Delay Unit</label>
                <select class="lc-new-file-delay-unit">${delayUnitOptionsHtml}</select>
            </div>
        </div>
        <div>
            <label class="section-label" data-tooltip="Glob patterns matched against each file's path relative to the library root.<br>Case-insensitive. <code>*</code> matches any characters including directory separators.<br>Files matching any pattern are skipped before probing.<br><br>Examples:<br><code>*trailer*</code> (files with 'trailer' in the name)<br><code>*/Extras/*</code> (files inside an Extras folder)<br><code>*sample*</code> (files with 'sample' in the name)">Path Patterns</label>
            <div class="lc-path-patterns">${pathPatternsHtml}</div>
            <button class="btn lc-add-pattern" type="button" style="margin-top:6px">Add Pattern</button>
        </div>
        <div style="margin-top:12px">
            <label class="section-label" data-tooltip="Rules that prevent specific files from being queued.<br>Each rule can have multiple conditions, all of which must match (AND).<br>If any rule matches, the file is skipped (OR between rules).<br><br>Example: skip HEVC files below 3000 kbps by adding both conditions to one rule.<br><br><code>hdr_type</code> is empty for SDR files, otherwise <code>hdr10</code>, <code>hdr10+</code>, <code>dolby_vision</code>, or <code>hlg</code>. <code>hdr_type not_equals</code> with an empty value skips every HDR file.">Skip Rules</label>
            <div class="lc-skip-rules">${skipRulesHtml}</div>
            <button class="btn lc-add-rule" type="button" style="margin-top:6px">Add Rule</button>
        </div>
        <div class="form-actions">
            <span class="lc-preview-hint" style="display:none;font-size:12px;align-self:center">Preview unavailable when marking existing files as processed.</span>
            <button class="btn lc-preview" type="button">Preview</button>
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
        <button class="btn-icon btn-remove-cond" type="button"><img src="close.svg" alt="Remove"></button>
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
                <button class="btn-icon btn-move-rule-up" type="button"><img src="arrow-up.svg" alt="Move up"></button>
                <button class="btn-icon btn-move-rule-down" type="button"><img src="arrow-down.svg" alt="Move down"></button>
                <button class="btn-icon btn-remove-rule" type="button"><img src="trash.svg" alt="Remove rule"></button>
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
    group.querySelector(".btn-move-rule-up").addEventListener("click", () => {
        moveRuleGroup(group, -1, rulesEl);
        rulesEl.dispatchEvent(new Event("input", { bubbles: true }));
    });
    group.querySelector(".btn-move-rule-down").addEventListener("click", () => {
        moveRuleGroup(group, 1, rulesEl);
        rulesEl.dispatchEvent(new Event("input", { bubbles: true }));
    });
    const condsEl = group.querySelector(".skip-rule-conds");
    group.querySelector(".skip-add-cond").addEventListener("click", () => {
        addCondRow(condsEl, "video_codec", "equals", "");
        rulesEl.dispatchEvent(new Event("input", { bubbles: true }));
    });
    addCondRow(condsEl, "video_codec", "equals", "");
    rulesEl.appendChild(group);
    updateRuleArrows(rulesEl);
}

function renumberRuleGroups(container) {
    if (!container) return;
    container.querySelectorAll(".skip-rule-group").forEach((g, i) => {
        const label = g.querySelector(".skip-rule-label");
        if (label) label.textContent = `Rule ${i + 1}`;
    });
    updateRuleArrows(container);
}

function updateRuleArrows(container) {
    if (!container) return;
    const groups = container.querySelectorAll(".skip-rule-group");
    groups.forEach((g, i) => {
        const up = g.querySelector(".btn-move-rule-up");
        const down = g.querySelector(".btn-move-rule-down");
        if (up) up.style.visibility = i === 0 ? "hidden" : "";
        if (down) down.style.visibility = i === groups.length - 1 ? "hidden" : "";
    });
}

function moveRuleGroup(group, dir, container) {
    const sibling = dir === -1 ? group.previousElementSibling : group.nextElementSibling;
    if (!sibling || !sibling.classList.contains("skip-rule-group")) return;
    if (dir === -1) container.insertBefore(group, sibling);
    else container.insertBefore(sibling, group);
    renumberRuleGroups(container);
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
        <button class="btn-icon btn-remove-pattern" type="button"><img src="close.svg" alt="Remove"></button>
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

    const chipsContainer = card.querySelector(".lc-path-chips");
    const pathInput = card.querySelector(".lc-path-input");

    const rulesEl = card.querySelector(".lc-skip-rules");
    card.querySelectorAll(".skip-rule-group").forEach(group => {
        group.querySelector(".btn-remove-rule").addEventListener("click", () => {
            group.remove();
            renumberRuleGroups(rulesEl);
            checkChanged();
        });
        group.querySelector(".btn-move-rule-up").addEventListener("click", () => {
            moveRuleGroup(group, -1, rulesEl);
            checkChanged();
        });
        group.querySelector(".btn-move-rule-down").addEventListener("click", () => {
            moveRuleGroup(group, 1, rulesEl);
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
    updateRuleArrows(rulesEl);

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

    function updatePathEmpty() {
        const empty = chipsContainer.querySelector(".path-empty");
        if (chipsContainer.querySelectorAll(".path-chip").length) {
            if (empty) empty.remove();
        } else if (!empty) {
            chipsContainer.innerHTML = `<span class="path-empty">No paths added.</span>`;
        }
    }

    function addPathChip(path) {
        path = path.trim();
        if (!path) return;
        const existing = chipsContainer.querySelectorAll(".path-chip");
        for (const chip of existing) {
            if (chip.dataset.path === path) return;
        }
        const chip = document.createElement("span");
        chip.className = "path-chip";
        chip.dataset.path = path;
        chip.innerHTML = `<button class="browse-chip" type="button">${esc(path)}</button><button class="remove-chip" type="button"><img src="close.svg" alt="Remove"></button>`;
        chipsContainer.appendChild(chip);
        updatePathEmpty();
        checkChanged();
    }

    function getPathsFromChips() {
        return Array.from(chipsContainer.querySelectorAll(".path-chip")).map(c => c.dataset.path);
    }

    chipsContainer.addEventListener("click", (e) => {
        const removeBtn = e.target.closest(".remove-chip");
        if (removeBtn) {
            removeBtn.closest(".path-chip").remove();
            updatePathEmpty();
            checkChanged();
            return;
        }
        const browseBtn = e.target.closest(".browse-chip");
        if (browseBtn) {
            const chip = browseBtn.closest(".path-chip");
            openDirBrowser(chip.dataset.path, addPathChip, { multi: true, currentPaths: getPathsFromChips() });
        }
    });

    const addPathBtn = card.querySelector(".lc-add-path");
    addPathBtn.disabled = true;

    function clearPathError() {
        pathInput.classList.remove("invalid");
        const existing = pathInput.parentElement.parentElement.querySelector(".path-input-error");
        if (existing) existing.remove();
    }

    function showPathError(msg) {
        clearPathError();
        pathInput.classList.add("invalid");
        const err = document.createElement("div");
        err.className = "field-error path-input-error";
        err.textContent = msg;
        pathInput.parentElement.after(err);
    }

    pathInput.addEventListener("input", () => {
        clearPathError();
        addPathBtn.disabled = !pathInput.value.trim();
    });

    async function validateAndAddPath() {
        const path = pathInput.value.trim();
        if (!path) return;
        if (!path.startsWith("/")) {
            showPathError("Path must be absolute (start with /)");
            return;
        }
        try {
            await api("GET", `/api/filesystem/browse?path=${encodeURIComponent(path)}`);
            clearPathError();
            addPathChip(path);
            pathInput.value = "";
            addPathBtn.disabled = true;
        } catch (e) {
            showPathError(e.message);
        }
    }

    pathInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter") { e.preventDefault(); validateAndAddPath(); }
    });

    addPathBtn.addEventListener("click", validateAndAddPath);

    card.querySelector(".lc-browse-path").addEventListener("click", () => {
        openDirBrowser(null, addPathChip, { multi: true, currentPaths: getPathsFromChips() });
    });

    card.querySelector(".lc-save").addEventListener("click", async () => {
        clearValidation(card);
        const nameEl = card.querySelector(".lc-name");
        const presetEl = card.querySelector(".lc-preset");
        const name = nameEl.value.trim();
        const paths = getPathsFromChips();
        const preset = presetEl.value;
        const watch = card.querySelector(".lc-watch").checked;
        const scan_interval = parseInt(card.querySelector(".lc-scan-interval").value) || 0;
        const scan_unit = card.querySelector(".lc-scan-unit").value;
        const new_file_delay = parseInt(card.querySelector(".lc-new-file-delay").value) || 0;
        const new_file_delay_unit = card.querySelector(".lc-new-file-delay-unit").value;
        const skip_rules = collectSkipRules(card.querySelector(".lc-skip-rules"));
        const path_patterns = collectPathPatterns(card.querySelector(".lc-path-patterns"));

        let valid = true;
        if (!name) { setError(nameEl, "Name is required"); valid = false; }
        if (!paths.length) { setError(chipsContainer, "At least one path is required"); valid = false; }
        card.querySelectorAll(".skip-cond-row").forEach(row => {
            const valInput = row.querySelector(".cond-value");
            const op = row.querySelector(".cond-op").value;
            const val = valInput.value.trim();
            if (op !== "equals" && op !== "not_equals" && !val) { setError(valInput, "Value is required"); valid = false; }
            else if ((op === "less_than" || op === "greater_than") && isNaN(Number(val))) { setError(valInput, "Value must be a number"); valid = false; }
        });
        if (!valid) return;

        const description = card.querySelector(".lc-desc").value.trim() || null;

        try {
            if (isNew) {
                const mark_existing_processed = card.querySelector(".lc-mark-processed").checked;
                await api("POST", "/api/libraries", { name, paths, preset, watch, skip_rules, path_patterns, scan_interval, scan_unit, description, mark_existing_processed, new_file_delay, new_file_delay_unit });
                creatingNewLibrary = false;
            } else {
                await api("PUT", `/api/libraries/${encodeURIComponent(originalName)}`, { name, paths, preset, watch, skip_rules, path_patterns, scan_interval, scan_unit, description, new_file_delay, new_file_delay_unit });
                editingLibraryName = null;
            }
            loadLibraries();
        } catch (e) {
            if (e.message.toLowerCase().includes("overlaps with library")) {
                showPathError(e.message);
            } else {
                setError(nameEl, e.message);
            }
        }
    });

    const markProcessedCb = card.querySelector(".lc-mark-processed");
    const previewBtn = card.querySelector(".lc-preview");
    const previewHint = card.querySelector(".lc-preview-hint");
    if (markProcessedCb) {
        markProcessedCb.addEventListener("change", () => {
            previewBtn.disabled = markProcessedCb.checked;
            previewHint.style.display = markProcessedCb.checked ? "" : "none";
        });
    }

    previewBtn.addEventListener("click", () => {
        const paths = getPathsFromChips();
        if (!paths.length) return;
        const name = card.querySelector(".lc-name").value.trim();
        const skip_rules = collectSkipRules(card.querySelector(".lc-skip-rules"));
        const path_patterns = collectPathPatterns(card.querySelector(".lc-path-patterns"));
        const new_file_delay = parseInt(card.querySelector(".lc-new-file-delay").value) || 0;
        const new_file_delay_unit = card.querySelector(".lc-new-file-delay-unit").value;
        openPreviewModal(null, { name, paths, skip_rules, path_patterns, new_file_delay, new_file_delay_unit });
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

function setScanningBadge(name, show, label = "SCANNING") {
    const card = document.querySelector(`.lib-card[data-name="${CSS.escape(name)}"]`);
    if (!card) return;
    const header = card.querySelector(".lib-card-header");
    const existing = header.querySelector(".lib-scanning-badge");
    if (show && !existing) {
        const badge = document.createElement("span");
        badge.className = "lib-scanning-badge";
        badge.textContent = label;
        const nameEl = header.querySelector(".lib-card-name");
        nameEl.after(badge);
    } else if (!show && existing) {
        existing.remove();
    }
}

export function initLibraries() {
    document.getElementById("library-grid").addEventListener("click", async (e) => {
        const btn = e.target.closest("[data-action]");
        if (!btn) return;
        const name = btn.dataset.name;
        if (btn.dataset.action === "edit-library") {
            editingLibraryName = name;
            creatingNewLibrary = false;
            renderLibraries();
        } else if (btn.dataset.action === "delete-library") {
            if (!confirm(`Delete library "${name}"?\n\nThis removes the library configuration and stops watching its paths. Your media files are not affected.\n\nQueued jobs from this library will remain in the queue. History and processed file records are kept.`)) return;
            try {
                await api("DELETE", `/api/libraries/${encodeURIComponent(name)}`);
                if (editingLibraryName === name) editingLibraryName = null;
                loadLibraries();
            } catch (err) {
                alert(err.message);
            }
        } else if (btn.dataset.action === "lib-menu") {
            const wrapper = btn.closest(".lib-menu-wrapper");
            const existing = wrapper.querySelector(".lib-context-menu");
            if (existing) { existing.remove(); return; }

            const lib = libraries.find(l => l.name === name);
            const preset = lib ? presets.find(p => p.name === lib.preset) : null;
            const encoder = preset ? (parsePresetData(preset).encoder || "") : "";
            const scanDisabled = !lib?.preset || (encoder && isEncoderDisabled(encoder));

            const menu = document.createElement("div");
            menu.className = "lib-context-menu";

            const items = [
                { action: "toggle-pause", label: lib?.paused ? "Resume Processing" : "Pause Processing" },
                { action: "preview", label: "Preview" },
                { action: "scan", label: "Scan & Queue", disabled: scanDisabled },
                { action: "force-scan", label: "Force Rescan", disabled: scanDisabled },
                { action: "mark-processed", label: "Mark All Processed" },
            ];

            for (const item of items) {
                const b = document.createElement("button");
                b.textContent = item.label;
                b.dataset.menuAction = item.action;
                if (item.disabled) b.disabled = true;
                menu.appendChild(b);
            }

            wrapper.appendChild(menu);

            menu.addEventListener("click", async (ev) => {
                const menuBtn = ev.target.closest("[data-menu-action]");
                if (!menuBtn || menuBtn.disabled) return;
                const action = menuBtn.dataset.menuAction;
                menu.remove();

                if (action === "preview") {
                    openPreviewModal(name);
                } else if (action === "toggle-pause") {
                    const isPaused = lib?.paused;
                    try {
                        await api("POST", `/api/libraries/${encodeURIComponent(name)}/pause`, { paused: !isPaused });
                        loadLibraries();
                    } catch (err) {
                        alert(err.message);
                    }
                } else if (action === "scan") {
                    if (!confirm(`This will scan all paths in "${name}" and queue any unprocessed files for transcoding. Continue?`)) return;
                    setScanningBadge(name, true);
                    try {
                        const result = await api("POST", `/api/libraries/${encodeURIComponent(name)}/scan`);
                        setScanningBadge(name, false);
                        await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
                        alert(scanResultMessage(result));
                    } catch (err) {
                        setScanningBadge(name, false);
                        alert("Scan failed: " + err.message);
                    }
                } else if (action === "force-scan") {
                    if (!confirm(`Force rescan "${name}"?\n\nThis clears all processed file records for this library and re-evaluates every file from scratch. Files matching skip rules will still be skipped.\n\nThis is only needed if you changed the library's preset and want to re-process files, or if files were incorrectly skipped.`)) return;
                    setScanningBadge(name, true);
                    try {
                        const result = await api("POST", `/api/libraries/${encodeURIComponent(name)}/scan?force=true`);
                        setScanningBadge(name, false);
                        await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
                        alert(scanResultMessage(result));
                    } catch (err) {
                        setScanningBadge(name, false);
                        alert("Force scan failed: " + err.message);
                    }
                } else if (action === "mark-processed") {
                    if (!confirm(`Mark all files in "${name}" as processed?\n\nEvery file currently in this library's paths will be marked as already handled. They will not be queued on future scans or startup.\n\nOnly new files added after this point, or files whose content changes, will be picked up.\n\nUse Force Rescan to undo this and re-evaluate all files.`)) return;
                    setScanningBadge(name, true, "MARKING");
                    try {
                        const result = await api("POST", `/api/libraries/${encodeURIComponent(name)}/mark-processed`);
                        setScanningBadge(name, false);
                        alert(`Marked ${result.marked} file${result.marked !== 1 ? "s" : ""} as processed.`);
                    } catch (err) {
                        setScanningBadge(name, false);
                        alert("Failed to mark files: " + err.message);
                    }
                }
            });

            const closeMenu = (ev) => {
                if (!menu.contains(ev.target) && ev.target !== btn && !btn.contains(ev.target)) {
                    menu.remove();
                    document.removeEventListener("click", closeMenu);
                }
            };
            setTimeout(() => document.addEventListener("click", closeMenu), 0);
        }
    });

    document.getElementById("btn-new-library").addEventListener("click", () => {
        creatingNewLibrary = !creatingNewLibrary;
        if (creatingNewLibrary) editingLibraryName = null;
        renderLibraries();
    });
}

let previewOverlay = null;
let previewScanning = false;

export function updatePreviewProgress(data) {
    if (!previewOverlay) return;
    const loading = previewOverlay.querySelector(".preview-loading");
    if (loading) {
        loading.textContent = `Scanning... ${data.scanned}/${data.total}`;
    }
}

export function onLibraryMissingPaths(data) {
    if (data.missing_paths && data.missing_paths.length) {
        missingPathsByLibrary[data.library_name] = data.missing_paths;
    } else {
        delete missingPathsByLibrary[data.library_name];
    }
    if (!editingLibraryName && !creatingNewLibrary) renderLibraries();
}

export function onLibraryUnavailable(data) {
    if (data.unavailable) {
        unavailableLibraries[data.library_name] = data.reason;
    } else {
        delete unavailableLibraries[data.library_name];
    }
    if (!editingLibraryName && !creatingNewLibrary) renderLibraries();
}

function cancelPreview() {
    if (previewScanning) {
        previewScanning = false;
        api("POST", "/api/libraries/preview/cancel").catch(() => {});
    }
}

export function openPreviewModal(libraryName, config) {
    if (previewOverlay) {
        cancelPreview();
        previewOverlay.remove();
    }

    previewScanning = true;
    const title = libraryName || config?.name || "New Library";
    const overlay = document.createElement("div");
    overlay.className = "preview-overlay";
    overlay.innerHTML = `
        <div class="preview-modal">
            <div class="preview-header">
                <span class="preview-title">Preview: ${esc(title)}</span>
                <button class="btn-icon preview-close" data-tooltip="Close"><img src="close.svg" alt="Close"></button>
            </div>
            <div class="preview-body">
                <button class="btn preview-stop-btn">Stop Scanning</button>
                <div class="preview-loading">Scanning...</div>
            </div>
            <div class="preview-footer">
                <button class="btn preview-close-btn">Close</button>
            </div>
        </div>`;
    document.body.appendChild(overlay);
    previewOverlay = overlay;

    const modal = overlay.querySelector(".preview-modal");

    function close() {
        cancelPreview();
        overlay.remove();
        previewOverlay = null;
        document.removeEventListener("keydown", onKey);
    }

    function onKey(e) {
        if (e.key === "Escape") close();
    }
    document.addEventListener("keydown", onKey);

    overlay.addEventListener("click", (e) => {
        if (e.target === overlay) {
            modal.classList.add("flash");
            setTimeout(() => modal.classList.remove("flash"), 150);
        }
    });

    overlay.querySelector(".preview-close").addEventListener("click", close);
    overlay.querySelector(".preview-close-btn").addEventListener("click", close);
    overlay.querySelector(".preview-stop-btn").addEventListener("click", cancelPreview);

    const body_data = config ? { ...config } : null;

    const request = body_data
        ? api("POST", "/api/libraries/preview", body_data)
        : api("POST", `/api/libraries/${encodeURIComponent(libraryName)}/preview`);

    request
        .then(result => {
            previewScanning = false;
            renderPreviewResult(overlay, result);
        })
        .catch(err => {
            previewScanning = false;
            const body = overlay.querySelector(".preview-body");
            if (body) body.innerHTML = `<div class="preview-error">${esc(err.message)}</div>`;
        });
}

function renderPreviewResult(overlay, result) {
    const body = overlay.querySelector(".preview-body");
    if (!body) return;
    const s = result.summary;

    let summaryHtml = `<div class="preview-summary">`;
    summaryHtml += `<span>${s.total_files} total files</span>`;
    summaryHtml += `<span>${s.would_queue} would be queued (${formatBytes(s.would_queue_bytes)})</span>`;
    summaryHtml += `<span>${s.already_processed} already processed</span>`;
    if (s.skipped > 0) summaryHtml += `<span>${s.skipped} skipped</span>`;
    if (s.not_scanned > 0) summaryHtml += `<span>${s.not_scanned} files not scanned</span>`;
    summaryHtml += `</div>`;

    const hasSkipped = result.skipped.length > 0;

    let tabsHtml = `<div class="preview-tabs">`;
    tabsHtml += `<button class="preview-tab active" data-ptab="queue">Would Be Queued (${result.queue.length})</button>`;
    if (hasSkipped) tabsHtml += `<button class="preview-tab" data-ptab="skipped">Skipped (${result.skipped.length})</button>`;
    tabsHtml += `</div>`;

    let queuePane = `<div class="preview-pane active" id="preview-pane-queue">`;
    if (result.queue.length) {
        const sorted = [...result.queue].sort((a, b) => b.size_bytes - a.size_bytes);
        queuePane += `<div class="preview-table-wrap">
            <table class="preview-table queue-table">
                <thead><tr><th>File</th><th>Codec</th><th>Resolution</th><th>Size</th></tr></thead>
                <tbody>${sorted.map((f, i) => `<tr class="${i % 2 ? "stripe" : ""}">
                    <td title="${escAttr(f.path)}">${esc(f.path)}</td>
                    <td>${esc(f.video_codec.toUpperCase())}</td>
                    <td>${esc(f.resolution)}</td>
                    <td>${formatBytes(f.size_bytes)}</td>
                </tr>`).join("")}</tbody>
            </table>
        </div>`;
    } else {
        queuePane += `<div class="preview-empty">No files would be queued.</div>`;
    }
    queuePane += `</div>`;

    let skippedPane = "";
    if (hasSkipped) {
        skippedPane = `<div class="preview-pane" id="preview-pane-skipped">
            <div class="preview-table-wrap">
                <table class="preview-table skipped-table">
                    <thead><tr><th>File</th><th>Reason</th><th>Size</th></tr></thead>
                    <tbody>${result.skipped.map((f, i) => `<tr class="${i % 2 ? "stripe" : ""}">
                        <td title="${escAttr(f.path)}">${esc(f.path)}</td>
                        <td>${esc(f.reason)}</td>
                        <td>${formatBytes(f.size_bytes)}</td>
                    </tr>`).join("")}</tbody>
                </table>
            </div>
        </div>`;
    }

    body.innerHTML = summaryHtml + tabsHtml + queuePane + skippedPane;

    body.querySelectorAll(".preview-tab").forEach(tab => {
        tab.addEventListener("click", () => {
            body.querySelectorAll(".preview-tab").forEach(t => t.classList.toggle("active", t === tab));
            body.querySelectorAll(".preview-pane").forEach(p => p.classList.toggle("active", p.id === "preview-pane-" + tab.dataset.ptab));
        });
    });
}
