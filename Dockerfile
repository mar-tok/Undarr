FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl gnupg && \
    curl -fsSL https://repo.jellyfin.org/ubuntu/jellyfin_team.gpg.key \
        | gpg --dearmor -o /usr/share/keyrings/jellyfin.gpg && \
    echo "deb [arch=amd64 signed-by=/usr/share/keyrings/jellyfin.gpg] https://repo.jellyfin.org/ubuntu noble main" \
        > /etc/apt/sources.list.d/jellyfin.list && \
    apt-get update && apt-get install -y --no-install-recommends \
        jellyfin-ffmpeg7 \
        python3.12 python3.12-venv \
        gosu && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

RUN ln -sf /usr/lib/jellyfin-ffmpeg/ffmpeg /usr/local/bin/ffmpeg && \
    ln -sf /usr/lib/jellyfin-ffmpeg/ffprobe /usr/local/bin/ffprobe

RUN useradd -u 911 -U -d /app -s /bin/false undarr && \
    mkdir -p /data /logs

COPY --from=ghcr.io/astral-sh/uv:0.10.7 /uv /usr/local/bin/uv

WORKDIR /app

ENV UV_PROJECT_ENVIRONMENT=/opt/venv

COPY pyproject.toml .
RUN uv venv $UV_PROJECT_ENVIRONMENT && uv pip install --no-cache --python $UV_PROJECT_ENVIRONMENT/bin/python .

COPY . .
RUN chmod -R a+rX /app

ENV UNDARR_HOST=0.0.0.0 \
    UNDARR_PORT=6545 \
    UNDARR_DATA_DIR=/data \
    UNDARR_LOG_DIR=/logs

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 6545

ENTRYPOINT ["/entrypoint.sh"]
CMD ["/opt/venv/bin/python", "main.py"]
