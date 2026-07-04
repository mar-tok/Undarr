import pytest

from core.ffmpeg import build_subtitle_args
from core.ffprobe import extract_subtitle_streams
from core.yaml_store import (
    SubtitleConfig,
    Preset,
    AudioConfig,
    AudioTrackConfig,
    _config_from_dict,
    _config_to_dict,
    Config,
)

# Helpers


def _sub_stream(codec="subrip", language="eng", commentary=False):
    return {
        "codec_name": codec,
        "language": language,
        "is_commentary": commentary,
    }


# extract_subtitle_streams


def test_extract_subtitle_streams_basic():
    probe = {
        "streams": [
            {"codec_type": "video", "codec_name": "hevc"},
            {"codec_type": "audio", "codec_name": "aac", "channels": 2},
            {
                "codec_type": "subtitle",
                "codec_name": "subrip",
                "tags": {"language": "eng"},
                "disposition": {"comment": 0},
            },
            {
                "codec_type": "subtitle",
                "codec_name": "ass",
                "tags": {"language": "nor"},
                "disposition": {"comment": 1},
            },
        ]
    }
    result = extract_subtitle_streams(probe)
    assert len(result) == 2
    assert result[0]["codec_name"] == "subrip"
    assert result[0]["language"] == "eng"
    assert result[0]["is_commentary"] is False
    assert result[1]["codec_name"] == "ass"
    assert result[1]["language"] == "nor"
    assert result[1]["is_commentary"] is True


def test_extract_subtitle_streams_no_subs():
    probe = {
        "streams": [
            {"codec_type": "video", "codec_name": "hevc"},
            {"codec_type": "audio", "codec_name": "aac", "channels": 2},
        ]
    }
    assert extract_subtitle_streams(probe) == []


def test_extract_subtitle_streams_no_language_tag():
    probe = {
        "streams": [
            {
                "codec_type": "subtitle",
                "codec_name": "subrip",
                "tags": {},
                "disposition": {"comment": 0},
            },
        ]
    }
    result = extract_subtitle_streams(probe)
    assert result[0]["language"] == "und"


# build_subtitle_args: mode "keep"


def test_keep_returns_none():
    cfg = SubtitleConfig(mode="keep")
    result = build_subtitle_args(cfg, [_sub_stream()])
    assert result is None


# build_subtitle_args: mode "remove"


def test_remove_returns_empty():
    cfg = SubtitleConfig(mode="remove")
    result = build_subtitle_args(cfg, [_sub_stream(), _sub_stream(language="nor")])
    assert result == []


# build_subtitle_args: mode "keep_by_language"


def test_keep_by_language_filters():
    cfg = SubtitleConfig(mode="keep_by_language", languages=["eng"])
    streams = [
        _sub_stream(language="eng"),
        _sub_stream(language="nor"),
        _sub_stream(language="swe"),
    ]
    result = build_subtitle_args(cfg, streams)
    assert result == ["-map", "0:s:0"]


def test_keep_by_language_maps_source_index():
    cfg = SubtitleConfig(mode="keep_by_language", languages=["eng"])
    streams = [_sub_stream(language="jpn"), _sub_stream(language="eng")]
    result = build_subtitle_args(cfg, streams)
    assert result == ["-map", "0:s:1"]


def test_keep_by_language_keeps_und():
    cfg = SubtitleConfig(mode="keep_by_language", languages=["eng"])
    streams = [_sub_stream(language="und"), _sub_stream(language="jpn")]
    result = build_subtitle_args(cfg, streams)
    assert result == ["-map", "0:s:0"]


def test_keep_by_language_multiple():
    cfg = SubtitleConfig(mode="keep_by_language", languages=["eng", "nor"])
    streams = [
        _sub_stream(language="eng"),
        _sub_stream(language="nor"),
        _sub_stream(language="swe"),
    ]
    result = build_subtitle_args(cfg, streams)
    assert result == ["-map", "0:s:0", "-map", "0:s:1"]


def test_keep_by_language_no_languages_keeps_all():
    cfg = SubtitleConfig(mode="keep_by_language", languages=None)
    streams = [_sub_stream(language="eng"), _sub_stream(language="nor")]
    result = build_subtitle_args(cfg, streams)
    assert result == ["-map", "0:s:0", "-map", "0:s:1"]


def test_keep_by_language_remove_commentary():
    cfg = SubtitleConfig(
        mode="keep_by_language", languages=["eng"], remove_commentary=True
    )
    streams = [
        _sub_stream(language="eng", commentary=False),
        _sub_stream(language="eng", commentary=True),
    ]
    result = build_subtitle_args(cfg, streams)
    assert result == ["-map", "0:s:0"]


def test_keep_by_language_empty_streams():
    cfg = SubtitleConfig(mode="keep_by_language", languages=["eng"])
    result = build_subtitle_args(cfg, [])
    assert result == []


# YAML roundtrip: subtitle config


def test_config_roundtrip_with_subtitle():
    cfg = Config()
    cfg.presets["test"] = Preset(
        ffmpeg_args="-c:s copy -c:v libx265 -crf 28",
        subtitle=SubtitleConfig(
            mode="keep_by_language",
            languages=["eng", "nor"],
            remove_commentary=True,
        ),
    )
    data = _config_to_dict(cfg)
    restored = _config_from_dict(data)
    p = restored.presets["test"]
    assert p.subtitle is not None
    assert p.subtitle.mode == "keep_by_language"
    assert p.subtitle.languages == ["eng", "nor"]
    assert p.subtitle.remove_commentary is True


def test_config_roundtrip_subtitle_remove():
    cfg = Config()
    cfg.presets["test"] = Preset(
        ffmpeg_args="-c:v libx265",
        subtitle=SubtitleConfig(mode="remove"),
    )
    data = _config_to_dict(cfg)
    restored = _config_from_dict(data)
    p = restored.presets["test"]
    assert p.subtitle is not None
    assert p.subtitle.mode == "remove"
    assert p.subtitle.languages is None
    assert p.subtitle.remove_commentary is False


def test_config_roundtrip_no_subtitle():
    cfg = Config()
    cfg.presets["test"] = Preset(ffmpeg_args="-c:v libx265")
    data = _config_to_dict(cfg)
    restored = _config_from_dict(data)
    assert restored.presets["test"].subtitle is None


def test_config_subtitle_yaml_omits_defaults():
    """YAML output omits fields at their defaults."""
    cfg = Config()
    cfg.presets["test"] = Preset(
        ffmpeg_args="-c:v libx265",
        subtitle=SubtitleConfig(mode="remove"),
    )
    data = _config_to_dict(cfg)
    sub_dict = data["presets"]["test"]["subtitle"]
    assert sub_dict == {"mode": "remove"}
    assert "languages" not in sub_dict
    assert "remove_commentary" not in sub_dict


def test_config_roundtrip_with_resolution_cap():
    cfg = Config()
    cfg.presets["test"] = Preset(
        ffmpeg_args="-c:v libx265",
        resolution_cap=1080,
    )
    data = _config_to_dict(cfg)
    assert data["presets"]["test"]["resolution_cap"] == 1080
    restored = _config_from_dict(data)
    assert restored.presets["test"].resolution_cap == 1080


def test_config_roundtrip_no_resolution_cap():
    cfg = Config()
    cfg.presets["test"] = Preset(ffmpeg_args="-c:v libx265")
    data = _config_to_dict(cfg)
    assert "resolution_cap" not in data["presets"]["test"]
    restored = _config_from_dict(data)
    assert restored.presets["test"].resolution_cap is None


def test_config_roundtrip_all_new_fields():
    """Subtitle + resolution_cap + audio all roundtrip together."""
    cfg = Config()
    cfg.presets["test"] = Preset(
        ffmpeg_args="-c:v libx265 -crf 28",
        audio=AudioConfig(stereo=AudioTrackConfig(codec="aac", bitrate="160k")),
        subtitle=SubtitleConfig(mode="keep_by_language", languages=["eng"]),
        resolution_cap=720,
    )
    data = _config_to_dict(cfg)
    restored = _config_from_dict(data)
    p = restored.presets["test"]
    assert p.audio.stereo.codec == "aac"
    assert p.subtitle.mode == "keep_by_language"
    assert p.subtitle.languages == ["eng"]
    assert p.resolution_cap == 720
