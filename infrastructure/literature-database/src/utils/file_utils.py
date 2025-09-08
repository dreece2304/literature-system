"""File and path utilities for the literature database."""
import hashlib
import shutil
from pathlib import Path
from typing import Optional, List
from loguru import logger


def calculate_file_hash(file_path: Path, algorithm: str = "sha256") -> str:
    """
    Calculate hash of a file.
    
    Args:
        file_path: Path to file
        algorithm: Hash algorithm (sha256, md5, sha1)
        
    Returns:
        Hex digest of file hash
    """
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    
    if algorithm.lower() not in ['sha256', 'md5', 'sha1']:
        raise ValueError(f"Unsupported hash algorithm: {algorithm}")
    
    hasher = getattr(hashlib, algorithm.lower())()
    
    try:
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b""):
                hasher.update(chunk)
        return hasher.hexdigest()
    except Exception as e:
        logger.error(f"Failed to calculate {algorithm} hash for {file_path}: {e}")
        raise


def safe_move_file(source: Path, destination: Path, overwrite: bool = False) -> bool:
    """
    Safely move a file to a new location.
    
    Args:
        source: Source file path
        destination: Destination file path
        overwrite: Whether to overwrite existing file
        
    Returns:
        True if successful, False otherwise
    """
    if not source.exists():
        logger.error(f"Source file does not exist: {source}")
        return False
    
    if destination.exists() and not overwrite:
        logger.error(f"Destination file exists and overwrite=False: {destination}")
        return False
    
    try:
        # Ensure destination directory exists
        destination.parent.mkdir(parents=True, exist_ok=True)
        
        # Move the file
        shutil.move(str(source), str(destination))
        logger.info(f"Moved file: {source} -> {destination}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to move file {source} -> {destination}: {e}")
        return False


def copy_file_with_hash_check(source: Path, destination: Path) -> bool:
    """
    Copy file and verify integrity with hash check.
    
    Args:
        source: Source file path
        destination: Destination file path
        
    Returns:
        True if copy successful and hashes match
    """
    if not source.exists():
        logger.error(f"Source file does not exist: {source}")
        return False
    
    try:
        # Calculate source hash
        source_hash = calculate_file_hash(source)
        
        # Ensure destination directory exists
        destination.parent.mkdir(parents=True, exist_ok=True)
        
        # Copy file
        shutil.copy2(str(source), str(destination))
        
        # Verify copy with hash
        if destination.exists():
            dest_hash = calculate_file_hash(destination)
            if source_hash == dest_hash:
                logger.info(f"File copied successfully with hash verification: {source} -> {destination}")
                return True
            else:
                logger.error(f"Hash mismatch after copy: {source} -> {destination}")
                destination.unlink()  # Remove corrupted copy
                return False
        else:
            logger.error(f"Destination file not found after copy: {destination}")
            return False
            
    except Exception as e:
        logger.error(f"Failed to copy file with hash check {source} -> {destination}: {e}")
        return False


def get_file_size_human(file_path: Path) -> str:
    """
    Get human-readable file size.
    
    Args:
        file_path: Path to file
        
    Returns:
        Human readable size string (e.g., "1.2 MB")
    """
    if not file_path.exists():
        return "File not found"
    
    try:
        size_bytes = file_path.stat().st_size
        
        # Convert to human readable format
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0
        
        return f"{size_bytes:.1f} PB"
        
    except Exception as e:
        logger.error(f"Failed to get file size for {file_path}: {e}")
        return "Unknown"


def find_duplicate_files(directory: Path, by_hash: bool = True) -> List[List[Path]]:
    """
    Find duplicate files in a directory.
    
    Args:
        directory: Directory to search
        by_hash: If True, use file hash; if False, use size and name
        
    Returns:
        List of lists, where each inner list contains duplicate files
    """
    if not directory.exists() or not directory.is_dir():
        logger.error(f"Directory does not exist or is not a directory: {directory}")
        return []
    
    file_groups = {}
    
    try:
        for file_path in directory.rglob('*'):
            if file_path.is_file():
                if by_hash:
                    key = calculate_file_hash(file_path)
                else:
                    key = (file_path.stat().st_size, file_path.name)
                
                if key not in file_groups:
                    file_groups[key] = []
                file_groups[key].append(file_path)
        
        # Return only groups with duplicates
        duplicates = [group for group in file_groups.values() if len(group) > 1]
        
        if duplicates:
            logger.info(f"Found {len(duplicates)} groups of duplicate files in {directory}")
        
        return duplicates
        
    except Exception as e:
        logger.error(f"Failed to find duplicates in {directory}: {e}")
        return []


def clean_filename(filename: str) -> str:
    """
    Clean filename by removing invalid characters.
    
    Args:
        filename: Original filename
        
    Returns:
        Cleaned filename safe for filesystem
    """
    import re
    
    # Replace invalid characters with underscores
    invalid_chars = r'[<>:"/\\|?*]'
    cleaned = re.sub(invalid_chars, '_', filename)
    
    # Remove multiple consecutive underscores
    cleaned = re.sub(r'_{2,}', '_', cleaned)
    
    # Trim whitespace and dots from ends
    cleaned = cleaned.strip(' .')
    
    # Ensure filename is not empty
    if not cleaned:
        cleaned = "unnamed_file"
    
    # Limit length
    if len(cleaned) > 255:
        cleaned = cleaned[:255]
    
    return cleaned


def ensure_directory_exists(directory: Path) -> bool:
    """
    Ensure directory exists, creating if necessary.
    
    Args:
        directory: Directory path to create
        
    Returns:
        True if directory exists or was created successfully
    """
    try:
        directory.mkdir(parents=True, exist_ok=True)
        return True
    except Exception as e:
        logger.error(f"Failed to create directory {directory}: {e}")
        return False