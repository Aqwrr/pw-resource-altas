from pathlib import Path
import os
import sys
import tempfile
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "src"))

import atlas_core as core
from atlas_help import HelpDialog, PAGES
from atlas_ui import Window, configure_app
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QDialog, QPushButton, QTextBrowser

app = QApplication([])
configure_app(app)
with tempfile.TemporaryDirectory(prefix="atlas-help-") as folder:
    core.ROOT = Path(folder)
    core.write_json(
        core.ROOT / "update-settings.json", {"check_on_start": False, "auto_update": False}
    )
    window = Window(preview=True)
    window.show()
    app.processEvents()
    assert "Тест" not in [action.text() for action in window.menuBar().actions()]
    help_menu = window.menuBar().actions()[-1].menu()
    calls = []

    def modal(dialog):
        calls.append(dialog.windowTitle())
        if isinstance(dialog, HelpDialog):
            assert dialog.windowModality() == Qt.WindowModality.WindowModal
        dialog.done(QDialog.DialogCode.Accepted)
        return QDialog.DialogCode.Accepted

    with (
        patch("os.startfile") as external,
        patch.object(QDialog, "exec", modal),
        patch.object(window.updates, "check"),
    ):
        for action in help_menu.actions():
            if action.isSeparator():
                continue
            action.trigger()
            app.processEvents()
            if window.updates.dialog:
                assert window.updates.dialog.windowModality() == Qt.WindowModality.WindowModal
                window.updates.dialog.close()
                app.processEvents()
        assert external.call_count == 0
    assert len(calls) == 5
    for key in PAGES:
        dialog = HelpDialog(window, key)
        dialog.show()
        app.processEvents()
        page = dialog.tabs.currentWidget()
        assert isinstance(page, QTextBrowser) and not page.openExternalLinks()
        assert 15 < len(page.toPlainText().split()) < 160
        assert {
            button.height() for button in dialog.findChildren(QPushButton) if button.isVisible()
        } == {38}
        if key == "start":
            output = root / "build/test-results"
            output.mkdir(parents=True, exist_ok=True)
            dialog.grab().save(str(output / f"help-{app.devicePixelRatio()}.png"))
        dialog.close()
    window.close()
print("PASS: all Help entries stay in native modal windows; no external app launches; no Test menu")
