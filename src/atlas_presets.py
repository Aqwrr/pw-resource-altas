"""Collection sets and personal presets; no game or map changes on selection."""

import json
from pathlib import Path
from uuid import uuid4
from atlas_core import read_json, write_json, ASSETS


def builtin_presets(resources):
    by_id = {r["id"]: r for r in resources}
    result = []
    data = read_json(ASSETS / "collection-presets.json", {})
    if data.get("format") != 1:
        raise ValueError("Не удалось прочитать встроенные наборы сбора.")
    for entry in data["presets"]:
        row = dict(entry)
        row["selected"] = [by_id[item["item_id"]]["key"] for item in row["requirements"]]
        row["details"] = "\n".join(
            f"{by_id[item['item_id']]['name']} — {item['quantity']} шт."
            for item in row["requirements"]
        )
        result.append(row)
    for tier in (1, 2, 3, 4, 5, 0):
        selected = [
            r["key"] for r in resources if r["kind"] != "herb" and (not tier or r["tier"] == tier)
        ]
        result.append(
            {
                "id": f"craft_{tier}",
                "name": f"Крафт · Т{tier}" if tier else "Крафт · все материалы",
                "group": "Крафт",
                "selected": selected,
                "note": "Древесина, руда, камень и уголь"
                + (f" Т{tier}." if tier else " всех тиров."),
                "details": "\n".join(r["name"] for r in resources if r["key"] in selected),
            }
        )
    return result


def clean_name(name):
    name = " ".join(name.split())
    if not name:
        raise ValueError("Введите название набора.")
    if len(name) > 60:
        raise ValueError("Название должно быть не длиннее 60 символов.")
    if any(ord(ch) < 32 for ch in name):
        raise ValueError("В названии есть недопустимые символы.")
    return name


class PresetStore:
    def __init__(self, path):
        self.path = Path(path)
        self.presets = []
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf8"))
            if data.get("format") != 1 or not isinstance(data.get("presets"), list):
                raise ValueError()
            ids = set()
            names = set()
            for row in data["presets"]:
                if (
                    not isinstance(row["id"], str)
                    or not row["id"].startswith("user_")
                    or row["id"] in ids
                ):
                    raise ValueError()
                name = clean_name(row["name"])
                keys = row["selected"]
                if (
                    name.casefold() in names
                    or not isinstance(keys, list)
                    or not keys
                    or not all(isinstance(k, str) and k for k in keys)
                ):
                    raise ValueError()
                ids.add(row["id"])
                names.add(name.casefold())
                self.presets.append({"id": row["id"], "name": name, "selected": sorted(set(keys))})
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
            raise ValueError(
                "Не удалось прочитать presets.json. Файл сохранён без изменений; исправьте его или восстановите копию."
            ) from error

    def find(self, preset_id):
        return next((row for row in self.presets if row["id"] == preset_id), None)

    def save(self, name, selected, preset_id=None):
        name = clean_name(name)
        keys = sorted(set(selected))
        if not keys or not all(isinstance(k, str) and k for k in keys):
            raise ValueError("Сначала выберите хотя бы один ресурс.")
        if preset_id is not None and not self.find(preset_id):
            raise ValueError("Набор уже удалён.")
        if any(
            row["name"].casefold() == name.casefold() and row["id"] != preset_id
            for row in self.presets
        ):
            raise ValueError("Набор с таким названием уже существует.")
        row = {"id": preset_id or "user_" + uuid4().hex, "name": name, "selected": keys}
        rows = (
            [row if old["id"] == preset_id else old for old in self.presets]
            if preset_id
            else self.presets + [row]
        )
        self._write(rows)
        return row

    def rename(self, preset_id, name):
        row = self.find(preset_id)
        if row is None:
            raise ValueError("Набор уже удалён.")
        return self.save(name, row["selected"], preset_id)

    def delete(self, preset_id):
        if self.find(preset_id) is None:
            raise ValueError("Набор уже удалён.")
        self._write([row for row in self.presets if row["id"] != preset_id])

    def _write(self, rows):
        write_json(self.path, {"format": 1, "presets": rows})
        self.presets = rows
