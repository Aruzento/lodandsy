import os
import sys
from pathlib import Path

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtGui import QFontDatabase


@pytest.fixture(scope="session", autouse=True)
def offscreen_system_font(qapp):
    """Windows offscreen QPA has no font discovery; zero metrics invalidate layout tests."""
    if sys.platform == "win32" and qapp.platformName() == "offscreen":
        font = Path(os.environ["WINDIR"]) / "Fonts" / "segoeui.ttf"
        assert QFontDatabase.addApplicationFont(str(font)) >= 0


@pytest.fixture(autouse=True)
def isolated_project_catalogue(tmp_path, monkeypatch):
    """GUI tests must not publish temporary worlds into the user's catalogue."""
    monkeypatch.setattr(
        "lodandsy.application.project_history.QSettings",
        lambda *args: QSettings(str(tmp_path / "user.ini"), QSettings.Format.IniFormat),
    )
