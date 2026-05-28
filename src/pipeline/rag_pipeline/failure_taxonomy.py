"""
Production-grade failure taxonomy for RAG pipeline.

Systematically classifies failures across all layers of the Q&A pipeline.
Used for detailed diagnostics and targeted refinement.
"""

from typing import List, Set, Dict, Any
from enum import Enum
from dataclasses import dataclass, field


class FailureCategory(Enum):
    """Primary failure categories across the RAG pipeline."""
    
    # Retrieval failures
    R1 = "retrieval_failed"  # No relevant documents retrieved
    R2 = "retrieval_weak"  # Retrieved docs exist but are insufficient or borderline
    
    # KB relevance failures
    K1 = "kb_relevance_false_negative"  # Query is relevant but marked as not relevant
    K2 = "kb_relevance_false_positive"  # Query marked as relevant when it isn't
    
    # Prompt failures
    P1 = "prompt_contamination"  # Stale context, old conversation history, unrelated examples
    P2 = "prompt_too_loose"  # Prompt allows too much freedom, generic responses
    P3 = "prompt_too_strict"  # Prompt too restrictive, rejects valid answers
    
    # Generation failures
    G1 = "wrong_domain_hallucination"  # Answer drifts to unrelated domain
    G2 = "unsupported_over_inference"  # Answer makes claims beyond evidence
    G3 = "false_abstention"  # Incorrectly says insufficient context when evidence exists
    
    # Expectation failures
    E1 = "expectation_coverage_low"  # Missing key facts from expected answer
    
    # Domain failures
    D1 = "domain_consistency_failure"  # Answer violates domain consistency rules
    
    # Metric inconsistencies
    M1 = "metric_inconsistency"  # Conflicting signals between lexical, semantic, reranker scores


@dataclass
class FailureClassification:
    """Classify a single test case failure."""
    
    test_case_id: str
    query: str
    generated_answer: str
    
    # Primary failure categories from taxonomy
    failure_categories: List[FailureCategory] = field(default_factory=list)
    
    # Detailed failure reasons
    failure_reasons: List[str] = field(default_factory=list)
    
    # Supporting evidence
    supporting_evidence: Dict[str, Any] = field(default_factory=dict)
    
    # Severity (critical, high, medium, low)
    severity: str = "medium"
    
    # Whether this is a false positive failure (system correctly identified a limit)
    is_false_positive: bool = False
    
    def add_failure(self, category: FailureCategory, reason: str, evidence: Dict[str, Any] = None):
        """Add a failure category and supporting evidence."""
        if category not in self.failure_categories:
            self.failure_categories.append(category)
        self.failure_reasons.append(reason)
        if evidence:
            self.supporting_evidence[f"{category.value}"] = evidence
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "test_case_id": self.test_case_id,
            "query": self.query,
            "generated_answer": self.generated_answer,
            "failure_categories": [cat.value for cat in self.failure_categories],
            "failure_reasons": self.failure_reasons,
            "severity": self.severity,
            "is_false_positive": self.is_false_positive,
            "supporting_evidence": self.supporting_evidence,
        }


class FailureTaxonomyAnalyzer:
    """
    Analyzes test results and assigns failure classifications.
    
    Provides structured diagnosis for understanding and fixing recurring failures.
    """
    
    def __init__(self):
        """Initialize the failure analyzer."""
        self.forbidden_topic_keywords = {}  # test_case_id -> set of forbidden keywords
    
    def set_forbidden_topics(self, test_case_id: str, forbidden_topics: List[str]):
        """Register forbidden topics for a test case."""
        self.forbidden_topic_keywords[test_case_id] = set(
            t.lower() for t in forbidden_topics
        )
    
    def analyze_failure(
        self,
        test_case_id: str,
        query: str,
        generated_answer: str,
        expected_domain: str,
        expected_answer_points: List[str],
        required_keywords: List[str],
        optional_keywords: List[str],
        forbidden_topics: List[str],
        kb_relevance_score: float,
        semantic_relevance_score: float,
        reranker_score: float,
        lexical_overlap_score: float,
        retrieval_pass: bool,
        grounding_score: float,
        expectation_coverage: float,
        hallucination_risk_score: float,
        abstention_used: bool,
        top_evidence: List[Dict[str, Any]] = None,
    ) -> FailureClassification:
        """
        Analyze a failed test case and assign failure classifications.
        
        Args:
            test_case_id: Unique test identifier
            query: User query
            generated_answer: Answer produced by system
            expected_domain: Expected answer domain
            expected_answer_points: Key facts expected in answer
            required_keywords: Keywords that must appear
            optional_keywords: Keywords that should appear
            forbidden_topics: Topics that must not appear
            kb_relevance_score: KB relevance score (0-1)
            semantic_relevance_score: Semantic relevance score (0-1)
            reranker_score: Cross-encoder/reranker score
            lexical_overlap_score: Lexical overlap score (0-1)
            retrieval_pass: Whether retrieval returned relevant docs
            grounding_score: Grounding in evidence (0-1)
            expectation_coverage: Coverage of expected answer points (0-1)
            hallucination_risk_score: Risk of hallucination (0-1)
            abstention_used: Whether system abstained
            top_evidence: Top retrieved evidence chunks
            
        Returns:
            FailureClassification with taxonomy assignments
        """
        classification = FailureClassification(
            test_case_id=test_case_id,
            query=query,
            generated_answer=generated_answer,
        )
        
        top_evidence = top_evidence or []
        
        # =====================================================================
        # Detect K1: KB Relevance False Negative
        # =====================================================================
        if (kb_relevance_score < 0.5 and  # System marked as not relevant
            semantic_relevance_score > 0.7 and  # But semantic evidence exists
            (reranker_score > 3.0 if reranker_score else True) and  # Reranker agrees
            retrieval_pass):  # Retrieval actually returned relevant docs
            
            classification.add_failure(
                FailureCategory.K1,
                f"KB relevance false negative: semantic_score={semantic_relevance_score:.3f}, reranker_score={reranker_score}, "
                f"but kb_relevance_score={kb_relevance_score:.3f}",
                {
                    "semantic_relevance_score": semantic_relevance_score,
                    "reranker_score": reranker_score,
                    "kb_relevance_score": kb_relevance_score,
                    "lexical_overlap_score": lexical_overlap_score,
                    "retrieval_pass": retrieval_pass,
                }
            )
        
        # =====================================================================
        # Detect M1: Metric Inconsistency
        # =====================================================================
        if (lexical_overlap_score < 0.3 and  # Very low lexical overlap
            semantic_relevance_score > 0.7 and  # But high semantic relevance
            reranker_score and reranker_score > 3.0):  # Reranker agrees
            
            classification.add_failure(
                FailureCategory.M1,
                f"Metric inconsistency: lexical_overlap={lexical_overlap_score:.3f} vs "
                f"semantic_relevance={semantic_relevance_score:.3f} (major divergence)",
                {
                    "lexical_overlap_score": lexical_overlap_score,
                    "semantic_relevance_score": semantic_relevance_score,
                    "reranker_score": reranker_score,
                }
            )
        
        # =====================================================================
        # Detect G3: False Abstention
        # =====================================================================
        if (abstention_used and  # System abstained
            grounding_score > 0.6 and  # But evidence grounding is decent
            retrieval_pass and  # Retrieval worked
            semantic_relevance_score > 0.6):  # Semantic match is good
            
            classification.add_failure(
                FailureCategory.G3,
                f"False abstention: grounding_score={grounding_score:.3f}, "
                f"semantic_relevance={semantic_relevance_score:.3f}, but answer says insufficient context",
                {
                    "grounding_score": grounding_score,
                    "semantic_relevance_score": semantic_relevance_score,
                    "retrieval_pass": retrieval_pass,
                    "abstention_used": abstention_used,
                }
            )
        
        # =====================================================================
        # Detect G1: Wrong-Domain Hallucination
        # =====================================================================
        forbidden_keywords = self.forbidden_topic_keywords.get(test_case_id, set())
        answer_lower = generated_answer.lower()
        found_forbidden = [kw for kw in forbidden_keywords if kw in answer_lower]
        
        if found_forbidden and not abstention_used:
            classification.add_failure(
                FailureCategory.G1,
                f"Wrong-domain hallucination: found forbidden topics {found_forbidden} in answer; "
                f"expected domain was {expected_domain}",
                {
                    "forbidden_topics": forbidden_topics,
                    "found_in_answer": found_forbidden,
                    "expected_domain": expected_domain,
                }
            )
        
        # =====================================================================
        # Detect G2: Unsupported Over-Inference
        # =====================================================================
        if (not abstention_used and  # Made a claim
            grounding_score < 0.5 and  # But grounding is weak
            hallucination_risk_score > 0.6):  # And hallucination risk is high
            
            classification.add_failure(
                FailureCategory.G2,
                f"Unsupported over-inference: grounding_score={grounding_score:.3f}, "
                f"hallucination_risk={hallucination_risk_score:.3f}",
                {
                    "grounding_score": grounding_score,
                    "hallucination_risk_score": hallucination_risk_score,
                }
            )
        
        # =====================================================================
        # Detect R1 or R2: Retrieval Failures
        # =====================================================================
        if not retrieval_pass:
            if semantic_relevance_score > 0.5:
                classification.add_failure(
                    FailureCategory.R2,
                    f"Retrieval weak: semantic_score={semantic_relevance_score:.3f} suggests "
                    f"relevant docs exist but weren't retrieved",
                    {
                        "semantic_relevance_score": semantic_relevance_score,
                        "retrieval_pass": False,
                    }
                )
            else:
                classification.add_failure(
                    FailureCategory.R1,
                    "No relevant documents retrieved",
                    {
                        "retrieval_pass": False,
                    }
                )
        
        # =====================================================================
        # Detect E1: Expectation Coverage
        # =====================================================================
        if expectation_coverage < 0.7 and not abstention_used:
            classification.add_failure(
                FailureCategory.E1,
                f"Low expectation coverage: {expectation_coverage:.1%} vs 0.70 minimum; "
                f"missing key facts from expected answer points",
                {
                    "expectation_coverage": expectation_coverage,
                    "expected_answer_points": expected_answer_points[:3],  # First 3
                }
            )
        
        # =====================================================================
        # Detect D1: Domain Consistency
        # =====================================================================
        if expected_domain.lower() not in answer_lower and not abstention_used:
            if len(generated_answer) > 20:  # Only if answer is substantial
                classification.add_failure(
                    FailureCategory.D1,
                    f"Domain consistency: answer doesn't mention expected domain '{expected_domain}'",
                    {
                        "expected_domain": expected_domain,
                    }
                )
        
        # =====================================================================
        # Determine severity and category patterns
        # =====================================================================
        self._set_severity_and_patterns(classification, abstention_used)
        
        return classification
    
    def _set_severity_and_patterns(
        self,
        classification: FailureClassification,
        abstention_used: bool,
    ):
        """Determine failure severity based on category patterns."""
        critical_categories = {FailureCategory.G1, FailureCategory.G2}
        high_categories = {FailureCategory.K1, FailureCategory.G3, FailureCategory.R1}
        
        failure_set = set(classification.failure_categories)
        
        if failure_set & critical_categories:
            classification.severity = "critical"
        elif failure_set & high_categories:
            classification.severity = "high"
        elif FailureCategory.M1 in failure_set or FailureCategory.E1 in failure_set:
            classification.severity = "medium"
        else:
            classification.severity = "low"
    
    def compute_taxonomy_statistics(
        self,
        classifications: List[FailureClassification],
    ) -> Dict[str, Any]:
        """
        Compute aggregate failure statistics by category.
        
        Args:
            classifications: List of FailureClassification results
            
        Returns:
            Dictionary with statistics by failure category
        """
        stats = {}
        
        # Count by category
        category_counts = {}
        severity_counts = {}
        
        for cat in FailureCategory:
            category_counts[cat.value] = 0
        
        for severity in ["critical", "high", "medium", "low"]:
            severity_counts[severity] = 0
        
        # Process classifications
        for classification in classifications:
            severity_counts[classification.severity] += 1
            
            for category in classification.failure_categories:
                category_counts[category.value] += 1
        
        stats = {
            "total_failures": len(classifications),
            "by_category": category_counts,
            "by_severity": severity_counts,
            "top_failure_categories": sorted(
                category_counts.items(),
                key=lambda x: x[1],
                reverse=True
            )[:5],
        }
        
        return stats
