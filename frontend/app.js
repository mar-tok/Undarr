(function () {
    let activeJobs = [];
    let pendingJobs = [];
    let paused = false;
    let eventSource = null;

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

    connectSSE();
})();
