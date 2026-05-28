"""
Evaluation framework orchestrating test execution, scoring, classification, and refinement loop.

Provides machine-readable reports and iteration history.
"""

from typing import List, Dict, Any, Optional
import json
from dataclasses import dataclass, asdict
from pathlib import Path
from datetime import datetime

from .failure_taxonomy import FailureTaxonomyAnalyzer, FailureCategory
from .quality_gates import QualityGates, GateResult


@dataclass
class TestCaseResult:
    test_case_id: str
    query: str
    expected_domain: str
    answerability_level: str
    generated_answer: str
    kb_relevance_pass: bool
    retrieval_pass: bool
    retrieval_answerable_pass: bool
    prompt_integrity_pass: bool
    generation_pass: bool
    grounding_pass: bool
    domain_pass: bool
    expectation_pass: bool
    hallucination_pass: bool
    abstention_used: bool
    abstention_valid: bool
    false_abstention: bool
    lexical_overlap_score: float
    semantic_relevance_score: float
    reranker_score: float
    kb_relevance_score: float
    retrieval_sufficiency_score: float
    grounding_score: float
    expectation_coverage_score: float
    domain_consistency_score: float
    hallucination_risk_score: float
    overall_pass: bool
    failure_taxonomy: List[str]
    failure_reasons: List[str]
    top_evidence: List[Dict[str, Any]]

    def to_dict(self):
        return asdict(self)


class EvaluationFramework:
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.gates = QualityGates(config=self.config)
        self.taxonomy = FailureTaxonomyAnalyzer()
        self.iteration_history: List[Dict[str, Any]] = []

    def run_test_case(
        self,
        test_case: Dict[str, Any],
        generated_answer: str,
        retrieved_chunks: List[Dict[str, Any]],
        intent_analysis: Dict[str, Any],
        system_prompt: str,
        conversation_history: Optional[str] = None,
    ) -> TestCaseResult:
        """Run verification and quality gates for a single test case."""
        # Extract scores
        lexical_overlap = self._compute_lexical_overlap(test_case["query"], retrieved_chunks)
        semantic_relevance = self._compute_semantic_relevance(test_case["query"], retrieved_chunks)
        reranker_score = self._extract_reranker_score(retrieved_chunks)

        # KB relevance gate
        domain_match = (test_case.get("expected_domain", "").lower() in test_case["query"].lower())
        top_k_consistency = [c.get("semantic_similarity", None) for c in retrieved_chunks if c.get("semantic_similarity") is not None]
        kb_gate = self.gates.kb_relevance_gate(
            test_case["query"],
            lexical_overlap_score=lexical_overlap,
            semantic_similarity_score=semantic_relevance,
            reranker_score=reranker_score,
            domain_match=domain_match,
            top_k_consistency=top_k_consistency,
        )

        # Retrieval sufficiency
        semantic_scores = [self._chunk_semantic_score(c) for c in retrieved_chunks]
        cross_encoder_scores = [float(c.get("cross_encoder_score", 0.0) or 0.0) for c in retrieved_chunks]
        retrieval_gate = self.gates.retrieval_sufficiency_gate(
            top_chunks=retrieved_chunks,
            query=test_case["query"],
            semantic_scores=semantic_scores,
            cross_encoder_scores=cross_encoder_scores,
        )

        # Prompt integrity
        context_text = "\n\n".join([c.get("text","") for c in retrieved_chunks])
        assembled_prompt = f"{system_prompt}\n\nContext:\n{context_text}\n\nQuestion: {test_case['query']}"
        prompt_gate = self.gates.prompt_integrity_gate(
            system_prompt=assembled_prompt,
            query=test_case["query"],
            context_text=context_text,
            conversation_history=conversation_history,
        )

        # Grounding score: simple heuristic from evidence
        grounding_score = self._compute_grounding_score(generated_answer, retrieved_chunks)

        gen_gate = self.gates.grounded_generation_gate(
            generated_answer=generated_answer,
            top_evidence=retrieved_chunks,
            grounding_score=grounding_score,
            domain_expected=test_case.get("expected_domain"),
        )

        # Abstention validity
        abstention_used = "insufficient" in generated_answer.lower() or "not contain" in generated_answer.lower()
        abst_gate = self.gates.abstention_validity_gate(
            abstention_used=abstention_used,
            generated_answer=generated_answer,
            grounding_score=retrieval_gate.score,
            semantic_relevance_score=semantic_relevance,
            retrieval_pass=retrieval_gate.pass_flag,
        )

        # Expectation coverage
        expect_gate = self.gates.expectation_coverage_gate(
            generated_answer=generated_answer,
            expected_answer_points=test_case.get("expected_answer_points", []),
            required_keywords=test_case.get("required_keywords", []),
            minimum_coverage=test_case.get("minimum_expectation_coverage") or test_case.get("minimum_semantic_coverage"),
        )

        # Domain consistency score - semantic token overlap, not exact substring matching
        expected_domain = test_case.get("expected_domain", "")
        expected_tokens = {token for token in expected_domain.lower().split() if len(token) > 2}
        answer_tokens = {token for token in generated_answer.lower().split() if len(token) > 2}
        domain_overlap = len(expected_tokens.intersection(answer_tokens)) / max(1, len(expected_tokens)) if expected_tokens else 1.0
        domain_consistency_score = domain_overlap

        # Hallucination risk - simple heuristic
        hallucination_risk = 0.0
        if "always" in generated_answer.lower() and not any("always" in c.get("text", "").lower() for c in retrieved_chunks):
            hallucination_risk = 0.5

        # Overall pass logic
        overall_pass = all([
            kb_gate.pass_flag,
            retrieval_gate.pass_flag,
            prompt_gate.pass_flag,
            gen_gate.pass_flag,
            abst_gate.pass_flag,
            expect_gate.pass_flag,
        ])

        # Build taxonomy classification if any gate failed
        failure_taxonomy = []
        failure_reasons = []
        if not overall_pass:
            taxonomy_grounding_score = retrieval_gate.score if abstention_used else grounding_score
            classification = self.taxonomy.analyze_failure(
                test_case_id=test_case["test_case_id"],
                query=test_case["query"],
                generated_answer=generated_answer,
                expected_domain=test_case.get("expected_domain",""),
                expected_answer_points=test_case.get("expected_answer_points",[]),
                required_keywords=test_case.get("required_keywords",[]),
                optional_keywords=test_case.get("optional_keywords",[]),
                forbidden_topics=test_case.get("forbidden_topics",[]),
                kb_relevance_score=kb_gate.score,
                semantic_relevance_score=semantic_relevance,
                reranker_score=reranker_score,
                lexical_overlap_score=lexical_overlap,
                retrieval_pass=retrieval_gate.pass_flag,
                grounding_score=taxonomy_grounding_score,
                expectation_coverage=expect_gate.score,
                hallucination_risk_score=hallucination_risk,
                abstention_used=abstention_used,
                top_evidence=retrieved_chunks,
            )
            failure_taxonomy = [c.value for c in classification.failure_categories]
            failure_reasons = classification.failure_reasons

        # Compose TestCaseResult
        result = TestCaseResult(
            test_case_id=test_case["test_case_id"],
            query=test_case["query"],
            expected_domain=test_case.get("expected_domain"),
            answerability_level=test_case.get("answerability_level", "answerable_with_light_semantic_inference"),
            generated_answer=generated_answer,
            kb_relevance_pass=kb_gate.pass_flag,
            retrieval_pass=retrieval_gate.pass_flag,
            retrieval_answerable_pass=retrieval_gate.details.get("retrieval_answerable", False),
            prompt_integrity_pass=prompt_gate.pass_flag,
            generation_pass=gen_gate.pass_flag,
            grounding_pass=grounding_score >= self.gates.grounding_threshold,
            domain_pass=domain_consistency_score >= 0.5,
            expectation_pass=expect_gate.pass_flag,
            hallucination_pass=hallucination_risk < 0.4,
            abstention_used=abstention_used,
            abstention_valid=abst_gate.pass_flag,
            false_abstention=(abstention_used and not abst_gate.pass_flag),
            lexical_overlap_score=lexical_overlap,
            semantic_relevance_score=semantic_relevance,
            reranker_score=reranker_score,
            kb_relevance_score=kb_gate.score,
            retrieval_sufficiency_score=retrieval_gate.score,
            grounding_score=grounding_score,
            expectation_coverage_score=expect_gate.score,
            domain_consistency_score=domain_consistency_score,
            hallucination_risk_score=hallucination_risk,
            overall_pass=overall_pass,
            failure_taxonomy=failure_taxonomy,
            failure_reasons=failure_reasons,
            top_evidence=retrieved_chunks,
        )

        return result

    def _compute_lexical_overlap(self, query: str, retrieved_chunks: List[Dict[str, Any]]) -> float:
        # simple lexical overlap: fraction of query words present in top chunk
        if not retrieved_chunks:
            return 0.0
        q_words = set(query.lower().split())
        top_text = retrieved_chunks[0].get("text","") if retrieved_chunks else ""
        top_words = set(top_text.lower().split())
        overlap = q_words.intersection(top_words)
        return len(overlap) / max(1, len(q_words))

    def _compute_semantic_relevance(self, query: str, retrieved_chunks: List[Dict[str, Any]]) -> float:
        # Use semantic_similarity field if present, else heuristic from reranker score
        if not retrieved_chunks:
            return 0.0
        sims = [self._chunk_semantic_score(c) for c in retrieved_chunks]
        if sims:
            return sum(sims)/len(sims)
        return 0.0

    def _chunk_semantic_score(self, chunk: Dict[str, Any]) -> float:
        """Derive a 0-1 semantic similarity score from available chunk fields."""
        if chunk.get("semantic_similarity") is not None:
            return max(0.0, min(1.0, float(chunk.get("semantic_similarity", 0.0))))
        if chunk.get("distance") is not None:
            try:
                return max(0.0, 1.0 - min(1.0, float(chunk.get("distance", 1.0) or 1.0)))
            except (TypeError, ValueError):
                pass
        if chunk.get("cross_encoder_score") is not None:
            try:
                return max(0.0, min(1.0, float(chunk.get("cross_encoder_score", 0.0) or 0.0) / 10.0))
            except (TypeError, ValueError):
                pass
        return 0.0

    def _extract_reranker_score(self, retrieved_chunks: List[Dict[str, Any]]) -> float:
        if not retrieved_chunks:
            return 0.0
        ces = [c.get("cross_encoder_score") for c in retrieved_chunks if c.get("cross_encoder_score") is not None]
        if not ces:
            return 0.0
        return max(ces)

    def _compute_grounding_score(self, generated_answer: str, retrieved_chunks: List[Dict[str, Any]]) -> float:
        # Heuristic: measure fraction of sentences that directly reference evidence terms
        if not retrieved_chunks:
            return 0.0
        synonyms = {
            "verification": "verify",
            "verified": "verify",
            "validation": "verify",
            "validating": "verify",
            "trusted": "trust",
            "trusting": "trust",
            "implicitly": "default",
            "assumed": "default",
        }
        stop_tokens = {"important", "necessary", "because", "instead", "should", "reason", "may", "might", "could", "would"}

        def normalize(text: str) -> set[str]:
            tokens: set[str] = set()
            for raw in text.lower().replace("-", " ").split():
                token = "".join(ch for ch in raw if ch.isalnum())
                if len(token) <= 2:
                    continue
                if token in stop_tokens:
                    continue
                tokens.add(synonyms.get(token, token))
            return tokens

        context_tokens = normalize(" ".join([c.get("text", "") for c in retrieved_chunks]))
        ans_tokens = list(normalize(generated_answer))
        matches = sum(1 for token in ans_tokens if token in context_tokens)
        grounding = matches / max(1, len(ans_tokens))
        return min(1.0, grounding)

    def evaluate_batch(self, test_cases: List[Dict[str, Any]], results_dir: str = "./evaluation_results") -> Dict[str, Any]:
        """Evaluate a batch of test cases given precomputed pipeline outputs in test_cases structure.

        This function expects each test_case dict to include fields `generated_answer` and `retrieved_chunks` for simplicity.
        """
        Path(results_dir).mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        batch_report = {
            "timestamp": timestamp,
            "cases": [],
        }

        passed = 0
        critical_failures = 0
        false_abstentions = 0
        kb_relevance_false_negatives = 0
        total_grounding = 0.0
        total_expectation = 0.0
        total_domain_consistency = 0.0

        classifications = []

        for tc in test_cases:
            result = self.run_test_case(
                test_case=tc,
                generated_answer=tc.get("generated_answer",""),
                retrieved_chunks=tc.get("retrieved_chunks",[]),
                intent_analysis=tc.get("intent_analysis",{}),
                system_prompt=tc.get("system_prompt",""),
                conversation_history=tc.get("conversation_history",""),
            )

            batch_report["cases"].append(result.to_dict())

            if result.overall_pass:
                passed += 1
            else:
                # collect classification for statistics
                classification = self.taxonomy.analyze_failure(
                    test_case_id=tc["test_case_id"],
                    query=tc["query"],
                    generated_answer=tc.get("generated_answer",""),
                    expected_domain=tc.get("expected_domain",""),
                    expected_answer_points=tc.get("expected_answer_points",[]),
                    required_keywords=tc.get("required_keywords",[]),
                    optional_keywords=tc.get("optional_keywords",[]),
                    forbidden_topics=tc.get("forbidden_topics",[]),
                    kb_relevance_score=result.kb_relevance_score,
                    semantic_relevance_score=result.semantic_relevance_score,
                    reranker_score=result.reranker_score,
                    lexical_overlap_score=result.lexical_overlap_score,
                    retrieval_pass=result.retrieval_pass,
                    grounding_score=result.grounding_score,
                    expectation_coverage=result.expectation_coverage_score,
                    hallucination_risk_score=result.hallucination_risk_score,
                    abstention_used=result.abstention_used,
                    top_evidence=result.top_evidence,
                )
                classifications.append(classification)

                if classification.severity == "critical":
                    critical_failures += 1
                if FailureCategory.K1 in classification.failure_categories:
                    kb_relevance_false_negatives += 1
                if FailureCategory.G3 in classification.failure_categories:
                    false_abstentions += 1

            total_grounding += result.grounding_score
            total_expectation += result.expectation_coverage_score
            total_domain_consistency += result.domain_consistency_score

        total_cases = len(test_cases)
        avg_grounding = total_grounding / max(1, total_cases)
        avg_expectation = total_expectation / max(1, total_cases)
        avg_domain_consistency = total_domain_consistency / max(1, total_cases)

        batch_summary = {
            "total_cases": total_cases,
            "passed_cases": passed,
            "failed_cases": total_cases - passed,
            "critical_failures": critical_failures,
            "hallucination_failures": sum(1 for c in classifications if FailureCategory.G2 in c.failure_categories),
            "false_abstentions": false_abstentions,
            "kb_relevance_false_negatives": kb_relevance_false_negatives,
            "average_grounding_score": avg_grounding,
            "average_expectation_coverage": avg_expectation,
            "average_domain_consistency": avg_domain_consistency,
            "iteration_count": len(self.iteration_history) + 1,
            "final_status": "incomplete",
        }

        batch_report["summary"] = batch_summary

        # persist JSON
        out_file = Path(results_dir) / f"evaluation_report_{timestamp}.json"
        with open(out_file, 'w', encoding='utf-8') as f:
            json.dump(batch_report, f, indent=2, ensure_ascii=False)

        # append to iteration history
        self.iteration_history.append({"timestamp": timestamp, "report_path": str(out_file), "summary": batch_summary})

        return batch_summary


# Expose for modules
_default_framework = EvaluationFramework()

def evaluate_batch(test_cases: List[Dict[str, Any]], results_dir: str = "./evaluation_results") -> Dict[str, Any]:
    return _default_framework.evaluate_batch(test_cases, results_dir=results_dir)
