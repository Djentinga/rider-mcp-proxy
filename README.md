# Djentinga-mcp

Claude Code plugin that configures JetBrains Rider and Serena MCP servers with skills for tool routing, C# conventions, and code review.

## Features

- **Rider MCP** — auto-detects Rider installation path (standard + Toolbox), builds classpath, detects MCP port from running process
- **Serena MCP** — Roslyn-based C# language server with `.slnx` support
- **Auto-install** — installs uv, .NET 10 SDK, and pre-caches Serena on first run (skips if already present)
- **Serena patch** — skips redundant csproj BFS scan when a `.sln`/`.slnx` file is found

## Skills

| Skill | Description |
|-------|-------------|
| `tool-selection` | Mandatory routing: when to use Rider, Serena, or built-in tools |
| `writing-csharp` | C# 14 conventions (formatting, primary constructors, patterns, naming) |
| `code-review` | Review workflow using Rider + Serena for changed symbols only |

## Install

```
/plugin marketplace add Djentinga/claude-marketplace
/plugin install Djentinga-mcp@djentinga-plugins
```

## Prerequisites

Installed automatically by the SessionStart hook if missing:

- [uv](https://docs.astral.sh/uv/) (provides `uvx` for running Serena)
- [.NET 10 SDK](https://dotnet.microsoft.com/)
- [Serena](https://github.com/oraios/serena) (pre-cached via uvx)

Required on the host machine:

- JetBrains Rider (standard install or Toolbox)
- WSL2 (scripts assume Linux-side execution calling Windows-side Rider)
