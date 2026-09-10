from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch, AsyncMock
from urllib.error import URLError

import pytest

from core.webhooks import (
    _build_payload,
    _next_digest,
    _ntfy_target,
    _send_digests,
    _text_parts,
    check_top_reduction,
    fire_event,
    send,
    send_test,
    _send_tasks,
)
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

    def test_queue_stalled_lists_reasons(self):
        payload = _build_payload(
            "discord",
            "queue_stalled",
            {"pending_count": 3, "reasons": ["Library 'Movies' is paused"]},
        )
        embed = payload["embeds"][0]
        assert embed["title"] == "Queue Stalled"
        assert (
            embed["description"]
            == "3 pending jobs blocked.\n- Library 'Movies' is paused"
        )

    def test_queue_stalled_singular(self):
        payload = _build_payload("discord", "queue_stalled", {"pending_count": 1})
        assert payload["embeds"][0]["description"] == "1 pending job blocked."

    def test_daily_digest_color_follows_failures(self):
        clean = _build_payload(
            "discord",
            "daily_digest",
            {"completed": 4, "failed": 0, "space_saved_bytes": 3 * 1073741824},
        )
        assert clean["embeds"][0]["description"] == "4 completed, 3.0 GB saved"
        assert clean["embeds"][0]["color"] == 5763719
        failed = _build_payload(
            "discord",
            "daily_digest",
            {"completed": 1, "failed": 2, "space_saved_bytes": 0},
        )
        assert failed["embeds"][0]["description"] == "1 completed, 2 failed"
        assert failed["embeds"][0]["color"] == 16776960

    def test_daily_digest_growth_and_empty(self):
        grown = _build_payload(
            "discord", "daily_digest", {"completed": 1, "space_saved_bytes": -2048}
        )
        assert grown["embeds"][0]["description"] == "1 completed, 2.0 KB added"
        empty = _build_payload("discord", "daily_digest", {})
        assert empty["embeds"][0]["description"] == "No activity."

    def test_top_reduction_sizes(self):
        payload = _build_payload(
            "discord",
            "top_reduction",
            {
                "file_path": "/media/Movies/Video.Title.mkv",
                "old_size_bytes": 4 * 1073741824,
                "new_size_bytes": 1073741824,
            },
        )
        embed = payload["embeds"][0]
        assert embed["title"] == "New Top Reduction"
        assert (
            embed["description"]
            == "Video.Title.mkv\n4.0 GB \u2192 1.0 GB (75% smaller)"
        )

    def test_test_event(self):
        payload = _build_payload("discord", "test", {})
        assert payload["embeds"][0]["description"] == "Webhook is working."

    def test_unknown_event_falls_back_to_content(self):
        payload = _build_payload("discord", "something_else", {})
        assert payload == {"content": "Undarr: something_else"}

    def test_unknown_template_uses_discord(self):
        payload = _build_payload("nope", "test", {})
        assert "embeds" in payload


# Text templates


class TestTextParts:
    def test_job_failed_lines(self):
        title, body = _text_parts(
            "job_failed",
            {
                "file_path": "/media/Movies/Video.Title.mkv",
                "error_message": "ffmpeg exited with code 1",
                "preset_name": "HEVC Transparent",
                "device_name": "CPU",
            },
        )
        assert title == "Job Failed"
        assert body.split("\n") == [
            "Video.Title.mkv",
            "Error: ffmpeg exited with code 1",
            "Preset: HEVC Transparent, Device: CPU",
        ]

    @pytest.mark.parametrize(
        "data, last",
        [
            ({"preset_name": "HEVC Transparent"}, "Preset: HEVC Transparent"),
            ({"device_name": "CPU"}, "Device: CPU"),
        ],
    )
    def test_job_failed_single_origin(self, data, last):
        _, body = _text_parts("job_failed", {"file_path": "a.mkv", **data})
        assert body.split("\n")[-1] == last

    def test_job_failed_without_origin(self):
        _, body = _text_parts("job_failed", {"file_path": "a.mkv"})
        assert body == "a.mkv\nError: No error details"

    def test_other_events_share_the_discord_text(self):
        stalled = _text_parts("queue_stalled", {"pending_count": 2, "reasons": ["x"]})
        assert stalled == ("Queue Stalled", "2 pending jobs blocked.\n- x")
        digest = _text_parts(
            "daily_digest", {"completed": 2, "space_saved_bytes": 1024}
        )
        assert digest == ("Daily Digest", "2 completed, 1.0 KB saved")
        top = _text_parts(
            "top_reduction",
            {"file_path": "a.mkv", "old_size_bytes": 2048, "new_size_bytes": 1024},
        )
        assert top == ("New Top Reduction", "a.mkv\n2.0 KB \u2192 1.0 KB (50% smaller)")

    def test_test_and_unknown_events(self):
        assert _text_parts("test", {}) == ("Undarr", "Webhook is working.")
        assert _text_parts("something_else", {}) == ("Undarr", "something_else")


class TestTextPayloads:
    def test_ntfy_priority_per_event(self):
        failed = _build_payload("ntfy", "job_failed", {"file_path": "a.mkv"})
        assert failed["title"] == "Job Failed"
        assert failed["message"].startswith("a.mkv")
        assert failed["priority"] == 4
        assert _build_payload("ntfy", "queue_stalled", {})["priority"] == 4
        assert _build_payload("ntfy", "daily_digest", {})["priority"] == 3
        assert _build_payload("ntfy", "test", {})["priority"] == 3

    def test_gotify_priority_per_event(self):
        failed = _build_payload("gotify", "job_failed", {"file_path": "a.mkv"})
        assert failed["title"] == "Job Failed"
        assert failed["priority"] == 8
        assert _build_payload("gotify", "queue_stalled", {})["priority"] == 8
        assert _build_payload("gotify", "top_reduction", {})["priority"] == 5
        assert _build_payload("gotify", "test", {})["priority"] == 5

    def test_generic_wraps_data_verbatim(self):
        data = {"file_path": "a.mkv", "status": "failed", "seq": 3}
        payload = _build_payload("generic", "job_failed", data)
        assert payload["event"] == "job_failed"
        assert payload["data"] == data
        assert payload["timestamp"].endswith("+00:00")


class TestNtfyTarget:
    @pytest.mark.parametrize(
        "url, root, topic",
        [
            ("https://ntfy.sh/undarr", "https://ntfy.sh/", "undarr"),
            ("https://ntfy.sh/undarr/", "https://ntfy.sh/", "undarr"),
            ("http://10.0.0.5:8080/alerts", "http://10.0.0.5:8080/", "alerts"),
            (
                "https://ntfy.sh/undarr?auth=abc",
                "https://ntfy.sh/?auth=abc",
                "undarr",
            ),
        ],
    )
    def test_topic_moves_to_body(self, url, root, topic):
        assert _ntfy_target(url) == (root, topic)


# Delivery


class TestSend:
    async def test_posts_json_to_url(self):
        wh = WebhookConfig(url="https://example.com/hook", events=["job_failed"])
        with patch("core.webhooks._send_sync") as sync:
            await send(wh, "test", {})
        url, payload = sync.call_args.args
        assert url == "https://example.com/hook"
        assert payload["embeds"][0]["title"] == "Undarr"

    async def test_ntfy_posts_to_root_with_topic(self):
        wh = WebhookConfig(url="https://ntfy.sh/undarr", template="ntfy")
        with patch("core.webhooks._send_sync") as sync:
            await send(wh, "test", {})
        url, payload = sync.call_args.args
        assert url == "https://ntfy.sh/"
        assert payload["topic"] == "undarr"
        assert payload["title"] == "Undarr"

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

    async def test_send_test_uses_the_template(self):
        wh = WebhookConfig(url="https://ntfy.sh/undarr", template="ntfy")
        with patch("core.webhooks._send_sync") as sync:
            await send_test(wh)
        url, payload = sync.call_args.args
        assert url == "https://ntfy.sh/"
        assert payload["message"] == "Webhook is working."


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


# Top reduction


class TestCheckTopReduction:
    def _job(self, path="/media/Movies/Video.Title.mkv"):
        return SimpleNamespace(file_path=path, old_size_bytes=2048, new_size_bytes=1024)

    async def test_fires_when_the_job_leads(self):
        hooks = [WebhookConfig(url="https://a/hook", events=["top_reduction"])]
        top = [{"file_path": "/media/Movies/Video.Title.mkv"}]
        with (
            patch("core.webhooks.store.get_webhooks", AsyncMock(return_value=hooks)),
            patch(
                "core.webhooks.db.get_stats_top_savings", AsyncMock(return_value=top)
            ),
            patch("core.webhooks.fire_event", AsyncMock()) as fire,
        ):
            await check_top_reduction(self._job())
        event, data = fire.call_args.args
        assert event == "top_reduction"
        assert data == {
            "file_path": "/media/Movies/Video.Title.mkv",
            "old_size_bytes": 2048,
            "new_size_bytes": 1024,
        }

    async def test_silent_when_another_file_leads(self):
        hooks = [WebhookConfig(url="https://a/hook", events=["top_reduction"])]
        top = [{"file_path": "/media/Movies/Other.mkv"}]
        with (
            patch("core.webhooks.store.get_webhooks", AsyncMock(return_value=hooks)),
            patch(
                "core.webhooks.db.get_stats_top_savings", AsyncMock(return_value=top)
            ),
            patch("core.webhooks.fire_event", AsyncMock()) as fire,
        ):
            await check_top_reduction(self._job())
        assert not fire.called

    async def test_skips_the_query_without_a_subscriber(self):
        hooks = [WebhookConfig(url="https://a/hook", events=["job_failed"])]
        with (
            patch("core.webhooks.store.get_webhooks", AsyncMock(return_value=hooks)),
            patch("core.webhooks.db.get_stats_top_savings", AsyncMock()) as query,
        ):
            await check_top_reduction(self._job())
        assert not query.called


# Daily digest


class TestNextDigest:
    @pytest.mark.parametrize(
        "now, delay, hour, day",
        [
            (datetime(2026, 9, 10, 7, 59, 30), 30.0, 8, "2026-09-09"),
            (datetime(2026, 9, 10, 8, 0, 0), 3600.0, 9, "2026-09-09"),
            (datetime(2026, 9, 10, 23, 30, 0), 1800.0, 0, "2026-09-10"),
            (datetime(2026, 10, 1, 0, 15, 0), 2700.0, 1, "2026-09-30"),
        ],
    )
    def test_sleeps_to_the_boundary_and_names_the_day_before(
        self, now, delay, hour, day
    ):
        assert _next_digest(now) == (delay, hour, day)


class TestSendDigests:
    @pytest.fixture
    def hooks(self):
        hooks = [
            WebhookConfig(url="https://a/hook", events=["daily_digest"], digest_hour=8),
            WebhookConfig(url="https://b/hook", events=["daily_digest"], digest_hour=9),
            WebhookConfig(
                url="https://c/hook",
                events=["daily_digest"],
                digest_hour=8,
                enabled=False,
            ),
            WebhookConfig(url="https://d/hook", events=["job_failed"], digest_hour=8),
        ]
        with patch("core.webhooks.store.get_webhooks", AsyncMock(return_value=hooks)):
            yield hooks

    async def test_sends_the_day_to_hooks_on_that_hour(self, hooks):
        daily = [
            {
                "date": "2026-09-09",
                "completed": 3,
                "failed": 1,
                "space_saved_bytes": 10,
            },
            {"date": "2026-09-10", "completed": 1, "failed": 0, "space_saved_bytes": 5},
        ]
        with (
            patch("core.webhooks.db.get_stats_daily", AsyncMock(return_value=daily)),
            patch("core.webhooks.send", AsyncMock()) as send_mock,
        ):
            await _send_digests(8, "2026-09-09")
        calls = [
            (c.args[0].url, c.args[1], c.args[2]) for c in send_mock.call_args_list
        ]
        assert calls == [("https://a/hook", "daily_digest", daily[0])]

    async def test_silent_for_a_day_without_a_row(self, hooks):
        with (
            patch("core.webhooks.db.get_stats_daily", AsyncMock(return_value=[])),
            patch("core.webhooks.send", AsyncMock()) as send_mock,
        ):
            await _send_digests(8, "2026-09-09")
        assert not send_mock.called

    async def test_skips_the_query_when_no_hook_matches_the_hour(self, hooks):
        with (
            patch("core.webhooks.db.get_stats_daily", AsyncMock()) as query,
            patch("core.webhooks.send", AsyncMock()),
        ):
            await _send_digests(3, "2026-09-09")
        assert not query.called
