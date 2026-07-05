"""Subprocess wrappers for luau-lsp analyze, selene, and stylua."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

from . import bootstrap
from .parsers import Diagnostic, merge_diagnostics, parse_luau_lsp, parse_selene, to_dict


def _run(cmd: list[str], cwd: str | None = None, timeout: int = 30,
         stdin_input: str | None = None) -> tuple[str, str, int]:
    """Run a command and return (stdout, stderr, exit_code).

    Handles timeout, missing binary, and signal-based crashes (segfault etc).
    """
    try:
        proc = subprocess.run(
            cmd,
            input=stdin_input,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
        )
        return proc.stdout, proc.stderr, proc.returncode
    except subprocess.TimeoutExpired:
        return "", f"Command timed out after {timeout}s: {' '.join(cmd)}", -1
    except FileNotFoundError:
        return "", f"Binary not found: {cmd[0]}", -1


# ---------------------------------------------------------------------------
# Config file detection — walks up from a directory to find project configs
# ---------------------------------------------------------------------------

def _find_config(start_dir: str, config_names: tuple[str, ...]) -> str | None:
    """Walk up from start_dir to find the first existing config file.

    Returns the absolute path to the config, or None if not found.
    """
    current = Path(start_dir).resolve()
    while True:
        for name in config_names:
            candidate = current / name
            if candidate.exists():
                return str(candidate)
        if current.parent == current:
            break
        current = current.parent
    return None


def _find_luaurc(start_dir: str) -> str | None:
    return _find_config(start_dir, (".luaurc",))


def _find_selene_toml(start_dir: str) -> str | None:
    return _find_config(start_dir, ("selene.toml", "selene.yml"))


def _find_stylua_toml(start_dir: str) -> str | None:
    return _find_config(start_dir, (".stylua.toml", "stylua.toml"))


# ---------------------------------------------------------------------------
# Path normalization helper
# ---------------------------------------------------------------------------

def _normalize_paths(diagnostics: list[Diagnostic], base_dir: str) -> None:
    """Resolve relative diagnostic file paths against base_dir, in place."""
    for d in diagnostics:
        if not os.path.isabs(d.file):
            d.file = os.path.normpath(os.path.join(base_dir, d.file))


# ---------------------------------------------------------------------------
# Tool runners
# ---------------------------------------------------------------------------

def run_luau_lsp(filepath: str, project_root: str | None = None,
                 cwd: str | None = None) -> list[Diagnostic]:
    """Run luau-lsp analyze on a file or project directory.

    If cwd is set, luau-lsp will output paths relative to that directory
    (used for check_project so paths are relative to the project root).
    """
    paths = bootstrap.get_paths()
    luau_lsp = str(paths["luau_lsp"])
    defs = str(paths["defs"])
    luaurc = str(paths["luaurc"])

    cmd = [
        luau_lsp, "analyze",
        "--platform", "roblox",
        "--formatter", "plain",
        f"--definitions=@roblox={defs}",
    ]

    # Use project's .luaurc if it exists, otherwise use our default
    target_dir = project_root if project_root else os.path.dirname(filepath)
    project_luaurc = _find_luaurc(target_dir) if target_dir else None
    if project_luaurc:
        cmd.append(f"--base-luaurc={project_luaurc}")
    else:
        cmd.append(f"--base-luaurc={luaurc}")

    cmd.append(filepath)

    stdout, stderr, exit_code = _run(cmd, timeout=60, cwd=cwd)

    # luau-lsp exits non-zero on analysis errors (which is normal — those are diagnostics)
    # But exit code -1 means a crash or timeout
    if exit_code == -1 and not stdout:
        return [Diagnostic(
            file=filepath, line=1, column=1, end_line=None, end_column=None,
            code="InternalError", severity="error",
            message=f"luau-lsp failed: {stderr}", source="luau-lsp",
        )]

    return parse_luau_lsp(stdout, stderr)


def run_selene(filepath: str, project_root: str | None = None,
               cwd: str | None = None) -> list[Diagnostic]:
    """Run selene on a file or project directory."""
    if not bootstrap.has_selene():
        return []

    paths = bootstrap.get_paths()
    selene = str(paths["selene"])
    selene_toml = str(paths["selene_toml"])

    cmd = [
        selene,
        "--display-style", "json",
        "--no-summary",
    ]

    # Use project's selene.toml if it exists, otherwise use our default
    target_dir = project_root if project_root else os.path.dirname(filepath)
    project_selene = _find_selene_toml(target_dir) if target_dir else None
    if project_selene:
        cmd.append(f"--config={project_selene}")
    else:
        cmd.append(f"--config={selene_toml}")

    cmd.append(filepath)

    stdout, stderr, exit_code = _run(cmd, timeout=60, cwd=cwd)

    if exit_code == -1 and not stdout:
        return [Diagnostic(
            file=filepath, line=1, column=1, end_line=None, end_column=None,
            code="InternalError", severity="error",
            message=f"selene failed: {stderr}", source="selene",
        )]

    return parse_selene(stdout)


def run_stylua_check(filepath: str, project_root: str | None = None,
                     cwd: str | None = None) -> list[Diagnostic]:
    """Run stylua --check on a file. Returns formatting diagnostics."""
    if not bootstrap.has_stylua():
        return []

    paths = bootstrap.get_paths()
    stylua = str(paths["stylua"])

    cmd = [stylua, "--check"]

    # Detect if target dir has its own .stylua.toml or stylua.toml
    target_dir = project_root if project_root else os.path.dirname(filepath)
    if target_dir:
        project_stylua = _find_stylua_toml(target_dir)
        if project_stylua:
            cmd.append(f"--config-path={project_stylua}")

    cmd.append(filepath)

    stdout, stderr, exit_code = _run(cmd, timeout=30, cwd=cwd)

    # stylua --check exits non-zero if formatting is needed — that's normal
    # But exit code -1 means a crash or timeout
    if exit_code == -1 and not stdout:
        return [Diagnostic(
            file=filepath, line=1, column=1, end_line=None, end_column=None,
            code="InternalError", severity="error",
            message=f"stylua failed: {stderr}", source="stylua",
        )]

    # stylua --check outputs "Diff in <filepath>:" lines to stdout
    diagnostics: list[Diagnostic] = []
    if exit_code != 0:
        for line in stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            if line.startswith("Diff in "):
                diff_file = line.replace("Diff in ", "").rstrip(":")
                diagnostics.append(Diagnostic(
                    file=diff_file,
                    line=1,
                    column=1,
                    end_line=None,
                    end_column=None,
                    code="StyLuaFormat",
                    severity="warning",
                    message="Code is not formatted (run format_code to fix)",
                    source="stylua",
                ))
    return diagnostics


def run_stylua_format(code: str, filename: str = "snippet.luau") -> dict:
    """Format Luau code with stylua. Returns formatted code or error."""
    if not bootstrap.is_ready():
        err = bootstrap.last_error()
        if err:
            return {"error": f"luau-lens setup failed: {err}. Restart the MCP server to retry."}
        return {"error": "luau-lens is still setting up. Please retry in a few seconds."}

    if not bootstrap.has_stylua():
        return {"error": "StyLua binary not available"}

    paths = bootstrap.get_paths()
    stylua = str(paths["stylua"])

    # stylua reads from stdin with - and outputs to stdout
    cmd = [stylua, "--stdin-filepath", filename, "-"]
    stdout, stderr, exit_code = _run(cmd, stdin_input=code, timeout=30)

    if exit_code != 0:
        return {"error": f"StyLua failed: {stderr.strip() or stdout.strip()}"}

    return {
        "formatted_code": stdout,
        "changed": stdout != code,
    }


# ---------------------------------------------------------------------------
# Public API — check_code, check_file, check_project
# ---------------------------------------------------------------------------

def check_code(code: str, filename: str = "snippet.luau") -> dict:
    """Type-check and lint a Luau code string."""
    if not bootstrap.is_ready():
        err = bootstrap.last_error()
        if err:
            return {"error": f"luau-lens setup failed: {err}. Restart the MCP server to retry."}
        return {"error": "luau-lens is still setting up. Please retry in a few seconds."}

    # Write to temp file
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".luau", prefix="luau_lens_", delete=False, encoding="utf-8"
    ) as tmp:
        tmp.write(code)
        tmp_path = tmp.name

    try:
        luau_results = run_luau_lsp(tmp_path)
        selene_results = run_selene(tmp_path)
        stylua_results = run_stylua_check(tmp_path)

        # Rewrite file paths to the virtual filename
        for d in luau_results + selene_results + stylua_results:
            d.file = filename

        merged = merge_diagnostics(luau_results, selene_results, stylua_results)
        return to_dict(merged)
    finally:
        os.unlink(tmp_path)


def check_file(filepath: str) -> dict:
    """Type-check and lint a .luau or .lua file on disk."""
    if not bootstrap.is_ready():
        err = bootstrap.last_error()
        if err:
            return {"error": f"luau-lens setup failed: {err}. Restart the MCP server to retry."}
        return {"error": "luau-lens is still setting up. Please retry in a few seconds."}

    abs_path = os.path.abspath(filepath)
    if not os.path.exists(abs_path):
        return {"error": f"File not found: {abs_path}"}

    file_dir = os.path.dirname(abs_path)
    luau_results = run_luau_lsp(abs_path, project_root=file_dir)
    selene_results = run_selene(abs_path, project_root=file_dir)
    stylua_results = run_stylua_check(abs_path, project_root=file_dir)

    # Normalize file paths to the absolute path we passed in
    for d in luau_results + selene_results + stylua_results:
        if not os.path.isabs(d.file):
            d.file = abs_path

    merged = merge_diagnostics(luau_results, selene_results, stylua_results)
    return to_dict(merged)


def check_project(directory: str) -> dict:
    """Type-check and lint an entire project directory."""
    if not bootstrap.is_ready():
        err = bootstrap.last_error()
        if err:
            return {"error": f"luau-lens setup failed: {err}. Restart the MCP server to retry."}
        return {"error": "luau-lens is still setting up. Please retry in a few seconds."}

    abs_dir = os.path.abspath(directory)
    if not os.path.isdir(abs_dir):
        return {"error": f"Directory not found: {abs_dir}"}

    # Check if directory has any .luau or .lua files
    has_files = False
    for root, _, files in os.walk(abs_dir):
        for f in files:
            if f.endswith((".luau", ".lua")):
                has_files = True
                break
        if has_files:
            break

    if not has_files:
        return {
            "diagnostics": [],
            "summary": {"errors": 0, "warnings": 0, "total": 0},
            "note": f"No .luau or .lua files found in {abs_dir}",
        }

    # Run with cwd=abs_dir so luau-lsp outputs paths relative to the project root
    luau_results = run_luau_lsp(abs_dir, project_root=abs_dir, cwd=abs_dir)
    selene_results = run_selene(abs_dir, project_root=abs_dir, cwd=abs_dir)
    stylua_results = run_stylua_check(abs_dir, project_root=abs_dir, cwd=abs_dir)

    # Normalize relative paths against the project directory
    _normalize_paths(luau_results, abs_dir)
    _normalize_paths(selene_results, abs_dir)
    _normalize_paths(stylua_results, abs_dir)

    merged = merge_diagnostics(luau_results, selene_results, stylua_results)
    return to_dict(merged)
