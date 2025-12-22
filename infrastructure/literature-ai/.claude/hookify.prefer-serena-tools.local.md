---
name: prefer-serena-tools
enabled: true
event: file
conditions:
  - field: file_path
    operator: regex_match
    pattern: \.(py|js|ts|tsx|jsx|java|go|rs|cpp|c|h|hpp)$
---

**Consider using Serena symbolic tools instead of Edit**

When modifying code symbols (functions, methods, classes), Serena's tools are more precise:

- `find_symbol` - Locate symbols by name path
- `replace_symbol_body` - Replace entire function/method bodies
- `insert_after_symbol` / `insert_before_symbol` - Add new code relative to symbols
- `rename_symbol` - Rename across the codebase

**When to use Edit instead:**
- Simple text replacements (imports, comments, strings)
- Indentation/formatting fixes
- Changes that don't align with symbol boundaries

**Serena is better for:**
- Replacing entire methods or functions
- Adding new methods to a class
- Refactoring symbol names
- Structural code changes
