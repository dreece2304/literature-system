"""Zotero integration for syncing papers and collections."""
import os
# shutil removed - unused
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from pyzotero import zotero
import yaml
from loguru import logger

from literature_core.database import get_session
from literature_core.models import Paper, Author, paper_authors

from extractors.zotero_local_api import ZoteroLocalAPI


class ZoteroSync:
    """Handle Zotero synchronization with preference for local API."""

    def __init__(self, config_path: Optional[str] = None):
        """Initialize Zotero client with credentials."""
        self.config = self._load_config(config_path)
        self.client = None
        self.local_api = ZoteroLocalAPI()
        self._init_client()

    def _load_config(self, config_path: Optional[str] = None) -> Dict:
        """Load configuration files."""
        # Get base path - config is in data/config/
        # This file is at src/extractors/zotero_sync.py
        src_dir = Path(__file__).parent.parent  # src/
        project_root = src_dir.parent  # research/
        config_dir = project_root / 'data' / 'config'

        # Load main settings
        if config_path:
            settings_path = Path(config_path)
        else:
            env_path = os.getenv('LITDB_CONFIG_PATH')
            if env_path:
                settings_path = Path(env_path)
            else:
                settings_path = config_dir / 'settings.yml'

        with open(settings_path, 'r') as f:
            config = yaml.safe_load(f)

        # Load credentials
        credentials_path = config_dir / 'credentials.yml'
        try:
            with open(credentials_path, 'r') as f:
                credentials = yaml.safe_load(f)
                config['zotero']['api_key'] = credentials.get('zotero', {}).get('api_key', '')
        except FileNotFoundError:
            logger.warning(f"credentials.yml not found at {credentials_path} - API sync will be unavailable")
            config['zotero']['api_key'] = ''

        return config

    def _init_client(self):
        """Initialize Zotero API client if credentials available."""
        zotero_config = self.config['zotero']

        if zotero_config['api_key'] and zotero_config['library_id']:
            try:
                self.client = zotero.Zotero(
                    library_id=zotero_config['library_id'],
                    library_type=zotero_config['library_type'],
                    api_key=zotero_config['api_key']
                )
                logger.info("Zotero API client initialized")
            except Exception as e:
                logger.error(f"Failed to initialize Zotero API client: {e}")
                self.client = None
        else:
            logger.info("Zotero API credentials not configured - using local sync only")

    def sync_from_local_library(self) -> Tuple[int, int]:
        """
        Sync papers from local Zotero library (Windows path).

        Returns:
            Tuple of (papers_added, papers_updated)
        """
        zotero_path = Path(self.config['zotero']['windows_path'])

        if not zotero_path.exists():
            raise FileNotFoundError(f"Zotero library not found at: {zotero_path}")

        # Look for Zotero database
        zotero_db = zotero_path / "zotero.sqlite"
        if not zotero_db.exists():
            raise FileNotFoundError(f"Zotero database not found: {zotero_db}")

        logger.info(f"Syncing from local Zotero library: {zotero_path}")

        # For now, return placeholder counts
        # Full implementation would parse Zotero's SQLite database
        logger.warning("Local Zotero sync not yet implemented - placeholder only")
        return 0, 0

    def sync_from_api(self) -> Tuple[int, int]:
        """
        Sync papers from Zotero web API.

        NOTE: The Zotero connector API (port 23119) cannot list items - it's designed
        for browser extensions to SAVE items. We must use the web API for syncing.

        Returns:
            Tuple of (papers_added, papers_updated)
        """
        # Check if Zotero is running (informational only)
        if self.local_api.is_available():
            version = self.local_api.get_zotero_version()
            logger.info(f"Zotero {version} is running locally")

        # Web API is required for syncing items
        if not self.client:
            raise ValueError(
                "Zotero web API client required for sync. "
                "Configure API key in config/credentials.yml"
            )

        logger.info("Syncing from Zotero web API...")
        papers_added = 0
        papers_updated = 0

        try:
            # Get all items from Zotero (handle pagination)
            logger.info("Fetching items from Zotero web API...")
            items = self.client.everything(self.client.items())

            with get_session() as session:
                for item in items:
                    try:
                        if self._is_paper_item(item):
                            added, updated = self._sync_paper_item(session, item)
                            if added:
                                papers_added += 1
                            if updated:
                                papers_updated += 1

                    except Exception as e:
                        logger.error(f"Failed to sync item {item.get('key', 'unknown')}: {e}")

                session.commit()

        except Exception as e:
            logger.error(f"Zotero web API sync failed: {e}")
            raise

        logger.info(f"Zotero sync complete: {papers_added} added, {papers_updated} updated")
        return papers_added, papers_updated

    def _is_paper_item(self, item: Dict) -> bool:
        """Check if Zotero item is a paper/article."""
        item_type = item.get('data', {}).get('itemType', '')
        return item_type in ['journalArticle', 'preprint', 'conferencePaper', 'report']

    def _sync_paper_item(self, session, item: Dict) -> Tuple[bool, bool]:
        """
        Sync a single paper item from Zotero.

        Returns:
            Tuple of (was_added, was_updated)
        """
        data = item.get('data', {})
        zotero_key = item.get('key', '')
        doi = data.get('DOI', '').strip()

        # Check if paper already exists by zotero_key
        existing_paper = session.query(Paper).filter_by(zotero_key=zotero_key).first()

        if existing_paper:
            # Update existing paper
            updated = self._update_paper_from_zotero(existing_paper, data)
            return False, updated

        # Check if paper exists by DOI (might have been imported from elsewhere)
        if doi:
            existing_by_doi = session.query(Paper).filter_by(doi=doi).first()
            if existing_by_doi:
                # Link existing paper to Zotero
                existing_by_doi.zotero_key = zotero_key
                existing_by_doi.zotero_version = data.get('version', 0)
                # Also update with any new data from Zotero
                self._update_paper_from_zotero(existing_by_doi, data)
                logger.info(f"Linked existing paper (DOI: {doi}) to Zotero key {zotero_key}")
                return False, True

        # Create new paper
        self._create_paper_from_zotero(session, data, zotero_key)
        return True, False

    def _create_paper_from_zotero(self, session, data: Dict, zotero_key: str) -> Paper:
        """Create a new Paper object from Zotero data."""
        # Handle DOI - convert empty string to None for unique constraint
        doi = data.get('DOI', '').strip()
        if not doi:
            doi = None

        paper = Paper(
            title=data.get('title', ''),
            abstract=data.get('abstractNote', ''),
            year=self._extract_year(data.get('date', '')),
            doi=doi,
            journal=data.get('publicationTitle', ''),
            volume=data.get('volume', ''),
            issue=data.get('issue', ''),
            pages=data.get('pages', ''),
            publisher=data.get('publisher', ''),
            zotero_key=zotero_key,
            zotero_version=data.get('version', 0)
        )

        # Flush to get paper ID before adding authors
        session.add(paper)
        session.flush()

        # Add authors with position (exclude editors)
        creators = data.get('creators', [])
        position = 0
        for creator in creators:
            if creator.get('creatorType') == 'author':  # Only authors, not editors
                author_name = self._format_author_name(creator)
                if author_name:
                    # Find or create author
                    author = session.query(Author).filter_by(name=author_name).first()
                    if not author:
                        author = Author(name=author_name)
                        session.add(author)
                        session.flush()
                    # Insert with position
                    session.execute(
                        paper_authors.insert().values(
                            paper_id=paper.id,
                            author_id=author.id,
                            position=position
                        )
                    )
                    position += 1

        return paper

    def _update_paper_from_zotero(self, paper: Paper, data: Dict) -> bool:
        """Update existing paper with Zotero data."""
        updated = False

        # Check if Zotero version is newer
        new_version = data.get('version', 0)
        if new_version <= paper.zotero_version:
            return False  # No update needed

        # Update fields
        fields_to_update = {
            'title': data.get('title', ''),
            'abstract': data.get('abstractNote', ''),
            'year': self._extract_year(data.get('date', '')),
            'doi': data.get('DOI', ''),
            'journal': data.get('publicationTitle', ''),
            'volume': data.get('volume', ''),
            'issue': data.get('issue', ''),
            'pages': data.get('pages', ''),
            'publisher': data.get('publisher', ''),
            'zotero_version': new_version
        }

        for field, value in fields_to_update.items():
            if value and getattr(paper, field) != value:
                setattr(paper, field, value)
                updated = True

        return updated

    def _extract_year(self, date_string: str) -> Optional[int]:
        """Extract year from Zotero date string."""
        if not date_string:
            return None

        # Try to extract 4-digit year
        import re
        year_match = re.search(r'\b(19|20)\d{2}\b', date_string)
        if year_match:
            return int(year_match.group(0))

        return None

    def _format_author_name(self, creator: Dict) -> str:
        """Format author name from Zotero creator data."""
        if 'name' in creator:
            return creator['name']

        first_name = creator.get('firstName', '')
        last_name = creator.get('lastName', '')

        if first_name and last_name:
            return f"{first_name} {last_name}"
        elif last_name:
            return last_name
        elif first_name:
            return first_name

        return ""

    def get_collections(self) -> List[Dict]:
        """Get collections from Zotero web API."""
        if not self.client:
            raise ValueError("Zotero web API client required")

        try:
            collections = self.client.collections()
            return collections
        except Exception as e:
            logger.error(f"Failed to get Zotero collections: {e}")
            raise

    def is_api_available(self) -> bool:
        """Check if Zotero web API is available (required for sync)."""
        return self.client is not None

    def is_local_api_available(self) -> bool:
        """Check if Zotero is running locally (connector API)."""
        return self.local_api.is_available()

    def get_api_info(self) -> Dict[str, Any]:
        """
        Get information about available APIs.

        Note: The local connector API can only detect if Zotero is running.
        The web API is required for reading/writing items.
        """
        local_available = self.local_api.is_available()
        web_available = self.client is not None

        return {
            'local_api': local_available,
            'local_api_note': 'Zotero is running' if local_available else 'Zotero not detected',
            'web_api': web_available,
            'can_sync': web_available,  # Web API required for sync
            'preferred': 'web'  # Web API is always used for sync
        }

    # =========================================================================
    # PUSH TO ZOTERO (Database → Zotero)
    # =========================================================================

    def sync_to_zotero(self, enrich_only: bool = True) -> Dict[str, int]:
        """
        Sync papers from database to Zotero.

        Args:
            enrich_only: If True, only fill empty fields in Zotero (non-destructive).
                        If False, also create new items in Zotero for database-only papers.

        Returns:
            Dict with counts: {'created': n, 'updated': n, 'skipped': n, 'errors': n}
        """
        if not self.client:
            raise ValueError("Web API client required for push operations. Configure API key.")

        logger.info(f"Starting sync to Zotero (enrich_only={enrich_only})")

        results = {'created': 0, 'updated': 0, 'skipped': 0, 'errors': 0}

        with get_session() as session:
            try:
                # Get all papers from database
                papers = session.query(Paper).all()
                logger.info(f"Found {len(papers)} papers in database")

                for paper in papers:
                    try:
                        if paper.zotero_key:
                            # Paper exists in Zotero - try to enrich
                            updated = self._enrich_zotero_item(paper)
                            if updated:
                                results['updated'] += 1
                            else:
                                results['skipped'] += 1
                        elif not enrich_only:
                            # Paper doesn't exist in Zotero - create it
                            created = self._create_zotero_item(session, paper)
                            if created:
                                results['created'] += 1
                            else:
                                results['skipped'] += 1
                        else:
                            results['skipped'] += 1

                    except Exception as e:
                        logger.error(f"Failed to sync paper {paper.id} '{paper.title[:50]}...': {e}")
                        results['errors'] += 1

                session.commit()

            except Exception as e:
                session.rollback()
                logger.error(f"Sync to Zotero failed: {e}")
                raise

        logger.info(f"Sync to Zotero complete: {results}")
        return results

    def push_paper_to_zotero(self, paper_id: int, create_if_missing: bool = True) -> Dict[str, Any]:
        """
        Push a single paper to Zotero.

        Args:
            paper_id: Database paper ID
            create_if_missing: If True, create new Zotero item if paper doesn't exist there

        Returns:
            Dict with result: {'action': 'created'|'updated'|'skipped', 'zotero_key': str, 'details': str}
        """
        if not self.client:
            raise ValueError("Web API client required for push operations. Configure API key.")

        with get_session() as session:
            try:
                paper = session.query(Paper).filter_by(id=paper_id).first()
                if not paper:
                    return {'action': 'error', 'details': f'Paper {paper_id} not found'}

                if paper.zotero_key:
                    # Try to enrich existing Zotero item
                    updated = self._enrich_zotero_item(paper)
                    session.commit()
                    if updated:
                        return {
                            'action': 'updated',
                            'zotero_key': paper.zotero_key,
                            'details': 'Enriched with database metadata'
                        }
                    else:
                        return {
                            'action': 'skipped',
                            'zotero_key': paper.zotero_key,
                            'details': 'Zotero item already complete'
                        }
                elif create_if_missing:
                    # Create new Zotero item
                    created = self._create_zotero_item(session, paper)
                    session.commit()
                    if created:
                        return {
                            'action': 'created',
                            'zotero_key': paper.zotero_key,
                            'details': 'New item created in Zotero'
                        }
                    else:
                        return {
                            'action': 'error',
                            'details': 'Failed to create Zotero item'
                        }
                else:
                    return {
                        'action': 'skipped',
                        'details': 'Paper not in Zotero and create_if_missing=False'
                    }

            except Exception as e:
                session.rollback()
                logger.error(f"Failed to push paper {paper_id}: {e}")
                return {'action': 'error', 'details': str(e)}

    def _create_zotero_item(self, session, paper: Paper) -> bool:
        """
        Create a new item in Zotero from database paper.

        Returns:
            True if created successfully
        """
        try:
            # Build Zotero item template
            item_data = self._build_zotero_item(session, paper)

            # Create item via API
            response = self.client.create_items([item_data])

            if response and 'successful' in response:
                # Get the created item key
                created = response.get('successful', {})
                if created:
                    # pyzotero returns {'0': {'key': 'ABC123', ...}}
                    first_key = list(created.keys())[0]
                    zotero_key = created[first_key].get('key')
                    zotero_version = created[first_key].get('version', 0)

                    # Update paper with Zotero key
                    paper.zotero_key = zotero_key
                    paper.zotero_version = zotero_version

                    logger.info(f"Created Zotero item {zotero_key} for paper '{paper.title[:50]}...'")
                    return True

            logger.warning(f"Zotero create returned unexpected response: {response}")
            return False

        except Exception as e:
            logger.error(f"Failed to create Zotero item: {e}")
            return False

    def _enrich_zotero_item(self, paper: Paper) -> bool:
        """
        Enrich existing Zotero item with database data (non-destructive).

        Only fills in fields that are empty in Zotero but have values in database.

        Returns:
            True if item was updated
        """
        try:
            # Get current Zotero item
            zotero_item = self.client.item(paper.zotero_key)
            if not zotero_item:
                logger.warning(f"Zotero item {paper.zotero_key} not found")
                return False

            data = zotero_item.get('data', {})
            updates = {}

            # Non-destructive enrichment: only fill empty fields
            enrichment_map = {
                'abstractNote': paper.abstract,
                'DOI': paper.doi,
                'volume': paper.volume,
                'issue': paper.issue,
                'pages': paper.pages,
                'publisher': paper.publisher,
            }

            for zotero_field, db_value in enrichment_map.items():
                zotero_value = data.get(zotero_field, '').strip()
                if not zotero_value and db_value:
                    updates[zotero_field] = db_value

            # Enrich tags (add new ones, don't remove existing)
            if paper.tags:
                existing_tags = {t.get('tag', '').lower() for t in data.get('tags', [])}
                new_tags = []
                for tag in paper.tags:
                    if tag.name.lower() not in existing_tags:
                        new_tags.append({'tag': tag.name})

                if new_tags:
                    updates['tags'] = data.get('tags', []) + new_tags

            if updates:
                # Update the item
                data.update(updates)
                zotero_item['data'] = data
                self.client.update_item(zotero_item)
                logger.info(f"Enriched Zotero item {paper.zotero_key} with: {list(updates.keys())}")
                return True

            return False

        except Exception as e:
            logger.error(f"Failed to enrich Zotero item {paper.zotero_key}: {e}")
            return False

    def _build_zotero_item(self, session, paper: Paper) -> Dict[str, Any]:
        """Build Zotero item data from database Paper."""
        # Determine item type based on available data
        item_type = 'journalArticle'
        if paper.arxiv_id:
            item_type = 'preprint'

        # Get ordered authors
        from sqlalchemy import select
        stmt = select(Author, paper_authors.c.position).join(
            paper_authors, Author.id == paper_authors.c.author_id
        ).where(paper_authors.c.paper_id == paper.id).order_by(paper_authors.c.position)

        authors_result = session.execute(stmt).fetchall()

        creators = []
        for author, _position in authors_result:
            # Try to split name into first/last
            name_parts = author.name.rsplit(' ', 1)
            if len(name_parts) == 2:
                creators.append({
                    'creatorType': 'author',
                    'firstName': name_parts[0],
                    'lastName': name_parts[1]
                })
            else:
                creators.append({
                    'creatorType': 'author',
                    'name': author.name
                })

        # Build item template
        item = {
            'itemType': item_type,
            'title': paper.title or '',
            'abstractNote': paper.abstract or '',
            'date': str(paper.year) if paper.year else '',
            'DOI': paper.doi or '',
            'publicationTitle': paper.journal or '',
            'volume': paper.volume or '',
            'issue': paper.issue or '',
            'pages': paper.pages or '',
            'publisher': paper.publisher or '',
            'creators': creators,
            'tags': [{'tag': tag.name} for tag in paper.tags] if paper.tags else [],
        }

        # Add arXiv ID if present
        if paper.arxiv_id:
            item['archiveID'] = f"arXiv:{paper.arxiv_id}"
            item['url'] = f"https://arxiv.org/abs/{paper.arxiv_id}"

        return item

    def push_pdf_to_zotero(self, paper_id: int) -> Dict[str, Any]:
        """
        Upload PDF attachment to Zotero for a paper.

        Args:
            paper_id: Database paper ID

        Returns:
            Dict with result info
        """
        if not self.client:
            raise ValueError("Web API client required for push operations. Configure API key.")

        with get_session() as session:
            paper = session.query(Paper).filter_by(id=paper_id).first()
            if not paper:
                return {'success': False, 'error': f'Paper {paper_id} not found'}

            if not paper.zotero_key:
                return {'success': False, 'error': 'Paper not in Zotero. Push paper first.'}

            if not paper.file_path:
                return {'success': False, 'error': 'Paper has no PDF file'}

            file_path = Path(paper.file_path)
            if not file_path.exists():
                return {'success': False, 'error': f'PDF file not found: {file_path}'}

            # Upload as child attachment
            try:
                self.client.attachment_simple([str(file_path)], paper.zotero_key)
                logger.info(f"Uploaded PDF to Zotero item {paper.zotero_key}")
                return {'success': True, 'zotero_key': paper.zotero_key}
            except Exception as e:
                return {'success': False, 'error': f'Upload failed: {e}'}

    def get_sync_status(self) -> Dict[str, Any]:
        """
        Get sync status comparing database and Zotero.

        Returns:
            Dict with counts and lists of papers in various states
        """
        with get_session() as session:
            # Papers linked to Zotero
            linked = session.query(Paper).filter(Paper.zotero_key.isnot(None)).count()

            # Papers not in Zotero
            db_only = session.query(Paper).filter(Paper.zotero_key.is_(None)).count()

            # Papers that could enrich Zotero (have data Zotero might be missing)
            enrichable = session.query(Paper).filter(
                Paper.zotero_key.isnot(None),
                (Paper.abstract.isnot(None)) | (Paper.doi.isnot(None))
            ).count()

            return {
                'total_papers': linked + db_only,
                'linked_to_zotero': linked,
                'database_only': db_only,
                'potentially_enrichable': enrichable,
                'api_available': {
                    'local': self.local_api.is_available(),
                    'web': self.client is not None
                }
            }
