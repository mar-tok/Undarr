import subprocess
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session", autouse=True)
def test_media():
    # generate.sh writes this file last. It exists only when every fixture exists
    if not (FIXTURES / "video_profiles" / "hdr10plus.mkv").exists():
        subprocess.run(["./generate.sh"], cwd=FIXTURES, check=True)
