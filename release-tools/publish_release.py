"""Publish a verified OTA package using the owner's local Git credential helper.

Credentials stay in memory, never in the app, files, logs or release assets.
By default the release stays a draft; --publish makes it available to clients.
"""

from pathlib import Path
import argparse
import hashlib
import json
import os
import subprocess
import sys
import urllib.request
import urllib.error
import urllib.parse


def publish(folder, repo, publish_now=False):
    folder = Path(folder).resolve()
    owner, project = repo.split("/")
    api = "https://api.github.com"
    token = os.environ.get("GITHUB_TOKEN")
    ci_token = bool(token)
    if not token:
        r = subprocess.run(
            ["git", "credential", "fill"],
            input="protocol=https\nhost=github.com\nusername=" + owner + "\n\n",
            text=True,
            capture_output=True,
            timeout=15,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "Never"},
        )
        fields = dict(line.split("=", 1) for line in r.stdout.splitlines() if "=" in line)
        token = fields.get("password")
    if not token:
        raise RuntimeError(
            "Авторизуйтесь в GitHub через Git/Git Credential Manager; пароль или токен в файлы программы добавлять не нужно."
        )
    headers = {
        "Authorization": "Bearer " + token,
        "User-Agent": "PW-Resource-Atlas-Publisher",
        "Accept": "application/vnd.github+json",
    }

    def request(method, url, data=None, content_type="application/json", length=None):
        if not url.startswith(("https://api.github.com/", "https://uploads.github.com/")):
            raise ValueError("Unexpected GitHub endpoint")
        if isinstance(data, dict):
            data = json.dumps(data, ensure_ascii=False).encode("utf-8")
        extra = {"Content-Type": content_type}
        if length is not None:
            extra["Content-Length"] = str(length)
        try:
            with urllib.request.urlopen(
                urllib.request.Request(url, data=data, headers={**headers, **extra}, method=method),
                timeout=300,
            ) as response:
                raw = response.read()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as error:
            try:
                message = json.loads(error.read(8192)).get("message", "")
            except ValueError:
                message = ""
            raise RuntimeError(f"GitHub: {error.code} {message}") from None

    if not ci_token:
        user = request("GET", api + "/user")
        if user["login"].casefold() != owner.casefold():
            raise RuntimeError("Локальная авторизация GitHub принадлежит другому пользователю.")
    repository = request("GET", api + "/repos/" + repo)
    if not ci_token and not repository.get("permissions", {}).get("push"):
        raise RuntimeError("Нет права публикации в этом репозитории.")
    if repository["private"] and publish_now:
        raise RuntimeError(
            "Для обновлений без авторизации нужен публичный репозиторий. В приватном можно подготовить черновик без --publish."
        )
    feed = json.loads((folder / "atlas-release.json").read_text(encoding="utf-8"))
    package = folder / feed["package"]["name"]

    def digest(path):
        h = hashlib.sha256()
        with path.open("rb") as f:
            for block in iter(lambda: f.read(1024 * 1024), b""):
                h.update(block)
        return h.hexdigest()

    if (
        digest(package) != feed["package"]["sha256"]
        or package.stat().st_size != feed["package"]["bytes"]
    ):
        raise RuntimeError("Пакет изменился после сборки.")
    tag = "v" + feed["version"]
    base = api + "/repos/" + repo + "/releases"
    existing = request("GET", base + "?per_page=30")
    release = next((r for r in existing if r["tag_name"] == tag), None)
    if release and not release["draft"]:
        raise RuntimeError(
            "Эта версия уже опубликована. Увеличьте VERSION и соберите следующий релиз."
        )
    if not release:
        release = request(
            "POST",
            base,
            {
                "tag_name": tag,
                "target_commitish": repository["default_branch"],
                "name": "PW Resource Atlas " + feed["version"],
                "body": feed.get("notes", ""),
                "draft": True,
                "prerelease": False,
            },
        )
    rid = release["id"]
    assets = request("GET", base + "/" + str(rid) + "/assets")
    upload = "https://uploads.github.com/repos/" + repo + "/releases/" + str(rid) + "/assets"
    names = [package.name, "atlas-release.json", "SHA256SUMS.txt"]
    for name in names:
        path = folder / name
        old = next((a for a in assets if a["name"] == name), None)
        if old:
            if old.get("digest") == "sha256:" + digest(path) and old["size"] == path.stat().st_size:
                continue
            request("DELETE", base + "/assets/" + str(old["id"]))
        print("Публикация файла: " + name, flush=True)
        with path.open("rb") as data:
            asset = request(
                "POST",
                upload + "?name=" + urllib.parse.quote(name),
                data,
                "application/zip" if name.endswith(".zip") else "application/octet-stream",
                path.stat().st_size,
            )
        if asset["size"] != path.stat().st_size or asset.get("digest") not in (
            None,
            "sha256:" + digest(path),
        ):
            raise RuntimeError("GitHub не подтвердил целостность загруженного файла.")
    release = request(
        "PATCH",
        base + "/" + str(rid),
        {
            "draft": not publish_now,
            "make_latest": "true" if publish_now else "false",
            "body": feed.get("notes", ""),
        },
    )
    print(
        ("Опубликовано: " if publish_now else "Черновик готов: ") + release["html_url"], flush=True
    )
    return release["html_url"]


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--package-dir", required=True, type=Path)
    p.add_argument("--repo", default="Aqwrr/pw-resource-altas")
    p.add_argument("--publish", action="store_true")
    a = p.parse_args()
    try:
        publish(a.package_dir, a.repo, a.publish)
    except Exception as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
