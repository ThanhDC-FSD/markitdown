"""Document converter using MarkItDown."""

import os
from pathlib import Path
from typing import Union, Optional
from markitdown import MarkItDown


class DocumentConverter:
    """Wrapper around MarkItDown for document to Markdown conversion."""

    def __init__(self):
        """Initialize the MarkItDown converter."""
        self.converter = MarkItDown()

    def convert_file(self, file_path: Union[str, Path]) -> Optional[str]:
        """
        Convert a local file to Markdown.

        Args:
            file_path: Path to the file (str or Path object)

        Returns:
            Markdown content as string, or None if conversion failed
        """
        try:
            file_path = str(file_path)
            if not os.path.exists(file_path):
                print(f"File not found: {file_path}")
                return None

            result = self.converter.convert(file_path)
            return result.markdown
        except Exception as e:
            print(f"Error converting file {file_path}: {e}")
            return None

    def convert_url(self, url: str) -> Optional[str]:
        """
        Convert a URL to Markdown.

        Args:
            url: URL to convert

        Returns:
            Markdown content as string, or None if conversion failed
        """
        try:
            result = self.converter.convert_uri(url)
            return result.markdown
        except Exception as e:
            print(f"Error converting URL {url}: {e}")
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
