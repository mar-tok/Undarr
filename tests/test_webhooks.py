from unittest.mock import patch, AsyncMock
from urllib.error import URLError

import pytest

from core.webhooks import _build_payload, fire_event, send, send_test, _send_tasks
from core.yaml_store import WebhookConfig

# Discord payloads


class TestDiscordPayload:
    def test_job_failed_embed(self):
        payload = _build_payload(
            "discord",
            "job_failed",
            {
                "file_path": "/media/Movies/Video.Title.mkv",
                "error_message": "ffmpeg exited with code 1",
                "preset_name": "HEVC Transparent",
                "device_name": "CPU",
            },
        )
        embed = payload["embeds"][0]
        assert embed["title"] == "Job Failed"
        assert embed["description"] == "Video.Title.mkv"
        names = [f["name"] for f in embed["fields"]]
        assert names == ["Error", "Preset", "Device"]
        assert embed["fields"][0]["value"] == "ffmpeg exited with code 1"

    def test_job_failed_omits_missing_fields(self):
        payload = _build_payload("discord", "job_failed", {"file_path": "/x/a.mkv"})
        embed = payload["embeds"][0]
        assert [f["name"] for f in embed["fields"]] == ["Error"]
        assert embed["fields"][0]["value"] == "No error details"

    def test_error_truncated_to_discord_limit(self):
        payload = _build_payload(
            "discord", "job_failed", {"file_path": "a.mkv", "error_message": "x" * 3000}
        )
        assert len(payload["embeds"][0]["fields"][0]["value"]) == 1024

    def test_test_event(self):
        payload = _build_payload("discord", "test", {})
        assert payload["embeds"][0]["description"] == "Webhook is working."

    def test_unknown_event_falls_back_to_content(self):
        payload = _build_payload("discord", "something_else", {})
        assert payload == {"content": "Undarr: something_else"}

    def test_unknown_template_uses_discord(self):
        payload = _build_payload("nope", "test", {})
        assert "embeds" in payload


# Delivery


class TestSend:
    async def test_posts_json_to_url(self):
        wh = WebhookConfig(url="https://example.com/hook", events=["job_failed"])
        with patch("core.webhooks._send_sync") as sync:
            await send(wh, "test", {})
        url, payload = sync.call_args.args
        assert url == "https://example.com/hook"
        assert payload["embeds"][0]["title"] == "Undarr"

    async def test_failure_is_logged_not_raised(self):
        wh = WebhookConfig(url="https://example.com/hook")
        with (
            patch("core.webhooks._send_sync", side_effect=URLError("refused")),
            patch("core.webhooks.log") as log,
        ):
            await send(wh, "job_failed", {"file_path": "a.mkv"})
        assert log.warning.called

    async def test_send_test_returns_error_text(self):
        wh = WebhookConfig(url="not a url")
        with patch(
            "core.webhooks._send_sync", side_effect=ValueError("unknown url type")
        ):
            assert await send_test(wh) == "unknown url type"

    async def test_send_test_returns_none_on_success(self):
        wh = WebhookConfig(url="https://example.com/hook")
        with patch("core.webhooks._send_sync"):
            assert await send_test(wh) is None


# Event routing


class TestFireEvent:
    @pytest.fixture
    def webhooks(self):
        hooks = [
            WebhookConfig(url="https://a/hook", events=["job_failed"]),
            WebhookConfig(url="https://b/hook", events=["job_failed"], enabled=False),
            WebhookConfig(url="https://c/hook", events=[]),
        ]
        with patch("core.webhooks.store.get_webhooks", AsyncMock(return_value=hooks)):
            yield hooks

    async def test_only_enabled_subscribed_webhooks_get_the_event(self, webhooks):
        with patch("core.webhooks.send", AsyncMock()) as send_mock:
            await fire_event("job_failed", {"file_path": "a.mkv"})
            for t in list(_send_tasks):
                await t
        urls = [c.args[0].url for c in send_mock.call_args_list]
        assert urls == ["https://a/hook"]

    async def test_unsubscribed_event_sends_nothing(self, webhooks):
        with patch("core.webhooks.send", AsyncMock()) as send_mock:
            await fire_event("queue_stalled", {})
            for t in list(_send_tasks):
                await t
        assert not send_mock.called
