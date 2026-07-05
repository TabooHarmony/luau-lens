<div align="center">

# 🔍 luau-lens

**MCP server that gives AI agents instant Luau diagnostics.**

Type checking, linting, and formatting without opening Roblox Studio.

[![MCP](https://img.shields.io/badge/MCP-Server-7B61FF?logo=modelcontextprotocol&logoColor=white)](https://modelcontextprotocol.io)
[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Tools](https://img.shields.io/badge/Tools-luau--lsp_%7C_selene_%7C_stylua-blueviolet)](#how-it-works)

[![Platform](https://img.shields.io/badge/Platform-Windows_%7C_macOS_%7C_Linux-lightgrey)](#requirements)
[![Zero Setup](https://img.shields.io/badge/Setup-Zero_Config-success)](#install)
[![Roblox](https://img.shields.io/badge/Roblox-Luau-FF6B6B?logo=robloxstudio&logoColor=white)](https://create.roblox.com/docs/luau)

</div>

---

luau-lens is an [MCP server](https://modelcontextprotocol.io) that plugs your AI coding agent (Claude Code, Cursor, etc.) into the three core tools of the Roblox Luau toolchain. No CLI, no manual binary installs, no Rojo project. Paste a config snippet and your agent can:

- catch type errors before runtime
- lint for unused variables, bad patterns, deprecated APIs
- detect and fix code formatting issues

All wrapped behind four simple tools your agent calls automatically.

## Install

Add to your MCP client config:

```json
{
  "mcpServers": {
    "luau-lens": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/TabooHarmony/luau-lens", "luau-lens"]
    }
  }
}
```

That's it. On first run, luau-lens downloads everything it needs (~11MB, cached in `~/.luau-lens/`). No manual setup, no pre-installed tools, no Roblox Studio.

> Not yet on PyPI. The git URL is required for now. Once published, the config simplifies to `"args": ["luau-lens"]`.

## How it works

Three tools run automatically on every check. Results merge into structured JSON with line numbers, severity, and source attribution.

| Tool | What it does | Made by |
| --- | --- | --- |
| **luau-lsp** `analyze` | Type checking with Roblox API definitions. Catches type mismatches, unknown properties, missing globals. | [JohnnyMorganz](https://github.com/JohnnyMorganz/luau-lsp) |
| **selene** | Linting with Roblox standard library. Catches unused variables, bad patterns, divide-by-zero, deprecated APIs. | [Kampfkarren](https://github.com/Kampfkarren/selene) |
| **stylua** | Code formatting. Detects style violations and returns properly formatted code. | [JohnnyMorganz](https://github.com/JohnnyMorganz/StyLua) |

luau-lens auto-downloads all three on first run. Type definitions refresh automatically every 7 days. Project-level `.luaurc`, `selene.toml`, and `.stylua.toml` are respected if present.

## Tools

**`check_code`**`(code, filename?)`
Type-check, lint, and format-check a Luau code string. Call this after writing or modifying Luau code.

**`check_file`**`(filepath)`
Same as above, but for a file on disk. Respects existing project configs in the file's directory tree.

**`check_project`**`(directory)`
Run all three tools across every `.luau` and `.lua` file in a project directory.

**`format_code`**`(code, filename?)`
Format Luau code with stylua and return the formatted result. Call this when you want the agent to fix formatting, not just detect it.

## Requirements

- [`uv`](https://docs.astral.sh/uv/) (installed automatically by most MCP clients, and by `uvx`)
- Internet access on first run (to download ~11MB of binaries and type definitions, ~31MB extracted)
- Works on Windows, macOS, and Linux (x86_64 and arm64)

## License

MIT
