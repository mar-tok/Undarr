# Tests

```sh
pip install -e ".[test]"
pytest
```

The tests need ffmpeg and ffprobe on the machine. The first run generates the test media under `tests/fixtures` from `generate.sh`.
