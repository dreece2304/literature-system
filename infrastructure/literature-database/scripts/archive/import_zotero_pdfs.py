#!/usr/bin/env python
"""Import and organize PDF files from Zotero storage."""
import sys
import shutil
import requests
from pathlib import Path
from typing import Dict, List
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeRemainingColumn
from rich.prompt import Confirm

# Add src to path for imports
sys.path.append(str(Path(__file__).parent.parent))

from src.database import get_session
from src.models import Paper
from src.utils.file_utils import calculate_file_hash
from src.utils.path_manager import PathManager
from src.extractors.pdf_extractor import PDFExtractor


def get_zotero_storage_files() -> Dict[str, Path]:
    """Map Zotero keys to their PDF files in storage."""
    console = Console()
    path_manager = PathManager()
    
    # Get Zotero storage path
    zotero_path = path_manager.get_zotero_path()
    storage_path = zotero_path / "storage"
    
    if not storage_path.exists():
        console.print(f"[red]Zotero storage not found: {storage_path}[/red]")
        return {}
    
    console.print(f"Scanning Zotero storage: {storage_path}")
    
    # Map storage folders to PDF files
    pdf_map = {}
    folder_count = 0
    
    for item_folder in storage_path.iterdir():
        if item_folder.is_dir() and len(item_folder.name) == 8:  # Zotero key format
            folder_count += 1
            # Find PDF in this folder
            for pdf_file in item_folder.glob("*.pdf"):
                pdf_map[item_folder.name] = pdf_file
                break  # Take first PDF found
    
    console.print(f"Scanned {folder_count} Zotero folders, found {len(pdf_map)} PDFs")
    return pdf_map


def import_pdfs_to_database():
    """Import PDFs from Zotero storage to organized literature database structure."""
    console = Console()
    session = next(get_session())
    path_manager = PathManager()
    pdf_extractor = PDFExtractor()
    
    try:
        # Get Zotero PDFs
        console.print("[cyan]Step 1: Scanning Zotero storage...[/cyan]")
        zotero_pdfs = get_zotero_storage_files()
        
        if not zotero_pdfs:
            console.print("[yellow]No PDFs found in Zotero storage[/yellow]")
            return
        
        # Get papers from database with Zotero keys
        console.print("[cyan]Step 2: Matching papers with PDFs...[/cyan]")
        papers = session.query(Paper).filter(Paper.zotero_key.isnot(None)).all()
        papers_by_key = {paper.zotero_key: paper for paper in papers}
        
        # Find matches
        matches = []
        for zotero_key, pdf_path in zotero_pdfs.items():
            if zotero_key in papers_by_key:
                paper = papers_by_key[zotero_key]
                matches.append((paper, pdf_path))
        
        console.print(f"Found {len(matches)} papers with PDFs to import")
        
        if not matches:
            console.print("[yellow]No matching papers found[/yellow]")
            return
        
        # Ask for confirmation
        if not Confirm.ask(f"Import {len(matches)} PDFs to organized storage?", default=True):
            console.print("Import cancelled")
            return
        
        # Import PDFs
        console.print("[cyan]Step 3: Importing and organizing PDFs...[/cyan]")
        
        imported_count = 0
        extracted_count = 0
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TimeRemainingColumn(),
            console=console
        ) as progress:
            
            task = progress.add_task("Importing PDFs...", total=len(matches))
            
            for paper, source_pdf_path in matches:
                try:
                    # Skip if paper already has a PDF
                    if paper.file_path and Path(paper.file_path).exists():
                        progress.advance(task)
                        continue
                    
                    # Create organized path
                    year = paper.year or 2024
                    pdf_storage = path_manager.get_pdf_storage_path()
                    
                    # Organize by year and paper ID
                    year_dir = pdf_storage / str(year)
                    year_dir.mkdir(exist_ok=True)
                    
                    # Create filename: paperID_sanitized_title.pdf
                    safe_title = "".join(c for c in (paper.title or "unknown")[:50] if c.isalnum() or c in (' ', '-', '_')).rstrip()
                    safe_title = safe_title.replace(' ', '_')
                    filename = f"{paper.id:04d}_{safe_title}.pdf"
                    
                    target_path = year_dir / filename
                    
                    # Copy PDF file
                    shutil.copy2(source_pdf_path, target_path)
                    
                    # Calculate hash
                    file_hash = calculate_file_hash(target_path)
                    
                    # Update database
                    paper.file_path = str(target_path)
                    paper.file_hash = file_hash
                    
                    # Extract full text if not already present
                    if not paper.full_text:
                        try:
                            extracted = pdf_extractor.extract(target_path)
                            if extracted.get('full_text'):
                                paper.full_text = extracted['full_text']
                                paper.word_count = len(extracted['full_text'].split())
                                extracted_count += 1
                        except Exception as e:
                            console.print(f"[yellow]Warning: Text extraction failed for {paper.title[:30]}: {e}[/yellow]")
                    
                    imported_count += 1
                    
                    if imported_count % 10 == 0:
                        session.commit()  # Commit periodically
                    
                except Exception as e:
                    console.print(f"[red]Error importing {source_pdf_path.name}: {e}[/red]")
                
                progress.advance(task)
        
        # Final commit
        session.commit()
        
        console.print(f"\n[green]✓ Import complete![/green]")
        console.print(f"  📁 PDFs imported: {imported_count}")
        console.print(f"  📄 Full text extracted: {extracted_count}")
        
        # Show storage info
        pdf_storage = path_manager.get_pdf_storage_path()
        total_size = sum(f.stat().st_size for f in pdf_storage.rglob("*.pdf")) / (1024 * 1024)
        console.print(f"  💾 Storage used: {total_size:.1f} MB")
        
    except Exception as e:
        session.rollback()
        console.print(f"[red]Import failed: {e}[/red]")
        raise
    finally:
        session.close()


def show_import_preview():
    """Show what would be imported without actually importing."""
    console = Console()
    session = next(get_session())
    
    try:
        # Get Zotero PDFs
        zotero_pdfs = get_zotero_storage_files()
        
        if not zotero_pdfs:
            console.print("[yellow]No PDFs found in Zotero storage[/yellow]")
            return
        
        # Get papers with Zotero keys
        papers = session.query(Paper).filter(Paper.zotero_key.isnot(None)).all()
        papers_by_key = {paper.zotero_key: paper for paper in papers}
        
        # Show preview
        console.print(f"\n[bold blue]Import Preview[/bold blue]")
        console.print(f"PDFs in Zotero storage: {len(zotero_pdfs)}")
        console.print(f"Papers in database: {len(papers)}")
        
        matches = 0
        already_have_pdfs = 0
        
        for zotero_key in zotero_pdfs:
            if zotero_key in papers_by_key:
                paper = papers_by_key[zotero_key]
                if paper.file_path and Path(paper.file_path).exists():
                    already_have_pdfs += 1
                else:
                    matches += 1
        
        console.print(f"Papers that would get PDFs: {matches}")
        console.print(f"Papers that already have PDFs: {already_have_pdfs}")
        
        if matches > 0:
            console.print(f"\n[green]Ready to import {matches} PDFs[/green]")
            console.print("Run with --import to proceed")
        
    finally:
        session.close()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Import Zotero PDFs to literature database")
    parser.add_argument('--preview', action='store_true', help='Show preview of what would be imported')
    parser.add_argument('--import', action='store_true', help='Actually import the PDFs')
    
    args = parser.parse_args()
    
    if args.preview:
        show_import_preview()
    elif getattr(args, 'import'):
        import_pdfs_to_database()
    else:
        parser.print_help()