import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--apply-update":
        from atlas_updates import helper_main

        sys.exit(helper_main(sys.argv[2]))
    if "--update-healthcheck" in sys.argv:
        try:
            import os

            os.environ["QT_QPA_PLATFORM"] = "offscreen"
            from PySide6.QtWidgets import QApplication
            from atlas_ui import Window, configure_app
            import atlas_core

            if len(sys.argv) > 2 and sys.argv[2] != atlas_core.VERSION:
                sys.exit(2)
            app = QApplication([])
            configure_app(app)
            window = Window(preview=True)
            app.processEvents()
            window.close()
        except Exception:
            # A windowed executable otherwise waits on its traceback dialog,
            # preventing the updater from immediately restoring the old version.
            sys.exit(1)
        sys.exit(0)
    import atlas_updates
    import atlas_core

    try:
        _instance = atlas_updates.instance_lock(atlas_core.ROOT)
        if getattr(sys, "frozen", False):
            atlas_updates.register_current(atlas_core.ROOT, atlas_core.VERSION)
    except atlas_updates.UpdateError as error:
        if sys.platform == "win32":
            __import__("ctypes").windll.user32.MessageBoxW(
                None, str(error), "PW Resource Atlas", 0x40
            )
        sys.exit(1)
    from atlas_ui import main

    main()
