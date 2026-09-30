"""화면이 에러 없이 뜨는지만 본다."""
from pathlib import Path

from streamlit.testing.v1 import AppTest


def test_app_starts():
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py")).run(timeout=30)
    assert not app.exception
