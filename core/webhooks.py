from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from http.client import HTTPException
from urllib.error import URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import urlopen, Request

from core.logger import log
from core.yaml_store import store, WebhookConfig

# Discord embed colors as decimal ints
COLOR_RED = 15548997
COLOR_BLUE = 5793266


def _build_discord_payload(event: str, data: dict) -> dict:
    if event == "job_failed":
        file_path = data.get("file_path", "Unknown file")
        filename = file_path.rsplit("/", 1)[-1]
        error = data.get("error_message", "No error details")
        fields = [{"name": "Error", "value": error[:1024], "inline": False}]
        if data.get("preset_name"):
            fields.append(
                {"name": "Preset", "value": data["preset_name"], "inline": True}
            )
        if data.get("device_name"):
            fields.append(
                {"name": "Device", "value": data["device_name"], "inline": True}
            )
        return {
            "embeds": [
                {
                    "title": "Job Failed",
                    "description": filename,
                    "color": COLOR_RED,
                    "fields": fields,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            ]
        }

    if event == "test":
        return {
            "embeds": [
                {
                    "title": "Undarr",
                    "description": "Webhook is working.",
                    "color": COLOR_BLUE,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            ]
        }

    return {"content": f"Undarr: {event}"}


def _text_parts(event: str, data: dict) -> tuple[str, str]:
    if event == "job_failed":
        file_path = data.get("file_path", "Unknown file")
        filename = file_path.rsplit("/", 1)[-1]
        error = data.get("error_message", "No error details")
        parts = [filename, f"Error: {error}"]
        origin = ", ".join(
            f"{label}: {data[key]}"
            for label, key in (("Preset", "preset_name"), ("Device", "device_name"))
            if data.get(key)
        )
        if origin:
            parts.append(origin)
        return "Job Failed", "\n".join(parts)

    if event == "test":
        return "Undarr", "Webhook is working."

    return "Undarr", str(event)


NTFY_PRIORITY = {"job_failed": 4}
GOTIFY_PRIORITY = {"job_failed": 8}


def _build_ntfy_payload(event: str, data: dict) -> dict:
    title, body = _text_parts(event, data)
    return {"title": title, "message": body, "priority": NTFY_PRIORITY.get(event, 3)}


def _build_gotify_payload(event: str, data: dict) -> dict:
    title, body = _text_parts(event, data)
    return {"title": title, "message": body, "priority": GOTIFY_PRIORITY.get(event, 5)}


def _build_generic_payload(event: str, data: dict) -> dict:
    return {
        "event": event,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": data,
    }


TEMPLATE_BUILDERS = {
    "discord": _build_discord_payload,
    "ntfy": _build_ntfy_payload,
    "gotify": _build_gotify_payload,
    "generic": _build_generic_payload,
}


def _build_payload(template: str, event: str, data: dict) -> dict:
    builder = TEMPLATE_BUILDERS.get(template, _build_discord_payload)
    return builder(event, data)


def _ntfy_target(url: str) -> tuple[str, str]:
    # ntfy parses the JSON body only when posted to the server root
    parts = urlsplit(url)
    topic = parts.path.rstrip("/").rsplit("/", 1)[-1]
    root = urlunsplit((parts.scheme, parts.netloc, "/", parts.query, ""))
    return root, topic


def _prepare(webhook: WebhookConfig, event: str, data: dict) -> tuple[str, dict]:
    payload = _build_payload(webhook.template, event, data)
    url = webhook.url
    if webhook.template == "ntfy":
        url, payload["topic"] = _ntfy_target(url)
    return url, payload


def _send_sync(url: str, payload: dict) -> None:
    body = json.dumps(payload).encode("utf-8")
    req = Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", "User-Agent": "Undarr"},
        method="POST",
    )
    with urlopen(req, timeout=10) as resp:
        resp.read()


async def send(webhook: WebhookConfig, event: str, data: dict) -> None:
    url, payload = _prepare(webhook, event, data)
    try:
        await asyncio.to_thread(_send_sync, url, payload)
    except (URLError, HTTPException, OSError, ValueError) as e:
        log.warning("Webhook delivery failed (%s): %s", event, e)


_send_tasks: set[asyncio.Task] = set()


async def fire_event(event: str, data: dict) -> None:
    for wh in await store.get_webhooks():
        if not wh.enabled or event not in wh.events:
            continue
        task = asyncio.create_task(send(wh, event, data))
        _send_tasks.add(task)
        task.add_done_callback(_send_tasks.discard)


async def send_test(webhook: WebhookConfig) -> str | None:
    """Returns None on success, the error text on failure."""
    url, payload = _prepare(webhook, "test", {})
    try:
        await asyncio.to_thread(_send_sync, url, payload)
        return None
    except (URLError, HTTPException, OSError, ValueError) as e:
        return str(e)
