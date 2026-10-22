from pathlib import Path
import os
import sys
import tempfile
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "src"))
import atlas_access as access
import atlas_core as core
import atlas_glow as glow
import atlas_bundle as bundle
from atlas_access_ui import ActivationDialog, ensure_activation
from atlas_ui import Window, configure_app, main
from PySide6.QtWidgets import QApplication, QPushButton

TEST_KEY = "PWA-ADMIN-AAAA-AAAA-AAAA-AAAA-AAAA-AAAA-AAAA-AAAA"
salt = "1234567890abcdef" * 2
digest = access.key_digest(access.normalize_key(TEST_KEY), salt)
app = QApplication([])
configure_app(app)


def blocked(operation):
    try:
        operation()
    except access.ActivationRequired:
        return
    raise AssertionError("Unlicensed feature was not blocked")


with (
    tempfile.TemporaryDirectory(prefix="atlas-access-") as temporary,
    patch.object(access.policy, "SALT", salt),
    patch.object(access.policy, "DIGEST", digest),
):
    core.ROOT = Path(temporary) / "Атлас с пробелами"
    core.ROOT.mkdir()
    assert not access.is_activated(core.ROOT)
    assert not access.valid_key("") and not access.valid_key("X" * 10000)
    assert not access.valid_key("PWA-ADMIN-BBBB-AAAA-AAAA-AAAA-AAAA-AAAA-AAAA-AAAA")
    assert access.valid_key(TEST_KEY.lower()) and access.valid_key("  " + TEST_KEY + "\n")
    for operation in (
        lambda: Window(),
        lambda: core.build_patch([]),
        lambda: core.install(None),
        core.uninstall,
        lambda: glow.build_beacons(None),
        lambda: glow.install_beacons(None),
        glow.remove_beacons,
        lambda: bundle.install(None),
    ):
        blocked(operation)
    assert not list(core.ROOT.iterdir()), "Blocked actions must not write or touch game files"
    with patch.object(ActivationDialog, "exec", return_value=ActivationDialog.DialogCode.Rejected):
        assert not ensure_activation()
    # Even screenshot mode must pass the same activation gate.
    with (
        patch("atlas_ui.QApplication", return_value=app),
        patch("atlas_ui.Window") as window,
        patch("atlas_access_ui.ensure_activation", return_value=False),
        patch.object(sys, "argv", ["atlas", "--screenshot"]),
    ):
        main()
        assert not window.called
    dialog = ActivationDialog()
    dialog.show()
    app.processEvents()
    assert not dialog.activate_button.isEnabled()
    dialog.key.setText("wrong")
    dialog.submit()
    assert dialog.result() != dialog.DialogCode.Accepted and not access.is_activated(core.ROOT)
    assert "не подошёл" in dialog.message.text()
    output = root / "build/test-results"
    output.mkdir(parents=True, exist_ok=True)
    dialog.key.clear()
    dialog.grab().save(str(output / f"activation-{app.devicePixelRatio()}.png"))
    assert {
        button.height() for button in dialog.findChildren(QPushButton) if button.isVisible()
    } == {38}
    dialog.key.setText(TEST_KEY)
    dialog.submit()
    assert dialog.result() == dialog.DialogCode.Accepted and access.is_activated(core.ROOT)
    record = core.ROOT / access.ACTIVATION_FILE
    protected = record.read_bytes()
    assert (
        TEST_KEY.encode() not in protected
        and access.normalize_key(TEST_KEY).encode() not in protected
    )
    access.require_activated(core.ROOT)
    with patch.object(
        ActivationDialog, "exec", side_effect=AssertionError("Activated users must not be prompted")
    ):
        assert ensure_activation()
    window = Window()
    window.close()
    record.write_bytes(b'{"active":true}')
    assert not access.is_activated(core.ROOT)
    record.write_bytes(protected[:-1] + bytes([protected[-1] ^ 1]))
    assert not access.is_activated(core.ROOT)
    record.write_bytes(access.MAGIC + b"x" * 70000)
    assert not access.is_activated(core.ROOT)
    record.write_bytes(protected)
    with patch.object(access.policy, "DIGEST", "0" * 64):
        assert not access.is_activated(core.ROOT), "Rotating the key must reject an old activation"
    record.unlink()
    assert not access.is_activated(core.ROOT)
print(
    "PASS: real DPAPI activation; wrong/tampered keys blocked; startup/screenshot/install gates; private key not stored as plaintext"
)
