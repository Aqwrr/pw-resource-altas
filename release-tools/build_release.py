"""Build an OTA ZIP from a tested Windows bundle, excluding personal data."""

from pathlib import Path
import argparse
import ast
import importlib.util
import json
import zipfile

PROJECT = Path(__file__).resolve().parents[1]


def build(bundle, output, notes=""):
    bundle = Path(bundle).resolve()
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    spec = importlib.util.spec_from_file_location(
        "atlas_update_packager", PROJECT / "src/atlas_updates.py"
    )
    u = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(u)
    tree = ast.parse((PROJECT / "src/atlas_core.py").read_text(encoding="utf-8"))
    ver = next(
        ast.literal_eval(n.value)
        for n in tree.body
        if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "VERSION" for t in n.targets)
    )
    u.version(ver)
    paths = []
    for p in bundle.iterdir():
        if p.is_file() and p.name == u.EXE:
            paths.append(p)
        elif p.is_dir() and p.name in ("_internal", "third-party-licenses"):
            paths.extend(f for f in p.rglob("*") if f.is_file() and "__pycache__" not in f.parts)
    if (
        not (bundle / u.EXE).is_file()
        or not (bundle / "_internal/assets/update-source.json").is_file()
    ):
        raise RuntimeError("Not a complete updater-enabled Windows bundle")
    if any(p.is_symlink() or not p.resolve().is_relative_to(bundle) for p in paths):
        raise RuntimeError("Bundle contains a link outside its own folder")
    files = {p.relative_to(bundle).as_posix(): u.sha256(p) for p in sorted(paths)}
    descriptor = {"schema": 1, "app": u.APP, "version": ver, "files": files}
    u.validate_descriptor(descriptor)
    archive = output / u.PACKAGE
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for name in files:
            z.write(bundle / name, name)
        z.writestr(u.DESCRIPTOR, json.dumps(descriptor, ensure_ascii=False, indent=2))
    if archive.stat().st_size > u.MAX_DOWNLOAD:
        raise RuntimeError("Update ZIP exceeds the updater size limit")
    with zipfile.ZipFile(archive) as z:
        if z.testzip() is not None:
            raise RuntimeError("ZIP integrity check failed")
    feed = {
        "schema": 1,
        "app": u.APP,
        "version": ver,
        "min_updater": 1,
        "package": {
            "name": u.PACKAGE,
            "bytes": archive.stat().st_size,
            "sha256": u.sha256(archive),
        },
        "notes": notes,
    }
    u.write_json(output / u.FEED, feed)
    u.write_json(output / u.DESCRIPTOR, descriptor)
    (output / "SHA256SUMS.txt").write_text(
        feed["package"]["sha256"]
        + "  "
        + u.PACKAGE
        + "\n"
        + u.sha256(output / u.FEED)
        + "  "
        + u.FEED
        + "\n",
        encoding="utf-8",
    )
    print(
        f"Готово: версия {ver}, {len(files)} файлов, архив {archive.stat().st_size / 1024 / 1024:.1f} МБ. Личные данные исключены.",
        flush=True,
    )
    return feed


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--bundle", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--notes", type=Path)
    a = p.parse_args()
    build(a.bundle, a.output, a.notes.read_text(encoding="utf-8") if a.notes else "")
