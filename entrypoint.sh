#!/bin/bash
set -e

PUID=${PUID:-911}
PGID=${PGID:-911}

groupmod -o -g "$PGID" undarr
usermod -o -u "$PUID" undarr

usermod -aG video,render undarr || true

chown undarr:undarr /data /logs

exec gosu undarr "$@"
