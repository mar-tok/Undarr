import { api, formatBytes, formatBytesLarge, esc, escAttr, codecLabel, codecColor, formatBitrate, formatFileDuration, formatChannels } from "./helpers.js";

let currentLibrary = null;
let currentPath = null;
let activeTab = "tree";
let libraries = [];

// Duplicates tab state
let dupGroups = null;
let dupScanning = false;
let dupAllowDeletion = false;
let dupTotalSize = 0;
let dupNotHashed = 0;

// Selection state to persist across navigation/pagination
const treeSelected = new Set();
const filesSelected = new Set();

// Tree tab state
let treeSortBy = "total_size";
let treeSortDir = "desc";
let treeSearch = "";
let treeSearchTimer = null;
let treeData = null;

// Files tab state
const FILES_PAGE_SIZES = [25, 50, 100, 200];
let filesPage = 0;
let filesPageSize = 50;
let filesSortBy = "file_size";
let filesSortDir = "desc";
let filesCodecFilter = null;
let filesResolutionFilter = null;
let filesContainerFilter = null;
let filesStatusFilter = null;
let filesSearch = "";
let filesSearchTimer = null;
let filesFilters = { codecs: [], containers: [] };
let filesTotal = 0;
let filesGeneration = 0;

function isVisible() {
    return document.getElementById("view-storage").classList.contains("active");
}

function renderHeader() {
    const el = document.getElementById("storage-header");
    el.innerHTML = `
        <div class="settings-tabs">
            <button class="settings-tab${activeTab === "tree" ? " active" : ""}" data-stab="tree">Directory</button>
            <button class="settings-tab${activeTab === "files" ? " active" : ""}" data-stab="files">Files</button>
            <button class="settings-tab${activeTab === "dupes" ? " active" : ""}" data-stab="dupes">Duplicates</button>
        </div>`;
}

function renderLibraryOptions(withAll = false) {
    const allOpt = withAll ? `<option value=""${!currentLibrary ? " selected" : ""}>All Libraries</option>` : "";
    let opts = libraries.map(l =>
        `<option value="${escAttr(l.name)}"${l.name === currentLibrary ? " selected" : ""}>${esc(l.name)}</option>`
    ).join("");
    if (!libraries.length && !allOpt) opts = '<option value="">No libraries</option>';
    return allOpt + opts;
}

function libraryPaths() {
    const lib = libraries.find(l => l.name === currentLibrary);
    return lib ? lib.paths.map(p => p.replace(/\/+$/, "")) : [];
}

function singleRootPath() {
    const paths = libraryPaths();
    return paths.length === 1 ? paths[0] : null;
}

function matchRoot(path) {
    let best = null;
    for (const rp of libraryPaths()) {
        if ((path === rp || path.startsWith(rp + "/")) && (!best || rp.length > best.length)) best = rp;
    }
    return best;
}

function renderBreadcrumb(path) {
    const single = singleRootPath();
    if (!path || path === single) return `<span class="storage-crumb-current">${esc(currentLibrary)}</span>`;
    let html = `<span class="storage-crumb" data-path="${escAttr(single || "")}">${esc(currentLibrary)}</span>`;
    const root = matchRoot(path);
    let built;
    let parts;
    if (root) {
        built = root;
        parts = path.slice(root.length).split("/").filter(Boolean);
        if (!single) {
            const rootName = root.split("/").pop() || root;
            if (path === root) {
                return html + ` <span class="storage-sep">/</span> <span class="storage-crumb-current">${esc(rootName)}</span>`;
            }
            html += ` <span class="storage-sep">/</span> <span class="storage-crumb" data-path="${escAttr(root)}">${esc(rootName)}</span>`;
        }
    } else {
        built = "";
        parts = path.split("/").filter(Boolean);
    }
    for (let i = 0; i < parts.length; i++) {
        built += "/" + parts[i];
        const isLast = i === parts.length - 1;
        if (isLast) {
            html += ` <span class="storage-sep">/</span> <span class="storage-crumb-current">${esc(parts[i])}</span>`;
        } else {
            html += ` <span class="storage-sep">/</span> <span class="storage-crumb" data-path="${escAttr(built)}">${esc(parts[i])}</span>`;
        }
    }
    return html;
}

const formatSize = formatBytesLarge;

function renderMiniCodecBar(codecs) {
    if (!codecs || !Object.keys(codecs).length) return { html: "", tooltip: "" };
    const entries = Object.entries(codecs).sort((a, b) => b[1] - a[1]);
    const total = entries.reduce((s, [, n]) => s + n, 0);
    if (!total) return { html: "", tooltip: "" };
    let html = '<div class="codec-bar storage-codec-bar">';
    const tips = [];
    for (const [codec, count] of entries) {
        const w = (count / total * 100).toFixed(1);
        tips.push(`${codecLabel(codec)}: ${count}`);
        html += `<div class="codec-segment" style="flex-basis:${w}%;background:${codecColor(codec)}"></div>`;
    }
    html += "</div>";
    return { html, tooltip: tips.join("<br>") };
}

function renderTreeControls() {
    const stats = treeData
        ? `${formatSize(treeData.total_size)} total, ${treeData.total_files} files${treeData.total_saved > 0 ? `, ${formatSize(treeData.total_saved)} saved` : ""}`
        : "";
    return `<div class="storage-filters" id="tree-controls">
        <select id="storage-lib-select">${renderLibraryOptions()}</select>
        <input type="text" id="tree-search" placeholder="Search..." value="${escAttr(treeSearch)}" style="max-width:220px;margin:0">
        <span class="storage-stats">${stats}</span>
        <button class="btn btn-primary" id="btn-queue-tree"${treeSelected.size ? "" : " disabled"}>${treeSelected.size ? `Queue Selected (${treeSelected.size})` : "Queue Selected"}</button>
    </div>`;
}

function ensureTreeLayout() {
    const content = document.getElementById("storage-content");
    if (content.querySelector("#tree-controls")) return;
    content.innerHTML = `${renderTreeControls()}<div class="storage-breadcrumb" id="tree-breadcrumb"></div><div id="tree-results"></div>`;
}

function updateTreeControls() {
    const sel = document.getElementById("storage-lib-select");
    if (sel) sel.innerHTML = renderLibraryOptions();
    const stats = document.querySelector("#tree-controls .storage-stats");
    if (stats && treeData) {
        stats.innerHTML = `${formatSize(treeData.total_size)} total, ${treeData.total_files} files${treeData.total_saved > 0 ? `, ${formatSize(treeData.total_saved)} saved` : ""}`;
    }
    const search = document.getElementById("tree-search");
    if (search && document.activeElement !== search) search.value = treeSearch;
}

async function loadTree(refetch = true) {
    const content = document.getElementById("storage-content");
    if (!currentLibrary) {
        content.innerHTML = "";
        return;
    }

    ensureTreeLayout();
    const results = document.getElementById("tree-results");
    if (refetch) {
        let url = `/api/storage/tree?library=${encodeURIComponent(currentLibrary)}`;
        if (currentPath) url += `&path=${encodeURIComponent(currentPath)}`;
        try {
            treeData = await api("GET", url);
        } catch (e) {
            results.innerHTML = `<p class="section-empty">${esc(e.message)}</p>`;
            return;
        }
    }
    if (!treeData) return;

    updateTreeControls();
    document.getElementById("tree-breadcrumb").innerHTML = renderBreadcrumb(currentPath);

    let entries = treeData.entries;
    if (treeSearch) {
        const q = treeSearch.toLowerCase();
        entries = entries.filter(e => e.name.toLowerCase().includes(q));
    }

    entries = [...entries];
    const col = treeSortBy;
    const dir = treeSortDir === "asc" ? 1 : -1;
    entries.sort((a, b) => {
        if (col === "name") return dir * a.name.localeCompare(b.name);
        if (col === "file_count") return dir * (a.file_count - b.file_count);
        if (col === "space_saved") return dir * (a.space_saved - b.space_saved);
        return dir * (a.total_size - b.total_size);
    });

    if (!entries.length) {
        results.innerHTML = '<p class="section-empty">No files found.</p>';
        return;
    }

    const maxSize = Math.max(...entries.map(e => e.total_size));

    let html = `<table class="overview-table storage-table" id="tree-table"><thead><tr>
            <th class="storage-check-col"><input type="checkbox" id="tree-select-all" data-tooltip="Select all"></th>
            <th class="sortable" style="width:38%" data-treesort="name">Name${treeSortArrow("name")}</th>
            <th class="sortable" style="width:18%" data-treesort="total_size">Size${treeSortArrow("total_size")}</th>
            <th class="sortable" style="width:8%" data-treesort="file_count">Files${treeSortArrow("file_count")}</th>
            <th style="width:20%">Codecs</th>
            <th class="sortable" style="width:14%" data-treesort="space_saved">Saved${treeSortArrow("space_saved")}</th>
        </tr></thead><tbody>`;

    entries.forEach((entry, i) => {
        const barW = maxSize > 0 ? (entry.total_size / maxSize * 100).toFixed(1) : 0;
        const icon = entry.is_dir ? "folder.svg" : "file-earmark.svg";
        const savedText = entry.space_saved > 0 ? formatBytes(entry.space_saved) : "-";
        const codec = renderMiniCodecBar(entry.codecs);
        const nameTooltip = entry.is_dir ? "" : ` data-tooltip="${escAttr(entry.path)}"`;
        const codecTip = codec.tooltip ? ` data-tooltip="${escAttr(codec.tooltip)}"` : "";
        const nameHtml = entry.is_dir
            ? `<a class="dir-link" data-dir="${escAttr(entry.path)}">${esc(entry.name)}</a>`
            : esc(entry.name);

        html += `<tr class="storage-row${i % 2 ? " stripe" : ""}">
            <td><input type="checkbox" class="tree-check" data-path="${escAttr(entry.path)}"${treeSelected.has(entry.path) ? " checked" : ""}></td>
            <td${nameTooltip}><img class="storage-icon" src="${icon}" alt="">${nameHtml}</td>
            <td class="storage-size-cell"><div class="progress-cell"><span>${formatSize(entry.total_size)}</span><div class="progress-bar-wrap"><div class="progress-bar-fill" style="width:${barW}%"></div></div></div></td>
            <td>${entry.file_count}</td>
            <td class="codec-cell"${codecTip}>${codec.html}</td>
            <td>${savedText}</td>
        </tr>`;
    });
    html += "</tbody></table>";
    results.innerHTML = html;
}

function treeSortArrow(col) {
    if (col !== treeSortBy) return "";
    return `<span class="sort-arrow">${treeSortDir === "asc" ? "\u25B2" : "\u25BC"}</span>`;
}

function sortArrow(col) {
    if (col !== filesSortBy) return "";
    return `<span class="sort-arrow">${filesSortDir === "asc" ? "\u25B2" : "\u25BC"}</span>`;
}

function filterOption(value, label, selected) {
    return `<option value="${escAttr(value)}"${value === selected ? " selected" : ""}>${esc(label)}</option>`;
}

function renderFilters() {
    const codecOpts = [filterOption("", "All codecs", filesCodecFilter || "")]
        .concat(filesFilters.codecs.map(c => filterOption(c, codecLabel(c), filesCodecFilter || "")))
        .join("");
    const containerOpts = [filterOption("", "All containers", filesContainerFilter || "")]
        .concat(filesFilters.containers.map(c => filterOption(c, c.toUpperCase(), filesContainerFilter || "")))
        .join("");
    const resOpts = [
        filterOption("", "All resolutions", filesResolutionFilter || ""),
        filterOption("4k", "4K", filesResolutionFilter || ""),
        filterOption("1080p", "1080p", filesResolutionFilter || ""),
        filterOption("720p", "720p", filesResolutionFilter || ""),
        filterOption("sd", "SD", filesResolutionFilter || ""),
    ].join("");

    return `<div class="storage-filters" id="files-filter-bar">
        <select id="storage-lib-select">${renderLibraryOptions()}</select>
        <input type="text" id="files-search" placeholder="Search..." value="${escAttr(filesSearch)}" style="max-width:220px;margin:0">
        <select id="files-codec-filter">${codecOpts}</select>
        <select id="files-resolution-filter">${resOpts}</select>
        <select id="files-container-filter">${containerOpts}</select>
        <button class="btn btn-primary" id="btn-queue-files"${filesSelected.size ? "" : " disabled"}>${filesSelected.size ? `Queue Selected (${filesSelected.size})` : "Queue Selected"}</button>
    </div>`;
}

function formatAudio(codec, channels) {
    if (!codec) return "-";
    const label = codec.toUpperCase();
    const ch = formatChannels(channels);
    return ch ? label + " " + ch : label;
}

const HDR_LABELS = { hdr10: "HDR10", "hdr10+": "HDR10+", dolby_vision: "Dolby Vision", hlg: "HLG" };
function hdrLabel(type) { return HDR_LABELS[type] || ""; }

function ensureFilesLayout() {
    const content = document.getElementById("storage-content");
    if (content.querySelector("#files-filter-bar")) return;
    content.innerHTML = renderFilters() + '<div id="files-results"></div>';
}

function updateFilterSelects() {
    const sel = document.getElementById("storage-lib-select");
    if (sel) sel.innerHTML = renderLibraryOptions();
    const codecSel = document.getElementById("files-codec-filter");
    const resSel = document.getElementById("files-resolution-filter");
    const containerSel = document.getElementById("files-container-filter");
    if (codecSel) codecSel.value = filesCodecFilter || "";
    if (resSel) resSel.value = filesResolutionFilter || "";
    if (containerSel) containerSel.value = filesContainerFilter || "";
}

async function loadFiles() {
    const content = document.getElementById("storage-content");
    if (!currentLibrary) {
        content.innerHTML = "";
        return;
    }

    ensureFilesLayout();
    updateFilterSelects();
    const results = document.getElementById("files-results");
    const gen = ++filesGeneration;

    const params = new URLSearchParams();
    params.set("library", currentLibrary);
    params.set("limit", filesPageSize);
    params.set("offset", filesPage * filesPageSize);
    params.set("sort_by", filesSortBy);
    params.set("sort_dir", filesSortDir);
    if (filesCodecFilter) params.set("codec", filesCodecFilter);
    if (filesResolutionFilter) params.set("resolution", filesResolutionFilter);
    if (filesContainerFilter) params.set("container", filesContainerFilter);
    if (filesSearch) params.set("search", filesSearch);
    if (filesStatusFilter) params.set("status", filesStatusFilter);

    let data;
    try {
        data = await api("GET", `/api/storage/files?${params}`);
    } catch (e) {
        if (gen === filesGeneration) results.innerHTML = `<p class="section-empty">${esc(e.message)}</p>`;
        return;
    }
    if (gen !== filesGeneration) return;

    filesTotal = data.total;

    // The empty state renders without pagination, so a page past the end would have no way back
    if (!data.files.length && filesTotal > 0 && filesPage > 0) {
        filesPage = Math.ceil(filesTotal / filesPageSize) - 1;
        loadFiles();
        return;
    }

    // The status filter can only be cleared from the header
    const filtersActive = !!(filesCodecFilter || filesResolutionFilter || filesContainerFilter || filesSearch || filesStatusFilter);
    if (!data.files.length && !filtersActive) {
        results.innerHTML = '<p class="section-empty">No files found.</p>';
        return;
    }

    let html = `<table class="overview-table storage-table files-table" id="files-table"><thead><tr>
        <th class="storage-check-col"><input type="checkbox" id="files-select-all" data-tooltip="Select all"></th>
        <th class="sortable" data-sort="file_path">File${sortArrow("file_path")}</th>
        <th class="sortable" style="width:76px" data-sort="file_size">Size${sortArrow("file_size")}</th>
        <th class="sortable" style="width:96px" data-sort="duration">Duration${sortArrow("duration")}</th>
        <th class="sortable" style="width:92px" data-sort="bitrate_kbps">Bitrate${sortArrow("bitrate_kbps")}</th>
        <th class="sortable" style="width:68px" data-sort="video_codec">Codec${sortArrow("video_codec")}</th>
        <th class="sortable" style="width:64px" data-sort="resolution_h">Res${sortArrow("resolution_h")}</th>
        <th class="sortable" style="width:92px" data-sort="audio_codec">Audio${sortArrow("audio_codec")}</th>
        <th class="sortable" style="width:100px" data-sort="container">Container${sortArrow("container")}</th>
        <th class="sortable" style="width:100px" data-sort="hdr_type">HDR${sortArrow("hdr_type")}</th>
        <th id="files-status-th" style="width:116px">${filesStatusFilter ? filesStatusFilter.charAt(0).toUpperCase() + filesStatusFilter.slice(1) : "Status"}</th>
    </tr></thead><tbody>`;

    data.files.forEach((f, i) => {
        const codec = f.video_codec ? codecLabel(f.video_codec) : "-";
        const res = f.resolution_h ? f.resolution_h + "p" : "-";
        const status = f.processed ? '<span class="status-processed">Processed</span>' : "";
        html += `<tr class="storage-row${i % 2 ? " stripe" : ""}" data-tooltip="${escAttr(f.file_path)}">
            <td><input type="checkbox" class="files-check" data-path="${escAttr(f.file_path)}"${filesSelected.has(f.file_path) ? " checked" : ""}></td>
            <td>${esc(f.file_path.split("/").pop())}</td>
            <td>${formatSize(f.file_size)}</td>
            <td>${formatFileDuration(f.duration)}</td>
            <td>${formatBitrate(f.bitrate_kbps)}</td>
            <td>${esc(codec)}</td>
            <td>${esc(res)}</td>
            <td>${esc(formatAudio(f.audio_codec, f.audio_channels))}</td>
            <td>${esc(f.container ? f.container.toUpperCase() : "-")}</td>
            <td>${esc(hdrLabel(f.hdr_type)) || "-"}</td>
            <td>${status}</td>
        </tr>`;
    });
    html += "</tbody></table>";

    if (!data.files.length) {
        html += '<p class="section-empty">No results.</p>';
        results.innerHTML = html;
        return;
    }

    // Pagination
    const totalPages = Math.max(1, Math.ceil(filesTotal / filesPageSize));
    const hasPrev = filesPage > 0;
    const hasNext = filesPage < totalPages - 1;
    const sizeOptions = FILES_PAGE_SIZES.map(n =>
        `<option value="${n}"${n === filesPageSize ? " selected" : ""}>${n}</option>`
    ).join("");
    html += `<div class="pagination">
        <span class="number-wrap">
            <button class="number-btn" type="button" id="files-prev" ${hasPrev ? "" : "disabled"}><img src="arrow-left.svg" alt="Previous"></button>
            <input type="number" id="files-page" class="page-input" value="${filesPage + 1}" min="1" max="${totalPages}">
            <button class="number-btn" type="button" id="files-next" ${hasNext ? "" : "disabled"}><img src="arrow-right.svg" alt="Next"></button>
        </span>
        <select id="files-page-size">${sizeOptions}</select>
    </div>`;

    results.innerHTML = html;
    updateQueueBtn("files-check", "btn-queue-files", "files-select-all");
}

async function loadFileFilters() {
    if (!currentLibrary) {
        filesFilters = { codecs: [], containers: [] };
        return;
    }
    try {
        filesFilters = await api("GET", `/api/storage/files/filters?library=${encodeURIComponent(currentLibrary)}`);
    } catch {
        filesFilters = { codecs: [], containers: [] };
    }
}

function resetFilesState() {
    filesPage = 0;
    filesCodecFilter = null;
    filesResolutionFilter = null;
    filesContainerFilter = null;
    filesStatusFilter = null;
    filesSearch = "";
}

function setForCheck(checkClass) {
    return checkClass === "tree-check" ? treeSelected : filesSelected;
}

function selectionTooltip(selected) {
    if (!selected.size) return "";
    const paths = Array.from(selected);
    const MAX = 20;
    const names = paths.slice(0, MAX).map(p => esc(p.split("/").pop()));
    let tip = names.join("<br>");
    if (paths.length > MAX) tip += `<br>and ${paths.length - MAX} more`;
    return tip;
}

function updateQueueBtn(checkClass, btnId, selectAllId) {
    const selected = setForCheck(checkClass);
    const btn = document.getElementById(btnId);
    if (btn) {
        btn.disabled = selected.size === 0;
        btn.textContent = selected.size > 0 ? `Queue Selected (${selected.size})` : "Queue Selected";
        if (selected.size) btn.setAttribute("data-tooltip", selectionTooltip(selected));
        else btn.removeAttribute("data-tooltip");
    }
    const checks = document.querySelectorAll(`.${checkClass}`);
    const all = document.getElementById(selectAllId);
    if (all) all.checked = checks.length > 0 && Array.from(checks).every(c => c.checked);
}

async function showQueueConfirm(checkClass, btnId, selectAllId) {
    const selected = setForCheck(checkClass);
    const paths = Array.from(selected);
    if (!paths.length || !currentLibrary) return;

    let filePaths;
    try {
        filePaths = await api("POST", "/api/queue/resolve-paths", { library: currentLibrary, paths });
    } catch (err) {
        alert(err.message);
        return;
    }
    if (!filePaths.length) return;

    const groups = new Map();
    for (const fp of filePaths) {
        const slash = fp.lastIndexOf("/");
        const dir = slash > 0 ? fp.substring(0, slash) : "";
        if (!groups.has(dir)) groups.set(dir, []);
        groups.get(dir).push(fp);
    }

    const dirs = Array.from(groups.keys());
    let prefix = dirs[0];
    for (let i = 1; i < dirs.length; i++) {
        while (prefix && dirs[i] !== prefix && !dirs[i].startsWith(prefix + "/")) {
            prefix = prefix.substring(0, prefix.lastIndexOf("/"));
        }
    }

    const sortedDirs = dirs.sort();
    let rowIdx = 0;
    let bodyHtml = "";
    for (const dir of sortedDirs) {
        const files = groups.get(dir).sort();
        const label = (dir === prefix ? dir.split("/").pop() : dir.substring(prefix.length + 1)) + "/";
        bodyHtml += `<tr class="queue-confirm-dir"><td><img class="storage-icon" src="folder.svg" alt="">${esc(label)}</td></tr>`;
        for (const fp of files) {
            const name = fp.substring(fp.lastIndexOf("/") + 1);
            bodyHtml += `<tr${rowIdx++ % 2 ? ' class="stripe"' : ''}><td class="queue-confirm-file" data-tooltip="${escAttr(fp)}"><img class="storage-icon" src="file-earmark.svg" alt="">${esc(name)}</td></tr>`;
        }
    }

    const overlay = document.createElement("div");
    overlay.className = "preview-overlay";
    overlay.innerHTML = `
        <div class="preview-modal queue-confirm-modal">
            <div class="preview-header">
                <span class="preview-title">Queue ${filePaths.length} file${filePaths.length > 1 ? "s" : ""} from ${esc(currentLibrary)}</span>
                <button class="btn-icon queue-confirm-close" data-tooltip="Close"><img src="close.svg" alt="Close"></button>
            </div>
            <div class="preview-body">
                <table class="overview-table"><tbody>${bodyHtml}</tbody></table>
            </div>
            <div class="preview-footer">
                <button class="btn queue-confirm-close" style="margin-right:8px">Cancel</button>
                <button class="btn btn-primary" id="queue-confirm-send">Send to queue</button>
            </div>
        </div>`;

    document.body.appendChild(overlay);
    const modal = overlay.querySelector(".preview-modal");

    function close() {
        overlay.remove();
        document.removeEventListener("keydown", onKey);
    }

    function onKey(e) {
        if (e.key === "Escape") close();
    }
    document.addEventListener("keydown", onKey);

    overlay.addEventListener("click", e => {
        if (e.target === overlay) {
            modal.classList.add("flash");
            setTimeout(() => modal.classList.remove("flash"), 150);
        }
    });
    overlay.querySelectorAll(".queue-confirm-close").forEach(b => b.addEventListener("click", close));

    overlay.querySelector("#queue-confirm-send").addEventListener("click", async () => {
        const sendBtn = overlay.querySelector("#queue-confirm-send");
        sendBtn.disabled = true;
        sendBtn.textContent = "Queuing...";
        try {
            const result = await api("POST", "/api/queue/enqueue-paths", { library: currentLibrary, paths });
            selected.clear();
            document.querySelectorAll(`.${checkClass}`).forEach(c => { c.checked = false; });
            const all = document.getElementById(selectAllId);
            if (all) all.checked = false;
            updateQueueBtn(checkClass, btnId, selectAllId);
            close();
            const btn = document.getElementById(btnId);
            if (result.queued > 0 && result.skipped > 0) {
                btn.textContent = `Queued ${result.queued}, ${result.skipped} skipped`;
            } else if (result.queued > 0) {
                btn.textContent = `Queued ${result.queued}`;
            } else {
                btn.textContent = `${result.skipped} skipped`;
            }
            setTimeout(() => { btn.textContent = "Queue Selected"; btn.disabled = true; }, 4000);
        } catch (err) {
            alert(err.message);
            sendBtn.disabled = false;
            sendBtn.textContent = "Send to queue";
        }
    });
}

async function queueSelected(checkClass, btnId, selectAllId) {
    const selected = setForCheck(checkClass);
    const paths = Array.from(selected);
    if (!paths.length || !currentLibrary) return;
    const btn = document.getElementById(btnId);
    btn.disabled = true;
    btn.textContent = "Queuing...";
    try {
        const result = await api("POST", "/api/queue/enqueue-paths", { library: currentLibrary, paths });
        selected.clear();
        document.querySelectorAll(`.${checkClass}`).forEach(c => { c.checked = false; });
        const all = document.getElementById(selectAllId);
        if (all) all.checked = false;
        if (result.queued > 0 && result.skipped > 0) {
            btn.textContent = `Queued ${result.queued}, ${result.skipped} skipped`;
        } else if (result.queued > 0) {
            btn.textContent = `Queued ${result.queued}`;
        } else {
            btn.textContent = `${result.skipped} skipped`;
        }
        setTimeout(() => { btn.textContent = "Queue Selected"; btn.disabled = true; }, 4000);
    } catch (err) {
        alert(err.message);
        btn.textContent = "Queue Selected";
        updateQueueBtn(checkClass, btnId, selectAllId);
    }
}

function loadTab() {
    if (activeTab === "tree") loadTree();
    else if (activeTab === "files") loadFiles();
    else if (activeTab === "dupes") loadDuplicates();
}

// Duplicates tab

function renderDupControls() {
    return `<div class="storage-filters" id="dup-controls">
        <select id="storage-lib-select">${renderLibraryOptions(true)}</select>
        <button class="btn btn-primary" id="btn-dup-scan"${dupScanning ? " disabled" : ""}>Scan for Duplicates</button>
    </div>`;
}

function ensureDupLayout() {
    const content = document.getElementById("storage-content");
    if (content.querySelector("#dup-controls")) return;
    content.innerHTML = `${renderDupControls()}<div id="dup-results"></div>`;
}

async function loadDuplicates() {
    if (!dupScanning) {
        try {
            const s = await api("GET", "/api/settings");
            dupAllowDeletion = !!s.allow_duplicate_deletion;
        } catch {}
        if (activeTab !== "dupes") return;
    }
    ensureDupLayout();
    const sel = document.getElementById("storage-lib-select");
    sel.innerHTML = renderLibraryOptions(true);
    document.getElementById("btn-dup-scan").disabled = dupScanning;
    const results = document.getElementById("dup-results");
    if (dupScanning) {
        results.innerHTML = `<div class="dup-scan-status">
            <p>Scanning for duplicates...</p>
            <div class="dup-progress"><div class="dup-progress-bar" id="dup-progress-bar"></div></div>
            <p class="dup-progress-text" id="dup-progress-text"></p>
            <button class="btn" id="btn-dup-cancel">Stop Scanning</button>
        </div>`;
        return;
    }
    if (dupGroups === null) {
        results.innerHTML = "";
        return;
    }
    results.innerHTML = renderDuplicateResults();
}

function renderDuplicateResults() {
    const notHashed = dupNotHashed > 0 ? `<span>${dupNotHashed} files not hashed</span>` : "";
    if (!dupGroups.length) {
        return `<div class="dup-summary"><span>No duplicates found.</span>${notHashed}</div>`;
    }
    let html = `<div class="dup-summary">
        <span>${dupGroups.length} duplicate group${dupGroups.length === 1 ? "" : "s"}</span>
        <span>${formatSize(dupTotalSize)} in extra copies</span>
        ${notHashed}
    </div>`;

    dupGroups.forEach((group, gi) => {
        const f0 = group.files[0];
        const codec = f0.video_codec ? codecLabel(f0.video_codec) : "";
        const res = f0.resolution_h ? f0.resolution_h + "p" : "";
        const container = f0.container ? f0.container.toUpperCase() : "";
        const meta = [formatSize(group.file_size), codec, res, container].filter(Boolean).join(", ");
        html += `<div class="dup-group">
            <div class="dup-group-header">
                <span>${group.files.length} copies</span>
                <span class="dup-group-meta">${esc(meta)}</span>
            </div>
            <table class="overview-table dup-table"><thead><tr>
                <th>Path</th>
                <th>Library</th>
            </tr></thead><tbody>`;
        group.files.forEach((f, fi) => {
            const delIcon = dupAllowDeletion
                ? `<button class="btn-icon dup-delete" data-fp="${escAttr(f.file_path)}" data-lib="${escAttr(f.library_name)}" data-gi="${gi}" data-tooltip="Delete file"><img src="trash.svg" alt="Delete"></button>`
                : "";
            html += `<tr class="${fi % 2 ? "stripe" : ""}" data-tooltip="${escAttr(f.file_path)}">
                <td>${esc(f.file_path)}</td>
                <td>${esc(f.library_name)}${delIcon}</td>
            </tr>`;
        });
        html += "</tbody></table></div>";
    });

    return html;
}

async function startDupScan() {
    dupScanning = true;
    dupGroups = null;
    loadDuplicates();
    const lib = currentLibrary || "";
    const url = lib ? `/api/storage/duplicates/scan?library=${encodeURIComponent(lib)}` : "/api/storage/duplicates/scan";
    try {
        const result = await api("POST", url);
        dupGroups = result.groups;
        dupTotalSize = result.total_duplicate_size;
        dupNotHashed = result.not_hashed;
    } catch (e) {
        dupGroups = null;
        alert(e.message);
    } finally {
        dupScanning = false;
        if (activeTab === "dupes") loadDuplicates();
    }
}

export function onDupScanProgress(data) {
    const bar = document.getElementById("dup-progress-bar");
    const text = document.getElementById("dup-progress-text");
    if (!bar || !text) return;
    const pct = data.total > 0 ? Math.round((data.hashed / data.total) * 100) : 0;
    bar.style.width = pct + "%";
    text.textContent = `Hashed ${data.hashed} of ${data.total} files`;
}

export function initStorage() {
    document.getElementById("storage-header").addEventListener("click", e => {
        const tab = e.target.closest("[data-stab]");
        if (tab) {
            activeTab = tab.dataset.stab;
            if (activeTab !== "dupes" && !currentLibrary && libraries.length) {
                currentLibrary = libraries[0].name;
                dupGroups = null;
            }
            currentPath = singleRootPath();
            treeSearch = "";
            document.querySelectorAll("#storage-header .settings-tab").forEach(b => b.classList.toggle("active", b === tab));
            loadTab();
        }
    });

    const content = document.getElementById("storage-content");

    content.addEventListener("change", e => {
        if (e.target.id === "storage-lib-select") {
            currentLibrary = e.target.value || null;
            currentPath = singleRootPath();
            treeSearch = "";
            treeData = null;
            resetFilesState();
            treeSelected.clear();
            filesSelected.clear();
            dupGroups = null;
            content.innerHTML = "";
            loadFileFilters().then(() => loadTab());
        } else if (e.target.id === "files-codec-filter") {
            filesCodecFilter = e.target.value || null;
            filesPage = 0;
            loadFiles();
        } else if (e.target.id === "files-resolution-filter") {
            filesResolutionFilter = e.target.value || null;
            filesPage = 0;
            loadFiles();
        } else if (e.target.id === "files-container-filter") {
            filesContainerFilter = e.target.value || null;
            filesPage = 0;
            loadFiles();
        } else if (e.target.id === "files-page-size") {
            filesPageSize = parseInt(e.target.value);
            filesPage = 0;
            loadFiles();
        }
    });

    content.addEventListener("click", async e => {
        // Duplicates tab buttons
        if (e.target.id === "btn-dup-scan" || e.target.closest("#btn-dup-scan")) {
            startDupScan();
            return;
        }
        if (e.target.id === "btn-dup-cancel" || e.target.closest("#btn-dup-cancel")) {
            api("POST", "/api/storage/duplicates/cancel").catch(() => {});
            return;
        }
        const delBtn = e.target.closest(".dup-delete");
        if (delBtn) {
            const fp = delBtn.dataset.fp;
            const lib = delBtn.dataset.lib;
            const gi = parseInt(delBtn.dataset.gi);
            if (!confirm(`Permanently delete this file?\n\n${fp}`)) return;
            try {
                await api("DELETE", `/api/storage/duplicates/file?file_path=${encodeURIComponent(fp)}&library_name=${encodeURIComponent(lib)}`);
                if (dupGroups && dupGroups[gi]) {
                    dupGroups[gi].files = dupGroups[gi].files.filter(f => !(f.file_path === fp && f.library_name === lib));
                    dupTotalSize -= dupGroups[gi].file_size;
                    if (dupGroups[gi].files.length < 2) dupGroups.splice(gi, 1);
                    loadDuplicates();
                }
            } catch (err) {
                alert(err.message);
            }
            return;
        }

        // Queue buttons
        if (e.target.id === "btn-queue-tree" || e.target.closest("#btn-queue-tree")) {
            showQueueConfirm("tree-check", "btn-queue-tree", "tree-select-all");
            return;
        }
        if (e.target.id === "btn-queue-files" || e.target.closest("#btn-queue-files")) {
            queueSelected("files-check", "btn-queue-files", "files-select-all");
            return;
        }

        // Checkboxes
        const checkCell = e.target.closest("td, th");
        const checkInput = e.target.type === "checkbox" ? e.target
            : checkCell?.querySelector("input[type=checkbox]");
        if (checkInput) {
            if (e.target.type !== "checkbox") checkInput.checked = !checkInput.checked;
            if (checkInput.id === "tree-select-all") {
                if (!checkInput.checked) treeSelected.clear();
                document.querySelectorAll(".tree-check").forEach(c => {
                    c.checked = checkInput.checked;
                    if (c.checked) treeSelected.add(c.dataset.path);
                });
                updateQueueBtn("tree-check", "btn-queue-tree", "tree-select-all");
            } else if (checkInput.classList.contains("tree-check")) {
                if (checkInput.checked) treeSelected.add(checkInput.dataset.path); else treeSelected.delete(checkInput.dataset.path);
                updateQueueBtn("tree-check", "btn-queue-tree", "tree-select-all");
            } else if (checkInput.id === "files-select-all") {
                if (!checkInput.checked) filesSelected.clear();
                document.querySelectorAll(".files-check").forEach(c => {
                    c.checked = checkInput.checked;
                    if (c.checked) filesSelected.add(c.dataset.path);
                });
                updateQueueBtn("files-check", "btn-queue-files", "files-select-all");
            } else if (checkInput.classList.contains("files-check")) {
                if (checkInput.checked) filesSelected.add(checkInput.dataset.path); else filesSelected.delete(checkInput.dataset.path);
                updateQueueBtn("files-check", "btn-queue-files", "files-select-all");
            }
            return;
        }

        const crumb = e.target.closest(".storage-crumb");
        if (crumb) {
            const path = crumb.dataset.path;
            currentPath = path || null;
            treeSearch = "";
            loadTree();
            return;
        }
        const dirLink = e.target.closest("a.dir-link");
        if (dirLink) {
            currentPath = dirLink.dataset.dir;
            treeSearch = "";
            loadTree();
            return;
        }

        // Status filter dropdown
        const statusTh = e.target.closest("#files-status-th");
        if (statusTh && !e.target.closest(".status-dropdown")) {
            const existing = statusTh.querySelector(".status-dropdown");
            if (existing) { existing.remove(); return; }
            const dd = document.createElement("div");
            dd.className = "status-dropdown";
            const options = [null, "processed", "unprocessed"];
            const labels = ["All", "Processed", "Unprocessed"];
            options.forEach((val, i) => {
                const btn = document.createElement("button");
                btn.textContent = labels[i];
                if (filesStatusFilter === val) btn.classList.add("active");
                btn.addEventListener("click", ev => {
                    ev.stopPropagation();
                    filesStatusFilter = val;
                    filesPage = 0;
                    dd.remove();
                    loadFiles();
                });
                dd.appendChild(btn);
            });
            statusTh.appendChild(dd);
            const close = ev => {
                if (!dd.contains(ev.target) && ev.target !== statusTh) {
                    dd.remove();
                    document.removeEventListener("click", close);
                }
            };
            setTimeout(() => document.addEventListener("click", close), 0);
            return;
        }

        const th = e.target.closest("th.sortable");
        if (th && activeTab === "tree" && th.dataset.treesort) {
            const col = th.dataset.treesort;
            if (treeSortBy === col) {
                if (treeSortDir === "asc") {
                    treeSortDir = "desc";
                } else if (col === "total_size") {
                    treeSortDir = "asc";
                } else {
                    treeSortBy = "total_size";
                    treeSortDir = "desc";
                }
            } else {
                treeSortBy = col;
                treeSortDir = col === "total_size" ? "desc" : "asc";
            }
            loadTree(false);
            return;
        }
        if (th && activeTab === "files" && th.dataset.sort) {
            const col = th.dataset.sort;
            if (filesSortBy === col) {
                if (filesSortDir === "asc") {
                    filesSortDir = "desc";
                } else if (col === "file_size") {
                    filesSortDir = "asc";
                } else {
                    filesSortBy = "file_size";
                    filesSortDir = "desc";
                }
            } else {
                filesSortBy = col;
                filesSortDir = col === "file_size" ? "desc" : "asc";
            }
            filesPage = 0;
            loadFiles();
            return;
        }

        if (e.target.closest("#files-prev")) {
            filesPage--;
            loadFiles();
            return;
        }
        if (e.target.closest("#files-next")) {
            filesPage++;
            loadFiles();
        }
    });

    content.addEventListener("input", e => {
        if (e.target.id === "tree-search") {
            clearTimeout(treeSearchTimer);
            treeSearchTimer = setTimeout(() => {
                treeSearch = e.target.value.trim();
                loadTree(false);
            }, 300);
        }
        if (e.target.id === "files-search") {
            clearTimeout(filesSearchTimer);
            filesSearchTimer = setTimeout(() => {
                filesSearch = e.target.value.trim();
                filesPage = 0;
                loadFiles();
            }, 300);
        }
    });

    content.addEventListener("keydown", e => {
        if (e.target.id === "files-page" && e.key === "Enter") {
            const val = parseInt(e.target.value);
            if (!isNaN(val) && val >= 1) {
                filesPage = val - 1;
                loadFiles();
            }
        }
    });

    content.addEventListener("blur", e => {
        if (e.target.id === "files-page") {
            const val = parseInt(e.target.value);
            if (!isNaN(val) && val >= 1 && val - 1 !== filesPage) {
                filesPage = val - 1;
                loadFiles();
            } else {
                e.target.value = filesPage + 1;
            }
        }
    }, true);
}

export async function loadStorageView() {
    try {
        libraries = await api("GET", "/api/libraries");
    } catch {
        libraries = [];
    }
    if (!currentLibrary && libraries.length) currentLibrary = libraries[0].name;
    if (!currentPath) currentPath = singleRootPath();
    renderHeader();
    await loadFileFilters();
    loadTab();
}

export function onStorageSSE() {
    if (isVisible() && activeTab !== "dupes") loadTab();
}
