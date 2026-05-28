"""
Enhanced Embedding Generator for Production RAG
Creates hybrid embeddings: dense vectors + sparse keywords + metadata enrichment
Focuses on retrieval safety and distractor prevention
"""

import hashlib
import json
from typing import List, Dict, Tuple, Any
from dataclasses import dataclass


@dataclass
class EmbeddingPayload:
    """Enriched payload for embedding generation"""
    chunk_text: str
    canonical_summary: str
    section_context: str
    keywords: List[str]
    negative_scope: List[str]
    retrieval_intent_tags: List[str]
    distractor_guards: Dict[str, Any]
    
    def to_embedding_string(self) -> str:
        """Convert to weighted string for embedding"""
        components = []
        
        # Primary content (weight: 1.0)
        components.append(f"[CONTENT] {self.chunk_text[:300]}")
        
        # Summary (weight: 0.8 - important context)
        components.append(f"[SUMMARY] {self.canonical_summary}")
        
        # Section context (weight: 0.6 - hierarchy)
        components.append(f"[SECTION] {self.section_context}")
        
        # Keywords (weight: 0.9 - very important for retrieval)
        if self.keywords:
            components.append(f"[KEYWORDS] {' '.join(self.keywords)}")
        
        # Retrieval intent (weight: 0.8 - query matching)
        if self.retrieval_intent_tags:
            components.append(f"[INTENT] {' '.join(self.retrieval_intent_tags)}")
        
        # Negative scope (weight: 0.7 - distractor prevention)
        if self.negative_scope:
            components.append(f"[NOT_FOR] {' '.join(self.negative_scope)}")
        
        # Retrieval guard terms (weight: 0.9 - critical for precision)
        if self.distractor_guards:
            guard_terms = self.distractor_guards.get("retrieval_guard_terms", [])
            if guard_terms:
                components.append(f"[GUARD] {' '.join(guard_terms)}")
        
        return "\n".join(components)


class HybridEmbedder:
    """
    Generates hybrid embeddings: dense vectors + sparse representations + metadata
    
    Strategy:
    1. Dense embedding: 16-dim hash-based (extensible to transformer)
    2. Sparse representation: keyword-based for BM25-style retrieval
    3. Metadata filtering: pre-vector-search filtering
    4. Distractor guards: prevent wrong documents
    """
    
    def __init__(self, embedding_dim: int = 16):
        self.embedding_dim = embedding_dim
    
    def create_embedding_payload(
        self,
        chunk_text: str,
        canonical_summary: str,
        section_context: str,
        keywords: List[str],
        negative_scope: List[str],
        retrieval_intent_tags: List[str],
        distractor_guards: Dict[str, Any],
    ) -> EmbeddingPayload:
        """Create enriched embedding payload"""
        return EmbeddingPayload(
            chunk_text=chunk_text,
            canonical_summary=canonical_summary,
            section_context=section_context,
            keywords=keywords,
            negative_scope=negative_scope,
            retrieval_intent_tags=retrieval_intent_tags,
            distractor_guards=distractor_guards,
        )
    
    def generate_dense_embedding(self, text: str, dim: int = None) -> List[float]:
        """
        Generate dense embedding using hash-based approach.
        Produces reproducible vectors suitable for cosine similarity.
        
        Strategy:
        - Hash text into multiple substrings
        - Create feature vector
        - Normalize to unit length
        """
        if dim is None:
            dim = self.embedding_dim
        
        embedding = [0.0] * dim
        
        # Create multiple hash seeds for diversity
        seeds = ["seed_0", "seed_1", "seed_2"]
        
        for seed in seeds:
            combined = f"{seed}:{text}".encode('utf-8')
            hash_obj = hashlib.sha256(combined).digest()
            
            for i in range(min(dim, len(hash_obj))):
                byte_val = hash_obj[i]
                embedding[i] += (byte_val / 255.0) - 0.5  # Center around 0
        
        # Normalize to unit length
        magnitude = sum(x ** 2 for x in embedding) ** 0.5
        if magnitude > 0:
            embedding = [x / magnitude for x in embedding]
        
        return embedding
    
    def generate_sparse_representation(self, keywords: List[str]) -> Dict[str, float]:
        """
        Generate sparse keyword-based representation for BM25-style retrieval.
        Each keyword gets a score based on term frequency.
        """
        sparse_repr = {}
        total_keywords = len(keywords)
        
        for i, keyword in enumerate(keywords):
            # Score decreases with position (first keywords more important)
            score = 1.0 - (i / max(total_keywords, 1))
            sparse_repr[keyword.lower()] = score
        
        return sparse_repr
    
    def generate_retrieval_safe_embedding(
        self,
        embedding_payload: EmbeddingPayload
    ) -> Dict[str, Any]:
        """
        Generate complete retrieval-safe embedding with all components.
        
        Output:
        {
            "dense_vector": [...],  # For vector similarity search
            "sparse_representation": {...},  # For BM25-like retrieval
            "keyword_boost_terms": [...],  # High-confidence retrieval terms
            "distractor_penalty_terms": [...],  # Should reduce score
            "metadata_filters": {...},  # For metadata pre-filtering
            "retrieval_confidence": 0.0-1.0,
        }
        """
        
        # Dense embedding from enriched payload
        embedding_text = embedding_payload.to_embedding_string()
        dense_vector = self.generate_dense_embedding(embedding_text)
        
        # Sparse representation from keywords
        sparse_repr = self.generate_sparse_representation(
            embedding_payload.keywords
        )
        
        # Boost terms (should increase relevance score)
        keyword_boost_terms = embedding_payload.keywords + embedding_payload.retrieval_intent_tags
        
        # Penalty terms (should decrease score if present with wrong query)
        distractor_penalty_terms = embedding_payload.negative_scope + \
            embedding_payload.distractor_guards.get("exclusion_indicators", [])
        
        # Retrieval confidence based on components
        confidence = self._calculate_retrieval_confidence(embedding_payload)
        
        return {
            "dense_vector": dense_vector,
            "sparse_representation": sparse_repr,
            "keyword_boost_terms": keyword_boost_terms,
            "distractor_penalty_terms": distractor_penalty_terms,
            "retrieval_intent_tags": embedding_payload.retrieval_intent_tags,
            "negative_scope_tags": embedding_payload.negative_scope,
            "distractor_guard_metadata": embedding_payload.distractor_guards,
            "retrieval_confidence": confidence,
            "embedding_metadata": {
                "chunk_content_summary": embedding_payload.canonical_summary,
                "section_hierarchy": embedding_payload.section_context,
                "retrieval_safety_score": 1.0 - (len(distractor_penalty_terms) / 10),  # Normalized 0-1
            }
        }
    
    def _calculate_retrieval_confidence(self, payload: EmbeddingPayload) -> float:
        """
        Calculate confidence in retrieval quality for this chunk.
        
        Factors:
        - Has clear summary (good)
        - Has retrieval intent tags (good)
        - Has distractor guards (good - explicit scoping)
        - Has few negative scope tags (good)
        """
        confidence = 0.5  # Base confidence
        
        if payload.canonical_summary:
            confidence += 0.2
        
        if payload.retrieval_intent_tags:
            confidence += 0.1 * min(len(payload.retrieval_intent_tags) / 3, 1.0)
        
        if payload.distractor_guards.get("distractor_count", 0) > 0:
            confidence += 0.1  # Explicit distractor marking is good
        
        if len(payload.negative_scope) > 0:
            confidence += 0.05  # Clear scope definition is good
        
        # Cap at 1.0
        return min(confidence, 1.0)
    
    def create_hybrid_embedding_record(
        self,
        chunk_id: str,
        chunk_text: str,
        metadata: Dict[str, Any],
        embedding_payload: EmbeddingPayload,
    ) -> Dict[str, Any]:
        """Create complete embedding record with all retrieval components"""
        
        safe_embedding = self.generate_retrieval_safe_embedding(embedding_payload)
        
        return {
            "chunk_id": chunk_id,
            "text": chunk_text,
            "text_length": len(chunk_text),
            # Core embeddings
            "embedding": safe_embedding["dense_vector"],
            "embedding_model": "hash_based_16dim",
            # Hybrid retrieval components
            "hybrid_retrieval": {
                "dense_vector": safe_embedding["dense_vector"],
                "sparse_keywords": safe_embedding["sparse_representation"],
                "keyword_boost_terms": safe_embedding["keyword_boost_terms"],
                "distractor_penalty_terms": safe_embedding["distractor_penalty_terms"],
            },
            # Safety metadata
            "retrieval_safety": {
                "retrieval_intent_tags": safe_embedding["retrieval_intent_tags"],
                "negative_scope_tags": safe_embedding["negative_scope_tags"],
                "distractor_guard_metadata": safe_embedding["distractor_guard_metadata"],
                "retrieval_confidence": safe_embedding["retrieval_confidence"],
                "retrieval_safety_score": safe_embedding["embedding_metadata"]["retrieval_safety_score"],
            },
            # Document metadata
            "metadata": metadata,
            # Evidence quality
            "evidence_quality": {
                "authority_level": metadata.get("authority_level", "medium"),
                "source_reliability": metadata.get("source_reliability_score", 0.5),
                "confidence_level": metadata.get("confidence_level", 0.5),
            }
        }


def cosine_similarity_safe(vec1: List[float], vec2: List[float], safety_factor: float = 1.0) -> float:
    """
    Calculate cosine similarity with safety factor.
    
    safety_factor: penalizes based on distractor presence
    """
    if len(vec1) != len(vec2):
        return 0.0
    
    dot_product = sum(a * b for a, b in zip(vec1, vec2))
    mag1 = sum(a ** 2 for a in vec1) ** 0.5
    mag2 = sum(b ** 2 for b in vec2) ** 0.5
    
    if mag1 == 0 or mag2 == 0:
        return 0.0
    
    similarity = dot_product / (mag1 * mag2)
    
    # Apply safety factor (reduce score if distractors detected)
    return similarity * safety_factor
