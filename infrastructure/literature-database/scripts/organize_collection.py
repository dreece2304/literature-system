#!/usr/bin/env python
"""Tools for organizing and categorizing paper collections."""
import sys
from pathlib import Path
from typing import List, Dict, Set, Optional, Tuple
from collections import defaultdict, Counter
import re
from rich.console import Console
from rich.prompt import Prompt, Confirm, IntPrompt
from rich.table import Table
from rich.panel import Panel
from rich.columns import Columns
import click

# Add src to path for imports
sys.path.append(str(Path(__file__).parent.parent))

from src.database import get_session
from src.models import Paper, Author, Tag, Collection
from src.services.paper_service import PaperService
from src.utils.logging import setup_logging

console = Console()


class CollectionOrganizer:
    """Organize and categorize paper collections."""
    
    def __init__(self):
        self.session = next(get_session())
        self.paper_service = PaperService()
        
        # Academic field patterns for auto-categorization (research-specific)
        self.field_patterns = {
            'Atomic Layer Deposition': [
                'atomic layer deposition', 'ALD', 'atomic layer epitaxy', 'ALE',
                'precursor', 'trimethylaluminum', 'TMA', 'thermal ALD', 'plasma ALD',
                'pulse', 'purge', 'self-limiting', 'conformal coating', 'nucleation'
            ],
            'Molecular Layer Deposition': [
                'molecular layer deposition', 'MLD', 'hybrid materials', 'organic-inorganic',
                'alucone', 'zincone', 'titanicone', 'hafnicone', 'polymer films',
                'sequential polymerization', 'molecular precursor'
            ],
            'Membrane Science': [
                'membrane', 'nanofiltration', 'ultrafiltration', 'reverse osmosis',
                'pervaporation', 'gas separation', 'permeability', 'selectivity',
                'membrane fouling', 'anti-fouling', 'membrane reactor', 'hollow fiber'
            ],
            'Surface Engineering': [
                'surface modification', 'surface functionalization', 'wetting',
                'hydrophobic', 'hydrophilic', 'superhydrophobic', 'contact angle',
                'surface energy', 'adhesion', 'coating', 'surface treatment'
            ],
            'Electrocatalysis': [
                'electrocatalysis', 'oxygen reduction reaction', 'ORR', 'oxygen evolution reaction', 'OER',
                'hydrogen evolution reaction', 'HER', 'catalyst', 'electrode',
                'fuel cell', 'electrochemical', 'overpotential', 'current density'
            ],
            'Energy Materials': [
                'lithium battery', 'solid electrolyte interphase', 'SEI', 'anode', 'cathode',
                'lithium metal', 'dendrite', 'electrolyte', 'ionic conductivity',
                'battery cycling', 'capacity retention', 'coulombic efficiency'
            ],
            'Nanoporous Materials': [
                'porous materials', 'MOF', 'metal organic framework', 'zeolite',
                'pore size', 'surface area', 'adsorption', 'gas storage',
                'framework', 'linker', 'node', 'topology'
            ],
            'Thin Film Characterization': [
                'XPS', 'ellipsometry', 'AFM', 'SEM', 'TEM', 'XRD',
                'thickness measurement', 'film properties', 'crystallinity',
                'morphology', 'composition', 'interface'
            ],
            'Machine Learning': [
                'machine learning', 'neural network', 'deep learning', 'artificial intelligence',
                'classification', 'regression', 'clustering', 'reinforcement learning',
                'supervised learning', 'unsupervised learning', 'CNN', 'RNN', 'LSTM', 'GAN'
            ],
            'Natural Language Processing': [
                'natural language', 'NLP', 'text processing', 'language model', 'sentiment analysis',
                'named entity recognition', 'parsing', 'tokenization', 'word embedding',
                'transformer', 'BERT', 'GPT', 'language understanding'
            ],
            'Computer Vision': [
                'computer vision', 'image processing', 'object detection', 'face recognition',
                'image classification', 'segmentation', 'optical character recognition',
                'feature extraction', 'edge detection', 'pattern recognition'
            ],
            'Data Science': [
                'data science', 'data mining', 'data analysis', 'statistics', 'big data',
                'data visualization', 'predictive analytics', 'business intelligence',
                'exploratory data analysis', 'feature engineering'
            ],
            'Cybersecurity': [
                'cybersecurity', 'information security', 'network security', 'cryptography',
                'malware', 'intrusion detection', 'vulnerability', 'penetration testing',
                'security analysis', 'threat detection', 'authentication'
            ],
            'Software Engineering': [
                'software engineering', 'software development', 'programming', 'code quality',
                'software architecture', 'design patterns', 'testing', 'debugging',
                'version control', 'agile', 'DevOps'
            ],
            'Human-Computer Interaction': [
                'human computer interaction', 'HCI', 'user experience', 'usability',
                'user interface', 'interaction design', 'user study', 'accessibility'
            ],
            'Databases': [
                'database', 'SQL', 'NoSQL', 'data storage', 'query optimization',
                'database design', 'ACID', 'transaction', 'indexing'
            ],
            'Systems': [
                'operating system', 'distributed system', 'parallel computing',
                'cloud computing', 'performance', 'scalability', 'architecture'
            ]
        }
        
        # Common academic venues for categorization
        self.venue_categories = {
            'Top-Tier ML': ['NIPS', 'ICML', 'ICLR', 'NeurIPS', 'JMLR'],
            'Top-Tier CV': ['CVPR', 'ICCV', 'ECCV', 'PAMI', 'IJCV'],
            'Top-Tier NLP': ['ACL', 'EMNLP', 'NAACL', 'COLING', 'TACL'],
            'Top-Tier Systems': ['OSDI', 'SOSP', 'NSDI', 'SIGCOMM', 'MOBICOM'],
            'Top-Tier Security': ['IEEE S&P', 'CCS', 'USENIX Security', 'NDSS'],
            'Top-Tier DB': ['SIGMOD', 'VLDB', 'ICDE', 'PODS'],
            'Conferences': ['Conference', 'Proceedings', 'Workshop'],
            'Journals': ['Journal', 'Transactions', 'Letters', 'Review']
        }
    
    def analyze_collection(self) -> Dict:
        """Analyze the current collection and provide insights."""
        papers = self.session.query(Paper).all()
        
        analysis = {
            'total_papers': len(papers),
            'papers_with_abstracts': sum(1 for p in papers if p.abstract),
            'papers_with_years': sum(1 for p in papers if p.year),
            'papers_with_dois': sum(1 for p in papers if p.doi),
            'papers_with_pdfs': sum(1 for p in papers if p.file_path),
            'unique_authors': len(set(a.name for p in papers for a in p.authors)),
            'unique_journals': len(set(p.journal for p in papers if p.journal)),
            'year_range': self._get_year_range(papers),
            'top_authors': self._get_top_authors(papers),
            'top_journals': self._get_top_journals(papers),
            'field_distribution': self._analyze_fields(papers),
            'untagged_papers': sum(1 for p in papers if not p.tags),
            'uncategorized_papers': sum(1 for p in papers if not p.collections)
        }
        
        return analysis
    
    def _get_year_range(self, papers: List[Paper]) -> Tuple[int, int]:
        """Get the range of publication years."""
        years = [p.year for p in papers if p.year]
        if years:
            return min(years), max(years)
        return 0, 0
    
    def _get_top_authors(self, papers: List[Paper], limit: int = 10) -> List[Tuple[str, int]]:
        """Get most frequent authors."""
        author_counts = Counter()
        for paper in papers:
            for author in paper.authors:
                author_counts[author.name] += 1
        return author_counts.most_common(limit)
    
    def _get_top_journals(self, papers: List[Paper], limit: int = 10) -> List[Tuple[str, int]]:
        """Get most frequent journals."""
        journal_counts = Counter()
        for paper in papers:
            if paper.journal:
                journal_counts[paper.journal] += 1
        return journal_counts.most_common(limit)
    
    def _analyze_fields(self, papers: List[Paper]) -> Dict[str, int]:
        """Analyze papers by academic field."""
        field_counts = defaultdict(int)
        
        for paper in papers:
            text = f"{paper.title or ''} {paper.abstract or ''}".lower()
            
            for field, keywords in self.field_patterns.items():
                for keyword in keywords:
                    if keyword.lower() in text:
                        field_counts[field] += 1
                        break  # Count each paper only once per field
        
        return dict(field_counts)
    
    def suggest_tags(self, paper: Paper) -> List[str]:
        """Suggest tags for a paper based on content analysis."""
        suggestions = []
        text = f"{paper.title or ''} {paper.abstract or ''}".lower()
        
        # Field-based suggestions
        for field, keywords in self.field_patterns.items():
            if any(keyword.lower() in text for keyword in keywords):
                suggestions.append(field.replace(' ', '-').lower())
        
        # Venue-based suggestions
        if paper.journal:
            journal_lower = paper.journal.lower()
            for category, venues in self.venue_categories.items():
                if any(venue.lower() in journal_lower for venue in venues):
                    suggestions.append(category.replace(' ', '-').lower())
        
        # Year-based suggestions
        if paper.year:
            decade = f"{paper.year//10*10}s"
            suggestions.append(decade)
            
            if paper.year >= 2020:
                suggestions.append('recent')
            elif paper.year >= 2010:
                suggestions.append('2010s')
        
        # Method-based suggestions (basic)
        method_keywords = {
            'survey': ['survey', 'review', 'overview'],
            'empirical': ['empirical', 'experimental', 'evaluation'],
            'theoretical': ['theoretical', 'theory', 'analysis'],
            'application': ['application', 'case study', 'implementation']
        }
        
        for tag, keywords in method_keywords.items():
            if any(keyword in text for keyword in keywords):
                suggestions.append(tag)
        
        return list(set(suggestions))  # Remove duplicates
    
    def suggest_collections(self, paper: Paper) -> List[str]:
        """Suggest collections for a paper."""
        suggestions = []
        
        # Field-based collections
        text = f"{paper.title or ''} {paper.abstract or ''}".lower()
        for field, keywords in self.field_patterns.items():
            if any(keyword.lower() in text for keyword in keywords):
                suggestions.append(field)
        
        # Author-based collections (if author has many papers)
        for author in paper.authors:
            author_paper_count = self.session.query(Paper).join(Paper.authors).filter(
                Author.name == author.name
            ).count()
            if author_paper_count >= 3:  # Threshold for creating author collection
                suggestions.append(f"Papers by {author.name}")
        
        # Venue-based collections
        if paper.journal:
            suggestions.append(f"Published in {paper.journal}")
        
        # Year-based collections
        if paper.year:
            suggestions.append(f"Papers from {paper.year}")
            decade = f"{paper.year//10*10}-{paper.year//10*10+9}"
            suggestions.append(f"Papers from {decade}")
        
        return suggestions
    
    def auto_categorize_papers(self, dry_run: bool = False) -> Dict[str, int]:
        """Automatically categorize papers with suggested tags and collections."""
        papers = self.session.query(Paper).all()
        stats = {'tags_added': 0, 'collections_added': 0, 'papers_processed': 0}
        
        console.print(f"\n[blue]Auto-categorizing {len(papers)} papers...[/blue]")
        
        for paper in papers:
            stats['papers_processed'] += 1
            
            # Add suggested tags
            if not paper.tags:  # Only add to untagged papers
                suggested_tags = self.suggest_tags(paper)
                if suggested_tags and not dry_run:
                    for tag_name in suggested_tags[:3]:  # Limit to 3 tags
                        tag = self._get_or_create_tag(tag_name)
                        paper.tags.append(tag)
                        stats['tags_added'] += 1
            
            # Add suggested collections
            if not paper.collections:  # Only add to uncategorized papers
                suggested_collections = self.suggest_collections(paper)
                if suggested_collections and not dry_run:
                    for collection_name in suggested_collections[:2]:  # Limit to 2 collections
                        collection = self._get_or_create_collection(collection_name)
                        paper.collections.append(collection)
                        stats['collections_added'] += 1
        
        if not dry_run:
            self.session.commit()
        
        return stats
    
    def interactive_categorization(self):
        """Interactive paper categorization interface."""
        untagged_papers = self.session.query(Paper).filter(~Paper.tags.any()).all()
        
        console.print(f"\n[blue]Found {len(untagged_papers)} untagged papers[/blue]")
        
        if not untagged_papers:
            console.print("[green]All papers are already tagged![/green]")
            return
        
        for i, paper in enumerate(untagged_papers, 1):
            console.print(f"\n[bold cyan]Paper {i}/{len(untagged_papers)}:[/bold cyan]")
            console.print(f"[bold]Title:[/bold] {paper.title}")
            
            if paper.authors:
                authors = ", ".join([a.name for a in paper.authors])
                console.print(f"[bold]Authors:[/bold] {authors}")
            
            if paper.year:
                console.print(f"[bold]Year:[/bold] {paper.year}")
            
            if paper.journal:
                console.print(f"[bold]Journal:[/bold] {paper.journal}")
            
            if paper.abstract:
                abstract = paper.abstract[:200] + "..." if len(paper.abstract) > 200 else paper.abstract
                console.print(f"[bold]Abstract:[/bold] {abstract}")
            
            # Show suggestions
            suggested_tags = self.suggest_tags(paper)
            if suggested_tags:
                console.print(f"[yellow]Suggested tags:[/yellow] {', '.join(suggested_tags)}")
            
            suggested_collections = self.suggest_collections(paper)
            if suggested_collections:
                console.print(f"[yellow]Suggested collections:[/yellow] {', '.join(suggested_collections[:3])}")
            
            # Get user input
            if Confirm.ask("\nCategorize this paper?", default=True):
                # Add tags
                if suggested_tags and Confirm.ask("Use suggested tags?", default=True):
                    for tag_name in suggested_tags[:3]:
                        tag = self._get_or_create_tag(tag_name)
                        paper.tags.append(tag)
                else:
                    custom_tags = Prompt.ask("Enter tags (comma-separated)", default="")
                    if custom_tags:
                        for tag_name in custom_tags.split(','):
                            tag_name = tag_name.strip()
                            if tag_name:
                                tag = self._get_or_create_tag(tag_name)
                                paper.tags.append(tag)
                
                # Add collections
                if suggested_collections and Confirm.ask("Add to suggested collections?", default=False):
                    for collection_name in suggested_collections[:2]:
                        collection = self._get_or_create_collection(collection_name)
                        paper.collections.append(collection)
                
                self.session.commit()
                console.print("[green]✓ Paper categorized[/green]")
            else:
                console.print("[yellow]⚠ Paper skipped[/yellow]")
    
    def _get_or_create_tag(self, name: str) -> Tag:
        """Get existing tag or create new one."""
        tag = self.session.query(Tag).filter(Tag.name == name).first()
        if not tag:
            tag = Tag(name=name)
            self.session.add(tag)
        return tag
    
    def _get_or_create_collection(self, name: str) -> Collection:
        """Get existing collection or create new one."""
        collection = self.session.query(Collection).filter(Collection.name == name).first()
        if not collection:
            collection = Collection(name=name)
            self.session.add(collection)
        return collection
    
    def show_analysis(self):
        """Display collection analysis."""
        analysis = self.analyze_collection()
        
        # Overview table
        overview_table = Table(title="Collection Overview")
        overview_table.add_column("Metric", style="cyan")
        overview_table.add_column("Value", style="green")
        
        overview_table.add_row("Total Papers", str(analysis['total_papers']))
        overview_table.add_row("With Abstracts", f"{analysis['papers_with_abstracts']}")
        overview_table.add_row("With Years", f"{analysis['papers_with_years']}")
        overview_table.add_row("With DOIs", f"{analysis['papers_with_dois']}")
        overview_table.add_row("With PDFs", f"{analysis['papers_with_pdfs']}")
        overview_table.add_row("Unique Authors", str(analysis['unique_authors']))
        overview_table.add_row("Unique Journals", str(analysis['unique_journals']))
        
        if analysis['year_range'][0] > 0:
            overview_table.add_row("Year Range", f"{analysis['year_range'][0]}-{analysis['year_range'][1]}")
        
        overview_table.add_row("Untagged Papers", str(analysis['untagged_papers']))
        overview_table.add_row("Uncategorized Papers", str(analysis['uncategorized_papers']))
        
        console.print(overview_table)
        
        # Field distribution
        if analysis['field_distribution']:
            field_table = Table(title="Field Distribution")
            field_table.add_column("Field", style="blue")
            field_table.add_column("Papers", style="yellow")
            
            for field, count in sorted(analysis['field_distribution'].items(), 
                                     key=lambda x: x[1], reverse=True):
                field_table.add_row(field, str(count))
            
            console.print(field_table)
        
        # Top authors
        if analysis['top_authors']:
            author_table = Table(title="Top Authors")
            author_table.add_column("Author", style="green")
            author_table.add_column("Papers", style="yellow")
            
            for author, count in analysis['top_authors'][:10]:
                author_table.add_row(author, str(count))
            
            console.print(author_table)
        
        # Top journals
        if analysis['top_journals']:
            journal_table = Table(title="Top Journals/Conferences")
            journal_table.add_column("Venue", style="magenta")
            journal_table.add_column("Papers", style="yellow")
            
            for journal, count in analysis['top_journals'][:10]:
                journal_table.add_row(journal, str(count))
            
            console.print(journal_table)
    
    def cleanup(self):
        """Cleanup resources."""
        self.session.close()


@click.group()
def organize():
    """Literature collection organization tools."""
    setup_logging()


@organize.command()
def analyze():
    """Analyze your paper collection and show statistics."""
    organizer = CollectionOrganizer()
    try:
        console.print("[bold green]Literature Collection Analysis[/bold green]")
        console.print("=" * 50)
        organizer.show_analysis()
    finally:
        organizer.cleanup()


@organize.command()
@click.option('--dry-run', is_flag=True, help='Show what would be done without making changes')
def auto_categorize(dry_run):
    """Automatically categorize papers with suggested tags and collections."""
    organizer = CollectionOrganizer()
    try:
        if dry_run:
            console.print("[yellow]DRY RUN - No changes will be made[/yellow]")
        
        stats = organizer.auto_categorize_papers(dry_run=dry_run)
        
        console.print(f"\n[green]Auto-categorization complete![/green]")
        console.print(f"Papers processed: {stats['papers_processed']}")
        console.print(f"Tags added: {stats['tags_added']}")
        console.print(f"Collections added: {stats['collections_added']}")
        
    finally:
        organizer.cleanup()


@organize.command()
def interactive():
    """Interactively categorize papers one by one."""
    organizer = CollectionOrganizer()
    try:
        organizer.interactive_categorization()
    finally:
        organizer.cleanup()


@organize.command()
@click.argument('paper_id', type=int)
def suggest(paper_id):
    """Show categorization suggestions for a specific paper."""
    organizer = CollectionOrganizer()
    try:
        paper = organizer.session.query(Paper).filter(Paper.id == paper_id).first()
        
        if not paper:
            console.print(f"[red]Paper with ID {paper_id} not found[/red]")
            return
        
        console.print(f"[bold green]Suggestions for: {paper.title}[/bold green]")
        
        suggested_tags = organizer.suggest_tags(paper)
        if suggested_tags:
            console.print(f"\n[blue]Suggested tags:[/blue]")
            for tag in suggested_tags:
                console.print(f"  • {tag}")
        
        suggested_collections = organizer.suggest_collections(paper)
        if suggested_collections:
            console.print(f"\n[blue]Suggested collections:[/blue]")
            for collection in suggested_collections:
                console.print(f"  • {collection}")
        
        if not suggested_tags and not suggested_collections:
            console.print("[yellow]No suggestions available for this paper[/yellow]")
            
    finally:
        organizer.cleanup()


if __name__ == '__main__':
    organize()