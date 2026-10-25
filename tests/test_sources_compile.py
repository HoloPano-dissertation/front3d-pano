import py_compile
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parents[1] / "src" / "front3d_pano"


@pytest.mark.parametrize("path", sorted(PACKAGE.rglob("*.py")), ids=lambda path: path.name)
def test_every_module_compiles(path):
    py_compile.compile(str(path), doraise=True)
