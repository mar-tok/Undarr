# Tests

```sh
pip install -e ".[test]"
pytest
```

The tests need ffmpeg and ffprobe on the machine. The first run generates the test media under `tests/fixtures` from `generate.sh`.

The frontend helper tests are in `tests/js` and need Node 22.7 or newer, which loads the frontend ES modules without a package.json. They have no dependencies.

```sh
node --test tests/js
```
