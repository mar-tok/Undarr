import { api, formatBytes, basename, esc, escAttr, formatDate } from "./helpers.js";

const PAGE_SIZES = [25, 50, 100, 200];
let pageSize = 25;
let searchQuery = "";
let searchPage = 0;
let sortBy = "finished_at";
let sortDir = "desc";
let statusFilter = null;
let searchTimer = null;
let lastResults = [];
let lastTotal = 0;

function sizeLabel(r) {
    if (r.source === "history" && r.new_size_bytes != null) {
        return formatBytes(r.old_size_bytes) + " \u2192 " + formatBytes(r.new_size_bytes);
    }
    return formatBytes(r.old_size_bytes);
}

function setSearchActive(active) {
    const results = document.getElementById("search-results");
    const panes = document.querySelectorAll("#view-queue .queue-pane");
    const tabs = document.querySelectorAll("#queue-tabs .settings-tab");

    if (active) {
        panes.forEach(p => p.style.display = "none");
        tabs.forEach(t => t.classList.add("dimmed"));
        results.style.display = "";
    } else {
        results.style.display = "none";
        tabs.forEach(t => t.classList.remove("dimmed"));
        panes.forEach(p => p.style.display = "");
    }
}

function updateSortHeaders() {
    document.querySelectorAll("#search-table th.sortable").forEach(th => {
        const existing = th.querySelector(".sort-arrow");
        if (existing) existing.remove();
        if (th.dataset.sort === sortBy) {
            const arrow = document.createElement("span");
            arrow.className = "sort-arrow";
            arrow.textContent = sortDir === "asc" ? "\u25B2" : "\u25BC";
            th.appendChild(arrow);
        }
    });
    const statusTh = document.getElementById("search-status-th");
    statusTh.textContent = statusFilter
        ? statusFilter.charAt(0).toUpperCase() + statusFilter.slice(1)
        : "Status";
}

async function doSearch() {
    if (searchQuery.length < 2) {
        lastResults = [];
        lastTotal = 0;
        setSearchActive(false);
        render();
        return;
    }
    setSearchActive(true);
    const params = new URLSearchParams({
        q: searchQuery,
        limit: pageSize,
        offset: searchPage * pageSize,
        sort_by: sortBy,
        sort_dir: sortDir,
    });
    if (statusFilter) params.set("status", statusFilter);
    const data = await api("GET", `/api/search?${params}`);
    lastResults = data.results;
    lastTotal = data.total;
    render();
}

function render() {
    const table = document.getElementById("search-table");
    const tbody = document.getElementById("search-body");
    const empty = document.getElementById("search-empty");
    const pagEl = document.getElementById("search-pagination");

    const active = searchQuery.length >= 2;
    table.style.display = active ? "" : "none";
    empty.style.display = active && !lastResults.length ? "" : "none";

    if (!lastResults.length) {
        tbody.innerHTML = "";
        pagEl.innerHTML = "";
        updateSortHeaders();
        return;
    }
    updateSortHeaders();

    tbody.innerHTML = lastResults.map((r, i) =>
        `<tr class="${i % 2 ? "stripe" : ""}" data-tooltip="${escAttr(r.file_path)}">
            <td>${esc(basename(r.file_path))}</td>
            <td>${esc(r.library_name)}</td>
            <td>${sizeLabel(r)}</td>
            <td>${formatDate(r.date)}</td>
            <td class="status-${r.status.replace(/\s+/g, "-")}">${esc(r.status)}</td>
        </tr>`
    ).join("");

    const hasPrev = searchPage > 0;
    const hasNext = lastTotal > (searchPage + 1) * pageSize;
    const sizeOptions = PAGE_SIZES.map(n =>
        `<option value="${n}"${n === pageSize ? " selected" : ""}>${n}</option>`
    ).join("");
    pagEl.innerHTML = `
        <span class="number-wrap">
            <button class="number-btn" type="button" id="search-prev" ${hasPrev ? "" : "disabled"}><img src="arrow-left.svg" alt="Previous"></button>
            <input type="number" id="search-page" class="page-input" value="${searchPage + 1}" min="1">
            <button class="number-btn" type="button" id="search-next" ${hasNext ? "" : "disabled"}><img src="arrow-right.svg" alt="Next"></button>
        </span>
        <select id="search-page-size">${sizeOptions}</select>
    `;
    if (hasPrev) document.getElementById("search-prev").addEventListener("click", () => { searchPage--; doSearch(); });
    if (hasNext) document.getElementById("search-next").addEventListener("click", () => { searchPage++; doSearch(); });
    const pageInput = document.getElementById("search-page");
    function sizeIt() { pageInput.style.width = (String(pageInput.value).length + 1) + "ch"; }
    sizeIt();
    pageInput.addEventListener("input", sizeIt);
    pageInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter") {
            const val = parseInt(pageInput.value);
            if (!isNaN(val) && val >= 1) { searchPage = val - 1; doSearch(); }
        }
    });
    pageInput.addEventListener("blur", () => {
        const val = parseInt(pageInput.value);
        if (!isNaN(val) && val >= 1 && val - 1 !== searchPage) {
            searchPage = val - 1;
            doSearch();
        } else {
            pageInput.value = searchPage + 1;
        }
    });
    document.getElementById("search-page-size").addEventListener("change", (e) => {
        pageSize = parseInt(e.target.value);
        searchPage = 0;
        doSearch();
    });
}

export function clearSearch() {
    const input = document.getElementById("queue-search");
    if (input.value) {
        input.value = "";
        searchQuery = "";
        lastResults = [];
        lastTotal = 0;
        setSearchActive(false);
        render();
    }
}

export function initSearch() {
    document.getElementById("queue-search").addEventListener("input", (e) => {
        clearTimeout(searchTimer);
        searchTimer = setTimeout(() => {
            searchQuery = e.target.value.trim();
            searchPage = 0;
            doSearch();
        }, 300);
    });

    document.getElementById("search-status-th").addEventListener("click", (e) => {
        e.stopPropagation();
        const existing = document.querySelector(".status-dropdown");
        if (existing) { existing.remove(); return; }
        const th = document.getElementById("search-status-th");
        const dd = document.createElement("div");
        dd.className = "status-dropdown";
        const options = [null, "completed", "failed", "cancelled", "skipped", "skipped (rule)"];
        const labels = ["All", "Completed", "Failed", "Skipped (rule)"];
        options.forEach((val, i) => {
            const btn = document.createElement("button");
            btn.textContent = labels[i];
            if (statusFilter === val) btn.classList.add("active");
            btn.addEventListener("click", (ev) => {
                ev.stopPropagation();
                statusFilter = val;
                searchPage = 0;
                dd.remove();
                doSearch();
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

    document.querySelectorAll("#search-table th.sortable").forEach(th => {
        th.addEventListener("click", () => {
            const col = th.dataset.sort;
            if (sortBy === col) {
                if (sortDir === "asc") {
                    sortDir = "desc";
                } else if (col === "finished_at") {
                    sortDir = "asc";
                } else {
                    sortBy = "finished_at";
                    sortDir = "desc";
                }
            } else {
                sortBy = col;
                sortDir = col === "finished_at" ? "desc" : "asc";
            }
            searchPage = 0;
            doSearch();
        });
    });
}
