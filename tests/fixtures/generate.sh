#!/bin/sh
# Regenerates the test media. Run from this directory.
set -e
mkdir -p edge_cases video_profiles

ffmpeg -y -v error -f lavfi -i testsrc=duration=3:size=320x240:rate=24 -c:v libx264 -pix_fmt yuv420p edge_cases/valid.mkv
ffmpeg -y -v error -f lavfi -i testsrc=duration=10:size=320x240:rate=24 -c:v libx264 -pix_fmt yuv420p edge_cases/long.mkv
ffmpeg -y -v error -f lavfi -i testsrc=duration=3:size=360x360:rate=30 -f lavfi -i sine=frequency=440:duration=3 -c:v libx264 -pix_fmt yuv420p -c:a aac -shortest edge_cases/valid.mov
ffmpeg -y -v error -f lavfi -i sine=frequency=440:duration=3 -c:a aac edge_cases/audio_only.mka
printf 'this is not a video' > edge_cases/corrupt.mkv

# A 16x16 cover muxed in as an attached picture stream
ffmpeg -y -v error -f lavfi -i color=red:size=16x16:duration=1,format=yuvj420p -frames:v 1 cover.jpg
ffmpeg -y -v error -i edge_cases/valid.mov -i cover.jpg -map 0 -map 1 -c copy -disposition:v:1 attached_pic edge_cases/attached_pic.mp4
rm cover.jpg

ffmpeg -y -v error -f lavfi -i testsrc=duration=3:size=1920x1080:rate=24 -f lavfi -i sine=frequency=440:duration=3 -c:v libx264 -pix_fmt yuv420p -c:a aac -shortest edge_cases/1080p_h264_8bit_audio.mkv
ffmpeg -y -v error -f lavfi -i testsrc=duration=3:size=1920x1080:rate=24 -c:v libx264 -pix_fmt yuv420p video_profiles/1080p_h264_8bit.mkv
ffmpeg -y -v error -f lavfi -i testsrc=duration=3:size=1280x720:rate=24 -c:v libx264 -pix_fmt yuv420p video_profiles/720p_h264_8bit.mkv
ffmpeg -y -v error -f lavfi -i testsrc=duration=3:size=3840x2160:rate=24 -c:v libx264 -pix_fmt yuv420p video_profiles/4k_h264_8bit.mkv
ffmpeg -y -v error -f lavfi -i testsrc=duration=3:size=1920x1080:rate=24 -c:v libx265 -pix_fmt yuv420p10le -x265-params log-level=error video_profiles/1080p_h265_10bit.mkv

# ffmpeg 9 ignores -color_trc for libx265, setparams sets the transfer
HDR_VF="format=yuv420p10le,setparams=color_primaries=bt2020:color_trc=smpte2084:colorspace=bt2020nc"
HDR_X265="master-display=G(13250,34500)B(7500,3000)R(34000,16000)WP(15635,16450)L(10000000,1):max-cll=1000,400:log-level=error"
cat > hdr10plus.json <<'JSON'
{"JSONInfo": {"HDR10plusProfile": "A", "Version": "1.0"},
 "SceneInfo": [
  {"LuminanceParameters": {"AverageRGB": 1000, "LuminanceDistributions": {"DistributionIndex": [1, 5, 10, 25, 50, 75, 90, 95, 99], "DistributionValues": [0, 10, 100, 500, 1000, 5000, 10000, 20000, 40000]}, "MaxScl": [40000, 40000, 40000]}, "NumberOfWindows": 1, "TargetedSystemDisplayMaximumLuminance": 0, "SceneFrameIndex": 0, "SceneId": 0, "SequenceFrameIndex": 0},
  {"LuminanceParameters": {"AverageRGB": 1000, "LuminanceDistributions": {"DistributionIndex": [1, 5, 10, 25, 50, 75, 90, 95, 99], "DistributionValues": [0, 10, 100, 500, 1000, 5000, 10000, 20000, 40000]}, "MaxScl": [40000, 40000, 40000]}, "NumberOfWindows": 1, "TargetedSystemDisplayMaximumLuminance": 0, "SceneFrameIndex": 1, "SceneId": 0, "SequenceFrameIndex": 1},
  {"LuminanceParameters": {"AverageRGB": 1000, "LuminanceDistributions": {"DistributionIndex": [1, 5, 10, 25, 50, 75, 90, 95, 99], "DistributionValues": [0, 10, 100, 500, 1000, 5000, 10000, 20000, 40000]}, "MaxScl": [40000, 40000, 40000]}, "NumberOfWindows": 1, "TargetedSystemDisplayMaximumLuminance": 0, "SceneFrameIndex": 2, "SceneId": 0, "SequenceFrameIndex": 2}
 ],
 "SceneInfoSummary": {"SceneFirstFrameIndex": [0], "SceneFrameNumbers": [3]},
 "ToolInfo": {"Tool": "generate.sh", "Version": "1"}}
JSON
ffmpeg -y -v error -f lavfi -i testsrc=size=320x240:rate=24 -frames:v 3 -vf "$HDR_VF" -c:v libx265 -preset ultrafast -x265-params "$HDR_X265" video_profiles/hdr10.mkv
ffmpeg -y -v error -f lavfi -i testsrc=size=320x240:rate=24 -frames:v 3 -vf "$HDR_VF" -c:v libx265 -preset ultrafast -x265-params "$HDR_X265:dhdr10-info=hdr10plus.json" video_profiles/hdr10plus.mkv
rm hdr10plus.json
