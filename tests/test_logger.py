from core.logger import filter_level

DEBUG = "2026-09-11 10:00:00,000 DEBUG    undarr - Probing Video.Title.mkv"
INFO = "2026-09-11 10:00:01,000 INFO     undarr - Settings updated: cache_dir"
WARNING = "2026-09-11 10:00:02,000 WARNING  undarr - Webhook delivery failed: timed out"
ERROR = "2026-09-11 10:00:03,000 ERROR    undarr - Job 3 failed"
TRACEBACK = [
    "Traceback (most recent call last):",
    '  File "core/queue_manager.py", line 1, in _run_job',
    "RuntimeError: boom",
]
LINES = [DEBUG, INFO, WARNING, ERROR, *TRACEBACK, INFO]


class TestFilterLevel:
    def test_debug_keeps_everything(self):
        assert filter_level(LINES, "DEBUG") == LINES

    def test_threshold_drops_lower_levels(self):
        assert filter_level(LINES, "WARNING") == [WARNING, ERROR, *TRACEBACK]

    def test_traceback_follows_its_entry(self):
        assert filter_level(LINES, "ERROR") == [ERROR, *TRACEBACK]

    def test_traceback_dropped_with_its_entry(self):
        assert filter_level([WARNING, *TRACEBACK, ERROR], "ERROR") == [ERROR]

    def test_lines_before_the_first_entry_are_dropped(self):
        assert filter_level(["RuntimeError: boom", INFO], "INFO") == [INFO]

    def test_message_text_is_not_an_entry(self):
        lines = [ERROR, "3 files ERROR skipped", INFO]
        assert filter_level(lines, "INFO") == lines
        assert filter_level(lines, "ERROR") == [ERROR, "3 files ERROR skipped"]
