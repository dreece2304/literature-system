"""Path management utilities for the literature database."""
import os
import yaml
from pathlib import Path
from typing import Dict, Optional
from loguru import logger


class PathManager:
    """Manage paths and directories for the literature database."""
    
    def __init__(self, config_path: Optional[str] = None):
        """Initialize with configuration."""
        self.config = self._load_config(config_path)
        self._ensure_directories()
    
    def _load_config(self, config_path: Optional[str] = None) -> Dict:
        """Load configuration file."""
        if config_path is None:
            config_path = os.getenv('LITDB_CONFIG_PATH', 'config/settings.yml')
        
        try:
            with open(config_path, 'r') as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            logger.warning(f"Configuration file not found: {config_path}")
            return self._get_default_config()
    
    def _get_default_config(self) -> Dict:
        """Get default configuration."""
        return {
            'pdf': {'storage_path': 'data/pdfs'},
            'database': {'path': 'data/metadata/literature.db'},
            'search': {'index_path': 'data/cache/search_index'},
            'logging': {'file': 'logs/litdb.log'},
            'zotero': {'windows_path': '/mnt/c/Users/dreec/Zotero'}
        }
    
    def _ensure_directories(self):
        """Ensure all required directories exist."""
        required_dirs = [
            self.get_pdf_storage_path(),
            self.get_database_path().parent,
            self.get_search_index_path(),
            self.get_log_path().parent,
            Path('data/cache'),
            Path('data/zotero_sync'),
            Path('temp'),
            Path('notebooks'),
            Path('scripts'),
            Path('tests')
        ]
        
        for directory in required_dirs:
            try:
                directory.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                logger.error(f"Failed to create directory {directory}: {e}")
    
    def get_pdf_storage_path(self) -> Path:
        """Get PDF storage directory path."""
        return Path(self.config.get('pdf', {}).get('storage_path', 'data/pdfs'))
    
    def get_database_path(self) -> Path:
        """Get database file path."""
        return Path(self.config.get('database', {}).get('path', 'data/metadata/literature.db'))
    
    def get_search_index_path(self) -> Path:
        """Get search index directory path."""
        return Path(self.config.get('search', {}).get('index_path', 'data/cache/search_index'))
    
    def get_log_path(self) -> Path:
        """Get log file path."""
        return Path(self.config.get('logging', {}).get('file', 'logs/litdb.log'))
    
    def get_zotero_path(self) -> Path:
        """Get Zotero library path."""
        return Path(self.config.get('zotero', {}).get('windows_path', '/mnt/c/Users/dreec/Zotero'))
    
    def get_cache_path(self) -> Path:
        """Get cache directory path."""
        return Path('data/cache')
    
    def get_temp_path(self) -> Path:
        """Get temporary directory path."""
        return Path('temp')
    
    def get_zotero_sync_path(self) -> Path:
        """Get Zotero sync directory path."""
        return Path('data/zotero_sync')
    
    def generate_pdf_path(self, filename: str, year: Optional[int] = None) -> Path:
        """
        Generate organized PDF storage path.
        
        Args:
            filename: Original filename
            year: Publication year for organization
            
        Returns:
            Full path for PDF storage
        """
        base_path = self.get_pdf_storage_path()
        
        # Clean filename
        from src.utils.file_utils import clean_filename
        clean_name = clean_filename(filename)
        
        if year:
            # Organize by year
            return base_path / str(year) / clean_name
        else:
            # Store in unsorted directory
            return base_path / 'unsorted' / clean_name
    
    def get_relative_path(self, absolute_path: Path, relative_to: Optional[Path] = None) -> Path:
        """
        Get relative path from absolute path.
        
        Args:
            absolute_path: Absolute path to convert
            relative_to: Base path (defaults to project root)
            
        Returns:
            Relative path
        """
        if relative_to is None:
            relative_to = Path.cwd()
        
        try:
            return absolute_path.relative_to(relative_to)
        except ValueError:
            # If paths are on different drives/roots, return absolute path
            return absolute_path
    
    def resolve_path(self, path_str: str) -> Path:
        """
        Resolve path string to absolute Path object.
        
        Args:
            path_str: Path string (may be relative)
            
        Returns:
            Absolute Path object
        """
        path = Path(path_str)
        
        if path.is_absolute():
            return path
        else:
            return Path.cwd() / path
    
    def get_backup_path(self, original_path: Path) -> Path:
        """
        Generate backup path for a file.
        
        Args:
            original_path: Original file path
            
        Returns:
            Backup file path with timestamp
        """
        from datetime import datetime
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"{original_path.stem}_{timestamp}{original_path.suffix}"
        
        return original_path.parent / 'backups' / backup_name
    
    def cleanup_temp_files(self, older_than_hours: int = 24):
        """
        Clean up temporary files older than specified hours.
        
        Args:
            older_than_hours: Remove files older than this many hours
        """
        import time
        
        temp_path = self.get_temp_path()
        if not temp_path.exists():
            return
        
        current_time = time.time()
        cutoff_time = current_time - (older_than_hours * 3600)
        
        cleaned_count = 0
        
        try:
            for file_path in temp_path.rglob('*'):
                if file_path.is_file():
                    file_mtime = file_path.stat().st_mtime
                    if file_mtime < cutoff_time:
                        file_path.unlink()
                        cleaned_count += 1
            
            logger.info(f"Cleaned up {cleaned_count} temporary files older than {older_than_hours} hours")
            
        except Exception as e:
            logger.error(f"Failed to cleanup temp files: {e}")
    
    def get_disk_usage(self) -> Dict[str, Dict[str, float]]:
        """
        Get disk usage statistics for main directories.
        
        Returns:
            Dictionary with directory names and their sizes
        """
        import shutil
        
        directories = {
            'pdfs': self.get_pdf_storage_path(),
            'cache': self.get_cache_path(),
            'logs': self.get_log_path().parent,
            'temp': self.get_temp_path(),
            'total': Path.cwd()
        }
        
        usage = {}
        
        for name, path in directories.items():
            try:
                if path.exists():
                    if path.is_file():
                        size_bytes = path.stat().st_size
                    else:
                        size_bytes = sum(f.stat().st_size for f in path.rglob('*') if f.is_file())
                    
                    # Convert to MB
                    size_mb = size_bytes / (1024 * 1024)
                    
                    # Get available space for directories
                    if path.is_dir():
                        _, _, free_bytes = shutil.disk_usage(path)
                        free_mb = free_bytes / (1024 * 1024)
                    else:
                        free_mb = 0
                    
                    usage[name] = {
                        'used_mb': round(size_mb, 2),
                        'free_mb': round(free_mb, 2)
                    }
                else:
                    usage[name] = {'used_mb': 0, 'free_mb': 0}
                    
            except Exception as e:
                logger.error(f"Failed to get disk usage for {name}: {e}")
                usage[name] = {'used_mb': 0, 'free_mb': 0, 'error': str(e)}
        
        return usage