#!/usr/bin/env python3
"""Freeze launcher.py into a self-contained MH3U_Online.exe.

Mirrors the conventions in e:\\mh3ureversing\\dist_build\\pyi (that's how
server.exe is frozen): PyInstaller onefile, UPX on, no console. The launcher is
STDLIB-ONLY, so there are NO hidden-imports / collect_all calls like the server
spec needs — tkinter is bundled automatically by PyInstaller's own hooks.

Usage:
    python build_launcher.py            # build MH3U_Online.exe into ./dist
    python build_launcher.py --stamp v0.1.7-beta   # also write version.txt

The resulting dist/MH3U_Online.exe drops into the bundle ROOT, next to
Cemu_release.exe (player bundle) and, when hosting, server.exe. version.txt
must sit beside it — see the stamping note at the bottom.
"""
import os
import sys
import shutil
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
ENTRY = HERE / "launcher.py"
NAME = "MH3U_Online"


def build():
    # Match the server build: onefile, windowed (no console), UPX on.
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--noconsole",              # windowed app — no black console box
        "--name", NAME,
        "--distpath", str(HERE / "dist"),
        "--workpath", str(HERE / "build"),
        "--specpath", str(HERE),
        "--clean",
        "--noconfirm",
        str(ENTRY),
    ]
    # UPX if it's on PATH (the server spec uses upx=True); harmless if absent.
    print("running:", " ".join(cmd))
    subprocess.check_call(cmd)
    exe = HERE / "dist" / (NAME + ".exe")
    print("built:", exe, "(", exe.stat().st_size, "bytes )" if exe.exists() else "(missing!)")
    return exe


def stamp_version(tag):
    """Write version.txt next to the built exe. The bundle build should copy
    BOTH MH3U_Online.exe and version.txt into the bundle root."""
    vt = HERE / "dist" / "version.txt"
    vt.write_text(tag.strip() + "\n", newline="\n", encoding="utf-8")
    print("stamped:", vt, "=", tag)


if __name__ == "__main__":
    tag = None
    args = sys.argv[1:]
    if "--stamp" in args:
        i = args.index("--stamp")
        tag = args[i + 1]
    build()
    if tag:
        stamp_version(tag)
    print()
    print("Next: copy dist/MH3U_Online.exe (and dist/version.txt) into the bundle")
    print("root — the same folder that holds Cemu_release.exe / server.exe.")
