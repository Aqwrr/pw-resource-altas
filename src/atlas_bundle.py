"""Coordinate map and beacon installation, rolling the map back on model errors."""

from pathlib import Path
import os
import shutil
from datetime import datetime
import atlas_core as core
import atlas_glow as glow


def install(client, beacons=True):
    core.atlas_access.require_activated(core.ROOT)
    client = Path(client).resolve()
    if core.game_running():
        raise ValueError("Сначала полностью закройте игру.")
    if beacons:
        maps = core.read_json(core.ROOT / "patch/manifest.json", {})
        models = core.read_json(glow.feature_root() / "prepared/manifest.json", {})
        if (
            not models
            or Path(models["client"]).resolve() != client
            or set(models.get("resource_keys", [])) != set(maps.get("selected", []))
        ):
            raise ValueError(
                "Карта и маяки собраны для разных наборов. Пересоберите выбранные ресурсы."
            )
    folder = core.ROOT / "bundle-transactions" / datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    folder.mkdir(parents=True)
    before = {}
    for name in core.INSTALL_PATHS:
        path = client / name
        before[name] = core.digest(path) if path.exists() else None
        if path.exists():
            backup = folder / name
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, backup)
    journal = core.ROOT / "installed.json"
    previous = journal.read_bytes() if journal.exists() else None
    changed = False
    cleanup = False
    try:
        core.install(client)
        changed = True
        if beacons:
            glow.install_beacons(client)
        elif glow.load_state():
            glow.remove_beacons()
        cleanup = True
    except Exception:
        if changed:
            # Only restore our own just-installed files or the captured originals.
            manifest = core.read_json(core.ROOT / "patch/manifest.json")
            if any(
                (core.digest(client / name) if (client / name).exists() else None)
                not in (before[name], manifest["files"].get(name))
                for name in before
            ):
                raise RuntimeError(
                    "После ошибки обнаружены внешние изменения карты. Снимок сохранён: "
                    + str(folder)
                )
            for name, sha in before.items():
                dest = client / name
                if sha is None:
                    dest.unlink(missing_ok=True)
                else:
                    temp = dest.with_name(dest.name + ".atlas-bundle-rollback")
                    shutil.copyfile(folder / name, temp)
                    os.replace(temp, dest)
            if previous is None:
                journal.unlink(missing_ok=True)
            else:
                temp = journal.with_suffix(".bundle-rollback")
                temp.write_bytes(previous)
                os.replace(temp, journal)
        cleanup = True
        raise
    finally:
        # Remove only known snapshot files after success or a completed rollback.
        if cleanup:
            for name in before:
                snapshot = folder / name
                if snapshot.exists():
                    snapshot.unlink()
