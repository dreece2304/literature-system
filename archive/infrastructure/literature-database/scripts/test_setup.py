#!/usr/bin/env python
"""Test the literature database setup."""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from src.database import get_session, get_engine
from src.models import Paper, Author, Tag, Collection
from sqlalchemy import inspect
from rich.console import Console
from rich.table import Table

console = Console()

def test_database():
    """Test database connectivity and structure."""
    console.print("\n[bold blue]Testing Database Setup[/bold blue]\n")
    
    try:
        # Get engine and inspector
        engine = get_engine()
        inspector = inspect(engine)
        
        # Get all tables
        tables = inspector.get_table_names()
        
        # Create a nice table display
        table = Table(title="Database Tables")
        table.add_column("Table Name", style="cyan")
        table.add_column("Columns", style="green")
        
        for table_name in sorted(tables):
            columns = inspector.get_columns(table_name)
            col_names = [col['name'] for col in columns]
            table.add_row(table_name, ", ".join(col_names[:3]) + f"... ({len(col_names)} total)")
        
        console.print(table)
        
        # Test session
        session = next(get_session())
        
        # Try a simple query
        paper_count = session.query(Paper).count()
        author_count = session.query(Author).count()
        
        console.print(f"\n[green]✓[/green] Database connection successful!")
        console.print(f"[green]✓[/green] {len(tables)} tables created")
        console.print(f"[green]✓[/green] Papers in database: {paper_count}")
        console.print(f"[green]✓[/green] Authors in database: {author_count}")
        
        session.close()
        return True
        
    except Exception as e:
        console.print(f"[red]✗ Database test failed: {e}[/red]")
        return False

def test_paths():
    """Test that all required paths exist."""
    console.print("\n[bold blue]Testing Directory Structure[/bold blue]\n")
    
    required_paths = [
        'data/pdfs',
        'data/metadata',
        'data/cache',
        'data/zotero_sync',
        'scripts',
        'notebooks',
        'config',
        'src',
        'logs',
        'temp'
    ]
    
    all_exist = True
    for path in required_paths:
        p = Path(path)
        if p.exists():
            console.print(f"[green]✓[/green] {path}")
        else:
            console.print(f"[red]✗[/red] {path} - NOT FOUND")
            all_exist = False
    
    return all_exist

def test_config():
    """Test configuration files."""
    console.print("\n[bold blue]Testing Configuration[/bold blue]\n")
    
    config_files = [
        'config/settings.yml',
        'config/credentials.yml',
        '.env',
        'requirements.txt'
    ]
    
    all_exist = True
    for file in config_files:
        p = Path(file)
        if p.exists():
            console.print(f"[green]✓[/green] {file}")
        else:
            console.print(f"[red]✗[/red] {file} - NOT FOUND")
            all_exist = False
    
    # Check Zotero path in config
    import yaml
    with open('config/settings.yml', 'r') as f:
        config = yaml.safe_load(f)
    
    zotero_path = config['zotero']['windows_path']
    console.print(f"\nZotero path configured: [cyan]{zotero_path}[/cyan]")
    
    # Check if Zotero path exists (if running in WSL)
    zotero_p = Path(zotero_path)
    if zotero_p.exists():
        console.print(f"[green]✓[/green] Zotero directory found!")
    else:
        console.print(f"[yellow]⚠[/yellow] Zotero directory not found at {zotero_path}")
        console.print("  Make sure Zotero is installed on Windows and the path is correct")
    
    return all_exist

if __name__ == "__main__":
    console.print("[bold cyan]Literature Database Setup Test[/bold cyan]")
    console.print("=" * 50)
    
    paths_ok = test_paths()
    config_ok = test_config()
    db_ok = test_database()
    
    console.print("\n" + "=" * 50)
    if paths_ok and config_ok and db_ok:
        console.print("[bold green]✓ All tests passed! Setup is complete.[/bold green]")
    else:
        console.print("[bold yellow]⚠ Some tests failed. Check the output above.[/bold yellow]")
