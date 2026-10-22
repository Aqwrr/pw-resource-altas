from pathlib import Path
import sys
import os
import tempfile
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
root = Path(__file__).resolve().parents[1]
bundle = root / ".local"
sys.path.insert(0, str(root / "src"))
(root / "build/test-results").mkdir(parents=True, exist_ok=True)
import atlas_core as c
from atlas_ui import Window, configure_app
from atlas_onboarding import OnboardingDialog
from atlas_preset_ui import PresetsDialog
from atlas_updates_ui import UpdatesDialog
from PySide6.QtCore import Qt, QPoint
from PySide6.QtWidgets import QApplication, QPushButton, QInputDialog

app = QApplication([])
configure_app(app)
real_root = c.ROOT
preserved = {
    n: c.digest(bundle / n) if (bundle / n).exists() else None
    for n in (
        "settings.json",
        "presets.json",
        "installed.json",
        "glow-test/installed.json",
        "update-settings.json",
    )
}
# Folder discovery uses real Unicode filesystem paths. Client signature checks are covered separately.
c.require_supported_client = c.resolve_client_folder


def visible(w):
    return sum(not row.isHidden() for row in w.leaves.values())


def same_heights(widget):
    heights = {b.height() for b in widget.findChildren(QPushButton) if b.isVisible()}
    assert heights == {38}, heights


with tempfile.TemporaryDirectory(prefix="atlas-ux-") as tmp:
    tmp = Path(tmp).resolve()
    c.ROOT = tmp / "Атлас"
    c.ROOT.mkdir()
    client = tmp / "Игры друга" / "Русский клиент с пробелами"
    element = client / "element"
    element.mkdir(parents=True)
    (element / "ElementClient.exe").write_bytes(b"folder fixture")
    for name in ("surfaces.pck", "configs.pck"):
        (element / name).write_bytes(b"folder fixture")
    (client / "launcher.ini").write_text("[Options]\nTestClient=0\n")
    c.write_json(c.ROOT / "update-settings.json", {"check_on_start": False, "auto_update": False})
    assert c.DEFAULT_CLIENT is None
    try:
        c.require_supported_client(None)
    except ValueError:
        pass
    else:
        raise AssertionError("Empty path accepted")
    wizard = OnboardingDialog()
    wizard.show()
    app.processEvents()
    assert wizard.path.text() == "" and not wizard.next.isEnabled()
    wizard.path.setText(str(tmp / "missing"))
    assert not wizard.validate()
    wizard.path.setText(str(element))
    assert wizard.validate() and wizard.client == client
    same_heights(wizard)
    wizard.grab().save(
        str(root / "build/test-results" / ("onboarding-" + str(app.devicePixelRatio()) + ".png"))
    )
    wizard.advance()
    assert wizard.pages.currentIndex() == 1
    wizard.advance()
    assert wizard.result() == wizard.DialogCode.Accepted
    wizard.close()
    w = Window()
    w.show()
    app.processEvents()
    assert (
        w.state["client"] == ""
        and not w.apply.isEnabled()
        and visible(w) == 49
        and w.tier.currentData() == 0
        and w.category.currentData() == "all"
    )
    with patch("atlas_ui.QFileDialog.getExistingDirectory", return_value=str(element)):
        w.choose_client()
    assert w.state["client"] == str(client) and w.state["onboarding_completed"]
    preset = w.builtin_presets[0]
    w.preset_changed(w.presets.findData(preset["id"]))
    assert (
        w.selected() == set(preset["selected"])
        and visible(w) == 49
        and w.category.currentData() == "all"
    )
    w.category.setCurrentIndex(w.category.findData("selected"))
    assert visible(w) == len(w.selected())
    w.search.setText("несуществующий ресурс")
    assert visible(w) == 0
    kept = w.selected()
    w.reset_filters()
    assert visible(w) == 49 and w.selected() == kept
    w.category.setCurrentIndex(w.category.findData("selected"))
    w.clear.click()
    assert (
        not w.selected()
        and not w.active_preset
        and visible(w) == 49
        and w.category.currentData() == "all"
        and w.tier.currentData() == 0
    )
    w.preset_changed(w.presets.findData(preset["id"]))
    kept = w.selected()
    w.category.setCurrentIndex(w.category.findData("selected"))
    w.preset_changed(0)
    assert w.selected() == kept and visible(w) == 49 and w.active_preset is None
    manager = PresetsDialog(w)
    manager.show()
    app.processEvents()
    with patch.object(QInputDialog, "getText", return_value=("Мой круг", True)):
        manager.save.click()
    assert manager.list.topLevelItemCount() == 1 and w.preset_store.presets[0][
        "selected"
    ] == sorted(kept)
    key = w.preset_store.presets[0]["id"]
    with patch.object(QInputDialog, "getText", return_value=("Новый круг", True)):
        manager.rename.click()
    assert w.preset_store.find(key)["name"] == "Новый круг"
    same_heights(manager)
    manager.grab().save(
        str(root / "build/test-results" / ("presets-" + str(app.devicePixelRatio()) + ".png"))
    )
    manager.close()
    app.processEvents()
    for width, height in ((980, 600), (1280, 720), (1350, 900), (1920, 1080), (2560, 1440)):
        w.resize(width, height)
        app.processEvents()
        app.processEvents()
        assert w.size().toTuple() == (width, height), w.size().toTuple()
        same_heights(w)
        for widget in (
            w.tree,
            w.map,
            w.folder,
            w.updateButton,
            w.resetFilters,
            w.topmost,
            w.coords,
        ):
            p = widget.mapTo(w, QPoint())
            assert (
                p.x() >= 0
                and p.y() >= 0
                and p.x() + widget.width() <= width
                and p.y() + widget.height() <= height
            ), (width, height, widget.objectName(), p.toTuple(), widget.size().toTuple())
        assert w.tree.viewport().height() > 55
    w.resize(1350, 900)
    app.processEvents()
    w.topmost.setChecked(True)
    app.processEvents()
    overlay = w.overlay
    assert (
        overlay.isVisible()
        and overlay.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
        and not w.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
    )
    assert overlay.map.selected == w.selected() and overlay.map.world == w.map.world
    main_scale = w.map.scale
    overlay.map.zoom(1.5)
    assert w.map.scale == main_scale
    overlay.map.route = [[667, 372], [471, 324]]
    overlay.map.routeChanged.emit()
    assert w.routes["world"] == overlay.map.route == w.map.route
    w.map.route.append([550, 650])
    w.route_changed()
    assert overlay.map.route == w.map.route
    w.set_busy(True)
    assert not overlay.map.route_editable
    w.set_busy(False)
    assert overlay.map.route_editable
    overlay.resize(500, 560)
    app.processEvents()
    overlay.geometryChanged.emit()
    assert w.state["overlay_geometry"][2:] == [500, 560]
    w.showMinimized()
    app.processEvents()
    assert overlay.isVisible() and not overlay.isMinimized()
    w.showNormal()
    app.processEvents()
    overlay.grab().save(
        str(root / "build/test-results" / ("overlay-" + str(app.devicePixelRatio()) + ".png"))
    )
    overlay.close()
    app.processEvents()
    assert not w.topmost.isChecked() and not w.state["overlay_enabled"]
    w.topmost.setChecked(True)
    app.processEvents()
    assert overlay.size().toTuple() == (500, 560)
    w.world.setCurrentIndex(w.world.findData("a21"))
    assert overlay.map.world == "a21"
    w.world.setCurrentIndex(w.world.findData("world"))
    w.updates.latest = {
        "available": False,
        "version": c.VERSION,
        "notes": "Все изменения версии отображаются даже после обновления.",
    }
    dialog = UpdatesDialog(w.updates, w)
    dialog.show()
    app.processEvents()
    same_heights(dialog)
    assert not dialog.action.isVisible() and dialog.notes.toPlainText()
    dialog.grab().save(
        str(root / "build/test-results" / ("updates-" + str(app.devicePixelRatio()) + ".png"))
    )
    dialog.close()
    app.processEvents()
    w.grab().save(
        str(root / "build/test-results" / ("interface-" + str(app.devicePixelRatio()) + ".png"))
    )
    w.close()
    app.processEvents()
    assert not overlay.isVisible()
    state = c.read_json(c.ROOT / "settings.json")
    assert state["overlay_enabled"] and state["topmost"] is False and state["client"] == str(client)
    w = Window()
    w.show()
    app.processEvents()
    assert visible(w) == 49 and w.tier.currentData() == 0 and w.category.currentData() == "all"
    w.begin_first_run()
    assert w.overlay.isVisible() and not w.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
    w.close()
c.ROOT = real_root
assert all(
    (c.digest(bundle / n) if (bundle / n).exists() else None) == sha for n, sha in preserved.items()
)
c.write_json(
    root / "build/test-results" / ("ux-checks-" + str(app.devicePixelRatio()) + ".json"),
    {
        "all_buttons_height": 38,
        "default_all_49_visible": True,
        "preset_and_visibility_filters_independent": True,
        "reset_restores_all_categories_and_tiers": True,
        "personal_presets_saved_and_renamed": True,
        "required_onboarding_empty_default_and_cyrillic_path": True,
        "overlay_only_topmost_resizable_and_minimize_independent": True,
        "overlay_routes_selection_and_busy_state_synchronized": True,
        "overlay_geometry_persisted_and_restored": True,
        "main_layout_checked_from_980x600_to_2560x1440": True,
        "update_changelog_visible_when_current": True,
        "DPI": app.devicePixelRatio(),
        "real_user_files_unchanged": True,
    },
)
print(
    "PASS: UX, onboarding Cyrillic folder, filters/presets/reset, separate resizable map, route sync and uniform 38px buttons; DPI="
    + str(app.devicePixelRatio())
)
