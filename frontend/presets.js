import { api, esc, escAttr, getFormSnapshot, wrapNumberInputs, clearValidation, setError } from "./helpers.js";
import { loadDeviceData, isEncoderDisabled, disabledDeviceTooltip } from "./devices.js";

let presets = [];
let editingPresetName = null;
let creatingNewPreset = false;

const CODEC_LABELS = { hevc: "HEVC (H.265)", h264: "H.264 (AVC)", av1: "AV1", vp9: "VP9" };

const QUALITY_LABELS = {
    libx265: "CRF", libx264: "CRF", libsvtav1: "CRF", "libaom-av1": "CRF", "libvpx-vp9": "CRF",
    hevc_nvenc: "CQ", h264_nvenc: "CQ", av1_nvenc: "CQ",
    hevc_qsv: "Global Quality", h264_qsv: "Global Quality", av1_qsv: "Global Quality",
};

const QUALITY_FLAGS = {
    libx265: "crf", libx264: "crf", libsvtav1: "crf", "libaom-av1": "crf", "libvpx-vp9": "crf",
    hevc_nvenc: "cq", h264_nvenc: "cq", av1_nvenc: "cq",
    hevc_qsv: "global_quality", h264_qsv: "global_quality", av1_qsv: "global_quality",
};

const QUALITY_TOOLTIPS = {
    libx264: "Constant Rate Factor (0-51).<br>Lower = better quality, larger files.<br>Good range: 18-23. Default: 23.",
    libx265: "Constant Rate Factor (0-51).<br>Lower = better quality, larger files.<br>Good range: 20-28. Around 20 is visually transparent, 24-28 favors space savings. x265 is more efficient, so values are higher than x264 for similar quality.",
    libsvtav1: "Constant Rate Factor (0-63).<br>Lower = better quality, larger files.<br>Good range: 25-35. AV1 uses a wider scale than H.264/H.265.",
    "libaom-av1": "Constant Rate Factor (0-63).<br>Lower = better quality, larger files.<br>Good range: 23-35. AV1 uses a wider scale than H.264/H.265.",
    "libvpx-vp9": "Constant Rate Factor (0-63).<br>Lower = better quality, larger files.<br>Good range: 15-35.",
    hevc_nvenc: "Constant Quality (0-51).<br>Lower = better quality, larger files.<br>Good range: 19-28. Not directly comparable to software CRF values.",
    h264_nvenc: "Constant Quality (0-51).<br>Lower = better quality, larger files.<br>Good range: 19-28. Not directly comparable to software CRF values.",
    av1_nvenc: "Constant Quality (0-63).<br>Lower = better quality, larger files.<br>Good range: 19-28. Not directly comparable to software CRF values.",
    hevc_qsv: "Intelligent Constant Quality (1-51).<br>Lower = better quality, larger files.<br>Good range: 21-25. Not directly comparable to CRF or CQ values.",
    h264_qsv: "Intelligent Constant Quality (1-51).<br>Lower = better quality, larger files.<br>Good range: 21-25. Not directly comparable to CRF or CQ values.",
    av1_qsv: "Intelligent Constant Quality (1-51).<br>Lower = better quality, larger files.<br>Good range: 21-25. Not directly comparable to CRF or CQ values.",
};

const SPEED_PRESETS = {
    x26x: [
        { value: "ultrafast", label: "ultrafast" }, { value: "superfast", label: "superfast" },
        { value: "veryfast", label: "veryfast" }, { value: "faster", label: "faster" },
        { value: "fast", label: "fast" }, { value: "medium", label: "medium" },
        { value: "slow", label: "slow" }, { value: "slower", label: "slower" },
        { value: "veryslow", label: "veryslow" },
    ],
    nvenc: [
        { value: "p1", label: "p1 (fastest)" }, { value: "p2", label: "p2" },
        { value: "p3", label: "p3" }, { value: "p4", label: "p4" },
        { value: "p5", label: "p5" }, { value: "p6", label: "p6" },
        { value: "p7", label: "p7 (slowest)" },
    ],
    qsv: [
        { value: "veryfast", label: "veryfast" }, { value: "faster", label: "faster" },
        { value: "fast", label: "fast" }, { value: "medium", label: "medium" },
        { value: "slow", label: "slow" }, { value: "slower", label: "slower" },
        { value: "veryslow", label: "veryslow" },
    ],
    svtav1: [
        { value: "0", label: "0 (slowest)" }, { value: "1", label: "1" },
        { value: "2", label: "2" }, { value: "3", label: "3" },
        { value: "4", label: "4" }, { value: "5", label: "5" },
        { value: "6", label: "6" }, { value: "7", label: "7" },
        { value: "8", label: "8" }, { value: "9", label: "9" },
        { value: "10", label: "10" }, { value: "11", label: "11" },
        { value: "12", label: "12" }, { value: "13", label: "13 (fastest)" },
    ],
    aom: [
        { value: "0", label: "0 (slowest)" }, { value: "1", label: "1" },
        { value: "2", label: "2" }, { value: "3", label: "3" },
        { value: "4", label: "4" }, { value: "5", label: "5" },
        { value: "6", label: "6 (fastest)" },
    ],
    vpx: [
        { value: "0", label: "0 (slowest)" }, { value: "1", label: "1" },
        { value: "2", label: "2" }, { value: "3", label: "3" },
        { value: "4", label: "4" }, { value: "5", label: "5 (fastest)" },
    ],
};

const ENCODER_SPEED_MAP = {
    libx265: "x26x", libx264: "x26x",
    hevc_nvenc: "nvenc", h264_nvenc: "nvenc", av1_nvenc: "nvenc",
    hevc_qsv: "qsv", h264_qsv: "qsv", av1_qsv: "qsv",
    libsvtav1: "svtav1",
    "libaom-av1": "aom", "libvpx-vp9": "vpx",
};

const SPEED_FLAG = { aom: "cpu-used", vpx: "cpu-used" };

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

const CONTAINER_OPTIONS = [
    { value: "", label: "Keep original" }, { value: "mkv", label: "mkv" },
    { value: "mp4", label: "mp4" }, { value: "avi", label: "avi" },
    { value: "mov", label: "mov" }, { value: "webm", label: "webm" },
    { value: "ts", label: "ts" },
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

let encoderCache = null;

async function loadEncoderCache() {
    if (!encoderCache) {
        try { encoderCache = await api("GET", "/api/encoders"); } catch { return; }
    }
}

function buildEncoderOptionsHTML() {
    let html = '<option value="">Select encoder...</option>';
    if (!encoderCache) return html;
    for (const [codec, encs] of Object.entries(encoderCache)) {
        const label = CODEC_LABELS[codec] || codec;
        html += `<optgroup label="${escAttr(label)}">`;
        encs.forEach(e => {
            html += `<option value="${escAttr(e.name)}" title="${escAttr(e.description)}">${esc(e.name)}</option>`;
        });
        html += "</optgroup>";
    }
    return html;
}

function encoderHasTenBit(encoder) {
    return Object.values(encoderCache || {}).some(encs => encs.some(e => e.name === encoder && e.ten_bit));
}

function buildSpeedOptionsHTML(encoder, selected) {
    const group = ENCODER_SPEED_MAP[encoder];
    const options = group ? SPEED_PRESETS[group] : [];
    let html = '<option value="">None</option>';
    html += options.map(s =>
        `<option value="${escAttr(s.value)}"${s.value === selected ? " selected" : ""}>${esc(s.label)}</option>`
    ).join("");
    return html;
}

function buildContainerOptionsHTML(selected) {
    return CONTAINER_OPTIONS.map(c =>
        `<option value="${escAttr(c.value)}"${c.value === selected ? " selected" : ""}>${esc(c.label)}</option>`
    ).join("");
}

export function parsePresetData(p) {
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
    const renameFile = p.rename_file || false;
    const tenBit = p.ten_bit || false;
    const data = { encoder: "", quality: "", qualityLabel: "Quality", speed: "", container: p.output_container || "", extraArgs: [], audio, audioMode, subtitle, subtitleMode, resolutionCap, renameFile, tenBit };
    let rest = p.ffmpeg_args;

    const encMatch = rest.match(/-c:v\s+(\S+)/);
    if (encMatch) { data.encoder = encMatch[1]; rest = rest.replace(encMatch[0], ""); }

    const qMatch = rest.match(/-(crf|cq|global_quality)\s+(\S+)/);
    if (qMatch) {
        data.quality = qMatch[2];
        data.qualityLabel = QUALITY_LABELS[data.encoder] || "Quality";
        rest = rest.replace(qMatch[0], "");
    }

    const spMatch = rest.match(/-(?:preset|cpu-used)\s+(\S+)/);
    if (spMatch) { data.speed = spMatch[1]; rest = rest.replace(spMatch[0], ""); }

    rest = rest.replace(/-c\s+copy/g, "").replace(/-c:a(?::\d+)?\s+\S+/g, "").replace(/-c:s\s+copy/g, "")
        .replace(/-b:a(?::\d+)?\s+\S+/g, "").replace(/-ac(?::a)?(?::\d+)?\s+\S+/g, "")
        .replace(/\s+/g, " ").trim();
    data.extraArgs = parseExtraArgs(rest);
    return data;
}

function parseExtraArgs(str) {
    if (!str) return [];
    const pairs = [];
    const tokens = str.split(/\s+/);
    let i = 0;
    while (i < tokens.length) {
        if (tokens[i].startsWith("-")) {
            const flag = tokens[i].substring(1);
            if (i + 1 < tokens.length && !tokens[i + 1].startsWith("-")) {
                pairs.push({ flag, value: tokens[i + 1] });
                i += 2;
            } else {
                pairs.push({ flag, value: "" });
                i++;
            }
        } else {
            i++;
        }
    }
    return pairs;
}

function assembleArgsFromData(encoder, quality, speed, extraPairs) {
    let args = "-c:s copy";
    if (encoder) {
        args += ` -c:v ${encoder}`;
        if (quality) {
            const flag = QUALITY_FLAGS[encoder] || "crf";
            args += ` -${flag} ${quality}`;
        }
        if (speed) {
            const speedGroup = ENCODER_SPEED_MAP[encoder];
            const speedFlag = SPEED_FLAG[speedGroup] || "preset";
            args += ` -${speedFlag} ${speed}`;
        }
    }
    const extra = assembleExtraArgsString(extraPairs);
    if (extra) args += ` ${extra}`;
    return args;
}

function addExtraArgRow(container, flag, value) {
    const row = document.createElement("div");
    row.className = "extra-arg-row";
    row.innerHTML = `
        <input class="arg-flag" value="${escAttr(flag || "")}" placeholder="flag">
        <input class="arg-value" value="${escAttr(value || "")}" placeholder="value">
        <button class="btn-icon btn-remove-arg" type="button"><img src="close.svg" alt="Remove"></button>
    `;
    row.querySelector(".btn-remove-arg").addEventListener("click", () => { row.remove(); container.dispatchEvent(new Event("input", { bubbles: true })); });
    container.appendChild(row);
}

function collectExtraArgs(container) {
    return Array.from(container.querySelectorAll(".extra-arg-row")).map(row => ({
        flag: row.querySelector(".arg-flag").value.trim(),
        value: row.querySelector(".arg-value").value.trim()
    }));
}

function assembleExtraArgsString(pairs) {
    return pairs.filter(p => p.flag.trim()).map(p =>
        p.value ? `-${p.flag} ${p.value}` : `-${p.flag}`
    ).join(" ");
}

function getArgsModePref() {
    return localStorage.getItem("undarr-args-mode") === "raw";
}

function applyArgsMode(rawMode, labels, structuredEl, rawEl, addBtn) {
    labels[0].classList.toggle("active", !rawMode);
    labels[0].classList.toggle("inactive", rawMode);
    labels[1].classList.toggle("active", rawMode);
    labels[1].classList.toggle("inactive", !rawMode);
    structuredEl.style.display = rawMode ? "none" : "";
    addBtn.style.display = rawMode ? "none" : "";
    rawEl.style.display = rawMode ? "" : "none";
}

function setupArgsToggle(toggleBtn, structuredEl, rawEl, addBtn, initialPairs) {
    let rawMode = getArgsModePref();
    const labels = toggleBtn.querySelectorAll(".args-mode-label");
    if (rawMode) {
        rawEl.value = assembleExtraArgsString(initialPairs || []);
        applyArgsMode(true, labels, structuredEl, rawEl, addBtn);
    }
    toggleBtn.addEventListener("click", () => {
        if (rawMode) {
            const pairs = parseExtraArgs(rawEl.value.trim());
            structuredEl.innerHTML = "";
            pairs.forEach(p => addExtraArgRow(structuredEl, p.flag, p.value));
        } else {
            const pairs = collectExtraArgs(structuredEl);
            rawEl.value = assembleExtraArgsString(pairs);
        }
        rawMode = !rawMode;
        localStorage.setItem("undarr-args-mode", rawMode ? "raw" : "structured");
        applyArgsMode(rawMode, labels, structuredEl, rawEl, addBtn);
    });
    return { isRaw: () => rawMode };
}

function loadPresets() {
    return api("GET", "/api/presets").then(data => {
        presets = data;
        renderPresets();
    });
}

function renderPresets() {
    const container = document.getElementById("preset-grid");
    const builtinPresets = presets.filter(p => p.is_builtin);
    const userPresets = presets.filter(p => !p.is_builtin);

    let html = "";
    if (builtinPresets.length) {
        html += '<h3>Built-in Presets</h3>';
        html += '<p class="section-desc">Ready-to-use presets with software encoders. They can\'t be edited directly, but you can copy one and customize it. These presets do not rename files after transcoding, so codec tags in filenames (e.g. x264) will be left the same. If your filenames include codec info, enable "Update filename" on a copy.</p>';
        html += '<div class="preset-section-grid">';
        html += builtinPresets.map(p => renderPresetViewCard(p, true)).join("");
        html += '</div>';
    }
    html += '<h3>Presets</h3>';
    html += '<div class="preset-section-grid">';
    if (creatingNewPreset) {
        html += renderPresetFormCard("", { encoder: "", quality: "", qualityLabel: "Quality", speed: "", container: "", extraArgs: [] }, "");
    }
    html += userPresets.map(p => {
        if (editingPresetName === p.name) return renderPresetFormCard(p.name, parsePresetData(p), p.description || "");
        return renderPresetViewCard(p, false);
    }).join("");
    html += '</div>';
    container.innerHTML = html;

    const editCard = container.querySelector(".preset-card.editing");
    if (editCard) {
        attachFormCardListeners(editCard, creatingNewPreset ? null : editingPresetName);
        wrapNumberInputs(editCard);
    }
}

function renderPresetViewCard(p, builtin = false) {
    const data = parsePresetData(p);
    const disabled = data.encoder && isEncoderDisabled(data.encoder);

    let videoHtml = "";
    if (data.encoder) videoHtml += `<div><dt>Encoder</dt><dd>${esc(data.encoder)}</dd></div>`;
    if (data.quality) videoHtml += `<div><dt>${esc(data.qualityLabel)}</dt><dd>${esc(data.quality)}</dd></div>`;
    if (data.speed) videoHtml += `<div><dt>Speed</dt><dd>${esc(data.speed)}</dd></div>`;
    videoHtml += `<div><dt>Container</dt><dd>${data.container ? "." + esc(data.container) : "Keep original"}</dd></div>`;
    if (data.resolutionCap) {
        videoHtml += `<div><dt>Resolution Cap</dt><dd>${esc(String(data.resolutionCap))}p</dd></div>`;
    }
    if (data.tenBit && encoderHasTenBit(data.encoder)) {
        videoHtml += `<div><dt>Bit Depth</dt><dd>10-bit</dd></div>`;
    }
    if (data.renameFile) {
        videoHtml += `<div><dt>Rename</dt><dd>Update filename</dd></div>`;
    }

    let audioHtml = "";
    if (data.audioMode === "configure" && data.audio) {
        const a = data.audio;
        const tierLabel = (t) => {
            if (!t || t.codec === "copy") return "Copy";
            const cl = AUDIO_TIER_CODEC_OPTIONS.find(c => c.value === t.codec)?.label || t.codec;
            return t.bitrate ? `${cl} ${t.bitrate}` : cl;
        };
        audioHtml += `<div><dt>Stereo</dt><dd>${esc(tierLabel(a.stereo))}</dd></div>`;
        audioHtml += `<div><dt>Surround</dt><dd>${esc(tierLabel(a.surround))}</dd></div>`;
        if (a.add_stereo_downmix && a.add_stereo_downmix !== "never") {
            const dmxLabel = a.add_stereo_downmix === "if_no_stereo" ? "If no stereo" : "Always";
            audioHtml += `<div><dt>Downmix</dt><dd>${esc(dmxLabel)}</dd></div>`;
            if (a.downmix_bitrate) audioHtml += `<div><dt>Dmx Bitrate</dt><dd>${esc(a.downmix_bitrate)}</dd></div>`;
        }
        if (a.languages && a.languages.length) {
            audioHtml += `<div><dt>Languages</dt><dd>${esc(a.languages.join(", "))}</dd></div>`;
        }
        if (a.remove_commentary) {
            audioHtml += `<div><dt>Commentary</dt><dd>Remove</dd></div>`;
        }
    }

    let subtitleHtml = "";
    if (data.subtitleMode !== "keep") {
        const s = data.subtitle;
        if (data.subtitleMode === "remove") {
            subtitleHtml += `<div><dt>Mode</dt><dd>Remove all</dd></div>`;
        } else {
            subtitleHtml += `<div><dt>Mode</dt><dd>Keep by language</dd></div>`;
            if (s && s.languages && s.languages.length) {
                subtitleHtml += `<div><dt>Languages</dt><dd>${esc(s.languages.join(", "))}</dd></div>`;
            }
            if (s && s.remove_commentary) {
                subtitleHtml += `<div><dt>Commentary</dt><dd>Remove</dd></div>`;
            }
        }
    }

    let extraHtml = "";
    if (data.extraArgs.length) {
        let dlHtml = data.extraArgs.map(a =>
            `<div><dt>${esc(a.flag)}</dt><dd>${esc(a.value) || "(flag)"}</dd></div>`
        ).join("");
        extraHtml = `<div class="preset-card-section"><span class="preset-card-section-label">Extra Arguments</span><dl class="preset-card-props">${dlHtml}</dl></div>`;
    }

    const warnHtml = disabled
        ? `<span data-tooltip="${disabledDeviceTooltip(data.encoder, 'preset')}"><img class="warning-icon" src="warning-triangle-fill.svg" alt="Device disabled"></span>`
        : "";

    const descHtml = p.description ? `<div class="preset-card-desc">${esc(p.description)}</div>` : "";

    const actionsHtml = builtin
        ? `<button class="btn-icon" data-action="copy-preset" data-name="${escAttr(p.name)}" data-tooltip="Duplicate"><img src="copy.svg" alt="Duplicate"></button>`
        : `<button class="btn-icon" data-action="copy-preset" data-name="${escAttr(p.name)}" data-tooltip="Duplicate"><img src="copy.svg" alt="Duplicate"></button>
                <button class="btn-icon" data-action="edit-preset" data-name="${escAttr(p.name)}" data-tooltip="Edit"><img src="pencil.svg" alt="Edit"></button>
                <button class="btn-icon" data-action="delete-preset" data-name="${escAttr(p.name)}" data-tooltip="Delete"><img src="trash.svg" alt="Delete"></button>`;

    return `<div class="preset-card" data-name="${escAttr(p.name)}">
        <div class="preset-card-header">
            <span class="preset-card-name">${warnHtml}${esc(p.name)}</span>
            <div class="preset-card-actions">
                ${actionsHtml}
            </div>
        </div>
        ${descHtml}
        ${videoHtml ? `<div class="preset-card-section"><span class="preset-card-section-label">Video</span><dl class="preset-card-props">${videoHtml}</dl></div>` : ""}
        ${audioHtml ? `<div class="preset-card-section"><span class="preset-card-section-label">Audio</span><dl class="preset-card-props">${audioHtml}</dl></div>` : ""}
        ${subtitleHtml ? `<div class="preset-card-section"><span class="preset-card-section-label">Subtitles</span><dl class="preset-card-props">${subtitleHtml}</dl></div>` : ""}
        ${extraHtml}
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

function renderPresetFormCard(name, data, description) {
    const extraRowsHtml = data.extraArgs.map(a => `
        <div class="extra-arg-row">
            <input class="arg-flag" value="${escAttr(a.flag)}" placeholder="flag">
            <input class="arg-value" value="${escAttr(a.value)}" placeholder="value">
            <button class="btn-icon btn-remove-arg" type="button"><img src="close.svg" alt="Remove"></button>
        </div>
    `).join("");

    const subtitleMode = data.subtitleMode || "keep";
    const sub = data.subtitle || {};
    const subLanguages = sub.languages ? sub.languages.join(", ") : "";
    const subCommentaryChecked = sub.remove_commentary ? " checked" : "";
    const subConfigHidden = subtitleMode !== "keep_by_language" ? ' style="display:none"' : "";
    const resCap = data.resolutionCap ? String(data.resolutionCap) : "";

    const renameChecked = data.renameFile ? " checked" : "";
    const tenBitChecked = data.tenBit ? " checked" : "";

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

    return `<div class="preset-card editing" data-name="${escAttr(name)}">
        <div class="form-group">
            <label data-tooltip="A display name for this preset.<br>Used to identify it when assigning to libraries. Does not affect encoding.">Name</label>
            <input type="text" class="pc-name" value="${escAttr(name)}" placeholder="e.g. hevc-qsv-18">
        </div>
        <div class="form-group">
            <label data-tooltip="A personal note for your own reference.<br>Displayed on the preset card. Does not affect encoding.">Description</label>
            <input type="text" class="pc-desc" value="${escAttr(description)}" placeholder="Optional note about this preset">
        </div>
        <div class="form-group">
            <label class="audio-checkbox" style="align-self:flex-start" data-tooltip="After a successful transcode, Undarr will try to update the codec, resolution, and audio tags in the filename, so that they match the output.<br>For example, <code>Title.x264.mkv</code> becomes <code>Title.x265.mkv</code> after encoding to HEVC, and <code>AAC</code> becomes <code>Opus</code> if the audio codec changed.<br>Preserves the naming style already used in the filename. Resolution tags are only updated when the resolution cap changes the output height."><input type="checkbox" role="switch" class="pc-rename-file"${renameChecked}> Update filename after transcode</label>
        </div>
        <div class="preset-tabs">
            <button class="preset-tab active" data-tab="video" type="button">Video</button>
            <button class="preset-tab" data-tab="audio" type="button">Audio</button>
            <button class="preset-tab" data-tab="subtitle" type="button">Subtitles</button>
        </div>
        <div class="preset-tab-panel pc-tab-video">
            <div class="form-row form-row-4">
                <div class="form-group">
                    <label data-tooltip="The FFmpeg <em>encoder</em> to use for the video stream.<br>Determines codec, hardware acceleration, and available quality/speed options.<br><br>Undarr removes the Dolby Vision metadata and the HDR10+ dynamic metadata when it transcodes a file. To keep Dolby Vision or HDR10+ files as they are, add the skip rule <code>hdr_type equals dolby_vision</code> or <code>hdr_type equals hdr10+</code> to the library.">Encoder</label>
                    <select class="pc-encoder">${buildEncoderOptionsHTML()}</select>
                </div>
                <div class="form-group">
                    <label class="pc-quality-label" data-tooltip="${QUALITY_TOOLTIPS[data.encoder] || 'Select an encoder to see quality guidelines for it.'}">${esc(data.qualityLabel)}</label>
                    <input type="number" class="pc-quality" value="${escAttr(data.quality)}" placeholder="e.g. 28">
                </div>
                <div class="form-group">
                    <label data-tooltip="Encoding speed preset.<br>Slower = better compression at the same quality, but takes longer.<br>For GPU encoders, the difference is small. For CPU encoders, it is significant.">Speed</label>
                    <select class="pc-speed">${buildSpeedOptionsHTML(data.encoder, data.speed)}</select>
                </div>
                <div class="form-group">
                    <label data-tooltip="Output file <em>container</em> format.<br><em>Keep original</em> preserves the source container.<br>Changing container does not re-encode, it only repackages the streams.<br>Streams the target container cannot hold will fail the job: for example, mp4 cannot hold PGS (Blu-ray) subtitles.">Container</label>
                    <select class="pc-container">${buildContainerOptionsHTML(data.container)}</select>
                </div>
            </div>
            <div class="form-row form-row-2">
                <div class="form-group pc-rescap-group">
                    <label data-tooltip="Maximum output resolution (height).<br>Files above the cap are downscaled while preserving aspect ratio.<br>Files at or below the cap pass through at original resolution.">Resolution Cap</label>
                    <select class="pc-rescap">${buildResolutionCapOptionsHTML(resCap)}</select>
                </div>
                <div class="form-group" style="align-self:flex-end">
                    <label class="audio-checkbox" style="align-self:flex-start" data-tooltip="The output uses 10-bit color instead of 8-bit, which reduces visible banding in dark scenes and gradients.<br>Encoding takes longer. Some very old HEVC players cannot play 10-bit.<br><br>The switch is disabled for H.264 encoders, because few devices can play 10-bit H.264. It is also disabled for <code>av1_amf</code>, <code>hevc_vulkan</code>, and <code>hevc_v4l2m2m</code>."><input type="checkbox" role="switch" class="pc-ten-bit"${tenBitChecked}> 10-bit encoding</label>
                </div>
            </div>
            <div>
                <div class="extra-args-header">
                    <label class="section-label" data-tooltip="Additional FFmpeg flags appended to the command.<br>Use for encoder-specific options not covered by the fields above.<br>Example: <code>-look_ahead 1</code>, <code>-rdo 1</code>">Extra Arguments</label>
                    <button class="args-mode-toggle pc-toggle-args" type="button">
                        <span class="args-mode-label active">Structured</span>
                        <img src="arrow-left-right.svg" alt="">
                        <span class="args-mode-label inactive">Raw Input</span>
                    </button>
                </div>
                <div class="pc-extra-args">${extraRowsHtml}</div>
                <textarea class="pc-extra-args-raw" style="display:none" placeholder="e.g. -look_ahead 1 -rdo 1"></textarea>
                <button class="btn pc-add-arg" type="button" style="margin-top:6px">Add Argument</button>
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
                        <label class="audio-checkbox" data-tooltip="Drop audio streams with the <em>commentary</em> disposition flag set by the source."><input type="checkbox" role="switch" class="pc-remove-commentary"${commentaryChecked}> Remove commentary</label>
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
                    <label class="audio-checkbox" data-tooltip="Drop subtitle streams with the <em>commentary</em> disposition flag set by the source."><input type="checkbox" role="switch" class="pc-sub-remove-commentary"${subCommentaryChecked}> Remove commentary</label>
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
    const data = isNew
        ? { encoder: "", extraArgs: [] }
        : parsePresetData(presets.find(p => p.name === originalName));

    const saveBtn = card.querySelector(".pc-save");
    saveBtn.disabled = true;

    card.querySelectorAll(".preset-tab").forEach(tab => {
        tab.addEventListener("click", () => {
            card.querySelectorAll(".preset-tab").forEach(t => t.classList.toggle("active", t === tab));
            card.querySelector(".pc-tab-video").style.display = tab.dataset.tab === "video" ? "" : "none";
            card.querySelector(".pc-tab-audio").style.display = tab.dataset.tab === "audio" ? "" : "none";
            card.querySelector(".pc-tab-subtitle").style.display = tab.dataset.tab === "subtitle" ? "" : "none";
        });
    });

    const encoderSel = card.querySelector(".pc-encoder");
    encoderSel.value = data.encoder;

    const tenBitSwitch = card.querySelector(".pc-ten-bit");
    let tenBitChoice = tenBitSwitch.checked;
    tenBitSwitch.addEventListener("change", () => { tenBitChoice = tenBitSwitch.checked; });
    function updateTenBitSwitch() {
        const unavailable = encoderSel.value !== "" && !encoderHasTenBit(encoderSel.value);
        tenBitSwitch.disabled = unavailable;
        tenBitSwitch.checked = tenBitChoice && !unavailable;
    }
    updateTenBitSwitch();

    const initialSnapshot = getFormSnapshot(card);
    function checkChanged() { saveBtn.disabled = getFormSnapshot(card) === initialSnapshot; }
    card.addEventListener("input", checkChanged);
    card.addEventListener("change", checkChanged);

    encoderSel.addEventListener("change", () => {
        const qualityLabel = card.querySelector(".pc-quality-label");
        qualityLabel.textContent = QUALITY_LABELS[encoderSel.value] || "Quality";
        qualityLabel.dataset.tooltip = QUALITY_TOOLTIPS[encoderSel.value] || "Select an encoder to see quality guidelines for it.";
        card.querySelector(".pc-speed").innerHTML = buildSpeedOptionsHTML(encoderSel.value, "");
        updateTenBitSwitch();
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

    card.querySelectorAll(".btn-remove-arg").forEach(btn => {
        btn.addEventListener("click", () => { btn.closest(".extra-arg-row").remove(); checkChanged(); });
    });

    card.querySelector(".pc-add-arg").addEventListener("click", () => {
        addExtraArgRow(card.querySelector(".pc-extra-args"), "", "");
        checkChanged();
    });

    const cardArgsToggle = setupArgsToggle(
        card.querySelector(".pc-toggle-args"),
        card.querySelector(".pc-extra-args"),
        card.querySelector(".pc-extra-args-raw"),
        card.querySelector(".pc-add-arg"),
        data.extraArgs
    );

    card.querySelector(".pc-save").addEventListener("click", async () => {
        clearValidation(card);
        const newName = card.querySelector(".pc-name").value.trim();
        const encoderEl = card.querySelector(".pc-encoder");
        const qualityEl = card.querySelector(".pc-quality");
        const speedEl = card.querySelector(".pc-speed");
        let valid = true;
        if (!newName) { setError(card.querySelector(".pc-name"), "Name is required"); valid = false; }
        if (!encoderEl.value) { setError(encoderEl, "Encoder is required"); valid = false; }
        if (!qualityEl.value.trim()) { setError(qualityEl, "Quality is required"); valid = false; }
        if (!speedEl.value) { setError(speedEl, "Speed is required"); valid = false; }
        if (!valid) return;
        const encoder = encoderEl.value;
        const quality = qualityEl.value.trim();
        const speed = speedEl.value;
        const container = card.querySelector(".pc-container").value || null;
        const extraPairs = cardArgsToggle.isRaw()
            ? parseExtraArgs(card.querySelector(".pc-extra-args-raw").value.trim())
            : collectExtraArgs(card.querySelector(".pc-extra-args"));
        const args = assembleArgsFromData(encoder, quality, speed, extraPairs);
        const description = card.querySelector(".pc-desc").value.trim() || null;

        function validateBitrate(input) {
            const v = input.value.trim();
            if (!v) return true;
            if (/^\d+k$/i.test(v)) return true;
            setError(input, "Use format like 160k, 320k, 640k");
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
        const rename_file = card.querySelector(".pc-rename-file").checked;
        const ten_bit = card.querySelector(".pc-ten-bit").checked;

        try {
            if (isNew) {
                await api("POST", "/api/presets", { name: newName, ffmpeg_args: args, output_container: container, description, audio, subtitle, resolution_cap, rename_file, ten_bit });
                creatingNewPreset = false;
            } else {
                await api("PUT", `/api/presets/${encodeURIComponent(originalName)}`, {
                    name: newName, ffmpeg_args: args, output_container: container, description, audio, subtitle, resolution_cap, rename_file, ten_bit
                });
                editingPresetName = null;
            }
            loadPresets();
        } catch (e) {
            setError(card.querySelector(".pc-name"), e.message);
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

export async function loadPresetView() {
    await Promise.all([loadEncoderCache(), loadDeviceData()]);
    await loadPresets();
}

export function initPresets() {
    document.getElementById("preset-grid").addEventListener("click", async (e) => {
        const btn = e.target.closest("[data-action]");
        if (!btn) return;
        const name = btn.dataset.name;
        if (btn.dataset.action === "copy-preset") {
            const source = presets.find(p => p.name === name);
            if (!source) return;
            const existingNames = new Set(presets.map(p => p.name));
            let copyName, i = 2;
            do {
                copyName = `${name} (${i++})`;
            } while (existingNames.has(copyName));
            try {
                await api("POST", "/api/presets", {
                    name: copyName,
                    ffmpeg_args: source.ffmpeg_args,
                    output_container: source.output_container,
                    description: source.description,
                    audio: source.audio || null,
                    subtitle: source.subtitle || null,
                    resolution_cap: source.resolution_cap || null,
                    rename_file: source.rename_file || false,
                    ten_bit: source.ten_bit || false,
                });
                loadPresets();
            } catch (err) {
                alert(err.message);
            }
        } else if (btn.dataset.action === "edit-preset") {
            editingPresetName = name;
            creatingNewPreset = false;
            renderPresets();
        } else if (btn.dataset.action === "delete-preset") {
            if (!confirm(`Delete preset "${name}"?\n\nThis removes the preset configuration permanently. Any libraries using this preset will need to be reassigned to a different one.\n\nIf you just want to change settings, edit the preset instead.`)) return;
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
