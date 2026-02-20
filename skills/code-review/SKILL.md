---
name: code-review
description: "USE: when reviewing diffs, PRs, or validating changes after editing. NOT: when writing new code, debugging, exploring, or doing builds."
user-invocable: false
---

# Code Review

## Flow
1. **Scope**: `git diff --stat` — only review changed files
2. **Read changed symbols only**: Serena `find_symbol(include_body=true)` for modified methods — never full files
3. **Check references** (if signatures changed): Serena `find_referencing_symbols` + Rider `search_in_files_by_text`
4. **Validate**: Rider `get_file_problems` per changed file + `build_project`
