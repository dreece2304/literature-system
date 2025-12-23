"""MCP Tools for Import/Export operations."""
import json
import os
import re
from typing import Any

import httpx
from mcp.types import Tool, TextContent

from src.services.external_search import ExternalSearchService

API_BASE_URL = os.getenv("LITERATURE_DB_URL", "http://localhost:8001")


async def list_tools() -> list[Tool]:
    """Return available import/export tools."""
    return [
        Tool(
            name="import_bibtex",
            description="Import papers from BibTeX content. Parses entries and adds papers to the database.",
            inputSchema={
                "type": "object",
                "properties": {
                    "bibtex_content": {
                        "type": "string",
                        "description": "Raw BibTeX content to parse and import",
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Tags to apply to all imported papers",
                    },
                    "collection_id": {
                        "type": "integer",
                        "description": "Add imported papers to this collection",
                    },
                },
                "required": ["bibtex_content"],
            },
        ),
        Tool(
            name="export_papers",
            description="Export papers from the database in various formats",
            inputSchema={
                "type": "object",
                "properties": {
                    "paper_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "List of paper IDs to export (omit for all papers)",
                    },
                    "format": {
                        "type": "string",
                        "enum": ["bibtex", "json", "csv"],
                        "default": "bibtex",
                        "description": "Export format",
                    },
                    "include_abstract": {
                        "type": "boolean",
                        "default": True,
                        "description": "Include abstracts in export",
                    },
                    "include_notes": {
                        "type": "boolean",
                        "default": False,
                        "description": "Include notes in export (JSON only)",
                    },
                },
            },
        ),
        Tool(
            name="import_from_external",
            description="Import a paper from external search results (using DOI, arXiv ID, or title lookup)",
            inputSchema={
                "type": "object",
                "properties": {
                    "doi": {
                        "type": "string",
                        "description": "DOI of paper to import",
                    },
                    "arxiv_id": {
                        "type": "string",
                        "description": "arXiv ID of paper to import",
                    },
                    "title": {
                        "type": "string",
                        "description": "Title of paper to look up and import",
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Tags to apply to imported paper",
                    },
                    "collection_id": {
                        "type": "integer",
                        "description": "Add imported paper to this collection",
                    },
                },
            },
        ),
        Tool(
            name="export_collection",
            description="Export all papers in a collection",
            inputSchema={
                "type": "object",
                "properties": {
                    "collection_id": {
                        "type": "integer",
                        "description": "Collection ID to export",
                    },
                    "format": {
                        "type": "string",
                        "enum": ["bibtex", "json", "csv"],
                        "default": "bibtex",
                        "description": "Export format",
                    },
                    "include_subcollections": {
                        "type": "boolean",
                        "default": False,
                        "description": "Include papers from child collections",
                    },
                },
                "required": ["collection_id"],
            },
        ),
    ]


def parse_bibtex(bibtex_content: str) -> list[dict]:
    """Parse BibTeX content into paper dictionaries."""
    entries = []
    # Simple BibTeX parser - handles common cases
    entry_pattern = r'@(\w+)\s*\{\s*([^,]+)\s*,([^@]+)\}'
    field_pattern = r'(\w+)\s*=\s*[\{"]((?:[^{}"]|(?:\{[^{}]*\}))+)[\}"]\s*,?'

    for match in re.finditer(entry_pattern, bibtex_content, re.DOTALL):
        entry_type, key, fields_text = match.groups()
        paper = {
            "bibtex_key": key.strip(),
            "bibtex_type": entry_type.lower(),
        }

        for field_match in re.finditer(field_pattern, fields_text, re.DOTALL):
            field_name = field_match.group(1).lower()
            field_value = field_match.group(2).strip()
            # Clean up LaTeX artifacts
            field_value = re.sub(r'[{}]', '', field_value)
            field_value = field_value.replace('\\&', '&')

            if field_name == "title":
                paper["title"] = field_value
            elif field_name == "author":
                # Split authors by 'and'
                authors = [a.strip() for a in field_value.split(' and ')]
                paper["authors"] = authors
            elif field_name == "year":
                try:
                    paper["year"] = int(field_value)
                except ValueError:
                    pass
            elif field_name == "doi":
                paper["doi"] = field_value
            elif field_name == "abstract":
                paper["abstract"] = field_value
            elif field_name == "journal":
                paper["journal"] = field_value
            elif field_name == "volume":
                paper["volume"] = field_value
            elif field_name == "pages":
                paper["pages"] = field_value
            elif field_name == "eprint":
                paper["arxiv_id"] = field_value

        if "title" in paper:
            entries.append(paper)

    return entries


def format_bibtex_entry(paper: dict) -> str:
    """Format a paper as a BibTeX entry."""
    # Generate citation key if not present
    key = paper.get("citation_key") or ""
    if not key:
        first_author = ""
        if paper.get("authors"):
            author = paper["authors"][0]
            if isinstance(author, dict):
                first_author = author.get("name", "").split()[-1].lower()
            else:
                first_author = str(author).split()[-1].lower()
        year = paper.get("year", "")
        title_word = (paper.get("title", "").split()[0] if paper.get("title") else "").lower()
        key = f"{first_author}{year}{title_word}"

    entry_type = "article"  # Default type

    fields = []
    if paper.get("title"):
        fields.append(f'  title = {{{paper["title"]}}}')
    if paper.get("authors"):
        authors_list = paper["authors"]
        if authors_list and isinstance(authors_list[0], dict):
            author_names = [a.get("name", "") for a in authors_list]
        else:
            author_names = [str(a) for a in authors_list]
        fields.append(f'  author = {{{" and ".join(author_names)}}}')
    if paper.get("year"):
        fields.append(f'  year = {{{paper["year"]}}}')
    if paper.get("journal"):
        fields.append(f'  journal = {{{paper["journal"]}}}')
    if paper.get("volume"):
        fields.append(f'  volume = {{{paper["volume"]}}}')
    if paper.get("pages"):
        fields.append(f'  pages = {{{paper["pages"]}}}')
    if paper.get("doi"):
        fields.append(f'  doi = {{{paper["doi"]}}}')
    if paper.get("abstract"):
        fields.append(f'  abstract = {{{paper["abstract"]}}}')
    if paper.get("arxiv_id"):
        fields.append(f'  eprint = {{{paper["arxiv_id"]}}}')

    return f"@{entry_type}{{{key},\n" + ",\n".join(fields) + "\n}"


async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Execute an import/export tool."""
    api_url = API_BASE_URL

    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            if name == "import_bibtex":
                bibtex_content = arguments["bibtex_content"]
                tags = arguments.get("tags", [])
                collection_id = arguments.get("collection_id")

                # Parse BibTeX
                entries = parse_bibtex(bibtex_content)
                if not entries:
                    return [TextContent(type="text", text=json.dumps({
                        "status": "error",
                        "message": "No valid BibTeX entries found"
                    }))]

                results = {"imported": [], "failed": [], "skipped": []}

                for entry in entries:
                    try:
                        # Add paper
                        paper_data = {
                            "title": entry.get("title", "Unknown Title"),
                            "abstract": entry.get("abstract"),
                            "year": entry.get("year"),
                            "doi": entry.get("doi"),
                            "arxiv_id": entry.get("arxiv_id"),
                            "journal": entry.get("journal"),
                            "volume": entry.get("volume"),
                            "pages": entry.get("pages"),
                            "authors": entry.get("authors", []),
                            "tags": tags,
                        }

                        response = await client.post(
                            f"{api_url}/api/v1/papers",
                            json=paper_data
                        )

                        if response.status_code in (200, 201):
                            paper = response.json()
                            results["imported"].append({
                                "id": paper.get("id"),
                                "title": paper.get("title"),
                                "bibtex_key": entry.get("bibtex_key")
                            })

                            # Add to collection if specified
                            if collection_id:
                                await client.post(
                                    f"{api_url}/api/v1/collections/{collection_id}/papers",
                                    json={"paper_ids": [paper.get("id")]}
                                )
                        elif response.status_code == 409:
                            results["skipped"].append({
                                "title": entry.get("title"),
                                "reason": "Already exists"
                            })
                        else:
                            results["failed"].append({
                                "title": entry.get("title"),
                                "error": response.text[:200]
                            })

                    except Exception as e:
                        results["failed"].append({
                            "title": entry.get("title", "Unknown"),
                            "error": str(e)
                        })

                return [TextContent(type="text", text=json.dumps({
                    "status": "completed",
                    "total_entries": len(entries),
                    "imported": len(results["imported"]),
                    "skipped": len(results["skipped"]),
                    "failed": len(results["failed"]),
                    "details": results
                }, indent=2))]

            elif name == "export_papers":
                paper_ids = arguments.get("paper_ids")
                export_format = arguments.get("format", "bibtex")
                include_abstract = arguments.get("include_abstract", True)
                include_notes = arguments.get("include_notes", False)

                # Get papers
                if paper_ids:
                    papers = []
                    for pid in paper_ids:
                        resp = await client.get(f"{api_url}/api/v1/papers/{pid}")
                        if resp.status_code == 200:
                            papers.append(resp.json())
                else:
                    resp = await client.get(f"{api_url}/api/v1/papers", params={"limit": 100})
                    if resp.status_code == 200:
                        data = resp.json()
                        papers = data.get("items", data) if isinstance(data, dict) else data
                    else:
                        papers = []

                if export_format == "bibtex":
                    bibtex_entries = []
                    for paper in papers:
                        if not include_abstract:
                            paper = {k: v for k, v in paper.items() if k != "abstract"}
                        bibtex_entries.append(format_bibtex_entry(paper))
                    output = "\n\n".join(bibtex_entries)
                    return [TextContent(type="text", text=output)]

                elif export_format == "json":
                    if include_notes:
                        for paper in papers:
                            notes_resp = await client.get(
                                f"{api_url}/api/v1/notes/paper/{paper['id']}"
                            )
                            if notes_resp.status_code == 200:
                                paper["notes"] = notes_resp.json()
                    return [TextContent(type="text", text=json.dumps(papers, indent=2))]

                elif export_format == "csv":
                    import csv
                    import io
                    output = io.StringIO()
                    fieldnames = ["id", "title", "authors", "year", "journal", "doi"]
                    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction='ignore')
                    writer.writeheader()
                    for paper in papers:
                        row = dict(paper)
                        if row.get("authors"):
                            if isinstance(row["authors"][0], dict):
                                row["authors"] = "; ".join(a.get("name", "") for a in row["authors"])
                            else:
                                row["authors"] = "; ".join(str(a) for a in row["authors"])
                        writer.writerow(row)
                    return [TextContent(type="text", text=output.getvalue())]

            elif name == "import_from_external":
                doi = arguments.get("doi")
                arxiv_id = arguments.get("arxiv_id")
                title = arguments.get("title")
                tags = arguments.get("tags", [])
                collection_id = arguments.get("collection_id")

                # Look up metadata using multiple sources for corroboration
                external_service = ExternalSearchService()
                sources_checked = []
                all_results = {}

                # Query multiple APIs based on what we have
                if doi:
                    # CrossRef - primary for DOI (direct lookup, not search)
                    try:
                        cr_result = await external_service.lookup_by_doi(doi)
                        if cr_result:
                            all_results["crossref"] = cr_result
                            sources_checked.append("crossref")
                    except Exception:
                        pass

                    # OpenAlex - secondary for DOI
                    try:
                        oa_results = await external_service._search_openalex(doi, limit=1)
                        if oa_results:
                            all_results["openalex"] = oa_results[0]
                            sources_checked.append("openalex")
                    except Exception:
                        pass

                elif arxiv_id:
                    # arXiv - primary for arXiv ID
                    try:
                        arxiv_results = await external_service._search_arxiv(arxiv_id, limit=1)
                        if arxiv_results:
                            all_results["arxiv"] = arxiv_results[0]
                            sources_checked.append("arxiv")
                    except Exception:
                        pass

                elif title:
                    # Search multiple sources by title
                    try:
                        oa_results = await external_service._search_openalex(title, limit=3)
                        if oa_results:
                            def sim(r): return external_service._title_similarity(title, r.title)
                            best = max(oa_results, key=sim)
                            if sim(best) > 0.5:
                                all_results["openalex"] = best
                                sources_checked.append("openalex")
                    except Exception:
                        pass

                    try:
                        cr_results = await external_service._search_crossref_multi(title, limit=3)
                        if cr_results:
                            best = max(cr_results, key=lambda r: r.confidence)
                            if best.confidence > 0.5:
                                all_results["crossref"] = best
                                sources_checked.append("crossref")
                    except Exception:
                        pass

                # Merge results from multiple sources - prefer completeness
                metadata = None
                if all_results:
                    # Start with the first result
                    primary_source = list(all_results.keys())[0]
                    r = all_results[primary_source]
                    metadata = {
                        "title": r.title,
                        "authors": r.authors or [],
                        "year": r.year,
                        "doi": r.doi,
                        "abstract": r.abstract,
                        "journal": getattr(r, 'journal', None),
                        "arxiv_id": getattr(r, 'arxiv_id', None),
                        "sources_checked": sources_checked,
                        "primary_source": primary_source,
                    }

                    # Fill in missing fields from other sources
                    for source_name, result in all_results.items():
                        if source_name == primary_source:
                            continue
                        if not metadata["abstract"] and result.abstract:
                            metadata["abstract"] = result.abstract
                        if not metadata["doi"] and result.doi:
                            metadata["doi"] = result.doi
                        if not metadata["authors"] and result.authors:
                            metadata["authors"] = result.authors
                        if not metadata.get("journal") and getattr(result, 'journal', None):
                            metadata["journal"] = result.journal

                if not metadata:
                    return [TextContent(type="text", text=json.dumps({
                        "status": "error",
                        "message": "Could not find paper metadata"
                    }))]

                # Create paper
                paper_data = {
                    "title": metadata.get("title", "Unknown Title"),
                    "abstract": metadata.get("abstract"),
                    "year": metadata.get("year"),
                    "doi": metadata.get("doi") or doi,
                    "arxiv_id": metadata.get("arxiv_id") or arxiv_id,
                    "journal": metadata.get("journal"),
                    "authors": metadata.get("authors", []),
                    "tags": tags,
                }

                response = await client.post(f"{api_url}/api/v1/papers", json=paper_data)

                if response.status_code in (200, 201):
                    paper = response.json()

                    # Add to collection if specified
                    if collection_id:
                        await client.post(
                            f"{api_url}/api/v1/collections/{collection_id}/papers",
                            json={"paper_ids": [paper.get("id")]}
                        )

                    return [TextContent(type="text", text=json.dumps({
                        "status": "success",
                        "paper": paper
                    }, indent=2))]
                else:
                    return [TextContent(type="text", text=json.dumps({
                        "status": "error",
                        "message": response.text[:500]
                    }))]

            elif name == "export_collection":
                collection_id = arguments["collection_id"]
                export_format = arguments.get("format", "bibtex")
                include_subcollections = arguments.get("include_subcollections", False)

                # Get collection
                resp = await client.get(f"{api_url}/api/v1/collections/{collection_id}")
                if resp.status_code != 200:
                    return [TextContent(type="text", text=json.dumps({
                        "status": "error",
                        "message": "Collection not found"
                    }))]

                collection = resp.json()
                paper_ids = collection.get("paper_ids", [])

                # Include subcollections if requested
                if include_subcollections:
                    children_resp = await client.get(
                        f"{api_url}/api/v1/collections/{collection_id}/children"
                    )
                    if children_resp.status_code == 200:
                        for child in children_resp.json():
                            paper_ids.extend(child.get("paper_ids", []))
                    paper_ids = list(set(paper_ids))  # Deduplicate

                # Reuse export_papers logic
                return await call_tool("export_papers", {
                    "paper_ids": paper_ids,
                    "format": export_format,
                    "include_abstract": True
                })

            else:
                return [TextContent(type="text", text=f"Unknown import/export tool: {name}")]

        except httpx.HTTPStatusError as e:
            error_detail = e.response.text[:500] if e.response.text else str(e)
            return [TextContent(
                type="text",
                text=json.dumps({"error": f"HTTP {e.response.status_code}", "detail": error_detail})
            )]
        except Exception as e:
            return [TextContent(type="text", text=json.dumps({"error": str(e)}))]
