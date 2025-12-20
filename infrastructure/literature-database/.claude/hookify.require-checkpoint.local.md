---
name: require-checkpoint
enabled: true
event: stop
pattern: .*
---

**CHECKPOINT PROTOCOL REMINDER**

Before completing this task, ensure your response includes the required checkpoint format:

```markdown
## CHECKPOINT: [Task Name]

**SERVICE**: [Which service/agent]
**GOAL**: [What will be accomplished]
**FILES TO MODIFY**:
- path/to/file1.py [CREATE/MODIFY/DELETE]

**IMPLEMENTATION**:
[actual code or summary]

**VERIFICATION**:
- [ ] Tests pass
- [ ] Service starts
- [ ] API responds
- [ ] No breaking changes

**SUMMARY**: [What was done]
**NEXT STEPS**: [Suggested followup]
```

This is required by the `CLAUDE.md` governance protocol.
