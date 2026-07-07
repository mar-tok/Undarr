from core.skip_rules import _compare, should_skip, match_path_pattern, format_rule
from core.yaml_store import SkipRule, SkipCondition


class TestCompare:
    def test_equals_case_insensitive(self):
        assert _compare("HEVC", "equals", "hevc") is True

    def test_equals_mismatch(self):
        assert _compare("h264", "equals", "hevc") is False

    def test_equals_numeric_string(self):
        assert _compare(1080, "equals", "1080") is True

    def test_not_equals(self):
        assert _compare("h264", "not_equals", "hevc") is True

    def test_not_equals_same(self):
        assert _compare("hevc", "not_equals", "HEVC") is False

    def test_less_than(self):
        assert _compare(100, "less_than", 200) is True

    def test_less_than_equal(self):
        assert _compare(200, "less_than", 200) is False

    def test_less_than_string_numbers(self):
        assert _compare("100", "less_than", "200") is True

    def test_less_than_non_numeric(self):
        assert _compare("abc", "less_than", "200") is False

    def test_greater_than(self):
        assert _compare(300, "greater_than", 200) is True

    def test_greater_than_equal(self):
        assert _compare(200, "greater_than", 200) is False

    def test_greater_than_non_numeric(self):
        assert _compare("abc", "greater_than", "200") is False

    def test_greater_than_mixed_types(self):
        assert _compare(0.45, "greater_than", "0.4") is True

    def test_contains(self):
        assert _compare("libx265", "contains", "x265") is True

    def test_contains_case_insensitive(self):
        assert _compare("LIBX265", "contains", "x265") is True

    def test_contains_no_match(self):
        assert _compare("libx264", "contains", "x265") is False

    def test_unknown_operator(self):
        assert _compare("a", "bogus", "b") is False


def _rule(*conds):
    return SkipRule(
        conditions=[SkipCondition(field=f, operator=o, value=v) for f, o, v in conds]
    )


class TestShouldSkip:
    def test_single_condition_match(self):
        rules = [_rule(("video_codec", "equals", "hevc"))]
        assert (
            should_skip({"video_codec": "hevc", "bitrate_kbps": 5000}, rules)
            is rules[0]
        )

    def test_single_condition_no_match(self):
        rules = [_rule(("video_codec", "equals", "av1"))]
        assert should_skip({"video_codec": "hevc"}, rules) is None

    def test_missing_field(self):
        rules = [_rule(("nonexistent", "equals", "x"))]
        assert should_skip({"video_codec": "hevc"}, rules) is None

    def test_first_rule_wins(self):
        rules = [
            _rule(("video_codec", "equals", "hevc")),
            _rule(("bitrate_kbps", "less_than", 1000)),
        ]
        assert (
            should_skip({"video_codec": "hevc", "bitrate_kbps": 500}, rules) is rules[0]
        )

    def test_empty_rules(self):
        assert should_skip({"video_codec": "hevc"}, []) is None

    def test_compound_all_match(self):
        rules = [
            _rule(
                ("video_codec", "equals", "hevc"), ("bitrate_kbps", "less_than", 3000)
            )
        ]
        assert (
            should_skip({"video_codec": "hevc", "bitrate_kbps": 2000}, rules)
            is rules[0]
        )

    def test_compound_partial_match(self):
        rules = [
            _rule(
                ("video_codec", "equals", "hevc"), ("bitrate_kbps", "less_than", 3000)
            )
        ]
        assert should_skip({"video_codec": "hevc", "bitrate_kbps": 5000}, rules) is None

    def test_compound_missing_field_fails(self):
        rules = [
            _rule(("video_codec", "equals", "hevc"), ("nonexistent", "equals", "x"))
        ]
        assert should_skip({"video_codec": "hevc"}, rules) is None

    def test_or_between_rules(self):
        rules = [
            _rule(("video_codec", "equals", "hevc")),
            _rule(("bitrate_kbps", "less_than", 1000)),
        ]
        # Only second matches
        assert (
            should_skip({"video_codec": "h264", "bitrate_kbps": 500}, rules) is rules[1]
        )
        # Neither matches
        assert should_skip({"video_codec": "h264", "bitrate_kbps": 5000}, rules) is None

    def test_empty_conditions_skipped(self):
        rule = SkipRule(conditions=[])
        assert should_skip({"video_codec": "hevc"}, [rule]) is None

    def test_three_conditions(self):
        rules = [
            _rule(
                ("video_codec", "equals", "hevc"),
                ("bitrate_kbps", "less_than", 5000),
                ("resolution_height", "greater_than", 720),
            )
        ]
        assert (
            should_skip(
                {
                    "video_codec": "hevc",
                    "bitrate_kbps": 3000,
                    "resolution_height": 1080,
                },
                rules,
            )
            is rules[0]
        )
        assert (
            should_skip(
                {"video_codec": "hevc", "bitrate_kbps": 3000, "resolution_height": 480},
                rules,
            )
            is None
        )


class TestFormatRule:
    def test_single_condition(self):
        rule = _rule(("video_codec", "equals", "hevc"))
        assert format_rule(rule) == "video_codec equals hevc"

    def test_compound(self):
        rule = _rule(
            ("video_codec", "equals", "hevc"), ("bitrate_kbps", "less_than", 3000)
        )
        assert (
            format_rule(rule)
            == "video_codec equals hevc AND bitrate_kbps less_than 3000"
        )


class TestMatchPathPattern:
    def test_basic_glob(self):
        assert match_path_pattern("extras/behind.mkv", ["*/extras/*"]) == "*/extras/*"

    def test_case_insensitive(self):
        assert match_path_pattern("Extras/Behind.mkv", ["*/extras/*"]) == "*/extras/*"

    def test_case_insensitive_pattern(self):
        assert match_path_pattern("extras/behind.mkv", ["*/Extras/*"]) == "*/Extras/*"

    def test_leading_slash_prepended(self):
        # The function prepends "/" to rel_path, so patterns must account for it
        assert match_path_pattern("sample.mkv", ["/*sample*"]) == "/*sample*"

    def test_no_match(self):
        assert match_path_pattern("movie.mkv", ["*/extras/*"]) is None

    def test_multiple_patterns_first_match(self):
        patterns = ["*/extras/*", "*sample*"]
        assert match_path_pattern("extras/clip.mkv", patterns) == "*/extras/*"

    def test_directory_separator(self):
        assert match_path_pattern("a/b/c/sample.mkv", ["*sample*"]) == "*sample*"
