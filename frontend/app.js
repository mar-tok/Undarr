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

    connectSSE();
})();
