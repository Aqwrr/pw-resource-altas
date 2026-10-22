"""GitHub Releases updates. No game paths or personal files are update targets."""

from pathlib import Path, PurePosixPath
import ctypes
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import time
import urllib.request
import urllib.error
import urllib.parse
import uuid
import zipfile

APP = "pw-resource-atlas"
EXE = "PW-Resource-Atlas.exe"
PACKAGE = "PW-Resource-Atlas-update.zip"
FEED = "atlas-release.json"
DESCRIPTOR = "atlas-package.json"
MAX_DOWNLOAD = 384 * 1024 * 1024
MAX_UNPACKED = 1536 * 1024 * 1024
DOCS = {
    "requirements.txt",
    "verification_checks.py",
    "НАЧНИ ЗДЕСЬ.txt",
    "ПРОЧИТАЙ МЕНЯ.txt",
    "3D-МАЯКИ.txt",
    "3D-ПОДСВЕТКА-ТЕСТ-Т4.txt",
    "ТАЙМЕР-РЕСУРСОВ-10-МИНУТ.md",
    "СПРАВОЧНИК ДК И ФОРМ.md",
    "ИССЛЕДОВАНИЕ ПОДСВЕТКИ И ТРАВ.md",
    "ОБНОВЛЕНИЯ.txt",
    "ПУБЛИКАЦИЯ-ОБНОВЛЕНИЙ.txt",
    "interface-preview.png",
}
HOSTS = {
    "api.github.com",
    "github.com",
    "release-assets.githubusercontent.com",
    "objects.githubusercontent.com",
    "github-releases.githubusercontent.com",
}


class UpdateError(ValueError):
    pass


class Cancelled(UpdateError):
    pass


def version(value):
    if not isinstance(value, str) or not re.fullmatch(r"v?\d+\.\d+(?:\.\d+)?", value):
        raise UpdateError("Неподдерживаемый номер версии.")
    parts = tuple(int(p) for p in value.lstrip("v").split("."))
    return parts + (0,) * (3 - len(parts))


def repository(value):
    value = str(value).strip().removesuffix(".git").rstrip("/")
    if value.startswith("https://github.com/"):
        value = value[len("https://github.com/") :]
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9_.-]+", value):
        raise UpdateError("Укажите репозиторий GitHub в виде владелец/название.")
    return value


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def safe_name(name):
    if (
        not isinstance(name, str)
        or not name
        or "\\" in name
        or any(c in name for c in ':*?"<>|\x00')
    ):
        raise UpdateError("Недопустимый путь в обновлении.")
    p = PurePosixPath(name)
    if (
        p.is_absolute()
        or str(p) != name
        or any(
            part in (".", "..")
            or part.endswith((" ", "."))
            or re.fullmatch(r"(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?", part)
            for part in p.parts
        )
    ):
        raise UpdateError("Недопустимый путь в обновлении.")
    return p


def managed(name):
    p = safe_name(name)
    return (len(p.parts) > 1 and p.parts[0] in ("_internal", "third-party-licenses")) or (
        len(p.parts) == 1
        and (name == EXE or name in DOCS or re.fullmatch(r"atlas_[a-z_]+\.py", name))
    )


def target_file(root, name):
    if not managed(name):
        raise UpdateError("Обновление пытается заменить пользовательский файл: " + name)
    root = Path(root).resolve()
    path = root.joinpath(*safe_name(name).parts)
    if not path.resolve().is_relative_to(root) or path.is_symlink():
        raise UpdateError("Путь обновления выходит за папку программы.")
    return path


def https_url(url):
    p = urllib.parse.urlsplit(url)
    if (
        p.scheme != "https"
        or p.hostname not in HOSTS
        or p.username
        or p.password
        or p.port not in (None, 443)
    ):
        raise UpdateError("Адрес обновления не принадлежит GitHub HTTPS.")
    return url


class GitHubRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        https_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def open_url(url, headers=None):
    req = urllib.request.Request(
        https_url(url),
        headers={
            "User-Agent": "PW-Resource-Atlas-Updater/1",
            "Accept": "application/vnd.github+json",
            **(headers or {}),
        },
    )
    try:
        return urllib.request.build_opener(GitHubRedirect()).open(req, timeout=20)
    except urllib.error.HTTPError as error:
        if error.code == 404:
            raise UpdateError("Релиз ещё не опубликован или репозиторий недоступен.") from None
        if error.code in (403, 429):
            raise UpdateError(
                "GitHub временно ограничил запросы. Повторите проверку позже."
            ) from None
        raise UpdateError(f"GitHub вернул ошибку {error.code}.") from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise UpdateError(
            "Не удалось связаться с GitHub. Проверьте подключение к интернету."
        ) from None


def remote_json(url, limit=1024 * 1024):
    with open_url(url) as response:
        data = response.read(limit + 1)
    if len(data) > limit:
        raise UpdateError("Слишком большой файл описания обновления.")
    try:
        result = json.loads(data)
    except (ValueError, UnicodeDecodeError):
        raise UpdateError("GitHub вернул некорректное описание обновления.") from None
    if not isinstance(result, dict):
        raise UpdateError("Некорректное описание обновления.")
    return result


def release_asset(release, name, repo):
    assets = [
        a
        for a in release.get("assets", [])
        if a.get("name") == name and a.get("state") == "uploaded"
    ]
    if len(assets) != 1:
        raise UpdateError("В релизе нет готового файла " + name + ".")
    asset = assets[0]
    url = asset.get("browser_download_url", "")
    p = urllib.parse.urlsplit(https_url(url))
    prefix = (
        "/" + repo + "/releases/download/" + urllib.parse.quote(release["tag_name"], safe="") + "/"
    )
    if (
        p.hostname != "github.com"
        or not p.path.casefold().startswith(prefix.casefold())
        or urllib.parse.unquote(p.path.rsplit("/", 1)[-1]) != name
    ):
        raise UpdateError("Файл обновления опубликован в другом репозитории.")
    return asset


def check(repo, current):
    repo = repository(repo)
    release = remote_json("https://api.github.com/repos/" + repo + "/releases/latest")
    if release.get("draft") or release.get("prerelease"):
        raise UpdateError("Этот релиз не является стабильным.")
    latest = release.get("tag_name", "")
    if version(latest) <= version(current):
        return {
            "available": False,
            "version": latest.lstrip("v"),
            "repository": repo,
            "notes": str(release.get("body") or "")[:14000],
        }
    descriptor = release_asset(release, FEED, repo)
    asset = release_asset(release, PACKAGE, repo)
    manifest = remote_json(descriptor["browser_download_url"], 128 * 1024)
    if (
        manifest.get("app") != APP
        or manifest.get("schema") != 1
        or type(manifest.get("min_updater", 1)) is not int
        or manifest.get("min_updater", 1) > 1
    ):
        raise UpdateError("Для этого релиза нужна новая версия установщика.")
    if version(manifest.get("version")) != version(latest):
        raise UpdateError("Версии релиза и файла обновления не совпадают.")
    pkg = manifest.get("package", {})
    if (
        pkg.get("name") != PACKAGE
        or not re.fullmatch("[a-f0-9]{64}", pkg.get("sha256", ""))
        or type(pkg.get("bytes")) is not int
        or not 0 < pkg["bytes"] <= MAX_DOWNLOAD
    ):
        raise UpdateError("Некорректное описание архива обновления.")
    if asset.get("size") != pkg["bytes"]:
        raise UpdateError("Размер архива не совпадает с описанием релиза.")
    digest = asset.get("digest")
    if digest and digest != "sha256:" + pkg["sha256"]:
        raise UpdateError("Контрольная сумма GitHub не совпадает с описанием релиза.")
    return {
        "available": True,
        "version": manifest["version"],
        "repository": repo,
        "url": asset["browser_download_url"],
        "sha256": pkg["sha256"],
        "bytes": pkg["bytes"],
        "notes": str(release.get("body") or manifest.get("notes") or "")[:14000],
    }


def cancelled(event):
    if event is not None and event.is_set():
        raise Cancelled("Обновление отменено.")


def validate_descriptor(data):
    if not isinstance(data, dict) or data.get("app") != APP or data.get("schema") != 1:
        raise UpdateError("Архив предназначен для другой программы.")
    version(data.get("version"))
    files = data.get("files")
    if not isinstance(files, dict) or not 1 <= len(files) <= 12000 or EXE not in files:
        raise UpdateError("В архиве нет программы или списка файлов.")
    seen = set()
    for name, digest in files.items():
        if (
            not managed(name)
            or name.casefold() in seen
            or not isinstance(digest, str)
            or not re.fullmatch("[a-f0-9]{64}", digest)
        ):
            raise UpdateError("Некорректный список файлов обновления.")
        seen.add(name.casefold())
    return data


def unpack(package, dest, expected_version, event=None):
    dest = Path(dest)
    with zipfile.ZipFile(package) as z:
        infos = z.infolist()
        seen = set()
        total = 0
        if len(infos) > 12001:
            raise UpdateError("Слишком много файлов в архиве.")
        for item in infos:
            safe_name(item.filename)
            if (
                item.is_dir()
                or stat.S_ISLNK(item.external_attr >> 16)
                or item.flag_bits & 1
                or item.filename.casefold() in seen
            ):
                raise UpdateError("Неподдерживаемая структура архива обновления.")
            if item.filename != DESCRIPTOR and not managed(item.filename):
                raise UpdateError(
                    "В архиве найден пользовательский или посторонний файл: " + item.filename
                )
            seen.add(item.filename.casefold())
            total += item.file_size
        if total > MAX_UNPACKED:
            raise UpdateError("Распакованное обновление слишком большое.")
        if DESCRIPTOR not in z.namelist() or z.getinfo(DESCRIPTOR).file_size > 4 * 1024 * 1024:
            raise UpdateError("Нет списка файлов обновления.")
        data = validate_descriptor(json.loads(z.read(DESCRIPTOR)))
        if version(data["version"]) != version(expected_version) or set(data["files"]) != {
            i.filename for i in infos if i.filename != DESCRIPTOR
        }:
            raise UpdateError("Состав архива не совпадает со списком файлов.")
        if shutil.disk_usage(dest.parent).free < total * 2 + 32 * 1024 * 1024:
            raise UpdateError("Недостаточно места для обновления и резервной копии.")
        dest.mkdir()
        for item in infos:
            cancelled(event)
            path = dest.joinpath(*safe_name(item.filename).parts)
            path.parent.mkdir(parents=True, exist_ok=True)
            with z.open(item) as source, path.open("wb") as output:
                shutil.copyfileobj(source, output, 1024 * 1024)
            if item.filename != DESCRIPTOR and sha256(path) != data["files"][item.filename]:
                raise UpdateError("Повреждён файл обновления: " + item.filename)
    return data


def prepare(root, release, progress=lambda n: None, event=None):
    root = Path(root).resolve()
    cache = root / "updates"
    cache.mkdir(exist_ok=True)
    if cache.resolve().parent != root:
        raise UpdateError("Папка обновлений находится вне папки программы.")
    work = cache / uuid.uuid4().hex
    work.mkdir()
    package = work / "download.zip"
    received = 0
    h = hashlib.sha256()
    cancelled(event)
    if shutil.disk_usage(work).free < release["bytes"] * 3:
        raise UpdateError("Недостаточно места для загрузки обновления.")
    with (
        open_url(release["url"], {"Accept": "application/octet-stream"}) as response,
        package.open("wb") as output,
    ):
        while True:
            cancelled(event)
            block = response.read(256 * 1024)
            if not block:
                break
            received += len(block)
            if received > release["bytes"] or received > MAX_DOWNLOAD:
                raise UpdateError("Размер загрузки превышает заявленный.")
            output.write(block)
            h.update(block)
            progress(min(85, round(received / release["bytes"] * 85)))
    if received != release["bytes"] or h.hexdigest() != release["sha256"]:
        raise UpdateError(
            "Обновление загружено не полностью или повреждено. Файлы программы сохранены."
        )
    data = unpack(package, work / "app", release["version"], event)
    cancelled(event)
    progress(95)
    plan = {
        "schema": 1,
        "target": str(root),
        "version": data["version"],
        "parent_pid": os.getpid(),
        "restart": False,
        "phase": "prepared",
    }
    write_json(work / "plan.json", plan)
    write_json(cache / "pending.json", {"plan": work.name + "/plan.json"})
    progress(100)
    return str(work / "plan.json")


def load_plan(path):
    path = Path(path).resolve()
    plan = read_json(path)
    if not isinstance(plan, dict) or plan.get("schema") != 1:
        raise UpdateError("Некорректный план обновления.")
    target = Path(plan["target"]).resolve()
    if (
        path.name != "plan.json"
        or not re.fullmatch("[a-f0-9]{32}", path.parent.name)
        or path.parent.parent != target / "updates"
    ):
        raise UpdateError("План обновления находится вне своей папки.")
    version(plan["version"])
    return path, plan, target


def pending(root, current):
    root = Path(root).resolve()
    data = read_json(root / "updates/pending.json", {})
    try:
        name = data["plan"]
        safe_name(name)
        path, plan, target = load_plan(root / "updates" / name)
        if (
            target == root
            and plan["phase"] == "prepared"
            and version(plan["version"]) > version(current)
        ):
            return str(path)
    except (UpdateError, KeyError, TypeError):
        pass
    return None


def wait_parent(pid, seconds=60):
    if not pid:
        return
    if os.name == "nt":
        api = ctypes.WinDLL("kernel32", use_last_error=True)
        api.OpenProcess.restype = ctypes.c_void_p
        handle = api.OpenProcess(0x100000, False, int(pid))
        if not handle:
            return
        try:
            api.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
            if api.WaitForSingleObject(handle, int(seconds * 1000)) != 0:
                raise UpdateError("Атлас ещё работает. Закройте его перед обновлением.")
        finally:
            api.CloseHandle.argtypes = [ctypes.c_void_p]
            api.CloseHandle(handle)
    else:
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                return
            time.sleep(0.1)
        raise UpdateError("Атлас ещё работает.")


def replace_file(source, dest):
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".atlas-update-tmp")
    try:
        shutil.copyfile(source, tmp)
        os.replace(tmp, dest)
    finally:
        tmp.unlink(missing_ok=True)


def apply(path, healthcheck=None, restart=True):
    path, plan, target = load_plan(path)
    work = path.parent
    stage = work / "app"
    journal = work / "transaction.json"
    if plan["phase"] != "prepared":
        raise UpdateError("Этот пакет уже применён или требует восстановления.")
    data = validate_descriptor(read_json(stage / DESCRIPTOR))
    if version(data["version"]) != version(plan["version"]):
        raise UpdateError("План и пакет относятся к разным версиям.")
    for name, digest in data["files"].items():
        target_file(target, name)
        if sha256(stage / name) != digest:
            raise UpdateError("Файлы подготовленного обновления повреждены.")
    old = read_json(target / "app-files.json")
    if old:
        validate_descriptor(old)
        if version(data["version"]) <= version(old["version"]):
            raise UpdateError("Эта или более новая версия уже установлена.")
    wait_parent(plan["parent_pid"])
    paths = set(data["files"]) | set((old or {}).get("files", {}))
    records = {}
    backup = work / "backup"
    for name in sorted(paths):
        dest = target_file(target, name)
        if name not in data["files"] and dest.is_file() and sha256(dest) != old["files"][name]:
            continue
        records[name] = {
            "existed": dest.is_file(),
            "sha256": sha256(dest) if dest.is_file() else None,
        }
        if records[name]["existed"]:
            saved = backup / name
            saved.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(dest, saved)
    previous_manifest = (
        (target / "app-files.json").read_bytes() if (target / "app-files.json").exists() else None
    )
    if previous_manifest is not None:
        (work / "previous-app-files.json").write_bytes(previous_manifest)
    write_json(
        journal,
        {"phase": "applying", "files": records, "previous_manifest": previous_manifest is not None},
    )
    try:
        for name in sorted(records, key=lambda n: n == EXE):
            dest = target_file(target, name)
            if name in data["files"]:
                replace_file(stage / name, dest)
            else:
                dest.unlink(missing_ok=True)
        for name, digest in data["files"].items():
            if sha256(target / name) != digest:
                raise UpdateError("Не прошла проверка установленного обновления.")
        write_json(target / "app-files.json", data)
        if healthcheck is None:
            result = subprocess.run(
                [str(target / EXE), "--update-healthcheck", data["version"]],
                cwd=target,
                timeout=40,
                capture_output=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if result.returncode:
                raise UpdateError("Новая версия не прошла проверку запуска.")
        elif not healthcheck(target):
            raise UpdateError("Новая версия не прошла проверку запуска.")
    except Exception as error:
        failures = []
        for name, row in reversed(list(records.items())):
            try:
                dest = target_file(target, name)
                if row["existed"]:
                    replace_file(backup / name, dest)
                else:
                    dest.unlink(missing_ok=True)
            except OSError:
                failures.append(name)
        try:
            if previous_manifest is None:
                (target / "app-files.json").unlink(missing_ok=True)
            else:
                replace_file(work / "previous-app-files.json", target / "app-files.json")
        except OSError:
            failures.append("app-files.json")
        write_json(
            journal,
            {
                "phase": "rollback_failed" if failures else "rolled_back",
                "error": str(error),
                "files": records,
                "failures": failures,
            },
        )
        plan["phase"] = "failed"
        write_json(path, plan)
        if failures:
            raise UpdateError(
                "Не удалось завершить откат. Резервная копия: " + str(backup)
            ) from error
        raise UpdateError(
            "Обновление отменено; прежняя версия восстановлена. " + str(error)
        ) from error
    plan["phase"] = "installed"
    write_json(path, plan)
    write_json(journal, {"phase": "installed", "version": data["version"], "files": records})
    write_json(
        target / "updates/last-result.json",
        {"ok": True, "version": data["version"], "backup": str(backup)},
    )
    if restart and plan.get("restart"):
        subprocess.Popen([str(target / EXE)], cwd=target)
    return data["version"]


def launch(root, path, restart):
    path, plan, target = load_plan(path)
    if target != Path(root).resolve():
        raise UpdateError("Пакет подготовлен для другой папки атласа.")
    if not getattr(sys, "frozen", False):
        raise UpdateError("Перезапуск с обновлением доступен в собранном EXE.")
    plan.update(parent_pid=os.getpid(), restart=bool(restart))
    write_json(path, plan)
    exe = path.parent / "app" / EXE
    subprocess.Popen(
        [str(exe), "--apply-update", str(path)],
        cwd=path.parent / "app",
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def instance_lock(root):
    if os.name != "nt":
        return None
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.CreateMutexW.restype = ctypes.c_void_p
    api.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
    key = hashlib.sha256(str(Path(root).resolve()).casefold().encode()).hexdigest()[:24]
    handle = api.CreateMutexW(None, False, "Local\\PWResourceAtlas-" + key)
    if not handle:
        raise UpdateError("Не удалось проверить запущенные экземпляры атласа.")
    if ctypes.get_last_error() == 183:
        release_lock(handle)
        raise UpdateError("Атлас из этой папки уже запущен.")
    return handle


def release_lock(handle):
    if handle and os.name == "nt":
        api = ctypes.WinDLL("kernel32", use_last_error=True)
        api.CloseHandle.argtypes = [ctypes.c_void_p]
        api.CloseHandle(handle)


def register_current(root, current):
    root = Path(root)
    if (root / "app-files.json").exists():
        return
    data = read_json(root / DESCRIPTOR)
    if data:
        validate_descriptor(data)
        if (
            version(data["version"]) == version(current)
            and sha256(root / EXE) == data["files"][EXE]
        ):
            write_json(root / "app-files.json", data)


def helper_main(path):
    handle = None
    plan = {}
    target = None
    try:
        _, plan, target = load_plan(path)
        wait_parent(plan["parent_pid"])
        handle = instance_lock(target)
        apply(path, restart=False)
    except Exception as error:
        message = str(error)
        try:
            if target:
                write_json(
                    target / "updates/last-result.json",
                    {"ok": False, "error": message, "backup": str(Path(path).parent / "backup")},
                )
        except Exception:
            pass
        if os.name == "nt":
            ctypes.windll.user32.MessageBoxW(None, message, "Обновление PW Resource Atlas", 0x10)
        result = 1
    else:
        result = 0
    finally:
        release_lock(handle)
    if target and plan.get("restart"):
        try:
            subprocess.Popen([str(target / EXE)], cwd=target)
        except OSError:
            pass
    return result
