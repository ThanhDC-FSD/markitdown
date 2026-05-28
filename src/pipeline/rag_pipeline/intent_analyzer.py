"""Intent analysis and baseline detection for query understanding."""

import re
from typing import List, Dict, Set
from collections import Counter


class IntentAnalyzer:
    """Analyze user queries and detect intent based on KB content."""

    def __init__(self):
        """Initialize the intent analyzer."""
        self.kb_terms: Dict[str, int] = {}
        self.kb_topics: Set[str] = set()
        self.kb_keywords: List[str] = []

    def build_baseline(self, documents: List[str]) -> None:
        """
        Build a baseline of topics and keywords from documents.

        Args:
            documents: List of documents in the KB
        """
        self.kb_terms = {}
        all_words = []

        # Extract all words and build term frequency
        for doc in documents:
            words = self._extract_keywords(doc)
            all_words.extend(words)
            for word in words:
                self.kb_terms[word] = self.kb_terms.get(word, 0) + 1

        # Get top keywords
        term_freq = Counter(self.kb_terms)
        self.kb_keywords = [word for word, _ in term_freq.most_common(100)]
        self.kb_topics = set(self.kb_keywords)

    def analyze_query(self, query: str) -> Dict:
        """
        Analyze a user query for intent and relevance.

        Args:
            query: User query text

        Returns:
            Dictionary with intent analysis results
        """
        query_keywords = self._extract_keywords(query)
        query_terms_set = set(query_keywords)

        # Calculate overlap with KB
        kb_overlap = query_terms_set.intersection(self.kb_topics)
        overlap_ratio = len(kb_overlap) / len(query_terms_set) if query_terms_set else 0.0

        # Detect intent types
        intent_type = self._detect_intent_type(query)

        # Calculate relevance score (0-1)
        relevance_score = self._calculate_relevance_score(query_keywords)

        # Improved KB relevance decision: hybrid of lexical and semantic proxy
        # Keep legacy relevance_score but add hybrid_score and decision
        hybrid_score = max(overlap_ratio, relevance_score)

        return {
            "query": query,
            "keywords": query_keywords,
            "kb_overlap": list(kb_overlap),
            "overlap_ratio": overlap_ratio,
            "intent_type": intent_type,
            "relevance_score": relevance_score,
            "hybrid_kb_relevance_score": hybrid_score,
            "is_kb_relevant": hybrid_score > 0.25,  # More permissive by default
        }

    def _extract_keywords(self, text: str) -> List[str]:
        """
        Extract keywords from text.

        Args:
            text: Input text

        Returns:
            List of keywords (lowercased, alphanumeric)
        """
        # Convert to lowercase and split
        words = text.lower().split()

        # Remove punctuation and keep only alphanumeric words
        keywords = [
            re.sub(r'[^\w]', '', word)
            for word in words
            if re.sub(r'[^\w]', '', word) and len(word) > 2
        ]

        return keywords

    def _detect_intent_type(self, query: str) -> str:
        """
        Detect the type of query intent.

        Args:
            query: User query

        Returns:
            Intent type: 'question', 'definition', 'comparison', 'explanation', 'other'
        """
        query_lower = query.lower()

        if query_lower.startswith(("what", "who", "when", "where", "why")):
            return "question"
        elif any(phrase in query_lower for phrase in ["what is", "define", "what does"]):
            return "definition"
        elif any(phrase in query_lower for phrase in ["compare", "difference", "vs"]):
            return "comparison"
        elif any(phrase in query_lower for phrase in ["how", "explain", "why"]):
            return "explanation"
        else:
            return "other"

    def _calculate_relevance_score(self, query_keywords: List[str]) -> float:
        """
        Calculate relevance score for query keywords against KB.

        Args:
            query_keywords: List of query keywords

        Returns:
            Relevance score (0-1)
        """
        if not query_keywords:
            return 0.0

        # Calculate how many query keywords are in KB
        kb_keyword_set = set(self.kb_keywords)
        matching_keywords = sum(1 for kw in query_keywords if kw in kb_keyword_set)

        score = matching_keywords / len(query_keywords)
        return min(score, 1.0)

    def get_baseline_info(self) -> Dict:
        """
        Get information about the current KB baseline.

        Returns:
            Dictionary with baseline statistics
        """
        return {
            "total_terms": len(self.kb_terms),
            "top_keywords_count": len(self.kb_keywords),
            "topics_count": len(self.kb_topics),
            "top_keywords": self.kb_keywords[:20],
        }
