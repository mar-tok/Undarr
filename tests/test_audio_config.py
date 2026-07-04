import pytest

from core.ffmpeg import (
    build_audio_args,
    strip_audio_flags,
    _audio_stream_matches,
    _parse_bitrate_k,
)
from core.ffprobe import extract_audio_streams
from core.yaml_store import (
    AudioConfig,
    AudioTrackConfig,
    Preset,
    _config_from_dict,
    _config_to_dict,
    Config,
)

# Helpers


def _stream(codec="aac", channels=2, bit_rate=128000, language="eng", commentary=False):
    return {
        "index": 0,
        "codec_name": codec,
        "channels": channels,
        "bit_rate": bit_rate,
        "language": language,
        "is_commentary": commentary,
    }


# _parse_bitrate_k


@pytest.mark.parametrize(
    "value, expected",
    [
        ("160k", 160),
        ("640K", 640),
        ("128", 128),
    ],
)
def test_parse_bitrate_k(value, expected):
    assert _parse_bitrate_k(value) == expected


# _audio_stream_matches


@pytest.mark.parametrize(
    "stream, codec, bitrate, channels, expected",
    [
        (
            {"codec_name": "aac", "channels": 2, "bit_rate": 128000},
            "aac",
            160,
            None,
            True,
        ),
        (
            {"codec_name": "aac", "channels": 2, "bit_rate": 96000},
            "aac",
            160,
            None,
            True,
        ),
        (
            {"codec_name": "dts", "channels": 6, "bit_rate": 768000},
            "aac",
            160,
            None,
            False,
        ),
        (
            {"codec_name": "aac", "channels": 2, "bit_rate": 256000},
            "aac",
            160,
            None,
            False,
        ),
        (
            {"codec_name": "aac", "channels": 2, "bit_rate": None},
            "aac",
            160,
            None,
            True,
        ),
        (
            {"codec_name": "aac", "channels": 2, "bit_rate": 320000},
            "aac",
            None,
            None,
            True,
        ),
        (
            {"codec_name": "aac", "channels": 6, "bit_rate": 128000},
            "aac",
            160,
            2,
            False,
        ),
        (
            {"codec_name": "aac", "channels": 2, "bit_rate": 128000},
            "aac",
            160,
            2,
            True,
        ),
    ],
)
def test_audio_stream_matches(stream, codec, bitrate, channels, expected):
    assert _audio_stream_matches(stream, codec, bitrate, channels) is expected


# build_audio_args: basic cases


def test_build_both_none():
    """Both tiers None = safety fallback to copy."""
    cfg = AudioConfig()
    result = build_audio_args(cfg, [])
    assert result.map_args is None
    assert result.codec_args == "-c:a copy"


def test_build_both_copy_no_filtering():
    cfg = AudioConfig(
        stereo=AudioTrackConfig(codec="copy"),
        surround=AudioTrackConfig(codec="copy"),
    )
    result = build_audio_args(cfg, [_stream()])
    assert result.map_args is None
    assert result.codec_args == "-c:a copy"


def test_build_no_streams():
    cfg = AudioConfig(stereo=AudioTrackConfig(codec="aac", bitrate="160k"))
    result = build_audio_args(cfg, [])
    assert result.map_args is None
    assert result.codec_args == ""


# build_audio_args: tier classification


def test_build_stereo_gets_stereo_config():
    cfg = AudioConfig(
        stereo=AudioTrackConfig(codec="aac", bitrate="160k"),
        surround=AudioTrackConfig(codec="copy"),
    )
    streams = [_stream(codec="dts", channels=2, bit_rate=768000)]
    result = build_audio_args(cfg, streams)
    assert result.map_args == ["-map", "0:a:0"]
    assert "-c:a:0 aac" in result.codec_args
    assert "-b:a:0 160k" in result.codec_args


def test_build_surround_gets_surround_config():
    cfg = AudioConfig(
        stereo=AudioTrackConfig(codec="aac", bitrate="160k"),
        surround=AudioTrackConfig(codec="ac3", bitrate="640k"),
    )
    streams = [_stream(codec="dts", channels=6, bit_rate=768000)]
    result = build_audio_args(cfg, streams)
    assert result.map_args == ["-map", "0:a:0"]
    assert "-c:a:0 ac3" in result.codec_args
    assert "-b:a:0 640k" in result.codec_args


def test_build_mixed_tiers():
    cfg = AudioConfig(
        stereo=AudioTrackConfig(codec="aac", bitrate="160k"),
        surround=AudioTrackConfig(codec="copy"),
    )
    streams = [
        _stream(codec="aac", channels=2, bit_rate=128000),
        _stream(codec="dts", channels=6, bit_rate=768000),
    ]
    result = build_audio_args(cfg, streams)
    assert result.map_args == ["-map", "0:a:0", "-map", "0:a:1"]
    # Stereo AAC 128k matches target AAC 160k, so copy
    assert "-c:a:0 copy" in result.codec_args
    assert "-c:a:1 copy" in result.codec_args


def test_build_stream_already_matches_copies():
    cfg = AudioConfig(
        stereo=AudioTrackConfig(codec="aac", bitrate="160k"),
    )
    streams = [_stream(codec="aac", channels=2, bit_rate=128000)]
    result = build_audio_args(cfg, streams)
    assert "-c:a:0 copy" in result.codec_args


def test_build_missing_tier_falls_back_to_copy():
    cfg = AudioConfig(
        surround=AudioTrackConfig(codec="ac3", bitrate="640k"),
    )
    streams = [_stream(codec="aac", channels=2, bit_rate=128000)]
    result = build_audio_args(cfg, streams)
    assert result.map_args == ["-map", "0:a:0"]
    assert "-c:a:0 copy" in result.codec_args


def test_build_opus_alias():
    """libopus encoder matches opus codec_name from ffprobe."""
    cfg = AudioConfig(
        stereo=AudioTrackConfig(codec="libopus", bitrate="128k"),
    )
    streams = [_stream(codec="opus", channels=2, bit_rate=96000)]
    result = build_audio_args(cfg, streams)
    assert "-c:a:0 copy" in result.codec_args


def test_build_opus_transcode():
    cfg = AudioConfig(
        stereo=AudioTrackConfig(codec="libopus", bitrate="128k"),
    )
    streams = [_stream(codec="aac", channels=2, bit_rate=160000)]
    result = build_audio_args(cfg, streams)
    assert "-c:a:0 libopus" in result.codec_args
    assert "-b:a:0 128k" in result.codec_args


# build_audio_args: language filtering


def test_build_language_filter_keeps_matching():
    cfg = AudioConfig(
        stereo=AudioTrackConfig(codec="copy"),
        surround=AudioTrackConfig(codec="copy"),
        languages=["eng"],
    )
    streams = [
        _stream(channels=2, language="eng"),
        _stream(channels=2, language="jpn"),
    ]
    result = build_audio_args(cfg, streams)
    assert result.map_args == ["-map", "0:a:0"]


def test_build_language_filter_keeps_und():
    cfg = AudioConfig(
        stereo=AudioTrackConfig(codec="copy"),
        languages=["eng"],
    )
    streams = [
        _stream(channels=2, language="und"),
        _stream(channels=2, language="jpn"),
    ]
    result = build_audio_args(cfg, streams)
    assert result.map_args == ["-map", "0:a:0"]


def test_build_no_language_filter_keeps_all():
    cfg = AudioConfig(
        stereo=AudioTrackConfig(codec="copy"),
        surround=AudioTrackConfig(codec="copy"),
    )
    streams = [
        _stream(channels=2, language="eng"),
        _stream(channels=2, language="jpn"),
    ]
    result = build_audio_args(cfg, streams)
    # Has filtering (languages != None) is False, both copy -> simple global copy
    assert result.map_args is None
    assert result.codec_args == "-c:a copy"


# build_audio_args: commentary removal


def test_build_remove_commentary():
    cfg = AudioConfig(
        stereo=AudioTrackConfig(codec="copy"),
        remove_commentary=True,
    )
    streams = [
        _stream(channels=2, commentary=False),
        _stream(channels=2, commentary=True),
    ]
    result = build_audio_args(cfg, streams)
    assert result.map_args == ["-map", "0:a:0"]


# build_audio_args: downmix


def test_build_downmix():
    cfg = AudioConfig(
        surround=AudioTrackConfig(codec="copy"),
        add_stereo_downmix="always",
        downmix_bitrate="160k",
    )
    streams = [_stream(codec="ac3", channels=6, bit_rate=640000)]
    result = build_audio_args(cfg, streams)
    assert result.map_args == ["-map", "0:a:0", "-map", "0:a:0"]
    assert "-c:a:0 copy" in result.codec_args
    assert "-c:a:1 aac" in result.codec_args
    assert "-b:a:1 160k" in result.codec_args
    assert "-ac:a:1 2" in result.codec_args


def test_build_downmix_multiple_surround():
    """Each surround stream gets its own downmix, output indices interleave."""
    cfg = AudioConfig(
        surround=AudioTrackConfig(codec="copy"),
        add_stereo_downmix="always",
        downmix_bitrate="160k",
    )
    streams = [
        _stream(codec="ac3", channels=6, bit_rate=640000),
        _stream(codec="dts", channels=8, bit_rate=768000),
    ]
    result = build_audio_args(cfg, streams)
    assert result.map_args == [
        "-map",
        "0:a:0",
        "-map",
        "0:a:0",
        "-map",
        "0:a:1",
        "-map",
        "0:a:1",
    ]
    assert "-c:a:0 copy" in result.codec_args
    assert "-c:a:1 aac" in result.codec_args
    assert "-ac:a:1 2" in result.codec_args
    assert "-c:a:2 copy" in result.codec_args
    assert "-c:a:3 aac" in result.codec_args
    assert "-b:a:3 160k" in result.codec_args
    assert "-ac:a:3 2" in result.codec_args


def test_build_downmix_stereo_stream_no_downmix():
    cfg = AudioConfig(
        stereo=AudioTrackConfig(codec="copy"),
        surround=AudioTrackConfig(codec="copy"),
        add_stereo_downmix="always",
        downmix_bitrate="160k",
    )
    streams = [_stream(codec="aac", channels=2, bit_rate=128000)]
    result = build_audio_args(cfg, streams)
    assert result.map_args == ["-map", "0:a:0"]
    assert "-c:a:0 copy" in result.codec_args


def test_build_downmix_if_no_stereo_skips_when_stereo_exists():
    cfg = AudioConfig(
        stereo=AudioTrackConfig(codec="copy"),
        surround=AudioTrackConfig(codec="copy"),
        add_stereo_downmix="if_no_stereo",
        downmix_bitrate="160k",
    )
    streams = [
        _stream(codec="aac", channels=2, bit_rate=128000),
        _stream(codec="ac3", channels=6, bit_rate=640000),
    ]
    result = build_audio_args(cfg, streams)
    assert result.map_args == ["-map", "0:a:0", "-map", "0:a:1"]
    assert "-c:a:0 copy" in result.codec_args
    assert "-c:a:1 copy" in result.codec_args
    assert "aac" not in result.codec_args


def test_build_downmix_if_no_stereo_adds_when_no_stereo():
    cfg = AudioConfig(
        surround=AudioTrackConfig(codec="copy"),
        add_stereo_downmix="if_no_stereo",
        downmix_bitrate="160k",
    )
    streams = [_stream(codec="ac3", channels=6, bit_rate=640000)]
    result = build_audio_args(cfg, streams)
    assert result.map_args == ["-map", "0:a:0", "-map", "0:a:0"]
    assert "-c:a:0 copy" in result.codec_args
    assert "-c:a:1 aac" in result.codec_args
    assert "-b:a:1 160k" in result.codec_args
    assert "-ac:a:1 2" in result.codec_args


def test_build_downmix_if_no_stereo_respects_language_filter():
    cfg = AudioConfig(
        stereo=AudioTrackConfig(codec="copy"),
        surround=AudioTrackConfig(codec="copy"),
        add_stereo_downmix="if_no_stereo",
        downmix_bitrate="160k",
        languages=["jpn"],
    )
    streams = [
        _stream(codec="aac", channels=2, bit_rate=128000, language="eng"),
        _stream(codec="ac3", channels=6, bit_rate=640000, language="jpn"),
    ]
    result = build_audio_args(cfg, streams)
    # English stereo filtered out, only Japanese surround remains, so downmix is added
    assert result.map_args == ["-map", "0:a:1", "-map", "0:a:1"]
    assert "-c:a:0 copy" in result.codec_args
    assert "-c:a:1 aac" in result.codec_args


def test_build_downmix_if_no_stereo_ignores_commentary_stereo():
    cfg = AudioConfig(
        stereo=AudioTrackConfig(codec="copy"),
        surround=AudioTrackConfig(codec="copy"),
        add_stereo_downmix="if_no_stereo",
        downmix_bitrate="160k",
        remove_commentary=True,
    )
    streams = [
        _stream(codec="aac", channels=2, bit_rate=128000, commentary=True),
        _stream(codec="ac3", channels=6, bit_rate=640000),
    ]
    result = build_audio_args(cfg, streams)
    # Commentary stereo removed, only surround remains, so downmix is added
    assert result.map_args == ["-map", "0:a:1", "-map", "0:a:1"]
    assert "-c:a:0 copy" in result.codec_args
    assert "-c:a:1 aac" in result.codec_args
    assert "-ac:a:1 2" in result.codec_args


# build_audio_args: full scenario


def test_build_full_scenario():
    """3 audio streams: filter by language, downmix surround, tier handling."""
    cfg = AudioConfig(
        stereo=AudioTrackConfig(codec="aac", bitrate="160k"),
        surround=AudioTrackConfig(codec="copy"),
        languages=["eng"],
        add_stereo_downmix="always",
        downmix_bitrate="160k",
    )
    streams = [
        _stream(codec="aac", channels=2, bit_rate=128000, language="eng"),  # stereo eng
        _stream(
            codec="ac3", channels=6, bit_rate=640000, language="eng"
        ),  # surround eng
        _stream(
            codec="ac3", channels=6, bit_rate=640000, language="jpn"
        ),  # surround jpn
    ]
    result = build_audio_args(cfg, streams)
    # Japanese stream dropped. Stereo AAC copied. Surround AC3 copied + downmix.
    assert result.map_args == ["-map", "0:a:0", "-map", "0:a:1", "-map", "0:a:1"]
    assert "-c:a:0 copy" in result.codec_args  # AAC stereo matches
    assert "-c:a:1 copy" in result.codec_args  # AC3 surround copy
    assert "-c:a:2 aac" in result.codec_args  # downmix
    assert "-b:a:2 160k" in result.codec_args
    assert "-ac:a:2 2" in result.codec_args


def test_build_reencode_scenario():
    """DTS surround re-encoded to AC3, AAC stereo copied."""
    cfg = AudioConfig(
        stereo=AudioTrackConfig(codec="aac", bitrate="160k"),
        surround=AudioTrackConfig(codec="ac3", bitrate="640k"),
    )
    streams = [
        _stream(codec="dts", channels=6, bit_rate=768000),
        _stream(codec="aac", channels=2, bit_rate=128000),
    ]
    result = build_audio_args(cfg, streams)
    assert result.map_args == ["-map", "0:a:0", "-map", "0:a:1"]
    assert "-c:a:0 ac3" in result.codec_args
    assert "-b:a:0 640k" in result.codec_args
    assert "-c:a:1 copy" in result.codec_args


# strip_audio_flags


@pytest.mark.parametrize(
    "input_args, expected",
    [
        ("-c:a copy -c:v libx265 -crf 28", "-c:v libx265 -crf 28"),
        ("-c:a:0 aac -c:a:1 copy -c:v libx265", "-c:v libx265"),
        ("-c:v libx265 -b:a 160k -crf 28", "-c:v libx265 -crf 28"),
        ("-c:v libx265 -ac 2 -crf 28", "-c:v libx265 -crf 28"),
        ("-c:v libx265 -ac:a:0 6 -crf 28", "-c:v libx265 -crf 28"),
        ("-c copy -c:v libx265", "-c:v libx265"),
        ("-c:s copy -c:v libx265 -c:a copy", "-c:s copy -c:v libx265"),
        ("-c:a copy", ""),
    ],
)
def test_strip_audio_flags(input_args, expected):
    assert strip_audio_flags(input_args) == expected


# extract_audio_streams


def test_extract_audio_streams():
    probe_data = {
        "streams": [
            {"index": 0, "codec_type": "video", "codec_name": "hevc"},
            {
                "index": 1,
                "codec_type": "audio",
                "codec_name": "aac",
                "channels": 2,
                "bit_rate": "128000",
                "tags": {"language": "eng"},
                "disposition": {"comment": 0},
            },
            {
                "index": 2,
                "codec_type": "audio",
                "codec_name": "dts",
                "channels": 6,
                "bit_rate": "768000",
                "tags": {"language": "jpn"},
                "disposition": {"comment": 0},
            },
            {"index": 3, "codec_type": "subtitle", "codec_name": "srt"},
        ]
    }
    result = extract_audio_streams(probe_data)
    assert len(result) == 2
    assert result[0]["codec_name"] == "aac"
    assert result[0]["language"] == "eng"
    assert result[0]["is_commentary"] is False
    assert result[1]["language"] == "jpn"


def test_extract_no_audio():
    probe_data = {
        "streams": [{"index": 0, "codec_type": "video", "codec_name": "hevc"}]
    }
    assert extract_audio_streams(probe_data) == []


def test_extract_missing_bitrate():
    probe_data = {
        "streams": [
            {"index": 1, "codec_type": "audio", "codec_name": "flac", "channels": 2}
        ]
    }
    result = extract_audio_streams(probe_data)
    assert result[0]["bit_rate"] is None
    assert result[0]["language"] == "und"


def test_extract_commentary_stream():
    probe_data = {
        "streams": [
            {
                "index": 1,
                "codec_type": "audio",
                "codec_name": "aac",
                "channels": 2,
                "bit_rate": "128000",
                "disposition": {"comment": 1},
            },
        ]
    }
    result = extract_audio_streams(probe_data)
    assert result[0]["is_commentary"] is True


# Config roundtrip


def test_config_roundtrip_with_audio():
    cfg = Config()
    cfg.presets["test"] = Preset(
        ffmpeg_args="-c:s copy -c:v libx265 -crf 28",
        audio=AudioConfig(
            stereo=AudioTrackConfig(codec="aac", bitrate="160k"),
            surround=AudioTrackConfig(codec="copy"),
            add_stereo_downmix="always",
            downmix_bitrate="160k",
            languages=["eng", "nor"],
            remove_commentary=True,
        ),
    )
    data = _config_to_dict(cfg)
    restored = _config_from_dict(data)
    p = restored.presets["test"]
    assert p.audio.stereo.codec == "aac"
    assert p.audio.stereo.bitrate == "160k"
    assert p.audio.surround.codec == "copy"
    assert p.audio.surround.bitrate is None
    assert p.audio.add_stereo_downmix == "always"
    assert p.audio.downmix_bitrate == "160k"
    assert p.audio.languages == ["eng", "nor"]
    assert p.audio.remove_commentary is True


def test_config_roundtrip_audio_copy():
    cfg = Config()
    cfg.presets["test"] = Preset(
        ffmpeg_args="-c:s copy -c:v libx265 -crf 28",
        audio=AudioConfig(
            stereo=AudioTrackConfig(codec="copy"),
            surround=AudioTrackConfig(codec="copy"),
        ),
    )
    data = _config_to_dict(cfg)
    restored = _config_from_dict(data)
    p = restored.presets["test"]
    assert p.audio.stereo.codec == "copy"
    assert p.audio.surround.codec == "copy"
    assert p.audio.languages is None
    assert p.audio.remove_commentary is False
    assert p.audio.add_stereo_downmix == "never"


def test_config_roundtrip_no_audio():
    cfg = Config()
    cfg.presets["test"] = Preset(ffmpeg_args="-c:a copy -c:s copy -c:v libx265 -crf 28")
    data = _config_to_dict(cfg)
    restored = _config_from_dict(data)
    assert restored.presets["test"].audio is None


def test_config_audio_yaml_omits_defaults():
    """YAML output omits fields at their defaults."""
    cfg = Config()
    cfg.presets["test"] = Preset(
        ffmpeg_args="-c:v libx265",
        audio=AudioConfig(
            stereo=AudioTrackConfig(codec="ac3"),
        ),
    )
    data = _config_to_dict(cfg)
    audio_dict = data["presets"]["test"]["audio"]
    assert "stereo" in audio_dict
    assert audio_dict["stereo"] == {"codec": "ac3"}
    assert "surround" not in audio_dict
    assert "languages" not in audio_dict
    assert "remove_commentary" not in audio_dict
    assert "add_stereo_downmix" not in audio_dict
    assert "downmix_bitrate" not in audio_dict


def test_config_roundtrip_downmix_if_no_stereo():
    cfg = Config()
    cfg.presets["test"] = Preset(
        ffmpeg_args="-c:v libx265",
        audio=AudioConfig(
            surround=AudioTrackConfig(codec="copy"),
            add_stereo_downmix="if_no_stereo",
            downmix_bitrate="160k",
        ),
    )
    data = _config_to_dict(cfg)
    assert data["presets"]["test"]["audio"]["add_stereo_downmix"] == "if_no_stereo"
    restored = _config_from_dict(data)
    assert restored.presets["test"].audio.add_stereo_downmix == "if_no_stereo"
