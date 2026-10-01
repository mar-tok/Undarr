# Undarr

Undarr transcodes media libraries in place to match your quality standards. Select a library and a preset, and it finds the video files, queues them, encodes each one with ffmpeg, checks the result, then replaces the original. It runs as a single container accessed via a web UI.

![Overview](docs/images/overview.png)

> [!CAUTION]
> Undarr is in early development and has had limited testing. Transcoding is lossy and the original is deleted after a successful job. You should test presets on a library of copied files first. Verify that your test library behaves as expected before you move on to your real files. Report problems in [Issues](https://github.com/mar-tok/Undarr/issues).

## Quick start

The image is built for x86_64 (amd64). Create a folder for Undarr and save the Compose file below as `docker-compose.yml` in that folder. Change `/path/to/media` to the folder with your media files, and set `PUID` and `PGID` to the IDs of the user and group that own those files.

```yaml
services:
  undarr:
    image: ghcr.io/mar-tok/undarr:latest
    container_name: undarr
    restart: unless-stopped
    ports:
      - "6545:6545"
    volumes:
      - ./data:/data
      - ./logs:/logs
      - /path/to/media:/media
    environment:
      - PUID=1000
      - PGID=1000
```

```sh
docker compose up -d
```

Open `http://localhost:6545`. The quick start page will help you get started.

To update, run `docker compose pull` and then `docker compose up -d` in the same folder.

## Documentation

- [Features](docs/features.md)
- [Hardware encoding](docs/hardware-encoding.md)
- [HDR](docs/hdr.md)
- [Configuration](docs/configuration.md)
- [Tests](docs/tests.md)

## Credits

Icons from [Bootstrap Icons](https://github.com/twbs/icons) and [Feather](https://github.com/feathericons/feather), charts by [Chart.js](https://www.chartjs.org). See `THIRD_PARTY_NOTICES.md`.

## License

AGPL-3.0. See `LICENSE`.
