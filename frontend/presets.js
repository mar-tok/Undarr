import { api, esc, escAttr } from "./helpers.js";

let presets = [];
let editingPresetName = null;
let creatingNewPreset = false;

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

export function loadPresets() {
    return api("GET", "/api/presets").then(data => {
        presets = data;
        renderPresets();
    });
}

function renderPresets() {
    const container = document.getElementById("preset-grid");
    let html = "";
    if (creatingNewPreset) {
        html += renderPresetFormCard(null);
    }
    html += presets.map(p => {
        if (editingPresetName === p.name) return renderPresetFormCard(p);
        return renderPresetViewCard(p);
    }).join("");
    container.innerHTML = html;

    const editCard = container.querySelector(".preset-card.editing");
    if (editCard) attachFormCardListeners(editCard, creatingNewPreset ? null : editingPresetName);
}

function renderPresetViewCard(p) {
    const data = parsePresetData(p);

    let videoHtml = "";
    videoHtml += `<dt>Args</dt><dd>${esc(p.ffmpeg_args)}</dd>`;
    videoHtml += `<dt>Container</dt><dd>${p.output_container ? esc(p.output_container) : "Keep original"}</dd>`;
    if (data.resolutionCap) {
        videoHtml += `<dt>Resolution Cap</dt><dd>${esc(String(data.resolutionCap))}p</dd>`;
    }

    let audioHtml = "";
    if (data.audioMode === "configure" && data.audio) {
        const a = data.audio;
        const tierLabel = (t) => {
            if (!t || t.codec === "copy") return "Copy";
            const cl = AUDIO_TIER_CODEC_OPTIONS.find(c => c.value === t.codec)?.label || t.codec;
            return t.bitrate ? `${cl} ${t.bitrate}` : cl;
        };
        audioHtml += `<dt>Stereo</dt><dd>${esc(tierLabel(a.stereo))}</dd>`;
        audioHtml += `<dt>Surround</dt><dd>${esc(tierLabel(a.surround))}</dd>`;
        if (a.add_stereo_downmix && a.add_stereo_downmix !== "never") {
            const dmxLabel = a.add_stereo_downmix === "if_no_stereo" ? "If no stereo" : "Always";
            audioHtml += `<dt>Downmix</dt><dd>${esc(dmxLabel)}</dd>`;
            if (a.downmix_bitrate) audioHtml += `<dt>Dmx Bitrate</dt><dd>${esc(a.downmix_bitrate)}</dd>`;
        }
        if (a.languages && a.languages.length) {
            audioHtml += `<dt>Languages</dt><dd>${esc(a.languages.join(", "))}</dd>`;
        }
        if (a.remove_commentary) {
            audioHtml += `<dt>Commentary</dt><dd>Remove</dd>`;
        }
    }

    let subtitleHtml = "";
    if (data.subtitleMode !== "keep") {
        const s = data.subtitle;
        if (data.subtitleMode === "remove") {
            subtitleHtml += `<dt>Mode</dt><dd>Remove all</dd>`;
        } else {
            subtitleHtml += `<dt>Mode</dt><dd>Keep by language</dd>`;
            if (s && s.languages && s.languages.length) {
                subtitleHtml += `<dt>Languages</dt><dd>${esc(s.languages.join(", "))}</dd>`;
            }
            if (s && s.remove_commentary) {
                subtitleHtml += `<dt>Commentary</dt><dd>Remove</dd>`;
            }
        }
    }

    return `<div class="preset-card">
        <div class="preset-card-header">
            <span class="preset-card-name">${esc(p.name)}</span>
            <div class="preset-card-actions">
                <button class="btn" data-action="edit" data-name="${escAttr(p.name)}">Edit</button>
                <button class="btn btn-danger" data-action="delete" data-name="${escAttr(p.name)}">Delete</button>
            </div>
        </div>
        <div class="preset-card-section"><span class="preset-card-section-label">Video</span><dl class="preset-card-props">${videoHtml}</dl></div>
        ${audioHtml ? `<div class="preset-card-section"><span class="preset-card-section-label">Audio</span><dl class="preset-card-props">${audioHtml}</dl></div>` : ""}
        ${subtitleHtml ? `<div class="preset-card-section"><span class="preset-card-section-label">Subtitles</span><dl class="preset-card-props">${subtitleHtml}</dl></div>` : ""}
    </div>`;
}

function buildSubtitleModeOptionsHTML(selected) {
    return SUBTITLE_MODE_OPTIONS.map(c =>
        `<option value="${escAttr(c.value)}"${c.value === selected ? " selected" : ""}>${esc(c.label)}</option>`
    ).join("");
}

function buildResolutionCapOptionsHTML(selected) {
    return RESOLUTION_CAP_OPTIONS.map(c =>
        `<option value="${escAttr(c.value)}"${c.value === (selected || "") ? " selected" : ""}>${esc(c.label)}</option>`
    ).join("");
}

function buildAudioModeOptionsHTML(selected) {
    return AUDIO_MODE_OPTIONS.map(c =>
        `<option value="${escAttr(c.value)}"${c.value === selected ? " selected" : ""}>${esc(c.label)}</option>`
    ).join("");
}

function buildAudioTierCodecOptionsHTML(selected) {
    return AUDIO_TIER_CODEC_OPTIONS.map(c =>
        `<option value="${escAttr(c.value)}"${c.value === selected ? " selected" : ""}>${esc(c.label)}</option>`
    ).join("");
}

function renderPresetFormCard(preset) {
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

    return `<div class="preset-card editing">
        <div class="form-group">
            <label data-tooltip="A display name for this preset.<br>Used to identify it when assigning to libraries. Does not affect encoding.">Name</label>
            <input type="text" class="pc-name" value="${escAttr(name)}">
        </div>
        <div class="preset-tabs">
            <button class="preset-tab active" data-tab="video" type="button">Video</button>
            <button class="preset-tab" data-tab="audio" type="button">Audio</button>
            <button class="preset-tab" data-tab="subtitle" type="button">Subtitles</button>
        </div>
        <div class="preset-tab-panel pc-tab-video">
            <div class="form-group">
                <label>FFmpeg Arguments</label>
                <input type="text" class="pc-args" value="${esc(args)}" placeholder="-c:v libx265 -crf 24 -preset slow">
            </div>
            <div class="form-group">
                <label>Output Container</label>
                <input type="text" class="pc-container" value="${esc(container)}" placeholder="Leave empty to keep original">
            </div>
            <div class="form-group pc-rescap-group">
                <label data-tooltip="Maximum output resolution (height).<br>Files above the cap are downscaled while preserving aspect ratio.<br>Files at or below the cap pass through at original resolution.">Resolution Cap</label>
                <select class="pc-rescap">${buildResolutionCapOptionsHTML(resCap)}</select>
            </div>
        </div>
        <div class="preset-tab-panel pc-tab-audio" style="display:none">
            <div class="form-group">
                <label data-tooltip="Audio handling mode.<br><em>Copy</em> passes through all audio streams unchanged.<br><em>Configure</em> lets you set per-tier codec, filtering, and downmix options.">Mode</label>
                <select class="pc-audio-mode">${buildAudioModeOptionsHTML(audioMode)}</select>
            </div>
            <div class="pc-audio-config"${configHidden}>
                <div class="audio-tier">
                    <label class="section-label" data-tooltip="Rules for audio streams with 1-2 channels (mono, stereo).<br>Streams already matching the target codec and bitrate are copied automatically.">Stereo, 1-2 channels</label>
                    <div class="form-row form-row-2">
                        <div class="form-group">
                            <label data-tooltip="Codec for stereo audio streams (1-2 channels).<br><em>Copy</em> keeps the original codec.<br>Other codecs re-encode streams that don't already match.">Codec</label>
                            <select class="pc-stereo-codec">${buildAudioTierCodecOptionsHTML(stereoCodec)}</select>
                        </div>
                        <div class="form-group pc-stereo-bitrate-group"${stereoBitrateHidden}>
                            <label data-tooltip="Maximum bitrate for stereo streams.<br>Streams at or below this bitrate (in the target codec) are copied.<br>Streams above are re-encoded at this bitrate.<br>If left empty, streams already in the target codec are always copied at their original bitrate. Re-encoded streams use FFmpeg's codec default.">Bitrate</label>
                            <input type="text" class="pc-stereo-bitrate" value="${escAttr(stereoBitrate)}" placeholder="e.g. 160k">
                        </div>
                    </div>
                </div>
                <div class="audio-tier">
                    <label class="section-label" data-tooltip="Rules for audio streams with 3 or more channels (5.1, 7.1, etc).<br>Streams already matching the target codec and bitrate are copied automatically.">Surround, 3+ channels</label>
                    <div class="form-row form-row-2">
                        <div class="form-group">
                            <label data-tooltip="Codec for surround audio streams (more than 2 channels).<br><em>Copy</em> keeps the original codec.<br>Other codecs re-encode streams that don't already match.">Codec</label>
                            <select class="pc-surround-codec">${buildAudioTierCodecOptionsHTML(surroundCodec)}</select>
                        </div>
                        <div class="form-group pc-surround-bitrate-group"${surroundBitrateHidden}>
                            <label data-tooltip="Maximum bitrate for surround streams.<br>Streams at or below this bitrate (in the target codec) are copied.<br>Streams above are re-encoded at this bitrate.<br>If left empty, streams already in the target codec are always copied at their original bitrate. Re-encoded streams use FFmpeg's codec default.">Bitrate</label>
                            <input type="text" class="pc-surround-bitrate" value="${escAttr(surroundBitrate)}" placeholder="e.g. 640k">
                        </div>
                    </div>
                    <div class="form-row form-row-2">
                        <div class="form-group">
                            <label data-tooltip="Add a stereo AAC track alongside each surround stream for device compatibility.<br><em>Always</em> adds a downmix regardless of existing stereo tracks.<br><em>If no stereo track exists</em> only adds a downmix when the file has no stereo streams after filtering.">Stereo downmix</label>
                            <select class="pc-downmix">
                                <option value="never"${downmixMode === "never" ? " selected" : ""}>Never</option>
                                <option value="always"${downmixMode === "always" ? " selected" : ""}>Always</option>
                                <option value="if_no_stereo"${downmixMode === "if_no_stereo" ? " selected" : ""}>If no stereo track exists</option>
                            </select>
                        </div>
                        <div class="form-group pc-downmix-bitrate-group"${downmixBitrateHidden}>
                            <label data-tooltip="Bitrate for the stereo AAC downmix track added alongside each surround stream.">Bitrate</label>
                            <input type="text" class="pc-downmix-bitrate" value="${escAttr(downmixBitrate)}" placeholder="e.g. 160k">
                        </div>
                    </div>
                </div>
                <div class="audio-tier">
                    <label class="section-label" data-tooltip="Filter out unwanted audio streams before encoding.<br>Filtered streams are removed entirely from the output file.">Filtering</label>
                    <div class="form-row form-row-2">
                        <div class="form-group">
                            <label data-tooltip="Comma-separated ISO 639 language codes (e.g. <code>eng</code>, <code>jpn</code>, <code>spa</code>).<br>Only streams tagged with these languages are kept.<br>Streams tagged <code>und</code> (undefined) are always kept.<br>Leave empty to keep all languages.">Languages</label>
                            <input type="text" class="pc-languages" value="${escAttr(languages)}" placeholder="e.g. eng, jpn, spa">
                        </div>
                        <label class="audio-checkbox" data-tooltip="Drop audio streams with the <em>commentary</em> disposition flag set by the source."><input type="checkbox" class="pc-remove-commentary"${commentaryChecked}> Remove commentary</label>
                    </div>
                </div>
            </div>
        </div>
        <div class="preset-tab-panel pc-tab-subtitle" style="display:none">
            <div class="form-group">
                <label data-tooltip="Subtitle handling mode.<br><em>Keep all</em> passes through all subtitle streams.<br><em>Remove all</em> strips all subtitle streams from the output.<br><em>Keep by language</em> lets you filter by language and remove commentary tracks.">Mode</label>
                <select class="pc-subtitle-mode">${buildSubtitleModeOptionsHTML(subtitleMode)}</select>
            </div>
            <div class="pc-subtitle-config"${subConfigHidden}>
                <div class="form-row form-row-2">
                    <div class="form-group">
                        <label data-tooltip="Comma-separated ISO 639 language codes (e.g. <code>eng</code>, <code>jpn</code>, <code>spa</code>).<br>Only subtitle streams tagged with these languages are kept.<br>Streams tagged <code>und</code> (undefined) are always kept.<br>Leave empty to keep all languages.">Languages</label>
                        <input type="text" class="pc-sub-languages" value="${escAttr(subLanguages)}" placeholder="e.g. eng, jpn, spa">
                    </div>
                    <label class="audio-checkbox" data-tooltip="Drop subtitle streams with the <em>commentary</em> disposition flag set by the source."><input type="checkbox" class="pc-sub-remove-commentary"${subCommentaryChecked}> Remove commentary</label>
                </div>
            </div>
        </div>
        <div class="form-actions">
            <button class="btn pc-cancel">Cancel</button>
            <button class="btn btn-primary pc-save">Save</button>
        </div>
    </div>`;
}

function attachFormCardListeners(card, originalName) {
    const isNew = originalName === null;

    card.querySelectorAll(".preset-tab").forEach(tab => {
        tab.addEventListener("click", () => {
            card.querySelectorAll(".preset-tab").forEach(t => t.classList.toggle("active", t === tab));
            card.querySelector(".pc-tab-video").style.display = tab.dataset.tab === "video" ? "" : "none";
            card.querySelector(".pc-tab-audio").style.display = tab.dataset.tab === "audio" ? "" : "none";
            card.querySelector(".pc-tab-subtitle").style.display = tab.dataset.tab === "subtitle" ? "" : "none";
        });
    });

    const audioModeSel = card.querySelector(".pc-audio-mode");
    const audioConfigDiv = card.querySelector(".pc-audio-config");
    audioModeSel.addEventListener("change", () => {
        audioConfigDiv.style.display = audioModeSel.value === "copy" ? "none" : "";
    });

    const stereoCodecSel = card.querySelector(".pc-stereo-codec");
    const stereoBitrateGroup = card.querySelector(".pc-stereo-bitrate-group");
    stereoCodecSel.addEventListener("change", () => {
        stereoBitrateGroup.style.display = stereoCodecSel.value === "copy" ? "none" : "";
    });

    const surroundCodecSel = card.querySelector(".pc-surround-codec");
    const surroundBitrateGroup = card.querySelector(".pc-surround-bitrate-group");
    surroundCodecSel.addEventListener("change", () => {
        surroundBitrateGroup.style.display = surroundCodecSel.value === "copy" ? "none" : "";
    });

    const downmixSelect = card.querySelector(".pc-downmix");
    const downmixBitrateGroup = card.querySelector(".pc-downmix-bitrate-group");
    downmixSelect.addEventListener("change", () => {
        downmixBitrateGroup.style.display = downmixSelect.value !== "never" ? "" : "none";
    });

    const subtitleModeSel = card.querySelector(".pc-subtitle-mode");
    const subtitleConfigDiv = card.querySelector(".pc-subtitle-config");
    subtitleModeSel.addEventListener("change", () => {
        subtitleConfigDiv.style.display = subtitleModeSel.value === "keep_by_language" ? "" : "none";
    });

    card.querySelector(".pc-save").addEventListener("click", async () => {
        const newName = card.querySelector(".pc-name").value.trim();
        const args = card.querySelector(".pc-args").value.trim();
        const container = card.querySelector(".pc-container").value.trim() || null;

        if (!newName || !args) {
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
        const audioModeVal = card.querySelector(".pc-audio-mode").value;
        if (audioModeVal === "copy") {
            audio = { stereo: { codec: "copy" }, surround: { codec: "copy" } };
        } else {
            const stereoCodecVal = card.querySelector(".pc-stereo-codec").value;
            const stereo = { codec: stereoCodecVal };
            if (stereoCodecVal !== "copy") {
                const brEl = card.querySelector(".pc-stereo-bitrate");
                validateBitrate(brEl);
                const br = brEl.value.trim();
                if (br) stereo.bitrate = br;
            }
            const surroundCodecVal = card.querySelector(".pc-surround-codec").value;
            const surround = { codec: surroundCodecVal };
            if (surroundCodecVal !== "copy") {
                const brEl = card.querySelector(".pc-surround-bitrate");
                validateBitrate(brEl);
                const br = brEl.value.trim();
                if (br) surround.bitrate = br;
            }
            audio = { stereo, surround };
            const dmxMode = card.querySelector(".pc-downmix").value;
            if (dmxMode !== "never") {
                audio.add_stereo_downmix = dmxMode;
                const dmxBrEl = card.querySelector(".pc-downmix-bitrate");
                validateBitrate(dmxBrEl);
                const dmxBr = dmxBrEl.value.trim();
                if (dmxBr) audio.downmix_bitrate = dmxBr;
            }
            if (!valid) return;
            const langs = card.querySelector(".pc-languages").value.trim();
            if (langs) audio.languages = langs.split(",").map(s => s.trim()).filter(Boolean);
            if (card.querySelector(".pc-remove-commentary").checked) audio.remove_commentary = true;
        }

        let subtitle = null;
        const subModeVal = card.querySelector(".pc-subtitle-mode").value;
        if (subModeVal !== "keep") {
            subtitle = { mode: subModeVal };
            if (subModeVal === "keep_by_language") {
                const subLangs = card.querySelector(".pc-sub-languages").value.trim();
                if (subLangs) subtitle.languages = subLangs.split(",").map(s => s.trim()).filter(Boolean);
                if (card.querySelector(".pc-sub-remove-commentary").checked) subtitle.remove_commentary = true;
            }
        }

        const resCapVal = card.querySelector(".pc-rescap").value;
        const resolution_cap = resCapVal ? parseInt(resCapVal, 10) : null;

        try {
            if (isNew) {
                await api("POST", "/api/presets", { name: newName, ffmpeg_args: args, output_container: container, audio, subtitle, resolution_cap });
                creatingNewPreset = false;
            } else {
                await api("PUT", `/api/presets/${encodeURIComponent(originalName)}`, { name: newName, ffmpeg_args: args, output_container: container, audio, subtitle, resolution_cap });
                editingPresetName = null;
            }
            loadPresets();
        } catch (e) {
            alert(e.message);
        }
    });

    card.querySelector(".pc-cancel").addEventListener("click", () => {
        if (isNew) {
            creatingNewPreset = false;
        } else {
            editingPresetName = null;
        }
        renderPresets();
    });
}

export function initPresets() {
    document.getElementById("preset-grid").addEventListener("click", async (e) => {
        const btn = e.target.closest("[data-action]");
        if (!btn) return;
        const name = btn.dataset.name;
        if (btn.dataset.action === "edit") {
            editingPresetName = name;
            creatingNewPreset = false;
            renderPresets();
        } else if (btn.dataset.action === "delete") {
            if (!confirm(`Delete preset "${name}"?`)) return;
            try {
                await api("DELETE", `/api/presets/${encodeURIComponent(name)}`);
                if (editingPresetName === name) editingPresetName = null;
                loadPresets();
            } catch (err) {
                alert(err.message);
            }
        }
    });

    document.getElementById("btn-new-preset").addEventListener("click", () => {
        creatingNewPreset = !creatingNewPreset;
        if (creatingNewPreset) editingPresetName = null;
        renderPresets();
    });
}
