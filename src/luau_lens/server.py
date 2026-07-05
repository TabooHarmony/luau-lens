"""luau-lens MCP server — instant Luau type checking and linting for AI agents."""

from __future__ import annotations

import logging
import sys

# Suppress MCP SDK debug logging that pollutes stderr
logging.getLogger("mcp").setLevel(logging.WARNING)

from mcp.server.fastmcp import FastMCP

from . import bootstrap
from . import runners

# Initialize on startup
bootstrap.ensure_tools()

mcp = FastMCP("luau-lens")


@mcp.tool()
def check_code(code: str, filename: str = "snippet.luau") -> dict:
    """Type-check and lint a Luau code string. Always call this after writing or modifying Luau code to catch type errors, unknown properties, deprecated patterns, unused variables, and formatting issues before runtime.

    Runs three tools: luau-lsp (type checking), selene (linting), and stylua (formatting check). Works with Roblox API types (Instance, Part, Color3, RemoteEvent, etc.) out of the box. No setup needed beyond installing this MCP server.

    Args:
        code: Luau source code to check
        filename: virtual filename for error reporting (default: snippet.luau)

    Returns:
        Structured diagnostics with line numbers, severity, and messages:
        {
            "diagnostics": [
                {
                    "file": "snippet.luau",
                    "line": 47,
                    "column": 12,
                    "endLine": 47,
                    "endColumn": 20,
                    "code": "TypeError",
                    "severity": "error",
                    "message": "Expected this to be 'number', but got 'string'",
                    "source": "luau-lsp"
                }
            ],
            "summary": {"errors": 1, "warnings": 0, "total": 1}
        }
        On error, returns {"error": "description of what went wrong"}.
    """
    return runners.check_code(code, filename)


@mcp.tool()
def check_file(filepath: str) -> dict:
    """Type-check and lint a .luau or .lua file on disk. Always call this after writing or modifying Luau files to catch errors before runtime.

    Detects and respects existing .luaurc, selene.toml, and .stylua.toml in the file's directory if present.

    Args:
        filepath: absolute or relative path to the .luau or .lua file

    Returns:
        Same structured diagnostics format as check_code.
        On error, returns {"error": "description of what went wrong"}.
    """
    return runners.check_file(filepath)


@mcp.tool()
def check_project(directory: str) -> dict:
    """Type-check and lint an entire project directory. Call this to run diagnostics across all .luau and .lua files in a project.

    Detects and respects existing .luaurc, selene.toml, and .stylua.toml in the project root if present.

    Args:
        directory: path to the project root directory

    Returns:
        Same structured diagnostics format as check_code, with diagnostics across all files.
        On error, returns {"error": "description of what went wrong"}.
    """
    return runners.check_project(directory)


@mcp.tool()
def format_code(code: str, filename: str = "snippet.luau") -> dict:
    """Format Luau code using StyLua. Call this after writing or modifying Luau code to enforce consistent style.

    Uses StyLua (the standard Roblox Luau formatter, same author as luau-lsp). Applies the Roblox Lua Style Guide by default. Detects and respects existing .stylua.toml or stylua.toml in the file's directory if present.

    Args:
        code: Luau source code to format
        filename: virtual filename for syntax detection (default: snippet.luau)

    Returns:
        {
            "formatted_code": "the formatted code string",
            "changed": true
        }
        If the code was already formatted, changed will be false and formatted_code will match the input.
        On error, returns {"error": "description of what went wrong"}.
    """
    return runners.run_stylua_format(code, filename)


def main():
    mcp.run()


if __name__ == "__main__":
    main()
