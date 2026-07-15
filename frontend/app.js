import { api } from "./helpers.js";
import { initQueue, connectSSE } from "./queue.js";
import { initHistory } from "./history.js";
import { initSearch } from "./search.js";
import { initPresets, loadPresetView } from "./presets.js";
import { initLibraries, loadLibraryView } from "./libraries.js";
import { initSettings, loadSettings } from "./settings.js";

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

function navigate(viewId) {
    navItems.forEach(n => n.classList.toggle("active", n.dataset.view === viewId));
    views.forEach(v => v.classList.toggle("active", v.id === "view-" + viewId));
    if (viewId === "presets") loadPresetView();
    if (viewId === "libraries") loadLibraryView();
    if (viewId === "settings") loadSettings();
    const hash = viewId === "queue" ? "" : viewId;
    if (location.hash.replace("#", "") !== hash)
        history.replaceState(null, "", hash ? "#" + hash : location.pathname);
}

navItems.forEach(n => n.addEventListener("click", () => navigate(n.dataset.view)));
document.getElementById("sidebar-title").addEventListener("click", () => navigate("queue"));

initQueue();
initHistory();
initSearch();
initPresets();
initLibraries();
initSettings();

const validViews = ["queue", "presets", "libraries", "settings"];
const hashView = location.hash.replace("#", "");
navigate(validViews.includes(hashView) ? hashView : "queue");
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
