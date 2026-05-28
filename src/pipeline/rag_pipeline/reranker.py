"""Cross-encoder based re-ranking for retrieved documents."""

from typing import List, Tuple
from sentence_transformers import CrossEncoder


class CrossEncoderReranker:
    """Re-rank retrieved documents using cross-encoder models."""

    def __init__(self, model_name: str = "cross-encoder/ms-marco-MiniLM-L-12-v2"):
        """
        Initialize the cross-encoder reranker.

        Args:
            model_name: Name of the cross-encoder model to use
        """
        self.model_name = model_name
        self.model = CrossEncoder(model_name)

    def rerank(
        self,
        query: str,
        documents: List[Tuple[str, float, dict]],
        top_k: int = None,
    ) -> List[Tuple[str, float, dict, float]]:
        """
        Re-rank documents based on query relevance using cross-encoder.

        Args:
            query: Query text
            documents: List of tuples (document_text, distance, metadata)
            top_k: Optional number of top results to return

        Returns:
            List of tuples (document_text, distance, metadata, ce_score)
        """
        if not documents:
            return []

        # Extract document texts for cross-encoder scoring
        doc_texts = [doc[0] for doc in documents]

        # Compute cross-encoder scores
        ce_scores = self.model.predict(
            [[query, doc] for doc in doc_texts],
            convert_to_numpy=True,
        )

        # Create results with cross-encoder scores
        results = []
        for i, (doc_text, distance, metadata) in enumerate(documents):
            ce_score = float(ce_scores[i])
            results.append((doc_text, distance, metadata, ce_score))

        # Sort by cross-encoder score (higher is better)
        results.sort(key=lambda x: x[3], reverse=True)

        if top_k:
            results = results[:top_k]

        return results
