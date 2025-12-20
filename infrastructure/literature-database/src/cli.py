"""Command Line Interface for Literature Database."""
from src.utils.path_manager import PathManager
from src.utils.logging import setup_logging
from src.extractors.zotero_sync import ZoteroSync
from src.services.search_service import SearchService
from src.services.paper_service import PaperService
from src.models import Paper, Author, Tag
from src.database import get_session, init_db
import click
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn
import sys
import os

# Add src to path for imports
sys.path.append(str(Path(__file__).parent.parent))


console = Console()


@click.group()
@click.option('--verbose', '-v', is_flag=True, help='Enable verbose logging')
def cli(verbose):
    """Literature Database CLI - Manage your academic papers."""
    if verbose:
        os.environ['LITDB_LOG_LEVEL'] = 'DEBUG'

    setup_logging()


@cli.command()
def init():
    """Initialize the literature database."""
    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            progress.add_task("Initializing database...", total=None)
            init_db()

        console.print("✓ Database initialized successfully!", style="green")

        # Initialize path structure (PathManager creates directories on init)
        PathManager()
        console.print("✓ Directory structure created!", style="green")

    except Exception as e:
        console.print(f"✗ Initialization failed: {e}", style="red")
        sys.exit(1)


@cli.command()
@click.argument('file_path', type=click.Path(exists=True, path_type=Path))
@click.option('--title', help='Override extracted title')
@click.option('--tags', help='Comma-separated tags')
@click.option('--collection', help='Collection name')
def add(file_path, title, tags, collection):
    """Add a paper from PDF file."""
    try:
        paper_service = PaperService()

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            progress.add_task(f"Processing {file_path.name}...", total=None)

            db = next(get_session())
            paper = paper_service.add_paper_from_file(db, file_path)

            # Override title if provided
            if title:
                paper.title = title
                db.commit()

            # Add tags if provided
            if tags:
                tag_names = [t.strip() for t in tags.split(',')]
                for tag_name in tag_names:
                    tag = db.query(Tag).filter_by(name=tag_name).first()
                    if not tag:
                        tag = Tag(name=tag_name)
                        db.add(tag)
                    paper.tags.append(tag)
                db.commit()

            db.close()

        console.print(f"✓ Added paper: {paper.title}", style="green")
        console.print(f"  ID: {paper.id}")
        console.print(f"  Authors: {', '.join([a.name for a in paper.authors])}")
        console.print(f"  Year: {paper.year or 'Unknown'}")

    except Exception as e:
        console.print(f"✗ Failed to add paper: {e}", style="red")
        sys.exit(1)


@cli.command()
@click.argument('query')
@click.option('--limit', '-l', default=10, help='Maximum number of results')
@click.option('--year', type=int, help='Filter by year')
@click.option('--author', help='Filter by author')
@click.option('--journal', help='Filter by journal')
def search(query, limit, year, author, journal):
    """Search papers by text query."""
    try:
        search_service = SearchService()

        # Build filters
        filters = {}
        if year:
            filters['year'] = year
        if author:
            filters['author'] = author
        if journal:
            filters['journal'] = journal

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            progress.add_task(f"Searching for '{query}'...", total=None)
            results = search_service.search(query, limit=limit, filters=filters)

        if not results:
            console.print("No results found.", style="yellow")
            return

        # Display results in table
        table = Table(title=f"Search Results for '{query}' ({len(results)} found)")
        table.add_column("ID", style="cyan", width=4)
        table.add_column("Title", style="green", width=40)
        table.add_column("Authors", style="blue", width=25)
        table.add_column("Year", style="magenta", width=6)
        table.add_column("Score", style="yellow", width=6)

        for result in results:
            table.add_row(
                str(result['id']),
                result['title'][:37] + "..." if len(result['title']) > 40 else result['title'],
                result['authors'][:22] + "..." if len(result['authors']) > 25 else result['authors'],
                str(result['year']) if result['year'] else "",
                f"{result['score']:.2f}"
            )

        console.print(table)

    except Exception as e:
        console.print(f"✗ Search failed: {e}", style="red")
        sys.exit(1)


@cli.command()
@click.option('--limit', '-l', default=20, help='Maximum number of papers to list')
@click.option('--year', type=int, help='Filter by year')
@click.option('--author', help='Filter by author')
@click.option('--tag', help='Filter by tag')
def list(limit, year, author, tag):
    """List papers in the database."""
    try:
        paper_service = PaperService()
        db = next(get_session())

        # Build filters
        filters = {}
        if year:
            filters['year'] = year
        if author:
            filters['author'] = author
        if tag:
            filters['tag'] = tag

        papers = paper_service.list_papers(db, limit=limit, filters=filters)
        db.close()

        if not papers:
            console.print("No papers found.", style="yellow")
            return

        # Display papers in table
        table = Table(title=f"Papers ({len(papers)} found)")
        table.add_column("ID", style="cyan", width=4)
        table.add_column("Title", style="green", width=40)
        table.add_column("Authors", style="blue", width=25)
        table.add_column("Year", style="magenta", width=6)
        table.add_column("Journal", style="white", width=20)

        for paper in papers:
            authors_str = ", ".join([a.name for a in paper.authors])
            table.add_row(
                str(paper.id),
                paper.title[:37] + "..." if len(paper.title) > 40 else paper.title,
                authors_str[:22] + "..." if len(authors_str) > 25 else authors_str,
                str(paper.year) if paper.year else "",
                paper.journal[:17] + "..." if paper.journal and len(paper.journal) > 20 else (paper.journal or "")
            )

        console.print(table)

    except Exception as e:
        console.print(f"✗ List failed: {e}", style="red")
        sys.exit(1)


@cli.command()
@click.argument('paper_id', type=int)
def show(paper_id):
    """Show detailed information about a paper."""
    try:
        paper_service = PaperService()
        db = next(get_session())

        paper = paper_service.get_paper(db, paper_id)
        db.close()

        if not paper:
            console.print(f"Paper with ID {paper_id} not found.", style="red")
            sys.exit(1)

        # Display paper details
        console.print(f"\n[bold green]Paper ID: {paper.id}[/bold green]")
        console.print(f"[bold]Title:[/bold] {paper.title}")

        if paper.authors:
            authors = ", ".join([a.name for a in paper.authors])
            console.print(f"[bold]Authors:[/bold] {authors}")

        if paper.year:
            console.print(f"[bold]Year:[/bold] {paper.year}")

        if paper.journal:
            console.print(f"[bold]Journal:[/bold] {paper.journal}")

        if paper.doi:
            console.print(f"[bold]DOI:[/bold] {paper.doi}")

        if paper.abstract:
            console.print("\n[bold]Abstract:[/bold]")
            console.print(paper.abstract[:500] + ("..." if len(paper.abstract) > 500 else ""))

        if paper.tags:
            tags = ", ".join([t.name for t in paper.tags])
            console.print(f"\n[bold]Tags:[/bold] {tags}")

        if paper.file_path:
            console.print(f"\n[bold]File:[/bold] {paper.file_path}")

        if paper.word_count:
            console.print(f"[bold]Word Count:[/bold] {paper.word_count:,}")

        console.print(f"[bold]Added:[/bold] {paper.date_added.strftime('%Y-%m-%d %H:%M')}")

    except Exception as e:
        console.print(f"✗ Show failed: {e}", style="red")
        sys.exit(1)


@cli.command()
def sync():
    """Sync papers from Zotero."""
    try:
        zotero_sync = ZoteroSync()

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            progress.add_task("Syncing with Zotero...", total=None)

            if zotero_sync.is_api_available():
                added, updated = zotero_sync.sync_from_api()
            else:
                added, updated = zotero_sync.sync_from_local_library()

        console.print("✓ Zotero sync completed!", style="green")
        console.print(f"  Papers added: {added}")
        console.print(f"  Papers updated: {updated}")

    except Exception as e:
        console.print(f"✗ Sync failed: {e}", style="red")
        sys.exit(1)


@cli.command()
def reindex():
    """Reindex all papers for search."""
    try:
        search_service = SearchService()

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            progress.add_task("Reindexing papers...", total=None)

            db = next(get_session())
            count = search_service.reindex_all_papers(db)
            db.close()

        console.print(f"✓ Reindexed {count} papers successfully!", style="green")

    except Exception as e:
        console.print(f"✗ Reindex failed: {e}", style="red")
        sys.exit(1)


@cli.command()
def stats():
    """Show database statistics."""
    try:
        db = next(get_session())

        # Get counts
        total_papers = db.query(Paper).count()
        total_authors = db.query(Author).count()
        total_tags = db.query(Tag).count()

        # Get papers by year
        from sqlalchemy import func
        year_counts = db.query(Paper.year, func.count(Paper.id)).group_by(Paper.year).all()
        year_counts = [(year, count) for year, count in year_counts if year]
        year_counts.sort(reverse=True)

        db.close()

        # Display statistics
        console.print("\n[bold green]Database Statistics[/bold green]")
        console.print(f"Total Papers: {total_papers}")
        console.print(f"Total Authors: {total_authors}")
        console.print(f"Total Tags: {total_tags}")

        if year_counts:
            console.print("\n[bold]Papers by Year:[/bold]")
            for year, count in year_counts[:10]:  # Show top 10 years
                console.print(f"  {year}: {count}")

        # Get disk usage
        path_manager = PathManager()
        usage = path_manager.get_disk_usage()

        console.print("\n[bold]Disk Usage:[/bold]")
        for name, stats in usage.items():
            if 'error' not in stats:
                console.print(f"  {name.title()}: {stats['used_mb']:.1f} MB")

    except Exception as e:
        console.print(f"✗ Stats failed: {e}", style="red")
        sys.exit(1)


@cli.command()
@click.option('--host', default='0.0.0.0', help='Host to bind to')
@click.option('--port', default=8000, help='Port to bind to')
def serve(host, port):
    """Start the API server."""
    try:
        import uvicorn
        from src.api.main import app

        console.print(f"Starting Literature Database API server on {host}:{port}")
        console.print(f"API docs will be available at: http://{host}:{port}/docs")

        uvicorn.run(app, host=host, port=port)

    except ImportError:
        console.print("✗ uvicorn not available. Install with: pip install uvicorn", style="red")
        sys.exit(1)
    except Exception as e:
        console.print(f"✗ Server failed to start: {e}", style="red")
        sys.exit(1)


if __name__ == '__main__':
    cli()
