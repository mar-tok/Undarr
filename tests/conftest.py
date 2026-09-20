import subprocess
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session", autouse=True)
def test_media():
    if not (FIXTURES / "edge_cases" / "valid.mkv").exists():
        subprocess.run(["./generate.sh"], cwd=FIXTURES, check=True)
