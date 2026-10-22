from pathlib import Path
from contextlib import contextmanager
import ctypes
import hashlib
import io
import json
import os
import sys
import tempfile
import zipfile
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import fetch_assets


def archive(extra=None):
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as package:
        package.writestr("_internal/assets/resources.json", "[]")
        package.writestr("settings.json", "must not be extracted")
        if extra:
            package.writestr(extra, "outside")
    return data.getvalue()


with tempfile.TemporaryDirectory(prefix="atlas bootstrap spaces ") as temporary:
    fixture = Path(temporary)
    staging = fixture / "Staging with spaces"
    staging.mkdir()
    short = str(staging)
    if os.name == "nt":
        result = ctypes.create_unicode_buffer(32768)
        if ctypes.windll.kernel32.GetShortPathNameW(str(staging), result, len(result)):
            short = result.value

    @contextmanager
    def temporary_staging(**_):
        yield short

    for index, (extra, wrong_hash) in enumerate(
        [(None, False), ("_internal/assets/../../outside.bin", False), (None, True)]
    ):
        data = archive(extra)
        (fixture / "asset-source.json").write_text(
            json.dumps(
                {
                    "url": "https://github.com/fixture.zip",
                    "sha256": "0" * 64 if wrong_hash else hashlib.sha256(data).hexdigest(),
                }
            )
        )
        destination = fixture / f"assets-{index}"
        with (
            patch.object(fetch_assets, "PROJECT", fixture),
            patch.object(fetch_assets.tempfile, "TemporaryDirectory", temporary_staging),
            patch.object(fetch_assets.urllib.request, "urlopen", return_value=io.BytesIO(data)),
        ):
            try:
                fetch_assets.fetch(destination)
            except ValueError:
                assert extra or wrong_hash
                assert not destination.exists()
            else:
                assert not extra and not wrong_hash
                assert (destination / "resources.json").read_text() == "[]"
                assert not (destination / "settings.json").exists()
print(
    "PASS: build asset bootstrap accepts Windows short paths; rejects bad hashes and path traversal"
)
