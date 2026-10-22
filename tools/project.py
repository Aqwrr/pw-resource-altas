"""One entry point for local development and GitHub Actions."""

from pathlib import Path
import ast
import os
import shutil
import subprocess
import sys

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "tools"))
BUILD = PROJECT / "build"
ASSETS = Path(os.environ.get("ATLAS_ASSETS_DIR", PROJECT / ".cache/assets")).resolve()
SOURCE = PROJECT / "src"
DIST = BUILD / "dist/PW-Resource-Atlas"


def run(*args, env=None):
    subprocess.run([str(arg) for arg in args], cwd=PROJECT, env=env, check=True)


def version():
    tree = ast.parse((SOURCE / "atlas_core.py").read_text(encoding="utf-8"))
    return next(
        ast.literal_eval(n.value)
        for n in tree.body
        if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "VERSION" for t in n.targets)
    )


def assets():
    from fetch_assets import fetch

    fetch(ASSETS)


def lint():
    run(sys.executable, "-m", "ruff", "check", "src", "tests", "tools", "release-tools")
    run(sys.executable, "-m", "ruff", "format", "--check", "src", "tests", "tools", "release-tools")


def test():
    assets()
    env = {
        **os.environ,
        "PYTHONIOENCODING": "utf-8",
        "PYTHONPATH": str(SOURCE),
        "ATLAS_ASSETS_DIR": str(ASSETS),
        "QT_QPA_PLATFORM": "offscreen",
    }
    for script in sorted((PROJECT / "tests").glob("verify_*.py")):
        for scale in (
            ("1", "1.5") if script.stem in ("verify_ux", "verify_help", "verify_access") else ("1",)
        ):
            print(f"Проверка: {script.name}, масштаб {scale}", flush=True)
            run(sys.executable, script, env={**env, "QT_SCALE_FACTOR": scale})


def build():
    if sys.platform != "win32":
        raise RuntimeError("Windows-сборка создаётся на Windows.")
    assets()
    run(
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--windowed",
        "--onedir",
        "--name",
        "PW-Resource-Atlas",
        "--icon",
        ASSETS / "atlas.ico",
        "--add-data",
        str(ASSETS) + os.pathsep + "assets",
        "--distpath",
        BUILD / "dist",
        "--workpath",
        BUILD / "pyinstaller",
        "--specpath",
        BUILD,
        SOURCE / "atlas_app.py",
    )
    # These DLLs shadow the Windows ICU used by Qt and cause startup crashes.
    for name in ("icuuc.dll", "icudt78.dll"):
        (DIST / "_internal" / name).unlink(missing_ok=True)
    shutil.copytree(
        PROJECT / "third-party-licenses", DIST / "third-party-licenses", dirs_exist_ok=True
    )
    run(DIST / "PW-Resource-Atlas.exe", "--update-healthcheck", version())


def package():
    if not (DIST / "PW-Resource-Atlas.exe").is_file():
        raise RuntimeError("Сначала выполните make build.")
    run(DIST / "PW-Resource-Atlas.exe", "--update-healthcheck", version())
    run(
        sys.executable,
        PROJECT / "release-tools/build_release.py",
        "--bundle",
        DIST,
        "--output",
        BUILD / "releases" / version(),
        "--notes",
        PROJECT / "release-notes" / (version() + ".md"),
    )


def main(task):
    if task == "help":
        print(
            "deps — зависимости; assets — ресурсы; run — запуск; lint / format — стиль; test — проверки; build — EXE; package — OTA-архив; release — проверки + сборка + архив; publish — публикация готового релиза; clean — удалить только build/."
        )
    elif task == "deps":
        run(sys.executable, "-m", "pip", "install", "-r", "requirements-dev.txt")
    elif task == "assets":
        assets()
    elif task == "run":
        assets()
        run(
            sys.executable,
            SOURCE / "atlas_app.py",
            env={**os.environ, "ATLAS_ASSETS_DIR": str(ASSETS)},
        )
    elif task == "lint":
        lint()
    elif task == "format":
        run(
            sys.executable, "-m", "ruff", "check", "--fix", "src", "tests", "tools", "release-tools"
        )
        run(sys.executable, "-m", "ruff", "format", "src", "tests", "tools", "release-tools")
    elif task == "test":
        test()
    elif task == "build":
        build()
    elif task == "package":
        package()
    elif task == "release":
        lint()
        test()
        build()
        package()
    elif task == "publish":
        run(
            sys.executable,
            PROJECT / "release-tools/publish_release.py",
            "--package-dir",
            BUILD / "releases" / version(),
            "--publish",
        )
    elif task == "clean":
        if BUILD.is_symlink() or BUILD.resolve() != PROJECT / "build":
            raise ValueError("Очистка разрешена только для build внутри репозитория.")
        if BUILD.exists():
            shutil.rmtree(BUILD)
    else:
        raise ValueError("Неизвестная команда: " + task)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "help")
