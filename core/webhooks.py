from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from http.client import HTTPException
from urllib.error import URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import urlopen, Request

from core import db
from core.logger import log
from core.sizes import format_size
from core.yaml_store import store, WebhookConfig

# Discord embed colors as decimal ints
COLOR_RED = 15548997
COLOR_GREEN = 5763719
COLOR_YELLOW = 16776960
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

    if event == "queue_stalled":
        return {
            "embeds": [
                {
                    "title": "Queue Stalled",
                    "description": _stall_text(data),
                    "color": COLOR_YELLOW,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            ]
        }

    if event == "daily_digest":
        return {
            "embeds": [
                {
                    "title": "Daily Digest",
                    "description": _digest_text(data),
                    "color": COLOR_YELLOW if data.get("failed") else COLOR_GREEN,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            ]
        }

    if event == "top_reduction":
        return {
            "embeds": [
                {
                    "title": "New Top Reduction",
                    "description": _reduction_text(data),
                    "color": COLOR_GREEN,
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


def _stall_text(data: dict) -> str:
    pending = data.get("pending_count", 0)
    text = f"{pending} pending job{'s' if pending != 1 else ''} blocked."
    reasons = data.get("reasons", [])
    if reasons:
        text += "\n" + "\n".join(f"- {r}" for r in reasons[:5])
    return text


def _digest_text(data: dict) -> str:
    lines = []
    if data.get("completed"):
        lines.append(f"{data['completed']} completed")
    if data.get("failed"):
        lines.append(f"{data['failed']} failed")
    saved = data.get("space_saved_bytes", 0)
    if saved > 0:
        lines.append(f"{format_size(saved)} saved")
    elif saved < 0:
        lines.append(f"{format_size(-saved)} added")
    return ", ".join(lines) if lines else "No activity."


def _reduction_text(data: dict) -> str:
    filename = data.get("file_path", "Unknown file").rsplit("/", 1)[-1]
    old = data.get("old_size_bytes", 0)
    new = data.get("new_size_bytes", 0)
    pct = round((old - new) / old * 100) if old else 0
    return f"{filename}\n{format_size(old)} \u2192 {format_size(new)} ({pct}% smaller)"


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

    if event == "queue_stalled":
        return "Queue Stalled", _stall_text(data)

    if event == "daily_digest":
        return "Daily Digest", _digest_text(data)

    if event == "top_reduction":
        return "New Top Reduction", _reduction_text(data)

    if event == "test":
        return "Undarr", "Webhook is working."

    return "Undarr", str(event)


NTFY_PRIORITY = {"job_failed": 4, "queue_stalled": 4}
GOTIFY_PRIORITY = {"job_failed": 8, "queue_stalled": 8}


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


async def check_top_reduction(job) -> None:
    webhooks = await store.get_webhooks()
    if not any(wh.enabled and "top_reduction" in wh.events for wh in webhooks):
        return
    top = await db.get_stats_top_savings(limit=1)
    # Runs after insert_job_history, so the query already includes this job
    if top and top[0]["file_path"] == job.file_path:
        await fire_event(
            "top_reduction",
            {
                "file_path": job.file_path,
                "old_size_bytes": job.old_size_bytes,
                "new_size_bytes": job.new_size_bytes,
            },
        )


async def send_test(webhook: WebhookConfig) -> str | None:
    """Returns None on success, the error text on failure."""
    url, payload = _prepare(webhook, "test", {})
    try:
        await asyncio.to_thread(_send_sync, url, payload)
        return None
    except (URLError, HTTPException, OSError, ValueError) as e:
        return str(e)


# Daily digest scheduler

_digest_task: asyncio.Task | None = None


async def _send_digests(hour: int, day: str) -> None:
    hooks = [
        wh
        for wh in await store.get_webhooks()
        if wh.enabled and "daily_digest" in wh.events and wh.digest_hour == hour
    ]
    if not hooks:
        return
    stats = next((d for d in await db.get_stats_daily() if d["date"] == day), None)
    if not stats:
        return
    for wh in hooks:
        await send(wh, "daily_digest", stats)


def _next_digest(now: datetime) -> tuple[float, int, str]:
    """Seconds until the next hour boundary, that hour, and the day before it."""
    next_hour = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
    yesterday = (next_hour - timedelta(days=1)).strftime("%Y-%m-%d")
    return (next_hour - now).total_seconds(), next_hour.hour, yesterday


async def _digest_loop() -> None:
    while True:
        delay, hour, day = _next_digest(datetime.now())
        await asyncio.sleep(delay)
        await _send_digests(hour, day)


async def start_digest_scheduler() -> None:
    global _digest_task
    _digest_task = asyncio.create_task(_digest_loop())


async def stop_digest_scheduler() -> None:
    global _digest_task
    if _digest_task:
        _digest_task.cancel()
        try:
            await _digest_task
        except asyncio.CancelledError:
            pass
        _digest_task = None
