import { api, formatBytes, basename, esc, escAttr, formatDate } from "./helpers.js";

const PAGE_SIZES = [25, 50, 100, 200];
let pageSize = 25;
let searchQuery = "";
let searchPage = 0;
let sortBy = "finished_at";
let sortDir = "desc";
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
    const tabs = document.querySelectorAll("#queue-tabs .queue-tab");

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
            arrow.textContent = sortDir === "asc" ? " ▲" : " ▼";
            th.appendChild(arrow);
        }
    });
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
        `<option value="${n}"${n === pageSize ? " selected" : ""}>${n} / page</option>`
    ).join("");
    pagEl.innerHTML = `<button class="btn btn-sm" id="search-prev"${hasPrev ? "" : " disabled"}>Prev</button>
        <span class="hist-page-label">Page ${searchPage + 1}</span>
        <button class="btn btn-sm" id="search-next"${hasNext ? "" : " disabled"}>Next</button>
        <select id="search-page-size">${sizeOptions}</select>`;
    if (hasPrev) document.getElementById("search-prev").addEventListener("click", () => { searchPage--; doSearch(); });
    if (hasNext) document.getElementById("search-next").addEventListener("click", () => { searchPage++; doSearch(); });
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

    document.querySelectorAll("#search-table th.sortable").forEach(th => {
        th.addEventListener("click", () => {
            const col = th.dataset.sort;
            if (sortBy === col) {
                sortDir = sortDir === "asc" ? "desc" : "asc";
            } else {
                sortBy = col;
                sortDir = col === "finished_at" ? "desc" : "asc";
            }
            searchPage = 0;
            doSearch();
        });
    });
}
