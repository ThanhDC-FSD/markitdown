"""Document converter using MarkItDown."""

import os
import sys
from pathlib import Path
from typing import Union, Optional
import logging

logger = logging.getLogger(__name__)

# Try to import MarkItDown, with fallback for alpha versions
try:
    from markitdown import MarkItDown
except ImportError:
    # Older alpha installs may not export MarkItDown from package root.
    MarkItDown = None
    package_src = Path(__file__).resolve().parents[3] / "packages" / "markitdown" / "src"
    if package_src.exists():
        sys.path.insert(0, str(package_src))
        sys.modules.pop("markitdown", None)
        try:
            from markitdown import MarkItDown
        except ImportError:
            MarkItDown = None
    if MarkItDown is None:
        logger.warning("MarkItDown not found in markitdown module, will use fallback")


class DocumentConverter:
    """Wrapper around MarkItDown for document to Markdown conversion."""

    def __init__(self):
        """Initialize the MarkItDown converter."""
        if MarkItDown is None:
            logger.warning("MarkItDown class not available, document conversion will be limited")
            self.converter = None
        else:
            self.converter = MarkItDown()

    def convert_file(self, file_path: Union[str, Path]) -> Optional[str]:
        """
        Convert a local file to Markdown.

        Args:
            file_path: Path to the file (str or Path object)

        Returns:
            Markdown content as string, or None if conversion failed
        """
        if self.converter is None:
            # Fallback: read file as text
            try:
                file_path = str(file_path)
                if not os.path.exists(file_path):
                    logger.error(f"File not found: {file_path}")
                    return None
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    return f.read()
            except Exception as e:
                logger.error(f"Error reading file {file_path}: {e}")
                return None
        
        try:
            file_path = str(file_path)
            if not os.path.exists(file_path):
                logger.error(f"File not found: {file_path}")
                return None

            result = self.converter.convert(file_path)
            return result.markdown
        except Exception as e:
            logger.error(f"Error converting file {file_path}: {e}")
            return None

    def convert_url(self, url: str) -> Optional[str]:
        """
        Convert a URL to Markdown.

        Args:
            url: URL to convert

        Returns:
            Markdown content as string, or None if conversion failed
        """
        if self.converter is None:
            logger.warning(f"MarkItDown converter not available, cannot convert URL {url}")
            return None
        
        try:
            result = self.converter.convert_uri(url)
            return result.markdown
        except Exception as e:
            logger.error(f"Error converting URL {url}: {e}")
            return None

    def convert_text(self, text: str, mimetype: str = "text/plain") -> str:
        """
        Convert plain text (returns as-is).

        Args:
            text: Plain text content
            mimetype: MIME type (default: text/plain)

        Returns:
            The text content
        """
        return text
