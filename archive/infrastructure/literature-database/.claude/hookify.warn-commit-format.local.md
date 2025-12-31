---
name: warn-commit-format
enabled: true
event: bash
pattern: git\s+commit.*-m\s+["'](?![a-z-]+:\s+(feat|fix|refactor|chore|docs|test|style):)
---

**GOVERNANCE WARNING: Commit Message Format**

Your commit message may not follow the required format from `CLAUDE.md`:

**Required format:**
```
<service>: <type>: <description>
```

**Examples:**
- `database: feat: add zotero sync`
- `ai: fix: memory leak in embeddings`
- `dashboard: refactor: extract components`
- `monorepo: chore: update dependencies`

**Valid types:**
- `feat` - New features
- `fix` - Bug fixes
- `refactor` - Code improvements
- `chore` - Maintenance tasks
- `docs` - Documentation
- `test` - Test additions/changes
- `style` - Code style/formatting

Please update your commit message to follow this format.
