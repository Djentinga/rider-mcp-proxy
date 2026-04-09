# Rider MCP Proxy

A Claude Code plugin that bridges Claude to JetBrains Rider's MCP server.

## Features

- Auto-detects running Rider (Windows-side or Linux Remote Dev)
- Lightweight stdio-to-HTTP proxy — no Java bridge needed
- Configurable tool filtering via `tools.json`
- Automatic WSL2 networking setup

## Install

```
claude plugin marketplace add Djentinga/claude-marketplace
claude plugin install rider-mcp-proxy@Djentinga
```

Requires JetBrains Rider with MCP enabled and WSL2.

On first run, the plugin configures `networkingMode=mirrored` in `.wslconfig`. Run `wsl --shutdown` from PowerShell and relaunch WSL to complete setup.

## Tool Filtering

Rider exposes ~30 MCP tools. Control which ones Claude sees via `tools.json` in the plugin root:

```json
{
  "allowed": ["get_file_text_by_path", "replace_text_in_file", "..."],
  "forbidden": ["search_in_files_by_text", "build_project", "..."]
}
```

- **`allowed`** — only these tools are exposed. Omit to allow all.
- **`forbidden`** — always removed, even if in `allowed`.
- If the file is missing, all tools pass through unfiltered.

Filtered tools never reach Claude — no token spend on unused schemas.
