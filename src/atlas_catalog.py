"""Versioned, UI-independent repository for future DQ and mold drop search.

Probabilities and server verification are explicit source data, never inferred.
An empty bundled catalog is valid; importing tested data needs no UI rewrite.
"""

import json
import sqlite3
import math
from pathlib import Path

SCHEMA_VERSION = 1
KINDS = {"dq", "form", "material", "herb", "other"}
SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE sources(id TEXT PRIMARY KEY,url TEXT NOT NULL,server TEXT NOT NULL,version TEXT NOT NULL,verified INTEGER NOT NULL CHECK(verified IN(0,1)));
CREATE TABLE items(id INTEGER PRIMARY KEY,name TEXT NOT NULL,normalized TEXT NOT NULL,kind TEXT NOT NULL CHECK(kind IN('dq','form','material','herb','other')),level INTEGER);
CREATE INDEX item_search ON items(kind,normalized);
CREATE TABLE dungeons(id TEXT PRIMARY KEY,name TEXT NOT NULL,world TEXT NOT NULL);
CREATE TABLE monsters(id INTEGER PRIMARY KEY,name TEXT NOT NULL,normalized TEXT NOT NULL,level INTEGER,dungeon_id TEXT REFERENCES dungeons(id));
CREATE INDEX monster_search ON monsters(normalized);
CREATE TABLE spawns(id INTEGER PRIMARY KEY,monster_id INTEGER NOT NULL REFERENCES monsters(id),world TEXT NOT NULL,x REAL NOT NULL,y REAL NOT NULL,source_id TEXT NOT NULL REFERENCES sources(id));
CREATE TABLE drops(monster_id INTEGER NOT NULL REFERENCES monsters(id),item_id INTEGER NOT NULL REFERENCES items(id),probability REAL CHECK(probability>=0 AND probability<=1),source_id TEXT NOT NULL REFERENCES sources(id),PRIMARY KEY(monster_id,item_id,source_id));
CREATE INDEX item_sources ON drops(item_id);
"""


def normalize(value):
    return str(value).casefold().replace("ё", "е").strip()


class CatalogRepository:
    def __init__(self):
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)

    @classmethod
    def from_file(cls, path):
        repo = cls()
        repo.import_bundle(json.loads(Path(path).read_text(encoding="utf8")))
        return repo

    def close(self):
        self.db.close()

    def import_bundle(self, bundle):
        if bundle.get("schema_version") != SCHEMA_VERSION:
            raise ValueError("Неподдерживаемая версия справочника")
        # Foreign-key errors, malformed probabilities and duplicate IDs roll
        # back the complete import, including all preceding table writes.
        with self.db:
            for s in bundle.get("sources", []):
                if not isinstance(s.get("verified", False), bool):
                    raise ValueError("verified должен быть логическим значением")
                self.db.execute(
                    "INSERT INTO sources VALUES(?,?,?,?,?)",
                    (s["id"], s["url"], s["server"], s["version"], int(s.get("verified", False))),
                )
            for i in bundle.get("items", []):
                self.db.execute(
                    "INSERT INTO items VALUES(?,?,?,?,?)",
                    (i["id"], i["name"], normalize(i["name"]), i["kind"], i.get("level")),
                )
            for d in bundle.get("dungeons", []):
                self.db.execute(
                    "INSERT INTO dungeons VALUES(?,?,?)", (d["id"], d["name"], d["world"])
                )
            for m in bundle.get("monsters", []):
                self.db.execute(
                    "INSERT INTO monsters VALUES(?,?,?,?,?)",
                    (m["id"], m["name"], normalize(m["name"]), m.get("level"), m.get("dungeon_id")),
                )
            for s in bundle.get("spawns", []):
                self.db.execute(
                    "INSERT INTO spawns(monster_id,world,x,y,source_id) VALUES(?,?,?,?,?)",
                    (s["monster_id"], s["world"], s["x"], s["y"], s["source_id"]),
                )
            for d in bundle.get("drops", []):
                probability = d.get("probability")
                if probability is not None and (
                    isinstance(probability, bool)
                    or not isinstance(probability, (int, float))
                    or not math.isfinite(probability)
                    or not 0 <= probability <= 1
                ):
                    raise ValueError("Шанс должен быть числом от 0 до 1 или null")
                self.db.execute(
                    "INSERT INTO drops VALUES(?,?,?,?)",
                    (d["monster_id"], d["item_id"], d.get("probability"), d["source_id"]),
                )

    def search_items(self, query="", kind=None):
        if kind is not None and kind not in KINDS:
            raise ValueError("Неизвестный тип предмета")
        text = normalize(query).replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        rows = self.db.execute(
            "SELECT id,name,kind,level FROM items WHERE normalized LIKE ? ESCAPE '\\' AND (? IS NULL OR kind=?) ORDER BY normalized,id",
            ("%" + text + "%", kind, kind),
        )
        return [dict(r) for r in rows]

    def item_sources(self, item_id):
        rows = self.db.execute(
            """SELECT m.id AS monster_id,m.name AS monster_name,m.level,d.id AS dungeon_id,d.name AS dungeon_name,l.probability,s.url,s.server,s.version,s.verified
        FROM drops l JOIN monsters m ON m.id=l.monster_id LEFT JOIN dungeons d ON d.id=m.dungeon_id JOIN sources s ON s.id=l.source_id WHERE l.item_id=? ORDER BY m.level,m.name""",
            (item_id,),
        )
        return [dict(r) for r in rows]

    def drops_from_monster(self, monster_id, kind=None):
        rows = self.db.execute(
            """SELECT i.id,i.name,i.kind,l.probability,s.url,s.server,s.version,s.verified FROM drops l JOIN items i ON i.id=l.item_id JOIN sources s ON s.id=l.source_id WHERE l.monster_id=? AND (? IS NULL OR i.kind=?) ORDER BY i.normalized""",
            (monster_id, kind, kind),
        )
        return [dict(r) for r in rows]

    def search_monsters(self, query=""):
        text = normalize(query).replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        return [
            dict(r)
            for r in self.db.execute(
                "SELECT id,name,level,dungeon_id FROM monsters WHERE normalized LIKE ? ESCAPE '\\' ORDER BY normalized",
                ("%" + text + "%",),
            )
        ]

    def list_dungeons(self):
        return [
            dict(r) for r in self.db.execute("SELECT id,name,world FROM dungeons ORDER BY name")
        ]

    def forms_from_dungeon(self, dungeon_id):
        rows = self.db.execute(
            """SELECT i.id,i.name,m.id AS monster_id,m.name AS monster_name,l.probability,s.url,s.server,s.version,s.verified FROM drops l JOIN items i ON i.id=l.item_id JOIN monsters m ON m.id=l.monster_id JOIN sources s ON s.id=l.source_id WHERE m.dungeon_id=? AND i.kind='form' ORDER BY i.normalized,m.name""",
            (dungeon_id,),
        )
        return [dict(r) for r in rows]

    def monster_locations(self, monster_id):
        return [
            dict(r)
            for r in self.db.execute(
                "SELECT world,x,y,source_id FROM spawns WHERE monster_id=?", (monster_id,)
            )
        ]
