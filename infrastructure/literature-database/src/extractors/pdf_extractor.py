"""PDF text extraction and metadata processing."""
import hashlib
from pathlib import Path
from typing import Dict
import pdfplumber
from pypdf import PdfReader
from loguru import logger


class PDFExtractor:
    """Extract text and metadata from PDF files."""

    def __init__(self):
        self.supported_extensions = {'.pdf'}

    def extract(self, file_path: Path) -> Dict:
        """
        Extract text and metadata from PDF file.

        Args:
            file_path: Path to PDF file

        Returns:
            Dict containing extracted data
        """
        if not file_path.exists():
            raise FileNotFoundError(f"PDF file not found: {file_path}")

        if file_path.suffix.lower() not in self.supported_extensions:
            raise ValueError(f"Unsupported file type: {file_path.suffix}")

        try:
            # Extract text using pdfplumber
            full_text = self._extract_text_pdfplumber(file_path)

            # Extract metadata using PyPDF2
            metadata = self._extract_metadata_pypdf2(file_path)

            # Calculate file hash for deduplication
            file_hash = self._calculate_file_hash(file_path)

            return {
                'full_text': full_text,
                'word_count': len(full_text.split()) if full_text else 0,
                'file_hash': file_hash,
                'file_path': str(file_path),
                'metadata': metadata
            }

        except Exception as e:
            logger.error(f"Failed to extract from PDF {file_path}: {e}")
            raise

    def _extract_text_pdfplumber(self, file_path: Path) -> str:
        """Extract text using pdfplumber for better formatting."""
        text_parts = []

        try:
            with pdfplumber.open(file_path) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text_parts.append(page_text)

            return '\n\n'.join(text_parts)

        except Exception as e:
            logger.warning(f"pdfplumber extraction failed for {file_path}: {e}")
            return ""

    def _extract_metadata_pypdf2(self, file_path: Path) -> Dict:
        """Extract metadata using PyPDF2."""
        metadata = {}

        try:
            with open(file_path, 'rb') as file:
                reader = PdfReader(file)

                if reader.metadata:
                    metadata.update({
                        'title': reader.metadata.get('/Title', ''),
                        'author': reader.metadata.get('/Author', ''),
                        'subject': reader.metadata.get('/Subject', ''),
                        'creator': reader.metadata.get('/Creator', ''),
                        'producer': reader.metadata.get('/Producer', ''),
                        'creation_date': reader.metadata.get('/CreationDate', ''),
                        'modification_date': reader.metadata.get('/ModDate', '')
                    })

                metadata['page_count'] = len(reader.pages)

        except Exception as e:
            logger.warning(f"Metadata extraction failed for {file_path}: {e}")

        return metadata

    def _calculate_file_hash(self, file_path: Path) -> str:
        """Calculate SHA256 hash of file for deduplication."""
        hasher = hashlib.sha256()

        try:
            with open(file_path, 'rb') as file:
                for chunk in iter(lambda: file.read(4096), b""):
                    hasher.update(chunk)
            return hasher.hexdigest()

        except Exception as e:
            logger.error(f"Failed to calculate hash for {file_path}: {e}")
            return ""

    def is_supported(self, file_path: Path) -> bool:
        """Check if file type is supported."""
        return file_path.suffix.lower() in self.supported_extensions
