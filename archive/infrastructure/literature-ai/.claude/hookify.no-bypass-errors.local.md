---
name: no-bypass-errors
enabled: true
event: bash
action: block
pattern: --no-verify|--skip-hooks|--skip-tests|--no-lint|HUSKY=0|HUSKY_SKIP_HOOKS=1|--ignore-scripts|--force-publish|eslint-disable|noqa:\s*all|type:\s*ignore
---

**BLOCKED: Bypass pattern detected**

You attempted to use a flag or pattern that bypasses error checking:
- `--no-verify` (skips git hooks)
- `--skip-hooks` (skips hooks)
- `--skip-tests` / `--no-lint` (skips quality checks)
- `HUSKY=0` (disables Husky hooks)
- `--ignore-scripts` (skips npm scripts)
- `eslint-disable` / `noqa` / `type: ignore` (disables linting)

**This violates the project's quality standards.**

**Required action:**
1. Fix the underlying error, warning, or linting issue
2. If you believe the bypass is truly necessary, explain WHY to the user
3. Wait for explicit user approval before proceeding

**Do NOT bypass without user approval.**
