from pathlib import Path
import sys
import tempfile
import io
import json
import hashlib
import zipfile
import stat
import copy
from unittest.mock import patch

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "src"))
import atlas_updates as u

checks = 0


def check(test):
    global checks
    assert test
    checks += 1


def raises(operation):
    global checks
    try:
        operation()
    except (u.UpdateError, ValueError, KeyError):
        checks += 1
    else:
        raise AssertionError("Expected a rejected update")


def archive(files=None, ver="2.9", extra=None, bad_hash=False):
    files = files or {
        u.EXE: b"new exe",
        "_internal/new.dll": b"new runtime",
        "atlas_updates.py": b"new source",
    }
    d = {
        "app": u.APP,
        "schema": 1,
        "version": ver,
        "files": {n: hashlib.sha256(b).hexdigest() for n, b in files.items()},
    }
    if bad_hash:
        d["files"][u.EXE] = "0" * 64
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for n, b in files.items():
            z.writestr(n, b)
        z.writestr(u.DESCRIPTOR, json.dumps(d))
        if extra:
            for n, b in extra:
                z.writestr(n, b)
    return out.getvalue(), d


def latest_for(blob):
    return {
        "available": True,
        "version": "2.9",
        "bytes": len(blob),
        "sha256": hashlib.sha256(blob).hexdigest(),
        "url": "https://github.com/Aqwrr/pw-resource-altas/releases/download/v2.9/" + u.PACKAGE,
    }


def snapshot(folder):
    return {
        p.relative_to(folder).as_posix(): p.read_bytes()
        for p in folder.rglob("*")
        if p.is_file() and "updates" not in p.relative_to(folder).parts
    }


def setup(folder):
    folder.mkdir()
    (folder / u.EXE).write_bytes(b"old exe")
    (folder / "_internal").mkdir()
    (folder / "_internal/retired.dll").write_bytes(b"old runtime")
    (folder / "_internal/custom.dll").write_bytes(b"keep externally modified")
    old = {
        "app": u.APP,
        "schema": 1,
        "version": "2.8",
        "files": {
            u.EXE: u.sha256(folder / u.EXE),
            "_internal/retired.dll": u.sha256(folder / "_internal/retired.dll"),
            "_internal/custom.dll": "0" * 64,
        },
    }
    u.write_json(folder / "app-files.json", old)
    for name in (
        "settings.json",
        "presets.json",
        "installed.json",
        "update-settings.json",
        "activation.dat",
        "backups/original.bin",
        "glow-test/installed.json",
        "glow-test/backups/models.pck",
        "patch/manifest.json",
        "data/private.json",
    ):
        p = folder / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(("personal " + name).encode())
    return snapshot(folder)


check(u.version("2.10") > u.version("2.9") and u.version("v2.8.0") == u.version("2.8"))
check(u.repository("https://github.com/Aqwrr/pw-resource-altas.git") == "Aqwrr/pw-resource-altas")
for value in ("nightly", "2.8-beta", "../2.8", None):
    raises(lambda: u.version(value))
for url in (
    "http://github.com/Aqwrr/repo",
    "https://evil.test/Aqwrr/repo",
    "https://github.com@evil.test/x",
):
    raises(lambda: u.https_url(url))
blob, descriptor = archive()
release = {
    "tag_name": "v2.9",
    "draft": False,
    "prerelease": False,
    "body": "Changes",
    "assets": [
        {
            "name": n,
            "state": "uploaded",
            "size": len(blob) if n == u.PACKAGE else 300,
            "browser_download_url": "https://github.com/Aqwrr/pw-resource-altas/releases/download/v2.9/"
            + n,
        }
        for n in (u.FEED, u.PACKAGE)
    ],
}
feed = {
    "app": u.APP,
    "schema": 1,
    "version": "2.9",
    "min_updater": 1,
    "package": {"name": u.PACKAGE, "bytes": len(blob), "sha256": hashlib.sha256(blob).hexdigest()},
}
with patch.object(u, "remote_json", side_effect=[release, feed]):
    check(u.check("Aqwrr/pw-resource-altas", "2.8")["available"])
with patch.object(u, "remote_json", return_value=release) as remote:
    check(not u.check("Aqwrr/pw-resource-altas", "2.10")["available"] and remote.call_count == 1)
for bad in (
    {**release, "prerelease": True},
    {**release, "draft": True},
    {**release, "tag_name": "nightly"},
):
    with patch.object(u, "remote_json", return_value=bad):
        raises(lambda: u.check("Aqwrr/pw-resource-altas", "2.8"))
bad = copy.deepcopy(release)
bad["assets"][1]["browser_download_url"] = bad["assets"][1]["browser_download_url"].replace(
    "Aqwrr", "another-owner"
)
with patch.object(u, "remote_json", return_value=bad):
    raises(lambda: u.check("Aqwrr/pw-resource-altas", "2.8"))
for bad in (
    {**feed, "version": "3.0"},
    {**feed, "min_updater": 2},
    {**feed, "package": {**feed["package"], "sha256": "x"}},
    {**feed, "package": {**feed["package"], "bytes": 7}},
):
    with patch.object(u, "remote_json", side_effect=[release, bad]):
        raises(lambda: u.check("Aqwrr/pw-resource-altas", "2.8"))
with tempfile.TemporaryDirectory(prefix="atlas-updater-tests-") as tmp:
    tmp = Path(tmp)
    folder = tmp / "Атлас друга с пробелами"
    original = setup(folder)
    with patch.object(u, "open_url", return_value=io.BytesIO(blob)):
        progress = []
        plan = u.prepare(folder, latest_for(blob), progress.append)
    check(progress[-1] == 100 and snapshot(folder) == original and u.pending(folder, "2.8") == plan)
    _, p, _ = u.load_plan(plan)
    check(p["phase"] == "prepared")
    with (
        patch.object(u, "wait_parent"),
        patch.object(u, "replace_file", wraps=u.replace_file) as replaced,
    ):
        check(
            u.apply(plan, healthcheck=lambda _: True, restart=False) == "2.9"
            and replaced.call_count >= 3
        )
    check(
        (folder / u.EXE).read_bytes() == b"new exe"
        and not (folder / "_internal/retired.dll").exists()
        and (folder / "_internal/custom.dll").read_bytes() == b"keep externally modified"
    )
    check(
        all(
            (folder / n).read_bytes() == b
            for n, b in original.items()
            if n not in (u.EXE, "_internal/retired.dll", "app-files.json")
        )
    )
    check(u.pending(folder, "2.9") is None)
    raises(lambda: u.apply(plan, healthcheck=lambda _: True, restart=False))
    for mode in ("health", "copy", "tampered", "running", "downgrade"):
        folder = tmp / mode
        before = setup(folder)
        with patch.object(u, "open_url", return_value=io.BytesIO(blob)):
            plan = u.prepare(folder, latest_for(blob))
        if mode == "tampered":
            (Path(plan).parent / "app" / u.EXE).write_bytes(b"changed after verification")
        if mode == "downgrade":
            d = u.read_json(folder / "app-files.json")
            d["version"] = "3.0"
            u.write_json(folder / "app-files.json", d)
            before = snapshot(folder)
        actual = u.replace_file
        calls = []

        def copy_failure(src, dest):
            calls.append(str(dest))
            if len(calls) == 2:
                raise OSError("simulated file lock")
            return actual(src, dest)

        with (
            patch.object(
                u,
                "wait_parent",
                side_effect=u.UpdateError("still running") if mode == "running" else None,
            ),
            patch.object(u, "replace_file", side_effect=copy_failure if mode == "copy" else actual),
        ):
            raises(lambda: u.apply(plan, healthcheck=lambda _: mode != "health", restart=False))
        check(snapshot(folder) == before)
    for number, name in enumerate(
        (
            "../escape",
            "settings.json",
            "activation.dat",
            "installed.json",
            "update-settings.json",
            "backups/old.bin",
            "glow-test/installed.json",
            "element/ElementClient.exe",
            "updates/pending.json",
            "_internal/../settings.json",
            "_internal\\escape.dll",
            "_internal/CON",
            "_internal/bad.dll:stream",
            "/_internal/a.dll",
        )
    ):
        folder = tmp / ("bad" + str(number))
        setup(folder)
        bad, _ = archive(extra=[(name, b"bad")])
        package = folder / "malicious.zip"
        package.write_bytes(bad)
        before = snapshot(folder)
        raises(lambda: u.unpack(package, folder / "unpack", "2.9"))
        check(snapshot(folder) == before and not (tmp / "escape").exists())
    folder = tmp / "symlink"
    setup(folder)
    info = zipfile.ZipInfo("_internal/link")
    info.create_system = 3
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    bad, _ = archive(extra=[(info, b"../../settings.json")])
    p = folder / "bad.zip"
    p.write_bytes(bad)
    raises(lambda: u.unpack(p, folder / "unpack", "2.9"))
    folder = tmp / "corrupt"
    before = setup(folder)
    with patch.object(u, "open_url", return_value=io.BytesIO(blob[:-4])):
        raises(lambda: u.prepare(folder, latest_for(blob)))
    check(snapshot(folder) == before)
    bad, _ = archive(bad_hash=True)
    with patch.object(u, "open_url", return_value=io.BytesIO(bad)):
        raises(lambda: u.prepare(folder, latest_for(bad)))
    check(snapshot(folder) == before)
    folder = tmp / "path-journal"
    setup(folder)
    bad = folder / "plan.json"
    u.write_json(bad, {"schema": 1, "target": str(folder), "version": "2.9"})
    raises(lambda: u.load_plan(bad))
    with patch.object(u, "MAX_UNPACKED", 1):
        p = folder / "size.zip"
        p.write_bytes(blob)
        raises(lambda: u.unpack(p, folder / "unpack", "2.9"))
u.write_json(
    root / "build/test-results/updater-checks.json",
    {
        "checks": checks,
        "semantic_version_comparison": True,
        "github_repo_https_and_asset_identity_validated": True,
        "truncated_and_tampered_downloads_rejected": True,
        "zip_paths_duplicates_symlinks_and_personal_files_rejected": True,
        "transaction_rollback_after_copy_and_healthcheck_failure": True,
        "retired_owned_files_removed_external_changes_preserved": True,
        "settings_presets_journals_backups_patch_and_personal_data_preserved": True,
        "running_parent_and_downgrade_rejected": True,
    },
)
print(
    f"PASS: {checks} updater checks; GitHub/version metadata, archive validation, preserved user files, rollback, locking and downgrade protection"
)
