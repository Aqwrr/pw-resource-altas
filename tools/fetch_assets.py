"""Fetch the pinned public resource bundle, never a developer's game folder."""

from pathlib import Path
import hashlib
import json
import shutil
import stat
import tempfile
import urllib.request
import zipfile

PROJECT = Path(__file__).resolve().parents[1]


def fetch(destination):
    destination = Path(destination).resolve()
    if (destination / "resources.json").is_file():
        print("Ресурсы уже подготовлены.", flush=True)
        return
    source = json.loads((PROJECT / "asset-source.json").read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory(prefix="atlas-assets-") as temporary:
        folder = Path(temporary).resolve()
        archive = folder / "resources.zip"
        digest = hashlib.sha256()
        request = urllib.request.Request(
            source["url"], headers={"User-Agent": "PW-Resource-Atlas-Build"}
        )
        with urllib.request.urlopen(request, timeout=180) as response, archive.open("wb") as output:
            while block := response.read(1024 * 1024):
                digest.update(block)
                output.write(block)
        if digest.hexdigest() != source["sha256"]:
            raise ValueError("Контрольная сумма ресурсов не совпадает.")
        with zipfile.ZipFile(archive) as package:
            prefix = "_internal/assets/"
            for member in package.infolist():
                if member.is_dir() or not member.filename.startswith(prefix):
                    continue
                path = folder / member.filename
                if not path.resolve().is_relative_to(folder / "_internal/assets") or stat.S_ISLNK(
                    member.external_attr >> 16
                ):
                    raise ValueError("Недопустимый путь в архиве ресурсов.")
                path.parent.mkdir(parents=True, exist_ok=True)
                with package.open(member) as incoming, path.open("wb") as output:
                    shutil.copyfileobj(incoming, output)
        assets = folder / "_internal/assets"
        if not (assets / "resources.json").is_file():
            raise ValueError("В пакете нет ресурсов атласа.")
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(assets, destination, dirs_exist_ok=True)
    print("Ресурсы загружены и проверены.", flush=True)


if __name__ == "__main__":
    fetch(PROJECT / ".cache/assets")
