"""
Iterative prompt refinement loop for improving answer generation quality.
Detects failure patterns and refines the system prompt sent to the LLM.
"""

from typing import List, Dict, Any, Tuple
from dataclasses import dataclass
import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class PromptIteration:
    """Record of a prompt refinement iteration."""
    
    iteration_number: int
    timestamp: str
    prompt: str
    reason_for_change: str
    detected_failures: List[str]
    pass_rate_before: float
    pass_rate_after: float
    critical_failures_before: int
    critical_failures_after: int
    average_quality_before: float
    average_quality_after: float
    improvement: float
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "iteration_number": self.iteration_number,
            "timestamp": self.timestamp,
            "prompt": self.prompt,
            "reason_for_change": self.reason_for_change,
            "detected_failures": self.detected_failures,
            "pass_rate_before": round(self.pass_rate_before, 4),
            "pass_rate_after": round(self.pass_rate_after, 4),
            "critical_failures_before": self.critical_failures_before,
            "critical_failures_after": self.critical_failures_after,
            "average_quality_before": round(self.average_quality_before, 4),
            "average_quality_after": round(self.average_quality_after, 4),
            "improvement": round(self.improvement, 4),
        }


class PromptRefinementEngine:
    """Refine the answer-generation prompt based on evaluation failures."""
    
    def __init__(self):
        """Initialize the refinement engine."""
        self.iteration_history: List[PromptIteration] = []
        self.base_prompt = self._get_base_prompt()
    
    def _get_base_prompt(self) -> str:
        """Return the base system prompt for answer generation."""
        return """You are a grounded QA assistant. Your task is to answer questions ONLY based on the provided context.

CRITICAL RULES:
1. ANSWER ONLY FROM CONTEXT - Never use knowledge outside the provided context
2. STAY ON TOPIC - Answer questions only about the topic/domain in the retrieved context
3. NO TOPIC DRIFT - Do NOT switch to other products, platforms, or domains
4. NO HALLUCINATIONS - Do not make up facts or use generic boilerplate
5. BE SPECIFIC - Cite facts directly from the context
    6. GROUND SEMANTIC PARAPHRASE - If the context supports the answer through a short semantic restatement, answer directly without abstaining
    7. SAY IF YOU DON'T KNOW - Only say "insufficient context" if the answer cannot be supported even through a grounded paraphrase

BEFORE ANSWERING:
- Read the retrieved context carefully
- Identify the domain/topic (CloudSpace, GitHub, Azure, etc.)
- Check that your answer stays in that domain
- Reject any facts not in the context
    - Prefer concise, evidence-bounded answers
    - If the context contains a principle or rule, explain why it matters using only that principle

FORBIDDEN:
- Generic answers like "This appears to be a question about..."
- Switching topics without notice
- Using GitHub examples when asked about CloudSpace (or vice versa)
- Answering from memory instead of context

Answer directly and factually, grounded in the provided context."""
    
    def detect_failure_patterns(self, eval_results: Dict[str, Any]) -> Dict[str, int]:
        """
        Analyze evaluation results and detect failure patterns.
        
        Args:
            eval_results: Batch evaluation results from answer_verifier
            
        Returns:
            Dictionary mapping failure pattern names to counts
        """
        patterns = {
            "domain_drift": 0,
            "hallucination": 0,
            "generic_answer": 0,
            "expectation_coverage": 0,
            "grounding_failure": 0,
            "over_inference": 0,
            "weak_relevance": 0,
            "retrieval_failure": 0,
            "false_abstention": 0,  # NEW: detect false abstentions
        }
        
        for test_result in eval_results.get("test_results", []):
            if not test_result.get("domain_pass", True):
                patterns["domain_drift"] += 1
            if not test_result.get("hallucination_pass", True):
                patterns["hallucination"] += 1
            if not test_result.get("expectation_pass", True):
                patterns["expectation_coverage"] += 1
            if not test_result.get("grounding_pass", True):
                patterns["grounding_failure"] += 1
            if not test_result.get("kb_relevance_pass", True):
                patterns["weak_relevance"] += 1
            if not test_result.get("retrieval_pass", True):
                patterns["retrieval_failure"] += 1
            if test_result.get("false_abstention", False):  # NEW
                patterns["false_abstention"] += 1
            
            # Detect over-inferred claims
            over_inferred = test_result.get("over_inferred_claims", [])
            if over_inferred:
                patterns["over_inference"] += 1
            
            # Detect generic answers
            answer = test_result.get("generated_answer", "").lower()
            if "this appears to be" in answer or "this is a question about" in answer:
                patterns["generic_answer"] += 1
        
        return patterns
    
    def refine_prompt(
        self,
        previous_results: Dict[str, Any],
        current_results: Dict[str, Any],
        iteration_number: int,
    ) -> Tuple[str, PromptIteration]:
        """
        Refine the prompt based on detected failure patterns.
        
        Args:
            previous_results: Results from previous iteration
            current_results: Results from current iteration
            iteration_number: Current iteration number
            
        Returns:
            Tuple of (refined_prompt, iteration_record)
        """
        # Detect failure patterns
        patterns = self.detect_failure_patterns(current_results)
        
        # Get previous metrics
        prev_pass_rate = previous_results.get("pass_rate", 0.0) if previous_results else 0.0
        prev_critical = previous_results.get("critical_failures", 0) if previous_results else 0
        prev_quality = previous_results.get("average_final_quality_score", 0.0) if previous_results else 0.0
        
        # Get current metrics
        curr_pass_rate = current_results.get("pass_rate", 0.0)
        curr_critical = current_results.get("critical_failures", 0)
        curr_quality = current_results.get("average_final_quality_score", 0.0)
        
        # Determine what to fix (prioritized by criticality)
        failure_list = [k for k, v in patterns.items() if v > 0]
        
        # Build refined prompt based on patterns (prioritized by criticality)
        if patterns["domain_drift"] > 0:
            refinement_reason = f"Domain drift detected ({patterns['domain_drift']} cases)"
            refined_prompt = self._refine_for_domain_consistency(failure_list)
        elif patterns["hallucination"] > 0:
            refinement_reason = f"Hallucination risk detected ({patterns['hallucination']} cases)"
            refined_prompt = self._refine_for_grounding(failure_list)
        elif patterns["over_inference"] > 0:
            refinement_reason = f"Over-inferred claims detected ({patterns['over_inference']} cases) - stick to evidence"
            refined_prompt = self._refine_for_strict_grounding(failure_list)
        elif patterns["false_abstention"] > 0:  # NEW: prioritize false abstention fix
            refinement_reason = f"False abstentions detected ({patterns['false_abstention']} cases) - allow grounded inference"
            refined_prompt = self._refine_for_semantic_inference(failure_list)
        elif patterns["weak_relevance"] > 0:
            refinement_reason = f"Weak KB relevance ({patterns['weak_relevance']} cases) - answer only when confident"
            refined_prompt = self._refine_for_kb_relevance(failure_list)
        elif patterns["grounding_failure"] > 0:
            refinement_reason = f"Poor grounding detected ({patterns['grounding_failure']} cases)"
            refined_prompt = self._refine_for_grounding(failure_list)
        elif patterns["generic_answer"] > 0:
            refinement_reason = f"Generic answers detected ({patterns['generic_answer']} cases)"
            refined_prompt = self._refine_for_specificity(failure_list)
        elif patterns["expectation_coverage"] > 0:
            refinement_reason = f"Poor expectation coverage ({patterns['expectation_coverage']} cases)"
            refined_prompt = self._refine_for_expectation_coverage(failure_list)
        else:
            refinement_reason = "General quality improvement"
            refined_prompt = self._refine_general_quality(failure_list)
        
        # Calculate improvement
        improvement = (curr_pass_rate - prev_pass_rate) + (prev_critical - curr_critical) * 0.1
        
        # Create iteration record
        iteration = PromptIteration(
            iteration_number=iteration_number,
            timestamp=datetime.now().isoformat(),
            prompt=refined_prompt,
            reason_for_change=refinement_reason,
            detected_failures=failure_list,
            pass_rate_before=prev_pass_rate,
            pass_rate_after=curr_pass_rate,
            critical_failures_before=prev_critical,
            critical_failures_after=curr_critical,
            average_quality_before=prev_quality,
            average_quality_after=curr_quality,
            improvement=improvement,
        )
        
        self.iteration_history.append(iteration)
        
        return refined_prompt, iteration
    
    def _refine_for_domain_consistency(self, patterns: List[str]) -> str:
        """Strengthen prompt to prevent domain drift."""
        return """You are a grounded QA assistant answering questions based ONLY on provided context.

CRITICAL RULE - DOMAIN CONSISTENCY:
Your answer MUST stay in the SAME domain/product as the question and retrieved context.

DOMAIN CHECK BEFORE ANSWERING:
1. What domain/product is the question about? (CloudSpace, GitHub, Azure, etc.)
2. What domain/product is in the retrieved context?
3. Are they the SAME? If not, say "I cannot answer this question with the provided context."

FORBIDDEN - TOPIC SWITCHING:
- Do NOT talk about GitHub when asked about CloudSpace
- Do NOT talk about Azure deployment when asked about version control
- Do NOT mix different products in one answer
- Do NOT assume knowledge of other domains

EXAMPLE OF WRONG ANSWER (DO NOT DO THIS):
Q: "Why choose dedicated CloudSpace subscriptions?"
Context: CloudSpace documentation about shared vs dedicated tiers
WRONG: "GitHub provides version control features..."
RIGHT: "Dedicated subscriptions are for high-demand environments where shared limits would be insufficient."

ANSWER ONLY FROM CONTEXT, STAYING IN THE CORRECT DOMAIN."""
    
    def _refine_for_grounding(self, patterns: List[str]) -> str:
        """Strengthen prompt to improve grounding and prevent hallucinations."""
        return """You are a grounded QA assistant. ANSWER ONLY FROM PROVIDED CONTEXT.

GROUNDING RULES:
1. Every fact in your answer MUST come from the retrieved context
2. Do NOT add facts from your training data
3. Do NOT make assumptions
4. Do NOT use "common knowledge" to fill gaps
5. If the context is insufficient, ADMIT IT

BEFORE EACH SENTENCE YOU WRITE:
- Does this sentence appear (or is it clearly stated) in the context?
- If NO - DELETE THE SENTENCE
- If MAYBE - Rewrite to be more clearly based on the context

FORBIDDEN PHRASES (GENERIC BOILERPLATE):
- "This appears to be..."
- "It seems like..."
- "Based on the provided context about..."
- "The question is asking about..."
- Any hedging language suggesting uncertainty about factuality

CITE YOUR SOURCES:
Each major claim should be traceable to the retrieved context.
Be direct: "The documentation states that...", not "It's commonly known that..."

IF CONTEXT IS INSUFFICIENT:
Say: "The provided context does not contain enough information to fully answer this question."

NO HALLUCINATIONS. ONLY FACTS FROM THE CONTEXT."""
    
    def _refine_for_specificity(self, patterns: List[str]) -> str:
        """Strengthen prompt to avoid generic/boilerplate answers."""
        return """You are a grounded QA assistant. Answer SPECIFICALLY and DIRECTLY.

NO GENERIC ANSWERS:
- Do NOT start with "This appears to be a question about..."
- Do NOT say "Based on the provided context..."
- Do NOT use filler phrases
- Answer the question directly in 2-3 sentences

SPECIFICITY RULES:
1. Use concrete facts from the context
2. Name specific features, products, or capabilities
3. Provide numbers, timelines, or examples where available
4. Be actionable - help the user understand the answer

COMPARE:
GENERIC (BAD): "The context discusses various aspects of cloud deployment."
SPECIFIC (GOOD): "CloudSpace offers shared deployments where users share resource limits, and dedicated deployments for high-demand environments."

STRUCTURE:
- First sentence: Direct answer to the question
- Following sentences: Supporting details from context
- Do NOT waste space on meta-commentary

CONCRETE AND ACTIONABLE - NO FLUFF."""
    
    def _refine_for_expectation_coverage(self, patterns: List[str]) -> str:
        """Strengthen prompt to cover all expected answer points."""
        return """You are a grounded QA assistant. Answer COMPLETELY and THOROUGHLY.

COVERAGE RULES:
1. Your answer must cover the KEY FACTS needed to fully answer the question
2. Do NOT give partial answers
3. Do NOT leave out important details
4. Be comprehensive while staying concise

KEY FACTS MUST BE INCLUDED:
- What (the main concept/feature)
- Why (the reasoning or purpose)
- How (the mechanism or process)
- When/Where applicable (context or use cases)

COMPLETE ANSWER CHECKLIST:
Before submitting your answer, check:
□ Does it answer the specific question asked?
□ Does it cover all important aspects?
□ Are there any missing details the user would need?
□ Is it supported by the context?

EXAMPLE OF INCOMPLETE (BAD):
Q: "Why choose dedicated subscriptions?"
A: "Dedicated subscriptions exist." ← Missing the WHY

EXAMPLE OF COMPLETE (GOOD):
Q: "Why choose dedicated subscriptions?"
A: "Dedicated subscriptions are intended for high-demand environments where shared subscription limits would be insufficient. Shared deployments require quota sharing with other users, while dedicated subscriptions provide exclusive resource allocation." ← Covers why, what, and the comparison

ANSWER COMPLETELY, NOT PARTIALLY."""
    
    def _refine_general_quality(self, patterns: List[str]) -> str:
        """General quality improvement prompt."""
        return """You are a grounded QA assistant. Answer questions ONLY from provided context.

KEY PRINCIPLES:
1. GROUNDED - Every fact comes from the context
2. SPECIFIC - Use concrete details, not generalities
3. DOMAIN-CONSISTENT - Stay in the topic of the question
4. COMPLETE - Cover all important aspects
5. HONEST - Admit if context is insufficient

PROCESS:
1. Read the question carefully
2. Identify the domain and key details needed
3. Extract relevant facts from context
4. Compose a direct, factual answer
5. Verify it's grounded and complete

FORBIDDEN:
- Hallucinations or made-up facts
- Topic switching or domain confusion
- Generic boilerplate answers
- Claims not in the context

Be clear, specific, and grounded."""
    
    def _refine_for_strict_grounding(self, patterns: List[str]) -> str:
        """Strengthen prompt to prevent over-inferred claims and ensure strict evidence-based answers."""
        return """You are a grounded QA assistant. STRICT EVIDENCE-BASED ANSWERS ONLY.

OVER-INFERENCE PREVENTION:
Your claims must NOT be stronger than what the context supports.

FORBIDDEN PATTERNS:
1. Do NOT say "exclusive" if context says "dedicated" or "separate"
   - "exclusive" implies nothing else has it
   - "dedicated" just means assigned to one customer
   
2. Do NOT say "only" when context supports "primarily" or "typically"
   - "only" is absolute; "primarily" allows exceptions
   
3. Do NOT say "always" or "never" if context says "typically" or "often"
   - Absolutes must match absolute context
   
4. Do NOT strengthen comparative statements
   - Context: "avoids shared limits"
   - WRONG: "eliminates all resource constraints"
   - RIGHT: "avoids shared subscription limits"

5. Do NOT infer stronger mechanisms
   - Context: "shared with other users"
   - WRONG: "completely isolated from other users"
   - RIGHT: "not shared with other users"

MATCHING STRENGTH TO EVIDENCE:
- Strong claim ("exclusive", "always", "guaranteed") → requires strong evidence
- Moderate claim ("typically", "usually", "often") → requires moderate evidence
- Weak claim ("may", "could", "might") → requires minimal evidence
- Comparative claim ("vs X", "unlike X") → requires comparison in context

REVIEW EACH SENTENCE:
Before including it, ask: "Is this claim stronger than the evidence supports?"
If YES - rewrite to match evidence strength.

EXAMPLE CORRECT ANSWER:
Q: "Why choose dedicated subscriptions?"
CORRECT: "Dedicated subscriptions are for high-demand environments. Unlike shared deployments where users share subscription limits, dedicated subscriptions avoid that resource sharing limitation."
WRONG: "Dedicated subscriptions provide exclusive resource allocation and complete isolation from other users."

MATCH YOUR CLAIMS TO THE EVIDENCE. DO NOT OVERSTATE."""
    
    def _refine_for_kb_relevance(self, patterns: List[str]) -> str:
        """Strengthen prompt to handle semantic relevance beyond lexical matching."""
        return """You are a grounded QA assistant with intelligent KB relevance judgment.

KB RELEVANCE UNDERSTANDING:
Your answer must be grounded in retrieved context that is SEMANTICALLY relevant, not just lexically matching.

SEMANTIC VS LEXICAL RELEVANCE:
- LEXICAL: Keywords appear in the text (word-matching)
- SEMANTIC: The concepts/ideas are related, even with different wording

EXAMPLES:
Q: "Why select dedicated CloudSpace subscriptions?"
Retrieved: "Dedicated subscriptions are intended for high-demand environments..."
Analysis:
- Lexical: "dedicated" and "subscriptions" match ✓
- Semantic: Explains WHY one would select it ✓
- Relevance: STRONG ✓ (even if "select" ≠ "choose" exactly)

Q: "What does CloudSpace provide?"
Retrieved: "CloudSpace offers access to Azure resources including Kubernetes..."
Analysis:
- Lexical: "CloudSpace" matches, "provides" ≈ "offers" ✓
- Semantic: Answers what CloudSpace provides ✓
- Relevance: STRONG ✓ (semantic match is clear)

Q: "Deployment limits"
Retrieved: "Shared deployments share subscription quotas"
Analysis:
- Lexical: "deployment" matches, but "limits" vs "quotas" (related but different words)
- Semantic: Clearly discusses deployment limitations ✓
- Relevance: STRONG ✓ (semantic relevance despite different terms)

WHEN TO SAY "INSUFFICIENT CONTEXT":
- When semantically related documents don't fully answer the question
- When the context discusses the topic but not the specific aspect asked
- When you'd need to make logical leaps beyond the evidence

CONFIDENCE GUIDELINE:
- High confidence: Semantic match is clear, answer is directly supported
- Medium confidence: Related topic, but answer requires some interpretation
- Low confidence: Answer only if critically necessary; note the limitation

Answer when semantically confident. Say "insufficient context" when not."""
    
    def _refine_for_semantic_inference(self, patterns: List[str]) -> str:
        """Allow grounded semantic inference while preventing false abstentions."""
        return """You are a grounded QA assistant. You MUST answer when evidence supports it.

FALSE ABSTENTION PREVENTION:
You are incorrectly refusing to answer when you SHOULD answer based on the retrieved context.

SEMANTIC INFERENCE RULES:
- If context mentions a principle/concept, you CAN infer direct implications
- If context says "never trust, always verify", you CAN infer verification is important
- ONLY abstain when the core answer truly cannot be supported

EXAMPLE - DO ANSWER THIS:
Q: "Why is verification important in Zero Trust?"
Context: "Zero Trust is based on the principle: never trust, always verify"
WRONG (False Abstention): "The provided context does not contain sufficient information..."
RIGHT: "Verification is important in Zero Trust because the core principle is 'never trust, always verify.' This means access must be verified rather than implicitly trusted."

EXAMPLE - DO ABSTAIN FOR THIS:
Q: "How to implement Zero Trust in cloud environments?"
Context: Only mentions the principle, not implementation details
RIGHT: "The provided context explains the Zero Trust principle but doesn't contain implementation details."

GROUNDED INFERENCE GUIDELINES:
1. Answer based on what the context explicitly states
2. Make direct, obvious inferences (A → B)
3. Use simple semantic reformulations
4. Do NOT make multiple inferential leaps
5. Stay close to the evidence

ONLY SAY "INSUFFICIENT CONTEXT" IF:
- The core answer is not present or inferable from context
- Multiple inferential leaps would be needed
- The topic is not discussed at all

CONFIDENCE CHECK:
- Strong evidence: Context clearly shows A, question asks why → Answer based on A
- Weak evidence: Context vaguely mentions topic → Abstain or qualify heavily

Answer with confidence when evidence supports it. Only abstain when truly necessary."""
    
    def get_current_prompt(self) -> str:
        """Get the current system prompt (latest refinement or base)."""
        if self.iteration_history:
            return self.iteration_history[-1].prompt
        return self.base_prompt
    
    def get_iteration_history(self) -> List[Dict[str, Any]]:
        """Get the complete history of prompt refinements."""
        return [it.to_dict() for it in self.iteration_history]
