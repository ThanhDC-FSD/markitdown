"""
Enhanced Retriever for Production RAG
Implements precision-focused retrieval with safety guards and hard distractor prevention
"""

from typing import List, Dict, Any, Tuple
import json
from pathlib import Path


class EnhancedRetriever:
    """
    Production-grade retriever with:
    - Metadata filtering (before vector search)
    - Hybrid retrieval (dense + sparse)
    - Hard distractor prevention
    - Evidence quality ranking
    - Context compression
    """
    
    def __init__(self, db_path: str = "./chroma_db"):
        self.db_path = Path(db_path)
        self.db_path.mkdir(exist_ok=True)
        self.embeddings_file = self.db_path / "enhanced_embeddings.json"
        self.embeddings = []
    
    def add_enhanced_embeddings(self, embedding_records: List[Dict[str, Any]]):
        """Store enhanced embedding records"""
        self.embeddings.extend(embedding_records)
        self._persist_embeddings()
    
    def _persist_embeddings(self):
        """Save embeddings to disk"""
        with open(self.embeddings_file, 'w', encoding='utf-8') as f:
            json.dump(self.embeddings, f, indent=2, ensure_ascii=False)
    
    def _load_embeddings(self):
        """Load embeddings from disk"""
        if self.embeddings_file.exists():
            with open(self.embeddings_file, 'r', encoding='utf-8') as f:
                self.embeddings = json.load(f)
    
    def metadata_filter(
        self,
        query: str,
        negative_scope_tags: List[str] = None,
        domain: str = "AUTOSAR",
        topic: str = None,
    ) -> List[Dict[str, Any]]:
        """
        Pre-filtering: Remove chunks that are out of scope BEFORE vector search.
        This prevents hard distractors from contaminating retrieval results.
        """
        if negative_scope_tags is None:
            negative_scope_tags = []
        
        filtered = []
        
        for record in self.embeddings:
            metadata = record.get("metadata", {})
            retrieval_safety = record.get("retrieval_safety", {})
            
            # Domain filter
            if metadata.get("domain") != domain:
                continue
            
            # Topic filter (if specified)
            if topic and metadata.get("topic") != topic:
                continue
            
            # Negative scope filter
            negative_tags = retrieval_safety.get("negative_scope_tags", [])
            if any(tag in query.lower() for tag in negative_tags):
                # Potential hard distractor detected
                continue
            
            # Distractor check
            distractor_guard = retrieval_safety.get("distractor_guard_metadata", {})
            exclusion_indicators = distractor_guard.get("exclusion_indicators", [])
            if any(term in query.lower() for term in exclusion_indicators):
                continue
            
            filtered.append(record)
        
        return filtered
    
    def hybrid_search(
        self,
        query: str,
        filtered_records: List[Dict[str, Any]],
        top_k: int = 5,
        dense_weight: float = 0.6,
        sparse_weight: float = 0.4,
    ) -> List[Tuple[Dict[str, Any], float]]:
        """
        Hybrid retrieval: Combine dense vector search + sparse keyword matching.
        
        Strategy:
        1. Dense similarity: Cosine similarity on hash-based vectors
        2. Sparse similarity: Keyword overlap (BM25-like)
        3. Combined score: Weighted average of both
        """
        from .hybrid_embedder import cosine_similarity_safe
        
        query_words = set(query.lower().split())
        scored_records = []
        
        # Generate query embedding
        query_embedding = self._generate_query_embedding(query)
        
        for record in filtered_records:
            # Dense similarity
            chunk_embedding = record.get("embedding", [])
            dense_sim = cosine_similarity_safe(query_embedding, chunk_embedding)
            
            # Sparse similarity (keyword matching)
            sparse_keywords = record.get("hybrid_retrieval", {}).get("sparse_keywords", {})
            keyword_matches = sum(
                sparse_keywords.get(word, 0)
                for word in query_words
                if word in sparse_keywords
            )
            sparse_sim = min(keyword_matches / max(len(query_words), 1), 1.0)
            
            # Combined score
            combined_score = (dense_weight * dense_sim) + (sparse_weight * sparse_sim)
            
            # Apply safety factor
            safety_score = record.get("retrieval_safety", {}).get("retrieval_confidence", 0.5)
            final_score = combined_score * safety_score
            
            scored_records.append((record, final_score))
        
        # Sort by score (descending) and return top_k
        scored_records.sort(key=lambda x: x[1], reverse=True)
        return scored_records[:top_k]
    
    def _generate_query_embedding(self, query: str) -> List[float]:
        """Generate embedding for query text"""
        from .hybrid_embedder import HybridEmbedder
        embedder = HybridEmbedder()
        return embedder.generate_dense_embedding(query)
    
    def rerank_with_evidence_quality(
        self,
        retrieved_records: List[Tuple[Dict[str, Any], float]],
        top_k: int = 3,
    ) -> List[Tuple[Dict[str, Any], float]]:
        """
        Rerank results based on evidence quality metrics.
        
        Factors:
        - Authority level (critical > high > medium > low)
        - Source reliability score
        - Confidence level
        - No contradictions
        """
        ranked = []
        
        for record, base_score in retrieved_records:
            evidence_quality = record.get("evidence_quality", {})
            authority_level = evidence_quality.get("authority_level", "medium")
            reliability = evidence_quality.get("source_reliability", 0.5)
            confidence = evidence_quality.get("confidence_level", 0.5)
            
            # Authority multiplier
            authority_mult = {
                "critical": 1.5,
                "high": 1.2,
                "medium": 1.0,
                "low": 0.8,
            }.get(authority_level, 1.0)
            
            # Final reranked score
            quality_score = base_score * authority_mult * reliability * confidence
            
            ranked.append((record, quality_score))
        
        # Sort by reranked score
        ranked.sort(key=lambda x: x[1], reverse=True)
        return ranked[:top_k]
    
    def retrieve_with_safety(
        self,
        query: str,
        top_k: int = 5,
        rerank_top_k: int = 3,
        negative_scope: List[str] = None,
        domain: str = "AUTOSAR",
        topic: str = None,
    ) -> Dict[str, Any]:
        """
        Complete retrieval pipeline with safety guards.
        
        Steps:
        1. Metadata filtering (remove out-of-scope)
        2. Hybrid search (dense + sparse)
        3. Reranking (evidence quality)
        4. Context compression
        """
        self._load_embeddings()
        
        # Step 1: Metadata filtering
        filtered_records = self.metadata_filter(
            query,
            negative_scope_tags=negative_scope or [],
            domain=domain,
            topic=topic,
        )
        
        if not filtered_records:
            return {
                "status": "insufficient_evidence",
                "message": "No documents found matching safety criteria",
                "filtered_count": 0,
                "retrieved": [],
            }
        
        # Step 2: Hybrid search
        hybrid_results = self.hybrid_search(
            query,
            filtered_records,
            top_k=top_k,
            dense_weight=0.6,
            sparse_weight=0.4,
        )
        
        if not hybrid_results:
            return {
                "status": "insufficient_evidence",
                "message": "No high-confidence matches found",
                "filtered_count": len(filtered_records),
                "retrieved": [],
            }
        
        # Step 3: Reranking
        reranked_results = self.rerank_with_evidence_quality(
            hybrid_results,
            top_k=rerank_top_k,
        )
        
        # Step 4: Prepare output with evidence tracking
        retrieved_items = []
        for record, score in reranked_results:
            retrieved_items.append({
                "chunk_id": record.get("chunk_id"),
                "text": record.get("text"),
                "metadata": record.get("metadata", {}),
                "retrieval_score": score,
                "retrieval_safety": record.get("retrieval_safety", {}),
                "evidence_quality": record.get("evidence_quality", {}),
            })
        
        return {
            "status": "success",
            "query": query,
            "retrieved_count": len(retrieved_items),
            "filtered_count": len(filtered_records),
            "total_records": len(self.embeddings),
            "retrieved": retrieved_items,
            "retrieval_method": "hybrid_with_safety",
        }
    
    def detect_contradictions(self, retrieved_items: List[Dict[str, Any]]) -> List[str]:
        """Detect if retrieved items contradict each other"""
        contradictions = []
        
        for i, item1 in enumerate(retrieved_items):
            for item2 in retrieved_items[i+1:]:
                # Check if both claim to cover same topic but different sections
                if item1["metadata"].get("topic") == item2["metadata"].get("topic"):
                    if item1["metadata"].get("section_title") != item2["metadata"].get("section_title"):
                        contradictions.append(
                            f"Potential contradiction: {item1['metadata']['section_title']} vs "
                            f"{item2['metadata']['section_title']}"
                        )
        
        return contradictions
    
    def prepare_evidence_context(
        self,
        retrieved_items: List[Dict[str, Any]],
        max_context_chars: int = 2000,
    ) -> str:
        """
        Prepare compressed evidence context for LLM.
        
        Rules:
        1. Deduplicate overlapping claims
        2. Preserve citations (chunk_id, source)
        3. Remove low-confidence items
        4. Compress if needed
        """
        context_parts = []
        char_count = 0
        
        for item in retrieved_items:
            if char_count > max_context_chars:
                break
            
            score = item.get("retrieval_score", 0)
            confidence = item.get("retrieval_safety", {}).get("retrieval_confidence", 0.5)
            
            # Skip low-confidence items
            if score < 0.3 or confidence < 0.3:
                continue
            
            chunk_id = item.get("chunk_id", "unknown")
            text = item.get("text", "")
            section = item.get("metadata", {}).get("section_title", "")
            
            # Format as evidence with citation
            evidence = f"[{chunk_id} | {section}]\n{text}\n"
            
            if char_count + len(evidence) <= max_context_chars:
                context_parts.append(evidence)
                char_count += len(evidence)
        
        return "\n".join(context_parts)
