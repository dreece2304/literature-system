#!/usr/bin/env python
"""Migrate existing PDF collection to literature database."""
import sys
from pathlib import Path
from typing import List, Dict, Tuple
import shutil
from rich.console import Console
from rich.progress import Progress, TaskID, SpinnerColumn, TextColumn, BarColumn, TimeRemainingColumn
from rich.prompt import Prompt, Confirm
from rich.table import Table
import click

# Add src to path for imports
sys.path.append(str(Path(__file__).parent.parent))

from src.database import get_session
from src.services.paper_service import PaperService
from src.utils.file_utils import calculate_file_hash, find_duplicate_files
from src.utils.path_manager import PathManager
from src.utils.logging import setup_logging, get_logger

console = Console()
logger = get_logger(__name__)


class PDFMigrator:
    """Handle migration of existing PDF collections."""
    
    def __init__(self):
        self.paper_service = PaperService()
        self.path_manager = PathManager()
        self.session = next(get_session())
        
        # Statistics
        self.stats = {
            'found': 0,
            'processed': 0,
            'added': 0,
            'duplicates': 0,
            'errors': 0,
            'skipped': 0
        }
    
    def scan_directory(self, source_dir: Path) -> List[Path]:
        """Scan directory for PDF files."""
        console.print(f"\n[blue]Scanning directory:[/blue] {source_dir}")
        
        pdf_files = []
        try:
            for file_path in source_dir.rglob('*.pdf'):
                if file_path.is_file():
                    pdf_files.append(file_path)
            
            self.stats['found'] = len(pdf_files)
            console.print(f"[green]Found {len(pdf_files)} PDF files[/green]")
            
        except Exception as e:
            console.print(f"[red]Error scanning directory: {e}[/red]")
            
        return pdf_files
    
    def check_for_duplicates(self, pdf_files: List[Path]) -> Dict[str, List[Path]]:
        """Check for duplicate files by hash."""
        console.print("\n[blue]Checking for duplicates...[/blue]")
        
        duplicates = {}
        file_hashes = {}
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            console=console,
        ) as progress:
            task = progress.add_task("Calculating hashes...", total=len(pdf_files))
            
            for file_path in pdf_files:
                try:
                    file_hash = calculate_file_hash(file_path)
                    
                    if file_hash in file_hashes:
                        if file_hash not in duplicates:
                            duplicates[file_hash] = [file_hashes[file_hash]]
                        duplicates[file_hash].append(file_path)
                    else:
                        file_hashes[file_hash] = file_path
                    
                    progress.advance(task)
                    
                except Exception as e:
                    logger.error(f"Failed to hash {file_path}: {e}")
                    progress.advance(task)
        
        if duplicates:
            console.print(f"[yellow]Found {len(duplicates)} groups of duplicate files[/yellow]")
            self.show_duplicates(duplicates)
        else:
            console.print("[green]No duplicates found[/green]")
        
        return duplicates
    
    def show_duplicates(self, duplicates: Dict[str, List[Path]]):
        """Show duplicate files to user."""
        for i, (hash_val, files) in enumerate(duplicates.items(), 1):
            console.print(f"\n[yellow]Duplicate group {i}:[/yellow]")
            for j, file_path in enumerate(files):
                size_mb = file_path.stat().st_size / (1024 * 1024)
                console.print(f"  {j+1}. {file_path} ({size_mb:.1f} MB)")
    
    def migrate_files(
        self, 
        pdf_files: List[Path], 
        copy_files: bool = True,
        organize_by_year: bool = True,
        skip_duplicates: bool = True
    ) -> None:
        """Migrate PDF files to the database."""
        console.print(f"\n[blue]Starting migration of {len(pdf_files)} files...[/blue]")
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeRemainingColumn(),
            console=console,
        ) as progress:
            
            task = progress.add_task("Migrating files...", total=len(pdf_files))
            
            for file_path in pdf_files:
                self.stats['processed'] += 1
                progress.update(task, description=f"Processing: {file_path.name}")
                
                try:
                    # Check if file already exists in database
                    if skip_duplicates:
                        file_hash = calculate_file_hash(file_path)
                        existing = self.session.query(self.paper_service.Paper).filter_by(
                            file_hash=file_hash
                        ).first()
                        
                        if existing:
                            self.stats['duplicates'] += 1
                            logger.info(f"Skipping duplicate: {file_path}")
                            progress.advance(task)
                            continue
                    
                    # Determine destination path
                    if copy_files:
                        # Extract metadata to get year for organization
                        try:
                            extracted_data = self.paper_service.pdf_extractor.extract(file_path)
                            metadata = self.paper_service.metadata_extractor.extract_from_text(
                                extracted_data['full_text'], file_path.name
                            )
                            year = metadata.get('year')
                        except:
                            year = None
                        
                        dest_path = self.path_manager.generate_pdf_path(file_path.name, year)
                        dest_path.parent.mkdir(parents=True, exist_ok=True)
                        
                        # Copy file to new location
                        shutil.copy2(file_path, dest_path)
                        target_path = dest_path
                    else:
                        # Use original path
                        target_path = file_path
                    
                    # Add to database
                    paper = self.paper_service.add_paper_from_file(self.session, target_path)
                    self.stats['added'] += 1
                    
                    logger.info(f"Added paper: {paper.title}")
                    
                except Exception as e:
                    self.stats['errors'] += 1
                    logger.error(f"Failed to process {file_path}: {e}")
                
                progress.advance(task)
        
        self.session.commit()
        console.print("\n[green]Migration completed![/green]")
        self.show_migration_stats()
    
    def show_migration_stats(self):
        """Show migration statistics."""
        table = Table(title="Migration Statistics")
        table.add_column("Metric", style="cyan")
        table.add_column("Count", style="green")
        
        table.add_row("Files Found", str(self.stats['found']))
        table.add_row("Files Processed", str(self.stats['processed']))
        table.add_row("Papers Added", str(self.stats['added']))
        table.add_row("Duplicates Skipped", str(self.stats['duplicates']))
        table.add_row("Errors", str(self.stats['errors']))
        
        console.print(table)
    
    def cleanup(self):
        """Cleanup resources."""
        self.session.close()


@click.command()
@click.argument('source_directory', type=click.Path(exists=True, path_type=Path))
@click.option('--copy/--no-copy', default=True, help='Copy files to organized structure')
@click.option('--organize/--no-organize', default=True, help='Organize files by year')
@click.option('--skip-duplicates/--include-duplicates', default=True, help='Skip duplicate files')
@click.option('--dry-run', is_flag=True, help='Show what would be done without making changes')
def migrate(source_directory, copy, organize, skip_duplicates, dry_run):
    """
    Migrate existing PDF collection to literature database.
    
    SOURCE_DIRECTORY: Path to your existing PDF collection
    
    Examples:
        python scripts/migrate_pdfs.py /path/to/pdfs --copy --organize
        python scripts/migrate_pdfs.py C:/Users/dreec/Documents/Papers --dry-run
    """
    setup_logging()
    
    console.print("[bold green]Literature Database PDF Migration[/bold green]")
    console.print("=" * 50)
    
    # Validate source directory
    if not source_directory.exists():
        console.print(f"[red]Source directory does not exist: {source_directory}[/red]")
        sys.exit(1)
    
    if not source_directory.is_dir():
        console.print(f"[red]Source path is not a directory: {source_directory}[/red]")
        sys.exit(1)
    
    # Initialize migrator
    migrator = PDFMigrator()
    
    try:
        # Scan for PDF files
        pdf_files = migrator.scan_directory(source_directory)
        
        if not pdf_files:
            console.print("[yellow]No PDF files found in directory[/yellow]")
            return
        
        # Check for duplicates
        duplicates = migrator.check_for_duplicates(pdf_files)
        
        # Show migration plan
        console.print(f"\n[bold blue]Migration Plan:[/bold blue]")
        console.print(f"Source: {source_directory}")
        console.print(f"Target: {migrator.path_manager.get_pdf_storage_path()}")
        console.print(f"Copy files: {'Yes' if copy else 'No'}")
        console.print(f"Organize by year: {'Yes' if organize else 'No'}")
        console.print(f"Skip duplicates: {'Yes' if skip_duplicates else 'No'}")
        console.print(f"Files to process: {len(pdf_files)}")
        
        if dry_run:
            console.print("\n[yellow]DRY RUN - No changes will be made[/yellow]")
            return
        
        # Confirm before proceeding
        if not Confirm.ask("\nProceed with migration?"):
            console.print("Migration cancelled.")
            return
        
        # Perform migration
        migrator.migrate_files(
            pdf_files, 
            copy_files=copy, 
            organize_by_year=organize,
            skip_duplicates=skip_duplicates
        )
        
    except KeyboardInterrupt:
        console.print("\n[yellow]Migration cancelled by user[/yellow]")
    except Exception as e:
        console.print(f"[red]Migration failed: {e}[/red]")
        logger.error(f"Migration error: {e}")
        sys.exit(1)
    finally:
        migrator.cleanup()


if __name__ == '__main__':
    migrate()