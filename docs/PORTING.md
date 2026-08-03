# Porting the Literature System to Another Machine

The repo carries all code; the `data/` directory (git-ignored) carries all
state. Moving machines = clone + restore data + rebase paths.

## On the old machine

1. Push the current branch (`git push`).
2. Bundle the data payload:
   ```bash
   cd src
   mamba run -n litai python -m scripts.backup --output-dir ~/lit-backup --include-pdfs --compress
   ```
   This captures `literature.db`, `data/pdfs/` (~2 GB), and the ChromaDB
   vectorstore. Transfer the archive by drive, external disk, or cloud.

## On the new machine

1. Clone and create the environment:
   ```bash
   git clone https://github.com/dreece2304/literature-system.git research
   cd research
   mamba env create -f environment.yml   # creates the litai env
   ```
2. Restore the backup archive so you end up with `data/literature.db`,
   `data/pdfs/`, and `data/vectorstore/` under the project root.
3. Fix absolute PDF paths (stored per-machine in `papers.file_path`):
   ```bash
   cd src
   mamba run -n litai python -m scripts.rebase_pdf_paths            # dry-run
   mamba run -n litai python -m scripts.rebase_pdf_paths --execute
   ```
4. Sanity-check:
   ```bash
   mamba run -n litai python -m pytest tests/unit -q       # from repo root
   mamba run -n litai python -m scripts.health_check       # from src/
   ```

## MCP registration on the new machine

Nothing to do — the repo's `.mcp.json` is already path-independent and Claude
Code picks it up on clone:

```json
{
  "mcpServers": {
    "literature": {
      "type": "stdio",
      "command": "${MAMBA_EXE:-mamba}",
      "args": ["run", "-n", "litai",
               "--cwd", "${CLAUDE_PROJECT_DIR:-.}/src",
               "python", "-m", "mcp_server.server"]
    }
  }
}
```

`mamba run --cwd src` is what makes this work: Python puts the working
directory on `sys.path` for `-m`, so `mcp_server` resolves without a
`PYTHONPATH` entry, and `literature_core` finds the project root by walking up
to the `.git` directory rather than trusting the caller's cwd.

Two caveats:

- `MAMBA_EXE` is exported by mamba's shell init. If Claude Code is launched
  from an environment that lacks it, the fallback `mamba` must be a real
  executable on `PATH` — a shell *function* (what `mamba init` usually
  installs) is not enough. Set `MAMBA_EXE` or substitute the absolute path.
- Prefer this project-scoped `.mcp.json` over a local-scope entry in
  `~/.claude.json`. Local-scope entries carry absolute `cwd`/`PYTHONPATH`
  values that silently drift off the project root and break the server; if one
  already exists for `literature`, delete it so the project config wins.

## Machine-specific settings to review

- `LITCORE_PROJECT_ROOT` env var overrides project-root autodetection if the
  layout is unusual; otherwise nothing to set.
- The Windows-browser PDF fetch queue (`browser_pdf` tools) defaults to
  `/mnt/c/Users/dreec/...` paths from the old machine — override its
  download directory settings on the new machine or ignore the feature if
  the laptop has direct network access to publishers.
- Ollama (local LLM extraction) must be installed separately if you want AI
  extraction there; `src/config/ai_settings.py` holds the model config. All
  other features degrade gracefully without it.
- GPU features (embeddings) work CPU-only; first embedding run just takes
  longer.

## Future GUI work (notes)

The service layer (`src/services/`) is deliberately UI-agnostic — the MCP
tools are thin wrappers over it, and a GUI should be too. The natural shape
is a small FastAPI app importing the same services (search, papers,
collections, citations), with a web frontend for browsing/reading/analysis.
Nothing in the current architecture blocks this; keep business logic in
services and the GUI becomes another thin client alongside MCP.
