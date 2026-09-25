# Porting the Literature System to Another Machine

The repo carries all code; the `data/` directory (git-ignored) carries all
state. Moving machines = clone + restore data + rebase paths.

Payload on the source machine (Sept 2026): `data/literature.db` 92 MB (≈40 MB
after `VACUUM INTO`), `data/pdfs/` 1.8 GB (494 files, flat), `data/vectorstore/`
980 MB ChromaDB. About 2.9 GB total.

## On the old machine

1. Commit and push the current branch (`git push`), and fast-forward `master`
   if the branch is ready so the new machine can clone the default branch.
2. Stage the payload outside the repo, in `~/lit-transfer/`:
   ```bash
   cd ~/projects/research/misc/research
   mkdir -p ~/lit-transfer/local-config

   # Database: compacted read-only copy (does not touch the live file)
   sqlite3 data/literature.db "VACUUM INTO '$HOME/lit-transfer/literature.db'"
   sqlite3 ~/lit-transfer/literature.db "pragma integrity_check"     # must print: ok

   # PDFs (no gzip - PDFs do not compress) and the vector store
   tar -cf  ~/lit-transfer/pdfs.tar        -C data pdfs
   tar -czf ~/lit-transfer/vectorstore.tar.gz -C data vectorstore

   # Secrets: .env holds live API keys and credentials, so encrypt before it
   # leaves the machine. gpg prompts for a passphrase; choose one you will
   # remember on the other side.
   tar -czf ~/lit-transfer/secrets.tar.gz .env data/config/credentials.yml
   gpg --symmetric --cipher-algo AES256 ~/lit-transfer/secrets.tar.gz
   shred -u ~/lit-transfer/secrets.tar.gz

   # Non-secret local config, for reference on the other side
   cp .claude/settings.local.json ~/lit-transfer/local-config/
   python3 -c "import json;print(json.dumps(json.load(open('$HOME/.mcp.json'))['mcpServers']['literature'],indent=2))" \
     > ~/lit-transfer/local-config/mcp-literature-entry.json

   # Manifest, then upload and verify
   cd ~/lit-transfer && sha256sum literature.db pdfs.tar vectorstore.tar.gz secrets.tar.gz.gpg > MANIFEST.sha256
   rclone copy ~/lit-transfer gdrive:Research/literature-system-transfer/ --progress --transfers 4
   rclone check ~/lit-transfer gdrive:Research/literature-system-transfer/    # 0 differences
   ```
   Any other route works too (external disk, `rsync` over the LAN); the
   layout of `~/lit-transfer/` is what matters.

Alternative: `cd src && mamba run -n litai python -m scripts.backup
--output-dir ~/lit-backup --include-pdfs --compress` produces the same
database + PDFs + ChromaDB payload in one timestamped directory, without the
secrets bundle.

## On the new machine

```bash
git clone https://github.com/dreece2304/literature-system.git research
cd research
mamba env create -f environment.yml          # creates the litai env; pins pytorch-cuda=12.1
sudo apt install tesseract-ocr poppler-utils # OS-level deps for OCR and pdf2image, not in environment.yml

# Pull the payload (rclone must have a gdrive: remote configured; the Drive web UI works too)
rclone copy gdrive:Research/literature-system-transfer/ ~/lit-transfer/ --progress
cd ~/lit-transfer && sha256sum -c MANIFEST.sha256

# Restore into the repo
REPO=~/research
gpg -d secrets.tar.gz.gpg | tar -xz -C "$REPO"           # restores .env and data/config/credentials.yml
cp literature.db "$REPO/data/"
tar -xf  pdfs.tar           -C "$REPO/data"
tar -xzf vectorstore.tar.gz -C "$REPO/data"

# Fix absolute PDF paths (stored per-machine in papers.file_path)
cd "$REPO/src"
mamba run -n litai python -m scripts.rebase_pdf_paths            # dry-run: shows what would change
mamba run -n litai python -m scripts.rebase_pdf_paths --execute

# Sanity-check
mamba run -n litai python -m scripts.health_check               # infrastructure: db, vector store, disk
mamba run -n litai python -m scripts.audit                      # data coherence: exit 0 expected
cd .. && mamba run -n litai python -m pytest tests/unit -q
```

## Machine-specific settings to review

- `data/projects.json` is tracked and holds two absolute
  `/home/dreece23/projects/research/...` manuscript paths. Edit them, or the
  `manage_project` tools will point at nothing.
- No NVIDIA GPU: export `LITCORE_EMBEDDING_DEVICE=cpu`. The embedding
  generator already falls back to CPU when CUDA is absent, but setting it
  avoids the warning and the CUDA-init attempt. `environment.yml` still solves
  on a CPU-only WSL2 box; the CUDA build simply runs on CPU.
- `browser_pdf` (Windows-browser PDF fetch queue) builds its paths from
  `WINDOWS_USER` (default `dreec`) under `/mnt/c/Users/<user>/literature-ai`.
  Set the variable or ignore the feature.
- Ollama is optional. Without it, `enrich_pipeline` refuses the `extract` and
  `verify` stages at preflight (exit 1 with the `ollama serve` / `ollama pull`
  command to run); `backfill` and `embed` still work, as does everything else.
  `src/config/ai_settings.py` holds the model config.
- `CLAUDE.md` and `docs/WORKFLOWS.md` spell out
  `/home/dreece23/miniforge3/bin/mamba` in their commands because `mamba` is a
  lazy-loaded shell shim on the source laptop. Substitute the local mamba path
  (or plain `mamba`) when copying commands.
- `.claude/settings.local.json` (permission allowlist) is git-ignored and
  carries absolute miniforge paths; a copy is in `local-config/` for reference,
  but Claude Code will rebuild it as you grant permissions.
- `LITCORE_PROJECT_ROOT` overrides project-root autodetection if the layout is
  unusual; otherwise nothing to set.

## How `.env` is actually consumed

The root `.env` accumulated ~66 keys across several architectures. Only these
are read by anything in `src/` today (verified by grep, Sept 2026):

| Keys | Reader | How it is loaded |
|---|---|---|
| `SEMANTIC_SCHOLAR_API_KEY`, `UNPAYWALL_EMAIL`, `CROSSREF_MAILTO`, `OPENALEX_EMAIL`, `PUBMED_EMAIL`, `PUBMED_TOOL`, `SPRINGER_API_KEY`, `SPRINGER_OPENACCESS_API_KEY`, `ENABLE_ARXIV` | `services/external_search.py` | `load_dotenv()` at import; python-dotenv walks up from that file, so the **root** `.env` is found regardless of cwd |
| `LITCORE_*` (paths, Zotero, log level, embedding device) | `literature_core/config.py` | pydantic `env_file=".env"` **relative to cwd** (`src/` under MCP), so the root `.env` is *not* read by this; use exported env vars or `src/.env`. The root `.env` contains no `LITCORE_` keys anyway |
| `OLLAMA_*`, `EMBEDDING_*`, `CHROMA_*`, `RERANKER_*`, `CLAUDE_*`, `LOG_*`, `GPU_*` | `config/ai_settings.py` | same cwd-relative `.env` rule |
| `WINDOWS_USER`, `PDF_STORAGE_PATH` | `mcp_server/tools/browser_pdf.py` | `os.getenv` at import |
| `LITERATURE_JSON_INDENT` | `literature_core/response.py` | `os.getenv` |

Everything else in the root `.env` has **no consumer in `src/`**:
`ANTHROPIC_API_KEY`, `HUGGINGFACE_API_TOKEN`, `UW_NETID` / `UW_PASSWORD`,
IEEE / JSTOR / Wiley / ORCID keys, `LITAGENTS_*`, `DATABASE_URL`, `API_*`,
`BROWSER_*`, `ENABLE_*` (other than `ENABLE_ARXIV`). They are leftovers from
the retired microservice architecture. The external-search keys are the ones
that demonstrably worked (Semantic Scholar, Unpaywall and Springer lookups run
through them); the rest never did anything in this codebase and can be dropped
when the new machine's `.env` is written. Root `.env.example` now lists only
the live keys; `src/.env.example` documents the `LITCORE_*` set.

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
  already exists for `literature`, delete it so the project config wins. The
  source laptop's `~/.mcp.json` entry (copied to `local-config/` in the
  transfer) is exactly that kind of absolute-path entry — do not recreate it.

## Future GUI work (notes)

The service layer (`src/services/`) is deliberately UI-agnostic — the MCP
tools are thin wrappers over it, and a GUI should be too. The natural shape
is a small FastAPI app importing the same services (search, papers,
collections, citations), with a web frontend for browsing/reading/analysis.
Nothing in the current architecture blocks this; keep business logic in
services and the GUI becomes another thin client alongside MCP.
