"""
Section J: False Abstention Detection

Implements 6 classification types for abstention analysis:
1. Confident Abstention - LLM confident but should answer (improper)
2. Timeout Abstention - Timeout forced abstention (infrastructure issue)
3. Policy Abstention - Policy-driven but had context (borderline)
4. Hallucination Abstention - Made up reason to abstain (improper)
5. Context-Aware Abstention - True positive (proper - don't flag)
6. Threshold Abstention - Below confidence threshold (borderline)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


@dataclass
class FalseAbstentionAnalysis:
    """Result of false abstention detection analysis."""
    
    # Classification
    abstention_type: str  # One of 6 types above
    is_false_abstention: bool  # True if improper abstention
    confidence_score: float  # 0.0-1.0, higher = more confident in classification
    
    # Reasoning
    reasons: List[str] = field(default_factory=list)
    evidence: Dict[str, Any] = field(default_factory=dict)
    
    # Actionable insights
    recommended_action: Optional[str] = None
    retry_likelihood: float = 0.0  # 0.0-1.0, likelihood retry would succeed
    
    @property
    def summary(self) -> str:
        """Human-readable summary."""
        return f"{self.abstention_type} (false={self.is_false_abstention}, confidence={self.confidence_score:.2f})"


class FalseAbstentionDetector:
    """Detects and classifies false abstractions in RAG responses."""
    
    def __init__(self, logger_instance: Optional[logging.Logger] = None):
        self.logger = logger_instance or logger
    
    def analyze(
        self,
        query: str,
        abstention_reason: str,
        context_chunks: List[Dict[str, Any]],
        retrieval_quality: Optional[Dict[str, Any]] = None,
        generation_details: Optional[Dict[str, Any]] = None,
    ) -> FalseAbstentionAnalysis:
        """
        Analyze an abstention to detect false positives.
        
        Args:
            query: Original user query
            abstention_reason: Reason LLM gave for abstaining
            context_chunks: Retrieved context chunks
            retrieval_quality: Optional dict with retrieval metrics
            generation_details: Optional dict with generation metrics
            
        Returns:
            FalseAbstentionAnalysis with classification and confidence
        """
        analysis = FalseAbstentionAnalysis(
            abstention_type="unknown",
            is_false_abstention=False,
            confidence_score=0.0,
        )
        
        # Gather evidence
        has_context = len(context_chunks) > 0
        context_quality = self._assess_context_quality(context_chunks, retrieval_quality)
        abstention_reason_lower = (abstention_reason or "").lower()
        
        # Check for timeout-related abstention
        if self._is_timeout_abstention(abstention_reason_lower):
            analysis.abstention_type = "timeout_abstention"
            analysis.is_false_abstention = True  # Timeouts are infrastructure issues, not proper abstention
            analysis.confidence_score = 0.95
            analysis.reasons.append("Abstention reason contains timeout keywords")
            analysis.recommended_action = "retry_with_longer_timeout"
            analysis.retry_likelihood = 0.8
            return analysis
        
        # Check for policy-driven abstention
        if self._is_policy_abstention(abstention_reason_lower, query):
            if has_context and context_quality > 0.5:
                analysis.abstention_type = "policy_abstention"
                analysis.is_false_abstention = True  # Borderline - had context but policy blocked
                analysis.confidence_score = 0.75
                analysis.reasons.append("Policy blocked answer despite available context")
                analysis.recommended_action = "review_policy_settings"
                analysis.retry_likelihood = 0.3
                return analysis
        
        # Check for hallucination abstention (made up reason)
        if self._is_hallucination_abstention(abstention_reason_lower, has_context):
            analysis.abstention_type = "hallucination_abstention"
            analysis.is_false_abstention = True
            analysis.confidence_score = 0.85
            analysis.reasons.append("Abstention reason appears fabricated or contradicts context")
            analysis.recommended_action = "retry_with_explicit_instruction"
            analysis.retry_likelihood = 0.7
            return analysis
        
        # Check for threshold abstention (confidence too low)
        if self._is_threshold_abstention(abstention_reason_lower):
            if has_context and context_quality > 0.6:
                analysis.abstention_type = "threshold_abstention"
                analysis.is_false_abstention = False  # Borderline but potentially legitimate
                analysis.confidence_score = 0.65
                analysis.reasons.append("LLM confidence below threshold despite available context")
                analysis.recommended_action = "lower_confidence_threshold_or_rephrase"
                analysis.retry_likelihood = 0.5
                return analysis
        
        # Check for confident abstention (LLM confident in its abstention)
        if self._is_confident_abstention(abstention_reason_lower):
            if has_context and context_quality > 0.7:
                analysis.abstention_type = "confident_abstention"
                analysis.is_false_abstention = True  # Confident but improper given context
                analysis.confidence_score = 0.80
                analysis.reasons.append("LLM explicitly confident in abstention despite strong evidence")
                analysis.recommended_action = "analyze_llm_behavior_or_prompt"
                analysis.retry_likelihood = 0.4
                return analysis
        
        # Default to context-aware abstention (proper)
        if not has_context or context_quality < 0.4:
            analysis.abstention_type = "context_aware_abstention"
            analysis.is_false_abstention = False  # Proper - insufficient context
            analysis.confidence_score = 0.85
            analysis.reasons.append("No meaningful context available - proper abstention")
            analysis.recommended_action = "none"
            analysis.retry_likelihood = 0.1
            return analysis
        
        # Default unknown but seems borderline
        analysis.abstention_type = "context_aware_abstention"
        analysis.is_false_abstention = False
        analysis.confidence_score = 0.5
        analysis.reasons.append("Insufficient signal for classification")
        return analysis
    
    def _is_timeout_abstention(self, reason: str) -> bool:
        """Check if abstention was due to timeout."""
        timeout_keywords = ["timeout", "exceeded", "time limit", "took too long", "timed out"]
        return any(kw in reason for kw in timeout_keywords)
    
    def _is_policy_abstention(self, reason: str, query: str) -> bool:
        """Check if abstention was due to policy/safety filters."""
        policy_keywords = [
            "policy", "forbidden", "blocked", "not allowed", "inappropriate",
            "sensitive", "safety", "filtered", "restricted", "prohibited",
            "compliance", "regulation", "breach", "violation"
        ]
        return any(kw in reason for kw in policy_keywords)
    
    def _is_hallucination_abstention(self, reason: str, has_context: bool) -> bool:
        """Check if abstention reason appears fabricated."""
        if not reason or len(reason) < 5:
            return False
        
        # Hallucination signatures
        nonsense_markers = [
            "i cannot", "i don't have", "i'm not able", "i lack",
            "i don't know", "i'm not equipped", "i haven't",
            "i cannot answer", "i'm unable"
        ]
        
        # These are common when LLM is avoiding (not hallucinating)
        legitimate_reasons = [
            "insufficient", "incomplete", "not mentioned", "not provided",
            "not found", "not available", "context", "information"
        ]
        
        has_hallucination_marker = any(m in reason for m in nonsense_markers)
        has_legitimate_reason = any(m in reason for m in legitimate_reasons)
        
        # Hallucination if generic excuse without legitimate reason
        return has_hallucination_marker and not has_legitimate_reason and has_context
    
    def _is_threshold_abstention(self, reason: str) -> bool:
        """Check if abstention was due to confidence threshold."""
        threshold_keywords = [
            "confident", "confidence", "sure", "certain", "confident",
            "low confidence", "not confident", "uncertain", "unsure",
            "likely", "probably", "maybe", "might", "could be",
            "threshold", "minimum", "score"
        ]
        return any(kw in reason for kw in threshold_keywords)
    
    def _is_confident_abstention(self, reason: str) -> bool:
        """Check if LLM is confident in its abstention (problematic)."""
        confident_keywords = [
            "i'm confident", "certain", "definitely", "absolutely",
            "clearly", "obviously", "undoubtedly", "without doubt",
            "cannot answer", "should not answer", "must abstain"
        ]
        return any(kw in reason for kw in confident_keywords)
    
    def _assess_context_quality(
        self,
        context_chunks: List[Dict[str, Any]],
        retrieval_quality: Optional[Dict[str, Any]] = None
    ) -> float:
        """Score context quality 0.0-1.0."""
        if not context_chunks:
            return 0.0
        
        # Basic scoring
        score = 0.5  # Base score for having any context
        
        # Boost for quantity
        if len(context_chunks) >= 3:
            score += 0.2
        elif len(context_chunks) >= 1:
            score += 0.1
        
        # Use retrieval quality metrics if available
        if retrieval_quality:
            semantic_score = retrieval_quality.get("semantic_relevance_score", 0.0)
            reranker_score = retrieval_quality.get("reranker_score", 0.0)
            
            avg_quality = (float(semantic_score) + min(1.0, float(reranker_score) / 10.0)) / 2.0
            score = max(score, avg_quality)
        
        # Check for meaningful content
        total_length = sum(len(str(chunk.get("text", ""))) for chunk in context_chunks)
        if total_length > 500:
            score += 0.1
        
        return min(1.0, score)


# Convenience function for module-level usage
def detect_false_abstention(
    query: str,
    abstention_reason: str,
    context_chunks: List[Dict[str, Any]],
    retrieval_quality: Optional[Dict[str, Any]] = None,
) -> FalseAbstentionAnalysis:
    """Convenience function for false abstention detection."""
    detector = FalseAbstentionDetector()
    return detector.analyze(
        query=query,
        abstention_reason=abstention_reason,
        context_chunks=context_chunks,
        retrieval_quality=retrieval_quality,
    )
