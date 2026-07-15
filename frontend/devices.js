import { api, esc } from "./helpers.js";

export let deviceData = [];

export async function loadDeviceData() {
    try { deviceData = await api("GET", "/api/devices"); } catch { deviceData = []; }
}

export function isDeviceDisabled(deviceId) {
    const dev = deviceData.find(d => d.id === deviceId);
    return dev ? dev.max_jobs === 0 : false;
}

export function isEncoderDisabled(encoderName) {
    for (const dev of deviceData) {
        if (dev.encoders.includes(encoderName)) return dev.max_jobs === 0;
    }
    return false;
}

export function disabledDeviceTooltip(encoderName, context) {
    for (const dev of deviceData) {
        if (dev.encoders.includes(encoderName) && dev.max_jobs === 0) {
            if (context === "preset") {
                return `Uses <em>${esc(encoderName)}</em> on <em>${esc(dev.name)}</em>, which is disabled.<br>Jobs from libraries using this preset will not be processed.<br>Enable it in <em>Settings > Devices</em>.`;
            }
            if (context === "library") {
                return `Uses <em>${esc(encoderName)}</em> on <em>${esc(dev.name)}</em>, which is disabled.<br>Files in this library will not be transcoded.<br>Enable it in <em>Settings > Devices</em>.`;
            }
        }
    }
    return "";
}

