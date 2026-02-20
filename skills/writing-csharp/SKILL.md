---
name: writing-csharp
description: "C# 14 + Razor conventions. USE: when writing/modifying .cs or .razor files."
user-invocable: false
---

# C# Conventions

## Formatting

- **Line limit: 120 characters.** Break with symmetric vertical stacking (all siblings on their own line).
- File-scoped namespaces (`namespace Foo;`).
- Always `var`.

## Expression Bodies

Use `=>` for any single-expression method, property, or operator. Only use `{ }` for multiple statements.

## Primary Constructors

Use primary constructors. Only assign to `private readonly` fields when needed outside initialization.

## Collections

Use `[]` syntax and `..` spread:

```csharp
List<string> names = ["Alice", "Bob"];
List<int> combined = [.. first, .. second, extra];
```

## Pattern Matching

Prefer `is`, `switch` expressions, and property patterns over type checks and casts.

## Nullability

- Always enabled. Never `#nullable disable`.
- Use `required` on must-set properties. Use `init` for immutable-after-creation.
- Avoid `null!`.

## Naming

| Element | Convention |
|---------|-----------|
| Private field | `_camelCase` |
| Local / param | `camelCase` |
| Property / Method | `PascalCase` |
| Async method | `*Async` suffix |
| Interface | `I` prefix |
| Constant | `PascalCase` |

## Razor

- `@code` blocks at the bottom.
- `[Parameter]` and `[Parameter, EditorRequired]` where applicable.
- **Sub-component binding**: `@bind-*` in a child component does NOT trigger `StateHasChanged` on the parent. Add `[Parameter] public EventCallback OnChanged` to the child, use `@bind-*:after="NotifyChanged"`, and wire parent with `OnChanged="StateHasChanged"`.

## Other Rules

- `string.IsNullOrWhiteSpace` over `IsNullOrEmpty`.
- `CancellationToken` as last parameter.
- `sealed` on classes not designed for inheritance.
- `IReadOnlyList<T>` / `IReadOnlyCollection<T>` in public APIs.
- Keep methods short — extract helpers to reduce nesting (CodeScene complexity).