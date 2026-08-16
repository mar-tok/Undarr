import { api, esc, escAttr } from "./helpers.js";
import { openDirBrowser } from "./dir-browser.js";
import { openPreviewModal } from "./libraries.js";

let navigateFn = null;
let devices = [];

const state = { codec: null, tier: null, path: null, importType: null, name: "" };

const PRESETS = {
    "hevc:transparent": "HEVC Transparent",
    "hevc:space_saver": "HEVC Space Saver",
    "av1:transparent": "AV1 Transparent",
    "av1:space_saver": "AV1 Space Saver",
};

export function initSetup(navigate) {
    navigateFn = navigate;
}

export async function checkFirstRun() {
    try {
        const libs = await api("GET", "/api/libraries");
        return libs.length === 0;
    } catch {
        return false;
    }
}

export async function loadSetupView() {
    const flow = document.getElementById("setup-flow");
    flow.innerHTML = "";
    state.codec = null;
    state.tier = null;
    state.path = null;
    state.importType = null;
    state.name = "";

    try {
        devices = await api("GET", "/api/devices");
    } catch {
        devices = [];
    }

    renderWelcome();
}

function renderWelcome() {
    const flow = document.getElementById("setup-flow");
    const header = document.createElement("div");
    header.className = "setup-header";

    header.innerHTML = `
        <h2><span class="accent">Un</span>darr Quick Start</h2>
        <p class="setup-text">
            Undarr transcodes your media libraries to match a target format and quality level. Transcoding decodes each video file and re-encodes it into a different format. Pick a preset, point it to a directory, and Undarr will match videos to the preset.
        </p>
        <p class="setup-text">
            Transcoding discards data from the original file, but discarded data is not the same as lost quality. Most of what gets removed is either redundant or under the threshold of perception. Every major streaming service transcodes aggressively, and billions of viewers don't notice. A properly configured preset will save you space with no difference in perceived quality, at the cost of spending energy and time to do so. That said, the data is technically unrecoverable. It is destructive. Acquiring media in your desired format is therefore always preferable to transcoding it after the fact.
        </p>
        <p class="setup-text">
            Whether to transcode an existing library or not is up to you. The built-in presets are tuned conservatively and to err on the side of caution. Ultimately, the user must weigh the file size savings against the possible risk of perceived quality loss.
        </p>`;

    flow.appendChild(header);
    renderCodecStep();
}

function renderCodecStep() {
    const flow = document.getElementById("setup-flow");
    const step = document.createElement("div");
    step.className = "setup-step";
    step.id = "step-codec";

    let deviceNote = "";
    if (devices.length) {
        const names = devices.map(d => d.name);
        deviceNote = `<p class="setup-note">Encoding hardware on this server: ${esc(names.join(", "))}</p>`;
    }

    step.innerHTML = `
        <h3>Format</h3>
        <p class="setup-text">What format should your files be transcoded to?</p>
        <div class="setup-cards">
            <button class="setup-card" data-value="hevc">
                <span class="setup-card-title">HEVC (H.265)</span>
                <span class="setup-card-desc">Widely supported. A big compression improvement over H.264. Pick this if device compatibility matters to you.</span>
            </button>
            <button class="setup-card" data-value="av1">
                <span class="setup-card-title">AV1</span>
                <span class="setup-card-desc">Better compression than HEVC, producing smaller files. Rarely compatible with older devices and players.</span>
            </button>
        </div>
        ${deviceNote}`;

    bindCards(step, (card) => {
        state.codec = card.dataset.value;
        completeStep(step, card.dataset.value === "hevc" ? "HEVC" : "AV1");
        renderQualityStep();
    });

    flow.appendChild(step);
    step.scrollIntoView({ behavior: "smooth", block: "start" });
}

function renderQualityStep() {
    const flow = document.getElementById("setup-flow");
    const step = document.createElement("div");
    step.className = "setup-step";
    step.id = "step-quality";

    step.innerHTML = `
        <h3>Quality</h3>
        <p class="setup-text">How should Undarr balance file size against quality?</p>
        <div class="setup-cards">
            <button class="setup-card" data-value="transparent">
                <span class="setup-card-title">Transparent</span>
                <span class="setup-card-desc">Prioritize quality. The output is perceptually identical to the original. Typical file size reductions are around ${state.codec === "av1" ? "50-60%" : "40-50%"}.</span>
            </button>
            <button class="setup-card" data-value="space_saver">
                <span class="setup-card-title">Space Saver</span>
                <span class="setup-card-desc">Prioritize space. Compresses more aggressively. The difference is hard to spot on most content but may be visible in dark, high-detail and dynamic scenes.</span>
            </button>
        </div>`;

    bindCards(step, (card) => {
        state.tier = card.dataset.value;
        completeStep(step, card.dataset.value === "transparent" ? "Transparent" : "Space Saver");
        renderPathStep();
    });

    flow.appendChild(step);
    step.scrollIntoView({ behavior: "smooth", block: "start" });
}

function renderPathStep() {
    const flow = document.getElementById("setup-flow");
    const step = document.createElement("div");
    step.className = "setup-step";
    step.id = "step-path";

    step.innerHTML = `
        <h3>Library</h3>
        <p class="setup-text">
            Pick the parent directory that contains all the video files you want to be affected. Undarr scans all subfolders automatically, so in most cases you'd select <code>/media/category</code> rather than individual folders containing files.
        </p>
        <div class="setup-path-display" style="display:none"></div>
        <button class="btn" id="setup-browse">Browse</button>`;

    const pathDisplay = step.querySelector(".setup-path-display");

    step.querySelector("#setup-browse").addEventListener("click", () => {
        openDirBrowser(state.path, (selected) => {
            state.path = selected;
            state.name = selected.split("/").filter(Boolean).pop() || "library";
            pathDisplay.textContent = selected;
            pathDisplay.style.display = "";

            removeStepsAfter(step);
            completeStep(step, selected);
            renderImportStep();
        });
    });

    flow.appendChild(step);
    step.scrollIntoView({ behavior: "smooth", block: "start" });
}

function renderImportStep() {
    const flow = document.getElementById("setup-flow");
    const step = document.createElement("div");
    step.className = "setup-step";
    step.id = "step-import";

    step.innerHTML = `
        <h3>Existing Files</h3>
        <p class="setup-text">Your folder may already have files in it. How should Undarr process them?</p>
        <div class="setup-cards">
            <button class="setup-card" data-value="scan">
                <span class="setup-card-title">Process All</span>
                <span class="setup-card-desc">Scan every video file and transcode them according to the preset. Pick this if the files haven't been transcoded before.</span>
            </button>
            <button class="setup-card" data-value="processed">
                <span class="setup-card-title">Skip Existing</span>
                <span class="setup-card-desc">Only files added after this point will be processed. Pick this if your library has already been transcoded, or if you only want to handle new additions.</span>
            </button>
        </div>`;

    bindCards(step, (card) => {
        state.importType = card.dataset.value;
        completeStep(step, card.dataset.value === "scan" ? "Process All" : "Skip Existing");
        renderSummary();
    });

    flow.appendChild(step);
    step.scrollIntoView({ behavior: "smooth", block: "start" });
}

function renderSummary() {
    const flow = document.getElementById("setup-flow");
    const step = document.createElement("div");
    step.className = "setup-step";
    step.id = "step-summary";

    const presetName = resolvePresetName();

    step.innerHTML = `
        <h3>Summary</h3>
        <div class="form-group" style="max-width:320px">
            <label>Library Name</label>
            <input type="text" id="setup-lib-name" value="${escAttr(state.name)}">
        </div>
        <dl class="setup-props">
            <dt>Preset</dt><dd>${esc(presetName)}</dd>
            <dt>Path</dt><dd>${esc(state.path)}</dd>
            <dt>Existing files</dt><dd>${state.importType === "scan" ? "Process all" : "Skip existing"}</dd>
        </dl>
        <div class="setup-actions">
            <button class="btn" id="setup-preview">Preview</button>
            <button class="btn btn-primary" id="setup-create">Create Library</button>
        </div>`;

    const nameInput = step.querySelector("#setup-lib-name");
    nameInput.addEventListener("input", () => { state.name = nameInput.value.trim(); });

    step.querySelector("#setup-preview").addEventListener("click", () => {
        if (!state.path) return;
        openPreviewModal(null, {
            name: state.name || "New Library",
            paths: [state.path],
            skip_rules: [],
            path_patterns: [],
            new_file_delay: 0,
            new_file_delay_unit: "minutes",
        });
    });

    step.querySelector("#setup-create").addEventListener("click", async () => {
        const name = state.name || state.path.split("/").filter(Boolean).pop() || "library";
        const btn = step.querySelector("#setup-create");
        btn.disabled = true;
        btn.textContent = "Creating...";

        try {
            await api("POST", "/api/libraries", {
                name,
                paths: [state.path],
                preset: presetName,
                watch: true,
                skip_rules: [],
                path_patterns: [],
                scan_interval: 0,
                scan_unit: "minutes",
                mark_existing_processed: state.importType === "processed",
                new_file_delay: 0,
                new_file_delay_unit: "minutes",
            });
            if (state.importType === "scan") {
                api("POST", `/api/libraries/${encodeURIComponent(name)}/scan`).catch(() => {});
            }
            navigateFn("overview");
        } catch (e) {
            btn.disabled = false;
            btn.textContent = "Create Library";
            alert(e.message);
        }
    });

    flow.appendChild(step);
    step.scrollIntoView({ behavior: "smooth", block: "start" });
}

function bindCards(step, onSelect) {
    step.querySelectorAll(".setup-card").forEach(card => {
        card.addEventListener("click", () => {
            step.querySelectorAll(".setup-card").forEach(c => c.classList.remove("selected"));
            card.classList.add("selected");
            removeStepsAfter(step);
            onSelect(card);
        });
    });
}

function resolvePresetName() {
    return PRESETS[state.codec + ":" + state.tier] || "HEVC Transparent";
}

function completeStep(step, chosenLabel) {
    step.classList.add("done");
    if (chosenLabel) {
        const tag = document.createElement("div");
        tag.className = "setup-chosen";
        tag.innerHTML = `<span>${esc(chosenLabel)}</span> <button class="setup-change">Change</button>`;
        tag.querySelector(".setup-change").addEventListener("click", () => {
            changeStep(step);
        });
        step.appendChild(tag);
    }
}

function changeStep(step) {
    step.classList.remove("done");
    const chosen = step.querySelector(".setup-chosen");
    if (chosen) chosen.remove();

    step.querySelectorAll(".setup-card").forEach(c => c.classList.remove("selected"));

    removeStepsAfter(step);
}

function removeStepsAfter(step) {
    const flow = document.getElementById("setup-flow");
    while (step.nextElementSibling) {
        step.nextElementSibling.remove();
    }
}
