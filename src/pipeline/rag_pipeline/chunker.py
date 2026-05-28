"""Text chunking utilities for document splitting."""

from typing import List
import re


class TextChunker:
    """Split documents into overlapping chunks for embedding and retrieval."""

    def __init__(self, chunk_size: int = 512, overlap: int = 64):
        """
        Initialize the text chunker.

        Args:
            chunk_size: Maximum size of each chunk in characters
            overlap: Number of characters to overlap between consecutive chunks
        """
        self.chunk_size = chunk_size
        self.overlap = overlap

    def chunk_by_sentences(self, text: str) -> List[str]:
        """
        Split text into chunks by sentence boundaries.

        Args:
            text: Input text to chunk

        Returns:
            List of text chunks
        """
        if not text or len(text.strip()) == 0:
            return []

        # Split by sentence-like boundaries (., !, ?, or newline)
        sentences = re.split(r'(?<=[.!?])\s+|(?=\n)', text)
        sentences = [s.strip() for s in sentences if s.strip()]

        chunks = []
        current_chunk = []
        current_size = 0

        for sentence in sentences:
            sentence_size = len(sentence)

            # If adding this sentence would exceed chunk_size, save current chunk
            if current_size + len(' '.join(current_chunk + [sentence])) > self.chunk_size and current_chunk:
                chunk_text = ' '.join(current_chunk)
                chunks.append(chunk_text)
                current_chunk = []
                current_size = 0

            current_chunk.append(sentence)
            current_size += sentence_size + 1  # +1 for space

        # Add the last chunk
        if current_chunk:
            chunks.append(' '.join(current_chunk))

        return chunks

    def chunk_with_overlap(self, text: str) -> List[str]:
        """
        Split text into fixed-size chunks with overlap.

        Args:
            text: Input text to chunk

        Returns:
            List of overlapping text chunks
        """
        if not text or len(text.strip()) == 0:
            return []

        chunks = []
        start = 0

        while start < len(text):
            end = min(start + self.chunk_size, len(text))
            chunk = text[start:end].strip()

            if chunk:
                chunks.append(chunk)

            # Move start by chunk_size - overlap
            start += self.chunk_size - self.overlap

            # Prevent infinite loop for very small overlaps
            if start == end:
                break

        return chunks

    def chunk(self, text: str, method: str = "sentences") -> List[str]:
        """
        Chunk text using the specified method.

        Args:
            text: Input text to chunk
            method: Chunking method ('sentences' or 'overlap')

        Returns:
            List of text chunks
        """
        if method == "overlap":
            return self.chunk_with_overlap(text)
        else:
            return self.chunk_by_sentences(text)
