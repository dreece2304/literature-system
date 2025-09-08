#!/usr/bin/env python
"""Link papers to their PDFs in Zotero storage without copying files."""
import sys
import requests
from pathlib import Path
from typing import Dict, List, Tuple
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.prompt import Confirm
from rich.table import Table

# Add src to path for imports
sys.path.append(str(Path(__file__).parent.parent))

from src.database import get_session
from src.models import Paper
from src.utils.path_manager import PathManager
from src.extractors.pdf_extractor import PDFExtractor


class ZoteroReferenceLinking:
    """Link papers to their PDFs in Zotero storage without copying files."""
    
    def __init__(self):
        self.console = Console()
        self.path_manager = PathManager()
        self.pdf_extractor = PDFExtractor()
    
    def get_pdf_mappings(self) -> List[Tuple[Paper, Path]]:
        """Map papers to their PDF files in Zotero storage."""
        session = next(get_session())
        
        try:
            # Get attachment relationships from Zotero API
            self.console.print("Fetching PDF attachments from Zotero...")
            
            response = requests.get("http://localhost:23119/api/users/0/items?itemType=attachment", timeout=30)
            if response.status_code != 200:
                self.console.print(f"[red]Failed to fetch attachments[/red]")
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
            
            self.console.print(f"Found {len(attachment_to_parent)} PDF attachments")
            
            # Get Zotero storage files
            storage_path = self.path_manager.get_zotero_path() / "storage"
            if not storage_path.exists():
                self.console.print(f"[red]Zotero storage not found: {storage_path}[/red]")
                return []
            
            storage_files = {}
            for folder in storage_path.iterdir():
                if folder.is_dir() and len(folder.name) == 8:
                    for pdf_file in folder.glob("*.pdf"):
                        storage_files[folder.name] = pdf_file
                        break
            
            self.console.print(f"Found {len(storage_files)} PDF files in storage")
            
            # Get papers from database
            papers = session.query(Paper).filter(Paper.zotero_key.isnot(None)).all()
            papers_by_key = {paper.zotero_key: paper for paper in papers}
            
            # Map papers to PDFs
            mappings = []
            for attachment_key, parent_key in attachment_to_parent.items():
                if parent_key in papers_by_key and attachment_key in storage_files:
                    paper = papers_by_key[parent_key]
                    pdf_path = storage_files[attachment_key]
                    mappings.append((paper, pdf_path))
            
            self.console.print(f"Successfully mapped {len(mappings)} papers to PDFs")
            return mappings
            
        except Exception as e:
            self.console.print(f"[red]Error mapping PDFs: {e}[/red]")
            return []
        finally:
            session.close()
    
    def show_link_preview(self):
        """Show preview of what would be linked."""
        mappings = self.get_pdf_mappings()
        
        if not mappings:
            self.console.print("[yellow]No papers could be mapped to PDFs[/yellow]")
            return
        
        session = next(get_session())
        try:
            # Count status
            to_link = []
            already_linked = []
            
            for paper, pdf_path in mappings:
                if paper.file_path:
                    already_linked.append((paper, pdf_path))
                else:
                    to_link.append((paper, pdf_path))
            
            # Show summary table
            table = Table(title="PDF Link Preview")
            table.add_column("Status", style="cyan")
            table.add_column("Count", style="green")
            table.add_column("Details", style="yellow")
            
            table.add_row("Total mappable", str(len(mappings)), "Papers with PDFs in Zotero")
            table.add_row("Ready to link", str(len(to_link)), "New PDF references")
            table.add_row("Already linked", str(len(already_linked)), "Previously linked")
            
            self.console.print(table)
            
            if to_link:
                self.console.print(f"\n[blue]Sample papers to link:[/blue]")
                for i, (paper, pdf_path) in enumerate(to_link[:5]):
                    # Check if PDF file actually exists
                    exists = "✓" if pdf_path.exists() else "✗"
                    size_mb = pdf_path.stat().st_size / (1024*1024) if pdf_path.exists() else 0
                    
                    self.console.print(f"  {i+1}. {paper.title[:55]}...")
                    self.console.print(f"     PDF: {pdf_path.name} ({exists} {size_mb:.1f}MB)")
                    self.console.print(f"     Path: {pdf_path}")
                    self.console.print()
                
                if len(to_link) > 5:
                    self.console.print(f"     ... and {len(to_link) - 5} more papers")
                
                # Calculate total size
                total_size = sum(p.stat().st_size for _, p in to_link if p.exists()) / (1024*1024)
                self.console.print(f"\n[green]Total PDF size: {total_size:.1f} MB[/green]")
                self.console.print("[green]No storage duplication - files stay in Zotero[/green]")
        
        finally:
            session.close()
    
    def link_pdfs(self, extract_text: bool = True):
        """Link papers to their PDFs in Zotero storage."""
        mappings = self.get_pdf_mappings()
        
        if not mappings:
            self.console.print("[yellow]No papers to link[/yellow]")
            return
        
        session = next(get_session())
        
        try:
            # Filter to papers that don't have file_path set
            to_link = [(paper, pdf_path) for paper, pdf_path in mappings if not paper.file_path]
            
            if not to_link:
                self.console.print("[yellow]All papers are already linked to PDFs[/yellow]")
                return
            
            self.console.print(f"Ready to link {len(to_link)} papers to their PDFs")
            
            # Auto-proceed in non-interactive mode
            self.console.print("Proceeding with linking...")
            
            linked_count = 0
            text_extracted = 0
            
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                console=self.console
            ) as progress:
                
                task = progress.add_task("Linking PDFs...", total=len(to_link))
                
                for paper, pdf_path in to_link:
                    try:
                        if not pdf_path.exists():
                            self.console.print(f"[yellow]PDF file not found: {pdf_path}[/yellow]")
                            progress.advance(task)
                            continue
                        
                        # Link to PDF in Zotero storage (no copying)
                        paper.file_path = str(pdf_path)
                        
                        # Calculate file hash for integrity checking
                        try:
                            from src.utils.file_utils import calculate_file_hash
                            paper.file_hash = calculate_file_hash(pdf_path)
                        except Exception:
                            pass  # Hash calculation is optional
                        
                        # Extract full text if requested and not already present
                        if extract_text and not paper.full_text:
                            try:
                                extracted = self.pdf_extractor.extract(pdf_path)
                                if extracted.get('full_text'):
                                    paper.full_text = extracted['full_text']
                                    paper.word_count = len(extracted['full_text'].split())
                                    text_extracted += 1
                            except Exception as e:
                                self.console.print(f"[yellow]Text extraction failed for {paper.title[:30]}: {e}[/yellow]")
                        
                        linked_count += 1
                        
                        if linked_count % 20 == 0:
                            session.commit()  # Periodic commits
                        
                    except Exception as e:
                        self.console.print(f"[red]Error linking {pdf_path.name}: {e}[/red]")
                    
                    progress.advance(task)
            
            session.commit()
            
            self.console.print(f"\n[green]✓ Linking successful![/green]")
            self.console.print(f"  🔗 Papers linked to PDFs: {linked_count}")
            self.console.print(f"  📄 Full text extracted: {text_extracted}")
            self.console.print(f"  💾 No additional storage used (PDFs stay in Zotero)")
            
            # Update search index if text was extracted
            if text_extracted > 0:
                self.console.print("  🔍 Updating search index...")
                try:
                    from src.services.search_service import SearchService
                    search_service = SearchService()
                    search_service.reindex_all_papers(session)
                    self.console.print("  ✓ Search index updated")
                except Exception as e:
                    self.console.print(f"  [yellow]Search index update failed: {e}[/yellow]")
        
        except Exception as e:
            session.rollback()
            self.console.print(f"[red]Linking failed: {e}[/red]")
            raise
        finally:
            session.close()
    
    def verify_links(self):
        """Verify that all linked PDFs still exist and are accessible."""
        session = next(get_session())
        
        try:
            papers_with_pdfs = session.query(Paper).filter(Paper.file_path.isnot(None)).all()
            
            if not papers_with_pdfs:
                self.console.print("[yellow]No papers are linked to PDFs[/yellow]")
                return
            
            self.console.print(f"Verifying {len(papers_with_pdfs)} PDF links...")
            
            valid_links = 0
            broken_links = 0
            
            for paper in papers_with_pdfs:
                pdf_path = Path(paper.file_path)
                if pdf_path.exists():
                    valid_links += 1
                else:
                    broken_links += 1
                    self.console.print(f"[red]Broken link: {paper.title[:50]}...[/red]")
                    self.console.print(f"  Missing: {paper.file_path}")
            
            # Show results
            table = Table(title="PDF Link Verification")
            table.add_column("Status", style="cyan")
            table.add_column("Count", style="green")
            
            table.add_row("Valid links", str(valid_links))
            table.add_row("Broken links", str(broken_links))
            table.add_row("Success rate", f"{valid_links/(valid_links+broken_links)*100:.1f}%")
            
            self.console.print(table)
            
        finally:
            session.close()


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Link papers to PDFs in Zotero storage")
    parser.add_argument('--preview', action='store_true', help='Show link preview')
    parser.add_argument('--link', action='store_true', help='Link papers to PDFs')
    parser.add_argument('--no-text', action='store_true', help='Skip text extraction')
    parser.add_argument('--verify', action='store_true', help='Verify existing links')
    
    args = parser.parse_args()
    
    linker = ZoteroReferenceLinking()
    
    if args.preview:
        linker.show_link_preview()
    elif args.link:
        linker.link_pdfs(extract_text=not args.no_text)
    elif args.verify:
        linker.verify_links()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()