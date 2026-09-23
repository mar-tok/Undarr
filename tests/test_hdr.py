from pathlib import Path

import pytest

from core.ffprobe import classify_hdr, extract_media_info, probe_file
from core.skip_rules import should_skip
from core.yaml_store import SkipRule, SkipCondition


def _rule(*conds):
    return SkipRule(
        conditions=[SkipCondition(field=f, operator=o, value=v) for f, o, v in conds]
    )


# classify_hdr


@pytest.mark.parametrize(
    "transfer,side_data,expected",
    [
        ("smpte2084", [], "hdr10"),
        ("smpte2084", [{"side_data_type": "Mastering display metadata"}], "hdr10"),
        (
            "smpte2084",
            [{"side_data_type": "DOVI configuration record"}],
            "dolby_vision",
        ),
        (
            "smpte2084",
            [{"side_data_type": "HDR Dynamic Metadata SMPTE2094-40 (HDR10+)"}],
            "hdr10+",
        ),
        ("arib-std-b67", [], "hlg"),
        ("bt709", [], ""),
        ("", [], ""),
        ("unknown", [], ""),
    ],
)
def test_classify_hdr(transfer, side_data, expected):
    stream = {"color_transfer": transfer, "side_data_list": side_data}
    assert classify_hdr(stream) == expected


def test_classify_hdr_no_side_data_key():
    stream = {"color_transfer": "smpte2084"}
    assert classify_hdr(stream) == "hdr10"


def test_classify_hdr_dv_takes_priority_over_hdr10plus():
    stream = {
        "color_transfer": "smpte2084",
        "side_data_list": [
            {"side_data_type": "DOVI configuration record"},
            {"side_data_type": "HDR Dynamic Metadata SMPTE2094-40 (HDR10+)"},
        ],
    }
    assert classify_hdr(stream) == "dolby_vision"


@pytest.mark.parametrize("transfer", ["arib-std-b67", "bt709", ""])
def test_classify_hdr_dv_without_pq_base_layer(transfer):
    stream = {
        "color_transfer": transfer,
        "side_data_list": [{"side_data_type": "DOVI configuration record"}],
    }
    assert classify_hdr(stream) == "dolby_vision"


def test_classify_hdr_empty_stream():
    assert classify_hdr({}) == ""


# extract_media_info with HDR


def test_extract_media_info_hdr10():
    probe = {
        "streams": [
            {
                "codec_type": "video",
                "codec_name": "hevc",
                "width": 3840,
                "height": 2160,
                "color_transfer": "smpte2084",
            }
        ],
        "format": {},
    }
    info = extract_media_info(probe)
    assert info["hdr_type"] == "hdr10"


def test_extract_media_info_sdr():
    probe = {
        "streams": [
            {
                "codec_type": "video",
                "codec_name": "h264",
                "width": 1920,
                "height": 1080,
            }
        ],
        "format": {},
    }
    info = extract_media_info(probe)
    assert info["hdr_type"] == ""


def test_extract_media_info_hlg():
    probe = {
        "streams": [
            {
                "codec_type": "video",
                "codec_name": "hevc",
                "width": 3840,
                "height": 2160,
                "color_transfer": "arib-std-b67",
            }
        ],
        "format": {},
    }
    info = extract_media_info(probe)
    assert info["hdr_type"] == "hlg"


def test_extract_media_info_skips_attached_pic():
    probe = {
        "streams": [
            {
                "codec_type": "video",
                "codec_name": "mjpeg",
                "width": 600,
                "height": 600,
                "disposition": {"attached_pic": 1},
                "color_transfer": "smpte2084",
            },
            {
                "codec_type": "video",
                "codec_name": "hevc",
                "width": 3840,
                "height": 2160,
            },
        ],
        "format": {},
    }
    info = extract_media_info(probe)
    assert info["hdr_type"] == ""
    assert info["video_codec"] == "hevc"


# probe_file on real HDR clips

FIXTURES = Path(__file__).parent / "fixtures" / "video_profiles"


@pytest.mark.parametrize(
    "name,expected",
    [
        ("hdr10.mkv", "hdr10"),
        ("hdr10plus.mkv", "hdr10+"),
        ("1080p_h265_10bit.mkv", ""),
    ],
)
async def test_probe_file_hdr_type(name, expected):
    info = extract_media_info(await probe_file(str(FIXTURES / name)))
    assert info["hdr_type"] == expected


# skip rules with hdr_type


def test_skip_all_hdr():
    rules = [_rule(("hdr_type", "not_equals", ""))]
    assert should_skip({"hdr_type": "hdr10", "video_codec": "hevc"}, rules) is rules[0]
    assert should_skip({"hdr_type": "", "video_codec": "hevc"}, rules) is None


def test_skip_dolby_vision_only():
    rules = [_rule(("hdr_type", "equals", "dolby_vision"))]
    assert should_skip({"hdr_type": "dolby_vision"}, rules) is rules[0]
    assert should_skip({"hdr_type": "hdr10"}, rules) is None
    assert should_skip({"hdr_type": ""}, rules) is None


def test_skip_hdr_compound_rule():
    rules = [_rule(("hdr_type", "not_equals", ""), ("video_codec", "equals", "hevc"))]
    assert should_skip({"hdr_type": "hdr10", "video_codec": "hevc"}, rules) is rules[0]
    assert should_skip({"hdr_type": "hdr10", "video_codec": "h264"}, rules) is None
    assert should_skip({"hdr_type": "", "video_codec": "hevc"}, rules) is None
