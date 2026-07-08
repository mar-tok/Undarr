export async function api(method, path, body) {
    const opts = { method, headers: {} };
    if (body !== undefined) {
        opts.headers["Content-Type"] = "application/json";
        opts.body = JSON.stringify(body);
    }
    const res = await fetch(path, opts);
    if (res.status === 204) return null;
    if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || res.statusText);
    }
    return res.json();
}

export function formatBytes(bytes) {
    if (bytes == null) return "-";
    if (bytes < 1024) return bytes + " B";
    if (bytes < 1048576) return Math.ceil(bytes / 1024) + " KB";
    if (bytes < 1073741824) return Math.ceil(bytes / 1048576) + " MB";
    return (bytes / 1073741824).toFixed(1) + " GB";
}

export function basename(path) {
    return path.split(/[\\/]/).pop() || path;
}

export function esc(s) {
    if (s == null) return "";
    const d = document.createElement("div");
    d.textContent = String(s);
    return d.innerHTML;
}

export function formatDuration(secs) {
    if (secs == null || secs < 0) return "-";
    const h = Math.floor(secs / 3600);
    const m = Math.floor((secs % 3600) / 60);
    const s = Math.floor(secs % 60);
    if (h > 0) return h + "h " + m + "m " + s + "s";
    if (m > 0) return m + "m " + s + "s";
    return s + "s";
}

export function formatDate(iso) {
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
