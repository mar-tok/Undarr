import pytest

from core.rename import rename_tokens


@pytest.mark.parametrize(
    "filename, encoder, expected",
    [
        (
            "Title.2020.1080p.BluRay.x264-GROUP.mkv",
            "libx265",
            "Title.2020.1080p.BluRay.x265-GROUP.mkv",
        ),
        (
            "Title.2020.1080p.BluRay.x264-GROUP.mkv",
            "hevc_nvenc",
            "Title.2020.1080p.BluRay.x265-GROUP.mkv",
        ),
        (
            "Title.2020.1080p.BluRay.x264-GROUP.mkv",
            "hevc_qsv",
            "Title.2020.1080p.BluRay.x265-GROUP.mkv",
        ),
        # Style preservation for dotted, short, lowercase, uppercase, spaced
        ("Title [H.264].mkv", "libx265", "Title [H.265].mkv"),
        ("Title.H264.mkv", "libx265", "Title.H265.mkv"),
        ("Title.h264.mkv", "libx265", "Title.h265.mkv"),
        ("Title.X264.mkv", "libx265", "Title.X265.mkv"),
        ("Title 1080p H 264-GROUP.mkv", "libx265", "Title 1080p H 265-GROUP.mkv"),
        # Cross codec
        ("Title.HEVC.mkv", "libsvtav1", "Title.AV1.mkv"),
        ("Title.hevc.mkv", "libsvtav1", "Title.av1.mkv"),
        ("Title.1080p.x265-GROUP.mkv", "libsvtav1", "Title.1080p.AV1-GROUP.mkv"),
        ("Title.AV1.mkv", "libx265", "Title.HEVC.mkv"),
        ("Title.H.264.mkv", "libsvtav1", "Title.AV1.mkv"),
        ("Title.x264.mkv", "av1_qsv", "Title.AV1.mkv"),
        # AVC is the formal name for H.264
        ("Title.AVC.mkv", "libx265", "Title.HEVC.mkv"),
        ("Title.VP9.mkv", "libsvtav1", "Title.AV1.mkv"),
        ("Title.x264.mkv", "libvpx-vp9", "Title.VP9.mkv"),
        ("Title.vp9.mkv", "libx265", "Title.hevc.mkv"),
        # Reverse direction
        ("Title.x265.mkv", "libx264", "Title.x264.mkv"),
        ("Title.HEVC.mkv", "libx264", "Title.AVC.mkv"),
        ("Title.AV1.mkv", "libx264", "Title.AVC.mkv"),
    ],
)
def test_codec_replacement(filename, encoder, expected):
    assert rename_tokens(filename, encoder) == expected


@pytest.mark.parametrize(
    "filename, encoder, expected",
    [
        ("Title.x265.mkv", "libx265", "Title.x265.mkv"),
        ("Title.HEVC.mkv", "hevc_nvenc", "Title.HEVC.mkv"),
        ("Title.2020.1080p.BluRay.mkv", "libx265", "Title.2020.1080p.BluRay.mkv"),
        # Without a proper extension, last segment treated as extension
        ("Title.x264", "libx265", "Title.x264"),
        ("Title.x264.mkv", "some_unknown_encoder", "Title.x264.mkv"),
    ],
)
def test_codec_noop(filename, encoder, expected):
    assert rename_tokens(filename, encoder) == expected


@pytest.mark.parametrize(
    "filename, encoder, expected",
    [
        # Episode numbers must not match as codec tokens
        ("Show.S01E264.mkv", "libx265", "Show.S01E264.mkv"),
        ("Show.S01E265.mkv", "libx265", "Show.S01E265.mkv"),
        ("Show.S01E264.x264.mkv", "libx265", "Show.S01E264.x265.mkv"),
        ("Title.2640.2020.mkv", "libx265", "Title.2640.2020.mkv"),
        ("Preh264title.mkv", "libx265", "Preh264title.mkv"),
        # Boundary positions. Start, before extension, brackets, parens
        ("x264.Title.mkv", "libx265", "x265.Title.mkv"),
        ("Title.x264.mkv", "libx265", "Title.x265.mkv"),
        ("Title [x264].mkv", "libx265", "Title [x265].mkv"),
        ("Title (H.264).mkv", "libx265", "Title (H.265).mkv"),
    ],
)
def test_word_boundary(filename, encoder, expected):
    assert rename_tokens(filename, encoder) == expected


@pytest.mark.parametrize(
    "filename, encoder, expected",
    [
        ("Title.x.264.mkv", "libx265", "Title.x.265.mkv"),
        ("Title.X.264.mkv", "libx265", "Title.X.265.mkv"),
        ("Title.x-264.mkv", "libx265", "Title.x-265.mkv"),
        ("Title_x_264_GROUP.mkv", "libx265", "Title_x_265_GROUP.mkv"),
        ("Title.H-264.mkv", "libx265", "Title.H-265.mkv"),
        ("Title.H_264.mkv", "libx265", "Title.H_265.mkv"),
        # Cross codec with separator for canonical forms
        ("Title.x.264.mkv", "libsvtav1", "Title.AV1.mkv"),
        ("Title.x.265.mkv", "libx265", "Title.x.265.mkv"),
        ("Title.avc.mkv", "libx265", "Title.hevc.mkv"),
        (
            "Video.Title.2024.1080p.BluRay.x.264-GROUP.mkv",
            "libx265",
            "Video.Title.2024.1080p.BluRay.x.265-GROUP.mkv",
        ),
    ],
)
def test_separator_variants(filename, encoder, expected):
    assert rename_tokens(filename, encoder) == expected


# Resolution tokens are only replaced when the output height differs
@pytest.mark.parametrize(
    "filename, encoder, src_h, tgt_h, expected",
    [
        ("Title.2160p.x264.mkv", "libx265", 2160, 1080, "Title.1080p.x265.mkv"),
        ("Title.4K.HEVC.mkv", "libx265", 2160, 1080, "Title.1080p.HEVC.mkv"),
        ("Title.4k.HEVC.mkv", "libx265", 2160, 1080, "Title.1080p.HEVC.mkv"),
        ("Title.1080p.x264.mkv", "libx265", 1080, 720, "Title.720p.x265.mkv"),
        ("Title.1080p.x264.mkv", "libx265", 1080, 1080, "Title.1080p.x265.mkv"),
        ("Title.2160p.x264.mkv", "libx265", 2160, None, "Title.2160p.x265.mkv"),
        ("Title.2160p.x264.mkv", "libx265", None, 1080, "Title.2160p.x265.mkv"),
        # When token doesn't match source the height, it's left alone
        ("Title.720p.x264.mkv", "libx265", 2160, 1080, "Title.720p.x265.mkv"),
        ("Title.2160p.BluRay.mkv", "libx265", 2160, 1080, "Title.1080p.BluRay.mkv"),
        ("Title.2160p.x265.mkv", "libx265", 2160, 1080, "Title.1080p.x265.mkv"),
        ("Title.4320p.x264.mkv", "libx265", 4320, 2160, "Title.2160p.x265.mkv"),
        ("Title.8K.HEVC.mkv", "libx265", 4320, 2160, "Title.2160p.HEVC.mkv"),
    ],
)
def test_resolution_replacement(filename, encoder, src_h, tgt_h, expected):
    assert (
        rename_tokens(filename, encoder, source_height=src_h, target_height=tgt_h)
        == expected
    )


# 1080i is interlaced, a broadcast TV format of half-frames.
# Encoders output whole frames, so the token changes to 1080p even at the same height.
@pytest.mark.parametrize(
    "filename, encoder, src_h, tgt_h, expected",
    [
        ("Title.1080i.x264.mkv", "libx265", None, None, "Title.1080p.x265.mkv"),
        ("Title.480i.x264.mkv", "libx265", None, None, "Title.480p.x265.mkv"),
        ("Title.576i.x264.mkv", "libx265", None, None, "Title.576p.x265.mkv"),
        ("Title.1080i.HEVC.mkv", "libx265", None, None, "Title.1080p.HEVC.mkv"),
        # Resolution cap takes precedence
        ("Title.1080i.x264.mkv", "libx265", 1080, 720, "Title.720p.x265.mkv"),
        # Progressive tokens not touched
        ("Title.1080p.x264.mkv", "libx265", None, None, "Title.1080p.x265.mkv"),
        (
            "Show.S01E01.1080i.HDTV.H.264-GROUP.mkv",
            "libx265",
            None,
            None,
            "Show.S01E01.1080p.HDTV.H.265-GROUP.mkv",
        ),
    ],
)
def test_interlaced(filename, encoder, src_h, tgt_h, expected):
    assert (
        rename_tokens(filename, encoder, source_height=src_h, target_height=tgt_h)
        == expected
    )


# UHD, FHD, and other non-numeric resolution tokens
@pytest.mark.parametrize(
    "filename, encoder, src_h, tgt_h, expected",
    [
        (
            "Title.UHD.BluRay.x264.mkv",
            "libx265",
            2160,
            1080,
            "Title.1080p.BluRay.x265.mkv",
        ),
        (
            "Title.uhd.BluRay.x264.mkv",
            "libx265",
            2160,
            1080,
            "Title.1080p.BluRay.x265.mkv",
        ),
        ("Title.UHD.x264.mkv", "libx265", None, None, "Title.UHD.x265.mkv"),
        ("Title.FHD.x264.mkv", "libx265", 1080, 720, "Title.720p.x265.mkv"),
        ("Title.fhd.x264.mkv", "libx265", 1080, 720, "Title.720p.x265.mkv"),
        ("Title.540p.x264.mkv", "libx265", 540, 480, "Title.480p.x265.mkv"),
        ("Title.360p.x264.mkv", "libx265", None, None, "Title.360p.x265.mkv"),
    ],
)
def test_resolution_labels(filename, encoder, src_h, tgt_h, expected):
    assert (
        rename_tokens(filename, encoder, source_height=src_h, target_height=tgt_h)
        == expected
    )


# WIDTHxHEIGHT format
@pytest.mark.parametrize(
    "filename, encoder, src_h, tgt_h, expected",
    [
        # Standard resolutions
        ("Title (1920x1080 x264).mkv", "libx265", 1080, 720, "Title (720p x265).mkv"),
        ("Title (3840x2160 x264).mkv", "libx265", 2160, 1080, "Title (1080p x265).mkv"),
        ("Title (1280x720 x264).mkv", "libx265", 720, 480, "Title (480p x265).mkv"),
        # Odd resolutions, like crops or non-standard aspect ratios
        (
            "[SubGroup] Title (BDRip 1920x1032 x264 FLAC).mkv",
            "libx265",
            1032,
            720,
            "[SubGroup] Title (BDRip 720p x265 FLAC).mkv",
        ),
        ("Title (1920x800 x264).mkv", "libx265", 800, 720, "Title (720p x265).mkv"),
        (
            "Title (1920x1080 x264).mkv",
            "libx265",
            1080,
            1080,
            "Title (1920x1080 x265).mkv",
        ),
        (
            "Title (1920x1080 x264).mkv",
            "libx265",
            None,
            None,
            "Title (1920x1080 x265).mkv",
        ),
        (
            "[SubGroup] Title (BDRip 1920x1032 x264 FLAC).mkv",
            "libx265",
            None,
            None,
            "[SubGroup] Title (BDRip 1920x1032 x265 FLAC).mkv",
        ),
        (
            "Title (1920x1080 x264).mkv",
            "libx265",
            2160,
            1080,
            "Title (1920x1080 x265).mkv",
        ),
        (
            "[SubGroup] Video.Title.1920x1080.x264.mkv",
            "libx265",
            1080,
            720,
            "[SubGroup] Video.Title.720p.x265.mkv",
        ),
    ],
)
def test_resolution_wxh(filename, encoder, src_h, tgt_h, expected):
    assert (
        rename_tokens(filename, encoder, source_height=src_h, target_height=tgt_h)
        == expected
    )


@pytest.mark.parametrize(
    "filename, encoder, src_h, tgt_h, expected",
    [
        (
            "The.Video.Title.2020.2160p.BluRay.x264-GROUP.mkv",
            "libx265",
            2160,
            1080,
            "The.Video.Title.2020.1080p.BluRay.x265-GROUP.mkv",
        ),
        (
            "The Series Title! (2010) - S01E01 - Episode Title [WEBDL-1080p][DTS 5.1][x264]-RlsGrp.mkv",
            "libx265",
            None,
            None,
            "The Series Title! (2010) - S01E01 - Episode Title [WEBDL-1080p][DTS 5.1][x265]-RlsGrp.mkv",
        ),
        (
            "The Video Title (2010) [Bluray-2160p][DV HDR10][DTS 5.1][H.264]-RlsGrp.mkv",
            "libsvtav1",
            2160,
            1080,
            "The Video Title (2010) [Bluray-1080p][DV HDR10][DTS 5.1][AV1]-RlsGrp.mkv",
        ),
        (
            "Video Title [1080p] [H.264].mkv",
            "libx265",
            None,
            None,
            "Video Title [1080p] [H.265].mkv",
        ),
        (
            "Video_Title_2020_1080p_x264.mkv",
            "hevc_qsv",
            None,
            None,
            "Video_Title_2020_1080p_x265.mkv",
        ),
        (
            "Video-Title-2020-1080p-x264.mkv",
            "libx265",
            None,
            None,
            "Video-Title-2020-1080p-x265.mkv",
        ),
        (
            "Video Title 2020 1080p x264.mkv",
            "libx265",
            None,
            None,
            "Video Title 2020 1080p x265.mkv",
        ),
        (
            "Show S01E01 Episode Title 1080p WEB-DL DDP5 1 H 264-GROUP.mkv",
            "libx265",
            None,
            None,
            "Show S01E01 Episode Title 1080p WEB-DL DDP5 1 H 265-GROUP.mkv",
        ),
        (
            "Show.S08E05.Episode.Title.1080p.WEB-DL.JPN.AAC2.0.H.264.MSubs-GROUP.mkv",
            "libx265",
            None,
            None,
            "Show.S08E05.Episode.Title.1080p.WEB-DL.JPN.AAC2.0.H.265.MSubs-GROUP.mkv",
        ),
        (
            "[SubGroup] Show Title 3rd Season - 05 [1080p WEB-DL AVC AAC][MultiSub][28C9EA79].mkv",
            "libx265",
            None,
            None,
            "[SubGroup] Show Title 3rd Season - 05 [1080p WEB-DL HEVC AAC][MultiSub][28C9EA79].mkv",
        ),
    ],
)
def test_combined(filename, encoder, src_h, tgt_h, expected):
    assert (
        rename_tokens(filename, encoder, source_height=src_h, target_height=tgt_h)
        == expected
    )


@pytest.mark.parametrize(
    "filename, encoder, src_h, tgt_h, expected",
    [
        ("", "libx265", None, None, ""),
        (".mkv", "libx265", None, None, ".mkv"),
        ("Title.x264.H.264.mkv", "libx265", None, None, "Title.x265.H.265.mkv"),
        ("Title.h264", "libx265", None, None, "Title.h264"),
        ("Title.x264.mp4", "libx265", None, None, "Title.x265.mp4"),
        ("Títle.Nàme.x264.mkv", "libx265", None, None, "Títle.Nàme.x265.mkv"),
        ("A" * 200 + ".x264.mkv", "libx265", None, None, "A" * 200 + ".x265.mkv"),
        # Sonarr bracket resolution
        (
            "Title [WEBDL-2160p] [x264].mkv",
            "libx265",
            2160,
            1080,
            "Title [WEBDL-1080p] [x265].mkv",
        ),
    ],
)
def test_edge_cases(filename, encoder, src_h, tgt_h, expected):
    assert (
        rename_tokens(filename, encoder, source_height=src_h, target_height=tgt_h)
        == expected
    )


# Audio codec replacement


@pytest.mark.parametrize(
    "filename, audio, expected",
    [
        ("Title.DTS.1080p.x264.mkv", "aac", "Title.AAC.1080p.x265.mkv"),
        ("Title.AC3.1080p.mkv", "aac", "Title.AAC.1080p.mkv"),
        ("Title.TrueHD.1080p.mkv", "eac3", "Title.EAC3.1080p.mkv"),
        ("Title.FLAC.1080p.mkv", "aac", "Title.AAC.1080p.mkv"),
        ("Title.MP3.mkv", "aac", "Title.AAC.mkv"),
        ("Title.Opus.mkv", "aac", "Title.AAC.mkv"),
        ("Title.EAC3.mkv", "aac", "Title.AAC.mkv"),
        ("Title.AC3.mkv", "eac3", "Title.EAC3.mkv"),
    ],
)
def test_audio_codec_replacement(filename, audio, expected):
    assert rename_tokens(filename, "libx265", target_audio_codec=audio) == expected


@pytest.mark.parametrize(
    "filename, audio, expected",
    [
        # No audio token in filename
        ("Title.1080p.x264.mkv", "aac", "Title.1080p.x265.mkv"),
        # Target matches source
        ("Title.AAC.1080p.mkv", "aac", "Title.AAC.1080p.mkv"),
        ("Title.EAC3.mkv", "eac3", "Title.EAC3.mkv"),
        # No target audio codec
        ("Title.DTS.1080p.mkv", None, "Title.DTS.1080p.mkv"),
    ],
)
def test_audio_codec_noop(filename, audio, expected):
    assert rename_tokens(filename, "libx265", target_audio_codec=audio) == expected


# DD is Dolby Digital, the filename form of AC3. Too short to match safely on its own,
# it only counts with a channel layout attached like DD5.1.
@pytest.mark.parametrize(
    "filename, audio, expected",
    [
        ("Title.DD5.1.mkv", "aac", "Title.AAC5.1.mkv"),
        ("Title.DD.5.1.mkv", "aac", "Title.AAC.5.1.mkv"),
        ("Title DD 2.0.mkv", "aac", "Title AAC 2.0.mkv"),
        ("Title.DD7.1.mkv", "eac3", "Title.EAC3.7.1.mkv"),
        # Same codec as the ac3 target, left alone
        ("Title.DD5.1.mkv", "ac3", "Title.DD5.1.mkv"),
    ],
)
def test_audio_dd_compound(filename, audio, expected):
    assert rename_tokens(filename, "libx265", target_audio_codec=audio) == expected


# DDP and DD+ are Dolby Digital Plus, the filename forms of EAC3
@pytest.mark.parametrize(
    "filename, audio, expected",
    [
        ("Title.DDP5.1.mkv", "aac", "Title.AAC5.1.mkv"),
        ("Title.DDP.5.1.mkv", "aac", "Title.AAC.5.1.mkv"),
        ("Title.DDP.Atmos.mkv", "aac", "Title.AAC.mkv"),
        ("Title.DD+.5.1.mkv", "aac", "Title.AAC.5.1.mkv"),
        ("Title.DD+.mkv", "aac", "Title.AAC.mkv"),
    ],
)
def test_audio_ddp_standalone(filename, audio, expected):
    assert rename_tokens(filename, "libx265", target_audio_codec=audio) == expected


# Lowercase tokens stay lowercase, uppercase stay uppercase, and mixed case like TrueHD gets the canonical form
@pytest.mark.parametrize(
    "filename, audio, expected",
    [
        ("Title.dts.mkv", "aac", "Title.aac.mkv"),
        ("Title.DTS.mkv", "aac", "Title.AAC.mkv"),
        ("Title.TRUEHD.mkv", "aac", "Title.AAC.mkv"),
        ("Title.truehd.mkv", "aac", "Title.aac.mkv"),
        ("Title.flac.mkv", "aac", "Title.aac.mkv"),
        ("Title.TrueHD.mkv", "aac", "Title.AAC.mkv"),
    ],
)
def test_audio_case_preservation(filename, audio, expected):
    assert rename_tokens(filename, "libx265", target_audio_codec=audio) == expected


@pytest.mark.parametrize(
    "filename, audio, expected",
    [
        ("Title.AC3.5.1.mkv", "aac", "Title.AAC.5.1.mkv"),
        ("Title.DTS-HD.MA.7.1.mkv", "aac", "Title.AAC.7.1.mkv"),
        ("Title.DTS5.1.mkv", "aac", "Title.AAC5.1.mkv"),
        ("Title.TrueHD.7.1.mkv", "aac", "Title.AAC.7.1.mkv"),
        ("Title.FLAC.2.0.mkv", "aac", "Title.AAC.2.0.mkv"),
    ],
)
def test_audio_channel_suffix(filename, audio, expected):
    assert rename_tokens(filename, "libx265", target_audio_codec=audio) == expected


@pytest.mark.parametrize(
    "filename, audio, expected",
    [
        ("Title.DTS-HD.MA.mkv", "aac", "Title.AAC.mkv"),
        ("Title.DTS-HD MA.mkv", "aac", "Title.AAC.mkv"),
        ("Title.DTSMA.mkv", "aac", "Title.AAC.mkv"),
        ("Title.DTS-HDMA.mkv", "aac", "Title.AAC.mkv"),
        ("Title.DTS-MA.mkv", "aac", "Title.AAC.mkv"),
        ("Title.DTS.HD.MA.mkv", "aac", "Title.AAC.mkv"),
        ("Title.DTS-ES.mkv", "aac", "Title.AAC.mkv"),
        ("Title.DTS-X.mkv", "aac", "Title.AAC.mkv"),
        ("Title.DTS-HD.HRA.mkv", "aac", "Title.AAC.mkv"),
    ],
)
def test_audio_dts_family(filename, audio, expected):
    assert rename_tokens(filename, "libx265", target_audio_codec=audio) == expected


@pytest.mark.parametrize(
    "filename, audio, expected",
    [
        # EAC3 should not be partially matched as AC3
        ("Title.EAC3.mkv", "aac", "Title.AAC.mkv"),
        ("Title.E-AC3.mkv", "aac", "Title.AAC.mkv"),
        ("Title.E-AC-3.mkv", "aac", "Title.AAC.mkv"),
        # AC3 should match independently
        ("Title.AC3.mkv", "eac3", "Title.EAC3.mkv"),
    ],
)
def test_audio_eac3_ac3_no_collision(filename, audio, expected):
    assert rename_tokens(filename, "libx265", target_audio_codec=audio) == expected


# Atmos is a Dolby metadata layer that re-encoding always strips
@pytest.mark.parametrize(
    "filename, audio, expected",
    [
        ("Title.TrueHD.Atmos.mkv", "aac", "Title.AAC.mkv"),
        ("Title.TrueHD.Atmos.7.1.mkv", "aac", "Title.AAC.7.1.mkv"),
        ("Title.DDP.Atmos.5.1.mkv", "aac", "Title.AAC.5.1.mkv"),
        ("Title.EAC3.ATMOS.mkv", "aac", "Title.AAC.mkv"),
        # Removed even when the codec family stays the same
        ("Title.EAC3.Atmos.mkv", "eac3", "Title.EAC3.mkv"),
    ],
)
def test_audio_atmos_removal(filename, audio, expected):
    assert rename_tokens(filename, "libx265", target_audio_codec=audio) == expected


@pytest.mark.parametrize(
    "filename, audio, expected",
    [
        # DD inside words should not match
        ("Title.ADDED.mkv", "aac", "Title.ADDED.mkv"),
        ("Title.Pudding.mkv", "aac", "Title.Pudding.mkv"),
        # DTS before a release group still matches, the hyphen counts as a boundary
        ("Title.DTS-GROUP.mkv", "aac", "Title.AAC-GROUP.mkv"),
    ],
)
def test_audio_boundary_safety(filename, audio, expected):
    assert rename_tokens(filename, "libx265", target_audio_codec=audio) == expected


# Underscores as separators
@pytest.mark.parametrize(
    "filename, audio, expected",
    [
        ("Title_2020_DTS_5.1_1080p.mkv", "aac", "Title_2020_AAC_5.1_1080p.mkv"),
        ("Show_S01E01_DD_5.1_720p.mkv", "aac", "Show_S01E01_AAC_5.1_720p.mkv"),
        ("Title_TrueHD_Atmos_7.1.mkv", "aac", "Title_AAC_7.1.mkv"),
        ("Title_2020_DDP_Atmos.mkv", "aac", "Title_2020_AAC.mkv"),
    ],
)
def test_audio_underscore_separators(filename, audio, expected):
    assert rename_tokens(filename, "libx265", target_audio_codec=audio) == expected


@pytest.mark.parametrize(
    "filename, audio, expected",
    [
        ("Title.1080p.x264.DTS.mkv", "aac", "Title.1080p.x265.AAC.mkv"),
        ("Title.H.264.AC3.5.1.mkv", "aac", "Title.H.265.AAC.5.1.mkv"),
        ("Title.x264.DTS-HD.MA.7.1.mkv", "eac3", "Title.x265.EAC3.7.1.mkv"),
    ],
)
def test_audio_combined_video_and_audio(filename, audio, expected):
    assert rename_tokens(filename, "libx265", target_audio_codec=audio) == expected


@pytest.mark.parametrize(
    "filename, audio, expected",
    [
        (
            "The.Video.Title.2020.1080p.BluRay.DTS-HD.MA.5.1.x264-GROUP.mkv",
            "aac",
            "The.Video.Title.2020.1080p.BluRay.AAC.5.1.x265-GROUP.mkv",
        ),
        (
            "Video.Title.2024.2160p.UHD.BluRay.TrueHD.Atmos.7.1.x265-GROUP.mkv",
            "aac",
            "Video.Title.2024.2160p.UHD.BluRay.AAC.7.1.x265-GROUP.mkv",
        ),
        (
            "Show.S01E01.1080p.WEB-DL.DDP5.1.H.264-GROUP.mkv",
            "aac",
            "Show.S01E01.1080p.WEB-DL.AAC5.1.H.265-GROUP.mkv",
        ),
        (
            "The Series Title! (2010) - S01E01 - Episode Title [WEBDL-1080p][DTS 5.1][x264]-RlsGrp.mkv",
            "aac",
            "The Series Title! (2010) - S01E01 - Episode Title [WEBDL-1080p][AAC 5.1][x265]-RlsGrp.mkv",
        ),
        (
            "[SubGroup] Show Title - 05 [1080p WEB-DL AVC AAC][MultiSub].mkv",
            "opus",
            "[SubGroup] Show Title - 05 [1080p WEB-DL HEVC OPUS][MultiSub].mkv",
        ),
    ],
)
def test_audio_real_world(filename, audio, expected):
    assert rename_tokens(filename, "libx265", target_audio_codec=audio) == expected
