from __future__ import annotations

import re

from core.codecs import ENCODER_TO_CODEC

_AUDIO_CODEC_TO_TOKEN: dict[str, str] = {
    "aac": "AAC",
    "ac3": "AC3",
    "eac3": "EAC3",
    "libopus": "Opus",
    "opus": "Opus",
    "flac": "FLAC",
    "mp3": "MP3",
}

_AUDIO_CODEC_GROUPS: dict[str, list[str]] = {
    "aac": ["AAC", "aac"],
    "ac3": ["AC-3", "ac-3", "AC3", "ac3"],
    "eac3": [
        "E-AC-3",
        "e-ac-3",
        "E-AC3",
        "e-ac3",
        "E.AC3",
        "e.ac3",
        "EAC3",
        "eac3",
        "DDP",
        "ddp",
        "DD+",
        "dd+",
    ],
    "dts": ["DTS", "dts"],
    "dts_hd_ma": [
        "DTS-HD.MA",
        "dts-hd.ma",
        "DTS-HD MA",
        "dts-hd ma",
        "DTS.HD.MA",
        "dts.hd.ma",
        "DTS-HDMA",
        "dts-hdma",
        "DTS-MA",
        "dts-ma",
        "DTSMA",
        "dtsma",
    ],
    "dts_hd_hra": [
        "DTS-HD.HRA",
        "dts-hd.hra",
        "DTS-HD HRA",
        "dts-hd hra",
        "DTS-HDHRA",
        "dts-hdhra",
    ],
    "dts_es": ["DTS-ES", "dts-es", "DTSES", "dtses"],
    "dts_x": ["DTS-X", "dts-x", "DTS:X", "dts:x", "DTSX", "dtsx"],
    "truehd": [
        "TrueHD",
        "TRUEHD",
        "truehd",
        "True-HD",
        "true-hd",
        "True.HD",
        "true.hd",
    ],
    "flac": ["FLAC", "flac"],
    "opus": ["Opus", "OPUS", "opus"],
    "mp3": ["MP3", "mp3"],
}

_AUDIO_GROUP_TO_TARGET: dict[str, str] = {
    "aac": "aac",
    "ac3": "ac3",
    "eac3": "eac3",
    "dts": "dts",
    "dts_hd_ma": "dts",
    "dts_hd_hra": "dts",
    "dts_es": "dts",
    "dts_x": "dts",
    "truehd": "truehd",
    "flac": "flac",
    "opus": "opus",
    "mp3": "mp3",
}

_HEIGHT_TO_TOKEN = {
    360: "360p",
    480: "480p",
    540: "540p",
    576: "576p",
    720: "720p",
    1080: "1080p",
    2160: "2160p",
    4320: "4320p",
}

_CODEC_GROUPS: dict[str, list[str]] = {
    "h264": [
        "H.264",
        "h.264",
        "H 264",
        "h 264",
        "H264",
        "h264",
        "x264",
        "X264",
        "AVC",
        "avc",
    ],
    "hevc": [
        "H.265",
        "h.265",
        "H 265",
        "h 265",
        "H265",
        "h265",
        "x265",
        "X265",
        "HEVC",
        "hevc",
    ],
    "av1": ["AV1", "av1"],
    "vp9": ["VP9", "vp9"],
}

_STYLE_MAP: dict[str, dict[str, str]] = {
    "h264": {
        "h.264": "dotted",
        "h 264": "spaced",
        "h264": "short",
        "x264": "x_style",
        "avc": "formal",
    },
    "hevc": {
        "h.265": "dotted",
        "h 265": "spaced",
        "h265": "short",
        "x265": "x_style",
        "hevc": "formal",
    },
    "av1": {"av1": "formal"},
    "vp9": {"vp9": "formal"},
}

_STYLE_TOKENS: dict[str, dict[str, str]] = {
    "h264": {
        "dotted": "H.264",
        "spaced": "H 264",
        "short": "H264",
        "x_style": "x264",
        "formal": "AVC",
    },
    "hevc": {
        "dotted": "H.265",
        "spaced": "H 265",
        "short": "H265",
        "x_style": "x265",
        "formal": "HEVC",
    },
    "av1": {"formal": "AV1"},
    "vp9": {"formal": "VP9"},
}


def _build_codec_pattern() -> re.Pattern:
    all_tokens = []
    for tokens in _CODEC_GROUPS.values():
        all_tokens.extend(tokens)
    # Longest first so H.264 matches before H264.
    unique = sorted(set(all_tokens), key=lambda t: -len(t))
    escaped = [re.escape(t) for t in unique]
    return re.compile(r"\b(" + "|".join(escaped) + r")\b")


_CODEC_RE = _build_codec_pattern()


def _find_token_codec(token: str) -> str | None:
    lower = token.lower()
    for codec, tokens in _CODEC_GROUPS.items():
        if any(t.lower() == lower for t in tokens):
            return codec
    return None


def _pick_replacement(matched_token: str, target_codec: str) -> str:
    source_lower = matched_token.lower()
    source_codec = _find_token_codec(matched_token)
    if source_codec and source_lower in _STYLE_MAP.get(source_codec, {}):
        style = _STYLE_MAP[source_codec][source_lower]
    else:
        style = "formal"

    replacement = _STYLE_TOKENS.get(target_codec, {}).get(style, target_codec.upper())

    target_style_map = _STYLE_MAP.get(target_codec, {})
    repl_lower = replacement.lower()
    if repl_lower in target_style_map and target_style_map[repl_lower] == style:
        if matched_token == matched_token.upper():
            replacement = replacement.upper()
        elif matched_token == matched_token.lower():
            replacement = replacement.lower()

    return replacement


def _build_resolution_pattern() -> re.Pattern:
    res_tokens = [
        "360p",
        "480p",
        "480i",
        "540p",
        "576p",
        "576i",
        "720p",
        "1080p",
        "1080i",
        "2160p",
        "4320p",
        "4K",
        "4k",
        "8K",
        "8k",
        "UHD",
        "uhd",
        "FHD",
        "fhd",
    ]
    escaped = [re.escape(t) for t in sorted(res_tokens, key=lambda t: -len(t))]
    return re.compile(r"\b(" + "|".join(escaped) + r")\b")


_RES_RE = _build_resolution_pattern()

_WXHRES_RE = re.compile(r"\b(\d{3,5})x(\d{3,5})\b")

_CHANNEL_SUFFIX = r"([\.\- ]?\d\.\d)?"


def _build_audio_codec_pattern() -> re.Pattern:
    all_tokens = []
    for tokens in _AUDIO_CODEC_GROUPS.values():
        all_tokens.extend(tokens)
    unique = sorted(set(all_tokens), key=lambda t: -len(t))
    escaped = [re.escape(t) for t in unique]
    return re.compile(r"\b(" + "|".join(escaped) + r")" + _CHANNEL_SUFFIX + r"\b")


# Dolby Digital only matches with a channel suffix so DD-GROUP stays untouched
_DD_RE = re.compile(r"\b(DD|dd)([\.\- ]?\d\.\d)\b")
_AUDIO_RE = _build_audio_codec_pattern()
_ATMOS_RE = re.compile(r"[\.\- ](Atmos|ATMOS|atmos)\b")


def _find_audio_group(token: str) -> str | None:
    lower = token.lower()
    for group, tokens in _AUDIO_CODEC_GROUPS.items():
        if any(t.lower() == lower for t in tokens):
            return group
    return None


def _audio_case_match(source_token: str, canonical: str) -> str:
    if source_token == source_token.lower():
        return canonical.lower()
    if source_token == source_token.upper():
        return canonical.upper()
    return canonical


def _join_codec_channels(codec: str, ch_suffix: str) -> str:
    # EAC3 + 2.0 would run together as EAC32.0
    if ch_suffix and codec[-1].isdigit() and ch_suffix[0].isdigit():
        return codec + "." + ch_suffix
    return codec + ch_suffix


_RES_TOKEN_TO_HEIGHT = {
    "360p": 360,
    "480p": 480,
    "480i": 480,
    "540p": 540,
    "576p": 576,
    "576i": 576,
    "720p": 720,
    "1080p": 1080,
    "1080i": 1080,
    "FHD": 1080,
    "fhd": 1080,
    "2160p": 2160,
    "4K": 2160,
    "4k": 2160,
    "UHD": 2160,
    "uhd": 2160,
    "4320p": 4320,
    "8K": 4320,
    "8k": 4320,
}


def rename_tokens(
    filename: str,
    encoder: str,
    source_height: int | None = None,
    target_height: int | None = None,
    target_audio_codec: str | None = None,
) -> str:
    target_codec = ENCODER_TO_CODEC.get(encoder)
    if not target_codec:
        return filename

    dot_idx = filename.rfind(".")
    if dot_idx > 0:
        stem = filename[:dot_idx]
        ext = filename[dot_idx:]
    else:
        stem = filename
        ext = ""

    def replace_codec(m: re.Match) -> str:
        token = m.group(1)
        token_codec = _find_token_codec(token)
        if token_codec == target_codec:
            return token
        return _pick_replacement(token, target_codec)

    stem = _CODEC_RE.sub(replace_codec, stem)

    new_res_token = None
    if (
        target_height is not None
        and source_height is not None
        and target_height != source_height
    ):
        new_res_token = _HEIGHT_TO_TOKEN.get(target_height)

    def replace_res(m: re.Match) -> str:
        token = m.group(1)
        old_height = _RES_TOKEN_TO_HEIGHT.get(token)
        if new_res_token and old_height == source_height:
            if token == token.lower():
                return new_res_token.lower()
            return new_res_token
        # Output is always progressive, 1080i becomes 1080p even without a downscale
        if token.endswith("i"):
            return token[:-1] + "p"
        return token

    stem = _RES_RE.sub(replace_res, stem)

    def replace_wxh(m: re.Match) -> str:
        h = int(m.group(2))
        if new_res_token and h == source_height:
            return new_res_token
        return m.group(0)

    stem = _WXHRES_RE.sub(replace_wxh, stem)

    if target_audio_codec:
        canonical = _AUDIO_CODEC_TO_TOKEN.get(target_audio_codec)
        if canonical:

            def replace_dd(m: re.Match) -> str:
                # Dolby Digital is AC3
                if target_audio_codec == "ac3":
                    return m.group(0)
                dd_token = m.group(1)
                ch_suffix = m.group(2)
                return _join_codec_channels(
                    _audio_case_match(dd_token, canonical), ch_suffix
                )

            stem = _DD_RE.sub(replace_dd, stem)

            def replace_audio(m: re.Match) -> str:
                token = m.group(1)
                ch_suffix = m.group(2) or ""
                group = _find_audio_group(token)
                if not group:
                    return m.group(0)
                target_family = _AUDIO_CODEC_TO_TOKEN.get(
                    target_audio_codec, ""
                ).lower()
                if _AUDIO_GROUP_TO_TARGET.get(group) == target_family:
                    return m.group(0)
                return _join_codec_channels(
                    _audio_case_match(token, canonical), ch_suffix
                )

            stem = _AUDIO_RE.sub(replace_audio, stem)

            # Atmos is a metadata layer on TrueHD/EAC3, which is always lost when re-encoding
            stem = _ATMOS_RE.sub("", stem)

    return stem + ext
