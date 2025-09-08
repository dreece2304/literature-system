#!/usr/bin/env python
"""Link Zotero PDFs to papers in the literature database."""
import sys
from pathlib import Path
from typing import Dict, List, Optional
import shutil
import requests
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn

# Add src to path for imports
sys.path.append(str(Path(__file__).parent.parent))

from src.database import get_session
from src.models import Paper
from src.extractors.zotero_local_api import ZoteroLocalAPI
from src.utils.file_utils import calculate_file_hash
from src.utils.path_manager import PathManager


def get_zotero_attachments() -> Dict[str, List[Dict]]:
    """Get all attachments from Zotero for each paper."""
    console = Console()
    
    # Get all items with attachments from Zotero
    console.print("Fetching items and attachments from Zotero...")
    
    try:
        response = requests.get("http://localhost:23119/api/users/0/items?itemType=attachment", timeout=30)
        if response.status_code != 200:
            console.print(f"[red]Failed to fetch attachments: HTTP {response.status_code}[/red]")
            return {}
        
        attachments = response.json()
        console.print(f"Found {len(attachments)} attachments in Zotero")
        
        # Group attachments by parent item
        attachments_by_parent = {}
        
        for attachment in attachments:
            data = attachment.get('data', {})
            parent_item = data.get('parentItem')
            
            if parent_item and data.get('itemType') == 'attachment':
                content_type = data.get('contentType', '')
                filename = data.get('filename', '')
                
                # Only process PDF attachments
                if 'pdf' in content_type.lower() or filename.lower().endswith('.pdf'):
                    if parent_item not in attachments_by_parent:
                        attachments_by_parent[parent_item] = []
                    
                    attachments_by_parent[parent_item].append({
                        'key': attachment.get('key'),
                        'filename': filename,
                        'content_type': content_type,
                        'url': data.get('url', ''),
                        'path': data.get('path', '')
                    })
        
        console.print(f"Found PDF attachments for {len(attachments_by_parent)} papers")
        return attachments_by_parent
        
    except Exception as e:
        console.print(f"[red]Error fetching Zotero attachments: {e}[/red]")
        return {}


def link_pdfs_to_papers():
    """Link Zotero PDF attachments to papers in the database."""
    console = Console()
    session = next(get_session())
    path_manager = PathManager()
    
    try:
        # Get Zotero attachments
        attachments_by_parent = get_zotero_attachments()
        
        if not attachments_by_parent:
            console.print("[yellow]No PDF attachments found in Zotero[/yellow]")
            return
        
        # Get papers from database
        papers = session.query(Paper).filter(Paper.zotero_key.isnot(None)).all()
        papers_by_key = {paper.zotero_key: paper for paper in papers}
        
        linked_count = 0
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            console=console
        ) as progress:
            
            task = progress.add_task("Linking PDFs...", total=len(attachments_by_parent))
            
            for parent_key, pdfs in attachments_by_parent.items():
                paper = papers_by_key.get(parent_key)
                
                if paper and not paper.file_path and pdfs:
                    # Use the first PDF attachment
                    pdf_info = pdfs[0]
                    
                    # For now, just record that this paper has a PDF available in Zotero
                    # In a full implementation, you'd download/copy the actual file
                    
                    console.print(f"[green]Found PDF for: {paper.title[:50]}...[/green]")
                    console.print(f"  Filename: {pdf_info['filename']}")
                    
                    # Record the availability (placeholder - actual file linking would go here)
                    # paper.file_path = f"zotero://{pdf_info['key']}/{pdf_info['filename']}"
                    
                    linked_count += 1
                
                progress.advance(task)
        
        console.print(f"\n[green]✓ Found {linked_count} papers with PDFs in Zotero[/green]")
        
        # Show some examples
        if linked_count > 0:
            console.print("\n[blue]Sample papers with PDFs:[/blue]")
            count = 0
            for parent_key, pdfs in attachments_by_parent.items():
                paper = papers_by_key.get(parent_key)
                if paper and pdfs and count < 5:
                    pdf_info = pdfs[0]
                    console.print(f"  • {paper.title[:60]}...")
                    console.print(f"    PDF: {pdf_info['filename']}")
                    count += 1
        
    finally:
        session.close()


def show_zotero_storage_info():
    """Show information about Zotero storage paths."""
    console = Console()
    path_manager = PathManager()
    
    # Check configured Zotero path
    zotero_path = path_manager.get_zotero_path()
    console.print(f"Configured Zotero path: {zotero_path}")
    console.print(f"Path exists: {zotero_path.exists()}")
    
    if zotero_path.exists():
        # Check for storage subdirectory
        storage_path = zotero_path / "storage"
        console.print(f"Storage path: {storage_path}")
        console.print(f"Storage exists: {storage_path.exists()}")
        
        if storage_path.exists():
            # Count PDF files
            pdf_files = list(storage_path.rglob("*.pdf"))
            console.print(f"PDF files in storage: {len(pdf_files)}")
            
            # Show some examples
            if pdf_files:
                console.print("\nSample PDF files:")
                for pdf_file in pdf_files[:5]:
                    console.print(f"  • {pdf_file.relative_to(storage_path)}")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Link Zotero PDFs to literature database")
    parser.add_argument('--info', action='store_true', help='Show Zotero storage information')
    parser.add_argument('--link', action='store_true', help='Link PDFs to papers')
    
    args = parser.parse_args()
    
    if args.info:
        show_zotero_storage_info()
    elif args.link:
        link_pdfs_to_papers()
    else:
        parser.print_help()