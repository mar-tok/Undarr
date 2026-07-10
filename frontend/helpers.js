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

export function escAttr(s) {
    return String(s).replace(/&/g, "&amp;").replace(/'/g, "&#39;").replace(/"/g, "&quot;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
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

export function getFormSnapshot(container) {
    const vals = [];
    container.querySelectorAll("input, select, textarea").forEach(el => {
        if (el.type === "checkbox") vals.push(el.checked ? "1" : "0");
        else vals.push(el.value);
    });
    return vals.join("\0");
}

function sizeNumberInput(input) {
    const digits = Math.max((input.value || input.placeholder || "0").length, 1);
    input.style.width = (digits * 12 + 16) + "px";
}

export function wrapNumberInputs(container) {
    container.querySelectorAll('input[type="number"]').forEach(input => {
        if (input.parentElement.classList.contains("number-wrap")) return;
        sizeNumberInput(input);
        input.addEventListener("input", () => sizeNumberInput(input));
        const wrap = document.createElement("span");
        wrap.className = "number-wrap";
        input.parentNode.insertBefore(wrap, input);
        const btnDec = document.createElement("button");
        btnDec.type = "button";
        btnDec.className = "number-btn";
        btnDec.innerHTML = '<img src="minus.svg" alt="-">';
        const btnInc = document.createElement("button");
        btnInc.type = "button";
        btnInc.className = "number-btn";
        btnInc.innerHTML = '<img src="plus.svg" alt="+">';
        wrap.append(btnDec, input, btnInc);
        btnDec.addEventListener("click", () => { input.stepDown(); input.dispatchEvent(new Event("input", { bubbles: true })); });
        btnInc.addEventListener("click", () => { input.stepUp(); input.dispatchEvent(new Event("input", { bubbles: true })); });
    });
}

export function clearValidation(container) {
    container.querySelectorAll(".invalid").forEach(el => el.classList.remove("invalid"));
    container.querySelectorAll(".field-error").forEach(el => el.remove());
}

export function setError(input, msg) {
    input.classList.add("invalid");
    const err = document.createElement("div");
    err.className = "field-error";
    err.textContent = msg;
    input.parentElement.appendChild(err);
}
