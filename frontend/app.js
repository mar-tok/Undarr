import { initQueue, connectSSE } from "./queue.js";
import { initHistory } from "./history.js";
import { initSearch } from "./search.js";
import { initPresets, loadPresets } from "./presets.js";
import { initLibraries, loadLibraries } from "./libraries.js";
import { initSettings, loadSettings } from "./settings.js";

const navItems = document.querySelectorAll(".nav-item");
const views = document.querySelectorAll(".view");

function navigate(viewId) {
    navItems.forEach(n => n.classList.toggle("active", n.dataset.view === viewId));
    views.forEach(v => v.classList.toggle("active", v.id === "view-" + viewId));
    if (viewId === "presets") loadPresets();
    if (viewId === "libraries") loadLibraries();
    if (viewId === "settings") loadSettings();
    const hash = viewId === "queue" ? "" : viewId;
    if (location.hash.replace("#", "") !== hash)
        history.replaceState(null, "", hash ? "#" + hash : location.pathname);
}

navItems.forEach(n => n.addEventListener("click", () => navigate(n.dataset.view)));

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
