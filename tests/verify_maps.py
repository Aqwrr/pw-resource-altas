from pathlib import Path
import sys
import tempfile
import math
import hashlib
import re
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import atlas_core as c


def check(value, message):
    if not value:
        raise AssertionError(message)


for xy in [(400, 550), (100, 1000), (552, 653), (0, 0)]:
    check(math.dist(c.unproject(*c.project(*xy)), xy) < 1e-9, "Coordinate round trip")
check(c.project(400, 550) == (2048, 2816), "Map centre")
rr = c.resources()
check(
    len(rr) == 49 and sum(c.resource_count(r) for r in rr) == 4970,
    "All T1-T5 materials and herbs complete",
)
check(
    {tier: sum(r["tier"] == tier for r in rr) for tier in range(1, 6)}
    == {1: 8, 2: 11, 3: 11, 4: 10, 5: 9},
    "All five tiers represented",
)
for world, spec in c.WORLDS.items():
    for r in rr:
        for x, y in c.resource_points(r, world):
            px, py = c.project(x, y, world)
            check(
                0 <= px < spec["columns"] * 256 and 0 <= py < spec["rows"] * 256,
                "Every spawn lies inside its own world",
            )
            check(
                math.dist(c.unproject(px, py, world), (x, y)) < 1e-8,
                "World-aware coordinate round trip",
            )
icon_index = c.read_json(c.ASSETS / "resource-icons/index.json")
for r in rr:
    check(icon_index[r["key"]]["item_id"] == r["id"], "Native icon belongs to the resource item")
    sprite = c.marker_sprite(r["key"], r["tier"], 24)
    check(
        sprite.size == (24, 24) and sprite.getchannel("A").getextrema() == (0, 255),
        "Native pictogram with transparent corners",
    )
for r in rr:
    for x, y in r["points"]:
        px, py = c.project(x, y)
        check(0 <= px < 4096 and 0 <= py < 5632, "Marker inside terrain")
all_points = [xy for r in rr for xy in r["points"]]
for points in ([], all_points, [xy for r in rr if r["tier"] == 3 for xy in r["points"]]):
    params = c.world_parameters("classic", points)
    for x, y in points:
        px, py = c.world_project(x, y, params)
        check(0 <= px < 2048 and 256 <= py <= 1792, "Selected marker inside visible overview crop")
check(
    c.world_parameters("original", all_points, [(100, 100), (700, 900)]) == c.ORIGINAL_WORLD,
    "Route and map style preserve native teleport coordinates",
)
p = c.world_parameters("classic")
top = c.world_project(*c.unproject(2048, c.CLASSIC_CROP[1]), p)[1]
bottom = c.world_project(*c.unproject(2048, c.CLASSIC_CROP[3]), p)[1]
check(1534 <= bottom - top <= 1538, "Classic mainland fills the 1536-pixel visible height")

original_root = c.ROOT
c.game_running = lambda: False
with tempfile.TemporaryDirectory(prefix="pw-atlas-verification-") as tmp:
    tmp = Path(tmp)
    c.ROOT = tmp / "tool"
    c.ROOT.mkdir()
    client = tmp / "client"
    (client / "element").mkdir(parents=True)
    (client / "element/ElementClient.exe").write_bytes(b"test fixture, never executed")
    rel = "element/surfaces.pck"
    dest = client / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(b"original custom map")
    patch = tmp / "patch"
    src = patch / rel
    src.parent.mkdir(parents=True)
    src.write_bytes(b"resource map v1")
    c.write_json(patch / "manifest.json", {"format": 3, "files": {rel: c.digest(src)}})
    check(c.install(client, patch) == 1, "Install")
    check(dest.read_bytes() == b"resource map v1", "Payload installed")
    check(c.install(client, patch) == 1, "Reinstall")
    n, p = c.uninstall()
    check(
        n == 1 and not p and dest.read_bytes() == b"original custom map",
        "Baseline survives reinstall",
    )
    dest.unlink()
    c.install(client, patch)
    dest.write_bytes(b"new game update")
    n, p = c.uninstall()
    check(
        n == 0 and p == [rel] and dest.read_bytes() == b"new game update",
        "External update preserved on uninstall",
    )
    c.install(client, patch)
    n, p = c.uninstall()
    check(dest.read_bytes() == b"new game update", "Updated baseline retained")
    # Legacy installations must remove their empty surfaces folder: the game
    # mistakes that directory for a texture when its icon filename is empty.
    legacy = "element/surfaces/ingame/world.dds"
    lp = client / legacy
    lp.parent.mkdir(parents=True)
    lp.write_bytes(b"legacy texture")
    c.write_json(
        c.ROOT / "installed.json",
        {"client": str(client), "files": {legacy: {"sha256": c.digest(lp), "baseline": None}}},
    )
    c.uninstall()
    check(not (client / "element/surfaces").exists(), "Legacy empty directory removed")
    (client / "element/surfaces").mkdir()
    (client / "element/surfaces/user-owned.txt").write_text("preserve me")
    try:
        c.install(client, patch)
    except ValueError:
        pass
    else:
        raise AssertionError("Loose surfaces folder must block installation")
    check(
        (client / "element/surfaces/user-owned.txt").read_text() == "preserve me",
        "User files preserved",
    )
    (client / "element/surfaces/user-owned.txt").unlink()
    (client / "element/surfaces").rmdir()
    for relbad in ["../bad.dds", "element/surfaces/../../bad.dds", "element/other.exe"]:
        try:
            c.safe_target(client, relbad)
        except ValueError:
            pass
        else:
            raise AssertionError("Path restriction")
    # The art and projection must install and restore as one set.
    config_rel = "element/configs.pck"
    config_dest = client / config_rel
    config_dest.write_bytes(b"original map settings")
    config_src = patch / config_rel
    config_src.write_bytes(b"fitted map settings")
    c.write_json(
        patch / "manifest.json",
        {"format": 4, "files": {rel: c.digest(src), config_rel: c.digest(config_src)}},
    )
    check(c.install(client, patch) == 2, "Paired archive installation")
    check(c.install(client, patch) == 2, "Paired archive reinstallation")
    config_dest.write_bytes(b"external config update")
    n, p = c.uninstall()
    check(
        n == 0 and p == [config_rel] and dest.read_bytes() == b"resource map v1",
        "Conflict preserves both coupled archives",
    )
    config_dest.write_bytes(b"fitted map settings")
    n, p = c.uninstall()
    check(
        n == 2
        and not p
        and config_dest.read_bytes() == b"original map settings"
        and dest.read_bytes() == b"new game update",
        "Both original archives restored",
    )
    exe_rel = "element/ElementClient.exe"
    exe_dest = client / exe_rel
    exe_before = exe_dest.read_bytes()
    exe_src = patch / exe_rel
    exe_src.write_bytes(b"display-only projection fixture, never executed")
    c.write_json(
        patch / "manifest.json",
        {
            "format": 5,
            "files": {
                rel: c.digest(src),
                config_rel: c.digest(config_src),
                exe_rel: c.digest(exe_src),
            },
        },
    )
    check(
        c.install(client, patch) == 3 and c.install(client, patch) == 3,
        "Three-file install and reinstall",
    )
    exe_dest.write_bytes(b"external client update")
    n, p = c.uninstall()
    check(
        n == 0 and p == [exe_rel] and dest.read_bytes() == b"resource map v1",
        "External EXE update preserves the entire installed set",
    )
    exe_dest.write_bytes(exe_src.read_bytes())
    n, p = c.uninstall()
    check(
        n == 3 and not p and exe_dest.read_bytes() == exe_before,
        "All three native files restored including the executable",
    )
    ui_rel = c.MINIMAP_LAYOUT
    ui_dest = client / ui_rel
    ui_dest.parent.mkdir(parents=True)
    ui_dest.write_bytes(b"original user minimap layout")
    ui_src = patch / ui_rel
    ui_src.parent.mkdir(parents=True)
    ui_src.write_bytes(b"larger minimap layout fixture")
    files = {
        rel: c.digest(src),
        config_rel: c.digest(config_src),
        exe_rel: c.digest(exe_src),
        ui_rel: c.digest(ui_src),
    }
    c.write_json(patch / "manifest.json", {"format": 6, "files": files})
    check(
        c.install(client, patch) == 4 and c.install(client, patch) == 4,
        "Four-file install and repeat install",
    )
    check(
        c.native_file(client, ui_rel, c.read_json(c.ROOT / "installed.json")).read_bytes()
        == b"original user minimap layout",
        "Repeat build scales the original layout, not an already enlarged one",
    )
    ui_dest.write_bytes(b"user changed layout externally")
    n, p = c.uninstall()
    check(
        n == 0 and p == [ui_rel] and exe_dest.read_bytes() == exe_src.read_bytes(),
        "External minimap customization prevents partial restoration",
    )
    ui_dest.write_bytes(ui_src.read_bytes())
    n, p = c.uninstall()
    check(
        n == 4
        and not p
        and ui_dest.read_bytes() == b"original user minimap layout"
        and exe_dest.read_bytes() == exe_before,
        "Original user layout and all three game files restored",
    )
c.ROOT = original_root
print(
    "PASS: 4970 point projections in three worlds, 49 resources across five tiers, repeat install, rollback, conflicts and path restrictions"
)

if "--build" in sys.argv:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--existing", action="store_true")
    parser.add_argument("--style", choices=("classic", "original"))
    parser.add_argument("--target", type=Path)
    options = parser.parse_args()
    settings = c.read_json(c.ROOT / "settings.json", {})
    chosen = (
        [r["key"] for r in rr]
        if options.all
        else settings.get("selected", [r["key"] for r in rr if r["kind"] != "herb"])
    )
    style = options.style or settings.get("world_style", "classic")
    target = options.target or c.ROOT / "patch"
    client = Path(settings.get("client", c.DEFAULT_CLIENT)).resolve()
    source = client / "element/surfaces.pck"
    state = c.read_json(c.ROOT / "installed.json", {})
    old = state.get("files", {}).get("element/surfaces.pck", {})
    if (
        state.get("client") == str(client)
        and old.get("baseline")
        and (c.digest(source) == old["sha256"] or c.archive_assets_match(source, state))
    ):
        source = c.baseline_path(old["baseline"])
    progress_seen = set()

    def progress(n):
        if n in (25, 50, 75, 100) and n not in progress_seen:
            print("Rendering", style, n, flush=True)
            progress_seen.add(n)

    m = (
        c.read_json(target / "manifest.json")
        if options.existing
        else c.build_patch(
            chosen,
            target=target,
            client=client,
            world_style=style,
            marker_size=settings.get("marker_size", 10),
            minimap_scale=settings.get("minimap_scale", 1.5),
            minimap_highlight=settings.get("minimap_highlight", True),
            minimap_marker_size=settings.get("minimap_marker_size", 24),
            progress=progress,
        )
    )
    check(
        m["version"] == c.VERSION
        and m["world_style"] == style
        and set(m["selected"]) == set(chosen),
        "Selected build matches the requested verification",
    )
    for rel, sha in {**m["files"], **m["textures"]}.items():
        p = target / rel
        check(c.digest(p) == sha, "Payload integrity")
        if p.suffix.lower() == ".dds":
            with Image.open(p) as im:
                im.load()
                check(im.size in [(256, 256), (1024, 1024), (2048, 2048)], "Native DDS dimensions")
                check(im.format == "DDS", "Native DDS format")
    check(
        set(m["files"]) == c.INSTALL_PATHS and len(m["textures"]) == 571,
        "Two archives, executable and minimap XML; no loose texture directory",
    )
    if options.all:
        check(
            m["nodes"] == 4970 and m["nodes_by_world"] == {"world": 4538, "a21": 231, "a22": 201},
            "All resources included in their own worlds",
        )
    import atlas_pck

    base = atlas_pck.Archive(source)
    new = atlas_pck.Archive(target / "element/surfaces.pck")
    changes = {rel[len("textures/") :].replace("/", "\\") for rel in m["textures"]}
    check(
        set(base.entries) == set(new.entries),
        "Original archive paths retained without adding whole-map variants",
    )
    for i in range(1, 5):
        check(
            f"surfaces\\ingame\\world-{i}.dds" not in new.entries,
            "No quadrant may override the whole map",
        )
    check(
        new.read("surfaces\\ingame\\world.dds")
        == (target / "textures/surfaces/ingame/world.dds").read_bytes(),
        "Complete overview selected by the native map loader",
    )
    for realm in ("a21", "a22"):
        check(
            new.read("surfaces/ingame/" + realm + ".dds")
            == (target / "textures/surfaces/ingame" / (realm + ".dds")).read_bytes(),
            "Realm overview installed under its native path",
        )
        check(
            sum(k.startswith("surfaces\\minimaps\\" + realm + "\\") for k in changes) == 64,
            "All native realm minimap tiles present",
        )
    check(
        new.read("surfaces/ingame/journeymap.dds") == base.read("surfaces/ingame/journeymap.dds"),
        "Native teleport map background retained byte for byte",
    )
    check(
        sum(k.startswith("surfaces\\maps\\") for k in changes) == 88,
        "All native detailed-map tiles carry the selected resource layer",
    )
    current = atlas_pck.Archive(client / "element/surfaces.pck")
    for key, e in base.entries.items():
        if key in c.DYNAMIC_ASSETS:
            check(new.read(key) == current.read(key), "Current launcher guild icons preserved")
        elif key not in changes:
            check(new.entries[key]["raw"] == e["raw"], "Unchanged archive entry metadata")
    # The entire original archive is retained byte for byte except its logical-size DWORD.
    with base.path.open("rb") as a, new.path.open("rb") as b:
        check(a.read(4) == b.read(4), "Archive signature")
        a.seek(8)
        b.seek(8)
        while chunk := a.read(1 << 20):
            check(b.read(len(chunk)) == chunk, "Original archive prefix retained")
    for key in changes:
        check(
            new.read(key) == (target / "textures" / key.replace("\\", "/")).read_bytes(),
            "Native archive payload",
        )
    cb = c.native_config_archive(client, state)
    cn = atlas_pck.Archive(target / "element/configs.pck")
    check(
        c.digest(cb.path) == c.digest(cn.path),
        "Teleport fix restores the entire original config archive byte for byte",
    )
    check(set(cb.entries) == set(cn.entries), "All config archive paths retained")
    for key in cb.entries:
        if key != "configs\\map_param.ini":
            check(
                cb.entries[key]["raw"] == cn.entries[key]["raw"],
                "All other client settings preserved",
            )
    oldini = cb.read("configs/map_param.ini")
    newini = cn.read("configs/map_param.ini")
    check(newini == oldini, "Native teleport projection must never be scaled or shifted")
    check(
        c.native_map_parameters(newini) == m["native_map_parameters"] == c.ORIGINAL_WORLD,
        "Teleports retain the actual native coordinate system",
    )
    check(newini[:2] == oldini[:2], "Native INI encoding preserved")
    check(
        c.map_config(oldini, c.ORIGINAL_WORLD) == oldini,
        "Original map style restores the native INI byte for byte",
    )
    if oldini.startswith(b"\xff\xfe"):
        oldini = oldini.decode("utf-16").encode("utf-8")
        newini = newini.decode("utf-16").encode("utf-8")
    section = rb"(?ms)^\[MapConvertParam20\]\r?\n.*?(?=^\[|\Z)"
    check(
        re.sub(section, b"WORLD", oldini) == re.sub(section, b"WORLD", newini),
        "Only the world projection section changed",
    )
    block = re.search(section, newini)[0]
    parsed = {
        key: float(re.search(rb"(?m)^" + key.encode() + rb"\s*=\s*([^\r\n]+)", block)[1])
        for key in m["map_parameters"]
    }
    check(
        parsed == m["native_map_parameters"],
        "Native INI projection remains independent of the fitted resource map",
    )
    check(
        hashlib.sha256(cn.read("configs/map_param.ini")).hexdigest()
        == m["config_assets"]["configs/map_param.ini"],
        "Config asset checksum",
    )
    exe_source = c.native_file(client, "element/ElementClient.exe", state)
    expected, info = c.atlas_client.patch(exe_source.read_bytes(), m["map_parameters"])
    check(
        m["client_patch"]["projection"] == m["map_parameters"],
        "Both styles use their rendered overview projection only for the visible normal M",
    )
    check(
        (target / "element/ElementClient.exe").read_bytes() == expected,
        "Generated executable matches the selected map style",
    )
    ui_original = c.native_file(client, c.MINIMAP_LAYOUT, state).read_bytes()
    ui_expected = c.atlas_minimap.scale_layout(ui_original, m["minimap_scale"])
    check(
        (target / c.MINIMAP_LAYOUT).read_bytes() == ui_expected,
        "Minimap XML is scaled from the current original user interface",
    )
    check(
        list(c.atlas_minimap.viewport(ui_expected)) == m["minimap_viewport"],
        "Minimap viewport matches selected scale",
    )
    print(
        "PASS: "
        + style
        + "; 571 DDS, three worlds, native config/JourneyMap byte identity, correct executable, scaled minimap and four-file install/restore/conflicts",
        flush=True,
    )
