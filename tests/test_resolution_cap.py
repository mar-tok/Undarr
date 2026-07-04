from core.ffmpeg import build_scale_filter


def test_above_cap():
    result = build_scale_filter(1080, 2160)
    assert result == "scale=-2:1080"


def test_at_cap():
    result = build_scale_filter(1080, 1080)
    assert result is None


def test_below_cap():
    result = build_scale_filter(1080, 720)
    assert result is None


def test_cap_720():
    result = build_scale_filter(720, 1080)
    assert result == "scale=-2:720"


def test_cap_1440():
    result = build_scale_filter(1440, 2160)
    assert result == "scale=-2:1440"
