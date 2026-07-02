(function () {
    function esc(s) {
        if (s == null) return "";
        const d = document.createElement("div");
        d.textContent = String(s);
        return d.innerHTML;
    }

    function formatBytes(bytes) {
        if (bytes == null) return "-";
        if (bytes < 1024) return bytes + " B";
        if (bytes < 1048576) return Math.ceil(bytes / 1024) + " KB";
        if (bytes < 1073741824) return Math.ceil(bytes / 1048576) + " MB";
        return (bytes / 1073741824).toFixed(1) + " GB";
    }

    function basename(path) {
        return path.split(/[\\/]/).pop() || path;
    }

    function formatDate(iso) {
        if (!iso) return "-";
        const d = new Date(iso);
        if (isNaN(d)) return "-";
        const now = new Date();
        const pad = n => String(n).padStart(2, "0");
        const time = pad(d.getHours()) + ":" + pad(d.getMinutes());
        const sameYear = d.getFullYear() === now.getFullYear();
        const date = pad(d.getDate()) + "/" + pad(d.getMonth() + 1);
        return sameYear ? date + " " + time : date + "/" + d.getFullYear() + " " + time;
    }

    function formatDuration(secs) {
        if (secs == null || secs < 0) return "-";
        const h = Math.floor(secs / 3600);
        const m = Math.floor((secs % 3600) / 60);
        const s = Math.floor(secs % 60);
        if (h > 0) return h + "h " + m + "m " + s + "s";
        if (m > 0) return m + "m " + s + "s";
        return s + "s";
    }

    function api(method, path, body) {
        const opts = { method, headers: {} };
        if (body !== undefined) {
            opts.headers["Content-Type"] = "application/json";
            opts.body = JSON.stringify(body);
        }
        return fetch(path, opts).then(async res => {
            if (res.status === 204) return null;
            if (!res.ok) {
                const data = await res.json().catch(() => null);
                throw new Error(data && data.detail ? data.detail : res.statusText);
            }
            return res.json();
        });
    }

    const navItems = document.querySelectorAll(".nav-item");
    const views = document.querySelectorAll(".view");

    function navigate(viewId) {
        navItems.forEach(n => n.classList.toggle("active", n.dataset.view === viewId));
        views.forEach(v => v.classList.toggle("active", v.id === "view-" + viewId));
        if (viewId === "presets") loadPresets();
        if (viewId === "libraries") loadLibraries();
        if (viewId === "settings") loadSettings();
    }

    navItems.forEach(n => n.addEventListener("click", () => { location.hash = n.dataset.view; }));
    window.addEventListener("hashchange", () => navigate(location.hash.slice(1) || "queue"));

    let activeJobs = [];
    let pendingJobs = [];
    let blockedJobs = [];
    let failedJobs = [];
    let paused = false;
    let eventSource = null;

    function renderQueue() {
        const table = document.getElementById("queue-table");
        const tbody = document.getElementById("queue-body");
        const emptyMsg = document.getElementById("queue-empty");
        const controls = document.getElementById("queue-controls");
        const countEl = document.getElementById("pending-count");

        const all = activeJobs.concat(pendingJobs);
        const hasJobs = all.length > 0;

        table.style.display = hasJobs ? "" : "none";
        emptyMsg.style.display = hasJobs ? "none" : "";
        controls.style.display = (hasJobs || paused) ? "" : "none";
        countEl.textContent = pendingJobs.length ? pendingJobs.length + " pending" : "";

        let html = "";
        for (const job of all) {
            const statusClass = "status-" + job.status;
            html += "<tr>"
                + "<td title=\"" + esc(job.file_path) + "\">" + esc(basename(job.file_path)) + "</td>"
                + "<td>" + esc(job.library_name || "") + "</td>"
                + "<td>" + formatBytes(job.old_size_bytes) + "</td>"
                + "<td class=\"" + statusClass + "\">" + esc(job.status) + "</td>"
                + "</tr>";
        }
        tbody.innerHTML = html;
    }

    function renderIssues() {
        const table = document.getElementById("issues-table");
        const tbody = document.getElementById("issues-body");
        const emptyMsg = document.getElementById("issues-empty");

        const all = blockedJobs.concat(failedJobs);
        const hasIssues = all.length > 0;
        table.style.display = hasIssues ? "" : "none";
        emptyMsg.style.display = hasIssues ? "none" : "";

        let html = "";
        for (const job of blockedJobs) {
            html += "<tr>"
                + "<td title=\"" + esc(job.file_path) + "\">" + esc(basename(job.file_path)) + "</td>"
                + "<td>" + esc(job.library_name || "") + "</td>"
                + "<td>" + formatBytes(job.old_size_bytes) + "</td>"
                + "<td class=\"status-blocked\">blocked</td>"
                + "<td>" + esc(job.block_reason || "") + "</td>"
                + "<td></td>"
                + "</tr>";
        }
        for (const job of failedJobs) {
            html += "<tr>"
                + "<td title=\"" + esc(job.file_path) + "\">" + esc(basename(job.file_path)) + "</td>"
                + "<td>" + esc(job.library_name || "") + "</td>"
                + "<td>" + formatBytes(job.old_size_bytes) + "</td>"
                + "<td class=\"status-failed\">failed</td>"
                + "<td>" + esc(job.error_message || "") + "</td>"
                + "<td class=\"issue-actions\">"
                + "<button class=\"btn btn-sm\" data-retry=\"" + esc(job.id) + "\">Retry</button>"
                + "<button class=\"btn btn-sm\" data-dismiss=\"" + esc(job.id) + "\">Dismiss</button>"
                + "</td>"
                + "</tr>";
        }
        tbody.innerHTML = html;
    }

    function updatePauseButton() {
        const btn = document.getElementById("btn-pause");
        btn.textContent = paused ? "Resume Queue" : "Pause Queue";
    }

    function connectSSE() {
        if (eventSource) eventSource.close();
        eventSource = new EventSource("/api/queue/events");

        eventSource.addEventListener("init", e => {
            const data = JSON.parse(e.data);
            activeJobs = data.active || [];
            pendingJobs = data.pending || [];
            blockedJobs = data.blocked || [];
            paused = data.paused || false;
            updatePauseButton();
            renderQueue();
            renderIssues();
        });

        eventSource.addEventListener("job_queued", e => {
            pendingJobs.push(JSON.parse(e.data));
            renderQueue();
        });

        eventSource.addEventListener("job_started", e => {
            const job = JSON.parse(e.data);
            pendingJobs = pendingJobs.filter(j => j.id !== job.id);
            activeJobs = activeJobs.filter(j => j.id !== job.id);
            activeJobs.push(job);
            renderQueue();
        });

        eventSource.addEventListener("job_finished", e => {
            const job = JSON.parse(e.data);
            activeJobs = activeJobs.filter(j => j.id !== job.id);
            blockedJobs = blockedJobs.filter(j => j.id !== job.id);
            if (job.status === "failed") {
                failedJobs.push(job);
            }
            renderQueue();
            renderIssues();
        });

        eventSource.addEventListener("job_blocked", e => {
            blockedJobs.push(JSON.parse(e.data));
            renderIssues();
        });

        eventSource.addEventListener("job_unblocked", e => {
            const job = JSON.parse(e.data);
            blockedJobs = blockedJobs.filter(j => j.id !== job.id);
            pendingJobs.push(job);
            renderQueue();
            renderIssues();
        });

        eventSource.addEventListener("queue_paused", e => {
            paused = JSON.parse(e.data).paused;
            updatePauseButton();
        });

        eventSource.onerror = () => {
            eventSource.close();
            setTimeout(connectSSE, 3000);
        };
    }

    document.getElementById("btn-pause").addEventListener("click", () => {
        api("POST", "/api/queue/pause", { paused: !paused });
    });

    document.querySelectorAll("#queue-tabs .queue-tab").forEach(tab => {
        tab.addEventListener("click", () => {
            document.querySelectorAll("#queue-tabs .queue-tab").forEach(t => t.classList.toggle("active", t === tab));
            document.querySelectorAll("#view-queue .queue-pane").forEach(p => {
                p.classList.toggle("active", p.id === "qtab-" + tab.dataset.qtab);
            });
            if (tab.dataset.qtab === "history") loadHistory();
        });
    });

    document.getElementById("issues-body").addEventListener("click", e => {
        const retryBtn = e.target.closest("[data-retry]");
        if (retryBtn) {
            const id = retryBtn.dataset.retry;
            api("POST", "/api/queue/retry", { ids: [id] }).then(() => {
                failedJobs = failedJobs.filter(j => j.id !== id);
                renderIssues();
            }).catch(err => alert(err.message));
            return;
        }
        const dismissBtn = e.target.closest("[data-dismiss]");
        if (dismissBtn) {
            const id = dismissBtn.dataset.dismiss;
            api("POST", "/api/history/dismiss", { ids: [id] }).then(() => {
                failedJobs = failedJobs.filter(j => j.id !== id);
                renderIssues();
            }).catch(err => alert(err.message));
        }
    });

    let historyData = [];
    let historyPage = 0;
    let historyPageSize = 50;
    let historySortBy = "finished_at";
    let historySortDir = "desc";
    let historyStatusFilter = "";
    const expandedHistoryIds = new Set();

    function loadHistory() {
        const params = new URLSearchParams();
        params.set("limit", historyPageSize);
        params.set("offset", historyPage * historyPageSize);
        params.set("sort_by", historySortBy);
        params.set("sort_dir", historySortDir);
        if (historyStatusFilter) params.set("status", historyStatusFilter);
        api("GET", "/api/history?" + params.toString()).then(rows => {
            historyData = rows;
            renderHistory();
        });
    }

    function updateSortArrows() {
        document.querySelectorAll("#history-table th.sortable").forEach(th => {
            const existing = th.querySelector(".sort-arrow");
            if (existing) existing.remove();
            if (th.dataset.sort === historySortBy) {
                const arrow = document.createElement("span");
                arrow.className = "sort-arrow";
                arrow.textContent = historySortDir === "asc" ? " ▲" : " ▼";
                th.appendChild(arrow);
            }
        });
    }

    function renderHistory() {
        const table = document.getElementById("history-table");
        const tbody = document.getElementById("history-body");
        const emptyMsg = document.getElementById("history-empty");

        updateSortArrows();

        const hasRows = historyData.length > 0;
        table.style.display = hasRows ? "" : "none";
        emptyMsg.style.display = hasRows ? "none" : "";

        let html = "";
        for (let i = 0; i < historyData.length; i++) {
            const r = historyData[i];
            html += "<tr class=\"clickable" + (i % 2 ? " stripe" : "") + "\" data-job-id=\"" + esc(r.id) + "\">"
                + "<td title=\"" + esc(r.file_path) + "\">" + esc(basename(r.file_path)) + "</td>"
                + "<td>" + esc(r.library_name) + "</td>"
                + "<td>" + formatBytes(r.old_size_bytes) + "</td>"
                + "<td>" + formatBytes(r.new_size_bytes) + "</td>"
                + "<td>" + formatDate(r.finished_at) + "</td>"
                + "<td class=\"status-" + esc(r.status.replace(/\s+/g, "-")) + "\">" + esc(r.status) + "</td>"
                + "</tr>";
        }
        tbody.innerHTML = html;

        for (const id of expandedHistoryIds) {
            const row = tbody.querySelector("tr[data-job-id=\"" + id + "\"]");
            if (row) expandHistoryRow(row);
            else expandedHistoryIds.delete(id);
        }

        renderHistoryPagination();
    }

    function renderHistoryPagination() {
        const el = document.getElementById("history-pagination");
        const hasPrev = historyPage > 0;
        const hasNext = historyData.length === historyPageSize;
        const sizes = [25, 50, 100, 200].map(n =>
            "<option value=\"" + n + "\"" + (n === historyPageSize ? " selected" : "") + ">" + n + " / page</option>"
        ).join("");
        el.innerHTML = "<button class=\"btn btn-sm\" id=\"hist-prev\"" + (hasPrev ? "" : " disabled") + ">Prev</button>"
            + "<span class=\"hist-page-label\">Page " + (historyPage + 1) + "</span>"
            + "<button class=\"btn btn-sm\" id=\"hist-next\"" + (hasNext ? "" : " disabled") + ">Next</button>"
            + "<select id=\"hist-page-size\">" + sizes + "</select>";
        if (hasPrev) document.getElementById("hist-prev").addEventListener("click", () => { historyPage--; loadHistory(); });
        if (hasNext) document.getElementById("hist-next").addEventListener("click", () => { historyPage++; loadHistory(); });
        document.getElementById("hist-page-size").addEventListener("change", e => {
            historyPageSize = parseInt(e.target.value);
            historyPage = 0;
            loadHistory();
        });
    }

    function buildDetailMessage(r) {
        const lines = [];
        if (r.status === "completed") {
            lines.push("Completed successfully.");
            if (r.new_size_bytes != null && r.old_size_bytes > 0) {
                const saved = r.old_size_bytes - r.new_size_bytes;
                const pct = Math.round((saved / r.old_size_bytes) * 100);
                lines.push("Saved: " + formatBytes(saved) + " (" + pct + "% smaller than original)");
            }
            lines.push("Duration: " + formatDuration(r.duration_seconds));
        } else if (r.error_message) {
            lines.push(r.error_message);
        }
        lines.push("Path: " + r.file_path);
        if (r.preset_name) lines.push("Preset: " + r.preset_name);
        if (r.device_name) lines.push("Device: " + r.device_name);
        return lines.map(esc).join("<br>");
    }

    function expandHistoryRow(row) {
        const jobId = row.dataset.jobId;
        const r = historyData.find(x => x.id === jobId);
        const detail = r ? buildDetailMessage(r) : "";
        const expandRow = document.createElement("tr");
        expandRow.className = "log-row";
        expandRow.innerHTML = "<td colspan=\"6\">"
            + (detail ? "<div class=\"history-detail\">" + detail + "</div>" : "")
            + "<button class=\"btn btn-copy-log\" style=\"margin-bottom:8px\">Copy to Clipboard</button>"
            + "<div class=\"log-expand\" id=\"log-" + jobId + "\">Loading...</div>"
            + "</td>";
        row.after(expandRow);
        expandRow.querySelector(".btn-copy-log").addEventListener("click", e => {
            e.stopPropagation();
            const logEl = document.getElementById("log-" + jobId);
            if (!logEl) return;
            const btn = e.currentTarget;
            const ta = document.createElement("textarea");
            ta.value = logEl.textContent;
            ta.style.position = "fixed";
            ta.style.opacity = "0";
            document.body.appendChild(ta);
            ta.select();
            document.execCommand("copy");
            ta.remove();
            let msg = btn.nextElementSibling;
            if (msg && msg.classList.contains("copy-confirm")) msg.remove();
            msg = document.createElement("span");
            msg.className = "copy-confirm";
            msg.textContent = "Copied!";
            btn.after(msg);
            setTimeout(() => msg.remove(), 4000);
        });
        fetchLog(jobId);
    }

    function toggleLog(row) {
        const jobId = row.dataset.jobId;
        const next = row.nextElementSibling;
        if (next && next.classList.contains("log-row")) {
            next.remove();
            expandedHistoryIds.delete(jobId);
            return;
        }
        expandedHistoryIds.add(jobId);
        expandHistoryRow(row);
    }

    function fetchLog(jobId) {
        const el = document.getElementById("log-" + jobId);
        if (!el) return;
        api("GET", "/api/history/" + encodeURIComponent(jobId) + "/log").then(data => {
            el.textContent = data.log || "(empty)";
        }).catch(() => { el.textContent = "(failed to load log)"; });
    }

    document.getElementById("history-body").addEventListener("click", e => {
        const row = e.target.closest("tr.clickable");
        if (row) toggleLog(row);
    });

    document.querySelectorAll("#history-table th.sortable").forEach(th => {
        th.addEventListener("click", () => {
            const col = th.dataset.sort;
            if (historySortBy === col) {
                historySortDir = historySortDir === "asc" ? "desc" : "asc";
            } else {
                historySortBy = col;
                historySortDir = col === "finished_at" ? "desc" : "asc";
            }
            historyPage = 0;
            loadHistory();
        });
    });

    document.getElementById("history-status-filter").addEventListener("change", e => {
        historyStatusFilter = e.target.value;
        historyPage = 0;
        loadHistory();
    });

    let searchQuery = "";
    let searchPage = 0;
    let searchPageSize = 25;
    let searchSortBy = "finished_at";
    let searchSortDir = "desc";
    let searchTimer = null;
    let searchResults = [];
    let searchTotal = 0;

    function sizeLabel(r) {
        if (r.source === "history" && r.new_size_bytes != null) {
            return formatBytes(r.old_size_bytes) + " → " + formatBytes(r.new_size_bytes);
        }
        return formatBytes(r.old_size_bytes);
    }

    function setSearchActive(active) {
        const panel = document.getElementById("search-results");
        const panes = document.querySelectorAll("#view-queue .queue-pane");
        const tabs = document.querySelectorAll("#queue-tabs .queue-tab");
        if (active) {
            panes.forEach(p => { p.style.display = "none"; });
            tabs.forEach(t => t.classList.add("dimmed"));
            panel.style.display = "";
        } else {
            panel.style.display = "none";
            tabs.forEach(t => t.classList.remove("dimmed"));
            panes.forEach(p => { p.style.display = ""; });
        }
    }

    function updateSearchSortArrows() {
        document.querySelectorAll("#search-table th.sortable").forEach(th => {
            const existing = th.querySelector(".sort-arrow");
            if (existing) existing.remove();
            if (th.dataset.sort === searchSortBy) {
                const arrow = document.createElement("span");
                arrow.className = "sort-arrow";
                arrow.textContent = searchSortDir === "asc" ? " ▲" : " ▼";
                th.appendChild(arrow);
            }
        });
    }

    async function runSearch() {
        if (searchQuery.length < 2) {
            searchResults = [];
            searchTotal = 0;
            setSearchActive(false);
            renderSearch();
            return;
        }
        setSearchActive(true);
        const params = new URLSearchParams();
        params.set("q", searchQuery);
        params.set("limit", searchPageSize);
        params.set("offset", searchPage * searchPageSize);
        params.set("sort_by", searchSortBy);
        params.set("sort_dir", searchSortDir);
        const data = await api("GET", "/api/search?" + params.toString());
        searchResults = data.results;
        searchTotal = data.total;
        renderSearch();
    }

    function renderSearch() {
        const table = document.getElementById("search-table");
        const tbody = document.getElementById("search-body");
        const empty = document.getElementById("search-empty");
        const pagEl = document.getElementById("search-pagination");

        updateSearchSortArrows();

        const active = searchQuery.length >= 2;
        table.style.display = active ? "" : "none";
        empty.style.display = active && !searchResults.length ? "" : "none";

        if (!searchResults.length) {
            tbody.innerHTML = "";
            pagEl.innerHTML = "";
            return;
        }

        let html = "";
        for (let i = 0; i < searchResults.length; i++) {
            const r = searchResults[i];
            html += "<tr class=\"" + (i % 2 ? "stripe" : "") + "\">"
                + "<td title=\"" + esc(r.file_path) + "\">" + esc(basename(r.file_path)) + "</td>"
                + "<td>" + esc(r.library_name) + "</td>"
                + "<td>" + sizeLabel(r) + "</td>"
                + "<td>" + formatDate(r.date) + "</td>"
                + "<td class=\"status-" + esc(r.status.replace(/\s+/g, "-")) + "\">" + esc(r.status) + "</td>"
                + "</tr>";
        }
        tbody.innerHTML = html;

        const hasPrev = searchPage > 0;
        const hasNext = searchTotal > (searchPage + 1) * searchPageSize;
        const sizes = [25, 50, 100, 200].map(n =>
            "<option value=\"" + n + "\"" + (n === searchPageSize ? " selected" : "") + ">" + n + " / page</option>"
        ).join("");
        pagEl.innerHTML = "<button class=\"btn btn-sm\" id=\"search-prev\"" + (hasPrev ? "" : " disabled") + ">Prev</button>"
            + "<span class=\"hist-page-label\">Page " + (searchPage + 1) + "</span>"
            + "<button class=\"btn btn-sm\" id=\"search-next\"" + (hasNext ? "" : " disabled") + ">Next</button>"
            + "<select id=\"search-page-size\">" + sizes + "</select>";
        if (hasPrev) document.getElementById("search-prev").addEventListener("click", () => { searchPage--; runSearch(); });
        if (hasNext) document.getElementById("search-next").addEventListener("click", () => { searchPage++; runSearch(); });
        document.getElementById("search-page-size").addEventListener("change", e => {
            searchPageSize = parseInt(e.target.value);
            searchPage = 0;
            runSearch();
        });
    }

    document.getElementById("queue-search").addEventListener("input", e => {
        clearTimeout(searchTimer);
        searchTimer = setTimeout(() => {
            searchQuery = e.target.value.trim();
            searchPage = 0;
            runSearch();
        }, 300);
    });

    document.querySelectorAll("#search-table th.sortable").forEach(th => {
        th.addEventListener("click", () => {
            const col = th.dataset.sort;
            if (searchSortBy === col) {
                searchSortDir = searchSortDir === "asc" ? "desc" : "asc";
            } else {
                searchSortBy = col;
                searchSortDir = col === "finished_at" ? "desc" : "asc";
            }
            searchPage = 0;
            runSearch();
        });
    });

    const AUDIO_MODE_OPTIONS = [
        { value: "copy", label: "Copy (passthrough)" },
        { value: "configure", label: "Configure" },
    ];

    const AUDIO_TIER_CODEC_OPTIONS = [
        { value: "copy", label: "Copy (keep original)" },
        { value: "aac", label: "AAC" },
        { value: "ac3", label: "AC3 (Dolby Digital)" },
        { value: "eac3", label: "EAC3 (Dolby Digital Plus)" },
        { value: "libopus", label: "Opus" },
    ];

    const SUBTITLE_MODE_OPTIONS = [
        { value: "keep", label: "Keep all" },
        { value: "remove", label: "Remove all" },
        { value: "keep_by_language", label: "Keep by language" },
    ];

    const RESOLUTION_CAP_OPTIONS = [
        { value: "", label: "No limit" },
        { value: "720", label: "720p" },
        { value: "1080", label: "1080p" },
        { value: "1440", label: "1440p" },
        { value: "2160", label: "2160p" },
    ];

    let presets = [];
    let editingPreset = null;
    let showingNewForm = false;

    function parsePresetData(p) {
        const audio = p.audio || null;
        let audioMode = "copy";
        if (audio) {
            const hasTierConfig = (audio.stereo && audio.stereo.codec !== "copy") || (audio.surround && audio.surround.codec !== "copy");
            const hasFiltering = (audio.languages && audio.languages.length > 0) || audio.remove_commentary || (audio.add_stereo_downmix && audio.add_stereo_downmix !== "never");
            if (hasTierConfig || hasFiltering) audioMode = "configure";
        }
        const subtitle = p.subtitle || null;
        let subtitleMode = "keep";
        if (subtitle && subtitle.mode !== "keep") subtitleMode = subtitle.mode;
        const resolutionCap = p.resolution_cap || null;
        return { audio, audioMode, subtitle, subtitleMode, resolutionCap };
    }

    function buildAudioModeOptionsHTML(selected) {
        return AUDIO_MODE_OPTIONS.map(c =>
            '<option value="' + c.value + '"' + (c.value === selected ? " selected" : "") + ">" + esc(c.label) + "</option>"
        ).join("");
    }

    function buildAudioTierCodecOptionsHTML(selected) {
        return AUDIO_TIER_CODEC_OPTIONS.map(c =>
            '<option value="' + c.value + '"' + (c.value === selected ? " selected" : "") + ">" + esc(c.label) + "</option>"
        ).join("");
    }

    function buildSubtitleModeOptionsHTML(selected) {
        return SUBTITLE_MODE_OPTIONS.map(c =>
            '<option value="' + c.value + '"' + (c.value === selected ? " selected" : "") + ">" + esc(c.label) + "</option>"
        ).join("");
    }

    function buildResolutionCapOptionsHTML(selected) {
        return RESOLUTION_CAP_OPTIONS.map(c =>
            '<option value="' + c.value + '"' + (c.value === (selected || "") ? " selected" : "") + ">" + esc(c.label) + "</option>"
        ).join("");
    }

    function loadPresets() {
        api("GET", "/api/presets").then(data => {
            presets = data;
            renderPresets();
        });
    }

    function renderPresets() {
        const grid = document.getElementById("preset-grid");
        let html = "";

        if (showingNewForm) {
            html += renderPresetForm(null);
        }

        for (const p of presets) {
            if (editingPreset === p.name) {
                html += renderPresetForm(p);
            } else {
                html += renderPresetCard(p);
            }
        }

        grid.innerHTML = html;

        const form = grid.querySelector(".preset-card.editing");
        if (form) attachFormListeners(form, editingPreset);
    }

    function renderPresetCard(p) {
        const data = parsePresetData(p);

        let videoHtml = "";
        videoHtml += "<dt>Args</dt><dd>" + esc(p.ffmpeg_args) + "</dd>";
        videoHtml += "<dt>Container</dt><dd>" + (p.output_container ? esc(p.output_container) : "Keep original") + "</dd>";
        if (data.resolutionCap) {
            videoHtml += "<dt>Resolution Cap</dt><dd>" + esc(String(data.resolutionCap)) + "p</dd>";
        }

        let audioHtml = "";
        if (data.audioMode === "configure" && data.audio) {
            const a = data.audio;
            const tierLabel = (t) => {
                if (!t || t.codec === "copy") return "Copy";
                const cl = AUDIO_TIER_CODEC_OPTIONS.find(c => c.value === t.codec)?.label || t.codec;
                return t.bitrate ? cl + " " + t.bitrate : cl;
            };
            audioHtml += "<dt>Stereo</dt><dd>" + esc(tierLabel(a.stereo)) + "</dd>";
            audioHtml += "<dt>Surround</dt><dd>" + esc(tierLabel(a.surround)) + "</dd>";
            if (a.add_stereo_downmix && a.add_stereo_downmix !== "never") {
                const dmxLabel = a.add_stereo_downmix === "if_no_stereo" ? "If no stereo" : "Always";
                audioHtml += "<dt>Downmix</dt><dd>" + esc(dmxLabel) + "</dd>";
                if (a.downmix_bitrate) audioHtml += "<dt>Dmx Bitrate</dt><dd>" + esc(a.downmix_bitrate) + "</dd>";
            }
            if (a.languages && a.languages.length) {
                audioHtml += "<dt>Languages</dt><dd>" + esc(a.languages.join(", ")) + "</dd>";
            }
            if (a.remove_commentary) {
                audioHtml += "<dt>Commentary</dt><dd>Remove</dd>";
            }
        }

        let subtitleHtml = "";
        if (data.subtitleMode !== "keep") {
            const s = data.subtitle;
            if (data.subtitleMode === "remove") {
                subtitleHtml += "<dt>Mode</dt><dd>Remove all</dd>";
            } else {
                subtitleHtml += "<dt>Mode</dt><dd>Keep by language</dd>";
                if (s && s.languages && s.languages.length) {
                    subtitleHtml += "<dt>Languages</dt><dd>" + esc(s.languages.join(", ")) + "</dd>";
                }
                if (s && s.remove_commentary) {
                    subtitleHtml += "<dt>Commentary</dt><dd>Remove</dd>";
                }
            }
        }

        return '<div class="preset-card">'
            + '<div class="preset-card-header">'
            + '<span class="preset-card-name">' + esc(p.name) + '</span>'
            + '<div class="preset-card-actions">'
            + '<button class="btn" data-action="edit" data-name="' + esc(p.name) + '">Edit</button>'
            + '<button class="btn btn-danger" data-action="delete" data-name="' + esc(p.name) + '">Delete</button>'
            + '</div></div>'
            + '<div class="preset-card-section"><span class="preset-card-section-label">Video</span><dl class="preset-card-props">' + videoHtml + '</dl></div>'
            + (audioHtml ? '<div class="preset-card-section"><span class="preset-card-section-label">Audio</span><dl class="preset-card-props">' + audioHtml + '</dl></div>' : "")
            + (subtitleHtml ? '<div class="preset-card-section"><span class="preset-card-section-label">Subtitles</span><dl class="preset-card-props">' + subtitleHtml + '</dl></div>' : "")
            + '</div>';
    }

    function renderPresetForm(preset) {
        const name = preset ? preset.name : "";
        const args = preset ? preset.ffmpeg_args : "";
        const container = preset ? (preset.output_container || "") : "";
        const data = preset ? parsePresetData(preset) : {};

        const subtitleMode = data.subtitleMode || "keep";
        const sub = data.subtitle || {};
        const subLanguages = sub.languages ? sub.languages.join(", ") : "";
        const subCommentaryChecked = sub.remove_commentary ? " checked" : "";
        const subConfigHidden = subtitleMode !== "keep_by_language" ? ' style="display:none"' : "";
        const resCap = data.resolutionCap ? String(data.resolutionCap) : "";

        const audioMode = data.audioMode || "copy";
        const a = data.audio || {};
        const stereoCodec = a.stereo ? a.stereo.codec : "copy";
        const stereoBitrate = a.stereo ? (a.stereo.bitrate || "") : "";
        const surroundCodec = a.surround ? a.surround.codec : "copy";
        const surroundBitrate = a.surround ? (a.surround.bitrate || "") : "";
        const downmixMode = a.add_stereo_downmix || "never";
        const downmixBitrate = a.downmix_bitrate || "";
        const languages = a.languages ? a.languages.join(", ") : "";
        const commentaryChecked = a.remove_commentary ? " checked" : "";
        const configHidden = audioMode === "copy" ? ' style="display:none"' : "";
        const stereoBitrateHidden = stereoCodec === "copy" ? ' style="display:none"' : "";
        const surroundBitrateHidden = surroundCodec === "copy" ? ' style="display:none"' : "";
        const downmixBitrateHidden = downmixMode === "never" ? ' style="display:none"' : "";

        return '<div class="preset-card editing">'
            + '<div class="form-group"><label>Name</label>'
            + '<input type="text" class="pc-name" value="' + esc(name) + '"></div>'
            + '<div class="preset-tabs">'
            + '<button class="preset-tab active" data-tab="video" type="button">Video</button>'
            + '<button class="preset-tab" data-tab="audio" type="button">Audio</button>'
            + '<button class="preset-tab" data-tab="subtitle" type="button">Subtitles</button>'
            + '</div>'
            + '<div class="preset-tab-panel pc-tab-video">'
            + '<div class="form-group"><label>FFmpeg Arguments</label>'
            + '<input type="text" class="pc-args" value="' + esc(args) + '" placeholder="-c:v libx265 -crf 24 -preset slow"></div>'
            + '<div class="form-group"><label>Output Container</label>'
            + '<input type="text" class="pc-container" value="' + esc(container) + '" placeholder="Leave empty to keep original"></div>'
            + '<div class="form-group pc-rescap-group"><label>Resolution Cap</label>'
            + '<select class="pc-rescap">' + buildResolutionCapOptionsHTML(resCap) + '</select></div>'
            + '</div>'
            + '<div class="preset-tab-panel pc-tab-audio" style="display:none">'
            + '<div class="form-group"><label>Mode</label>'
            + '<select class="pc-audio-mode">' + buildAudioModeOptionsHTML(audioMode) + '</select></div>'
            + '<div class="pc-audio-config"' + configHidden + '>'
            + '<div class="audio-tier">'
            + '<label class="section-label">Stereo, 1-2 channels</label>'
            + '<div class="form-row form-row-2">'
            + '<div class="form-group"><label>Codec</label>'
            + '<select class="pc-stereo-codec">' + buildAudioTierCodecOptionsHTML(stereoCodec) + '</select></div>'
            + '<div class="form-group pc-stereo-bitrate-group"' + stereoBitrateHidden + '><label>Bitrate</label>'
            + '<input type="text" class="pc-stereo-bitrate" value="' + esc(stereoBitrate) + '" placeholder="e.g. 160k"></div>'
            + '</div></div>'
            + '<div class="audio-tier">'
            + '<label class="section-label">Surround, 3+ channels</label>'
            + '<div class="form-row form-row-2">'
            + '<div class="form-group"><label>Codec</label>'
            + '<select class="pc-surround-codec">' + buildAudioTierCodecOptionsHTML(surroundCodec) + '</select></div>'
            + '<div class="form-group pc-surround-bitrate-group"' + surroundBitrateHidden + '><label>Bitrate</label>'
            + '<input type="text" class="pc-surround-bitrate" value="' + esc(surroundBitrate) + '" placeholder="e.g. 640k"></div>'
            + '</div>'
            + '<div class="form-row form-row-2">'
            + '<div class="form-group"><label>Stereo downmix</label>'
            + '<select class="pc-downmix">'
            + '<option value="never"' + (downmixMode === "never" ? " selected" : "") + '>Never</option>'
            + '<option value="always"' + (downmixMode === "always" ? " selected" : "") + '>Always</option>'
            + '<option value="if_no_stereo"' + (downmixMode === "if_no_stereo" ? " selected" : "") + '>If no stereo track exists</option>'
            + '</select></div>'
            + '<div class="form-group pc-downmix-bitrate-group"' + downmixBitrateHidden + '><label>Bitrate</label>'
            + '<input type="text" class="pc-downmix-bitrate" value="' + esc(downmixBitrate) + '" placeholder="e.g. 160k"></div>'
            + '</div></div>'
            + '<div class="audio-tier">'
            + '<label class="section-label">Filtering</label>'
            + '<div class="form-row form-row-2">'
            + '<div class="form-group"><label>Languages</label>'
            + '<input type="text" class="pc-languages" value="' + esc(languages) + '" placeholder="e.g. eng, jpn, spa"></div>'
            + '<label class="audio-checkbox"><input type="checkbox" class="pc-remove-commentary"' + commentaryChecked + '> Remove commentary</label>'
            + '</div></div>'
            + '</div></div>'
            + '<div class="preset-tab-panel pc-tab-subtitle" style="display:none">'
            + '<div class="form-group"><label>Mode</label>'
            + '<select class="pc-subtitle-mode">' + buildSubtitleModeOptionsHTML(subtitleMode) + '</select></div>'
            + '<div class="pc-subtitle-config"' + subConfigHidden + '>'
            + '<div class="form-row form-row-2">'
            + '<div class="form-group"><label>Languages</label>'
            + '<input type="text" class="pc-sub-languages" value="' + esc(subLanguages) + '" placeholder="e.g. eng, jpn, spa"></div>'
            + '<label class="audio-checkbox"><input type="checkbox" class="pc-sub-remove-commentary"' + subCommentaryChecked + '> Remove commentary</label>'
            + '</div></div>'
            + '</div>'
            + '<div class="form-actions">'
            + '<button class="btn pc-cancel">Cancel</button>'
            + '<button class="btn btn-primary pc-save">Save</button>'
            + '</div></div>';
    }

    function attachFormListeners(form, originalName) {
        const isNew = originalName === null;

        form.querySelectorAll(".preset-tab").forEach(tab => {
            tab.addEventListener("click", () => {
                form.querySelectorAll(".preset-tab").forEach(t => t.classList.toggle("active", t === tab));
                form.querySelector(".pc-tab-video").style.display = tab.dataset.tab === "video" ? "" : "none";
                form.querySelector(".pc-tab-audio").style.display = tab.dataset.tab === "audio" ? "" : "none";
                form.querySelector(".pc-tab-subtitle").style.display = tab.dataset.tab === "subtitle" ? "" : "none";
            });
        });

        const audioModeSel = form.querySelector(".pc-audio-mode");
        const audioConfigDiv = form.querySelector(".pc-audio-config");
        audioModeSel.addEventListener("change", () => {
            audioConfigDiv.style.display = audioModeSel.value === "copy" ? "none" : "";
        });

        const stereoCodecSel = form.querySelector(".pc-stereo-codec");
        const stereoBitrateGroup = form.querySelector(".pc-stereo-bitrate-group");
        stereoCodecSel.addEventListener("change", () => {
            stereoBitrateGroup.style.display = stereoCodecSel.value === "copy" ? "none" : "";
        });

        const surroundCodecSel = form.querySelector(".pc-surround-codec");
        const surroundBitrateGroup = form.querySelector(".pc-surround-bitrate-group");
        surroundCodecSel.addEventListener("change", () => {
            surroundBitrateGroup.style.display = surroundCodecSel.value === "copy" ? "none" : "";
        });

        const downmixSelect = form.querySelector(".pc-downmix");
        const downmixBitrateGroup = form.querySelector(".pc-downmix-bitrate-group");
        downmixSelect.addEventListener("change", () => {
            downmixBitrateGroup.style.display = downmixSelect.value !== "never" ? "" : "none";
        });

        const subtitleModeSel = form.querySelector(".pc-subtitle-mode");
        const subtitleConfigDiv = form.querySelector(".pc-subtitle-config");
        subtitleModeSel.addEventListener("change", () => {
            subtitleConfigDiv.style.display = subtitleModeSel.value === "keep_by_language" ? "" : "none";
        });

        form.querySelector(".pc-save").addEventListener("click", async () => {
            const name = form.querySelector(".pc-name").value.trim();
            const args = form.querySelector(".pc-args").value.trim();
            const container = form.querySelector(".pc-container").value.trim() || null;

            if (!name || !args) {
                alert("Name and arguments are required.");
                return;
            }

            let valid = true;
            function validateBitrate(input) {
                const v = input.value.trim();
                if (!v) return true;
                if (/^\d+k$/i.test(v)) return true;
                alert("Use format like 160k, 320k, 640k");
                valid = false;
                return false;
            }

            let audio;
            const audioModeVal = form.querySelector(".pc-audio-mode").value;
            if (audioModeVal === "copy") {
                audio = { stereo: { codec: "copy" }, surround: { codec: "copy" } };
            } else {
                const stereoCodecVal = form.querySelector(".pc-stereo-codec").value;
                const stereo = { codec: stereoCodecVal };
                if (stereoCodecVal !== "copy") {
                    const brEl = form.querySelector(".pc-stereo-bitrate");
                    validateBitrate(brEl);
                    const br = brEl.value.trim();
                    if (br) stereo.bitrate = br;
                }
                const surroundCodecVal = form.querySelector(".pc-surround-codec").value;
                const surround = { codec: surroundCodecVal };
                if (surroundCodecVal !== "copy") {
                    const brEl = form.querySelector(".pc-surround-bitrate");
                    validateBitrate(brEl);
                    const br = brEl.value.trim();
                    if (br) surround.bitrate = br;
                }
                audio = { stereo, surround };
                const dmxMode = form.querySelector(".pc-downmix").value;
                if (dmxMode !== "never") {
                    audio.add_stereo_downmix = dmxMode;
                    const dmxBrEl = form.querySelector(".pc-downmix-bitrate");
                    validateBitrate(dmxBrEl);
                    const dmxBr = dmxBrEl.value.trim();
                    if (dmxBr) audio.downmix_bitrate = dmxBr;
                }
                if (!valid) return;
                const langs = form.querySelector(".pc-languages").value.trim();
                if (langs) audio.languages = langs.split(",").map(s => s.trim()).filter(Boolean);
                if (form.querySelector(".pc-remove-commentary").checked) audio.remove_commentary = true;
            }

            let subtitle = null;
            const subModeVal = form.querySelector(".pc-subtitle-mode").value;
            if (subModeVal !== "keep") {
                subtitle = { mode: subModeVal };
                if (subModeVal === "keep_by_language") {
                    const subLangs = form.querySelector(".pc-sub-languages").value.trim();
                    if (subLangs) subtitle.languages = subLangs.split(",").map(s => s.trim()).filter(Boolean);
                    if (form.querySelector(".pc-sub-remove-commentary").checked) subtitle.remove_commentary = true;
                }
            }

            const resCapVal = form.querySelector(".pc-rescap").value;
            const resolution_cap = resCapVal ? parseInt(resCapVal, 10) : null;

            try {
                if (isNew) {
                    await api("POST", "/api/presets", { name, ffmpeg_args: args, output_container: container, audio, subtitle, resolution_cap });
                    showingNewForm = false;
                } else {
                    await api("PUT", "/api/presets/" + encodeURIComponent(originalName), { name, ffmpeg_args: args, output_container: container, audio, subtitle, resolution_cap });
                    editingPreset = null;
                }
                loadPresets();
            } catch (e) {
                alert(e.message);
            }
        });

        form.querySelector(".pc-cancel").addEventListener("click", () => {
            if (isNew) showingNewForm = false;
            else editingPreset = null;
            renderPresets();
        });
    }

    document.getElementById("preset-grid").addEventListener("click", e => {
        const btn = e.target.closest("[data-action]");
        if (!btn) return;
        const name = btn.dataset.name;

        if (btn.dataset.action === "edit") {
            editingPreset = name;
            showingNewForm = false;
            renderPresets();
        } else if (btn.dataset.action === "delete") {
            if (!confirm('Delete preset "' + name + '"?')) return;
            api("DELETE", "/api/presets/" + encodeURIComponent(name)).then(() => {
                loadPresets();
            }).catch(e => alert(e.message));
        }
    });

    document.getElementById("btn-new-preset").addEventListener("click", () => {
        showingNewForm = !showingNewForm;
        editingPreset = null;
        renderPresets();
    });

    let libraries = [];
    let editingLibrary = null;
    let showingNewLibraryForm = false;

    function loadLibraries() {
        api("GET", "/api/libraries").then(data => {
            libraries = data;
            renderLibraries();
        });
    }

    function renderLibraries() {
        const grid = document.getElementById("library-grid");
        let html = "";

        if (showingNewLibraryForm) {
            html += renderLibraryForm(null);
        }

        for (const lib of libraries) {
            if (editingLibrary === lib.name) {
                html += renderLibraryForm(lib);
            } else {
                html += renderLibraryCard(lib);
            }
        }

        grid.innerHTML = html;

        const form = grid.querySelector(".library-card.editing");
        if (form) attachLibraryFormListeners(form, editingLibrary);
    }

    function renderLibraryCard(lib) {
        let props = "";
        props += "<dt>Preset</dt><dd>" + esc(lib.preset) + "</dd>";
        props += "<dt>Watch</dt><dd>" + (lib.watch ? "Yes" : "No") + "</dd>";
        if (lib.scan_interval > 0) {
            props += "<dt>Scan</dt><dd>Every " + lib.scan_interval + " " + esc(lib.scan_unit) + "</dd>";
        }
        props += "<dt>Paths</dt><dd>" + esc(lib.paths.join(", ")) + "</dd>";

        return '<div class="library-card" data-name="' + esc(lib.name) + '">'
            + '<div class="library-card-header">'
            + '<span class="library-card-name">' + esc(lib.name) + '</span>'
            + '<div class="library-card-actions">'
            + '<button class="btn" data-lib-action="scan" data-name="' + esc(lib.name) + '">Scan</button>'
            + '<button class="btn" data-lib-action="edit" data-name="' + esc(lib.name) + '">Edit</button>'
            + '<button class="btn btn-danger" data-lib-action="delete" data-name="' + esc(lib.name) + '">Delete</button>'
            + '</div></div>'
            + '<dl class="library-card-props">' + props + '</dl>'
            + '</div>';
    }

    function renderLibraryForm(lib) {
        const name = lib ? lib.name : "";
        const paths = lib ? lib.paths.join(", ") : "";
        const preset = lib ? lib.preset : "";
        const watch = lib ? lib.watch : true;
        const scanInterval = lib ? (lib.scan_interval || 0) : 0;
        const scanUnit = lib ? (lib.scan_unit || "minutes") : "minutes";

        return '<div class="library-card editing">'
            + '<div class="form-group"><label>Name</label>'
            + '<input type="text" class="lc-name" value="' + esc(name) + '"></div>'
            + '<div class="form-group"><label>Preset</label>'
            + '<input type="text" class="lc-preset" value="' + esc(preset) + '" placeholder="Preset name"></div>'
            + '<div class="form-group"><label>Paths (comma-separated)</label>'
            + '<input type="text" class="lc-paths" value="' + esc(paths) + '" placeholder="/media/movies, /media/tv"></div>'
            + '<div class="form-group"><label>'
            + '<input type="checkbox" class="lc-watch"' + (watch ? " checked" : "") + '> Watch for new files</label></div>'
            + '<div class="form-group"><label>Scan Interval</label>'
            + '<div style="display:flex;gap:8px">'
            + '<input type="number" class="lc-scan-interval" value="' + scanInterval + '" min="0" style="width:80px">'
            + '<select class="lc-scan-unit">'
            + '<option value="minutes"' + (scanUnit === "minutes" ? " selected" : "") + '>minutes</option>'
            + '<option value="hours"' + (scanUnit === "hours" ? " selected" : "") + '>hours</option>'
            + '<option value="days"' + (scanUnit === "days" ? " selected" : "") + '>days</option>'
            + '</select></div></div>'
            + '<div class="form-actions">'
            + '<button class="btn lc-cancel">Cancel</button>'
            + '<button class="btn btn-primary lc-save">Save</button>'
            + '</div></div>';
    }

    function attachLibraryFormListeners(form, originalName) {
        const isNew = originalName === null;

        form.querySelector(".lc-save").addEventListener("click", async () => {
            const name = form.querySelector(".lc-name").value.trim();
            const preset = form.querySelector(".lc-preset").value.trim();
            const paths = form.querySelector(".lc-paths").value
                .split(",").map(p => p.trim()).filter(Boolean);
            const watch = form.querySelector(".lc-watch").checked;
            const scan_interval = parseInt(form.querySelector(".lc-scan-interval").value) || 0;
            const scan_unit = form.querySelector(".lc-scan-unit").value;

            if (!name || !preset || paths.length === 0) {
                alert("Name, preset, and at least one path are required.");
                return;
            }

            try {
                if (isNew) {
                    await api("POST", "/api/libraries", { name, paths, preset, watch, scan_interval, scan_unit });
                    showingNewLibraryForm = false;
                } else {
                    await api("PUT", "/api/libraries/" + encodeURIComponent(originalName), { name, paths, preset, watch, scan_interval, scan_unit });
                    editingLibrary = null;
                }
                loadLibraries();
            } catch (e) {
                alert(e.message);
            }
        });

        form.querySelector(".lc-cancel").addEventListener("click", () => {
            if (isNew) showingNewLibraryForm = false;
            else editingLibrary = null;
            renderLibraries();
        });
    }

    function setScanningBadge(name, show) {
        const card = document.querySelector('.library-card[data-name="' + CSS.escape(name) + '"]');
        if (!card) return;
        const header = card.querySelector(".library-card-header");
        const existing = header.querySelector(".scanning-badge");
        if (show && !existing) {
            const badge = document.createElement("span");
            badge.className = "scanning-badge";
            badge.textContent = "SCANNING";
            header.querySelector(".library-card-name").after(badge);
        } else if (!show && existing) {
            existing.remove();
        }
    }

    document.getElementById("library-grid").addEventListener("click", e => {
        const btn = e.target.closest("[data-lib-action]");
        if (!btn) return;
        const name = btn.dataset.name;

        if (btn.dataset.libAction === "scan") {
            setScanningBadge(name, true);
            api("POST", "/api/libraries/" + encodeURIComponent(name) + "/scan").then(result => {
                setScanningBadge(name, false);
                alert("Queued " + result.queued + " file" + (result.queued !== 1 ? "s" : "") + ".");
            }).catch(err => {
                setScanningBadge(name, false);
                alert("Scan failed: " + err.message);
            });
        } else if (btn.dataset.libAction === "edit") {
            editingLibrary = name;
            showingNewLibraryForm = false;
            renderLibraries();
        } else if (btn.dataset.libAction === "delete") {
            if (!confirm('Delete library "' + name + '"?')) return;
            api("DELETE", "/api/libraries/" + encodeURIComponent(name)).then(() => {
                loadLibraries();
            }).catch(e => alert(e.message));
        }
    });

    document.getElementById("btn-new-library").addEventListener("click", () => {
        showingNewLibraryForm = !showingNewLibraryForm;
        editingLibrary = null;
        renderLibraries();
    });

    function loadSettings() {
        api("GET", "/api/settings").then(s => {
            document.getElementById("set-cache-dir").value = s.cache_dir;
        });
        api("GET", "/api/devices").then(renderDevices);
    }

    function renderDevices(devices) {
        const grid = document.getElementById("device-grid");
        let html = "";
        for (const dev of devices) {
            html += '<div class="device-card">'
                + '<div class="device-card-header">'
                + '<span class="device-card-name">' + esc(dev.name) + '</span>'
                + '<span class="device-type">' + esc(dev.type) + '</span>'
                + '</div>'
                + '<div class="device-encoders">' + dev.encoders.map(esc).join(", ") + '</div>'
                + '<div class="form-group"><label>Max Concurrent Jobs (0 = disabled)</label>'
                + '<input type="number" class="dc-max-jobs" data-id="' + esc(dev.id) + '" value="' + dev.max_jobs + '" min="0"></div>'
                + '<button class="btn dc-save" data-id="' + esc(dev.id) + '">Save</button>'
                + '</div>';
        }
        grid.innerHTML = html;
    }

    document.getElementById("device-grid").addEventListener("click", e => {
        const btn = e.target.closest(".dc-save");
        if (!btn) return;
        const id = btn.dataset.id;
        const input = document.querySelector('.dc-max-jobs[data-id="' + CSS.escape(id) + '"]');
        api("PATCH", "/api/devices/" + encodeURIComponent(id), { max_jobs: parseInt(input.value) })
            .catch(err => alert(err.message));
    });

    document.getElementById("btn-save-settings").addEventListener("click", () => {
        const dir = document.getElementById("set-cache-dir").value.trim() || "/tmp/undarr";
        api("PATCH", "/api/settings", { cache_dir: dir })
            .catch(err => alert(err.message));
    });

    navigate(location.hash.slice(1) || "queue");
    connectSSE();
})();
