"""Search functionality using Whoosh full-text search."""
import os
from pathlib import Path
from typing import Dict, List, Optional, Any
from whoosh import fields, index, qparser
from whoosh.analysis import StemmingAnalyzer
from sqlalchemy.orm import Session
from loguru import logger

from src.models import Paper, SearchIndex


class SearchService:
    """Handle full-text search using Whoosh."""

    def __init__(self, index_path: Optional[str] = None):
        """Initialize search service."""
        self.index_path = Path(index_path or "data/cache/search_index")
        self.index_path.mkdir(parents=True, exist_ok=True)

        self.schema = fields.Schema(
            id=fields.NUMERIC(stored=True, unique=True),
            title=fields.TEXT(stored=True, analyzer=StemmingAnalyzer()),
            abstract=fields.TEXT(stored=True, analyzer=StemmingAnalyzer()),
            full_text=fields.TEXT(analyzer=StemmingAnalyzer()),
            authors=fields.TEXT(stored=True, analyzer=StemmingAnalyzer()),
            tags=fields.TEXT(stored=True),
            journal=fields.TEXT(stored=True),
            year=fields.NUMERIC(stored=True),
            doi=fields.TEXT(stored=True),
            arxiv_id=fields.TEXT(stored=True),
            file_path=fields.TEXT(stored=True)
        )

        self.index = self._get_or_create_index()

    def _get_or_create_index(self):
        """Get existing index or create new one."""
        if index.exists_in(str(self.index_path)):
            return index.open_dir(str(self.index_path))
        else:
            return index.create_in(str(self.index_path), self.schema)

    def add_paper_to_index(self, paper: Paper):
        """Add a single paper to the search index."""
        try:
            writer = self.index.writer()

            # Prepare authors string
            authors_text = ", ".join([author.name for author in paper.authors])

            # Prepare tags string
            tags_text = ", ".join([tag.name for tag in paper.tags])

            writer.add_document(
                id=paper.id,
                title=paper.title or "",
                abstract=paper.abstract or "",
                full_text=paper.full_text or "",
                authors=authors_text,
                tags=tags_text,
                journal=paper.journal or "",
                year=paper.year or 0,
                doi=paper.doi or "",
                arxiv_id=paper.arxiv_id or "",
                file_path=paper.file_path or ""
            )

            writer.commit()
            logger.debug(f"Added paper to search index: {paper.title}")

        except Exception as e:
            logger.error(f"Failed to add paper {paper.id} to index: {e}")
            raise

    def remove_paper_from_index(self, paper_id: int):
        """Remove a paper from the search index."""
        try:
            writer = self.index.writer()
            writer.delete_by_term('id', paper_id)
            writer.commit()
            logger.debug(f"Removed paper {paper_id} from search index")

        except Exception as e:
            logger.error(f"Failed to remove paper {paper_id} from index: {e}")
            raise

    def update_paper_in_index(self, paper: Paper):
        """Update a paper in the search index."""
        try:
            # Remove old version and add new
            self.remove_paper_from_index(paper.id)
            self.add_paper_to_index(paper)
            logger.debug(f"Updated paper in search index: {paper.title}")

        except Exception as e:
            logger.error(f"Failed to update paper {paper.id} in index: {e}")
            raise

    def search(
        self,
        query: str,
        limit: int = 20,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict]:
        """
        Search papers by query string.

        Args:
            query: Search query
            limit: Maximum number of results
            filters: Optional filters (year, journal, etc.)

        Returns:
            List of paper dictionaries with search scores
        """
        try:
            with self.index.searcher() as searcher:
                # Create query parser
                parser = qparser.MultifieldParser(
                    ["title", "abstract", "full_text", "authors"],
                    self.index.schema
                )

                # Parse main query
                parsed_query = parser.parse(query)

                # Apply filters if provided
                if filters:
                    filter_queries = []

                    if 'year' in filters:
                        filter_queries.append(f"year:{filters['year']}")

                    if 'journal' in filters:
                        filter_queries.append(f"journal:{filters['journal']}")

                    if 'author' in filters:
                        filter_queries.append(f"authors:{filters['author']}")

                    if filter_queries:
                        filter_query_str = " AND ".join(filter_queries)
                        filter_parsed = parser.parse(filter_query_str)
                        parsed_query = parsed_query & filter_parsed

                # Execute search
                results = searcher.search(parsed_query, limit=limit)

                # Convert results to dictionaries
                search_results = []
                for result in results:
                    search_results.append({
                        'id': result['id'],
                        'title': result['title'],
                        'abstract': result['abstract'],
                        'authors': result['authors'],
                        'journal': result['journal'],
                        'year': result['year'],
                        'doi': result['doi'],
                        'arxiv_id': result['arxiv_id'],
                        'score': result.score
                    })

                logger.info(f"Search query '{query}' returned {len(search_results)} results")
                return search_results

        except Exception as e:
            logger.error(f"Search failed for query '{query}': {e}")
            raise

    def reindex_all_papers(self, db: Session) -> int:
        """Reindex all papers in the database."""
        try:
            # Clear existing index by recreating it
            import shutil
            if os.path.exists(self.index_path):
                shutil.rmtree(self.index_path)

            # Ensure directory exists
            os.makedirs(self.index_path, exist_ok=True)

            # Create fresh index
            self.index = index.create_in(str(self.index_path), self.schema)

            # Get all papers
            papers = db.query(Paper).all()

            # Batch index all papers using a single writer
            writer = self.index.writer()
            count = 0

            for paper in papers:
                # Build search text
                search_text = f"{paper.title or ''} {paper.abstract or ''} {paper.journal or ''}"
                authors_text = ""
                tags_text = ""

                # Get authors and tags (may not be loaded due to session issues)
                try:
                    authors_text = " ".join([author.name for author in paper.authors])
                    tags_text = " ".join([tag.name for tag in paper.tags])
                except Exception:
                    # If relationships aren't loaded, that's okay
                    pass

                writer.add_document(
                    id=paper.id,
                    title=paper.title or "",
                    abstract=paper.abstract or "",
                    full_text=search_text,
                    authors=authors_text,
                    tags=tags_text,
                    journal=paper.journal or "",
                    year=paper.year or 0,
                    doi=paper.doi or "",
                    arxiv_id=paper.arxiv_id or "",
                    file_path=paper.file_path or ""
                )
                count += 1

                if count % 100 == 0:
                    logger.info(f"Indexed {count} papers...")

            writer.commit()

            # Update search index tracking
            db.query(SearchIndex).delete()
            for paper in papers:
                search_index = SearchIndex(
                    paper_id=paper.id,
                    index_version="1.0"
                )
                db.add(search_index)

            db.commit()

            logger.info(f"Reindexed {count} papers successfully")
            return count

        except Exception as e:
            logger.error(f"Failed to reindex papers: {e}")
            raise

    def get_suggestions(self, query: str, field: str = "title") -> List[str]:
        """Get search suggestions based on partial query."""
        try:
            with self.index.searcher() as searcher:
                # Use spell checker for suggestions
                corrector = searcher.corrector(field)
                suggestions = corrector.suggest(query, limit=5)
                return suggestions

        except Exception as e:
            logger.warning(f"Failed to get suggestions for '{query}': {e}")
            return []

    def get_index_stats(self) -> Dict[str, Any]:
        """Get statistics about the search index."""
        try:
            with self.index.searcher() as searcher:
                return {
                    'total_documents': searcher.doc_count(),
                    'index_path': str(self.index_path),
                    'schema_fields': list(self.schema.names())
                }
        except Exception as e:
            logger.error(f"Failed to get index stats: {e}")
            return {'error': str(e)}
