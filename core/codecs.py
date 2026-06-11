ENCODER_TO_CODEC: dict[str, str] = {
    "libx264": "h264", "h264_nvenc": "h264", "h264_qsv": "h264",
    "h264_amf": "h264", "h264_vaapi": "h264", "h264_videotoolbox": "h264",
    "libx265": "hevc", "hevc_nvenc": "hevc", "hevc_qsv": "hevc",
    "hevc_amf": "hevc", "hevc_vaapi": "hevc", "hevc_videotoolbox": "hevc",
    "libsvtav1": "av1", "av1_nvenc": "av1", "av1_qsv": "av1",
    "av1_amf": "av1", "av1_vaapi": "av1",
    "libvpx-vp9": "vp9", "vp9_vaapi": "vp9", "vp9_qsv": "vp9",
}
