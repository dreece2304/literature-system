#!/usr/bin/env python
"""Manage manuscript collections for paper citations and writing projects."""
import sys
from pathlib import Path
from typing import List, Dict, Set, Optional
from rich.console import Console
from rich.prompt import Prompt, Confirm
from rich.table import Table
from rich.panel import Panel
import click

# Add src to path for imports
sys.path.append(str(Path(__file__).parent.parent))

from src.database import get_session
from src.models import Paper, Collection, Author
from src.services.search_service import SearchService


class ManuscriptCollectionManager:
    """Manage collections of papers for manuscript writing."""
    
    def __init__(self):
        self.console = Console()
        self.session = next(get_session())
        self.search_service = SearchService()
    
    def create_manuscript_collection(self, manuscript_title: str, description: str = "") -> Collection:
        """Create a new collection for a manuscript."""
        try:
            # Create collection
            collection = Collection(
                name=manuscript_title,
                description=description or f"References for manuscript: {manuscript_title}"
            )
            
            self.session.add(collection)
            self.session.commit()
            
            self.console.print(f"[green]✓ Created collection: {manuscript_title}[/green]")
            return collection
            
        except Exception as e:
            self.session.rollback()
            self.console.print(f"[red]Error creating collection: {e}[/red]")
            raise
    
    def list_collections(self):
        """List all manuscript collections."""
        collections = self.session.query(Collection).all()
        
        if not collections:
            self.console.print("[yellow]No manuscript collections found[/yellow]")
            return
        
        table = Table(title="Manuscript Collections")
        table.add_column("ID", style="cyan")
        table.add_column("Manuscript", style="green")
        table.add_column("Papers", style="yellow")
        table.add_column("Description", style="blue")
        
        for collection in collections:
            paper_count = len(collection.papers) if collection.papers else 0
            description = collection.description[:50] + "..." if len(collection.description) > 50 else collection.description
            
            table.add_row(
                str(collection.id),
                collection.name,
                str(paper_count),
                description
            )
        
        self.console.print(table)
    
    def add_papers_to_collection(self, collection_id: int, search_terms: List[str] = None, paper_ids: List[int] = None):
        """Add papers to a collection via search or direct IDs."""
        collection = self.session.query(Collection).filter_by(id=collection_id).first()
        
        if not collection:
            self.console.print(f"[red]Collection with ID {collection_id} not found[/red]")
            return
        
        papers_to_add = []
        
        # Add by search terms
        if search_terms:
            for term in search_terms:
                search_results = self.search_service.search(term, limit=20)
                
                if search_results:
                    self.console.print(f"\n[blue]Search results for '{term}':[/blue]")
                    
                    # Show search results
                    for i, result in enumerate(search_results, 1):
                        paper = self.session.query(Paper).filter_by(id=result['id']).first()
                        if paper:
                            self.console.print(f"  {i}. {paper.title[:60]}...")
                            self.console.print(f"     Authors: {', '.join([a.name for a in paper.authors[:3]])}...")
                            self.console.print(f"     Journal: {paper.journal} ({paper.year})")
                    
                    # Ask which papers to add
                    selections = Prompt.ask(f"Select papers to add (1-{len(search_results)}, comma-separated, or 'all')", default="")
                    
                    if selections.lower() == 'all':
                        for result in search_results:
                            paper = self.session.query(Paper).filter_by(id=result['id']).first()
                            if paper:
                                papers_to_add.append(paper)
                    elif selections.strip():
                        try:
                            indices = [int(x.strip()) - 1 for x in selections.split(',')]
                            for idx in indices:
                                if 0 <= idx < len(search_results):
                                    paper = self.session.query(Paper).filter_by(id=search_results[idx]['id']).first()
                                    if paper:
                                        papers_to_add.append(paper)
                        except ValueError:
                            self.console.print("[red]Invalid selection format[/red]")
        
        # Add by direct paper IDs
        if paper_ids:
            for paper_id in paper_ids:
                paper = self.session.query(Paper).filter_by(id=paper_id).first()
                if paper:
                    papers_to_add.append(paper)
        
        # Add papers to collection (avoid duplicates)
        added_count = 0
        for paper in papers_to_add:
            if paper not in collection.papers:
                collection.papers.append(paper)
                added_count += 1
        
        if added_count > 0:
            self.session.commit()
            self.console.print(f"[green]✓ Added {added_count} papers to '{collection.name}'[/green]")
        else:
            self.console.print("[yellow]No new papers added[/yellow]")
    
    def view_collection(self, collection_id: int):
        """View papers in a collection."""
        collection = self.session.query(Collection).filter_by(id=collection_id).first()
        
        if not collection:
            self.console.print(f"[red]Collection with ID {collection_id} not found[/red]")
            return
        
        self.console.print(f"\n[bold blue]Collection: {collection.name}[/bold blue]")
        self.console.print(f"Description: {collection.description}")
        self.console.print(f"Papers: {len(collection.papers)}")
        
        if not collection.papers:
            self.console.print("[yellow]No papers in this collection[/yellow]")
            return
        
        # Show papers in collection
        table = Table(title=f"Papers in '{collection.name}'")
        table.add_column("ID", style="cyan")
        table.add_column("Title", style="green", width=50)
        table.add_column("Authors", style="yellow", width=30)
        table.add_column("Year", style="blue")
        table.add_column("Journal", style="magenta", width=25)
        
        for paper in collection.papers:
            authors = ", ".join([a.name for a in paper.authors[:2]])
            if len(paper.authors) > 2:
                authors += f" + {len(paper.authors) - 2} more"
            
            table.add_row(
                str(paper.id),
                paper.title[:47] + "..." if len(paper.title) > 50 else paper.title,
                authors,
                str(paper.year) if paper.year else "N/A",
                (paper.journal[:22] + "...") if paper.journal and len(paper.journal) > 25 else (paper.journal or "N/A")
            )
        
        self.console.print(table)
    
    def export_collection_bibliography(self, collection_id: int, format: str = "bibtex"):
        """Export collection as bibliography."""
        collection = self.session.query(Collection).filter_by(id=collection_id).first()
        
        if not collection:
            self.console.print(f"[red]Collection with ID {collection_id} not found[/red]")
            return
        
        if not collection.papers:
            self.console.print("[yellow]No papers in collection to export[/yellow]")
            return
        
        # Create export filename
        safe_name = "".join(c for c in collection.name if c.isalnum() or c in (' ', '-', '_')).strip()
        safe_name = safe_name.replace(' ', '_')
        filename = f"bibliography_{safe_name}.bib"
        
        # Generate BibTeX entries
        bibtex_entries = []
        for paper in collection.papers:
            # Create citation key
            first_author = paper.authors[0].name.split()[-1] if paper.authors else "Unknown"
            year = paper.year or 2024
            key = f"{first_author}{year}"
            
            # Build BibTeX entry
            entry = f"@article{{{key},\n"
            entry += f"  title = {{{paper.title}}},\n"
            
            if paper.authors:
                authors = " and ".join([a.name for a in paper.authors])
                entry += f"  author = {{{authors}}},\n"
            
            if paper.journal:
                entry += f"  journal = {{{paper.journal}}},\n"
            
            if paper.year:
                entry += f"  year = {{{paper.year}}},\n"
            
            if paper.volume:
                entry += f"  volume = {{{paper.volume}}},\n"
            
            if paper.issue:
                entry += f"  number = {{{paper.issue}}},\n"
            
            if paper.doi:
                entry += f"  doi = {{{paper.doi}}},\n"
            
            entry += "}\n"
            bibtex_entries.append(entry)
        
        # Write to file
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(f"% Bibliography for: {collection.name}\n")
            f.write(f"% Generated from literature database\n")
            f.write(f"% {len(collection.papers)} references\n\n")
            f.write("\n".join(bibtex_entries))
        
        self.console.print(f"[green]✓ Exported {len(collection.papers)} references to {filename}[/green]")
    
    def suggest_related_papers(self, collection_id: int, limit: int = 10):
        """Suggest related papers based on collection content."""
        collection = self.session.query(Collection).filter_by(id=collection_id).first()
        
        if not collection or not collection.papers:
            self.console.print("[yellow]Collection not found or empty[/yellow]")
            return
        
        # Get common keywords from collection papers
        all_tags = set()
        for paper in collection.papers:
            for tag in paper.tags:
                all_tags.add(tag.name.lower())
        
        # Search for papers with similar tags
        suggestions = []
        for tag in list(all_tags)[:5]:  # Use top 5 tags
            search_results = self.search_service.search(tag, limit=limit)
            
            for result in search_results:
                paper = self.session.query(Paper).filter_by(id=result['id']).first()
                if paper and paper not in collection.papers:
                    suggestions.append((paper, result['score']))
        
        # Sort by relevance and deduplicate
        unique_suggestions = {}
        for paper, score in suggestions:
            if paper.id not in unique_suggestions or unique_suggestions[paper.id][1] < score:
                unique_suggestions[paper.id] = (paper, score)
        
        sorted_suggestions = sorted(unique_suggestions.values(), key=lambda x: x[1], reverse=True)[:limit]
        
        if sorted_suggestions:
            self.console.print(f"\n[blue]Suggested papers for '{collection.name}':[/blue]")
            
            table = Table()
            table.add_column("Title", style="green", width=50)
            table.add_column("Authors", style="yellow", width=25)
            table.add_column("Year", style="blue")
            table.add_column("Score", style="red")
            
            for paper, score in sorted_suggestions:
                authors = ", ".join([a.name for a in paper.authors[:2]])
                if len(paper.authors) > 2:
                    authors += "..."
                
                table.add_row(
                    paper.title[:47] + "..." if len(paper.title) > 50 else paper.title,
                    authors,
                    str(paper.year) if paper.year else "N/A",
                    f"{score:.2f}"
                )
            
            self.console.print(table)
        else:
            self.console.print("[yellow]No related papers found[/yellow]")
    
    def __del__(self):
        """Close database session."""
        if hasattr(self, 'session'):
            self.session.close()


@click.command()
@click.option('--action', type=click.Choice(['create', 'list', 'add', 'view', 'export', 'suggest']), help='Action to perform')
@click.option('--title', help='Manuscript title for new collection')
@click.option('--collection-id', type=int, help='Collection ID')
@click.option('--search', help='Search terms for adding papers')
@click.option('--description', help='Collection description')
def main(action, title, collection_id, search, description):
    """Manage manuscript collections for citation organization."""
    manager = ManuscriptCollectionManager()
    
    if action == 'create':
        if not title:
            title = Prompt.ask("Manuscript title")
        description = description or Prompt.ask("Description (optional)", default="")
        manager.create_manuscript_collection(title, description)
    
    elif action == 'list':
        manager.list_collections()
    
    elif action == 'add':
        if not collection_id:
            collection_id = int(Prompt.ask("Collection ID"))
        if not search:
            search = Prompt.ask("Search terms (comma-separated)")
        search_terms = [term.strip() for term in search.split(',')]
        manager.add_papers_to_collection(collection_id, search_terms=search_terms)
    
    elif action == 'view':
        if not collection_id:
            collection_id = int(Prompt.ask("Collection ID"))
        manager.view_collection(collection_id)
    
    elif action == 'export':
        if not collection_id:
            collection_id = int(Prompt.ask("Collection ID"))
        manager.export_collection_bibliography(collection_id)
    
    elif action == 'suggest':
        if not collection_id:
            collection_id = int(Prompt.ask("Collection ID"))
        manager.suggest_related_papers(collection_id)
    
    else:
        click.echo("Please specify an action: create, list, add, view, export, or suggest")


if __name__ == "__main__":
    main()