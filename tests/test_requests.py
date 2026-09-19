import pytest
from pydantic import ValidationError

from app.models.requests import (
    LibraryCreate,
    PresetCreate,
    PreviewRequest,
    SkipConditionIn,
)


def _library(**overrides) -> dict:
    body = {"name": "Movies", "paths": ["/media/movies"], "preset": "HEVC Transparent"}
    body.update(overrides)
    return body


def _error(exc: ValidationError) -> str:
    return exc.errors()[0]["msg"]


class TestName:
    def test_stripped(self):
        assert PresetCreate(name="  x  ", ffmpeg_args="-c:v libx265").name == "x"

    @pytest.mark.parametrize("name", ["", "   "])
    def test_empty_rejected(self, name):
        with pytest.raises(ValidationError) as exc:
            PresetCreate(name=name, ffmpeg_args="-c:v libx265")
        assert "cannot be empty" in _error(exc.value)

    def test_slash_rejected(self):
        with pytest.raises(ValidationError) as exc:
            LibraryCreate(**_library(name="TV/Anime"))
        assert "cannot contain /" in _error(exc.value)


class TestResolutionCap:
    def test_none_allowed(self):
        assert PresetCreate(name="x", ffmpeg_args="a").resolution_cap is None

    @pytest.mark.parametrize("cap", [0, -720])
    def test_non_positive_rejected(self, cap):
        with pytest.raises(ValidationError) as exc:
            PresetCreate(name="x", ffmpeg_args="a", resolution_cap=cap)
        assert "greater than 0" in _error(exc.value)


class TestLibraryPaths:
    def test_empty_list_rejected(self):
        with pytest.raises(ValidationError) as exc:
            LibraryCreate(**_library(paths=[]))
        assert "At least one path" in _error(exc.value)

    def test_relative_rejected(self):
        with pytest.raises(ValidationError) as exc:
            LibraryCreate(**_library(paths=["/media/movies", "tv"]))
        assert _error(exc.value).endswith("Paths must be absolute: tv")

    def test_preview_shares_the_check(self):
        with pytest.raises(ValidationError):
            PreviewRequest(paths=[])


class TestLibraryIntervals:
    @pytest.mark.parametrize("field", ["scan_unit", "new_file_delay_unit"])
    def test_unknown_unit_rejected(self, field):
        with pytest.raises(ValidationError) as exc:
            LibraryCreate(**_library(**{field: "fortnights"}))
        assert _error(exc.value).endswith(
            f"{field} must be one of: seconds, minutes, hours, days"
        )

    @pytest.mark.parametrize("field", ["scan_interval", "new_file_delay"])
    def test_negative_rejected(self, field):
        with pytest.raises(ValidationError) as exc:
            LibraryCreate(**_library(**{field: -1}))
        assert _error(exc.value).endswith(f"{field} must be 0 or greater")

    def test_zero_allowed(self):
        lib = LibraryCreate(**_library(scan_interval=0, new_file_delay=0))
        assert lib.scan_interval == 0


class TestSkipCondition:
    def test_unknown_field_rejected(self):
        with pytest.raises(ValidationError) as exc:
            SkipConditionIn(field="codec", operator="equals", value="hevc")
        assert "field must be one of" in _error(exc.value)

    def test_unknown_operator_rejected(self):
        with pytest.raises(ValidationError) as exc:
            SkipConditionIn(field="video_codec", operator="lt", value="hevc")
        assert "operator must be one of" in _error(exc.value)

    @pytest.mark.parametrize("value", ["abc", "", "10 MB"])
    def test_numeric_operator_needs_a_number(self, value):
        with pytest.raises(ValidationError) as exc:
            SkipConditionIn(field="file_size_mb", operator="less_than", value=value)
        assert "must be a number" in _error(exc.value)

    @pytest.mark.parametrize("value", ["500", 500, 1.5])
    def test_numeric_operator_accepts_numbers(self, value):
        cond = SkipConditionIn(
            field="file_size_mb", operator="greater_than", value=value
        )
        assert cond.value == value

    def test_contains_needs_a_value(self):
        with pytest.raises(ValidationError) as exc:
            SkipConditionIn(field="video_codec", operator="contains", value=" ")
        assert "value is required" in _error(exc.value)

    @pytest.mark.parametrize("operator", ["equals", "not_equals"])
    def test_equality_allows_empty_value(self, operator):
        cond = SkipConditionIn(field="hdr_type", operator=operator, value="")
        assert cond.value == ""
