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
DEFS_URL = "https://luau-lsp.pages.dev/type-definitions/globalTypes.PluginSecurity.d.luau"
DEFS_FILENAME = "globalTypes.d.luau"

# Binary download URLs (filled by _get_urls)
LUAU_LSP_VERSION = "1.68.1"
SELENE_VERSION = "0.31.0"

# Re-download definitions if older than this (seconds)
DEFS_MAX_AGE = 7 * 24 * 60 * 60  # 7 days

_ensure_done = False
_ready = False


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
        return "macos", "universal"  # macos zip is universal

    # linux
    if "arm" in machine or "aarch" in machine:
        return "linux", "arm64"
    return "linux", "x86_64"


def _get_urls() -> dict[str, str]:
    os_name, arch = _get_platform()
    base = {
        "luau-lsp": {
            ("windows", "x86_64"): f"https://github.com/JohnnyMorganz/luau-lsp/releases/download/{LUAU_LSP_VERSION}/luau-lsp-win64.zip",
            ("macos", "universal"): f"https://github.com/JohnnyMorganz/luau-lsp/releases/download/{LUAU_LSP_VERSION}/luau-lsp-macos.zip",
            ("linux", "x86_64"): f"https://github.com/JohnnyMorganz/luau-lsp/releases/download/{LUAU_LSP_VERSION}/luau-lsp-linux-x86_64.zip",
            ("linux", "arm64"): f"https://github.com/JohnnyMorganz/luau-lsp/releases/download/{LUAU_LSP_VERSION}/luau-lsp-linux-arm64.zip",
        },
        "selene": {
            ("windows", "x86_64"): f"https://github.com/Kampfkarren/selene/releases/download/{SELENE_VERSION}/selene-{SELENE_VERSION}-windows.zip",
            ("macos", "universal"): f"https://github.com/Kampfkarren/selene/releases/download/{SELENE_VERSION}/selene-{SELENE_VERSION}-macos.zip",
            ("linux", "x86_64"): f"https://github.com/Kampfkarren/selene/releases/download/{SELENE_VERSION}/selene-{SELENE_VERSION}-linux.zip",
            ("linux", "arm64"): f"https://github.com/Kampfkarren/selene/releases/download/{SELENE_VERSION}/selene-{SELENE_VERSION}-linux.zip",
        },
    }
    return {
        "luau-lsp": base["luau-lsp"][(os_name, arch)],
        "selene": base["selene"][(os_name, arch)],
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


def ensure_tools() -> None:
    """Download all required tools if not present. Called once on startup."""
    global _ensure_done, _ready
    if _ensure_done:
        return
    _ensure_done = True

    urls = _get_urls()
    BIN_DIR.mkdir(parents=True, exist_ok=True)
    DEFS_DIR.mkdir(parents=True, exist_ok=True)

    # luau-lsp binary
    luau_lsp_path = BIN_DIR / _exe("luau-lsp")
    if not luau_lsp_path.exists():
        print(f"[luau-lens] downloading luau-lsp v{LUAU_LSP_VERSION}...", file=sys.stderr)
        _download_and_extract_zip(urls["luau-lsp"], BIN_DIR)
        if not luau_lsp_path.exists():
            print(f"[luau-lens] ERROR: luau-lsp binary not found after extraction", file=sys.stderr)
            _ready = False
            return

    # selene binary
    selene_path = BIN_DIR / _exe("selene")
    if not selene_path.exists():
        print(f"[luau-lens] downloading selene v{SELENE_VERSION}...", file=sys.stderr)
        _download_and_extract_zip(urls["selene"], BIN_DIR)
        if not selene_path.exists():
            print(f"[luau-lens] WARNING: selene binary not found, linting will be skipped", file=sys.stderr)

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
        _download_file(DEFS_URL, defs_path)

    # Config files
    _write_configs()

    _ready = True
    print("[luau-lens] ready", file=sys.stderr)


def get_paths() -> dict[str, Path]:
    """Return paths to all tools. Call ensure_tools() first."""
    return {
        "luau_lsp": BIN_DIR / _exe("luau-lsp"),
        "selene": BIN_DIR / _exe("selene"),
        "defs": DEFS_DIR / DEFS_FILENAME,
        "selene_toml": CONFIG_DIR / "selene.toml",
        "luaurc": CONFIG_DIR / ".luaurc",
    }


def has_selene() -> bool:
    """Check if selene binary exists."""
    return (BIN_DIR / _exe("selene")).exists()
