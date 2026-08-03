import { api } from "./helpers.js";

const DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"];
const DAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

let scheduleData = null;
let scheduleOriginal = null;
let scheduleEnabledOriginal = false;
let serverTimezone = "";
let serverUtcOffset = 0;
let clockInterval = null;
let saveBtn = null;
let painting = false;
let paintMode = true;
let paintTarget = "cell";
let loaded = false;

function defaultSchedule() {
    const s = {};
    for (const day of DAYS) s[day] = Array(24).fill(true);
    return s;
}

function cloneSchedule(s) {
    const c = {};
    for (const day of DAYS) c[day] = [...s[day]];
    return c;
}

function schedulesEqual(a, b) {
    for (const day of DAYS) {
        for (let h = 0; h < 24; h++) {
            if (a[day][h] !== b[day][h]) return false;
        }
    }
    return true;
}

function checkChanged() {
    const enabled = document.getElementById("schedule-enabled").checked;
    const gridChanged = !schedulesEqual(scheduleData, scheduleOriginal);
    const enabledChanged = enabled !== scheduleEnabledOriginal;
    saveBtn.disabled = !gridChanged && !enabledChanged;
}

export function isScheduleDirty() {
    if (!scheduleData || !scheduleOriginal) return false;
    const enabled = document.getElementById("schedule-enabled").checked;
    return !schedulesEqual(scheduleData, scheduleOriginal) || enabled !== scheduleEnabledOriginal;
}

export function discardScheduleChanges() {
    if (!scheduleOriginal) return;
    scheduleData = cloneSchedule(scheduleOriginal);
    document.getElementById("schedule-enabled").checked = scheduleEnabledOriginal;
    renderCells();
    updateGridDisabled();
    updateSummary();
    saveBtn.disabled = true;
}

function updateSummary() {
    const el = document.getElementById("schedule-summary");
    const enabled = document.getElementById("schedule-enabled").checked;
    if (!enabled) {
        el.textContent = "Schedule disabled. Transcoding runs at all times.";
        return;
    }
    let active = 0;
    for (const day of DAYS) {
        for (let h = 0; h < 24; h++) {
            if (scheduleData[day][h]) active++;
        }
    }
    el.textContent = `Active ${active} of 168 hours.`;
}

function getServerNow() {
    const now = new Date();
    return new Date(now.getTime() + (serverUtcOffset * 60000) + (now.getTimezoneOffset() * 60000));
}

function updateClock() {
    const el = document.getElementById("schedule-time-display");
    const serverNow = getServerNow();
    const localNow = new Date();
    const dayNames = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

    const sHH = String(serverNow.getHours()).padStart(2, "0");
    const sMM = String(serverNow.getMinutes()).padStart(2, "0");
    const sSS = String(serverNow.getSeconds()).padStart(2, "0");
    const sDay = dayNames[serverNow.getDay()];

    const lHH = String(localNow.getHours()).padStart(2, "0");
    const lMM = String(localNow.getMinutes()).padStart(2, "0");
    const lSS = String(localNow.getSeconds()).padStart(2, "0");
    const lDay = dayNames[localNow.getDay()];

    el.innerHTML =
        `Server: ${sDay} ${sHH}:${sMM}:${sSS} (${serverTimezone})` +
        `<br>Your time: ${lDay} ${lHH}:${lMM}:${lSS}`;

    const rows = document.querySelectorAll("#schedule-grid .schedule-table tbody tr");
    const currentHour = serverNow.getHours();
    rows.forEach((row, i) => {
        row.classList.toggle("current-hour", i === currentHour);
        const th = row.querySelector(".schedule-hour-header");
        if (!th) return;
        const hourLabel = String(i).padStart(2, "0");
        th.textContent = i === currentHour ? `Server time ${hourLabel}` : hourLabel;
    });
}

function startClock() {
    if (clockInterval) return;
    updateClock();
    clockInterval = setInterval(updateClock, 1000);
}

export function stopScheduleClock() {
    if (clockInterval) {
        clearInterval(clockInterval);
        clockInterval = null;
    }
}

function setCellState(td, active) {
    const day = td.dataset.day;
    const hour = parseInt(td.dataset.hour);
    scheduleData[day][hour] = active;
    td.classList.toggle("active", active);
    td.classList.toggle("inactive", !active);
}

function toggleDay(dayIndex) {
    const day = DAYS[dayIndex];
    const allOn = scheduleData[day].every(v => v);
    const target = !allOn;
    const cells = document.querySelectorAll(`#schedule-grid td[data-day="${day}"]`);
    cells.forEach(td => setCellState(td, target));
    updateSummary();
    checkChanged();
}

function toggleHour(hour) {
    const allOn = DAYS.every(day => scheduleData[day][hour]);
    const target = !allOn;
    const cells = document.querySelectorAll(`#schedule-grid td[data-hour="${hour}"]`);
    cells.forEach(td => setCellState(td, target));
    updateSummary();
    checkChanged();
}

function applyPreset(name) {
    const s = defaultSchedule();
    if (name === "allOff") {
        for (const day of DAYS) s[day] = Array(24).fill(false);
    } else if (name === "nights") {
        for (const day of DAYS) {
            for (let h = 0; h < 24; h++) {
                s[day][h] = h >= 22 || h < 6;
            }
        }
    } else if (name === "weekends") {
        for (const day of DAYS) {
            const isWeekend = day === "sat" || day === "sun";
            s[day] = Array(24).fill(isWeekend);
        }
    }
    scheduleData = s;
    renderCells();
    updateSummary();
    checkChanged();
}

function renderCells() {
    const cells = document.querySelectorAll("#schedule-grid td[data-day]");
    cells.forEach(td => {
        const active = scheduleData[td.dataset.day][parseInt(td.dataset.hour)];
        td.classList.toggle("active", active);
        td.classList.toggle("inactive", !active);
    });
}

function updateGridDisabled() {
    const enabled = document.getElementById("schedule-enabled").checked;
    const container = document.getElementById("schedule-grid");
    container.classList.toggle("disabled", !enabled);
    document.getElementById("schedule-presets").classList.toggle("disabled", !enabled);
}

function buildGrid() {
    const container = document.getElementById("schedule-grid");
    const table = document.createElement("table");
    table.className = "schedule-table";

    const thead = document.createElement("thead");
    const headerRow = document.createElement("tr");
    headerRow.innerHTML = "<th></th>";
    DAY_LABELS.forEach((label, i) => {
        const th = document.createElement("th");
        th.textContent = label;
        th.className = "schedule-day-header";
        th.addEventListener("mousedown", (e) => {
            e.preventDefault();
            toggleDay(i);
        });
        headerRow.appendChild(th);
    });
    thead.appendChild(headerRow);
    table.appendChild(thead);

    const tbody = document.createElement("tbody");
    for (let h = 0; h < 24; h++) {
        const row = document.createElement("tr");
        const hourTh = document.createElement("th");
        hourTh.textContent = String(h).padStart(2, "0");
        hourTh.className = "schedule-hour-header";
        hourTh.dataset.hour = h;
        hourTh.addEventListener("mousedown", (e) => {
            e.preventDefault();
            if (document.getElementById("schedule-grid").classList.contains("disabled")) return;
            painting = true;
            paintTarget = "hour-header";
            const allOn = DAYS.every(day => scheduleData[day][h]);
            paintMode = !allOn;
            toggleHour(h);
        });
        hourTh.addEventListener("mouseenter", () => {
            if (!painting || paintTarget !== "hour-header") return;
            const hour = parseInt(hourTh.dataset.hour);
            const cells = document.querySelectorAll(`#schedule-grid td[data-hour="${hour}"]`);
            cells.forEach(td => setCellState(td, paintMode));
            updateSummary();
            checkChanged();
        });
        row.appendChild(hourTh);

        for (const day of DAYS) {
            const td = document.createElement("td");
            td.dataset.day = day;
            td.dataset.hour = h;
            const active = scheduleData[day][h];
            td.classList.add(active ? "active" : "inactive");

            td.addEventListener("mousedown", (e) => {
                e.preventDefault();
                if (document.getElementById("schedule-grid").classList.contains("disabled")) return;
                painting = true;
                paintTarget = "cell";
                paintMode = !scheduleData[day][h];
                setCellState(td, paintMode);
                updateSummary();
                checkChanged();
            });
            td.addEventListener("mouseenter", () => {
                if (!painting || paintTarget !== "cell") return;
                setCellState(td, paintMode);
                updateSummary();
                checkChanged();
            });
            row.appendChild(td);
        }
        tbody.appendChild(row);
    }
    table.appendChild(tbody);
    container.innerHTML = "";
    container.appendChild(table);
}

export function loadSchedule(settings) {
    if (loaded && isScheduleDirty()) return;

    scheduleData = cloneSchedule(settings.schedule || defaultSchedule());
    scheduleOriginal = cloneSchedule(scheduleData);
    scheduleEnabledOriginal = !!settings.schedule_enabled;

    document.getElementById("schedule-enabled").checked = settings.schedule_enabled;

    serverTimezone = settings.server_timezone || "UTC";
    serverUtcOffset = settings.server_utc_offset || 0;
    startClock();

    buildGrid();
    updateGridDisabled();
    updateSummary();
    saveBtn.disabled = true;
    loaded = true;
}

export function initSchedule() {
    saveBtn = document.getElementById("btn-save-schedule");
    saveBtn.disabled = true;

    document.addEventListener("mouseup", () => { painting = false; });

    document.getElementById("schedule-enabled").addEventListener("change", () => {
        updateGridDisabled();
        updateSummary();
        checkChanged();
    });

    document.getElementById("schedule-presets").addEventListener("click", (e) => {
        const btn = e.target.closest("[data-preset]");
        if (!btn) return;
        if (document.getElementById("schedule-presets").classList.contains("disabled")) return;
        applyPreset(btn.dataset.preset);
    });

    saveBtn.addEventListener("click", async () => {
        try {
            const payload = {
                schedule_enabled: document.getElementById("schedule-enabled").checked,
                schedule: scheduleData,
            };
            const result = await api("PATCH", "/api/settings", payload);
            scheduleOriginal = cloneSchedule(result.schedule);
            scheduleEnabledOriginal = result.schedule_enabled;
            saveBtn.disabled = true;
        } catch (e) {
            alert(e.message);
        }
    });
}
