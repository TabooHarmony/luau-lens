"""Subprocess wrappers for luau-lsp analyze, selene, and stylua."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

from . import bootstrap
from .parsers import Diagnostic, merge_diagnostics, parse_luau_lsp, parse_selene, to_dict


def _run(cmd: list[str], cwd: str | None = None, timeout: int = 30) -> tuple[str, str, int]:
    """Run a command and return (stdout, stderr, exit_code)."""
    try:
        proc = subprocess.run(
            cmd,
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


def _run_with_stdin(cmd: list[str], stdin_input: str, timeout: int = 30) -> tuple[str, str, int]:
    """Run a command with stdin input and return (stdout, stderr, exit_code)."""
    try:
        proc = subprocess.run(
            cmd,
            input=stdin_input,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return proc.stdout, proc.stderr, proc.returncode
    except subprocess.TimeoutExpired:
        return "", f"Command timed out after {timeout}s: {' '.join(cmd)}", -1
    except FileNotFoundError:
        return "", f"Binary not found: {cmd[0]}", -1


def run_luau_lsp(filepath: str, project_root: str | None = None) -> list[Diagnostic]:
    """Run luau-lsp analyze on a file or project directory."""
    paths = bootstrap.get_paths()
    luau_lsp = str(paths["luau_lsp"])
    defs = str(paths["defs"])
    luaurc = str(paths["luaurc"])

    cmd = [
        luau_lsp, "analyze",
        "--platform", "roblox",
        "--formatter", "plain",
        f"--definitions=@roblox={defs}",
        f"--base-luaurc={luaurc}",
    ]

    # Detect if target dir has its own .luaurc — if so, don't force ours
    target_dir = project_root if project_root else os.path.dirname(filepath)
    if target_dir and Path(target_dir, ".luaurc").exists():
        cmd.remove(f"--base-luaurc={luaurc}")  # let project config take precedence

    cmd.append(filepath)

    stdout, stderr, _ = _run(cmd, timeout=60)
    return parse_luau_lsp(stdout, stderr)


def run_selene(filepath: str, project_root: str | None = None) -> list[Diagnostic]:
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
        f"--config={selene_toml}",
    ]

    # Detect if target dir has its own selene.toml — if so, use theirs
    target_dir = project_root if project_root else os.path.dirname(filepath)
    if target_dir and Path(target_dir, "selene.toml").exists():
        cmd.remove(f"--config={selene_toml}")

    cmd.append(filepath)

    stdout, stderr, _ = _run(cmd, timeout=60)
    return parse_selene(stdout)


def run_stylua_check(filepath: str, project_root: str | None = None) -> list[Diagnostic]:
    """Run stylua --check on a file. Returns formatting diagnostics."""
    if not bootstrap.has_stylua():
        return []

    paths = bootstrap.get_paths()
    stylua = str(paths["stylua"])

    cmd = [stylua, "--check"]

    # Detect if target dir has its own .stylua.toml or stylua.toml
    target_dir = project_root if project_root else os.path.dirname(filepath)
    if target_dir:
        for cfg_name in (".stylua.toml", "stylua.toml"):
            if Path(target_dir, cfg_name).exists():
                cmd.append(f"--config-path={Path(target_dir, cfg_name)}")
                break

    cmd.append(filepath)

    stdout, stderr, exit_code = _run(cmd, timeout=30)

    # stylua --check exits non-zero if formatting is needed
    # stdout contains the diff output showing what would change
    diagnostics: list[Diagnostic] = []
    if exit_code != 0:
        for line in stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            # stylua --check outputs lines like:
            # "Diff in /path/to/file.luau:"
            if line.startswith("Diff in "):
                filepath = line.replace("Diff in ", "").rstrip(":")
                diagnostics.append(Diagnostic(
                    file=filepath,
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
        return {"error": "luau-lens is still setting up. Please retry in a few seconds."}

    if not bootstrap.has_stylua():
        return {"error": "StyLua binary not available"}

    paths = bootstrap.get_paths()
    stylua = str(paths["stylua"])

    # stylua reads from stdin with - and outputs to stdout
    cmd = [stylua, "--stdin-filepath", filename, "-"]
    stdout, stderr, exit_code = _run_with_stdin(cmd, code, timeout=30)

    if exit_code != 0:
        return {"error": f"StyLua failed: {stderr.strip() or stdout.strip()}"}

    return {
        "formatted_code": stdout,
        "changed": stdout != code,
    }


def check_code(code: str, filename: str = "snippet.luau") -> dict:
    """Type-check and lint a Luau code string."""
    if not bootstrap.is_ready():
        return {"error": "luau-lens is still setting up. Please retry in a few seconds."}

    # Write to temp file
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".luau", prefix="luau_lens_", delete=False, encoding="utf-8"
    ) as tmp:
        tmp.write(code)
        tmp_path = tmp.name

    try:
        # Write a virtual filename for error reporting
        # luau-lsp uses the actual path in output, so we need to rewrite it
        luau_results = run_luau_lsp(tmp_path)
        selene_results = run_selene(tmp_path)
        stylua_results = run_stylua_check(tmp_path)

        # Rewrite file paths to the virtual filename
        for d in luau_results:
            d.file = filename
        for d in selene_results:
            d.file = filename
        for d in stylua_results:
            d.file = filename

        merged = merge_diagnostics(luau_results, selene_results, stylua_results)
        return to_dict(merged)
    finally:
        os.unlink(tmp_path)


def check_file(filepath: str) -> dict:
    """Type-check and lint a .luau or .lua file on disk."""
    if not bootstrap.is_ready():
        return {"error": "luau-lens is still setting up. Please retry in a few seconds."}

    abs_path = os.path.abspath(filepath)
    if not os.path.exists(abs_path):
        return {"error": f"File not found: {abs_path}"}

    luau_results = run_luau_lsp(abs_path)
    selene_results = run_selene(abs_path)
    stylua_results = run_stylua_check(abs_path)

    # Normalize file paths to the absolute path we passed in
    for d in luau_results + selene_results + stylua_results:
        if not os.path.isabs(d.file):
            d.file = abs_path

    merged = merge_diagnostics(luau_results, selene_results, stylua_results)
    return to_dict(merged)


def check_project(directory: str) -> dict:
    """Type-check and lint an entire project directory."""
    if not bootstrap.is_ready():
        return {"error": "luau-lens is still setting up. Please retry in a few seconds."}

    abs_dir = os.path.abspath(directory)
    if not os.path.isdir(abs_dir):
        return {"error": f"Directory not found: {abs_dir}"}

    luau_results = run_luau_lsp(abs_dir, project_root=abs_dir)
    selene_results = run_selene(abs_dir, project_root=abs_dir)
    stylua_results = run_stylua_check(abs_dir, project_root=abs_dir)

    # Normalize file paths to absolute
    for d in luau_results:
        if not os.path.isabs(d.file):
            d.file = os.path.normpath(os.path.join(abs_dir, d.file))
    for d in selene_results:
        if not os.path.isabs(d.file):
            d.file = os.path.normpath(os.path.join(abs_dir, d.file))
    for d in stylua_results:
        if not os.path.isabs(d.file):
            d.file = os.path.normpath(os.path.join(abs_dir, d.file))

    merged = merge_diagnostics(luau_results, selene_results, stylua_results)
    return to_dict(merged)
