import { api, esc, escAttr, getFormSnapshot, clearValidation, setError } from "./helpers.js";

const EVENTS = [
    { id: "job_failed", label: "Job failed", tip: "Sends a message when a transcode job fails.<br>Includes file name, error output, preset, and device." },
    { id: "queue_stalled", label: "Queue stalled", tip: "Sends a message when jobs are waiting and none can start.<br>Names what blocks them, such as a paused library or a disabled device.<br>Sends once per stall." },
    { id: "daily_digest", label: "Daily digest", tip: "Sends a summary of the previous day at the chosen hour, in the server's local time.<br>Includes completed/failed counts and space saved.<br>Sends nothing for a day without jobs." },
    { id: "top_reduction", label: "New top reduction", tip: "Sends a message when a completed job has the best size reduction in the job history.<br>Includes the file name and the old and new sizes." },
];

const TEMPLATES = [
    { id: "discord", label: "Discord" },
    { id: "ntfy", label: "ntfy" },
    { id: "gotify", label: "Gotify" },
    { id: "generic", label: "JSON" },
];

const URL_PLACEHOLDERS = {
    discord: "https://discord.com/api/webhooks/...",
    ntfy: "https://ntfy.sh/your-topic",
    gotify: "https://gotify.example.com/message?token=...",
    generic: "https://example.com/webhook",
};

let webhooks = [];
let initialSnapshot = "";

function checkChanged() {
    const pane = document.getElementById("stab-notifications");
    document.getElementById("btn-save-webhooks").disabled = getFormSnapshot(pane) === initialSnapshot;
}

function renderWebhooks() {
    const container = document.getElementById("webhooks-list");
    if (!webhooks.length) {
        container.innerHTML = '<p class="section-empty">No webhooks configured.</p>';
        return;
    }

    let html = "";
    for (let i = 0; i < webhooks.length; i++) {
        const wh = webhooks[i];
        const templateOptions = TEMPLATES.map(t =>
            `<option value="${t.id}"${t.id === wh.template ? " selected" : ""}>${esc(t.label)}</option>`
        ).join("");
        const eventChecks = EVENTS.map(ev => {
            const checked = wh.events.includes(ev.id) ? "checked" : "";
            return `<label class="webhook-event" data-tooltip="${ev.tip}">
                <input type="checkbox" role="switch" data-idx="${i}" data-event="${ev.id}" ${checked}> ${esc(ev.label)}
            </label>`;
        }).join("");

        const hasDigest = wh.events.includes("daily_digest");
        const hourOptions = Array.from({ length: 24 }, (_, h) => {
            const label = String(h).padStart(2, "0") + ":00";
            return `<option value="${h}"${wh.digest_hour === h ? " selected" : ""}>${label}</option>`;
        }).join("");

        html += `<div class="inline-form">
            <div class="webhook-header">
                <div class="webhook-meta">
                    <select class="webhook-template-select" data-idx="${i}">${templateOptions}</select>
                    <label class="webhook-enabled" data-tooltip="A disabled webhook stays configured and sends nothing.">
                        <input type="checkbox" role="switch" data-idx="${i}" data-field="enabled" ${wh.enabled ? "checked" : ""}> Enabled
                    </label>
                </div>
                <button class="btn-icon webhook-delete" data-idx="${i}" data-tooltip="Remove"><img src="trash.svg" alt="Remove"></button>
            </div>
            <div class="form-group">
                <label>Webhook URL</label>
                <div class="webhook-url-row">
                    <input type="text" class="webhook-url" data-idx="${i}" value="${escAttr(wh.url)}" placeholder="${URL_PLACEHOLDERS[wh.template] || ""}">
                    <button class="btn btn-sm webhook-test" data-idx="${i}" data-tooltip="Sends a test message to this URL. Does not need to be saved first.">Test</button>
                </div>
            </div>
            <div class="form-row">
                <div class="form-group">
                    <label>Events</label>
                    <div class="webhook-events">${eventChecks}</div>
                </div>
                <div class="form-group webhook-digest-hour" data-idx="${i}" style="${hasDigest ? "" : "display:none"}">
                    <label>Digest time</label>
                    <select class="digest-hour-select" data-idx="${i}">${hourOptions}</select>
                </div>
            </div>
        </div>`;
    }

    container.innerHTML = html;

    container.querySelectorAll(".webhook-template-select").forEach(sel => {
        sel.addEventListener("change", () => {
            const idx = +sel.dataset.idx;
            webhooks[idx].template = sel.value;
            const urlInput = container.querySelector(`.webhook-url[data-idx="${idx}"]`);
            if (urlInput) urlInput.placeholder = URL_PLACEHOLDERS[sel.value] || "";
            checkChanged();
        });
    });
    container.querySelectorAll(".webhook-url").forEach(input => {
        input.addEventListener("input", () => {
            webhooks[+input.dataset.idx].url = input.value;
            checkChanged();
        });
    });
    container.querySelectorAll("[data-field='enabled']").forEach(cb => {
        cb.addEventListener("change", () => {
            webhooks[+cb.dataset.idx].enabled = cb.checked;
            checkChanged();
        });
    });
    container.querySelectorAll("[data-event]").forEach(cb => {
        cb.addEventListener("change", () => {
            const wh = webhooks[+cb.dataset.idx];
            const ev = cb.dataset.event;
            if (cb.checked && !wh.events.includes(ev)) wh.events.push(ev);
            else wh.events = wh.events.filter(e => e !== ev);
            if (ev === "daily_digest") {
                container.querySelector(`.webhook-digest-hour[data-idx="${cb.dataset.idx}"]`).style.display = cb.checked ? "" : "none";
            }
            checkChanged();
        });
    });
    container.querySelectorAll(".digest-hour-select").forEach(sel => {
        sel.addEventListener("change", () => {
            webhooks[+sel.dataset.idx].digest_hour = +sel.value;
            checkChanged();
        });
    });
    container.querySelectorAll(".webhook-delete").forEach(btn => {
        btn.addEventListener("click", () => {
            const wh = webhooks[+btn.dataset.idx];
            if (wh.url.trim() && !confirm(`Remove webhook "${wh.url}"?\n\nUndarr stops sending notifications to this URL once you save.`)) return;
            webhooks.splice(+btn.dataset.idx, 1);
            renderWebhooks();
            checkChanged();
        });
    });
    container.querySelectorAll(".webhook-test").forEach(btn => {
        btn.addEventListener("click", async () => {
            const wh = webhooks[+btn.dataset.idx];
            if (!wh.url.trim()) { alert("Enter a webhook URL first."); return; }
            btn.disabled = true;
            btn.textContent = "...";
            try {
                await api("POST", "/api/webhooks/test", { url: wh.url, template: wh.template });
                btn.textContent = "Sent";
                setTimeout(() => { btn.textContent = "Test"; btn.disabled = false; }, 4000);
            } catch (e) {
                alert("Test failed: " + e.message);
                btn.textContent = "Test";
                btn.disabled = false;
            }
        });
    });
}

export async function loadNotifications() {
    try {
        webhooks = await api("GET", "/api/webhooks");
    } catch {
        webhooks = [];
    }
    renderWebhooks();
    initialSnapshot = getFormSnapshot(document.getElementById("stab-notifications"));
    checkChanged();
}

export function initNotifications() {
    document.getElementById("btn-add-webhook").addEventListener("click", () => {
        webhooks.push({ url: "", template: "discord", events: ["job_failed"], enabled: true, digest_hour: 0 });
        renderWebhooks();
        checkChanged();
        const inputs = document.querySelectorAll(".webhook-url");
        inputs[inputs.length - 1].focus();
    });

    document.getElementById("btn-save-webhooks").addEventListener("click", async () => {
        const pane = document.getElementById("stab-notifications");
        clearValidation(pane);
        const empty = webhooks.findIndex(wh => !wh.url.trim());
        if (empty !== -1) {
            setError(pane.querySelector(`.webhook-url[data-idx="${empty}"]`), "Webhook URL cannot be empty");
            return;
        }
        try {
            webhooks = await api("PUT", "/api/webhooks", webhooks);
            renderWebhooks();
            initialSnapshot = getFormSnapshot(document.getElementById("stab-notifications"));
            checkChanged();
        } catch (e) {
            alert(e.message);
        }
    });
}
