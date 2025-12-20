---
name: warn-root-files
enabled: true
event: file
conditions:
  - field: file_path
    operator: regex_match
    pattern: ^(?:\./)?[^/]+$
  - field: file_path
    operator: not_contains
    pattern: .gitignore
  - field: file_path
    operator: not_contains
    pattern: README.md
  - field: file_path
    operator: not_contains
    pattern: CLAUDE.md
  - field: file_path
    operator: not_contains
    pattern: .env
---

**GOVERNANCE WARNING: File in Monorepo Root**

You're creating a file directly in the monorepo root. According to `CLAUDE.md` governance rules:

**FORBIDDEN locations for files:**
- Files in monorepo root (except `.gitignore`, `README.md`, `CLAUDE.md`, etc.)

**Proper locations:**
- Service code: `infrastructure/{service-name}/src/`
- Tests: `infrastructure/{service-name}/tests/`
- Configs: `infrastructure/{service-name}/config/`
- Documentation: `infrastructure/{service-name}/docs/`
- Shared utilities: `shared/`

Please move this file to the appropriate service directory.
