from pathlib import Path
import os

HOST: str = os.getenv("UNDARR_HOST", "0.0.0.0")
PORT: int = int(os.getenv("UNDARR_PORT", "8080"))
DATA_DIR: Path = Path(os.getenv("UNDARR_DATA_DIR", "data"))
LOG_DIR: Path = Path(os.getenv("UNDARR_LOG_DIR", "logs"))
FFMPEG_BIN: str = os.getenv("UNDARR_FFMPEG_BIN", "ffmpeg")
FFPROBE_BIN: str = os.getenv("UNDARR_FFPROBE_BIN", "ffprobe")
