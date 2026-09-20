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
