#!/usr/bin/env python
"""Debug GROBID output to understand parsing issues."""
from __future__ import annotations

import sys
from pathlib import Path
import requests
from xml.etree import ElementTree as ET

# Add src to path
src_path = Path(__file__).parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from literature_core import get_session, Paper


def get_grobid_xml(paper_id: int) -> str:
    """Get raw GROBID TEI XML for a paper."""
    with get_session() as session:
        paper = session.query(Paper).filter(Paper.id == paper_id).first()
        if not paper or not paper.file_path:
            return ""
        file_path = Path(paper.file_path)

    grobid_url = "http://localhost:8070/api/processFulltextDocument"
    with open(file_path, "rb") as pdf_file:
        response = requests.post(
            grobid_url,
            files={"input": pdf_file},
            data={"consolidateHeader": "1", "consolidateCitations": "0"},
            timeout=120,
        )
    return response.text


def analyze_grobid_sections(tei_xml: str) -> None:
    """Analyze what GROBID detected as sections."""
    ns = {"tei": "http://www.tei-c.org/ns/1.0"}

    try:
        root = ET.fromstring(tei_xml)
    except ET.ParseError as e:
        print(f"Failed to parse XML: {e}")
        return

    # Print title
    title = root.find(".//tei:titleStmt/tei:title", ns)
    if title is not None:
        print(f"Title: {title.text[:80] if title.text else 'N/A'}...")

    # Check abstract
    abstract = root.find(".//tei:abstract", ns)
    print(f"\nAbstract present: {abstract is not None}")
    if abstract is not None:
        abstract_text = "".join(abstract.itertext())
        print(f"Abstract length: {len(abstract_text)} chars")

    # Find all divs (sections) in body
    body = root.find(".//tei:body", ns)
    if body is None:
        print("No body found!")
        return

    print(f"\nSection structure in body:")
    divs = body.findall(".//tei:div", ns)
    print(f"Total divs: {len(divs)}")

    for i, div in enumerate(divs[:15]):  # First 15
        head = div.find("tei:head", ns)
        head_text = head.text if head is not None and head.text else "[NO HEAD]"
        n_attr = div.get("n", "no-n")

        # Count paragraphs
        p_count = len(div.findall("tei:p", ns))
        p_text_len = sum(len("".join(p.itertext())) for p in div.findall("tei:p", ns))

        print(f"  [{i+1}] n='{n_attr}' head='{head_text[:60]}' "
              f"({p_count} paragraphs, {p_text_len} chars)")

    # Check for journal name patterns
    print("\n--- Checking for journal name patterns in div heads ---")
    journal_patterns = ["acs ", "energy letters", "wiley", "elsevier", "springer",
                        "nature ", "science ", "published", "doi:", "view article"]
    for div in divs:
        head = div.find("tei:head", ns)
        if head is not None and head.text:
            head_lower = head.text.lower()
            for pattern in journal_patterns:
                if pattern in head_lower:
                    print(f"  Found '{pattern}' in: {head.text[:80]}")


if __name__ == "__main__":
    paper_id = int(sys.argv[1]) if len(sys.argv) > 1 else 11

    print(f"Getting GROBID output for Paper {paper_id}...")
    tei_xml = get_grobid_xml(paper_id)

    if tei_xml:
        # Save raw XML for inspection
        output_path = Path(f"/tmp/paper_{paper_id}_grobid.xml")
        output_path.write_text(tei_xml)
        print(f"Raw XML saved to: {output_path}")

        analyze_grobid_sections(tei_xml)
    else:
        print("Failed to get GROBID output")
