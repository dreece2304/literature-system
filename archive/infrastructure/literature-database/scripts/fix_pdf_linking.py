#!/usr/bin/env python
"""Fixed PDF linking script with better session management."""
import sys
import requests
from pathlib import Path
from typing import Dict, List, Tuple
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn

# Add src to path for imports
sys.path.append(str(Path(__file__).parent.parent))

from src.database import get_session
from src.models import Paper
from src.utils.path_manager import PathManager


def get_zotero_pdf_mappings() -> List[Tuple[str, str, Path]]:
    """Get mappings of (paper_zotero_key, attachment_key, pdf_path)."""
    console = Console()
    path_manager = PathManager()
    
    try:
        # Get attachment relationships from Zotero API
        console.print("Fetching PDF attachments from Zotero...")
        
        response = requests.get("http://localhost:23119/api/users/0/items?itemType=attachment", timeout=30)
        if response.status_code != 200:
            console.print(f"[red]Failed to fetch attachments[/red]")
            return []
        
        attachments = response.json()
        
        # Build attachment key to parent mapping
        attachment_to_parent = {}
        for attachment in attachments:
            data = attachment.get('data', {})
            attachment_key = attachment.get('key')
            parent_item = data.get('parentItem')
            content_type = data.get('contentType', '')
            filename = data.get('filename', '')
            
            if (parent_item and attachment_key and 
                ('pdf' in content_type.lower() or filename.lower().endswith('.pdf'))):
                attachment_to_parent[attachment_key] = parent_item
        
        console.print(f"Found {len(attachment_to_parent)} PDF attachments")
        
        # Get Zotero storage files
        storage_path = path_manager.get_zotero_path() / "storage"
        if not storage_path.exists():
            console.print(f"[red]Zotero storage not found: {storage_path}[/red]")
            return []
        
        storage_files = {}
        for folder in storage_path.iterdir():
            if folder.is_dir() and len(folder.name) == 8:
                for pdf_file in folder.glob("*.pdf"):
                    storage_files[folder.name] = pdf_file
                    break
        
        console.print(f"Found {len(storage_files)} PDF files in storage")
        
        # Create mappings
        mappings = []
        for attachment_key, parent_key in attachment_to_parent.items():
            if attachment_key in storage_files:
                pdf_path = storage_files[attachment_key]
                mappings.append((parent_key, attachment_key, pdf_path))
        
        console.print(f"Created {len(mappings)} paper-to-PDF mappings")
        return mappings
        
    except Exception as e:
        console.print(f"[red]Error creating mappings: {e}[/red]")
        return []


def link_pdfs_to_database(mappings: List[Tuple[str, str, Path]], dry_run: bool = False):
    """Link PDFs to database papers with improved session management."""
    console = Console()
    
    if not mappings:
        console.print("[yellow]No mappings to process[/yellow]")
        return
    
    session = next(get_session())
    
    try:
        # Get papers from database
        console.print("Loading papers from database...")
        papers = session.query(Paper).filter(Paper.zotero_key.isnot(None)).all()
        papers_by_key = {paper.zotero_key: paper for paper in papers}
        
        # Filter mappings to only include papers we have
        valid_mappings = []
        for parent_key, attachment_key, pdf_path in mappings:
            if parent_key in papers_by_key:
                paper = papers_by_key[parent_key]
                # Only include if paper doesn't already have a file_path
                if not paper.file_path:
                    valid_mappings.append((paper, pdf_path))
        
        console.print(f"Found {len(valid_mappings)} papers to link")
        
        if not valid_mappings:
            console.print("[yellow]No papers need linking[/yellow]")
            return
        
        if dry_run:
            console.print("[yellow]DRY RUN - No changes will be made[/yellow]")
            for paper, pdf_path in valid_mappings[:5]:  # Show first 5
                console.print(f"Would link: {paper.title[:50]}... -> {pdf_path.name}")
            if len(valid_mappings) > 5:
                console.print(f"... and {len(valid_mappings) - 5} more")
            return
        
        # Process the linking
        linked_count = 0
        failed_count = 0
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            console=console
        ) as progress:
            
            task = progress.add_task("Linking PDFs...", total=len(valid_mappings))
            
            for paper, pdf_path in valid_mappings:
                try:
                    # Verify PDF file exists
                    if not pdf_path.exists():
                        console.print(f"[yellow]PDF not found: {pdf_path}[/yellow]")
                        failed_count += 1
                        progress.advance(task)
                        continue
                    
                    # Update the paper
                    paper.file_path = str(pdf_path)
                    
                    # Calculate hash if possible
                    try:
                        from src.utils.file_utils import calculate_file_hash
                        paper.file_hash = calculate_file_hash(pdf_path)
                    except Exception:
                        pass  # Hash calculation is optional
                    
                    linked_count += 1
                    
                    # Commit every 50 records to avoid large transactions
                    if linked_count % 50 == 0:
                        session.commit()
                        console.print(f"[green]Committed {linked_count} links...[/green]")
                    
                except Exception as e:
                    console.print(f"[red]Error linking {pdf_path.name}: {e}[/red]")
                    failed_count += 1
                
                progress.advance(task)
        
        # Final commit
        if linked_count > 0:
            session.commit()
            console.print(f"[green]✓ Final commit successful![/green]")
        
        # Show results
        console.print(f"\n[green]✓ PDF linking complete![/green]")
        console.print(f"  🔗 Papers linked: {linked_count}")
        console.print(f"  ❌ Failed: {failed_count}")
        console.print(f"  💾 No additional storage used (PDFs stay in Zotero)")
        
        # Verify the results
        console.print("\n[blue]Verifying results...[/blue]")
        papers_with_pdfs = session.query(Paper).filter(Paper.file_path.isnot(None)).count()
        console.print(f"Papers with PDFs in database: {papers_with_pdfs}")
        
    except Exception as e:
        session.rollback()
        console.print(f"[red]Transaction failed, rolling back: {e}[/red]")
        raise
    finally:
        session.close()


def main():
    """Main function."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Fixed PDF linking script")
    parser.add_argument('--dry-run', action='store_true', help='Show what would be linked without making changes')
    parser.add_argument('--link', action='store_true', help='Actually link the PDFs')
    
    args = parser.parse_args()
    
    # Get the mappings
    mappings = get_zotero_pdf_mappings()
    
    if args.dry_run:
        link_pdfs_to_database(mappings, dry_run=True)
    elif args.link:
        link_pdfs_to_database(mappings, dry_run=False)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()