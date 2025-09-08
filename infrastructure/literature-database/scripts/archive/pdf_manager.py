#!/usr/bin/env python
"""PDF management system for literature database."""
import sys
from pathlib import Path
from typing import List, Dict, Tuple, Optional
import shutil
import hashlib
import requests
from rich.console import Console
from rich.progress import Progress, TaskID, SpinnerColumn, TextColumn, BarColumn, TimeRemainingColumn
from rich.prompt import Prompt, Confirm
from rich.table import Table
from rich.panel import Panel

# Add src to path for imports
sys.path.append(str(Path(__file__).parent.parent))

from src.database import get_session
from src.models import Paper
from src.utils.file_utils import calculate_file_hash
from src.utils.path_manager import PathManager
from src.extractors.pdf_extractor import PDFExtractor


class PDFManager:
    """Manage PDF files for the literature database."""
    
    def __init__(self):
        self.console = Console()
        self.path_manager = PathManager()
        self.pdf_extractor = PDFExtractor()
        
    def analyze_pdf_status(self) -> Dict:
        """Analyze current PDF status across all papers."""
        session = next(get_session())
        
        try:
            papers = session.query(Paper).all()
            
            stats = {
                'total_papers': len(papers),
                'with_pdfs': 0,
                'missing_pdfs': 0,
                'broken_links': 0,
                'zotero_attachments': 0,
                'local_pdfs': 0
            }
            
            papers_by_status = {
                'has_pdf': [],
                'missing_pdf': [],
                'broken_link': [],
                'zotero_only': []
            }
            
            for paper in papers:
                if paper.file_path and Path(paper.file_path).exists():
                    stats['with_pdfs'] += 1
                    stats['local_pdfs'] += 1
                    papers_by_status['has_pdf'].append(paper)
                elif paper.file_path:
                    stats['broken_links'] += 1
                    papers_by_status['broken_link'].append(paper)
                else:
                    stats['missing_pdfs'] += 1
                    # Check if it might have a Zotero attachment
                    if paper.zotero_key:
                        stats['zotero_attachments'] += 1
                        papers_by_status['zotero_only'].append(paper)
                    else:
                        papers_by_status['missing_pdf'].append(paper)
            
            return {
                'stats': stats,
                'papers_by_status': papers_by_status
            }
            
        finally:
            session.close()
    
    def find_zotero_pdfs(self) -> Dict[str, Path]:
        """Find PDFs in Zotero storage directory."""
        zotero_storage = self.path_manager.get_zotero_storage_path()
        
        if not zotero_storage or not zotero_storage.exists():
            self.console.print("[yellow]Warning: Zotero storage path not found[/yellow]")
            return {}
        
        pdf_map = {}
        
        # Scan Zotero storage for PDFs
        for item_dir in zotero_storage.iterdir():
            if item_dir.is_dir() and len(item_dir.name) == 8:  # Zotero key format
                for pdf_file in item_dir.glob("*.pdf"):
                    pdf_map[item_dir.name] = pdf_file
                    break  # Take first PDF in each directory
        
        return pdf_map
    
    def link_zotero_pdfs(self) -> Tuple[int, int]:
        """Link existing Zotero PDFs to papers in database."""
        session = next(get_session())
        
        try:
            # Find Zotero PDFs
            zotero_pdfs = self.find_zotero_pdfs()
            
            if not zotero_pdfs:
                self.console.print("[yellow]No Zotero PDFs found[/yellow]")
                return 0, 0
            
            linked_count = 0
            copied_count = 0
            
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TimeRemainingColumn(),
                console=self.console
            ) as progress:
                
                task = progress.add_task("Linking Zotero PDFs...", total=len(zotero_pdfs))
                
                for zotero_key, pdf_path in zotero_pdfs.items():
                    # Find paper with this Zotero key
                    paper = session.query(Paper).filter_by(zotero_key=zotero_key).first()
                    
                    if paper and not paper.file_path:
                        # Copy PDF to organized location
                        year = paper.year or 2024
                        organized_path = self.path_manager.get_paper_pdf_path(
                            paper.id, 
                            pdf_path.name,
                            year=year
                        )
                        
                        # Ensure directory exists
                        organized_path.parent.mkdir(parents=True, exist_ok=True)
                        
                        # Copy file
                        shutil.copy2(pdf_path, organized_path)
                        
                        # Calculate hash and update database
                        file_hash = calculate_file_hash(organized_path)
                        paper.file_path = str(organized_path)
                        paper.file_hash = file_hash
                        
                        # Extract text if needed
                        if not paper.full_text:
                            try:
                                extracted = self.pdf_extractor.extract(organized_path)
                                if extracted.get('full_text'):
                                    paper.full_text = extracted['full_text']
                                    paper.word_count = len(extracted['full_text'].split())
                            except Exception as e:
                                self.console.print(f"[yellow]Warning: Could not extract text from {pdf_path.name}: {e}[/yellow]")
                        
                        linked_count += 1
                        copied_count += 1
                    
                    progress.advance(task)
            
            session.commit()
            
            return linked_count, copied_count
            
        finally:
            session.close()
    
    def download_missing_pdfs(self, max_downloads: int = 10) -> int:
        """Attempt to download missing PDFs using DOI/arXiv links."""
        session = next(get_session())
        
        try:
            # Find papers without PDFs but with DOIs
            papers_without_pdfs = session.query(Paper).filter(
                Paper.file_path.is_(None),
                Paper.doi.isnot(None)
            ).limit(max_downloads).all()
            
            if not papers_without_pdfs:
                self.console.print("[yellow]No papers with DOIs missing PDFs[/yellow]")
                return 0
            
            downloaded = 0
            
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                console=self.console
            ) as progress:
                
                task = progress.add_task("Downloading PDFs...", total=len(papers_without_pdfs))
                
                for paper in papers_without_pdfs:
                    success = self._try_download_pdf(paper)
                    if success:
                        downloaded += 1
                    progress.advance(task)
            
            session.commit()
            return downloaded
            
        finally:
            session.close()
    
    def _try_download_pdf(self, paper: Paper) -> bool:
        """Attempt to download PDF for a single paper."""
        # This is a placeholder - implementing PDF download requires
        # careful consideration of publisher policies and access rights
        
        # Common sources to try:
        # 1. arXiv (if arXiv ID available)
        # 2. PubMed Central (for life sciences)
        # 3. Publisher open access versions
        # 4. Institutional repositories
        
        self.console.print(f"[blue]Attempting download for: {paper.title[:50]}...[/blue]")
        
        # For now, just log the attempt
        # In production, implement actual download logic here
        
        return False
    
    def organize_existing_pdfs(self, source_dir: Path) -> Tuple[int, int]:
        """Organize PDFs from an existing directory."""
        if not source_dir.exists():
            raise ValueError(f"Source directory does not exist: {source_dir}")
        
        pdf_files = list(source_dir.rglob("*.pdf"))
        
        if not pdf_files:
            self.console.print(f"[yellow]No PDF files found in {source_dir}[/yellow]")
            return 0, 0
        
        session = next(get_session())
        matched = 0
        organized = 0
        
        try:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TimeRemainingColumn(),
                console=self.console
            ) as progress:
                
                task = progress.add_task("Organizing PDFs...", total=len(pdf_files))
                
                for pdf_file in pdf_files:
                    # Try to match with papers in database
                    paper = self._match_pdf_to_paper(session, pdf_file)
                    
                    if paper:
                        # Organize the PDF
                        year = paper.year or 2024
                        organized_path = self.path_manager.get_paper_pdf_path(
                            paper.id,
                            pdf_file.name,
                            year=year
                        )
                        
                        # Ensure directory exists
                        organized_path.parent.mkdir(parents=True, exist_ok=True)
                        
                        # Copy file
                        shutil.copy2(pdf_file, organized_path)
                        
                        # Update database
                        paper.file_path = str(organized_path)
                        paper.file_hash = calculate_file_hash(organized_path)
                        
                        matched += 1
                        organized += 1
                    
                    progress.advance(task)
            
            session.commit()
            
            return matched, organized
            
        finally:
            session.close()
    
    def _match_pdf_to_paper(self, session, pdf_file: Path) -> Optional[Paper]:
        """Try to match a PDF file to a paper in the database."""
        # Try multiple matching strategies:
        
        # 1. Filename contains DOI
        filename = pdf_file.stem.lower()
        
        # Look for DOI patterns in filename
        import re
        doi_pattern = r'10\.\d+/[^\s]+'
        doi_match = re.search(doi_pattern, filename)
        
        if doi_match:
            doi = doi_match.group(0)
            paper = session.query(Paper).filter_by(doi=doi).first()
            if paper:
                return paper
        
        # 2. Try to extract text and match title
        try:
            extracted = self.pdf_extractor.extract(pdf_file)
            if extracted.get('title'):
                # Fuzzy match with paper titles
                import difflib
                papers = session.query(Paper).all()
                
                best_match = None
                best_ratio = 0.8  # Minimum similarity threshold
                
                for paper in papers:
                    if paper.title:
                        ratio = difflib.SequenceMatcher(
                            None, 
                            extracted['title'].lower(),
                            paper.title.lower()
                        ).ratio()
                        
                        if ratio > best_ratio:
                            best_ratio = ratio
                            best_match = paper
                
                return best_match
                
        except Exception:
            pass  # PDF extraction failed
        
        return None
    
    def show_status_report(self):
        """Show comprehensive PDF status report."""
        analysis = self.analyze_pdf_status()
        stats = analysis['stats']
        
        # Main statistics table
        table = Table(title="PDF Status Report")
        table.add_column("Metric", style="cyan")
        table.add_column("Count", style="green")
        table.add_column("Percentage", style="yellow")
        
        total = stats['total_papers']
        
        table.add_row("Total Papers", str(total), "100%")
        table.add_row("With PDFs", str(stats['with_pdfs']), f"{stats['with_pdfs']/total*100:.1f}%")
        table.add_row("Missing PDFs", str(stats['missing_pdfs']), f"{stats['missing_pdfs']/total*100:.1f}%")
        table.add_row("Broken Links", str(stats['broken_links']), f"{stats['broken_links']/total*100:.1f}%")
        table.add_row("Zotero Attachments", str(stats['zotero_attachments']), f"{stats['zotero_attachments']/total*100:.1f}%")
        
        self.console.print(table)
        
        # Recommendations
        recommendations = []
        
        if stats['zotero_attachments'] > 0:
            recommendations.append("🔗 Link Zotero PDFs to import existing files")
        
        if stats['missing_pdfs'] > 10:
            recommendations.append("📥 Try downloading missing PDFs from open access sources")
        
        if stats['broken_links'] > 0:
            recommendations.append("🔧 Fix broken PDF links")
        
        if recommendations:
            panel = Panel(
                "\n".join(recommendations),
                title="Recommendations",
                border_style="green"
            )
            self.console.print(panel)


def main():
    """Main CLI interface for PDF manager."""
    import argparse
    
    parser = argparse.ArgumentParser(description="PDF Manager for Literature Database")
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Status command
    status_parser = subparsers.add_parser('status', help='Show PDF status report')
    
    # Link command
    link_parser = subparsers.add_parser('link', help='Link Zotero PDFs')
    
    # Download command
    download_parser = subparsers.add_parser('download', help='Download missing PDFs')
    download_parser.add_argument('--max', type=int, default=10, help='Maximum downloads')
    
    # Organize command
    organize_parser = subparsers.add_parser('organize', help='Organize PDFs from directory')
    organize_parser.add_argument('source_dir', type=Path, help='Source directory with PDFs')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    pdf_manager = PDFManager()
    
    if args.command == 'status':
        pdf_manager.show_status_report()
    
    elif args.command == 'link':
        linked, copied = pdf_manager.link_zotero_pdfs()
        pdf_manager.console.print(f"[green]✓ Linked {linked} PDFs, copied {copied} files[/green]")
    
    elif args.command == 'download':
        downloaded = pdf_manager.download_missing_pdfs(args.max)
        pdf_manager.console.print(f"[green]✓ Downloaded {downloaded} PDFs[/green]")
    
    elif args.command == 'organize':
        matched, organized = pdf_manager.organize_existing_pdfs(args.source_dir)
        pdf_manager.console.print(f"[green]✓ Matched {matched} PDFs, organized {organized} files[/green]")


if __name__ == "__main__":
    main()