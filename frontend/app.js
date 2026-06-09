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

    function api(method, path, body) {
        const opts = { method, headers: {} };
        if (body !== undefined) {
            opts.headers["Content-Type"] = "application/json";
            opts.body = JSON.stringify(body);
        }
        return fetch(path, opts).then(res => {
            if (res.status === 204) return null;
            if (!res.ok) throw new Error(res.statusText);
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
    }

    navItems.forEach(n => n.addEventListener("click", () => navigate(n.dataset.view)));

    let activeJobs = [];
    let pendingJobs = [];
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
                + "<td>" + formatBytes(job.old_size_bytes) + "</td>"
                + "<td class=\"" + statusClass + "\">" + esc(job.status) + "</td>"
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
            paused = data.paused || false;
            updatePauseButton();
            renderQueue();
        });

        eventSource.addEventListener("job_queued", e => {
            pendingJobs.push(JSON.parse(e.data));
            renderQueue();
        });

        eventSource.addEventListener("job_started", e => {
            const job = JSON.parse(e.data);
            pendingJobs = pendingJobs.filter(j => j.id !== job.id);
            activeJobs = [job];
            renderQueue();
        });

        eventSource.addEventListener("job_finished", e => {
            const job = JSON.parse(e.data);
            activeJobs = activeJobs.filter(j => j.id !== job.id);
            renderQueue();
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

    let presets = [];
    let editingPreset = null;
    let showingNewForm = false;

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
        let props = "";
        props += "<dt>Args</dt><dd>" + esc(p.ffmpeg_args) + "</dd>";
        props += "<dt>Container</dt><dd>" + (p.output_container ? esc(p.output_container) : "Keep original") + "</dd>";

        return '<div class="preset-card">'
            + '<div class="preset-card-header">'
            + '<span class="preset-card-name">' + esc(p.name) + '</span>'
            + '<div class="preset-card-actions">'
            + '<button class="btn" data-action="edit" data-name="' + esc(p.name) + '">Edit</button>'
            + '<button class="btn btn-danger" data-action="delete" data-name="' + esc(p.name) + '">Delete</button>'
            + '</div></div>'
            + '<dl class="preset-card-props">' + props + '</dl>'
            + '</div>';
    }

    function renderPresetForm(preset) {
        const name = preset ? preset.name : "";
        const args = preset ? preset.ffmpeg_args : "";
        const container = preset ? (preset.output_container || "") : "";

        return '<div class="preset-card editing">'
            + '<div class="form-group"><label>Name</label>'
            + '<input type="text" class="pc-name" value="' + esc(name) + '"></div>'
            + '<div class="form-group"><label>FFmpeg Arguments</label>'
            + '<input type="text" class="pc-args" value="' + esc(args) + '" placeholder="-c:v libx265 -crf 24 -preset slow"></div>'
            + '<div class="form-group"><label>Output Container</label>'
            + '<input type="text" class="pc-container" value="' + esc(container) + '" placeholder="Leave empty to keep original"></div>'
            + '<div class="form-actions">'
            + '<button class="btn pc-cancel">Cancel</button>'
            + '<button class="btn btn-primary pc-save">Save</button>'
            + '</div></div>';
    }

    function attachFormListeners(form, originalName) {
        const isNew = originalName === null;

        form.querySelector(".pc-save").addEventListener("click", async () => {
            const name = form.querySelector(".pc-name").value.trim();
            const args = form.querySelector(".pc-args").value.trim();
            const container = form.querySelector(".pc-container").value.trim() || null;

            if (!name || !args) {
                alert("Name and arguments are required.");
                return;
            }

            try {
                if (isNew) {
                    await api("POST", "/api/presets", { name, ffmpeg_args: args, output_container: container });
                    showingNewForm = false;
                } else {
                    await api("POST", "/api/presets", { name, ffmpeg_args: args, output_container: container });
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

    connectSSE();
})();
