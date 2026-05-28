"""
Enhanced Semantic Chunker for Production RAG
Chunks by semantic boundaries, not just token size.
Prevents splitting of related content that should stay together.
"""

import re
from typing import List, Tuple, Dict, Any
from dataclasses import dataclass


@dataclass
class SemanticChunk:
    """A semantically coherent chunk with boundary information"""
    text: str
    chunk_id: str
    start_pos: int
    end_pos: int
    chunk_type: str  # "section", "subsection", "definition", "rule", "example", "list"
    hierarchy_level: int
    section_title: str
    subsection_title: str = ""
    parent_chunk_id: str = ""


class SemanticChunker:
    """
    Chunks documents by semantic boundaries, not just size.
    Prioritizes:
    - Keeping rule + exception together
    - Keeping requirement + constraint together
    - Keeping definition + scope together
    - Preserving section hierarchy
    """
    
    def __init__(self, target_size: int = 512, min_size: int = 150, max_size: int = 800):
        self.target_size = target_size
        self.min_size = min_size
        self.max_size = max_size
    
    def identify_chunk_boundaries(self, text: str) -> List[Tuple[int, int, str, int]]:
        """
        Identify semantic boundaries in text.
        Returns list of (start, end, type, hierarchy_level)
        """
        boundaries = []
        
        # Find all section headers
        for match in re.finditer(r'^(#{1,6})\s+(.+)$', text, re.MULTILINE):
            level = len(match.group(1))
            start = match.start()
            boundaries.append((start, match.end(), "section_header", level))
        
        # Find definition markers
        for match in re.finditer(r'^[-*]\s+(?:Definition|Def|NOTE|Note|IMPORTANT):', text, re.MULTILINE):
            boundaries.append((match.start(), match.end(), "definition", 3))
        
        # Find rules/requirements
        for match in re.finditer(r'^[-*]\s+(?:Requirement|Rule|MUST|SHALL|SHOULD):', text, re.MULTILINE):
            boundaries.append((match.start(), match.end(), "requirement", 3))
        
        # Find examples
        for match in re.finditer(r'^(?:Example|EXAMPLE|Example:|Example:)\s*$', text, re.MULTILINE):
            boundaries.append((match.start(), match.end(), "example", 3))
        
        # Find list items
        for match in re.finditer(r'^[-*]\s+', text, re.MULTILINE):
            boundaries.append((match.start(), match.end(), "list_item", 3))
        
        # Sort by position
        boundaries.sort(key=lambda x: x[0])
        
        return boundaries
    
    def is_list_or_bullet_block(self, text: str) -> bool:
        """Check if text is a list or bullet block"""
        lines = text.strip().split('\n')
        bullet_count = sum(1 for line in lines if re.match(r'^[-*]\s+', line))
        return bullet_count / len(lines) > 0.5 if lines else False
    
    def detect_paragraph_boundaries(self, text: str) -> List[int]:
        """Detect paragraph boundaries (double newlines)"""
        boundaries = [0]
        for match in re.finditer(r'\n\n+', text):
            boundaries.append(match.start())
        boundaries.append(len(text))
        return boundaries
    
    def chunk_by_semantic_boundaries(self, text: str) -> List[SemanticChunk]:
        """
        Chunk text respecting semantic boundaries.
        This is the main chunking algorithm.
        """
        chunks = []
        semantic_boundaries = self.identify_chunk_boundaries(text)
        paragraph_boundaries = self.detect_paragraph_boundaries(text)
        
        # Extract current section headers to maintain hierarchy
        section_headers = []
        for match in re.finditer(r'^(#{1,6})\s+(.+)$', text, re.MULTILINE):
            level = len(match.group(1))
            title = match.group(2).strip()
            section_headers.append((match.start(), level, title))
        
        chunk_id = 0
        current_pos = 0
        
        while current_pos < len(text):
            # Get current section context
            current_section = ""
            current_subsection = ""
            current_level = 0
            
            for pos, level, title in section_headers:
                if pos <= current_pos:
                    if level == 1:
                        current_section = title
                    elif level == 2:
                        current_subsection = title
                    current_level = level
                else:
                    break
            
            # Find next natural break point
            next_break = self._find_next_break(
                text, current_pos, semantic_boundaries, paragraph_boundaries
            )
            
            chunk_text = text[current_pos:next_break].strip()
            
            # Skip empty chunks
            if len(chunk_text) < self.min_size:
                current_pos = next_break
                continue
            
            # Cap chunk size
            if len(chunk_text) > self.max_size:
                chunk_text = chunk_text[:self.max_size]
                next_break = current_pos + self.max_size
            
            chunk_type = self._classify_chunk(chunk_text)
            
            chunks.append(SemanticChunk(
                text=chunk_text,
                chunk_id=f"chunk_{chunk_id:04d}",
                start_pos=current_pos,
                end_pos=next_break,
                chunk_type=chunk_type,
                hierarchy_level=current_level,
                section_title=current_section,
                subsection_title=current_subsection,
            ))
            
            current_pos = next_break
            chunk_id += 1
        
        return chunks
    
    def _find_next_break(
        self,
        text: str,
        current_pos: int,
        semantic_boundaries: List[Tuple[int, int, str, int]],
        paragraph_boundaries: List[int]
    ) -> int:
        """Find the next natural break point for chunking"""
        
        # Target end position
        target_end = current_pos + self.target_size
        
        # Find semantic boundaries near target
        semantic_breaks = [
            pos[1] for pos in semantic_boundaries
            if current_pos < pos[1] <= target_end + 200
        ]
        
        # Find paragraph boundaries near target
        para_breaks = [
            pos for pos in paragraph_boundaries
            if current_pos < pos <= target_end + 100
        ]
        
        # Prefer semantic boundary, then paragraph, then position
        all_breaks = semantic_breaks + para_breaks
        
        if all_breaks:
            best_break = min(all_breaks, key=lambda x: abs(x - target_end))
            return best_break
        
        return min(target_end, len(text))
    
    def _classify_chunk(self, text: str) -> str:
        """Classify the type of chunk"""
        
        if text.strip().startswith('#'):
            return "section"
        elif text.count('\n') > 5 and text.count('\n-') > 0:
            return "list"
        elif any(keyword in text.upper() for keyword in ["DEFINITION", "DEF", "MEANS"]):
            return "definition"
        elif any(keyword in text.upper() for keyword in ["RULE", "MUST", "SHALL", "REQUIREMENT"]):
            return "requirement"
        elif any(keyword in text.upper() for keyword in ["EXAMPLE", "INSTANCE"]):
            return "example"
        else:
            return "content"
    
    def chunk_with_overlap(self, chunks: List[SemanticChunk], overlap_size: int = 64) -> List[SemanticChunk]:
        """
        Add overlapping context to chunks while respecting semantic boundaries.
        """
        enhanced_chunks = []
        
        for i, chunk in enumerate(chunks):
            # Get overlapping text from previous chunk if available
            if i > 0:
                prev_chunk = chunks[i - 1]
                overlap_start = max(prev_chunk.start_pos, chunk.start_pos - overlap_size)
                
                if overlap_start < chunk.start_pos:
                    overlap_text = chunk.text[:chunk.start_pos + overlap_size - chunk.start_pos]
                    if len(overlap_text.split()) > 3:  # At least 3 words of overlap
                        enhanced_chunks.append(SemanticChunk(
                            text=overlap_text,
                            chunk_id=f"{chunk.chunk_id}_overlap_prev",
                            start_pos=overlap_start,
                            end_pos=chunk.start_pos + overlap_size,
                            chunk_type="overlap",
                            hierarchy_level=chunk.hierarchy_level,
                            section_title=chunk.section_title,
                            subsection_title=chunk.subsection_title,
                            parent_chunk_id=chunk.chunk_id,
                        ))
            
            enhanced_chunks.append(chunk)
        
        return enhanced_chunks
    
    def smart_split(self, text: str) -> List[SemanticChunk]:
        """
        Main entry point: split text into semantic chunks.
        """
        chunks = self.chunk_by_semantic_boundaries(text)
        
        # Add overlap for context preservation
        chunks = self.chunk_with_overlap(chunks, overlap_size=64)
        
        return chunks


def merge_related_chunks(chunks: List[SemanticChunk], text: str) -> List[SemanticChunk]:
    """
    Post-processing: merge chunks that should stay together.
    
    Rules:
    - Keep definition + scope together
    - Keep rule + exception together
    - Keep requirement + constraint together
    """
    merged = []
    i = 0
    
    while i < len(chunks):
        current = chunks[i]
        
        # Look ahead for chunks that should be merged
        if i + 1 < len(chunks):
            next_chunk = chunks[i + 1]
            
            # Merge if current is a definition and next is a scope/constraint
            if current.chunk_type == "definition" and next_chunk.chunk_type == "requirement":
                merged_text = current.text + "\n\n" + next_chunk.text
                merged.append(SemanticChunk(
                    text=merged_text,
                    chunk_id=f"{current.chunk_id}_merged",
                    start_pos=current.start_pos,
                    end_pos=next_chunk.end_pos,
                    chunk_type="definition_with_constraint",
                    hierarchy_level=current.hierarchy_level,
                    section_title=current.section_title,
                    subsection_title=current.subsection_title,
                ))
                i += 2
                continue
        
        merged.append(current)
        i += 1
    
    return merged
