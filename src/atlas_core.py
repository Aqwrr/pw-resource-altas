"""Offline resource layers and reversible client display changes."""

from pathlib import Path
import csv
import hashlib
import io
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zlib
import atlas_pck
import atlas_client
import atlas_minimap
from atlas_markers import group_nodes, icon_offsets
from atlas_routes import world_routes
from datetime import datetime
from functools import lru_cache
from PIL import Image, ImageDraw, ImageFilter, ImageEnhance

PROJECT = Path(__file__).resolve().parent.parent
ROOT = Path(sys.executable).parent if getattr(sys, "frozen", False) else PROJECT / ".local"
ASSETS = (
    Path(sys._MEIPASS) / "assets"
    if getattr(sys, "frozen", False)
    else Path(os.environ.get("ATLAS_ASSETS_DIR", PROJECT / ".cache/assets"))
)
VERSION = "2.10"
MAP_VERSION = "2.7"
COLORS = {1: "#77ab75", 2: "#58a5b0", 3: "#c39b4d", 4: "#a285c9", 5: "#d48355"}
DEFAULT_CLIENT = None
DYNAMIC_ASSETS = ("surfaces\\iconset\\iconlist_guild.dds", "surfaces\\iconset\\iconlist_guild.txt")
ARCHIVE_PATHS = {"element/surfaces.pck", "element/configs.pck"}
CLIENT_MAP_PATHS = ARCHIVE_PATHS | {"element/ElementClient.exe"}
MINIMAP_LAYOUT = "element/interfaces/map.xml"
INSTALL_PATHS = CLIENT_MAP_PATHS | {MINIMAP_LAYOUT}
ORIGINAL_WORLD = {"a": 11, "b": 11, "ox": 0, "oy": 0, "w": 768, "h": 768}
CLASSIC_CROP = (390, 360, 3740, 4230)
WORLDS = {
    "world": {"id": 1, "name": "Основной мир", "columns": 16, "rows": 22},
    "a21": {"id": 121, "name": "Рай", "columns": 8, "rows": 8},
    "a22": {"id": 122, "name": "Ад", "columns": 8, "rows": 8},
}


def read_json(p, default=None):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def write_json(p, value):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, p)


def resources():
    return read_json(ASSETS / "resources.json", [])


def resource_points(resource, world="world"):
    return resource.get("locations", {}).get(
        world, resource.get("points", []) if world == "world" else []
    )


def resource_count(resource, world=None):
    return (
        len(resource_points(resource, world))
        if world
        else sum(len(resource_points(resource, k)) for k in WORLDS)
    )


def project(x, y, world="world"):
    """Game coordinates to the 4096 x 5632 minimap atlas; world=8192 x 11264."""
    spec = WORLDS[world]
    return (x - 400) * 5 + spec["columns"] * 128, spec["rows"] * 128 - (y - 550) * 5


def unproject(px, py, world="world"):
    spec = WORLDS[world]
    return (px - spec["columns"] * 128) / 5 + 400, (spec["rows"] * 128 - py) / 5 + 550


def world_parameters(style="classic", points=(), route=(), padding=45):
    # The executable confines this fitted projection to a visible ordinary M.
    # The shared map_param.ini and JourneyMap always retain their native values.
    if style == "original":
        return dict(ORIGINAL_WORLD)
    left, top, right, bottom = CLASSIC_CROP
    for x, y in [*points, *route]:
        px, py = project(x, y)
        if 0 <= px < 4096 and 0 <= py < 5632:
            left = min(left, px - padding)
            right = max(right, px + padding)
            top = min(top, py - padding)
            bottom = max(bottom, py + padding)
    extent = max(bottom - top, (right - left) * 0.75)
    scale = round(768 * 5632 / extent)
    return {
        "a": 11,
        "b": 11,
        "ox": round(left + right - 4096),
        "oy": round(5632 - top - bottom),
        "w": scale,
        "h": scale,
    }


def overview_parameters(style, groups, route=(), native=None):
    if style == "original":
        return dict(native or ORIGINAL_WORLD)
    points = [members[0][1:] for members in groups]
    params = world_parameters(style, points, route)
    if not groups:
        return params
    # Projection depends on the point set, never on the user's icon size.
    radius = max(max(group_sprite(members, 36).size) / 2 + 3 for members in groups)
    padding = 45
    for _ in range(8):
        required = math.ceil(radius / (4 * params["w"] / (1024 * params["a"]))) + 1
        if required <= padding:
            break
        padding = required
        params = world_parameters(style, points, route, padding)
    return params


def native_map_parameters(data, world_id=1):
    text = (
        data.decode("utf-16")
        if data.startswith((b"\xff\xfe", b"\xfe\xff"))
        else data.decode("utf-8")
    )
    sections = re.findall(r"(?ms)^\[MapConvertParam\d+\]\r?\n(.*?)(?=^\[|\Z)", text)
    blocks = [
        s
        for s in sections
        if re.search(r"(?m)^id[ \t]*=[ \t]*" + str(int(world_id)) + r"[ \t]*\r?$", s)
    ]
    if len(blocks) != 1:
        raise ValueError("Не найдена единственная штатная настройка карты мира")
    params = {
        key: int(re.search(r"(?m)^" + key + r"[ \t]*=[ \t]*(-?\d+)[ \t]*\r?$", blocks[0])[1])
        for key in ORIGINAL_WORLD
    }
    if any(params[key] <= 0 for key in ("a", "b", "w", "h")):
        raise ValueError("Некорректные штатные параметры карты")
    return params


def native_config_archive(client, state):
    source = client / "element/configs.pck"
    previous = (
        state.get("files", {}).get("element/configs.pck", {})
        if state.get("client") == str(client)
        else {}
    )
    if previous.get("baseline") and (
        digest(source) == previous["sha256"] or archive_assets_match(source, state)
    ):
        baseline = atlas_pck.Archive(baseline_path(previous["baseline"]))
        current = atlas_pck.Archive(source)
        owned = "configs\\map_param.ini"
        if set(baseline.entries) == set(current.entries) and all(
            baseline.entries[k]["raw"] == current.entries[k]["raw"]
            for k in baseline.entries
            if k != owned
        ):
            source = baseline.path
    return atlas_pck.Archive(source)


def native_file(client, relative, state):
    source = client / relative
    previous = (
        state.get("files", {}).get(relative, {}) if state.get("client") == str(client) else {}
    )
    if previous.get("baseline") and source.exists() and digest(source) == previous["sha256"]:
        return baseline_path(previous["baseline"])
    return source


def resolve_client_folder(path):
    """Accept the game root, element, or a container with one client inside."""
    if not path or not str(path).strip():
        raise ValueError("Сначала укажите папку игры в настройке клиента.")
    path = Path(path).expanduser().resolve()
    if path.is_file():
        path = path.parent

    def is_client(root):
        element = root / "element"
        return (
            element.is_dir()
            and any(p.is_file() for p in element.glob("ElementClient*.exe"))
            and all((element / name).is_file() for name in ("surfaces.pck", "configs.pck"))
        )

    for root in (path, path.parent):
        if is_client(root):
            return root
    if path.is_dir():
        matches = [child for child in path.iterdir() if child.is_dir() and is_client(child)]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise ValueError(
                "В этой папке несколько клиентов. Выберите папку нужной игры: "
                + ", ".join(p.name for p in matches)
                + "."
            )
    raise ValueError(
        "Не найдена папка клиента PW. Выберите папку игры с каталогом element или сам каталог element. В нём должны быть ElementClient*.exe, surfaces.pck и configs.pck."
    )


def client_compatibility_error(client):
    """Recognizing a folder must not imply compatibility with another client."""
    client = Path(client).resolve()
    launcher = client / "launcher.ini"
    text = launcher.read_bytes().decode("utf-8", errors="replace") if launcher.is_file() else ""
    if re.search(r"(?im)^\s*UpdateServerHost_\d+\s*=.*?/146_rus/", text):
        return "Папка Comeback 1.4.6 найдена. Эта версия мода поддерживает Comeback 1.3.6; для 1.4.6 нужна отдельная адаптация. Файлы игры не изменены."
    if re.search(r"(?im)^\s*TestClient\s*=\s*1\s*$", text):
        return "Папка клиента найдена, но лаунчер запускает ElementClient_test.exe. Эта сборка мода рассчитана на обычный клиент Comeback 1.3.6 (ElementClient.exe). Файлы игры не изменены."
    exe = client / "element/ElementClient.exe"
    if not exe.is_file():
        return "Папка клиента найдена, но в ней используется другое имя EXE. Эта сборка мода поддерживает обычный ElementClient.exe Comeback 1.3.6. Файлы игры не изменены."
    state = read_json(ROOT / "installed.json", {})
    source = native_file(client, "element/ElementClient.exe", state)
    if digest(source) != atlas_client.SUPPORTED_SHA256:
        return "Папка клиента найдена, но версия ElementClient.exe отличается от поддерживаемого Comeback 1.3.6. Нужна адаптация под эту сборку. Файлы игры не изменены."
    return None


def require_supported_client(client):
    client = resolve_client_folder(client)
    error = client_compatibility_error(client)
    if error:
        raise ValueError(error)
    return client


def world_project(x, y, params=None):
    p = params or ORIGINAL_WORLD
    return 1024 + ((x - 400) * 10 - p["ox"]) * 2 * p["w"] / (1024 * p["a"]), 1024 + (
        p["oy"] - (y - 550) * 10
    ) * 2 * p["h"] / (1024 * p["b"])


def world_image(style, params, world="world"):
    if style == "original" or world != "world":
        source = (
            ASSETS / "originals/world.dds"
            if world == "world"
            else ASSETS / "realms" / world / "overview" / (world + ".dds")
        )
        return Image.open(source).convert("RGBA").resize((2048, 2048), Image.Resampling.LANCZOS)
    atlas = Image.open(ASSETS / "classic-map.jpg").convert("RGBA")
    sx = 4 * params["w"] / (1024 * params["a"])
    sy = 4 * params["h"] / (1024 * params["b"])
    cx = (4096 + params["ox"]) / 2
    cy = (5632 - params["oy"]) / 2
    transform = (1 / sx, 0, cx - 1024 / sx, 0, 1 / sy, cy - 1024 / sy)
    return atlas.transform(
        (2048, 2048),
        Image.Transform.AFFINE,
        transform,
        Image.Resampling.BICUBIC,
        fillcolor=atlas.getpixel((2048, 5300)),
    )


def map_config(data, params):
    """Change only the world=1 projection, preserving every other INI byte."""
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        encoding = "utf-16le" if data[:2] == b"\xff\xfe" else "utf-16be"
        text = data[2:].decode(encoding).encode("utf-8")
        return data[:2] + map_config(text, params).decode("utf-8").encode(encoding)
    changed = 0

    def section(m):
        nonlocal changed
        body = m[2]
        if not re.search(rb"(?m)^id[ \t]*=[ \t]*1[ \t]*\r?$", body):
            return m[0]
        for key, value in params.items():
            pattern = rb"(?m)^(" + key.encode() + rb"[ \t]*=[ \t]*)[^\r\n]*"
            body, n = re.subn(pattern, lambda line: line[1] + str(value).encode("ascii"), body)
            if n != 1:
                raise ValueError("Изменился формат настройки карты: " + key)
        changed += 1
        return m[1] + body

    result = re.sub(rb"(?ms)(^\[MapConvertParam\d+\]\r?\n)(.*?)(?=^\[|\Z)", section, data)
    if changed != 1:
        raise ValueError("Не найдена единственная настройка карты мира")
    return result


def digest(p):
    h = hashlib.sha256()
    with Path(p).open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def baseline_path(value):
    p = Path(value)
    return p if p.is_absolute() else ROOT / p


def archive_assets_match(path, state):
    """The launcher changes guild icons without removing the resource layers."""
    prefix = Path(path).name.split(".")[0].lower() + "/"
    expected = {
        k: v
        for k, v in state.get("assets", {}).items()
        if k.replace("\\", "/").lower().startswith(prefix)
    }
    if not expected:
        return False
    try:
        a = atlas_pck.Archive(path)
        return all(
            hashlib.sha256(a.read(name)).hexdigest() == sha for name, sha in expected.items()
        )
    except (OSError, ValueError, KeyError, zlib.error):
        return False


def preserve_dynamic_assets(base, current, replacements, scratch):
    for name in DYNAMIC_ASSETS:
        if name in current.entries and current.read(name) != base.read(name):
            p = Path(scratch) / name.rsplit("\\", 1)[-1]
            p.write_bytes(current.read(name))
            replacements[name] = p


@lru_cache(maxsize=256)
def marker_sprite(key, tier, size=24):
    """Native item illustration, with a quiet tier rim and transparent corners."""
    size = int(size)
    scale = 3
    im = Image.open(ASSETS / "resource-icons" / f"{key}.png").convert("RGBA").crop((2, 2, 30, 30))
    im = im.resize((size * scale, size * scale), Image.Resampling.LANCZOS)
    mask = Image.new("L", im.size, 0)
    d = ImageDraw.Draw(mask)
    d.rounded_rectangle(
        (scale, scale, im.width - scale - 1, im.height - scale - 1), radius=4 * scale, fill=255
    )
    im.putalpha(mask)
    d = ImageDraw.Draw(im)
    d.rounded_rectangle(
        (scale, scale, im.width - scale - 1, im.height - scale - 1),
        radius=4 * scale,
        outline=COLORS[tier],
        width=scale,
    )
    return im.resize((size, size), Image.Resampling.LANCZOS)


@lru_cache(maxsize=256)
def marker_png(key, tier, size=24):
    out = io.BytesIO()
    marker_sprite(key, tier, size).save(out, format="PNG")
    return out.getvalue()


@lru_cache(maxsize=256)
def minimap_sprite(key, tier, size=10, highlight=True):
    if not highlight:
        return marker_sprite(key, tier, size)
    scale = 3
    edge = (int(size) + 10) * scale
    color = {1: "#b4ff98", 2: "#8affef", 3: "#ffe679", 4: "#eac7ff", 5: "#ffc78b"}[tier]
    glow = Image.new("RGBA", (edge, edge))
    d = ImageDraw.Draw(glow)
    d.ellipse((scale, scale, edge - scale - 1, edge - scale - 1), fill=color + "b0")
    glow = glow.filter(ImageFilter.GaussianBlur(1.1 * scale))
    d = ImageDraw.Draw(glow)
    # A dark edge keeps the bright ring visible on snow, sand and lit roads.
    box = (2 * scale, 2 * scale, edge - 2 * scale - 1, edge - 2 * scale - 1)
    d.rounded_rectangle(box, radius=5 * scale, fill="#08161ef0", outline="#071219", width=3 * scale)
    d.rounded_rectangle(
        (3 * scale, 3 * scale, edge - 3 * scale - 1, edge - 3 * scale - 1),
        radius=4 * scale,
        outline=color,
        width=2 * scale,
    )
    icon = marker_sprite(key, tier, int(size) * scale)
    icon = ImageEnhance.Brightness(icon).enhance(1.15)
    glow.alpha_composite(icon, (5 * scale, 5 * scale))
    d = ImageDraw.Draw(glow)
    d.line((5 * scale, 4 * scale, 8 * scale, 4 * scale), fill="#fffbe9", width=scale)
    return glow.resize((edge // scale, edge // scale), Image.Resampling.LANCZOS)


@lru_cache(maxsize=256)
def minimap_png(key, tier, size=10, highlight=True):
    out = io.BytesIO()
    minimap_sprite(key, tier, size, highlight).save(out, format="PNG")
    return out.getvalue()


def stamp_marker(im, x, y, r, size):
    sprite = marker_sprite(r["key"], r["tier"], size)
    im.alpha_composite(sprite, (round(x - size / 2), round(y - size / 2)))


@lru_cache(maxsize=1024)
def grouped_sprite(keys, size, minimap=False, highlight=True, precision=False):
    sprites = [
        minimap_sprite(key, tier, size, highlight) if minimap else marker_sprite(key, tier, size)
        for key, tier in keys
    ]
    if len(sprites) == 1:
        return sprites[0]
    edge = sprites[0].width
    offsets = icon_offsets(len(keys), size + 4 if minimap and highlight else size + 3)
    width = round(max(x for x, y in offsets) - min(x for x, y in offsets)) + edge
    height = round(max(y for x, y in offsets) - min(y for x, y in offsets)) + edge
    image = Image.new("RGBA", (width, height))
    draw = ImageDraw.Draw(image)
    for dx, dy in offsets:
        draw.line((width / 2, height / 2, width / 2 + dx, height / 2 + dy), fill="#162432", width=2)
    for sprite, (dx, dy) in zip(sprites, offsets):
        image.alpha_composite(
            sprite, (round(width / 2 + dx - edge / 2), round(height / 2 + dy - edge / 2))
        )
    if not any(dx == dy == 0 for dx, dy in offsets):
        draw = ImageDraw.Draw(image)
        cx, cy = width // 2, height // 2
        if precision:
            draw.line((cx - 5, cy, cx + 5, cy), fill="#101820", width=3)
            draw.line((cx, cy - 5, cx, cy + 5), fill="#101820", width=3)
            draw.line((cx - 4, cy, cx + 4, cy), fill="#ffffff", width=1)
            draw.line((cx, cy - 4, cx, cy + 4), fill="#ffffff", width=1)
        else:
            draw.rectangle((cx - 1, cy - 1, cx + 1, cy + 1), fill="#162432")
            draw.point((cx, cy), fill="#fff6dc")
    return image


def group_sprite(members, size, minimap=False, highlight=True, precision=False):
    return grouped_sprite(
        tuple((r["key"], r["tier"]) for r, x, y in members), size, minimap, highlight, precision
    )


def stamp_group(image, x, y, members, size):
    sprite = group_sprite(members, size, precision=True)
    # Use an integer point anchor for every group size and icon-size setting.
    image.alpha_composite(sprite, (round(x) - sprite.width // 2, round(y) - sprite.height // 2))


def build_patch(
    selected,
    route=None,
    target=None,
    progress=None,
    client=None,
    world_style="classic",
    marker_size=10,
    minimap_scale=1.5,
    minimap_highlight=True,
    minimap_marker_size=24,
    routes=None,
):
    client = require_supported_client(client or DEFAULT_CLIENT)
    routes = world_routes(routes, route)
    route = routes["world"]
    for realm, stops in routes.items():
        spec = WORLDS[realm]
        for x, y in stops:
            px, py = project(x, y, realm)
            if not (0 <= px < spec["columns"] * 256 and 0 <= py < spec["rows"] * 256):
                raise ValueError("Точка маршрута за границами мира: " + spec["name"])
    target = Path(target or ROOT / "patch")
    target.mkdir(parents=True, exist_ok=True)
    marker_size = max(8, min(18, int(marker_size)))
    minimap_marker_size = max(12, min(40, int(minimap_marker_size)))
    chosen = [r for r in resources() if r["key"] in selected]
    points_by_world = {
        world: [(r, x, y) for r in chosen for x, y in resource_points(r, world)] for world in WORLDS
    }
    groups_by_world = {world: group_nodes(nodes) for world, nodes in points_by_world.items()}
    state = read_json(ROOT / "installed.json", {})
    config_archive = native_config_archive(client, state)
    config_data = config_archive.read("configs/map_param.ini")
    native_params = native_map_parameters(config_data)
    realm_params = {
        world: native_map_parameters(config_data, spec["id"]) for world, spec in WORLDS.items()
    }
    map_params = overview_parameters(
        world_style, groups_by_world["world"], route or [], native_params
    )
    exe_source = native_file(client, "element/ElementClient.exe", state)
    exe_original = exe_source.read_bytes()
    # Both overview styles must use the exact projection used for their DDS.
    # Keep this local to M: the native shared lookup may choose a fallback,
    # whereas the teleport map and detailed view must retain their own records.
    exe_data, exe_report = atlas_client.patch(exe_original, map_params)
    layout_source = native_file(client, MINIMAP_LAYOUT, state)
    if not layout_source.is_file():
        raise ValueError(
            "Не найден текущий интерфейс миникарты interfaces/map.xml выбранного клиента"
        )
    layout_original = layout_source.read_bytes()
    layout_data = atlas_minimap.scale_layout(layout_original, minimap_scale)
    outfiles = []
    rendered = 0
    total_tiles = sum(s["columns"] * s["rows"] for s in WORLDS.values())
    for realm, spec in WORLDS.items():
        tile_marks = {}
        # Extend the whole glow across tile boundaries in every supported world.
        for members in groups_by_world[realm]:
            r, x, y = members[0]
            px, py = project(x, y, realm)
            sprite = group_sprite(members, minimap_marker_size, True, minimap_highlight)
            padx = sprite.width / 2 + 1
            pady = sprite.height / 2 + 1
            if not (0 <= px < spec["columns"] * 256 and 0 <= py < spec["rows"] * 256):
                raise ValueError("Точка за границами мира: " + r["key"] + " / " + realm)
            for row in range(
                max(0, int((py - pady) // 256)), min(spec["rows"] - 1, int((py + pady) // 256)) + 1
            ):
                for col in range(
                    max(0, int((px - padx) // 256)),
                    min(spec["columns"] - 1, int((px + padx) // 256)) + 1,
                ):
                    tile_marks.setdefault((row, col), []).append(
                        (sprite, px - col * 256, py - row * 256)
                    )
        directory = (
            ASSETS / "originals" if realm == "world" else ASSETS / "realms" / realm / "originals"
        )
        originals = sorted(directory.glob("[0-9][0-9][0-9][0-9].dds"))
        if len(originals) != spec["rows"] * spec["columns"]:
            raise ValueError("Не хватает исходных текстур миникарты: " + spec["name"])
        for p in originals:
            row, col = int(p.stem[:2]), int(p.stem[2:])
            im = Image.open(p).convert("RGBA")
            d = ImageDraw.Draw(im)
            if len(routes[realm]) > 1:
                ps = [project(*xy, realm) for xy in routes[realm]]
                ps.append(ps[0])
                d.line([(x - col * 256, y - row * 256) for x, y in ps], fill="#10252f", width=5)
                d.line([(x - col * 256, y - row * 256) for x, y in ps], fill="#e7f5e9", width=2)
            for sprite, px, py in tile_marks.get((row, col), []):
                im.alpha_composite(
                    sprite, (round(px - sprite.width / 2), round(py - sprite.height / 2))
                )
            dest = target / "textures/surfaces/minimaps" / realm / p.name
            dest.parent.mkdir(parents=True, exist_ok=True)
            im.save(dest, pixel_format="DXT5")
            outfiles.append(dest)
            rendered += 1
            if progress:
                progress(round(rendered / total_tiles * 55))
    # The detailed in-game map is the original illustrated PW map. Its native
    # atlas is 8192 x 11264 and uses exactly twice the minimap coordinates.
    detail_marks = {}
    detail_size = marker_size * 2
    for members in groups_by_world["world"]:
        r, x, y = members[0]
        px, py = project(x, y)
        px *= 2
        py *= 2
        sprite = group_sprite(members, detail_size)
        padx = sprite.width / 2 + 1
        pady = sprite.height / 2 + 1
        for row in range(max(0, int((py - pady) // 1024)), min(10, int((py + pady) // 1024)) + 1):
            for col in range(
                max(0, int((px - padx) // 1024)), min(7, int((px + padx) // 1024)) + 1
            ):
                detail_marks.setdefault((row, col), []).append(
                    (sprite, px - col * 1024, py - row * 1024)
                )
    detail_originals = sorted((ASSETS / "maps-originals").glob("[0-9][0-9][0-9].dds"))
    if len(detail_originals) != 88:
        raise ValueError("Не хватает исходных плиток рисованной карты ПВ")
    for i, p in enumerate(detail_originals):
        row, col = int(p.stem[:2]), int(p.stem[2:])
        im = Image.open(p).convert("RGBA")
        d = ImageDraw.Draw(im)
        if route and len(route) > 1:
            ps = [project(*xy) for xy in route]
            ps.append(ps[0])
            ps = [(x * 2 - col * 1024, y * 2 - row * 1024) for x, y in ps]
            d.line(ps, fill="#211a10", width=8)
            d.line(ps, fill="#f1dfae", width=3)
        for sprite, px, py in detail_marks.get((row, col), []):
            im.alpha_composite(
                sprite, (round(px - sprite.width / 2), round(py - sprite.height / 2))
            )
        dest = target / "textures/surfaces/maps" / p.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        im.save(dest, pixel_format="DXT5")
        outfiles.append(dest)
        if progress:
            progress(55 + round((i + 1) / len(detail_originals) * 15))
    world = world_image(world_style, map_params)
    d = ImageDraw.Draw(world)
    if route and len(route) > 1:
        ps = [world_project(*xy, map_params) for xy in route]
        ps.append(ps[0])
        d.line(ps, fill="#10252f", width=7)
        d.line(ps, fill="#e7f5e9", width=3)
    for members in groups_by_world["world"]:
        stamp_group(world, *world_project(*members[0][1:], map_params), members, marker_size * 2)
    dest = target / "textures/surfaces/ingame/world.dds"
    dest.parent.mkdir(parents=True, exist_ok=True)
    world.save(dest, pixel_format="DXT5")
    outfiles.append(dest)
    # world-N.dds are alternative WHOLE maps selected before world.dds by the
    # client, not zoom tiles. Adding cropped quadrants here breaks the overview.
    # Zoom tiles belong to the separate, original surfaces/maps directory.
    for i in range(1, 5):
        (dest.parent / f"world-{i}.dds").unlink(missing_ok=True)
    world.convert("RGB").save(target / "preview.jpg", quality=94)
    for realm in ("a21", "a22"):
        overview = world_image("original", realm_params[realm], realm)
        if len(routes[realm]) > 1:
            ps = [world_project(*xy, realm_params[realm]) for xy in routes[realm]]
            ps.append(ps[0])
            d = ImageDraw.Draw(overview)
            d.line(ps, fill="#10252f", width=7)
            d.line(ps, fill="#e7f5e9", width=3)
        for members in groups_by_world[realm]:
            stamp_group(
                overview,
                *world_project(*members[0][1:], realm_params[realm]),
                members,
                marker_size * 2,
            )
        p = dest.parent / (realm + ".dds")
        overview.save(p, pixel_format="DXT5")
        outfiles.append(p)
        overview.convert("RGB").save(target / ("preview-" + realm + ".jpg"), quality=94)
    archive_source = client / "element/surfaces.pck"
    current_archive = None
    if state.get("client") == str(client):
        old = state.get("files", {}).get("element/surfaces.pck")
        if (
            old
            and old.get("baseline")
            and archive_source.exists()
            and (
                digest(archive_source) == old["sha256"]
                or archive_assets_match(archive_source, state)
            )
        ):
            current_archive = atlas_pck.Archive(archive_source)
            archive_source = baseline_path(old["baseline"])
    if not archive_source.exists():
        raise ValueError("Не найден surfaces.pck выбранного клиента")
    if progress:
        progress(75)
    replacements = {str(p.relative_to(target / "textures")).replace("/", "\\"): p for p in outfiles}
    packed_path = target / "element/surfaces.pck"
    base_archive = atlas_pck.Archive(archive_source)
    with tempfile.TemporaryDirectory(prefix="pw-atlas-icons-") as scratch:
        if current_archive:
            preserve_dynamic_assets(base_archive, current_archive, replacements, scratch)
        archive_report = base_archive.replace(replacements, packed_path)
    # Restore the original archive byte for byte when upgrading from 1.4.
    # JourneyMap background, native teleport hitboxes and map parameters must
    # remain unchanged together; only the regular world DDS receives markers.
    config_file = target / "settings/configs/map_param.ini"
    config_file.parent.mkdir(parents=True, exist_ok=True)
    config_file.write_bytes(config_data)
    config_packed = target / "element/configs.pck"
    shutil.copy2(config_archive.path, config_packed)
    config_report = {"unchanged": True, "entries": len(config_archive.entries)}
    exe_packed = target / "element/ElementClient.exe"
    exe_packed.write_bytes(exe_data)
    layout_packed = target / MINIMAP_LAYOUT
    layout_packed.parent.mkdir(parents=True, exist_ok=True)
    layout_packed.write_bytes(layout_data)
    if progress:
        progress(95)
    manifest = {
        "format": 6,
        "version": VERSION,
        "map_version": MAP_VERSION,
        "built": datetime.now().astimezone().isoformat(),
        "selected": list(selected),
        "nodes": sum(len(v) for v in points_by_world.values()),
        "nodes_by_world": {k: len(v) for k, v in points_by_world.items()},
        "route": route or [],
        "world_style": world_style,
        "marker_size": marker_size,
        "minimap_scale": minimap_scale,
        "minimap_highlight": minimap_highlight,
        "minimap_marker_size": minimap_marker_size,
        "minimap_viewport": list(atlas_minimap.viewport(layout_data)),
        "map_parameters": map_params,
        "native_map_parameters": native_params,
        "realm_parameters": realm_params,
        "files": {
            "element/surfaces.pck": digest(packed_path),
            "element/configs.pck": digest(config_packed),
            "element/ElementClient.exe": digest(exe_packed),
            MINIMAP_LAYOUT: digest(layout_packed),
        },
        "textures": {str(p.relative_to(target)).replace("\\", "/"): digest(p) for p in outfiles},
        "config_assets": {"configs/map_param.ini": digest(config_file)},
        "archive": archive_report,
        "config_archive": config_report,
        "client_patch": exe_report,
        "runtime_verified": False,
        "source": "https://pwdatabase.online/db/types/2865/",
    }
    manifest["routes"] = routes
    write_json(target / "manifest.json", manifest)
    if progress:
        progress(100)
    return manifest


def game_running():
    if os.name != "nt":
        return False
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    r = subprocess.run(
        ["tasklist", "/FO", "CSV", "/NH", "/FI", "IMAGENAME eq ElementClient*"],
        capture_output=True,
        creationflags=flags,
    )
    if r.returncode:
        raise RuntimeError("Не удалось проверить, закрыта ли игра. Закройте её и повторите.")
    return b"elementclient" in r.stdout.lower()


def safe_target(client, relative):
    root = Path(client).resolve()
    target = (root / relative).resolve()
    surfaces = (root / "element/surfaces").resolve()
    if relative in INSTALL_PATHS and target == (root / relative).resolve():
        return target
    if (
        surfaces not in target.parents
        or not relative.startswith("element/surfaces/")
        or target.suffix.lower() != ".dds"
    ):
        raise ValueError("Некорректный путь в манифесте")
    return target


def cleanup_legacy_empty_dirs(client):
    root = Path(client).resolve() / "element/surfaces"
    for relative in ("minimaps/world", "minimaps", "ingame", ""):
        try:
            (root / relative).rmdir()
        except OSError:
            pass


def install(client=DEFAULT_CLIENT, patch=None):
    if not client:
        raise ValueError("Сначала укажите папку игры в настройке клиента.")
    client = Path(client).resolve()
    patch = Path(patch or ROOT / "patch").resolve()
    if not (client / "element/ElementClient.exe").is_file():
        raise ValueError("В выбранной папке не найден element/ElementClient.exe")
    if game_running():
        raise RuntimeError(
            "Сначала полностью закройте игру. Файлы текстур могут находиться в её кэше."
        )
    manifest = read_json(patch / "manifest.json")
    if not manifest or not manifest.get("files"):
        raise ValueError("Сначала соберите выбранные слои карты")
    if (manifest.get("format"), set(manifest["files"])) not in [
        (3, {"element/surfaces.pck"}),
        (4, ARCHIVE_PATHS),
        (5, CLIENT_MAP_PATHS),
        (6, INSTALL_PATHS),
    ]:
        raise ValueError(
            "Этот набор собран старой версией. Пересоберите его: отдельная папка surfaces вызывает ошибку клиента."
        )
    cleanup_legacy_empty_dirs(client)
    if (client / "element/surfaces").is_dir():
        raise ValueError(
            "Найдена отдельная папка element/surfaces. Для этого клиента она несовместима с модом. Сначала удалите старую установку; пользовательские файлы автоматически не удаляются."
        )
    statefile = ROOT / "installed.json"
    old = read_json(statefile, {})
    if old and old.get("client") != str(client):
        raise ValueError("Сначала удалите установленный набор из прежней папки клиента")
    for rel, sha in manifest["files"].items():
        safe_target(client, rel)
        if digest(patch / rel) != sha:
            raise ValueError("Повреждён файл набора: " + rel)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    backup = ROOT / "backups" / stamp
    records = {}
    rollback = []
    try:
        for rel, sha in manifest["files"].items():
            dest = safe_target(client, rel)
            prev = old.get("files", {}).get(rel)
            baseline = prev.get("baseline") if prev else None
            before = None
            if dest.exists():
                owned = prev and (
                    digest(dest) == prev["sha256"]
                    or rel in ARCHIVE_PATHS
                    and archive_assets_match(dest, old)
                )
                if not owned:
                    baseline = str((backup / "originals" / rel).relative_to(ROOT))
                    original = baseline_path(baseline)
                    original.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(dest, original)
                    before = original
                else:
                    before = backup / "transaction" / rel
                    before.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(dest, before)
            rollback.append((dest, before))
            dest.parent.mkdir(parents=True, exist_ok=True)
            tmp = dest.with_name(dest.name + ".atlas-tmp")
            shutil.copyfile(patch / rel, tmp)
            os.replace(tmp, dest)
            records[rel] = {"sha256": sha, "baseline": baseline}
        write_json(
            statefile,
            {
                "format": manifest["format"],
                "version": manifest.get("version", VERSION),
                "map_version": manifest.get("map_version", manifest.get("version", VERSION)),
                "client": str(client),
                "installed": stamp,
                "files": records,
                "selected": manifest.get("selected", []),
                "routes": world_routes(manifest.get("routes"), manifest.get("route", [])),
                "build_options": {
                    key: manifest[key]
                    for key in (
                        "world_style",
                        "marker_size",
                        "minimap_scale",
                        "minimap_highlight",
                        "minimap_marker_size",
                    )
                    if key in manifest
                },
                "assets": {
                    **{
                        k.removeprefix("textures/"): v
                        for k, v in manifest.get("textures", {}).items()
                    },
                    **manifest.get("config_assets", {}),
                },
            },
        )
    except Exception:
        for dest, before in reversed(rollback):
            if before:
                shutil.copy2(before, dest)
            elif dest.exists():
                dest.unlink()
        raise
    # Successful replacements no longer need the temporary transaction copies.
    transaction = (backup / "transaction").resolve()
    for dest, before in rollback:
        if before and before.resolve().is_relative_to(transaction) and before.exists():
            before.unlink()
    return len(records)


def uninstall():
    statefile = ROOT / "installed.json"
    state = read_json(statefile)
    if not state:
        return 0, []
    if game_running():
        raise RuntimeError("Сначала закройте игру")
    # Overview art and its coordinate parameters form one set. Do not restore
    # one archive if an external update prevents restoring the other.
    paired = INSTALL_PATHS.intersection(state["files"])
    if len(paired) > 1:
        conflicts = []
        for rel in paired:
            rec = state["files"][rel]
            dest = safe_target(state["client"], rel)
            original = baseline_path(rec["baseline"]) if rec.get("baseline") else None
            if original and not original.exists():
                conflicts.append(rel)
                continue
            if not dest.exists() or digest(dest) == rec["sha256"]:
                continue
            if not original or not archive_assets_match(dest, state):
                conflicts.append(rel)
                continue
            base = atlas_pck.Archive(original)
            current = atlas_pck.Archive(dest)
            allowed = {k.replace("/", "\\").lower() for k in state["assets"]} | set(DYNAMIC_ASSETS)
            others = set(current.entries) - allowed
            if others != set(base.entries) - allowed or not all(
                current.entries[k]["raw"] == base.entries[k]["raw"] for k in others
            ):
                conflicts.append(rel)
        if conflicts:
            return 0, conflicts
    pending = {}
    restored = 0
    dirs = set()
    for rel, rec in state["files"].items():
        dest = safe_target(state["client"], rel)
        if rel.startswith("element/surfaces/"):
            parent = dest.parent
            surface_root = (Path(state["client"]) / "element/surfaces").resolve()
            while parent == surface_root or surface_root in parent.parents:
                dirs.add(parent)
                parent = parent.parent
        if dest.exists() and digest(dest) != rec["sha256"]:
            if rel in ARCHIVE_PATHS and rec["baseline"] and archive_assets_match(dest, state):
                original = baseline_path(rec["baseline"])
                base = atlas_pck.Archive(original)
                current = atlas_pck.Archive(dest)
                allowed = {k.replace("/", "\\").lower() for k in state["assets"]} | set(
                    DYNAMIC_ASSETS
                )
                others = set(current.entries) - allowed
                # Retain launcher guild changes; preserve other updates for manual review.
                if others == set(base.entries) - allowed and all(
                    current.entries[k]["raw"] == base.entries[k]["raw"] for k in others
                ):
                    tmp = dest.with_name(dest.name + ".atlas-restore")
                    with tempfile.TemporaryDirectory(prefix="pw-atlas-restore-") as scratch:
                        replacements = {}
                        preserve_dynamic_assets(base, current, replacements, scratch)
                        if replacements:
                            base.replace(replacements, tmp)
                        else:
                            shutil.copy2(original, tmp)
                    os.replace(tmp, dest)
                    restored += 1
                    continue
            pending[rel] = rec
            continue
        if rec["baseline"]:
            original = baseline_path(rec["baseline"])
            if not original.exists():
                pending[rel] = rec
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            tmp = dest.with_name(dest.name + ".atlas-restore")
            shutil.copy2(original, tmp)
            os.replace(tmp, dest)
        elif dest.exists():
            dest.unlink()
        restored += 1
    for path in sorted(dirs, key=lambda p: len(p.parts), reverse=True):
        try:
            path.rmdir()
        except OSError:
            pass
    cleanup_legacy_empty_dirs(state["client"])
    if pending:
        state["files"] = pending
        write_json(statefile, state)
    else:
        statefile.unlink()
    return restored, list(pending)


def export_route(route, path):
    with Path(path).open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Порядок", "X", "Y"])
        for i, (x, y) in enumerate(route, 1):
            w.writerow([i, round(x, 1), round(y, 1)])
