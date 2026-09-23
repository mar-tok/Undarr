# Hardware encoding

At startup Undarr reads the encoder list from ffmpeg and runs a short test encode with each one. Only the encoders that complete the test are listed, grouped by device, and each device has its own concurrent job limit in Settings.

## NVIDIA NVENC

NVENC needs the NVIDIA driver and the NVIDIA Container Toolkit on the host. It has been tested on an RTX 40 series card. The image sets `NVIDIA_DRIVER_CAPABILITIES` to include `video`, so the toolkit mounts the encoder library when the GPU is passed through. Add this to the service in `docker-compose.yml`:

```yaml
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu]
```

## Intel Quick Sync (QSV)

QSV needs the render node passed through. The Intel media driver is included in the jellyfin-ffmpeg package. The entrypoint adds the app user to the group that owns each device node. This works with any group ID on the host. QSV has not been verified inside the container yet.

```yaml
    devices:
      - /dev/dri:/dev/dri
```

## VAAPI and AMD

VAAPI is currently not supported, so VAAPI encoders fail the startup test and are not listed. Intel GPUs use QSV. AMD GPUs on Linux encode through VAAPI, so Undarr cannot use them yet.
