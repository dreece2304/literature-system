---
name: warn-forbidden-dirs
enabled: true
event: all
pattern: /?(temp|old|backup|_old|_backup|\.bak)/
---

**GOVERNANCE WARNING: Forbidden Directory**

You're using a forbidden directory name. According to `CLAUDE.md` governance rules:

**FORBIDDEN directories:**
- `temp/`, `old/`, `backup/`
- `_old/`, `_backup/`, `.bak/`

**Why this matters:**
- These directories clutter the codebase
- They indicate incomplete refactoring
- They often contain outdated/dangerous code

**Instead:**
- Use git branches for experimental work
- Delete unused code (git history preserves it)
- Use proper versioning for migrations
