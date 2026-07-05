"""Auto-download and cache luau-lsp + selene binaries and Roblox type definitions.

On first run, downloads everything needed to ~/.luau-lens/.
On subsequent runs, uses cached files.
Type definitions are re-downloaded if older than 7 days.
"""

from __future__ import annotations

import io
import os
import platform
import shutil
import stat
import sys
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

CACHE_DIR = Path.home() / ".luau-lens"
BIN_DIR = CACHE_DIR / "bin"
DEFS_DIR = CACHE_DIR / "defs"
CONFIG_DIR = CACHE_DIR / "config"

# Type definitions URL (maintained by JohnnyMorganz/luau-lsp)
# Full API types — not PluginSecurity subset, which would cause false positives for game scripts
DEFS_URL = "https://luau-lsp.pages.dev/type-definitions/globalTypes.d.luau"
DEFS_FILENAME = "globalTypes.d.luau"

# Binary download URLs (filled by _get_urls)
LUAU_LSP_VERSION = "1.68.1"
SELENE_VERSION = "0.31.0"
STYLUA_VERSION = "2.5.2"

# Re-download definitions if older than this (seconds)
DEFS_MAX_AGE = 7 * 24 * 60 * 60  # 7 days

_ensure_done = False
_ready = False
_last_error: str | None = None


# ---------------------------------------------------------------------------
# Platform detection
# ---------------------------------------------------------------------------

def _get_platform() -> tuple[str, str]:
    """Return (os_name, arch) for download URL selection."""
    os_name = platform.system().lower()
    machine = platform.machine().lower()

    if os_name == "windows":
        return "windows", "x86_64"
    if os_name == "darwin":
        if "arm" in machine or "aarch" in machine:
            return "macos", "arm64"
        return "macos", "x86_64"

    # linux
    if "arm" in machine or "aarch" in machine:
        return "linux", "arm64"
    return "linux", "x86_64"


def _get_urls() -> dict[str, str]:
    os_name, arch = _get_platform()
    base = {
        "luau-lsp": {
            ("windows", "x86_64"): f"https://github.com/JohnnyMorganz/luau-lsp/releases/download/{LUAU_LSP_VERSION}/luau-lsp-win64.zip",
            ("macos", "arm64"): f"https://github.com/JohnnyMorganz/luau-lsp/releases/download/{LUAU_LSP_VERSION}/luau-lsp-macos.zip",
            ("macos", "x86_64"): f"https://github.com/JohnnyMorganz/luau-lsp/releases/download/{LUAU_LSP_VERSION}/luau-lsp-macos.zip",
            ("linux", "x86_64"): f"https://github.com/JohnnyMorganz/luau-lsp/releases/download/{LUAU_LSP_VERSION}/luau-lsp-linux-x86_64.zip",
            ("linux", "arm64"): f"https://github.com/JohnnyMorganz/luau-lsp/releases/download/{LUAU_LSP_VERSION}/luau-lsp-linux-arm64.zip",
        },
        "selene": {
            ("windows", "x86_64"): f"https://github.com/Kampfkarren/selene/releases/download/{SELENE_VERSION}/selene-{SELENE_VERSION}-windows.zip",
            ("macos", "arm64"): f"https://github.com/Kampfkarren/selene/releases/download/{SELENE_VERSION}/selene-{SELENE_VERSION}-macos.zip",
            ("macos", "x86_64"): f"https://github.com/Kampfkarren/selene/releases/download/{SELENE_VERSION}/selene-{SELENE_VERSION}-macos.zip",
            ("linux", "x86_64"): f"https://github.com/Kampfkarren/selene/releases/download/{SELENE_VERSION}/selene-{SELENE_VERSION}-linux.zip",
            ("linux", "arm64"): f"https://github.com/Kampfkarren/selene/releases/download/{SELENE_VERSION}/selene-{SELENE_VERSION}-linux.zip",
        },
        "stylua": {
            ("windows", "x86_64"): f"https://github.com/JohnnyMorganz/StyLua/releases/download/v{STYLUA_VERSION}/stylua-windows-x86_64.zip",
            ("macos", "arm64"): f"https://github.com/JohnnyMorganz/StyLua/releases/download/v{STYLUA_VERSION}/stylua-macos-aarch64.zip",
            ("macos", "x86_64"): f"https://github.com/JohnnyMorganz/StyLua/releases/download/v{STYLUA_VERSION}/stylua-macos-x86_64.zip",
            ("linux", "x86_64"): f"https://github.com/JohnnyMorganz/StyLua/releases/download/v{STYLUA_VERSION}/stylua-linux-x86_64.zip",
            ("linux", "arm64"): f"https://github.com/JohnnyMorganz/StyLua/releases/download/v{STYLUA_VERSION}/stylua-linux-aarch64.zip",
        },
    }
    return {
        "luau-lsp": base["luau-lsp"][(os_name, arch)],
        "selene": base["selene"][(os_name, arch)],
        "stylua": base["stylua"][(os_name, arch)],
    }


# ---------------------------------------------------------------------------
# Binary name per platform
# ---------------------------------------------------------------------------

def _exe(name: str) -> str:
    return f"{name}.exe" if platform.system() == "Windows" else name


# ---------------------------------------------------------------------------
# Download helpers
# ---------------------------------------------------------------------------

def _download(url: str, dest: Path, timeout: int = 60) -> None:
    """Download a URL to dest with a progress indicator on stderr."""
    req = urllib.request.Request(url, headers={"User-Agent": "luau-lens/bootstrap"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        total = int(resp.headers.get("Content-Length", 0))
        downloaded = 0
        with open(dest, "wb") as f:
            while True:
                chunk = resp.read(65536)
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)
                if total:
                    pct = downloaded * 100 // total
                    print(f"\r  downloading {dest.name}: {pct}%", end="", file=sys.stderr)
        if total:
            print(file=sys.stderr)


def _download_and_extract_zip(url: str, dest_dir: Path) -> None:
    """Download a zip and extract its contents into dest_dir."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        _download(url, tmp_path)
        with zipfile.ZipFile(tmp_path) as zf:
            zf.extractall(dest_dir)
        # Make binaries executable on unix
        if platform.system() != "Windows":
            for p in dest_dir.iterdir():
                if p.is_file() and not p.suffix:
                    p.chmod(p.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    finally:
        tmp_path.unlink(missing_ok=True)


def _download_file(url: str, dest: Path) -> None:
    """Download a single file to dest."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    _download(url, dest)


# ---------------------------------------------------------------------------
# Config file generation
# ---------------------------------------------------------------------------

SELENE_TOML = 'std = "roblox"\n'
LUAURC = '{\n  "languageMode": "strict"\n}\n'


def _write_configs() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    selene_toml = CONFIG_DIR / "selene.toml"
    luaurc = CONFIG_DIR / ".luaurc"
    if not selene_toml.exists():
        selene_toml.write_text(SELENE_TOML)
    if not luaurc.exists():
        luaurc.write_text(LUAURC)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def is_ready() -> bool:
    return _ready


def last_error() -> str | None:
    """Return the last bootstrap error, or None if bootstrap succeeded."""
    return _last_error


def ensure_tools() -> None:
    """Download all required tools if not present. Called once on startup.

    If a previous attempt failed, calling again will retry the download.
    """
    global _ensure_done, _ready, _last_error

    # If already ready, skip. If a previous attempt failed (_ready=False but
    # _ensure_done=True), allow retry by resetting _ensure_done.
    if _ready:
        return
    _ensure_done = True
    _last_error = None

    urls = _get_urls()
    BIN_DIR.mkdir(parents=True, exist_ok=True)
    DEFS_DIR.mkdir(parents=True, exist_ok=True)

    # luau-lsp binary
    luau_lsp_path = BIN_DIR / _exe("luau-lsp")
    if not luau_lsp_path.exists():
        print(f"[luau-lens] downloading luau-lsp v{LUAU_LSP_VERSION}...", file=sys.stderr)
        try:
            _download_and_extract_zip(urls["luau-lsp"], BIN_DIR)
        except Exception as e:
            _last_error = f"Failed to download luau-lsp: {e}"
            print(f"[luau-lens] ERROR: {_last_error}", file=sys.stderr)
            return
        if not luau_lsp_path.exists():
            _last_error = "luau-lsp binary not found after extraction"
            print(f"[luau-lens] ERROR: {_last_error}", file=sys.stderr)
            return

    # selene binary
    selene_path = BIN_DIR / _exe("selene")
    if not selene_path.exists():
        print(f"[luau-lens] downloading selene v{SELENE_VERSION}...", file=sys.stderr)
        try:
            _download_and_extract_zip(urls["selene"], BIN_DIR)
        except Exception as e:
            print(f"[luau-lens] WARNING: selene download failed: {e}, linting will be skipped", file=sys.stderr)
        else:
            if not selene_path.exists():
                print(f"[luau-lens] WARNING: selene binary not found, linting will be skipped", file=sys.stderr)

    # stylua binary
    stylua_path = BIN_DIR / _exe("stylua")
    if not stylua_path.exists():
        print(f"[luau-lens] downloading stylua v{STYLUA_VERSION}...", file=sys.stderr)
        try:
            _download_and_extract_zip(urls["stylua"], BIN_DIR)
        except Exception as e:
            print(f"[luau-lens] WARNING: stylua download failed: {e}, formatting will be skipped", file=sys.stderr)
        else:
            if not stylua_path.exists():
                print(f"[luau-lens] WARNING: stylua binary not found, formatting will be skipped", file=sys.stderr)

    # Roblox type definitions (re-download if stale)
    defs_path = DEFS_DIR / DEFS_FILENAME
    need_defs = not defs_path.exists()
    if defs_path.exists():
        age = time.time() - defs_path.stat().st_mtime
        if age > DEFS_MAX_AGE:
            need_defs = True
            print("[luau-lens] refreshing Roblox type definitions (stale)...", file=sys.stderr)
    if need_defs:
        print("[luau-lens] downloading Roblox type definitions...", file=sys.stderr)
        try:
            _download_file(DEFS_URL, defs_path)
        except Exception as e:
            _last_error = f"Failed to download type definitions: {e}"
            print(f"[luau-lens] ERROR: {_last_error}", file=sys.stderr)
            return

    # Config files
    _write_configs()

    # Warn if selene was downloaded but is the wrong architecture (no native arm64 Linux build)
    os_name, arch = _get_platform()
    if os_name == "linux" and arch == "arm64" and selene_path.exists():
        print("[luau-lens] WARNING: selene has no native Linux arm64 build; linting may not work on this platform", file=sys.stderr)

    _ready = True
    print("[luau-lens] ready", file=sys.stderr)


def get_paths() -> dict[str, Path]:
    """Return paths to all tools. Call ensure_tools() first."""
    return {
        "luau_lsp": BIN_DIR / _exe("luau-lsp"),
        "selene": BIN_DIR / _exe("selene"),
        "stylua": BIN_DIR / _exe("stylua"),
        "defs": DEFS_DIR / DEFS_FILENAME,
        "selene_toml": CONFIG_DIR / "selene.toml",
        "luaurc": CONFIG_DIR / ".luaurc",
    }


def has_selene() -> bool:
    """Check if selene binary exists."""
    return (BIN_DIR / _exe("selene")).exists()


def has_stylua() -> bool:
    """Check if stylua binary exists."""
    return (BIN_DIR / _exe("stylua")).exists()
