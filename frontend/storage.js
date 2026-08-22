import { api, formatBytes, formatBytesLarge, esc, escAttr, codecLabel, codecColor, formatBitrate, formatFileDuration, formatChannels } from "./helpers.js";

let currentLibrary = null;
let currentPath = null;
let activeTab = "tree";
let libraries = [];

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
        </div>`;
}

function renderLibraryOptions() {
    let opts = libraries.map(l =>
        `<option value="${escAttr(l.name)}"${l.name === currentLibrary ? " selected" : ""}>${esc(l.name)}</option>`
    ).join("");
    if (!libraries.length) opts = '<option value="">No libraries</option>';
    return opts;
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

function renderFilters() {
    return `<div class="storage-filters" id="files-filter-bar">
        <select id="storage-lib-select">${renderLibraryOptions()}</select>
    </div>`;
}

function formatAudio(codec, channels) {
    if (!codec) return "-";
    const label = codec.toUpperCase();
    const ch = formatChannels(channels);
    return ch ? label + " " + ch : label;
}

function ensureFilesLayout() {
    const content = document.getElementById("storage-content");
    if (content.querySelector("#files-filter-bar")) return;
    content.innerHTML = renderFilters() + '<div id="files-results"></div>';
}

function updateFilterSelects() {
    const sel = document.getElementById("storage-lib-select");
    if (sel) sel.innerHTML = renderLibraryOptions();
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

    if (!data.files.length) {
        results.innerHTML = '<p class="section-empty">No files found.</p>';
        return;
    }

    let html = `<table class="overview-table storage-table files-table" id="files-table"><thead><tr>
        <th class="sortable" style="width:35%" data-sort="file_path">File${sortArrow("file_path")}</th>
        <th class="sortable" style="width:7%" data-sort="file_size">Size${sortArrow("file_size")}</th>
        <th class="sortable" style="width:7%" data-sort="duration">Duration${sortArrow("duration")}</th>
        <th class="sortable" style="width:8%" data-sort="bitrate_kbps">Bitrate${sortArrow("bitrate_kbps")}</th>
        <th class="sortable" style="width:7%" data-sort="video_codec">Codec${sortArrow("video_codec")}</th>
        <th class="sortable" style="width:7%" data-sort="resolution_h">Res${sortArrow("resolution_h")}</th>
        <th class="sortable" style="width:10%" data-sort="audio_codec">Audio${sortArrow("audio_codec")}</th>
        <th class="sortable" style="width:7%" data-sort="container">Container${sortArrow("container")}</th>
        <th style="width:9%">Status</th>
    </tr></thead><tbody>`;

    data.files.forEach((f, i) => {
        const codec = f.video_codec ? codecLabel(f.video_codec) : "-";
        const res = f.resolution_h ? f.resolution_h + "p" : "-";
        const status = f.processed ? '<span class="status-processed">Processed</span>' : "";
        html += `<tr class="storage-row${i % 2 ? " stripe" : ""}" data-tooltip="${escAttr(f.file_path)}">
            <td>${esc(f.file_path.split("/").pop())}</td>
            <td>${formatSize(f.file_size)}</td>
            <td>${formatFileDuration(f.duration)}</td>
            <td>${formatBitrate(f.bitrate_kbps)}</td>
            <td>${esc(codec)}</td>
            <td>${esc(res)}</td>
            <td>${esc(formatAudio(f.audio_codec, f.audio_channels))}</td>
            <td>${esc(f.container ? f.container.toUpperCase() : "-")}</td>
            <td>${status}</td>
        </tr>`;
    });
    html += "</tbody></table>";

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
}

function resetFilesState() {
    filesPage = 0;
}

function loadTab() {
    if (activeTab === "tree") loadTree();
    else if (activeTab === "files") loadFiles();
}

export function initStorage() {
    document.getElementById("storage-header").addEventListener("click", e => {
        const tab = e.target.closest("[data-stab]");
        if (tab) {
            activeTab = tab.dataset.stab;
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
            content.innerHTML = "";
            loadTab();
        } else if (e.target.id === "files-page-size") {
            filesPageSize = parseInt(e.target.value);
            filesPage = 0;
            loadFiles();
        }
    });

    content.addEventListener("click", e => {
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
    loadTab();
}

export function onStorageSSE() {
    if (isVisible()) loadTab();
}
