#!/usr/bin/env python
"""Map Zotero attachments to papers and import PDFs."""
import sys
import shutil
import requests
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeRemainingColumn
from rich.prompt import Confirm
from rich.table import Table

# Add src to path for imports
sys.path.append(str(Path(__file__).parent.parent))

from src.database import get_session
from src.models import Paper
from src.utils.file_utils import calculate_file_hash
from src.utils.path_manager import PathManager
from src.extractors.pdf_extractor import PDFExtractor


class ZoteroPDFImporter:
    def __init__(self):
        self.console = Console()
        self.path_manager = PathManager()
        self.pdf_extractor = PDFExtractor()
    
    def get_attachment_to_parent_map(self) -> Dict[str, str]:
        """Map attachment keys to their parent paper keys."""
        self.console.print("Fetching attachment relationships from Zotero...")
        
        try:
            response = requests.get("http://localhost:23119/api/users/0/items?itemType=attachment", timeout=30)
            if response.status_code != 200:
                self.console.print(f"[red]Failed to fetch attachments: HTTP {response.status_code}[/red]")
                return {}
            
            attachments = response.json()
            attachment_map = {}
            
            for attachment in attachments:
                data = attachment.get('data', {})
                attachment_key = attachment.get('key')
                parent_item = data.get('parentItem')
                content_type = data.get('contentType', '')
                filename = data.get('filename', '')
                
                # Only process PDF attachments with parent items
                if (parent_item and attachment_key and 
                    ('pdf' in content_type.lower() or filename.lower().endswith('.pdf'))):
                    attachment_map[attachment_key] = parent_item
            
            self.console.print(f"Found {len(attachment_map)} PDF attachments with parent relationships")
            return attachment_map
            
        except Exception as e:
            self.console.print(f"[red]Error fetching attachments: {e}[/red]")
            return {}
    
    def get_storage_files(self) -> Dict[str, Path]:
        """Get all PDF files in Zotero storage, indexed by folder name (key)."""
        storage_path = self.path_manager.get_zotero_path() / "storage"
        
        if not storage_path.exists():
            self.console.print(f"[red]Zotero storage not found: {storage_path}[/red]")
            return {}
        
        pdf_files = {}
        for folder in storage_path.iterdir():
            if folder.is_dir() and len(folder.name) == 8:  # Zotero key length
                # Find PDF files in this folder
                for pdf_file in folder.glob("*.pdf"):
                    pdf_files[folder.name] = pdf_file
                    break  # Take first PDF
        
        self.console.print(f"Found {len(pdf_files)} PDF files in storage")
        return pdf_files
    
    def map_papers_to_pdfs(self) -> List[Tuple[Paper, Path]]:
        """Map database papers to their PDF files."""
        session = next(get_session())
        
        try:
            # Get mapping data
            attachment_to_parent = self.get_attachment_to_parent_map()
            storage_files = self.get_storage_files()
            
            if not attachment_to_parent or not storage_files:
                return []
            
            # Get papers from database
            papers = session.query(Paper).filter(Paper.zotero_key.isnot(None)).all()
            papers_by_key = {paper.zotero_key: paper for paper in papers}
            
            # Map papers to PDFs
            paper_pdf_pairs = []
            
            for attachment_key, parent_key in attachment_to_parent.items():
                # Check if we have this paper in our database
                if parent_key in papers_by_key:
                    paper = papers_by_key[parent_key]
                    
                    # Check if we have the PDF file for this attachment
                    if attachment_key in storage_files:
                        pdf_path = storage_files[attachment_key]
                        paper_pdf_pairs.append((paper, pdf_path))
            
            self.console.print(f"Mapped {len(paper_pdf_pairs)} papers to PDF files")
            return paper_pdf_pairs
            
        finally:
            session.close()
    
    def show_mapping_preview(self):
        """Show preview of what would be imported."""
        paper_pdf_pairs = self.map_papers_to_pdfs()
        
        if not paper_pdf_pairs:
            self.console.print("[yellow]No papers could be mapped to PDFs[/yellow]")
            return
        
        # Count existing vs new
        session = next(get_session())
        try:
            new_imports = []
            already_have = []
            
            for paper, pdf_path in paper_pdf_pairs:
                if paper.file_path and Path(paper.file_path).exists():
                    already_have.append((paper, pdf_path))
                else:
                    new_imports.append((paper, pdf_path))
            
            # Show summary
            table = Table(title="PDF Import Preview")
            table.add_column("Category", style="cyan")
            table.add_column("Count", style="green")
            
            table.add_row("Total mappable PDFs", str(len(paper_pdf_pairs)))
            table.add_row("New imports", str(len(new_imports)))
            table.add_row("Already imported", str(len(already_have)))
            
            self.console.print(table)
            
            if new_imports:
                self.console.print(f"\n[blue]Sample papers to import:[/blue]")
                for i, (paper, pdf_path) in enumerate(new_imports[:5]):
                    self.console.print(f"  {i+1}. {paper.title[:60]}...")
                    self.console.print(f"     PDF: {pdf_path.name}")
                    self.console.print(f"     Year: {paper.year}, Journal: {paper.journal}")
                    self.console.print()
                
                if len(new_imports) > 5:
                    self.console.print(f"     ... and {len(new_imports) - 5} more")
            
        finally:
            session.close()
    
    def import_pdfs(self, dry_run: bool = False):
        """Import PDFs into organized storage."""
        paper_pdf_pairs = self.map_papers_to_pdfs()
        
        if not paper_pdf_pairs:
            self.console.print("[yellow]No papers to import[/yellow]")
            return
        
        session = next(get_session())
        
        try:
            # Filter out papers that already have PDFs
            to_import = []
            for paper, pdf_path in paper_pdf_pairs:
                if not (paper.file_path and Path(paper.file_path).exists()):
                    to_import.append((paper, pdf_path))
            
            if not to_import:
                self.console.print("[yellow]All papers already have PDFs imported[/yellow]")
                return
            
            self.console.print(f"Ready to import {len(to_import)} PDFs")
            
            if dry_run:
                self.console.print("[yellow]Dry run - no files will be copied[/yellow]")
            elif not Confirm.ask("Proceed with import?", default=True):
                self.console.print("Import cancelled")
                return
            
            # Import PDFs
            imported = 0
            text_extracted = 0
            
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TimeRemainingColumn(),
                console=self.console
            ) as progress:
                
                task = progress.add_task("Importing PDFs...", total=len(to_import))
                
                for paper, source_path in to_import:
                    try:
                        if not dry_run:
                            # Create organized file path
                            target_path = self._create_organized_path(paper, source_path)
                            
                            # Copy file
                            shutil.copy2(source_path, target_path)
                            
                            # Update database
                            paper.file_path = str(target_path)
                            paper.file_hash = calculate_file_hash(target_path)
                            
                            # Extract text if needed
                            if not paper.full_text:
                                try:
                                    extracted = self.pdf_extractor.extract(target_path)
                                    if extracted.get('full_text'):
                                        paper.full_text = extracted['full_text']
                                        paper.word_count = len(extracted['full_text'].split())
                                        text_extracted += 1
                                except Exception:
                                    pass  # Text extraction is optional
                            
                            imported += 1
                        
                        else:
                            # Dry run - just log what would happen
                            self.console.print(f"Would import: {paper.title[:50]}... -> {source_path.name}")
                        
                        if imported % 20 == 0 and not dry_run:
                            session.commit()  # Periodic commits
                        
                    except Exception as e:
                        self.console.print(f"[red]Error importing {source_path.name}: {e}[/red]")
                    
                    progress.advance(task)
            
            if not dry_run:
                session.commit()
                
                self.console.print(f"\n[green]✓ Import successful![/green]")
                self.console.print(f"  📁 PDFs imported: {imported}")
                self.console.print(f"  📄 Full text extracted: {text_extracted}")
                
                # Update search index
                if imported > 0:
                    self.console.print("  🔍 Reindexing search...")
                    from src.services.search_service import SearchService
                    search_service = SearchService()
                    search_service.reindex_all_papers(session)
            
        except Exception as e:
            if not dry_run:
                session.rollback()
            self.console.print(f"[red]Import failed: {e}[/red]")
            raise
        finally:
            session.close()
    
    def _create_organized_path(self, paper: Paper, source_path: Path) -> Path:
        """Create organized file path for a paper."""
        pdf_storage = self.path_manager.get_pdf_storage_path()
        
        # Organize by year
        year = paper.year or 2024
        year_dir = pdf_storage / str(year)
        year_dir.mkdir(parents=True, exist_ok=True)
        
        # Create safe filename
        safe_title = "".join(c for c in (paper.title or "untitled")[:40] 
                           if c.isalnum() or c in (' ', '-', '_')).strip()
        safe_title = safe_title.replace(' ', '_')
        
        # Format: paperID_title.pdf
        filename = f"{paper.id:04d}_{safe_title}.pdf"
        
        return year_dir / filename


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Import Zotero PDFs using attachment mapping")
    parser.add_argument('--preview', action='store_true', help='Show import preview')
    parser.add_argument('--import', action='store_true', help='Import PDFs')
    parser.add_argument('--dry-run', action='store_true', help='Dry run (no actual importing)')
    
    args = parser.parse_args()
    
    importer = ZoteroPDFImporter()
    
    if args.preview:
        importer.show_mapping_preview()
    elif getattr(args, 'import'):
        importer.import_pdfs(dry_run=args.dry_run)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()