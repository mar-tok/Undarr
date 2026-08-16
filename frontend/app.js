import { api } from "./helpers.js";
import { initOverview, loadOverview } from "./overview.js";
import { initQueue, connectSSE, loadQueueTab } from "./queue.js";
import { initHistory } from "./history.js";
import { initSearch } from "./search.js";
import { initPresets, loadPresetView } from "./presets.js";
import { initLibraries, loadLibraryView } from "./libraries.js";
import { initSettings, loadSettings, switchSettingsTab } from "./settings.js";
import { isScheduleDirty, discardScheduleChanges, stopScheduleClock } from "./schedule.js";
import { initSetup, loadSetupView, checkFirstRun } from "./quickstart.js";

const tooltip = document.getElementById("tooltip");
let tipTarget = null;

document.addEventListener("mousemove", e => {
    const el = e.target.closest("[data-tooltip]");
    if (el) {
        if (el !== tipTarget) {
            tipTarget = el;
            tooltip.innerHTML = el.getAttribute("data-tooltip");
            tooltip.style.display = "block";
        }
        const nearRight = e.clientX + tooltip.offsetWidth + 12 > window.innerWidth;
        const nearBottom = e.clientY + tooltip.offsetHeight + 16 > window.innerHeight;
        tooltip.style.left = (nearRight ? e.clientX - tooltip.offsetWidth - 8 : e.clientX + 12) + "px";
        tooltip.style.top = (nearBottom ? e.clientY - tooltip.offsetHeight - 8 : e.clientY + 16) + "px";
    } else if (tipTarget) {
        tipTarget = null;
        tooltip.style.display = "none";
    }
});

const navItems = document.querySelectorAll(".nav-item");
const views = document.querySelectorAll(".view");

let currentView = "overview";

function navigate(viewId) {
    if (currentView === "settings" && viewId !== "settings" && isScheduleDirty()) {
        if (!confirm("You have unsaved schedule changes. Leave without saving?")) return;
        discardScheduleChanges();
    }
    if (currentView === "settings" && viewId !== "settings") stopScheduleClock();
    currentView = viewId;
    navItems.forEach(n => n.classList.toggle("active", n.dataset.view === viewId));
    views.forEach(v => v.classList.toggle("active", v.id === "view-" + viewId));
    if (viewId === "overview") loadOverview();
    if (viewId === "queue") loadQueueTab();
    if (viewId === "presets") loadPresetView();
    if (viewId === "libraries") loadLibraryView();
    if (viewId === "settings") loadSettings();
    if (viewId === "quickstart") loadSetupView();
    const hash = viewId === "overview" ? "" : viewId;
    if (location.hash.replace("#", "").split("/")[0] !== hash)
        history.replaceState(null, "", hash ? "#" + hash : location.pathname);
}

navItems.forEach(n => n.addEventListener("click", () => navigate(n.dataset.view)));
document.getElementById("sidebar-title").addEventListener("click", () => navigate("overview"));

initOverview();
initQueue();
initHistory();
initSearch();
initPresets();
initLibraries();
initSettings();
initSetup(navigate);

const validViews = ["overview", "queue", "presets", "libraries", "settings", "quickstart"];

async function initApp() {
    const hashParts = location.hash.replace("#", "").split("/");
    const hashView = hashParts[0];

    if (!hashView) {
        const firstRun = await checkFirstRun();
        navigate(firstRun ? "quickstart" : "overview");
    } else {
        navigate(validViews.includes(hashView) ? hashView : "overview");
    }

    if (hashParts[0] === "settings" && hashParts[1]) switchSettingsTab(hashParts[1]);
}

initApp();
connectSSE();

api("GET", "/api/version").then(data => {
    document.getElementById("version-label").textContent = "Version " + data.version;
    if (data.latest) {
        const link = document.getElementById("version-link");
        const icon = document.getElementById("update-icon");
        link.dataset.tooltip = "You are running " + data.version + ". Version " + data.latest + " is available with new changes. Click here to view the changelog.";
        icon.classList.remove("hidden");
    }
}).catch(() => {});
