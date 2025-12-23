"""MCP Tools for Project-level Citation Management.

Tools for managing BibTeX files, tracking citations, and syncing
between project files and the literature database.
"""
import json
import os
import re
from pathlib import Path
from typing import Any
from difflib import SequenceMatcher

import httpx
from mcp.types import Tool, TextContent

API_BASE_URL = os.getenv("LITERATURE_DB_URL", "http://localhost:8001")


def parse_bibtex_file(content: str) -> list[dict]:
    """Parse BibTeX content into structured entries."""
    entries = []
    # Match @type{key, ... }
    entry_pattern = r'@(\w+)\s*\{\s*([^,]+)\s*,([^@]+)\}'
    field_pattern = r'(\w+)\s*=\s*[\{"]((?:[^{}"]|(?:\{[^{}]*\}))+)[\}"]\s*,?'

    for match in re.finditer(entry_pattern, content, re.DOTALL):
        entry_type, key, fields_text = match.groups()
        entry = {
            "key": key.strip(),
            "type": entry_type.lower(),
            "fields": {},
            "raw": match.group(0),
        }

        for field_match in re.finditer(field_pattern, fields_text, re.DOTALL):
            field_name = field_match.group(1).lower()
            field_value = field_match.group(2).strip()
            # Clean up LaTeX artifacts
            field_value = re.sub(r'[{}]', '', field_value)
            field_value = field_value.replace('\\&', '&')
            entry["fields"][field_name] = field_value

        entries.append(entry)

    return entries


def extract_citations_from_tex(content: str) -> list[dict]:
    """Extract all citation keys and their locations from TeX content."""
    citations = []
    # Match \cite{key1, key2, ...} and variants
    cite_pattern = r'\\(?:cite|citep|citet|citeyear|citeauthor)\{([^}]+)\}'

    lines = content.split('\n')
    for line_num, line in enumerate(lines, 1):
        for match in re.finditer(cite_pattern, line):
            keys = [k.strip() for k in match.group(1).split(',')]
            for key in keys:
                citations.append({
                    "key": key,
                    "line": line_num,
                    "context": line.strip()[:100],
                })

    return citations


def title_similarity(a: str, b: str) -> float:
    """Calculate similarity between two titles."""
    if not a or not b:
        return 0.0
    a_clean = re.sub(r'[^\w\s]', '', a.lower())
    b_clean = re.sub(r'[^\w\s]', '', b.lower())
    return SequenceMatcher(None, a_clean, b_clean).ratio()


async def list_tools() -> list[Tool]:
    """Return available project management tools."""
    return [
        # BibTeX File Tools
        Tool(
            name="parse_bib_file",
            description="Parse a BibTeX file and return structured entries with keys and fields",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to the .bib file",
                    },
                    "content": {
                        "type": "string",
                        "description": "BibTeX content (alternative to file_path)",
                    },
                },
            },
        ),
        Tool(
            name="link_bib_to_database",
            description="Match BibTeX entries to papers in database by DOI, title, or author+year",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to the .bib file to link",
                    },
                    "content": {
                        "type": "string",
                        "description": "BibTeX content (alternative to file_path)",
                    },
                    "min_similarity": {
                        "type": "number",
                        "default": 0.8,
                        "description": "Minimum title similarity for matching (0-1)",
                    },
                },
            },
        ),

        # Citation Scanning Tools
        Tool(
            name="scan_tex_citations",
            description="Scan TeX files for all \\cite{} commands and extract keys with locations",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to .tex file or directory to scan",
                    },
                    "recursive": {
                        "type": "boolean",
                        "default": True,
                        "description": "Recursively scan directories",
                    },
                },
                "required": ["file_path"],
            },
        ),
        Tool(
            name="get_citation_locations",
            description="Get all locations where a specific citation key is used",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to .tex file or directory to scan",
                    },
                    "citation_key": {
                        "type": "string",
                        "description": "The citation key to find",
                    },
                },
                "required": ["file_path", "citation_key"],
            },
        ),

        # Health Check Tools
        Tool(
            name="citation_health_check",
            description=(
                "Comprehensive check: orphan bib entries, missing citations, "
                "incomplete entries, duplicates"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "bib_path": {
                        "type": "string",
                        "description": "Path to .bib file",
                    },
                    "tex_path": {
                        "type": "string",
                        "description": "Path to .tex file or directory",
                    },
                },
                "required": ["bib_path", "tex_path"],
            },
        ),
        Tool(
            name="find_orphan_citations",
            description="Find bib entries that are never cited in any .tex file",
            inputSchema={
                "type": "object",
                "properties": {
                    "bib_path": {
                        "type": "string",
                        "description": "Path to .bib file",
                    },
                    "tex_path": {
                        "type": "string",
                        "description": "Path to .tex file or directory",
                    },
                },
                "required": ["bib_path", "tex_path"],
            },
        ),
        Tool(
            name="find_missing_citations",
            description="Find citation keys used in .tex files but not in .bib file",
            inputSchema={
                "type": "object",
                "properties": {
                    "bib_path": {
                        "type": "string",
                        "description": "Path to .bib file",
                    },
                    "tex_path": {
                        "type": "string",
                        "description": "Path to .tex file or directory",
                    },
                },
                "required": ["bib_path", "tex_path"],
            },
        ),
        Tool(
            name="find_incomplete_bib_entries",
            description="Find bib entries missing required fields (author, title, year)",
            inputSchema={
                "type": "object",
                "properties": {
                    "bib_path": {
                        "type": "string",
                        "description": "Path to .bib file",
                    },
                },
                "required": ["bib_path"],
            },
        ),
        Tool(
            name="find_duplicate_bib_entries",
            description="Find duplicate bib entries (same DOI or very similar titles)",
            inputSchema={
                "type": "object",
                "properties": {
                    "bib_path": {
                        "type": "string",
                        "description": "Path to .bib file",
                    },
                    "similarity_threshold": {
                        "type": "number",
                        "default": 0.9,
                        "description": "Title similarity threshold for duplicates (0-1)",
                    },
                },
                "required": ["bib_path"],
            },
        ),

        # Sync Tools
        Tool(
            name="sync_bib_from_database",
            description="Update bib entries with latest metadata from database (by DOI match)",
            inputSchema={
                "type": "object",
                "properties": {
                    "bib_path": {
                        "type": "string",
                        "description": "Path to .bib file to update",
                    },
                    "dry_run": {
                        "type": "boolean",
                        "default": True,
                        "description": "If true, show changes without writing",
                    },
                },
                "required": ["bib_path"],
            },
        ),
        Tool(
            name="import_bib_to_database",
            description="Import papers from .bib file into the database",
            inputSchema={
                "type": "object",
                "properties": {
                    "bib_path": {
                        "type": "string",
                        "description": "Path to .bib file",
                    },
                    "skip_existing": {
                        "type": "boolean",
                        "default": True,
                        "description": "Skip entries already in database (by DOI)",
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Tags to apply to imported papers",
                    },
                },
                "required": ["bib_path"],
            },
        ),
        Tool(
            name="export_database_to_bib",
            description="Export papers from database to BibTeX format",
            inputSchema={
                "type": "object",
                "properties": {
                    "paper_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "Paper IDs to export (omit for all)",
                    },
                    "output_path": {
                        "type": "string",
                        "description": "Path to write .bib file (omit to return content)",
                    },
                    "tag": {
                        "type": "string",
                        "description": "Export only papers with this tag",
                    },
                },
            },
        ),

        # Project Config Tools
        Tool(
            name="get_project_config",
            description="Get project citation configuration (bib files, tex paths, settings)",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_path": {
                        "type": "string",
                        "description": "Path to project root",
                    },
                },
                "required": ["project_path"],
            },
        ),
        Tool(
            name="set_project_config",
            description="Set project citation configuration",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_path": {
                        "type": "string",
                        "description": "Path to project root",
                    },
                    "bib_files": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of .bib file paths (relative to project)",
                    },
                    "tex_paths": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of .tex file/directory paths",
                    },
                },
                "required": ["project_path"],
            },
        ),
    ]


async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Execute a project management tool."""
    api_url = API_BASE_URL

    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            # === BibTeX Parsing Tools ===
            if name == "parse_bib_file":
                file_path = arguments.get("file_path")
                content = arguments.get("content")

                if file_path and not content:
                    path = Path(file_path).expanduser()
                    if not path.exists():
                        return [TextContent(type="text", text=json.dumps({
                            "error": f"File not found: {file_path}"
                        }))]
                    content = path.read_text()

                if not content:
                    return [TextContent(type="text", text=json.dumps({
                        "error": "Either file_path or content is required"
                    }))]

                entries = parse_bibtex_file(content)
                return [TextContent(type="text", text=json.dumps({
                    "total_entries": len(entries),
                    "entries": entries
                }, indent=2))]

            elif name == "link_bib_to_database":
                file_path = arguments.get("file_path")
                content = arguments.get("content")
                min_sim = arguments.get("min_similarity", 0.8)

                if file_path and not content:
                    path = Path(file_path).expanduser()
                    if not path.exists():
                        return [TextContent(type="text", text=json.dumps({
                            "error": f"File not found: {file_path}"
                        }))]
                    content = path.read_text()

                entries = parse_bibtex_file(content)
                results = {"matched": [], "unmatched": [], "errors": []}

                for entry in entries:
                    key = entry["key"]
                    fields = entry["fields"]
                    matched = False

                    # Try DOI match first (most reliable)
                    if "doi" in fields:
                        doi = fields["doi"]
                        resp = await client.get(
                            f"{api_url}/api/v1/search/keyword",
                            params={"query": doi, "limit": 1}
                        )
                        if resp.status_code == 200:
                            data = resp.json()
                            papers = data.get("results", data) if isinstance(data, dict) else data
                            if papers:
                                paper = papers[0]
                                if paper.get("doi") == doi:
                                    results["matched"].append({
                                        "bib_key": key,
                                        "paper_id": paper.get("id"),
                                        "paper_title": paper.get("title"),
                                        "match_type": "doi",
                                        "confidence": 1.0,
                                    })
                                    matched = True

                    # Try title match
                    if not matched and "title" in fields:
                        title = fields["title"]
                        resp = await client.get(
                            f"{api_url}/api/v1/search/keyword",
                            params={"query": title, "limit": 5}
                        )
                        if resp.status_code == 200:
                            data = resp.json()
                            papers = data.get("results", data) if isinstance(data, dict) else data
                            for paper in papers:
                                sim = title_similarity(title, paper.get("title", ""))
                                if sim >= min_sim:
                                    results["matched"].append({
                                        "bib_key": key,
                                        "paper_id": paper.get("id"),
                                        "paper_title": paper.get("title"),
                                        "match_type": "title",
                                        "confidence": round(sim, 3),
                                    })
                                    matched = True
                                    break

                    if not matched:
                        results["unmatched"].append({
                            "bib_key": key,
                            "title": fields.get("title", "Unknown"),
                            "doi": fields.get("doi"),
                        })

                return [TextContent(type="text", text=json.dumps({
                    "summary": {
                        "total": len(entries),
                        "matched": len(results["matched"]),
                        "unmatched": len(results["unmatched"]),
                    },
                    **results
                }, indent=2))]

            # === Citation Scanning Tools ===
            elif name == "scan_tex_citations":
                file_path = arguments["file_path"]
                recursive = arguments.get("recursive", True)

                path = Path(file_path).expanduser()
                if not path.exists():
                    return [TextContent(type="text", text=json.dumps({
                        "error": f"Path not found: {file_path}"
                    }))]

                all_citations = []
                files_scanned = []

                if path.is_file():
                    tex_files = [path]
                else:
                    pattern = "**/*.tex" if recursive else "*.tex"
                    tex_files = list(path.glob(pattern))

                for tex_file in tex_files:
                    content = tex_file.read_text()
                    citations = extract_citations_from_tex(content)
                    for c in citations:
                        c["file"] = str(tex_file)
                    all_citations.extend(citations)
                    files_scanned.append(str(tex_file))

                # Group by key
                by_key = {}
                for c in all_citations:
                    key = c["key"]
                    if key not in by_key:
                        by_key[key] = []
                    by_key[key].append({
                        "file": c["file"],
                        "line": c["line"],
                        "context": c["context"],
                    })

                return [TextContent(type="text", text=json.dumps({
                    "files_scanned": len(files_scanned),
                    "total_citations": len(all_citations),
                    "unique_keys": len(by_key),
                    "citations_by_key": by_key,
                }, indent=2))]

            elif name == "get_citation_locations":
                file_path = arguments["file_path"]
                citation_key = arguments["citation_key"]

                path = Path(file_path).expanduser()
                if not path.exists():
                    return [TextContent(type="text", text=json.dumps({
                        "error": f"Path not found: {file_path}"
                    }))]

                locations = []

                if path.is_file():
                    tex_files = [path]
                else:
                    tex_files = list(path.glob("**/*.tex"))

                for tex_file in tex_files:
                    content = tex_file.read_text()
                    citations = extract_citations_from_tex(content)
                    for c in citations:
                        if c["key"] == citation_key:
                            locations.append({
                                "file": str(tex_file),
                                "line": c["line"],
                                "context": c["context"],
                            })

                return [TextContent(type="text", text=json.dumps({
                    "citation_key": citation_key,
                    "total_occurrences": len(locations),
                    "locations": locations,
                }, indent=2))]

            # === Health Check Tools ===
            elif name == "citation_health_check":
                bib_path = Path(arguments["bib_path"]).expanduser()
                tex_path = Path(arguments["tex_path"]).expanduser()

                if not bib_path.exists():
                    return [TextContent(type="text", text=json.dumps({
                        "error": f"Bib file not found: {bib_path}"
                    }))]

                # Parse bib file
                bib_content = bib_path.read_text()
                bib_entries = parse_bibtex_file(bib_content)
                bib_keys = {e["key"] for e in bib_entries}

                # Scan tex files
                if tex_path.is_file():
                    tex_files = [tex_path]
                else:
                    tex_files = list(tex_path.glob("**/*.tex"))

                cited_keys = set()
                for tex_file in tex_files:
                    content = tex_file.read_text()
                    citations = extract_citations_from_tex(content)
                    for c in citations:
                        cited_keys.add(c["key"])

                # Find issues
                orphans = bib_keys - cited_keys
                missing = cited_keys - bib_keys

                # Check incomplete entries
                required_fields = {"author", "title", "year"}
                incomplete = []
                for entry in bib_entries:
                    missing_fields = required_fields - set(entry["fields"].keys())
                    if missing_fields:
                        incomplete.append({
                            "key": entry["key"],
                            "missing_fields": list(missing_fields),
                        })

                # Check duplicates by DOI
                doi_map = {}
                duplicates = []
                for entry in bib_entries:
                    doi = entry["fields"].get("doi")
                    if doi:
                        if doi in doi_map:
                            duplicates.append({
                                "keys": [doi_map[doi], entry["key"]],
                                "doi": doi,
                            })
                        else:
                            doi_map[doi] = entry["key"]

                return [TextContent(type="text", text=json.dumps({
                    "summary": {
                        "bib_entries": len(bib_entries),
                        "unique_citations": len(cited_keys),
                        "orphan_entries": len(orphans),
                        "missing_citations": len(missing),
                        "incomplete_entries": len(incomplete),
                        "duplicate_entries": len(duplicates),
                    },
                    "issues": {
                        "orphans": list(orphans),
                        "missing": list(missing),
                        "incomplete": incomplete,
                        "duplicates": duplicates,
                    },
                    "status": ("healthy"
                               if not (orphans or missing or incomplete or duplicates)
                               else "issues_found"),
                }, indent=2))]

            elif name == "find_orphan_citations":
                bib_path = Path(arguments["bib_path"]).expanduser()
                tex_path = Path(arguments["tex_path"]).expanduser()

                bib_content = bib_path.read_text()
                bib_entries = parse_bibtex_file(bib_content)
                bib_keys = {e["key"]: e for e in bib_entries}

                if tex_path.is_file():
                    tex_files = [tex_path]
                else:
                    tex_files = list(tex_path.glob("**/*.tex"))

                cited_keys = set()
                for tex_file in tex_files:
                    content = tex_file.read_text()
                    for c in extract_citations_from_tex(content):
                        cited_keys.add(c["key"])

                orphans = []
                for key in set(bib_keys.keys()) - cited_keys:
                    entry = bib_keys[key]
                    orphans.append({
                        "key": key,
                        "title": entry["fields"].get("title", "Unknown"),
                        "year": entry["fields"].get("year"),
                    })

                return [TextContent(type="text", text=json.dumps({
                    "total_orphans": len(orphans),
                    "orphans": orphans,
                }, indent=2))]

            elif name == "find_missing_citations":
                bib_path = Path(arguments["bib_path"]).expanduser()
                tex_path = Path(arguments["tex_path"]).expanduser()

                bib_content = bib_path.read_text()
                bib_entries = parse_bibtex_file(bib_content)
                bib_keys = {e["key"] for e in bib_entries}

                if tex_path.is_file():
                    tex_files = [tex_path]
                else:
                    tex_files = list(tex_path.glob("**/*.tex"))

                missing = {}
                for tex_file in tex_files:
                    content = tex_file.read_text()
                    for c in extract_citations_from_tex(content):
                        if c["key"] not in bib_keys:
                            if c["key"] not in missing:
                                missing[c["key"]] = []
                            missing[c["key"]].append({
                                "file": str(tex_file),
                                "line": c["line"],
                            })

                return [TextContent(type="text", text=json.dumps({
                    "total_missing": len(missing),
                    "missing_citations": missing,
                }, indent=2))]

            elif name == "find_incomplete_bib_entries":
                bib_path = Path(arguments["bib_path"]).expanduser()
                bib_content = bib_path.read_text()
                bib_entries = parse_bibtex_file(bib_content)

                required = {"author", "title", "year"}
                incomplete = []

                for entry in bib_entries:
                    missing = required - set(entry["fields"].keys())
                    if missing:
                        incomplete.append({
                            "key": entry["key"],
                            "type": entry["type"],
                            "missing_fields": list(missing),
                            "has_fields": list(entry["fields"].keys()),
                        })

                return [TextContent(type="text", text=json.dumps({
                    "total_entries": len(bib_entries),
                    "incomplete_count": len(incomplete),
                    "incomplete_entries": incomplete,
                }, indent=2))]

            elif name == "find_duplicate_bib_entries":
                bib_path = Path(arguments["bib_path"]).expanduser()
                threshold = arguments.get("similarity_threshold", 0.9)

                bib_content = bib_path.read_text()
                bib_entries = parse_bibtex_file(bib_content)

                duplicates = []

                # Check DOI duplicates
                doi_map = {}
                for entry in bib_entries:
                    doi = entry["fields"].get("doi")
                    if doi:
                        if doi in doi_map:
                            duplicates.append({
                                "type": "doi_match",
                                "keys": [doi_map[doi]["key"], entry["key"]],
                                "doi": doi,
                            })
                        else:
                            doi_map[doi] = entry

                # Check title similarity
                for i, e1 in enumerate(bib_entries):
                    for e2 in bib_entries[i+1:]:
                        t1 = e1["fields"].get("title", "")
                        t2 = e2["fields"].get("title", "")
                        sim = title_similarity(t1, t2)
                        if sim >= threshold:
                            duplicates.append({
                                "type": "title_similarity",
                                "keys": [e1["key"], e2["key"]],
                                "titles": [t1, t2],
                                "similarity": round(sim, 3),
                            })

                return [TextContent(type="text", text=json.dumps({
                    "total_entries": len(bib_entries),
                    "duplicates_found": len(duplicates),
                    "duplicates": duplicates,
                }, indent=2))]

            # === Sync Tools ===
            elif name == "sync_bib_from_database":
                bib_path = Path(arguments["bib_path"]).expanduser()
                dry_run = arguments.get("dry_run", True)

                bib_content = bib_path.read_text()
                bib_entries = parse_bibtex_file(bib_content)

                updates = []

                for entry in bib_entries:
                    doi = entry["fields"].get("doi")
                    if not doi:
                        continue

                    # Look up in database
                    resp = await client.get(
                        f"{api_url}/api/v1/search/keyword",
                        params={"query": doi, "limit": 1}
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        papers = data.get("results", data) if isinstance(data, dict) else data
                        if papers and papers[0].get("doi") == doi:
                            paper = papers[0]
                            changes = {}

                            # Check for updates
                            if paper.get("abstract") and not entry["fields"].get("abstract"):
                                changes["abstract"] = paper["abstract"][:200] + "..."
                            if paper.get("year") and not entry["fields"].get("year"):
                                changes["year"] = paper["year"]

                            if changes:
                                updates.append({
                                    "key": entry["key"],
                                    "changes": changes,
                                })

                result = {
                    "dry_run": dry_run,
                    "entries_checked": len(bib_entries),
                    "updates_available": len(updates),
                    "updates": updates,
                }

                if not dry_run and updates:
                    result["note"] = "Writing updates not yet implemented - use dry_run=true"

                return [TextContent(type="text", text=json.dumps(result, indent=2))]

            elif name == "import_bib_to_database":
                bib_path = Path(arguments["bib_path"]).expanduser()
                skip_existing = arguments.get("skip_existing", True)
                tags = arguments.get("tags", [])

                bib_content = bib_path.read_text()
                bib_entries = parse_bibtex_file(bib_content)

                results = {"imported": [], "skipped": [], "failed": []}

                for entry in bib_entries:
                    fields = entry["fields"]

                    # Check if exists by DOI
                    if skip_existing and "doi" in fields:
                        resp = await client.get(
                            f"{api_url}/api/v1/search/keyword",
                            params={"query": fields["doi"], "limit": 1}
                        )
                        if resp.status_code == 200:
                            data = resp.json()
                            papers = data.get("results", data) if isinstance(data, dict) else data
                            if papers and papers[0].get("doi") == fields["doi"]:
                                results["skipped"].append({
                                    "key": entry["key"],
                                    "reason": "DOI already exists",
                                    "paper_id": papers[0].get("id"),
                                })
                                continue

                    # Import paper
                    authors = []
                    if "author" in fields:
                        authors = [a.strip() for a in fields["author"].split(" and ")]

                    paper_data = {
                        "title": fields.get("title", "Unknown"),
                        "authors": authors,
                        "year": int(fields["year"]) if fields.get("year", "").isdigit() else None,
                        "doi": fields.get("doi"),
                        "abstract": fields.get("abstract"),
                        "journal": fields.get("journal"),
                        "tags": tags,
                    }

                    resp = await client.post(f"{api_url}/api/v1/papers", json=paper_data)
                    if resp.status_code in (200, 201):
                        paper = resp.json()
                        results["imported"].append({
                            "key": entry["key"],
                            "paper_id": paper.get("id"),
                            "title": paper.get("title"),
                        })
                    else:
                        results["failed"].append({
                            "key": entry["key"],
                            "error": resp.text[:200],
                        })

                return [TextContent(type="text", text=json.dumps({
                    "summary": {
                        "total": len(bib_entries),
                        "imported": len(results["imported"]),
                        "skipped": len(results["skipped"]),
                        "failed": len(results["failed"]),
                    },
                    **results,
                }, indent=2))]

            elif name == "export_database_to_bib":
                paper_ids = arguments.get("paper_ids")
                output_path = arguments.get("output_path")
                tag = arguments.get("tag")

                # Get papers
                if paper_ids:
                    papers = []
                    for pid in paper_ids:
                        resp = await client.get(f"{api_url}/api/v1/papers/{pid}")
                        if resp.status_code == 200:
                            papers.append(resp.json())
                elif tag:
                    resp = await client.get(
                        f"{api_url}/api/v1/search/tag",
                        params={"tag": tag, "limit": 100}
                    )
                    if resp.status_code == 200:
                        papers = resp.json()
                    else:
                        papers = []
                else:
                    resp = await client.get(f"{api_url}/api/v1/papers", params={"limit": 100})
                    if resp.status_code == 200:
                        data = resp.json()
                        papers = data.get("items", data) if isinstance(data, dict) else data
                    else:
                        papers = []

                # Generate BibTeX
                bibtex_entries = []
                for paper in papers:
                    # Generate key
                    first_author = ""
                    if paper.get("authors"):
                        auth = paper["authors"][0]
                        if isinstance(auth, dict):
                            first_author = auth.get("name", "").split()[-1].lower()
                        else:
                            first_author = str(auth).split()[-1].lower()
                    year = paper.get("year", "")
                    title = paper.get("title", "")
                    title_word = title.split()[0].lower() if title else ""
                    key = f"{first_author}{year}{title_word}"

                    fields = []
                    if paper.get("title"):
                        fields.append(f'  title = {{{paper["title"]}}}')
                    if paper.get("authors"):
                        auths = paper["authors"]
                        if auths and isinstance(auths[0], dict):
                            names = [a.get("name", "") for a in auths]
                        else:
                            names = [str(a) for a in auths]
                        fields.append(f'  author = {{{" and ".join(names)}}}')
                    if paper.get("year"):
                        fields.append(f'  year = {{{paper["year"]}}}')
                    if paper.get("journal"):
                        fields.append(f'  journal = {{{paper["journal"]}}}')
                    if paper.get("doi"):
                        fields.append(f'  doi = {{{paper["doi"]}}}')
                    if paper.get("abstract"):
                        fields.append(f'  abstract = {{{paper["abstract"]}}}')

                    entry = f"@article{{{key},\n" + ",\n".join(fields) + "\n}"
                    bibtex_entries.append(entry)

                bibtex_content = "\n\n".join(bibtex_entries)

                if output_path:
                    Path(output_path).expanduser().write_text(bibtex_content)
                    return [TextContent(type="text", text=json.dumps({
                        "status": "written",
                        "output_path": output_path,
                        "entries_exported": len(bibtex_entries),
                    }))]
                else:
                    return [TextContent(type="text", text=bibtex_content)]

            # === Project Config Tools ===
            elif name == "get_project_config":
                project_path = Path(arguments["project_path"]).expanduser()
                config_path = project_path / ".literature-config.json"

                if config_path.exists():
                    config = json.loads(config_path.read_text())
                else:
                    # Auto-detect
                    bib_files = list(project_path.glob("**/*.bib"))
                    tex_files = list(project_path.glob("**/*.tex"))
                    config = {
                        "configured": False,
                        "detected": {
                            "bib_files": [str(f.relative_to(project_path)) for f in bib_files[:5]],
                            "tex_directories": list(set(
                                str(f.parent.relative_to(project_path)) for f in tex_files[:20]
                            )),
                        },
                    }

                return [TextContent(type="text", text=json.dumps(config, indent=2))]

            elif name == "set_project_config":
                project_path = Path(arguments["project_path"]).expanduser()
                config_path = project_path / ".literature-config.json"

                config = {}
                if config_path.exists():
                    config = json.loads(config_path.read_text())

                if "bib_files" in arguments:
                    config["bib_files"] = arguments["bib_files"]
                if "tex_paths" in arguments:
                    config["tex_paths"] = arguments["tex_paths"]

                config["configured"] = True
                config_path.write_text(json.dumps(config, indent=2))

                return [TextContent(type="text", text=json.dumps({
                    "status": "saved",
                    "config_path": str(config_path),
                    "config": config,
                }, indent=2))]

            else:
                return [TextContent(type="text", text=f"Unknown project tool: {name}")]

        except Exception as e:
            return [TextContent(type="text", text=json.dumps({"error": str(e)}))]
