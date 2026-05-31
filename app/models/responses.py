from __future__ import annotations

from pydantic import BaseModel


class PresetOut(BaseModel):
    name: str
    ffmpeg_args: str
    output_container: str | None = None
