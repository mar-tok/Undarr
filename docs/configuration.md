# Configuration

The environment variables below set where Undarr runs and where it writes. Presets, libraries, and settings are edited in the web UI and stored in `config.yaml` under the data folder. Job history and scanned file records are in `undarr.db` in the same folder.

| Variable | Default | Description |
|---|---|---|
| `PUID` / `PGID` | `1000` in the compose file | User and group the app runs as. Match the owner of the media files. |
| `UNDARR_HOST` | `0.0.0.0` | Address the web server binds to |
| `UNDARR_PORT` | `6545` | Web server port |
| `UNDARR_DATA_DIR` | `/data` | Config file and database |
| `UNDARR_LOG_DIR` | `/logs` | Log file, rotated at 10 MB, and the three newest old files are kept |
| `UNDARR_CONFIG` | `/data/config.yaml` | Config file path |
| `UNDARR_FFMPEG_BIN` | `ffmpeg` | ffmpeg binary |
| `UNDARR_FFPROBE_BIN` | `ffprobe` | ffprobe binary |

## Cache folder

A transcode job writes the new file to the cache folder. When every check passes, the new file replaces the original file. The cache folder is set in Settings and defaults to `/tmp/undarr`. That path is inside the container, so the file is written to Docker's storage on the host (`/var/lib/docker` by default).

If the cache and the media are in the same volume mount, the new file is renamed to the original's path and replaces it. If they are in separate mounts, the new file is copied into the media mount and then deleted from the cache. A rename takes no time. A copy takes longer the larger the file is. Two mounts count as separate even when they are on the same filesystem on the host. The container's `/tmp` is separate from every mount.

To avoid the copy, put the cache inside the media mount and outside every library path. With `/path/to/media:/media` mounted and libraries at `/media/Movies` and `/media/Shows`, set the cache to `/media/.undarr-cache`. The cache needs free space for the largest output.

## Running from source

You need Python 3.12 or newer and ffmpeg with ffprobe on `PATH`. Outside the image, the data and log folders default to `data` and `logs` in the working directory.

```sh
pip install -e .
python main.py
```
