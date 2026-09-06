import { api, esc, escAttr } from "./helpers.js";

export function openDirBrowser(startPath, onSelect, opts = {}) {
    const multi = opts.multi || false;
    const existingPaths = new Set(opts.currentPaths || []);
    const selectedPaths = new Set();

    const overlay = document.createElement("div");
    overlay.className = "dir-browser-overlay";
    overlay.innerHTML = `
        <div class="dir-browser">
            <div class="dir-browser-header">
                <button class="btn-icon db-back" style="display:none" data-tooltip="Back"><img src="arrow-left.svg" alt="Back"></button>
                <span class="dir-browser-path"></span>
            </div>
            <div class="dir-browser-entries"></div>
            <div class="dir-browser-footer">
                <button class="btn db-cancel">${multi ? "Close" : "Cancel"}</button>
                <button class="btn btn-primary db-select" disabled>${multi ? "Add" : "Select"}</button>
            </div>
        </div>`;
    document.body.appendChild(overlay);

    const pathDisplay = overlay.querySelector(".dir-browser-path");
    const entriesContainer = overlay.querySelector(".dir-browser-entries");
    const selectBtn = overlay.querySelector(".db-select");
    const backBtn = overlay.querySelector(".db-back");
    let currentPath = null;
    let selectedPath = null;
    let isRoots = false;
    let rootEntryPath = null;

    function close() { overlay.remove(); document.removeEventListener("keydown", onKey); }

    function updateSelectBtn() {
        if (multi) {
            selectBtn.disabled = selectedPaths.size === 0;
            selectBtn.textContent = selectedPaths.size ? `Add (${selectedPaths.size})` : "Add";
        }
    }

    function entryHtml(name, path, detail) {
        const detailSpan = detail ? ` <span style="color:var(--text-muted);font-size:11px">${esc(detail)}</span>` : "";
        let cls = "dir-browser-entry";
        let check = "";
        if (multi) {
            if (existingPaths.has(path)) {
                cls += " already-added";
                check = '<input type="checkbox" class="entry-check" checked disabled>';
            } else {
                check = `<input type="checkbox" class="entry-check"${selectedPaths.has(path) ? " checked" : ""}>`;
            }
        }
        return `<div class="${cls}" data-path="${escAttr(path)}">
            ${check}<span class="dir-browser-entry-name">${esc(name)}${detailSpan}</span>
            <span class="entry-nav"><img src="arrow-right.svg" alt="Open"></span>
        </div>`;
    }

    async function showRoots() {
        isRoots = true;
        currentPath = null;
        rootEntryPath = null;
        if (!multi) { selectedPath = null; selectBtn.disabled = true; }
        pathDisplay.textContent = "Volumes";
        backBtn.style.display = "none";
        try {
            const roots = await api("GET", "/api/filesystem/roots");
            if (!roots.length) {
                entriesContainer.innerHTML = '<div class="dir-browser-empty">No volumes found.<br><br>Undarr needs access to your media files through Docker volume mounts. Add them to <code>docker-compose.yml</code>:<br><br><code>- /mnt/media:/media</code><br><code>- /mnt/media/movies:/media/movies</code><br><code>- /mnt/media/shows:/media/shows</code><br><br>Then recreate the container.</div>';
                return;
            }
            entriesContainer.innerHTML = roots.map(r => entryHtml(r.name, r.path, r.path)).join("");
        } catch (e) {
            entriesContainer.innerHTML = `<div class="dir-browser-empty">${esc(e.message)}</div>`;
        }
    }

    async function browse(path) {
        isRoots = false;
        currentPath = path;
        if (!multi) { selectedPath = null; selectBtn.disabled = true; }
        pathDisplay.textContent = path;
        backBtn.style.display = "";
        try {
            const data = await api("GET", `/api/filesystem/browse?path=${encodeURIComponent(path)}`);
            if (!data.entries.length) {
                entriesContainer.innerHTML = '<div class="dir-browser-empty">No subdirectories</div>';
                if (!multi) { selectedPath = path; selectBtn.disabled = false; }
                else if (!existingPaths.has(path)) { selectedPaths.add(path); updateSelectBtn(); }
                return;
            }
            entriesContainer.innerHTML = data.entries.map(e => entryHtml(e.name, e.path)).join("");
        } catch (e) {
            entriesContainer.innerHTML = `<div class="dir-browser-empty">${esc(e.message)}</div>`;
        }
    }

    function navigateInto(path) {
        if (isRoots) rootEntryPath = path;
        browse(path);
    }

    entriesContainer.addEventListener("click", (e) => {
        if (e.target.closest(".entry-nav")) {
            const entry = e.target.closest(".dir-browser-entry");
            if (entry) navigateInto(entry.dataset.path);
            return;
        }

        const entry = e.target.closest(".dir-browser-entry");
        if (!entry) return;
        const path = entry.dataset.path;

        if (multi) {
            if (e.target.type !== "checkbox") { navigateInto(path); return; }
            if (e.target.disabled) return;
            if (e.target.checked) selectedPaths.add(path); else selectedPaths.delete(path);
            updateSelectBtn();
        } else {
            if (entry.classList.contains("selected")) {
                navigateInto(path);
                return;
            }
            entriesContainer.querySelectorAll(".dir-browser-entry").forEach(el => el.classList.remove("selected"));
            entry.classList.add("selected");
            selectedPath = path;
            selectBtn.disabled = false;
        }
    });

    backBtn.addEventListener("click", () => {
        if (isRoots) return;
        if (!currentPath || currentPath === rootEntryPath) {
            showRoots();
        } else {
            const parent = currentPath.replace(/\/[^/]+\/?$/, "") || "/";
            browse(parent);
        }
    });

    selectBtn.addEventListener("click", () => {
        if (multi) {
            selectedPaths.forEach(p => onSelect(p));
            close();
        } else {
            if (selectedPath) { onSelect(selectedPath); close(); }
        }
    });

    overlay.querySelector(".db-cancel").addEventListener("click", close);
    const browser = overlay.querySelector(".dir-browser");
    overlay.addEventListener("click", (e) => {
        if (e.target === overlay) {
            browser.classList.add("flash");
            setTimeout(() => browser.classList.remove("flash"), 300);
        }
    });
    function onKey(e) {
        if (e.key === "Escape") close();
    }
    document.addEventListener("keydown", onKey);

    if (startPath) browse(startPath); else showRoots();
}
