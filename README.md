# Rider MCP Proxy

A Claude Code plugin that bridges Claude to JetBrains Rider's MCP server.

## Features

- Auto-detects running Rider (Windows-side or Linux Remote Dev)
- Lightweight stdio-to-HTTP proxy — no Java bridge needed
- Automatic WSL2 networking setup

## Install

```
claude plugin marketplace add Djentinga/claude-marketplace
claude plugin install rider-mcp-proxy@djentinga
```

Requires JetBrains Rider with MCP enabled and WSL2.

On first run, the plugin configures `networkingMode=mirrored` in `.wslconfig`. Run `wsl --shutdown` from PowerShell and relaunch WSL to complete setup.

