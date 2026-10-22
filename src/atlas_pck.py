"""Reader/writer for the archive variant used by the inspected Comeback 1.3.6 client.

Preserves all original archive bytes except the four-byte logical size, then
appends replacement assets and a new index in the original archive format.
No executable changes or client-check suppression are performed.
"""

from pathlib import Path
import os
import struct
import zlib
import shutil

FOOTER_DISTANCE = 0x9E82
OFFSET_KEY = 0x9A4E1CB0
LENGTH_KEY_1 = 0x1597270A
LENGTH_KEY_2 = 0x604E0ECB


class Archive:
    def __init__(self, path):
        self.path = Path(path)
        physical = self.path.stat().st_size
        with self.path.open("rb") as f:
            self.header = f.read(12)
            if len(self.header) != 12:
                raise ValueError("Короткий заголовок PCK")
            a, self.logical, b = struct.unpack("<III", self.header)
            if (a, b) != (0x4DCA23EF, 0x56A089B7) or not FOOTER_DISTANCE < self.logical <= physical:
                raise ValueError("Формат архива изменился: требуется адаптация сборщика")
            f.seek(self.logical - 8)
            self.count, self.version = struct.unpack("<II", f.read(8))
            if self.version != 0x20002 or not 0 < self.count < 100000:
                raise ValueError("Неизвестная версия архива")
            self.footer_position = self.logical - FOOTER_DISTANCE
            f.seek(self.footer_position)
            self.footer = f.read(272)
            if (
                struct.unpack_from("<I", self.footer)[0] != 0xFDFDFEEE
                or struct.unpack_from("<I", self.footer, 268)[0] != 0xF00DBEEF
            ):
                raise ValueError("Неизвестный вариант архива. Исходные файлы не изменены.")
            self.table = struct.unpack_from("<I", self.footer, 8)[0] ^ OFFSET_KEY
            if not 12 < self.table < self.footer_position:
                raise ValueError("Неизвестная таблица архива")
            self.entries = {}
            f.seek(self.table)
            for i in range(self.count):
                lengths = f.read(8)
                if len(lengths) != 8:
                    raise ValueError("Обрыв таблицы PCK")
                x, y = struct.unpack("<II", lengths)
                length = x ^ LENGTH_KEY_1
                if length != (y ^ LENGTH_KEY_2) or not 0 < length <= 276:
                    raise ValueError("Неподдерживаемая запись PCK")
                data = f.read(length)
                raw = zlib.decompress(data) if length < 276 else data
                if len(raw) not in (272, 276):
                    raise ValueError("Неподдерживаемая длина записи PCK")
                name = raw[:260].split(b"\0")[0].decode("gb18030")
                offset, size, compressed = struct.unpack_from("<III", raw, 260)
                if offset + compressed > self.table or compressed > size:
                    raise ValueError("Повреждённая запись PCK")
                key = name.replace("/", "\\").lower()
                if key in self.entries:
                    raise ValueError("Повтор пути в таблице PCK")
                self.entries[key] = {
                    "name": name,
                    "raw": raw,
                    "offset": offset,
                    "size": size,
                    "compressed": compressed,
                }
            if f.tell() != self.footer_position:
                raise ValueError("Таблица PCK не совпадает с заголовком")
            self.suffix = f.read(self.logical - self.footer_position)
            self.trailing = f.read()

    def read(self, name):
        e = self.entries[name.replace("/", "\\").lower()]
        with self.path.open("rb") as f:
            f.seek(e["offset"])
            data = f.read(e["compressed"])
        return zlib.decompress(data) if e["compressed"] < e["size"] else data

    def replace(self, replacements, destination):
        destination = Path(destination)
        if self.path.resolve() == destination.resolve():
            raise ValueError("Сборка в исходный архив запрещена")
        destination.parent.mkdir(parents=True, exist_ok=True)
        tmp = destination.with_suffix(".pck.building")
        entries = {k: dict(v) for k, v in self.entries.items()}
        try:
            with self.path.open("rb") as src, tmp.open("w+b") as out:
                shutil.copyfileobj(src, out, 1 << 20)
                for name, p in replacements.items():
                    key = name.replace("/", "\\").lower()
                    data = Path(p).read_bytes()
                    packed = zlib.compress(data, 6)
                    if len(packed) >= len(data):
                        packed = data
                    offset = out.tell()
                    out.write(packed)
                    raw = bytearray(
                        entries[key]["raw"]
                        if key in entries
                        else key.encode("gb18030").ljust(260, b"\0") + bytes(16)
                    )
                    struct.pack_into("<III", raw, 260, offset, len(data), len(packed))
                    if len(raw) == 276:
                        struct.pack_into("<I", raw, 272, 0)
                    entries[key] = {
                        "name": key,
                        "raw": bytes(raw),
                        "offset": offset,
                        "size": len(data),
                        "compressed": len(packed),
                    }
                table = out.tell()
                for e in entries.values():
                    raw = e["raw"]
                    packed = zlib.compress(raw, 6)
                    if len(packed) >= len(raw):
                        packed = raw.ljust(276, b"\0")
                    n = len(packed)
                    out.write(struct.pack("<II", n ^ LENGTH_KEY_1, n ^ LENGTH_KEY_2))
                    out.write(packed)
                suffix = bytearray(self.suffix)
                struct.pack_into("<I", suffix, 8, table ^ OFFSET_KEY)
                struct.pack_into("<II", suffix, len(suffix) - 8, len(entries), self.version)
                out.write(suffix)
                logical = out.tell()
                out.write(self.trailing)
                if logical >= 2147483392:
                    raise ValueError("Набор превышает допустимый размер односоставного PCK")
                out.seek(4)
                out.write(struct.pack("<I", logical))
                out.flush()
                os.fsync(out.fileno())
            check = Archive(tmp)
            if set(check.entries) != set(entries):
                raise ValueError("Ошибка проверки таблицы собранного PCK")
            # Check every changed texture as decoded by the same file format used by the client.
            for name, p in replacements.items():
                if check.read(name) != Path(p).read_bytes():
                    raise ValueError("Ошибка проверки текстуры в PCK: " + name)
            os.replace(tmp, destination)
        except Exception:
            if tmp.exists():
                tmp.unlink()
            raise
        return {
            "original_entries": len(self.entries),
            "new_entries": len(entries),
            "replaced_assets": len(replacements),
            "archive_size": destination.stat().st_size,
            "format": "Comeback 1.3.6, inspected archive variant 5",
        }
