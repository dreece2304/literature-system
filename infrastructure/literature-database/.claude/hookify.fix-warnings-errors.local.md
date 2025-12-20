---
name: fix-warnings-errors
enabled: true
event: bash
pattern: (warning|Warning|WARN|deprecat|Deprecat|DEPRECAT)
---

**Warnings or deprecation notices detected in output!**

Even when tests pass, you MUST address warnings and deprecation notices:

1. **Deprecation warnings**: Update code to use the recommended approach
2. **Package deprecations**: Update to the replacement package (e.g., PyPDF2 -> pypdf)
3. **Config deprecations**: Update to new configuration patterns (e.g., Pydantic ConfigDict)

**Do NOT ignore warnings just because tests pass.**

Fix them now or create a todo item to track the fix. Document any warnings that cannot be immediately fixed with a reason why.
