"""Build a clean, relocatable Windows folder using this installation's runtime.

No downloads, registry edits, installers or user data are needed. The copied
runtime uses relative ._pth entries; see Python's official Windows embedding
documentation: https://docs.python.org/3/using/windows.html#finding-modules
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import sys

ROOT = Path(__file__).resolve().parent
ROOT_FILES = (
    "run.py", "run.pyw", "suite_bootstrap.py", "requirements.txt", ".env.example",
    "Start Lead Workspace.bat", "Start Lead Workspace.vbs", "Run_Combined.bat",
    "Setup_Combined.bat", "Check This Computer.bat", "portable_check.py",
    "Create Portable Copy.bat", "make_portable.py", "PORTABLE_README.txt", "USABILITY_GUIDE.md", "DATABASE_LOOKUP_GUIDE.md", "FORMULAS_GUIDE.md",
    "team_server.py", "Start Team Workspace.vbs", "Start Local Research.vbs", "Setup Team Server.bat", "Start Team Server.ps1", "Stop Team Server.ps1", "Status Team Server.ps1",
    "Start Team Server.bat", "Stop Team Server.bat", "Status Team Server.bat", "MULTIUSER_SETUP.md", "MULTIUSER_IMPLEMENTATION.md",
)


def filesystem_path(path):
    path = str(Path(path).resolve())
    if os.name != "nt" or path.startswith("\\\\?\\"):
        return Path(path)
    return Path("\\\\?\\UNC\\" + path[2:] if path.startswith("\\\\") else "\\\\?\\" + path)


def copy_tree(source, target, *, source_code=False):
    """Copy regular files only. Exclude runtime state and machine-specific caches."""
    excluded = {"__pycache__", ".git", ".pytest_cache", ".links", "gen_py"}
    if source_code:
        excluded |= {"data", "Data", "Logs", "Output"}
    for parent, dirs, files in os.walk(source):
        parent = Path(parent)
        dirs[:] = [name for name in dirs if name not in excluded and not name.startswith("objects-")
                   and not (parent / name).is_symlink()
                   and not (parent / name).is_junction()]
        relative = parent.relative_to(source)
        for name in files:
            file = parent / name
            if file.is_symlink() or name.endswith((".pyc", ".pyo")):
                continue
            if source_code and (name.startswith(("test_", "repair_", "verify_"))
                                or file.suffix not in {".py", ".json", ".svg", ".png", ".ico", ".qss"}):
                continue
            out = target / relative / name
            try:
                filesystem_path(out.parent).mkdir(parents=True, exist_ok=True)
                shutil.copy2(filesystem_path(file), filesystem_path(out))
            except OSError as exc:
                raise OSError(f"Could not copy {file} to {out}: {exc}") from exc


def build(destination=None, *, include_qwen=True):
    if sys.platform != "win32" or platform.machine().lower() not in {"amd64", "x86_64"}:
        raise RuntimeError("Build this Windows x64 package with a Windows x64 Python runtime.")
    default = ROOT / "Portable" / "Lead Workspace"
    if destination is None and default.exists():
        default = default.with_name("Lead Workspace " + datetime.now().strftime("%Y%m%d-%H%M%S"))
    target = Path(destination or default).resolve()
    if target.exists():
        raise FileExistsError("Destination already exists; choose a new folder. Nothing was overwritten.")
    if target == ROOT or target in ROOT.parents:
        raise ValueError("The destination must be a new folder.")
    base = Path(sys.base_prefix)
    dll = f"python{sys.version_info.major}{sys.version_info.minor}.dll"
    for required in (base / "python.exe", base / dll, base / "Lib" / "encodings"):
        if not required.exists():
            raise RuntimeError(f"The build runtime is incomplete: {required}")
    if not (ROOT / "runtime" / "browsers").is_dir():
        raise RuntimeError("Run Setup_Combined.bat once to install the bundled Chromium files.")
    if include_qwen and not list((ROOT / "runtime" / "qwen").glob("*.gguf")):
        raise RuntimeError("Qwen assets are missing. Use --without-qwen for a smaller package.")
    target.parent.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(target.parent).free < (7 if include_qwen else 3) * 1024**3:
        raise RuntimeError("Not enough free space to prepare the portable folder.")
    target.mkdir()
    populate(target, base, dll, include_qwen)
    return target


def populate(target, base, dll, include_qwen):
    """Populate a new build directory. Public build() rejects existing targets."""
    print("Copying application source and launchers...", flush=True)
    for directory in ("app", "scraper_engine"):
        copy_tree(ROOT / directory, target / directory, source_code=True)
    for name in ROOT_FILES:
        shutil.copy2(ROOT / name, target / name)
    print("Copying Python and installed libraries...", flush=True)
    runtime = target / "runtime" / "python"
    runtime.mkdir(parents=True, exist_ok=True)
    for file in base.iterdir():
        if file.is_file() and (file.suffix.lower() in {".exe", ".dll"} or file.name == "LICENSE.txt"):
            shutil.copy2(file, runtime / file.name)
    copy_tree(base / "DLLs", runtime / "DLLs")
    copy_tree(base / "Lib", runtime / "Lib")
    # This project's environment inherits installed libraries. Its own versions
    # override the base installation exactly as they do in the working app.
    overlay = Path(sys.prefix) / "Lib" / "site-packages"
    if sys.prefix != sys.base_prefix and overlay.exists():
        copy_tree(overlay, runtime / "Lib" / "site-packages")
    (runtime / dll.replace(".dll", "._pth")).write_text(
        "Lib\nDLLs\nLib/site-packages\n../../.\n../../scraper_engine\nimport site\n", encoding="utf-8")
    print("Copying bundled Chromium...", flush=True)
    copy_tree(ROOT / "runtime" / "browsers", target / "runtime" / "browsers")
    if include_qwen:
        print("Copying the optional Qwen runtime and model...", flush=True)
        qwen = target / "runtime" / "qwen"
        qwen.mkdir(parents=True, exist_ok=True)
        for file in (ROOT / "runtime" / "qwen").iterdir():
            if file.is_file() and (file.suffix.lower() in {".exe", ".dll", ".gguf"} or file.name.lower().startswith("license")):
                shutil.copy2(file, qwen / file.name)
    for directory in ("Data", "Logs", "Output"):
        (target / directory).mkdir(exist_ok=True)
    hashes = {}
    for directory in ("app", "scraper_engine"):
        for file in (target / directory).rglob("*"):
            if file.is_file():
                hashes[file.relative_to(target).as_posix()] = hashlib.sha256(file.read_bytes()).hexdigest()
    for name in ROOT_FILES:
        hashes[name] = hashlib.sha256((target / name).read_bytes()).hexdigest()
    manifest = {"created_utc": datetime.now(timezone.utc).isoformat(), "platform": "Windows x64",
                "python": sys.version.split()[0], "includes_qwen": include_qwen,
                "fresh_data": True, "source_sha256": hashes}
    (target / "portable_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Portable folder created:\n{target}\nRun Check This Computer.bat, then Start Lead Workspace.bat.", flush=True)
    return target


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--without-qwen", action="store_true")
    args = parser.parse_args()
    try:
        build(args.output, include_qwen=not args.without_qwen)
    except Exception as exc:
        print(f"Portable build failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
