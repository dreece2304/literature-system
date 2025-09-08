#!/usr/bin/env python
"""Debug PDF linking issues."""
import sys
from pathlib import Path
from rich.console import Console

# Add src to path for imports
sys.path.append(str(Path(__file__).parent.parent))

from src.database import get_session
from src.models import Paper


def check_database_state():
    """Check current database state."""
    console = Console()
    session = next(get_session())
    
    try:
        # Check papers
        total_papers = session.query(Paper).count()
        papers_with_pdfs = session.query(Paper).filter(Paper.file_path.isnot(None)).count()
        
        console.print(f"[blue]Database State Check[/blue]")
        console.print(f"Total papers: {total_papers}")
        console.print(f"Papers with file_path: {papers_with_pdfs}")
        
        # Sample a few papers to see their state
        sample_papers = session.query(Paper).limit(5).all()
        
        console.print(f"\n[blue]Sample Papers:[/blue]")
        for i, paper in enumerate(sample_papers, 1):
            console.print(f"{i}. {paper.title[:50]}...")
            console.print(f"   Zotero key: {paper.zotero_key}")
            console.print(f"   File path: {paper.file_path}")
            console.print()
    
    finally:
        session.close()


def test_simple_update():
    """Test a simple database update to verify session handling."""
    console = Console()
    session = next(get_session())
    
    try:
        # Get first paper
        paper = session.query(Paper).first()
        
        if paper:
            console.print(f"Testing update on: {paper.title[:50]}...")
            console.print(f"Current file_path: {paper.file_path}")
            
            # Test update
            old_file_path = paper.file_path
            test_path = "/test/path/test.pdf"
            
            paper.file_path = test_path
            session.commit()
            
            # Verify update
            session.refresh(paper)
            console.print(f"After update: {paper.file_path}")
            
            if paper.file_path == test_path:
                console.print("[green]✓ Database update successful[/green]")
                
                # Restore original value
                paper.file_path = old_file_path
                session.commit()
                console.print(f"[green]✓ Restored original value: {paper.file_path}[/green]")
            else:
                console.print("[red]✗ Database update failed[/red]")
        
    except Exception as e:
        session.rollback()
        console.print(f"[red]Error during test: {e}[/red]")
    finally:
        session.close()


def attempt_manual_link():
    """Attempt to manually link one paper to test the process."""
    console = Console()
    session = next(get_session())
    
    try:
        # Find a paper with Zotero key but no file_path
        paper = session.query(Paper).filter(
            Paper.zotero_key.isnot(None),
            Paper.file_path.is_(None)
        ).first()
        
        if paper:
            console.print(f"Testing manual link for: {paper.title[:50]}...")
            console.print(f"Zotero key: {paper.zotero_key}")
            
            # Try to find corresponding PDF
            from src.utils.path_manager import PathManager
            path_manager = PathManager()
            storage_path = path_manager.get_zotero_path() / "storage"
            
            # Check if storage folder exists for this key
            # Note: This is a simplified approach - the actual key mapping is more complex
            test_folders = list(storage_path.glob("*"))[:5]  # Check first 5 folders
            
            for folder in test_folders:
                if folder.is_dir():
                    pdf_files = list(folder.glob("*.pdf"))
                    if pdf_files:
                        pdf_file = pdf_files[0]
                        console.print(f"Found test PDF: {pdf_file}")
                        
                        # Try to link it
                        paper.file_path = str(pdf_file)
                        session.commit()
                        
                        # Verify
                        session.refresh(paper)
                        if paper.file_path:
                            console.print(f"[green]✓ Successfully linked: {paper.file_path}[/green]")
                            return True
                        else:
                            console.print("[red]✗ Link failed to persist[/red]")
                        break
            
        else:
            console.print("[yellow]No suitable paper found for testing[/yellow]")
    
    except Exception as e:
        session.rollback()
        console.print(f"[red]Error during manual link: {e}[/red]")
    finally:
        session.close()
    
    return False


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Debug PDF linking")
    parser.add_argument('--check', action='store_true', help='Check database state')
    parser.add_argument('--test-update', action='store_true', help='Test database updates')
    parser.add_argument('--manual-link', action='store_true', help='Test manual linking')
    
    args = parser.parse_args()
    
    if args.check:
        check_database_state()
    elif args.test_update:
        test_simple_update()
    elif args.manual_link:
        attempt_manual_link()
    else:
        parser.print_help()