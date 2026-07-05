# luau-lens

Instant Luau type checking, linting, and formatting for AI agents.

Give your AI coding agent the ability to catch Luau type errors, unknown properties, deprecated patterns, lint warnings, and formatting issues, without opening Roblox Studio.

## Install

Add to your MCP client config (Claude Code, Cursor, etc.):

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

That's it. On first run, luau-lens downloads `luau-lsp`, `selene`, and `stylua` automatically. No manual setup.

> **Note:** Not yet on PyPI. The git URL is required for now. Once published, the config will simplify to `"args": ["luau-lens"]`.

## How it works

luau-lens wraps three tools from the standard Roblox Luau toolchain:

- **luau-lsp analyze** — type checking with Roblox API type definitions. Catches type mismatches, unknown properties, missing globals.
- **selene** — linting with Roblox standard library. Catches unused variables, bad patterns, deprecated APIs.
- **stylua** — code formatting. Detects style violations and can return properly formatted code.

All three run automatically on every check. Results are merged into structured JSON with line numbers, severity, and source attribution.

## Tools

- `check_code(code, filename?)` — type-check, lint, and format-check a Luau code string
- `check_file(filepath)` — type-check, lint, and format-check a .luau or .lua file on disk
- `check_project(directory)` — type-check, lint, and format-check an entire project directory
- `format_code(code, filename?)` — format Luau code with stylua and return the formatted result

## Requirements

- `uv` (installed automatically by most MCP clients)
- Internet access on first run (to download ~11MB of binaries and type definitions, ~31MB extracted)

## License

MIT
