from pathlib import Path

from streamlit.testing.v1 import AppTest


def test_frontend_renders_without_backend():
    app = AppTest.from_file(Path(__file__).parents[1] / "app.py").run(timeout=30)
    assert not app.exception
    assert app.title[0].value == "VendorOps AI"
    assert app.button[0].disabled
