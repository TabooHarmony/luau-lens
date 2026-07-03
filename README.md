# luau-lens

Instant Luau type checking and linting for AI agents.

Give your AI coding agent the ability to catch Luau type errors, unknown properties, deprecated patterns, and lint warnings — without opening Roblox Studio.

## Install

Add to your MCP client config (Claude Code, Cursor, etc.):

```json
{
  "mcpServers": {
    "luau-lens": {
      "command": "uvx",
      "args": ["luau-lens"]
    }
  }
}
```

That's it. On first run, luau-lens downloads `luau-lsp` and `selene` automatically. No manual setup.

## How it works

luau-lens wraps two tools:

- **luau-lsp analyze** — type checking with Roblox API type definitions. Catches type mismatches, unknown properties, missing globals.
- **selene** — linting with Roblox standard library. Catches unused variables, bad patterns, deprecated APIs.

Both run automatically on every check. Results are merged into structured JSON with line numbers, severity, and source attribution.

## Tools

- `check_code(code, filename?)` — type-check and lint a Luau code string
- `check_file(filepath)` — type-check and lint a .luau or .lua file on disk
- `check_project(directory)` — type-check and lint an entire project directory

## Requirements

- `uv` (installed automatically by most MCP clients)
- Internet access on first run (to download ~26MB of binaries and type definitions)

## License

MIT
