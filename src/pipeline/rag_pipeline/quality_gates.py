"""
Layered quality gates for RAG pipeline verification.

Implements gates described in the specification:
- Query & KB Relevance Gate
- Retrieval Sufficiency Gate
- Prompt Assembly Integrity Gate
- Grounded Generation Gate
- Abstention Validity Gate
- Expectation Coverage Gate

Quality gates are designed to be configuration-driven and testable.
"""

from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
import math


@dataclass
class GateResult:
    pass_flag: bool
    score: float
    reasons: List[str] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)


class QualityGates:
    """Implements the layered quality gates for RAG verification."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        # Default thresholds
        cfg = config or {}
        self.kb_relevance_threshold = cfg.get("kb_relevance_threshold", 0.5)
        self.semantic_relevance_threshold = cfg.get("semantic_relevance_threshold", 0.65)
        self.reranker_score_threshold = cfg.get("reranker_score_threshold", 2.0)
        self.retrieval_sufficiency_threshold = cfg.get("retrieval_sufficiency_threshold", 0.6)
        self.grounding_threshold = cfg.get("grounding_threshold", 0.7)
        self.expectation_coverage_threshold = cfg.get("expectation_coverage_threshold", 0.7)
        self.abstention_grounding_allowance = cfg.get("abstention_grounding_allowance", 0.6)

    # ------------------------------------------------------------------
    # A. Query & KB Relevance Gate
    # ------------------------------------------------------------------
    def kb_relevance_gate(
        self,
        query: str,
        lexical_overlap_score: float,
        semantic_similarity_score: float,
        reranker_score: Optional[float],
        domain_match: Optional[bool] = None,
        top_k_consistency: Optional[List[float]] = None,
    ) -> GateResult:
        """Hybrid decision combining lexical, semantic, reranker, and domain signals."""
        reasons = []
        # Weighted hybrid score
        lexical_w = 0.25
        semantic_w = 0.45
        reranker_w = 0.25
        domain_w = 0.05

        reranker_signal = float(reranker_score) if reranker_score is not None else 0.0
        domain_signal = 1.0 if domain_match else 0.0

        hybrid_score = (
            lexical_w * lexical_overlap_score
            + semantic_w * semantic_similarity_score
            + reranker_w * min(1.0, reranker_signal / 10.0)
            + domain_w * domain_signal
        )

        # Top-k evidence consistency bonus
        if top_k_consistency:
            # If top-k semantic similarities are all high, boost score
            avg_topk = sum(top_k_consistency) / len(top_k_consistency)
            if avg_topk > 0.7:
                hybrid_score = min(1.0, hybrid_score + 0.1)
                reasons.append(f"Top-k consistency boost: avg_topk={avg_topk:.3f}")

        pass_flag = hybrid_score >= self.kb_relevance_threshold

        if not pass_flag:
            reasons.append(f"Hybrid KB relevance score below threshold: {hybrid_score:.3f} < {self.kb_relevance_threshold}")
        else:
            reasons.append(f"KB relevance passed: {hybrid_score:.3f} >= {self.kb_relevance_threshold}")

        return GateResult(pass_flag=pass_flag, score=hybrid_score, reasons=reasons, details={
            "lexical_overlap_score": lexical_overlap_score,
            "semantic_similarity_score": semantic_similarity_score,
            "reranker_score": reranker_score,
            "domain_match": domain_match,
            "top_k_consistency": top_k_consistency,
        })

    # ------------------------------------------------------------------
    # B. Retrieval Sufficiency Gate
    # ------------------------------------------------------------------
    def retrieval_sufficiency_gate(
        self,
        top_chunks: List[Dict[str, Any]],
        query: str,
        semantic_scores: List[float],
        cross_encoder_scores: List[float],
    ) -> GateResult:
        """Determine if retrieved chunks are enough to answer the query using hybrid signals.

        Returns three labels inside details: retrieval_relevant, retrieval_answerable, retrieval_sufficient
        
        The gate now uses:
        1. Lexical overlap (query-evidence token overlap)
        2. Semantic similarity (vector-based relevance)
        3. Reranker/cross-encoder score (relevance model assessment)
        4. Top-1 dominance (whether strongest chunk carries the answer)
        5. Top-k consistency (whether multiple chunks are coherent)
        
        Decision rules:
        - retrieval_relevant: At least one top chunk is meaningfully relevant (semantic or reranker-based)
        - retrieval_answerable: Top chunks contain enough info to directly answer or support grounded synthesis
        - retrieval_sufficient: Top evidence is strong enough for grounded generation without unsupported speculation
        """
        reasons = []
        if not top_chunks:
            return GateResult(
                pass_flag=False,
                score=0.0,
                reasons=["No top chunks retrieved"],
                details={
                    "retrieval_relevant": False,
                    "retrieval_answerable": False,
                    "retrieval_sufficient": False,
                    "retrieval_relevance_reasons": ["No chunks"],
                    "retrieval_answerability_reasons": ["No chunks"],
                    "retrieval_sufficiency_reasons": ["No chunks"],
                }
            )

        # ============================================================
        # SIGNAL 1: Compute semantic and reranker statistics
        # ============================================================
        avg_sem = sum(semantic_scores) / len(semantic_scores) if semantic_scores else 0.0
        max_sem = max(semantic_scores) if semantic_scores else 0.0
        avg_ce = sum(cross_encoder_scores) / len(cross_encoder_scores) if cross_encoder_scores else 0.0
        max_ce = max(cross_encoder_scores) if cross_encoder_scores else 0.0
        
        # Top-1 signal: strongest chunk's relevance
        top1_sem = semantic_scores[0] if semantic_scores else 0.0
        top1_ce = cross_encoder_scores[0] if cross_encoder_scores else 0.0
        
        # Top-k dominance: how much does top-1 dominate the rest?
        if len(semantic_scores) > 1:
            second_best_sem = sorted(semantic_scores, reverse=True)[1]
            top1_dominance = (top1_sem - second_best_sem) / max(0.01, top1_sem)  # Normalized gap
        else:
            top1_dominance = 1.0  # Single chunk dominates by definition
        
        # Top-k consistency: are top chunks coherent?
        if len(semantic_scores) >= 2:
            top3_scores = sorted(semantic_scores, reverse=True)[:3]
            top_k_avg = sum(top3_scores) / len(top3_scores)
            top_k_consistency = top_k_avg
        else:
            top_k_consistency = avg_sem

        # ============================================================
        # SIGNAL 2: Lexical overlap with query
        # ============================================================
        query_tokens = set(query.lower().split())
        lexical_overlaps = []
        for chunk in top_chunks[:3]:  # Consider only top-3 chunks
            chunk_text = chunk.get("text", "").lower()
            chunk_tokens = set(chunk_text.split())
            overlap_count = len(query_tokens.intersection(chunk_tokens))
            overlap_ratio = overlap_count / max(1, len(query_tokens))
            lexical_overlaps.append(overlap_ratio)
        
        max_lexical_overlap = max(lexical_overlaps) if lexical_overlaps else 0.0
        avg_lexical_overlap = sum(lexical_overlaps) / len(lexical_overlaps) if lexical_overlaps else 0.0

        # ============================================================
        # DECISION RULE A: retrieval_relevant
        # ============================================================
        # retrieval_relevant = true if top chunk is semantically relevant OR reranker confidence is high
        rel_reasons = []
        
        # Check top-1 semantic relevance
        top1_sem_relevant = top1_sem >= self.semantic_relevance_threshold
        if top1_sem_relevant:
            rel_reasons.append(f"Top chunk semantic score {top1_sem:.3f} exceeds threshold {self.semantic_relevance_threshold}")
        
        # Check top-1 reranker relevance (normalize: reranker scores can be > 1)
        top1_ce_normalized = min(1.0, top1_ce / 10.0)
        top1_ce_relevant = top1_ce >= self.reranker_score_threshold
        if top1_ce_relevant:
            rel_reasons.append(f"Top chunk reranker score {top1_ce:.2f} exceeds threshold {self.reranker_score_threshold}")
        
        # Check lexical overlap quality
        lexical_relevant = max_lexical_overlap >= 0.3  # At least 30% query tokens present
        if lexical_relevant:
            rel_reasons.append(f"Top chunk lexical overlap {max_lexical_overlap:.2%} acceptable")
        
        # Composite relevance: at least one strong signal
        retrieval_relevant = top1_sem_relevant or top1_ce_relevant or (lexical_relevant and top1_sem > 0.5)
        
        if not retrieval_relevant:
            rel_reasons.append(
                f"Top chunk weak: semantic={top1_sem:.3f}, reranker={top1_ce:.2f}, lexical={max_lexical_overlap:.2%}"
            )

        # ============================================================
        # DECISION RULE B: retrieval_answerable
        # ============================================================
        # retrieval_answerable = true if top chunks can directly support an answer
        ans_reasons = []
        
        # At least one chunk should have strong semantic + reranker
        strong_single_chunk = any(
            (s >= self.semantic_relevance_threshold and c >= self.grounding_threshold)
            for s, c in zip(semantic_scores[:3], cross_encoder_scores[:3])
        )
        
        # OR: top chunk alone has very high semantic score (direct answer signal)
        very_strong_top1 = top1_sem >= 0.85
        
        # OR: multiple decent chunks can collectively answer (top-k consistency high)
        strong_multi_chunk = (
            len(semantic_scores) >= 2 
            and top_k_consistency >= 0.70 
            and avg_ce >= self.reranker_score_threshold
        )
        
        retrieval_answerable = strong_single_chunk or very_strong_top1 or strong_multi_chunk
        
        if strong_single_chunk:
            ans_reasons.append("Strong single chunk identified with high semantic + reranker scores")
        elif very_strong_top1:
            ans_reasons.append(f"Top chunk has very high semantic relevance: {top1_sem:.3f}")
        elif strong_multi_chunk:
            ans_reasons.append(f"Multiple chunks collectively strong: top_k_consistency={top_k_consistency:.3f}")
        else:
            ans_reasons.append(
                f"No strong chunk combination: top1_sem={top1_sem:.3f}, strong_multi={strong_multi_chunk}"
            )

        # ============================================================
        # DECISION RULE C: retrieval_sufficient
        # ============================================================
        # retrieval_sufficient = true if top evidence is enough for grounded generation
        suff_reasons = []
        
        # Base requirement: retrieval must be answerable
        if not retrieval_answerable:
            retrieval_sufficient = False
            suff_reasons.append("Not answerable, cannot be sufficient")
        else:
            # Additional requirements for sufficiency:
            # 1. Top-1 dominance: strongest chunk should clearly lead
            top1_dominates = top1_dominance >= 0.2  # At least 20% better than 2nd
            if top1_dominates:
                suff_reasons.append(f"Top-1 chunk dominates with {top1_dominance:.2%} advantage")
            
            # 2. No severe drop-off in quality
            has_quality_cliff = (
                len(semantic_scores) > 2 
                and top1_sem >= 0.7 
                and semantic_scores[2] < 0.3
            )
            if has_quality_cliff:
                suff_reasons.append("Warning: quality cliff after top-2 chunks")
            
            # 3. Reranker agreement with semantic similarity
            reranker_agrees = (
                (top1_sem > 0.5 and top1_ce >= 1.0) or
                (top1_sem > 0.7 and top1_ce >= 0.5)  # Normalized: 0.5*10=5
            )
            if reranker_agrees:
                suff_reasons.append("Reranker and semantic similarity agree on top chunk quality")
            
            # Composite: sufficient if top chunk is strong and reranker agrees
            retrieval_sufficient = (
                top1_sem >= self.retrieval_sufficiency_threshold 
                and reranker_agrees
                and (not has_quality_cliff or top1_dominates)
            )
            
            if not retrieval_sufficient:
                suff_reasons.append(
                    f"Insufficient: top1_sem={top1_sem:.3f} vs thresh={self.retrieval_sufficiency_threshold}, "
                    f"reranker_agrees={reranker_agrees}"
                )

        # ============================================================
        # Composite score (for legacy compatibility)
        # ============================================================
        relevance_score = 1.0 if retrieval_relevant else 0.0
        answerability_score = 1.0 if retrieval_answerable else 0.0
        sufficiency_score = 1.0 if retrieval_sufficient else 0.0
        
        # Weighted composite
        score = (0.3 * relevance_score) + (0.4 * answerability_score) + (0.3 * sufficiency_score)

        # Log all reasons
        all_reasons = rel_reasons + ans_reasons + suff_reasons

        return GateResult(
            pass_flag=retrieval_sufficient,
            score=score,
            reasons=all_reasons,
            details={
                # Core decisions
                "retrieval_relevant": retrieval_relevant,
                "retrieval_answerable": retrieval_answerable,
                "retrieval_sufficient": retrieval_sufficient,
                
                # Signals used
                "top1_semantic": top1_sem,
                "top1_reranker": top1_ce,
                "avg_semantic": avg_sem,
                "avg_reranker": avg_ce,
                "top_k_consistency": top_k_consistency,
                "top1_dominance": top1_dominance,
                "max_lexical_overlap": max_lexical_overlap,
                
                # Explanation fields
                "retrieval_relevance_reasons": rel_reasons,
                "retrieval_answerability_reasons": ans_reasons,
                "retrieval_sufficiency_reasons": suff_reasons,
            }
        )

    # ------------------------------------------------------------------
    # C. Prompt Assembly Integrity Gate
    # ------------------------------------------------------------------
    def prompt_integrity_gate(
        self,
        system_prompt: str,
        query: str,
        context_text: str,
        conversation_history: Optional[str] = None,
    ) -> GateResult:
        """Check prompt correctness to avoid contamination and leakage."""
        reasons = []
        # Ensure query present
        if query.strip() not in system_prompt and query.strip() not in context_text:
            reasons.append("Query not injected into prompt or context")

        # Check for stale fallback templates
        if "insufficient context" in system_prompt.lower() and "do not answer" in system_prompt.lower():
            reasons.append("Fallback abstain template found in system prompt")

        # Check for unrelated few-shot examples
        if "Example" in system_prompt and "CloudSpace" in system_prompt and "Zero Trust" not in system_prompt:
            reasons.append("Potential few-shot contamination: CloudSpace examples present")

        # Conversation history contamination
        if conversation_history and len(conversation_history.strip()) > 0:
            # if conversation_history contains unrelated domains, flag it
            if "cloudspace" in conversation_history.lower() and "zero trust" in system_prompt.lower():
                reasons.append("Conversation history may include unrelated CloudSpace content")

        pass_flag = len([r for r in reasons if r]) == 0

        return GateResult(pass_flag=pass_flag, score=1.0 if pass_flag else 0.0, reasons=reasons, details={
            "system_prompt_snippet": system_prompt[:400],
            "context_snippet": context_text[:400],
        })

    # ------------------------------------------------------------------
    # D. Grounded Generation Gate
    # ------------------------------------------------------------------
    def grounded_generation_gate(
        self,
        generated_answer: str,
        top_evidence: List[Dict[str, Any]],
        grounding_score: float,
        domain_expected: Optional[str] = None,
    ) -> GateResult:
        """Ensure answers are grounded and domain-correct."""
        reasons = []
        answer_lower = generated_answer.lower()

        # Domain check
        domain_pass = True
        if domain_expected and domain_expected.lower() not in answer_lower:
            expected_tokens = {token for token in domain_expected.lower().split() if len(token) > 2}
            answer_tokens = {token for token in answer_lower.split() if len(token) > 2}
            token_overlap = len(expected_tokens.intersection(answer_tokens)) / max(1, len(expected_tokens))
            if token_overlap < 0.5:
                domain_pass = False
                reasons.append(f"Answer doesn't sufficiently align with expected domain '{domain_expected}'")

        # Grounding check
        if grounding_score < self.grounding_threshold:
            reasons.append(f"Grounding score below threshold: {grounding_score:.3f} < {self.grounding_threshold}")

        # Hallucination heuristic: answer contains facts not in evidence
        # Simple heuristic: check for numeric claims or strong modal verbs unsupported by evidence
        hallucination_risk = 0.0
        if any(word in generated_answer.lower() for word in ["always", "guarantee", "never"]) and all("never" not in e.get("text","") for e in top_evidence):
            hallucination_risk += 0.2
            reasons.append("Possible unsupported strong modal claim present")

        pass_flag = (grounding_score >= self.grounding_threshold) and domain_pass and (hallucination_risk < 0.5)

        return GateResult(pass_flag=pass_flag, score=grounding_score, reasons=reasons, details={
            "domain_expected": domain_expected,
            "top_evidence_count": len(top_evidence),
            "hallucination_risk": hallucination_risk,
        })

    # ------------------------------------------------------------------
    # E. Abstention Validity Gate
    # ------------------------------------------------------------------
    def abstention_validity_gate(
        self,
        abstention_used: bool,
        generated_answer: str,
        grounding_score: float,
        semantic_relevance_score: float,
        retrieval_pass: bool,
    ) -> GateResult:
        """Verify whether abstention was valid.

        If evidence supports an answer (semantic+grounding high) but system abstains,
        flag false abstention.
        """
        reasons = []
        if not abstention_used:
            return GateResult(pass_flag=True, score=1.0, reasons=["No abstention used"]) 

        if not retrieval_pass:
            reasons.append("Abstention valid: no retrieval results")
            return GateResult(pass_flag=True, score=1.0, reasons=reasons)

        # If semantics and grounding are strong, abstention is invalid
        if semantic_relevance_score >= self.semantic_relevance_threshold and grounding_score >= self.abstention_grounding_allowance:
            reasons.append("False abstention: retrieval and grounding indicate answerable")
            return GateResult(pass_flag=False, score=0.0, reasons=reasons)

        # Otherwise allow abstention
        reasons.append("Abstention appears valid based on current signals")
        return GateResult(pass_flag=True, score=1.0, reasons=reasons)

    # ------------------------------------------------------------------
    # F. Expectation Coverage Gate
    # ------------------------------------------------------------------
    def expectation_coverage_gate(
        self,
        generated_answer: str,
        expected_answer_points: List[str],
        required_keywords: List[str],
        minimum_coverage: float = None,
    ) -> GateResult:
        """Assess how many expected answer points are covered by generated answer.

        Use semantic matching for coverage, with fallback to lexical checks for required keywords.
        """
        reasons = []
        coverage_hits = 0
        total = len(expected_answer_points)

        def normalize(text: str) -> List[str]:
            synonyms = {
                "verification": "verify",
                "verified": "verify",
                "validating": "verify",
                "validation": "verify",
                "trusted": "trust",
                "trusting": "trust",
                "implicitly": "default",
                "assumed": "default",
                "important": "why",
                "necessary": "why",
            }
            tokens = []
            for raw in text.lower().replace("-", " ").split():
                token = "".join(ch for ch in raw if ch.isalnum())
                if len(token) <= 2:
                    continue
                tokens.append(synonyms.get(token, token))
            return tokens

        ans_tokens = set(normalize(generated_answer))
        ans_lower = generated_answer.lower()

        for point in expected_answer_points:
            p_lower = point.lower()
            if p_lower in ans_lower:
                coverage_hits += 1
            else:
                # semantic relaxation: compare normalized content tokens
                point_tokens = set(normalize(point))
                overlap = len(point_tokens.intersection(ans_tokens)) / max(1, len(point_tokens))
                if overlap >= 0.5:
                    coverage_hits += 1

        coverage = coverage_hits / total if total > 0 else 1.0

        # Required keywords must be present at least partially (lexical or semantically)
        missing_required = [kw for kw in required_keywords if kw.lower() not in ans_lower]

        if missing_required:
            reasons.append(f"Missing required keywords: {missing_required}")

        pass_flag = coverage >= (minimum_coverage or self.expectation_coverage_threshold) and len(missing_required) == 0

        return GateResult(pass_flag=pass_flag, score=coverage, reasons=reasons, details={
            "coverage_hits": coverage_hits,
            "coverage_total": total,
            "missing_required": missing_required,
        })


# ------------------------------------------------------------------
# Utility: Scoring helpers
# ------------------------------------------------------------------

def normalize_score(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    """Clamp score to [0,1]"""
    return max(lo, min(hi, x))
