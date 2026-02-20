---
name: tool-selection
description: "MANDATORY tool routing. USE: EVERY TIME you read files, search code, edit code, browse directories, or look up symbols. NEVER use built-in Read, Grep, Glob, Edit, or Write when Rider/Serena MCP tools can do the job."
user-invocable: false
---

# Tool Selection Guide

**RULE: Always prefer Rider MCP and Serena MCP over built-in tools (Read, Grep, Glob, Edit, Write).**

## projectPath (Rider MCP)

Always pass the Windows-style path to the project root (e.g. `C:/Users/.../MyProject`), never `/mnt/c/...`.

## Reading Code

| Need | Tool | Why |
|------|------|-----|
| Symbol overview | Serena `get_symbols_overview` | Compact names by kind (~200 tokens for a class) |
| One method body | Serena `find_symbol(include_body=true)` | Reads just that symbol, not the whole file |
| Symbol signature/type | Serena `find_symbol(include_info=true)` | Hover-like info without reading file |
| Member list of a class | Serena `find_symbol(depth=1)` | Names + line ranges |
| Find references | Serena `find_referencing_symbols` | Semantic refs with code snippets |
| Full file content | Rider `get_file_text_by_path` | Use `maxLinesCount` + `truncateMode` for partial reads |

**NEVER** use built-in `Read` for source files. Use Rider `get_file_text_by_path` or Serena symbol tools.

## Searching

| Need | Tool | Why |
|------|------|-----|
| File by name | Rider `find_files_by_name_keyword` | Indexed, fast, excludes noise |
| File by glob pattern | Rider `find_files_by_glob` | When pattern matching needed |
| Text in files | Rider `search_in_files_by_text` | Use `maxUsageCount`, `fileMask`, `directoryToSearch` |
| Regex in files | Rider `search_in_files_by_regex` | Same options as text search |
| Directory tree | Rider `list_directory_tree` | Always use `maxDepth` |

**NEVER** use built-in `Grep` or `Glob` for project files. Use Rider search tools.

## Editing

| Need | Tool | Why |
|------|------|-----|
| Replace entire method/class | Serena `replace_symbol_body` | Semantic — no old-text quoting needed |
| Add new method/field | Serena `insert_after/before_symbol` | Positional relative to existing symbols |
| Simple text replacement | Rider `replace_text_in_file` | Quick exact-match edits |
| Rename symbol | Serena `rename_symbol` | Roslyn-powered cross-project rename |
| Create new file | Rider `create_new_file` | IDE-aware |
| Reformat after edits | Rider `reformat_file` | Applies IDE formatting rules |

**NEVER** use built-in `Edit` or `Write` for project files. Use Rider/Serena editing tools.

## Build & Verify

| Need | Tool | Why |
|------|------|-----|
| Build solution | Rider `build_project` | IDE build with diagnostics |
| File-level errors | Rider `get_file_problems` | IDE inspections per file |
| Run configuration | Rider `execute_run_configuration` | Run/test from IDE |
| Show file to user | Rider `open_file_in_editor` | Opens in IDE |

## Cross-Tool Rules

- **After Serena edits**: Rider may have stale cache. Use `open_file_in_editor` if Rider tools need to see the change.
- **Critical refactors**: Cross-check `find_referencing_symbols` with Rider `search_in_files_by_text` (Roslyn may miss refs if not fully indexed).

## Exceptions (built-in tools OK)

- Non-project files (e.g. `~/.claude/` memory/skill files, system files)
- Binary files / images / PDFs
- Git operations (use Bash)
