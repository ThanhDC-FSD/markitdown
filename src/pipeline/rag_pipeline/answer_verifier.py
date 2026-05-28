"""
Answer Verification & Quality Gate System for RAG Pipeline
Validates answer accuracy, sources, completeness, and consistency
"""

from typing import List, Dict, Any, Tuple, Optional
from dataclasses import dataclass, asdict, field
import json
from datetime import datetime
from enum import Enum
import re


class VerificationStatus(Enum):
    """Answer verification status levels"""
    VERIFIED = "verified"  # Passed all quality gates
    PARTIAL = "partial"    # Passed core gates, warnings present
    UNVERIFIED = "unverified"  # Failed critical gates
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"  # Not enough source material


@dataclass
class SourceCitation:
    """Evidence source for answer component"""
    chunk_id: str
    chunk_content: str
    confidence_score: float
    semantic_similarity: float
    metadata_domain: str
    page_ref: Optional[str] = None
    
    def to_dict(self):
        return asdict(self)


@dataclass
class AnswerComponent:
    """Individual answer statement with verification"""
    statement: str
    component_type: str  # fact, explanation, example, definition
    citations: List[SourceCitation] = field(default_factory=list)
    verification_status: VerificationStatus = VerificationStatus.UNVERIFIED
    confidence_score: float = 0.0
    is_contradicted: bool = False
    contradiction_evidence: Optional[List[str]] = None
    
    def to_dict(self):
        return {
            "statement": self.statement,
            "component_type": self.component_type,
            "citations": [c.to_dict() for c in self.citations],
            "verification_status": self.verification_status.value,
            "confidence_score": self.confidence_score,
            "is_contradicted": self.is_contradicted,
            "contradiction_evidence": self.contradiction_evidence,
        }


@dataclass
class VerifiedAnswer:
    """Complete answer with verification report"""
    query: str
    answer_text: str
    components: List[AnswerComponent] = field(default_factory=list)
    overall_status: VerificationStatus = VerificationStatus.UNVERIFIED
    quality_score: float = 0.0  # 0.0-1.0
    completeness_score: float = 0.0  # Coverage of query aspects
    accuracy_score: float = 0.0  # Source fidelity
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    quality_gates_passed: Dict[str, bool] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)
    
    def to_dict(self):
        return {
            "query": self.query,
            "answer_text": self.answer_text,
            "components": [c.to_dict() for c in self.components],
            "overall_status": self.overall_status.value,
            "quality_score": self.quality_score,
            "completeness_score": self.completeness_score,
            "accuracy_score": self.accuracy_score,
            "timestamp": self.timestamp,
            "quality_gates_passed": self.quality_gates_passed,
            "warnings": self.warnings,
            "suggestions": self.suggestions,
        }


class AnswerVerifier:
    """
    Verification system for RAG answers
    
    Quality Gates:
    1. Source Fidelity - answer matches source content
    2. Evidence Coverage - answer backed by retrieved chunks
    3. Consistency - no contradictions within answer
    4. Completeness - addresses all query aspects
    5. Confidence Threshold - meets minimum confidence
    """
    
    def __init__(self):
        self.min_confidence_threshold = 0.65
        self.min_evidence_citations = 2
        self.min_quality_score = 0.70
        self.min_completeness_score = 0.60
        self.known_facts = {}  # Reference facts for validation
    
    def add_reference_facts(self, facts: Dict[str, List[str]]):
        """Add known facts for validation (from spec documents, etc)"""
        self.known_facts.update(facts)
    
    def verify_answer(
        self,
        query: str,
        answer_text: str,
        retrieved_chunks: List[Dict[str, Any]],
        metadata: Dict[str, Any] = None
    ) -> VerifiedAnswer:
        """
        Verify answer quality against multiple gates
        
        Args:
            query: Original query
            answer_text: Generated answer
            retrieved_chunks: Retrieved source chunks
            metadata: Additional context
            
        Returns:
            VerifiedAnswer with detailed verification report
        """
        verified_answer = VerifiedAnswer(query=query, answer_text=answer_text)
        
        # Gate 1: Extract and verify answer components
        components = self._extract_answer_components(answer_text, query)
        verified_answer.components = components
        
        # Gate 2: Match components to evidence
        verified_answer = self._verify_component_evidence(
            verified_answer, retrieved_chunks
        )
        
        # Gate 3: Check for contradictions
        contradiction_report = self._check_internal_consistency(
            verified_answer.components, retrieved_chunks
        )
        verified_answer.warnings.extend(contradiction_report["warnings"])
        
        # Gate 4: Assess completeness
        completeness = self._assess_completeness(query, verified_answer.components)
        verified_answer.completeness_score = completeness
        
        # Gate 5: Calculate final scores and status
        verified_answer = self._calculate_final_scores(verified_answer)
        
        return verified_answer
    
    def _extract_answer_components(
        self, answer_text: str, query: str
    ) -> List[AnswerComponent]:
        """Break answer into verifiable components"""
        components = []
        
        # Split by common delimiters
        sentences = re.split(r'(?<=[.!?])\s+|(?<=:)\n|•|[-]', answer_text)
        sentences = [s.strip() for s in sentences if s.strip() and len(s.strip()) > 10]
        
        for i, sentence in enumerate(sentences):
            # Classify component type
            comp_type = self._classify_component(sentence, query)
            
            component = AnswerComponent(
                statement=sentence,
                component_type=comp_type,
            )
            components.append(component)
        
        return components
    
    def _classify_component(self, text: str, query: str) -> str:
        """Classify statement type"""
        text_lower = text.lower()
        query_lower = query.lower()
        
        if any(word in text_lower for word in ["example", "such as", "for instance", "like"]):
            return "example"
        elif any(word in text_lower for word in ["is", "means", "refers", "defined"]):
            return "definition"
        elif any(word in text_lower for word in ["improve", "reduce", "increase", "enable"]):
            return "benefit"
        elif any(word in text_lower for word in ["because", "since", "due to", "caused"]):
            return "reason"
        else:
            return "fact"
    
    def _verify_component_evidence(
        self,
        verified_answer: VerifiedAnswer,
        retrieved_chunks: List[Dict[str, Any]]
    ) -> VerifiedAnswer:
        """Match answer components to source evidence"""
        
        for component in verified_answer.components:
            citations = self._find_supporting_evidence(
                component.statement, retrieved_chunks
            )
            
            if citations:
                component.citations = citations
                # Calculate confidence from citations
                avg_confidence = sum(c.confidence_score for c in citations) / len(citations)
                component.confidence_score = avg_confidence
                
                if avg_confidence >= self.min_confidence_threshold:
                    component.verification_status = VerificationStatus.VERIFIED
                elif avg_confidence >= self.min_confidence_threshold * 0.85:
                    component.verification_status = VerificationStatus.PARTIAL
                    verified_answer.warnings.append(
                        f"Component '{component.statement[:50]}...' has borderline confidence: {avg_confidence:.2f}"
                    )
                else:
                    component.verification_status = VerificationStatus.UNVERIFIED
                    verified_answer.warnings.append(
                        f"Component '{component.statement[:50]}...' lacks sufficient evidence confidence"
                    )
            else:
                component.verification_status = VerificationStatus.INSUFFICIENT_EVIDENCE
                verified_answer.warnings.append(
                    f"Component '{component.statement[:50]}...' has no supporting evidence"
                )
        
        return verified_answer
    
    def _find_supporting_evidence(
        self, statement: str, chunks: List[Dict[str, Any]]
    ) -> List[SourceCitation]:
        """Find chunks that support a statement"""
        citations = []
        statement_words = set(statement.lower().split())
        
        for chunk in chunks:
            chunk_text = chunk.get("content", "").lower()
            chunk_words = set(chunk_text.split())
            
            # Calculate word overlap
            overlap = statement_words & chunk_words
            overlap_ratio = len(overlap) / len(statement_words) if statement_words else 0
            
            # Use existing confidence score from chunk metadata
            chunk_confidence = chunk.get("confidence_score", 0.0)
            semantic_similarity = chunk.get("semantic_similarity", 0.0)
            
            # Combine scores
            if overlap_ratio >= 0.3 and chunk_confidence >= 0.5:  # At least 30% word overlap
                citation = SourceCitation(
                    chunk_id=chunk.get("chunk_id", "unknown"),
                    chunk_content=chunk_text[:200],  # First 200 chars
                    confidence_score=chunk_confidence,
                    semantic_similarity=semantic_similarity,
                    metadata_domain=chunk.get("metadata", {}).get("domain", "UNKNOWN"),
                    page_ref=chunk.get("metadata", {}).get("page_number"),
                )
                citations.append(citation)
        
        # Sort by confidence score (highest first)
        citations.sort(key=lambda x: x.confidence_score, reverse=True)
        
        # Return top 3 most confident citations
        return citations[:3]
    
    def _check_internal_consistency(
        self, components: List[AnswerComponent], chunks: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Check for contradictions within answer and with sources"""
        warnings = []
        
        # Extract key claims from components
        claims = [c.statement for c in components if c.component_type in ["fact", "definition"]]
        
        # Check for contradictory pairs
        for i, claim1 in enumerate(claims):
            for claim2 in claims[i+1:]:
                if self._are_contradictory(claim1, claim2):
                    warnings.append(
                        f"Potential contradiction detected:\n  '{claim1[:60]}...'\n  vs\n  '{claim2[:60]}...'"
                    )
        
        # Check against known facts
        for component in components:
            if component.component_type == "fact":
                for fact_category, fact_list in self.known_facts.items():
                    for known_fact in fact_list:
                        if self._statement_contradicts_fact(component.statement, known_fact):
                            component.is_contradicted = True
                            component.contradiction_evidence = [known_fact]
                            warnings.append(
                                f"Component may contradict known fact: {known_fact}"
                            )
        
        return {"warnings": warnings, "contradiction_count": len(warnings)}
    
    def _are_contradictory(self, claim1: str, claim2: str) -> bool:
        """Simple contradiction detection"""
        negation_words = {"no", "not", "never", "cannot", "impossible", "doesn't"}
        
        claim1_lower = claim1.lower()
        claim2_lower = claim2.lower()
        
        # Check if one has negation and the other doesn't
        claim1_negated = any(word in claim1_lower.split() for word in negation_words)
        claim2_negated = any(word in claim2_lower.split() for word in negation_words)
        
        if claim1_negated != claim2_negated:
            # Extract main subject (simplified)
            words1 = set(w for w in claim1_lower.split() if len(w) > 4)
            words2 = set(w for w in claim2_lower.split() if len(w) > 4)
            overlap = words1 & words2
            
            if len(overlap) >= 2:  # At least 2 overlapping content words
                return True
        
        return False
    
    def _statement_contradicts_fact(self, statement: str, known_fact: str) -> bool:
        """Check if statement contradicts known fact"""
        negation_words = {"no", "not", "never", "cannot", "doesn't"}
        statement_lower = statement.lower()
        fact_lower = known_fact.lower()
        
        # If statement negates the known fact
        if any(word in statement_lower for word in negation_words):
            # Extract main nouns/subjects
            statement_nouns = set(w for w in statement_lower.split() if len(w) > 3)
            fact_nouns = set(w for w in fact_lower.split() if len(w) > 3)
            
            if statement_nouns & fact_nouns:
                return True
        
        return False
    
    def _assess_completeness(
        self, query: str, components: List[AnswerComponent]
    ) -> float:
        """Assess how completely answer addresses query"""
        query_aspects = self._extract_query_aspects(query)
        
        if not query_aspects:
            return 0.5
        
        # Check how many query aspects are addressed
        answer_text = " ".join([c.statement for c in components])
        answer_lower = answer_text.lower()
        
        covered_aspects = 0
        for aspect in query_aspects:
            if aspect.lower() in answer_lower:
                covered_aspects += 1
        
        completeness = covered_aspects / len(query_aspects)
        return min(1.0, completeness)
    
    def _extract_query_aspects(self, query: str) -> List[str]:
        """Extract key aspects from query"""
        # Remove common stop words and split by punctuation
        stop_words = {"what", "why", "how", "when", "where", "is", "are", "the", "a", "an"}
        query_lower = query.lower()
        
        # Split on punctuation and stopwords
        aspects = [
            w.strip() for w in re.split(r'[,;?!]|\s+', query_lower)
            if w.strip() and len(w.strip()) > 3 and w.strip() not in stop_words
        ]
        
        return list(set(aspects))  # Remove duplicates
    
    def _calculate_final_scores(
        self, verified_answer: VerifiedAnswer
    ) -> VerifiedAnswer:
        """Calculate final quality scores and status"""
        
        # Calculate accuracy from components
        if verified_answer.components:
            verified_components = sum(
                1 for c in verified_answer.components
                if c.verification_status == VerificationStatus.VERIFIED
            )
            partial_components = sum(
                1 for c in verified_answer.components
                if c.verification_status == VerificationStatus.PARTIAL
            )
            
            accuracy = (verified_components + partial_components * 0.5) / len(verified_answer.components)
            verified_answer.accuracy_score = accuracy
        
        # Calculate overall quality score (weighted)
        weights = {
            "accuracy": 0.40,
            "completeness": 0.30,
            "confidence": 0.20,
            "consistency": 0.10,
        }
        
        # Consistency score (1.0 - normalized warnings)
        consistency_score = max(0.0, 1.0 - (len(verified_answer.warnings) * 0.1))
        
        # Average confidence from components
        avg_confidence = (
            sum(c.confidence_score for c in verified_answer.components) / len(verified_answer.components)
            if verified_answer.components else 0.0
        )
        
        quality_score = (
            verified_answer.accuracy_score * weights["accuracy"] +
            verified_answer.completeness_score * weights["completeness"] +
            avg_confidence * weights["confidence"] +
            consistency_score * weights["consistency"]
        )
        
        verified_answer.quality_score = quality_score
        
        # Determine overall status
        verified_answer.quality_gates_passed = {
            "min_confidence": avg_confidence >= self.min_confidence_threshold,
            "min_quality_score": quality_score >= self.min_quality_score,
            "min_completeness": verified_answer.completeness_score >= self.min_completeness_score,
            "no_contradictions": len([c for c in verified_answer.components if c.is_contradicted]) == 0,
            "sufficient_evidence": len([c for c in verified_answer.components if c.citations]) >= self.min_evidence_citations,
        }
        
        gates_passed = sum(1 for v in verified_answer.quality_gates_passed.values() if v)
        
        if gates_passed == 5:
            verified_answer.overall_status = VerificationStatus.VERIFIED
        elif gates_passed >= 3:
            verified_answer.overall_status = VerificationStatus.PARTIAL
        else:
            verified_answer.overall_status = VerificationStatus.UNVERIFIED
        
        # Add suggestions
        if avg_confidence < self.min_confidence_threshold:
            verified_answer.suggestions.append(
                f"Add more specific citations. Current confidence: {avg_confidence:.2f}"
            )
        
        if verified_answer.completeness_score < self.min_completeness_score:
            verified_answer.suggestions.append(
                "Answer may not fully address all query aspects. Consider expanding coverage."
            )
        
        if verified_answer.warnings:
            verified_answer.suggestions.append(
                "Review warnings above. Some components may need refinement or additional sources."
            )
        
        return verified_answer
    
    def generate_verification_report(self, verified_answer: VerifiedAnswer) -> str:
        """Generate human-readable verification report"""
        report = []
        report.append("=" * 80)
        report.append(f"ANSWER VERIFICATION REPORT")
        report.append(f"Query: {verified_answer.query}")
        report.append("=" * 80)
        report.append("")
        
        # Status and scores
        report.append(f"Overall Status: {verified_answer.overall_status.value.upper()}")
        report.append(f"Quality Score: {verified_answer.quality_score:.1%}")
        report.append(f"Accuracy Score: {verified_answer.accuracy_score:.1%}")
        report.append(f"Completeness Score: {verified_answer.completeness_score:.1%}")
        report.append("")
        
        # Quality gates
        report.append("Quality Gates:")
        for gate_name, passed in verified_answer.quality_gates_passed.items():
            status = "✓ PASSED" if passed else "✗ FAILED"
            report.append(f"  • {gate_name}: {status}")
        report.append("")
        
        # Answer components with citations
        report.append("Answer Components:")
        for i, component in enumerate(verified_answer.components, 1):
            report.append(f"\n  [{i}] {component.statement}")
            report.append(f"      Type: {component.component_type}")
            report.append(f"      Status: {component.verification_status.value}")
            report.append(f"      Confidence: {component.confidence_score:.1%}")
            
            if component.citations:
                report.append(f"      Citations ({len(component.citations)}):")
                for j, citation in enumerate(component.citations, 1):
                    report.append(f"        [{j}] Chunk {citation.chunk_id} (Confidence: {citation.confidence_score:.1%})")
                    report.append(f"            Domain: {citation.metadata_domain}")
            else:
                report.append(f"      Citations: NONE")
            
            if component.is_contradicted:
                report.append(f"      ⚠ CONTRADICTIONS: {component.contradiction_evidence}")
        
        report.append("")
        
        # Warnings
        if verified_answer.warnings:
            report.append("Warnings:")
            for warning in verified_answer.warnings:
                report.append(f"  ⚠ {warning}")
            report.append("")
        
        # Suggestions
        if verified_answer.suggestions:
            report.append("Suggestions for Improvement:")
            for suggestion in verified_answer.suggestions:
                report.append(f"  → {suggestion}")
            report.append("")
        
        report.append("=" * 80)
        
        return "\n".join(report)


class VerificationGateConfig:
    """Configuration for verification gates"""
    
    def __init__(self):
        self.min_confidence_threshold = 0.65
        self.min_evidence_citations = 2
        self.min_quality_score = 0.70
        self.min_completeness_score = 0.60
        self.max_allowed_warnings = 3
        self.enable_contradiction_check = True
        self.enable_completeness_check = True
        self.enable_consistency_check = True
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "min_confidence_threshold": self.min_confidence_threshold,
            "min_evidence_citations": self.min_evidence_citations,
            "min_quality_score": self.min_quality_score,
            "min_completeness_score": self.min_completeness_score,
            "max_allowed_warnings": self.max_allowed_warnings,
            "enable_contradiction_check": self.enable_contradiction_check,
            "enable_completeness_check": self.enable_completeness_check,
            "enable_consistency_check": self.enable_consistency_check,
        }
