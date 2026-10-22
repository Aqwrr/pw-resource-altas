"""Selection-driven, reversible model-owned beacons for materials and herbs.

The v18 attachment layout is checked against this client's loader. Shared herb
models get separate ECM aliases and fixed-width model paths in elements.data.
"""

from pathlib import Path
import hashlib
import json
import os
import shutil
import struct
import zlib
from datetime import datetime
import atlas_core as core
from atlas_pck import FOOTER_DISTANCE, OFFSET_KEY, LENGTH_KEY_1, LENGTH_KEY_2

PART_SIZE = 2147483392
FILES = ("models.pck", "models.pkx")
FILTER_FILES = FILES + ("gamedata.pck",)


class ModelArchive:
    """The inspected two-part PCK; archive offsets are unsigned, across both files."""

    def __init__(self, path, part_size=PART_SIZE):
        self.path = Path(path)
        self.part_size = part_size
        self.paths = [self.path, self.path.with_suffix(".pkx")]
        if self.path.with_suffix(".pkx1").exists():
            raise ValueError(
                "Архив моделей имеет больше двух частей. Этот вариант пока не поддерживается."
            )
        sizes = [p.stat().st_size for p in self.paths]
        if sizes[0] != part_size or not sizes[1]:
            raise ValueError("Изменился формат частей models.pck/models.pkx.")
        self.total = sum(sizes)
        header = self.read_at(0, 12)
        magic, self.logical, guard = struct.unpack("<III", header)
        if (magic, guard) != (
            0x4DCA23EF,
            0x56A089B7,
        ) or not FOOTER_DISTANCE < self.logical <= self.total:
            raise ValueError("Неизвестный заголовок models.pck.")
        self.count, self.version = struct.unpack("<II", self.read_at(self.logical - 8, 8))
        if self.version != 0x20002 or not 0 < self.count < 100000:
            raise ValueError("Неизвестная версия архива моделей.")
        self.footer_position = self.logical - FOOTER_DISTANCE
        footer = self.read_at(self.footer_position, 272)
        if (
            struct.unpack_from("<I", footer)[0] != 0xFDFDFEEE
            or struct.unpack_from("<I", footer, 268)[0] != 0xF00DBEEF
        ):
            raise ValueError("Неизвестный вариант таблицы моделей.")
        self.table = struct.unpack_from("<I", footer, 8)[0] ^ OFFSET_KEY
        if not 12 < self.table < self.footer_position:
            raise ValueError("Повреждена таблица моделей.")
        blob = self.read_at(self.table, self.footer_position - self.table)
        cursor = 0
        self.entries = {}
        for _ in range(self.count):
            one, two = struct.unpack_from("<II", blob, cursor)
            cursor += 8
            length = one ^ LENGTH_KEY_1
            if length != two ^ LENGTH_KEY_2 or not 0 < length <= 276:
                raise ValueError("Повреждена запись таблицы моделей.")
            packed = blob[cursor : cursor + length]
            cursor += length
            raw = zlib.decompress(packed) if length < 276 else packed
            if len(raw) not in (272, 276):
                raise ValueError("Неизвестная длина записи модели.")
            key = raw[:260].split(b"\0")[0].decode("gb18030").replace("/", "\\").lower()
            offset, size, compressed = struct.unpack_from("<III", raw, 260)
            if key in self.entries or offset + compressed > self.table or compressed > size:
                raise ValueError("Повреждена запись модели: " + key)
            self.entries[key] = {
                "raw": raw,
                "offset": offset,
                "size": size,
                "compressed": compressed,
            }
        if cursor != len(blob):
            raise ValueError("Размер таблицы моделей не совпадает с заголовком.")
        self.suffix = self.read_at(self.footer_position, self.logical - self.footer_position)
        self.trailing = self.read_at(self.logical, self.total - self.logical)

    def read_at(self, offset, size):
        if offset < 0 or size < 0 or offset + size > self.total:
            raise ValueError("Чтение за границей архива.")
        result = bytearray()
        while size:
            part = 0 if offset < self.part_size else 1
            local = offset if not part else offset - self.part_size
            take = min(size, self.part_size - offset) if not part else size
            with self.paths[part].open("rb") as file:
                file.seek(local)
                data = file.read(take)
            if len(data) != take:
                raise ValueError("Обрыв части архива моделей.")
            result.extend(data)
            offset += take
            size -= take
        return bytes(result)

    def read(self, name):
        row = self.entries[name.replace("/", "\\").lower()]
        data = self.read_at(row["offset"], row["compressed"])
        data = zlib.decompress(data) if row["compressed"] < row["size"] else data
        if len(data) != row["size"]:
            raise ValueError("Повреждён файл модели: " + name)
        return data

    def replace(self, replacements, directory, additions=None):
        additions = additions or {}
        directory = Path(directory)
        if directory.resolve() == self.path.parent.resolve():
            raise ValueError("Нельзя собирать тест прямо в исходный архив.")
        if not (replacements or additions) or not set(replacements) <= set(self.entries):
            raise ValueError("В архиве не найдены модели ресурсов.")
        if set(additions) & set(self.entries):
            raise ValueError("Имя отдельной модели уже занято.")
        directory.mkdir(parents=True, exist_ok=True)
        dest = directory / "models.pck"
        entries = {key: dict(row) for key, row in self.entries.items()}
        for key, (source, data) in additions.items():
            if (
                source not in self.entries
                or not key.startswith("models\\atlas_beacons\\")
                or len(key.encode("gb18030")) >= 260
            ):
                raise ValueError("Некорректная отдельная модель.")
            raw = bytearray(self.entries[source]["raw"])
            raw[:260] = key.encode("gb18030").ljust(260, b"\0")
            entries[key] = {"raw": bytes(raw)}
        payloads = {**replacements, **{key: value[1] for key, value in additions.items()}}
        for source, name in zip(self.paths, FILES):
            shutil.copyfile(source, directory / name)
        with (directory / "models.pkx").open("ab") as file:
            for key, data in payloads.items():
                packed = zlib.compress(data, 6)
                if len(packed) >= len(data):
                    packed = data
                offset = self.part_size + file.tell()
                file.write(packed)
                raw = bytearray(entries[key]["raw"])
                struct.pack_into("<III", raw, 260, offset, len(data), len(packed))
                if len(raw) == 276:
                    struct.pack_into("<I", raw, 272, 0)
                entries[key]["raw"] = bytes(raw)
            table = self.part_size + file.tell()
            for row in entries.values():
                raw = row["raw"]
                packed = zlib.compress(raw, 6)
                if len(packed) >= len(raw):
                    packed = raw.ljust(276, b"\0")
                size = len(packed)
                file.write(struct.pack("<II", size ^ LENGTH_KEY_1, size ^ LENGTH_KEY_2))
                file.write(packed)
            suffix = bytearray(self.suffix)
            struct.pack_into("<I", suffix, 8, table ^ OFFSET_KEY)
            struct.pack_into("<I", suffix, len(suffix) - 8, len(entries))
            file.write(suffix)
            logical = self.part_size + file.tell()
            if logical > 0xFFFFFFFF:
                raise ValueError("Архив моделей превышает допустимый размер.")
            file.write(self.trailing)
            file.flush()
            os.fsync(file.fileno())
        with dest.open("r+b") as file:
            file.seek(4)
            file.write(struct.pack("<I", logical))
            file.flush()
            os.fsync(file.fileno())
        check = ModelArchive(dest, self.part_size)
        if set(check.entries) != set(self.entries) | set(additions):
            raise ValueError("Изменился набор файлов архива моделей.")
        changed = {
            key for key in self.entries if check.entries[key]["raw"] != self.entries[key]["raw"]
        }
        if changed != set(replacements):
            raise ValueError("Изменены посторонние модели.")
        for key, data in payloads.items():
            if check.read(key) != data:
                raise ValueError("Исходная модель отличается от ожидаемой.")
        return {
            "entries": len(check.entries),
            "changed_models": sorted(changed),
            "added_models": sorted(additions),
            "logical_size": logical,
            "part_sizes": [p.stat().st_size for p in check.paths],
        }


def glowing_ecm(data, fx_path, scale=2.5):
    if not data.startswith(b"MOXTVersion: 18\r\n"):
        raise ValueError("Поддерживаются только модели ECM версии 18.")
    marker = b"CoGfxNum: 0\r\nComActCount: 0\r\n"
    if data.count(marker) != 1 or b"FxFilePath:" in data:
        raise ValueError("В модели уже есть эффекты или другой формат действий.")
    # v18: no TimeSpan (v20+), HookRot (v19+) or GfxAlpha (v22/v24+).
    block = "\r\n".join(
        (
            "CoGfxNum: 1",
            "ComActCount: 0",
            "EventType: 100",
            "StartTime: 0",
            "Once: 0",
            "FxFilePath: " + fx_path,
            "HookName: ",
            "HookOffset: 0.000000, 0.750000, 0.000000",
            "HookYaw: 0.000000",
            "HookPitch: 0.000000",
            "BindParent: 1",
            "FadeOut: 0",
            "UseModelAlpha: 1",
            f"GfxScale: {scale:.6f}",
            "GfxSpeed: 1.000000",
            "GfxParamCount: 0",
            "",
        )
    ).encode("gb18030")
    return data.replace(marker, block)


def feature_root():
    # Keep the original directory so existing installation journals and backups remain valid.
    return core.ROOT / "glow-test"


def journal_path():
    return feature_root() / "installed.json"


def load_state():
    path = journal_path()
    if not path.exists():
        return None
    try:
        state = json.loads(path.read_text(encoding="utf8"))
        if (state["format"], set(state["files"])) not in ((1, set(FILES)), (2, set(FILTER_FILES))):
            raise ValueError()
        for name, row in state["files"].items():
            backup = Path(row["backup"]).resolve()
            if (
                not backup.is_relative_to((feature_root() / "backups").resolve())
                or backup.name != name
            ):
                raise ValueError()
            if any(len(row[field]) != 64 for field in ("original_sha256", "installed_sha256")):
                raise ValueError()
            if "previous_sha256" in row and len(row["previous_sha256"]) != 64:
                raise ValueError()
        return state
    except (OSError, ValueError, TypeError, KeyError) as error:
        raise ValueError(
            "Повреждён журнал маяков. Резервные копии сохранены в glow-test/backups."
        ) from error


def verify_parser(client, config):
    exe = Path(client) / "element/ElementClient.exe"
    with exe.open("rb") as file:
        for block in config["parser_blocks"]:
            file.seek(block["offset"])
            data = file.read(block["size"])
            if hashlib.sha256(data).hexdigest() != block["sha256"]:
                raise ValueError(
                    "Загрузчик моделей этого клиента отличается от проверенного. Маяки не установлены."
                )


def build_beacons(client, progress=lambda value: None, selected=None):
    core.atlas_access.require_activated(core.ROOT)
    client = Path(client).resolve()
    config = core.read_json(core.ASSETS / "beacon-resources.json")
    verify_parser(client, config)
    if selected is None:
        selected = core.read_json(core.ROOT / "settings.json", {}).get("selected", [])
    selected = set(selected)
    known = {row["key"] for row in config["models"]}
    if not selected or not selected <= known:
        raise ValueError("Выберите известные материалы или травы для маяков.")
    state = load_state()
    source = client / "element"
    progress(2)
    current = {name: core.digest(source / name) for name in FILTER_FILES}
    sources = {name: source / name for name in FILTER_FILES}
    if state:
        if Path(state["client"]).resolve() != client:
            raise ValueError("Сначала уберите тест из прежней папки клиента.")
        for name, row in state["files"].items():
            if current[name] not in (
                row["original_sha256"],
                row["installed_sha256"],
                row.get("previous_sha256"),
            ):
                raise ValueError(
                    "Клиент изменён после установки теста: " + name + ". Подсветка не перезаписана."
                )
            if core.digest(row["backup"]) != row["original_sha256"]:
                raise ValueError("Изменена резервная копия: " + name)
        sources.update({name: Path(row["backup"]) for name, row in state["files"].items()})
    progress(12)
    archive = ModelArchive(sources["models.pck"])
    replacements = {}
    additions = {}
    from atlas_pck import Archive

    effects = Archive(client / "element/gfx.pck")
    fx = "gfx\\" + config["fx_path"]
    if hashlib.sha256(effects.read(fx)).hexdigest() != config["fx_sha256"]:
        raise ValueError("Родной эффект клиента отличается от проверенного.")
    gamedata = Archive(sources["gamedata.pck"])
    elements = gamedata.read("gamedata/elements.data")
    updated = bytearray(elements)
    aliases = []
    for row in config["models"]:
        if row["key"] not in selected:
            continue
        data = archive.read(row["path"])
        if hashlib.sha256(data).hexdigest() != row["sha256"]:
            raise ValueError("Модель ресурса отличается от проверенной: " + row["name"])
        modified = glowing_ecm(data, config["fx_path"], config["scale"])
        if row.get("alias_path"):
            offset = row["mine_offset"]
            name = elements[offset + 8 : offset + 72].decode("utf-16le").split("\0")[0]
            path = elements[offset + 104 : offset + 232].split(b"\0")[0].decode("gb18030").lower()
            if (
                int.from_bytes(elements[offset : offset + 4], "little") != row["mine_id"]
                or name != row["mine_name"]
                or path != row["path"]
            ):
                raise ValueError("Запись травы отличается от проверенной: " + row["name"])
            encoded = row["alias_path"].encode("gb18030")
            if len(encoded) >= 128:
                raise ValueError("Слишком длинный путь отдельной модели.")
            updated[offset + 104 : offset + 232] = encoded.ljust(128, b"\0")
            additions[row["alias_path"]] = (row["path"], modified)
            aliases.append(
                {"key": row["key"], "offset": offset + 104, "bytes": 128, "path": row["alias_path"]}
            )
        else:
            replacements[row["path"]] = modified
    progress(25)
    prepared = feature_root() / "prepared"
    (prepared / "manifest.json").unlink(missing_ok=True)
    check = archive.replace(replacements, prepared, additions)
    progress(60)
    if aliases:
        edited = prepared / "elements-selected.data"
        edited.write_bytes(updated)
        gamedata.replace({"gamedata\\elements.data": edited}, prepared / "gamedata.pck")
    else:
        shutil.copyfile(sources["gamedata.pck"], prepared / "gamedata.pck")
    progress(65)
    manifest = {
        "format": 2,
        "client": str(client),
        "created": datetime.now().astimezone().isoformat(),
        "resource_keys": sorted(selected),
        "profile": config.get("profile"),
        "aliases": aliases,
        "fx_path": config["fx_path"],
        "check": check,
        "files": {
            name: {
                "original_sha256": state["files"][name]["original_sha256"]
                if state and name in state["files"]
                else current[name],
                "installed_sha256": core.digest(prepared / name),
                "expected_current_sha256": current[name],
            }
            for name in FILTER_FILES
        },
    }
    core.write_json(prepared / "manifest.json", manifest)
    progress(75)
    return manifest


def _stopped():
    if core.game_running():
        raise ValueError("Полностью закройте игру перед установкой или удалением маяков.")


def _commit_files(client, sources, expected):
    """Stage both files on the game volume, then replace them; undo on failure."""
    names = tuple(sources)
    element = Path(client) / "element"
    changed = []
    created = []
    temporary = {name: element / (name + ".atlas-glow-new") for name in names}
    previous = {name: element / (name + ".atlas-glow-previous") for name in names}
    try:
        for name in names:
            if temporary[name].exists() or previous[name].exists():
                raise ValueError(
                    "Остались файлы прерванной установки подсветки: " + name + ".atlas-glow-*"
                )
        for name in names:
            created.append(temporary[name])
            shutil.copyfile(sources[name], temporary[name])
            if core.digest(temporary[name]) != core.digest(sources[name]):
                raise ValueError("Ошибка копирования: " + name)
        _stopped()
        for name in names:
            if core.digest(element / name) != expected[name]:
                raise ValueError("Файл изменился во время сборки: " + name)
        for name in names:
            os.replace(element / name, previous[name])
            changed.append(name)
            os.replace(temporary[name], element / name)
    except Exception:
        for name in reversed(changed):
            if previous[name].exists():
                os.replace(previous[name], element / name)
        raise
    finally:
        for path in created:
            path.unlink(missing_ok=True)
    for path in previous.values():
        path.unlink(missing_ok=True)


def _recover_interrupted(state):
    """Recover our own interrupted rename, never overwrite unknown external data."""
    element = Path(state["client"]) / "element"
    pending = [
        element / (name + suffix)
        for name in state["files"]
        for suffix in (".atlas-glow-new", ".atlas-glow-previous")
    ]
    if not any(path.exists() for path in pending):
        return
    _stopped()
    for name, row in state["files"].items():
        allowed = {row["original_sha256"], row["installed_sha256"], row.get("previous_sha256")}
        for suffix in ("", ".atlas-glow-new", ".atlas-glow-previous"):
            path = element / (name + suffix)
            if path.exists() and core.digest(path) not in allowed:
                raise ValueError("Неизвестный файл при восстановлении теста: " + path.name)
    for name in state["files"]:
        previous = element / (name + ".atlas-glow-previous")
        if previous.exists():
            os.replace(previous, element / name)
        (element / (name + ".atlas-glow-new")).unlink(missing_ok=True)


def install_beacons(client, progress=lambda value: None):
    core.atlas_access.require_activated(core.ROOT)
    _stopped()
    client = Path(client).resolve()
    state = load_state()
    if state:
        if Path(state["client"]).resolve() != client:
            raise ValueError("Маяки уже установлены в другой клиент.")
        _recover_interrupted(state)
    prepared = feature_root() / "prepared"
    manifest = core.read_json(prepared / "manifest.json")
    if not manifest or Path(manifest["client"]).resolve() != client:
        manifest = build_beacons(client, progress)
    if (manifest.get("format"), set(manifest.get("files", {}))) not in (
        (1, set(FILES)),
        (2, set(FILTER_FILES)),
    ):
        raise ValueError("Некорректный набор файлов маяков. Пересоберите его.")
    for name, row in manifest["files"].items():
        if core.digest(prepared / name) != row["installed_sha256"]:
            raise ValueError("Изменились подготовленные файлы подсветки. Соберите тест заново.")
        if core.digest(client / "element" / name) != row["expected_current_sha256"]:
            raise ValueError("Клиент изменился после сборки теста. Соберите тест заново.")
    state = load_state()
    backups = feature_root() / "backups"
    backups.mkdir(parents=True, exist_ok=True)
    if state and Path(state["client"]).resolve() != client:
        raise ValueError("Маяки уже установлены в другой клиент.")
    for name, row in manifest["files"].items():
        backup = backups / name
        if backup.exists():
            if core.digest(backup) != row["original_sha256"]:
                raise ValueError("Резервная копия относится к другому клиенту: " + name)
        else:
            source = client / "element" / name
            if core.digest(source) != row["original_sha256"]:
                raise ValueError("Нельзя сохранить изменённый архив вместо оригинала.")
            shutil.copyfile(source, backup)
            if core.digest(backup) != row["original_sha256"]:
                raise ValueError("Не удалось проверить резервную копию: " + name)
    previous_state = state
    state = {
        "format": manifest["format"],
        "client": str(client),
        "status": "installing",
        "resource_keys": manifest["resource_keys"],
        "profile": manifest.get("profile"),
        "files": {
            name: {
                "backup": str((backups / name).resolve()),
                "original_sha256": row["original_sha256"],
                "installed_sha256": row["installed_sha256"],
                "previous_sha256": row["expected_current_sha256"],
            }
            for name, row in manifest["files"].items()
        },
    }
    core.write_json(journal_path(), state)
    progress(82)
    try:
        _commit_files(
            client,
            {name: prepared / name for name in manifest["files"]},
            {name: row["expected_current_sha256"] for name, row in manifest["files"].items()},
        )
    except Exception:
        if previous_state:
            core.write_json(journal_path(), previous_state)
        else:
            journal_path().unlink(missing_ok=True)
        raise
    state["status"] = "installed"
    core.write_json(journal_path(), state)
    progress(100)
    return state


def remove_beacons(progress=lambda value: None):
    core.atlas_access.require_activated(core.ROOT)
    state = load_state()
    if not state:
        return False
    _stopped()
    _recover_interrupted(state)
    client = Path(state["client"])
    expected = {}
    for name, row in state["files"].items():
        expected[name] = core.digest(client / "element" / name)
        if expected[name] not in (
            row["original_sha256"],
            row["installed_sha256"],
            row.get("previous_sha256"),
        ):
            raise ValueError(
                "Клиент изменён после установки теста: "
                + name
                + ". Откат остановлен, чтобы сохранить обновление."
            )
        if core.digest(row["backup"]) != row["original_sha256"]:
            raise ValueError("Повреждена резервная копия: " + name)
    progress(20)
    _commit_files(
        client, {name: Path(row["backup"]) for name, row in state["files"].items()}, expected
    )
    if any(
        core.digest(client / "element" / name) != row["original_sha256"]
        for name, row in state["files"].items()
    ):
        raise ValueError("Не прошла проверка восстановления моделей.")
    state["status"] = "removed"
    core.write_json(feature_root() / "last-removed.json", state)
    journal_path().unlink()
    progress(100)
    return True
