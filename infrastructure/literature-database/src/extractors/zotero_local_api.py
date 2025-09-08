"""Zotero Local API integration for direct communication with running Zotero instance."""
import requests
from typing import Dict, List, Optional, Tuple
from pathlib import Path
import json
from loguru import logger

from src.database import get_session
from src.models import Paper, Author, Collection, Tag


class ZoteroLocalAPI:
    """Handle Zotero integration via local API server."""
    
    def __init__(self, base_url: Optional[str] = None):
        """
        Initialize Zotero local API client.
        
        Args:
            base_url: Base URL for Zotero local API server (auto-detects Windows host in WSL2)
        """
        self.base_url = self._determine_base_url(base_url)
        self.session = requests.Session()
        self.session.headers.update({
            'Content-Type': 'application/json',
            'User-Agent': 'Literature-Database/1.0'
        })
    
    def _determine_base_url(self, provided_url: Optional[str]) -> str:
        """Determine the correct base URL for Zotero API with fallback testing."""
        if provided_url:
            return provided_url.rstrip('/')
        
        # Try multiple URLs in order of preference
        candidate_urls = []
        
        # Check if we're in WSL2
        import subprocess
        import os
        
        try:
            # Check if we're in WSL
            if os.path.exists('/proc/version'):
                with open('/proc/version', 'r') as f:
                    proc_version = f.read().lower()
                    if 'microsoft' in proc_version or 'wsl' in proc_version:
                        logger.info("Detected WSL2 environment")
                        
                        # Method 1: Try localhost first (mirrored networking)
                        candidate_urls.append("http://localhost:23119/api")
                        
                        # Method 2: Try mDNS hostname.local
                        try:
                            hostname_result = subprocess.run(['hostname'], 
                                                           capture_output=True, text=True, timeout=3)
                            if hostname_result.returncode == 0:
                                hostname = hostname_result.stdout.strip()
                                candidate_urls.append(f"http://{hostname}.local:23119/api")
                        except:
                            pass
                        
                        # Method 3: Try Windows host IP
                        try:
                            result = subprocess.run(['ip', 'route', 'show', 'default'], 
                                                  capture_output=True, text=True, timeout=5)
                            if result.returncode == 0:
                                import re
                                match = re.search(r'default via (\d+\.\d+\.\d+\.\d+)', result.stdout)
                                if match:
                                    windows_ip = match.group(1)
                                    candidate_urls.append(f"http://{windows_ip}:23119/api")
                        except Exception as e:
                            logger.debug(f"Failed to get Windows host IP: {e}")
        except Exception:
            pass
        
        # Default fallback
        if not candidate_urls:
            candidate_urls = ["http://localhost:23119/api"]
        
        # Test each URL and return the first working one
        for url in candidate_urls:
            if self._test_url_connectivity(url):
                logger.info(f"Using working Zotero API URL: {url}")
                return url
            else:
                logger.debug(f"URL not accessible: {url}")
        
        # If none work, return the first one and let normal error handling deal with it
        logger.warning(f"No working URLs found, defaulting to: {candidate_urls[0]}")
        return candidate_urls[0]
    
    def _test_url_connectivity(self, url: str) -> bool:
        """Test if a URL is accessible."""
        try:
            import requests
            response = requests.get(url, timeout=2)
            return response.status_code == 200
        except:
            return False
    
    def is_available(self) -> bool:
        """Check if Zotero local API is available."""
        try:
            response = self.session.get(f"{self.base_url}/", timeout=5)
            return response.status_code == 200
        except requests.RequestException:
            return False
    
    def get_library_info(self) -> Optional[Dict]:
        """Get information about the Zotero library."""
        try:
            response = self.session.get(f"{self.base_url}/library", timeout=10)
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Failed to get library info: {response.status_code}")
                return None
        except requests.RequestException as e:
            logger.error(f"Error getting library info: {e}")
            return None
    
    def get_items(self, limit: Optional[int] = None, start: int = 0) -> List[Dict]:
        """
        Get items from Zotero library.
        
        Args:
            limit: Maximum number of items to retrieve
            start: Starting index
            
        Returns:
            List of Zotero items
        """
        try:
            params = {'start': start}
            if limit:
                params['limit'] = limit
            
            response = self.session.get(f"{self.base_url}/users/0/items", params=params, timeout=30)
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Failed to get items: {response.status_code}")
                return []
        except requests.RequestException as e:
            logger.error(f"Error getting items: {e}")
            return []
    
    def get_item(self, item_key: str) -> Optional[Dict]:
        """Get a specific item by key."""
        try:
            response = self.session.get(f"{self.base_url}/users/0/items/{item_key}", timeout=10)
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Failed to get item {item_key}: {response.status_code}")
                return None
        except requests.RequestException as e:
            logger.error(f"Error getting item {item_key}: {e}")
            return None
    
    def get_collections(self) -> List[Dict]:
        """Get all collections from Zotero library."""
        try:
            response = self.session.get(f"{self.base_url}/users/0/collections", timeout=30)
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Failed to get collections: {response.status_code}")
                return []
        except requests.RequestException as e:
            logger.error(f"Error getting collections: {e}")
            return []
    
    def get_collection_items(self, collection_key: str) -> List[Dict]:
        """Get items from a specific collection."""
        try:
            response = self.session.get(
                f"{self.base_url}/collections/{collection_key}/items", 
                timeout=30
            )
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Failed to get collection items: {response.status_code}")
                return []
        except requests.RequestException as e:
            logger.error(f"Error getting collection items: {e}")
            return []
    
    def get_item_attachments(self, item_key: str) -> List[Dict]:
        """Get attachments for a specific item."""
        try:
            response = self.session.get(
                f"{self.base_url}/items/{item_key}/children",
                timeout=10
            )
            if response.status_code == 200:
                children = response.json()
                # Filter for attachments
                return [child for child in children if child.get('itemType') == 'attachment']
            else:
                logger.error(f"Failed to get attachments: {response.status_code}")
                return []
        except requests.RequestException as e:
            logger.error(f"Error getting attachments: {e}")
            return []
    
    def sync_to_database(self) -> Tuple[int, int]:
        """
        Sync Zotero items to the literature database.
        
        Returns:
            Tuple of (papers_added, papers_updated)
        """
        if not self.is_available():
            raise ConnectionError("Zotero local API is not available. Make sure Zotero is running.")
        
        logger.info("Starting sync from Zotero local API...")
        
        # Get all items
        items = self.get_items()
        logger.info(f"Found {len(items)} items in Zotero library")
        
        papers_added = 0
        papers_updated = 0
        
        db_session = next(get_session())
        
        try:
            for item in items:
                if self._is_paper_item(item):
                    added, updated = self._sync_paper_item(db_session, item)
                    if added:
                        papers_added += 1
                    if updated:
                        papers_updated += 1
            
            db_session.commit()
            logger.info(f"Sync complete: {papers_added} added, {papers_updated} updated")
            
        except Exception as e:
            db_session.rollback()
            logger.error(f"Sync failed: {e}")
            raise
        finally:
            db_session.close()
        
        return papers_added, papers_updated
    
    def _is_paper_item(self, item: Dict) -> bool:
        """Check if item is a paper/article."""
        data = item.get('data', {})
        item_type = data.get('itemType', '')
        return item_type in [
            'journalArticle', 'preprint', 'conferencePaper', 
            'report', 'thesis', 'book', 'bookSection'
        ]
    
    def _sync_paper_item(self, db_session, item: Dict) -> Tuple[bool, bool]:
        """
        Sync a single paper item.
        
        Returns:
            Tuple of (was_added, was_updated)
        """
        item_key = item.get('key', '')
        
        # Check if paper already exists
        existing_paper = db_session.query(Paper).filter_by(zotero_key=item_key).first()
        
        if existing_paper:
            # Update existing paper
            updated = self._update_paper_from_zotero(db_session, existing_paper, item)
            return False, updated
        else:
            # Create new paper
            paper = self._create_paper_from_zotero(db_session, item, item_key)
            db_session.add(paper)
            return True, False
    
    def _create_paper_from_zotero(self, db_session, item: Dict, item_key: str) -> Paper:
        """Create a new Paper object from Zotero item."""
        
        # Get data from nested structure
        data = item.get('data', {})
        
        # Extract basic fields
        title = data.get('title', '')
        abstract = data.get('abstractNote', '')
        
        # Handle date - Zotero can have various date formats
        year = self._extract_year(data.get('date', ''))
        
        # Create paper
        doi = data.get('DOI', '').strip()
        paper = Paper(
            title=title,
            abstract=abstract,
            year=year,
            doi=doi if doi else None,  # Convert empty string to None for unique constraint
            journal=data.get('publicationTitle', ''),
            volume=data.get('volume', ''),
            issue=data.get('issue', ''),
            pages=data.get('pages', ''),
            publisher=data.get('publisher', ''),
            zotero_key=item_key,
            zotero_version=item.get('version', 0)
        )
        
        # Add authors
        creators = data.get('creators', [])
        for creator in creators:
            if creator.get('creatorType') in ['author', 'editor']:
                author_name = self._format_creator_name(creator)
                if author_name:
                    author = self._get_or_create_author(db_session, author_name)
                    paper.authors.append(author)
        
        # Add tags
        zotero_tags = data.get('tags', [])
        for tag_data in zotero_tags:
            tag_name = tag_data.get('tag', '').strip()
            if tag_name:
                tag = self._get_or_create_tag(db_session, tag_name)
                paper.tags.append(tag)
        
        return paper
    
    def _update_paper_from_zotero(self, db_session, paper: Paper, item: Dict) -> bool:
        """Update existing paper with Zotero data."""
        updated = False
        
        # Check version
        new_version = item.get('version', 0)
        if new_version <= paper.zotero_version:
            return False
        
        # Update basic fields
        fields_to_update = {
            'title': item.get('title', ''),
            'abstract': item.get('abstractNote', ''),
            'year': self._extract_year(item.get('date', '')),
            'doi': item.get('DOI', ''),
            'journal': item.get('publicationTitle', ''),
            'volume': item.get('volume', ''),
            'issue': item.get('issue', ''),
            'pages': item.get('pages', ''),
            'publisher': item.get('publisher', ''),
            'zotero_version': new_version
        }
        
        for field, value in fields_to_update.items():
            if value and getattr(paper, field) != value:
                setattr(paper, field, value)
                updated = True
        
        return updated
    
    def _extract_year(self, date_string: str) -> Optional[int]:
        """Extract year from date string."""
        if not date_string:
            return None
        
        import re
        year_match = re.search(r'\b(19|20)\d{2}\b', str(date_string))
        if year_match:
            return int(year_match.group(0))
        
        return None
    
    def _format_creator_name(self, creator: Dict) -> str:
        """Format creator name from Zotero data."""
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
    
    def _get_or_create_author(self, db_session, name: str) -> Author:
        """Get existing author or create new one."""
        author = db_session.query(Author).filter(Author.name == name).first()
        if not author:
            author = Author(name=name)
            db_session.add(author)
            db_session.flush()  # Flush to avoid duplicate key errors
        return author
    
    def _get_or_create_tag(self, db_session, name: str) -> Tag:
        """Get existing tag or create new one."""
        tag = db_session.query(Tag).filter(Tag.name == name).first()
        if not tag:
            tag = Tag(name=name)
            db_session.add(tag)
            db_session.flush()  # Flush to avoid duplicate key errors
        return tag
    
    def _get_or_create_collection(self, db_session, name: str) -> Collection:
        """Get existing collection or create new one."""
        collection = db_session.query(Collection).filter(Collection.name == name).first()
        if not collection:
            collection = Collection(name=name)
            db_session.add(collection)
        return collection