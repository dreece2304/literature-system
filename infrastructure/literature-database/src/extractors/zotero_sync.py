"""Zotero integration for syncing papers and collections."""
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from pyzotero import zotero
import yaml
from loguru import logger

from src.database import get_session
from src.models import Paper, Author, Collection, Tag
from src.extractors.zotero_local_api import ZoteroLocalAPI


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
        # Load main settings
        settings_path = config_path or os.getenv('LITDB_CONFIG_PATH', 'config/settings.yml')
        with open(settings_path, 'r') as f:
            config = yaml.safe_load(f)
        
        # Load credentials
        try:
            with open('config/credentials.yml', 'r') as f:
                credentials = yaml.safe_load(f)
                config['zotero']['api_key'] = credentials.get('zotero', {}).get('api_key', '')
        except FileNotFoundError:
            logger.warning("credentials.yml not found - API sync will be unavailable")
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
        Sync papers from Zotero API (local first, then web API).
        
        Returns:
            Tuple of (papers_added, papers_updated)
        """
        # Try local API first
        if self.local_api.is_available():
            logger.info("Using Zotero local API (localhost:23119)")
            return self.local_api.sync_to_database()
        
        # Fall back to web API
        if not self.client:
            raise ValueError("Neither local API nor web API client available")
        
        logger.info("Using Zotero web API (fallback)")
        papers_added = 0
        papers_updated = 0
        
        try:
            # Get all items from Zotero
            logger.info("Fetching items from Zotero web API...")
            items = self.client.items()
            
            session = next(get_session())
            
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
            session.close()
            
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
        
        # Check if paper already exists
        existing_paper = session.query(Paper).filter_by(zotero_key=zotero_key).first()
        
        if existing_paper:
            # Update existing paper
            updated = self._update_paper_from_zotero(existing_paper, data)
            return False, updated
        else:
            # Create new paper
            paper = self._create_paper_from_zotero(session, data, zotero_key)
            session.add(paper)
            return True, False
    
    def _create_paper_from_zotero(self, session, data: Dict, zotero_key: str) -> Paper:
        """Create a new Paper object from Zotero data."""
        paper = Paper(
            title=data.get('title', ''),
            abstract=data.get('abstractNote', ''),
            year=self._extract_year(data.get('date', '')),
            doi=data.get('DOI', ''),
            journal=data.get('publicationTitle', ''),
            volume=data.get('volume', ''),
            issue=data.get('issue', ''),
            pages=data.get('pages', ''),
            publisher=data.get('publisher', ''),
            zotero_key=zotero_key,
            zotero_version=data.get('version', 0)
        )
        
        # Add authors
        creators = data.get('creators', [])
        for creator in creators:
            if creator.get('creatorType') == 'author':
                author_name = self._format_author_name(creator)
                if author_name:
                    # Find or create author
                    author = session.query(Author).filter_by(name=author_name).first()
                    if not author:
                        author = Author(name=author_name)
                        session.add(author)
                    paper.authors.append(author)
        
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
        """Get collections from Zotero (local API first, then web API)."""
        # Try local API first
        if self.local_api.is_available():
            return self.local_api.get_collections()
        
        # Fall back to web API
        if not self.client:
            raise ValueError("Neither local API nor web API client available")
        
        try:
            collections = self.client.collections()
            return collections
        except Exception as e:
            logger.error(f"Failed to get Zotero collections: {e}")
            raise
    
    def is_api_available(self) -> bool:
        """Check if any Zotero API is available (local preferred)."""
        return self.local_api.is_available() or self.client is not None
    
    def is_local_api_available(self) -> bool:
        """Check if Zotero local API is available."""
        return self.local_api.is_available()
    
    def get_api_info(self) -> Dict[str, bool]:
        """Get information about available APIs."""
        return {
            'local_api': self.local_api.is_available(),
            'web_api': self.client is not None,
            'preferred': 'local' if self.local_api.is_available() else 'web'
        }