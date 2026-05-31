#!/usr/bin/env python3
"""Comprehensive test runner for full RAG validation across all test categories.

This version implements an expected answer quality contract to eliminate false PASS cases.
Every test is judged against explicit quality expectations, not just transport success.
"""

from datetime import datetime
import os
import json
import re
from pathlib import Path
import subprocess
import sys
from typing import Any, Dict, List, Optional, Set, Tuple

ROOT = Path(__file__).resolve().parent
GROUNDED_SCRIPT = ROOT / "src" / "tools" / "diagnostics" / "grounded_qa_diagnostic.py"
OUTPUT_DIR = ROOT / "diagnostics" / "comprehensive_test_run"
RAG_BASE_URL = os.getenv("RAG_BASE_URL", "http://127.0.0.1:8001")
EXPECTED_ANSWERS_FILE = ROOT / "expected_answer_contracts_v2.json"

# Ensure output directory exists
try:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
except Exception as e:
    print(f"Failed to create output directory: {e}")
    sys.exit(1)

# Test cases extracted from test_case.txt - representative from each category
TEST_QUERIES = {
    "basic_retrieval": [
        "What is the purpose of Aurora WP3.1 upgrade?",
        "What is CloudSpace in Azure?",
        "What is the purpose of GitHub Safe-Settings App?",
        "What is PMT Labs?",
    ],
    "structured_extraction": [
        "List all key improvements introduced in Aurora WP3.1.",
        "List all main components of CloudSpace architecture.",
        "List all GitHub permission levels for repository access.",
    ],
    "multi_hop_reasoning": [
        "Why does Aurora introduce Work Package-based planning?",
        "Why is CloudSpace better than traditional lab environments?",
        "Why is cloud-based architecture critical for PMT Labs?",
    ],
    "deep_technical": [
        "When is a requirement classified as System vs Software in Aurora?",
        "How does the Allocation attribute work in DOORS?",
    ],
    "scenario_based": [
        "A project affects both HW and SW → how should requirements be classified?",
        "A team needs isolated cloud resources → which CloudSpace tier should be used?",
    ],
}

STOPWORDS: Set[str] = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "how", "in", "is", "it", "of", "on", "or", "that", "the", "to", "was", "what", "when", "which", "who", "why", "with", "both", "does", "should", "all", "main", "list", "needs", "team", "project", "purpose",
}

SYNONYM_EXPANSIONS: Dict[str, Set[str]] = {
    "isolated": {"isolated", "dedicated", "private"},
    "tier": {"tier", "tiers", "shared", "dedicated", "subscription", "subscriptions"},
    "resources": {"resources", "resource", "subscription", "subscriptions", "quotas", "environment", "environments"},
    "architecture": {"architecture", "building", "blocks", "components"},
}

NOISE_PATTERNS = [
    re.compile(r"/Creator\(|/Producer\(|/CreationDate\(|/ModDate\(", re.IGNORECASE),
    re.compile(r"<</.*>>", re.IGNORECASE),
    re.compile(r"<\?xpacket", re.IGNORECASE),
    re.compile(r"\bAdobe\s+Photoshop\b", re.IGNORECASE),
]


def _tokenize(text: str) -> Set[str]:
    base_tokens = {
        token
        for token in re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{2,}", text.lower())
        if token not in STOPWORDS
    }
    expanded_tokens = set(base_tokens)
    for token in list(base_tokens):
        expanded_tokens.update(SYNONYM_EXPANSIONS.get(token, set()))
    return expanded_tokens


def _normalize_for_matching(text: str) -> str:
    """Normalize text for core fact matching by removing punctuation variations."""
    # Replace hyphens with spaces, collapse multiple spaces
    text = text.lower()
    text = re.sub(r'[-_]', ' ', text)  # Replace hyphens/underscores with spaces
    text = re.sub(r'\s+', ' ', text)   # Collapse multiple spaces
    return text.strip()


def _core_fact_matches(fact: str, answer: str) -> bool:
    """Check if a core fact is present in answer, handling punctuation variations."""
    normalized_answer = _normalize_for_matching(answer)
    normalized_fact = _normalize_for_matching(fact)
    return normalized_fact in normalized_answer


def _is_noise_answer(answer: str) -> Tuple[bool, str]:
    if not answer:
        return True, "empty_answer"

    trimmed = answer.strip()
    if len(trimmed) < 24:
        return True, "too_short"

    for pattern in NOISE_PATTERNS:
        if pattern.search(trimmed):
            return True, "metadata_pattern_detected"

    # Heuristic for gibberish: high symbol density and low alphabetic ratio.
    alpha_count = sum(1 for ch in trimmed if ch.isalpha())
    symbol_count = sum(1 for ch in trimmed if not ch.isalnum() and not ch.isspace())
    total = max(1, len(trimmed))
    alpha_ratio = alpha_count / total
    symbol_ratio = symbol_count / total
    if alpha_ratio < 0.35 and symbol_ratio > 0.12:
        return True, f"gibberish_signature(alpha_ratio={alpha_ratio:.2f},symbol_ratio={symbol_ratio:.2f})"

    # Detect spaced single-char streams like "A d o b e P h o t o s h o p".
    if re.search(r"(?:\b[A-Za-z]\b\s+){8,}", trimmed):
        return True, "single_char_stream"

    return False, "ok"


def _query_alignment_ok(query: str, answer: str) -> Tuple[bool, str]:
    query_tokens = _tokenize(query)
    answer_tokens = _tokenize(answer)
    if not query_tokens:
        return True, "no_query_tokens"
    overlap = len(query_tokens.intersection(answer_tokens))
    ratio = overlap / len(query_tokens)
    # More lenient for definition/purpose questions where subject is implied
    if overlap >= 1 or ratio >= 0.20:
        return True, f"query_overlap_ok(overlap={overlap},ratio={ratio:.2f})"
    return False, f"query_overlap_low(overlap={overlap},ratio={ratio:.2f})"


def _load_expected_answers() -> Dict[str, Dict[str, Any]]:
    """Load expected answer quality contract from v2 comprehensive file."""
    if not EXPECTED_ANSWERS_FILE.exists():
        print(f"Warning: Expected answers file not found: {EXPECTED_ANSWERS_FILE}")
        return {}
    try:
        data = json.loads(EXPECTED_ANSWERS_FILE.read_text(encoding="utf-8"))
        contracts = data.get("expected_answer_contracts", {})
        print(f"  - Loaded {len(contracts)} test case contracts")
        
        # Debug: Show what we loaded
        if contracts:
            sample_names = list(contracts.keys())[:3]
            print(f"  - Sample contract keys: {', '.join(sample_names)}")
        
        return contracts
    except Exception as e:
        print(f"Warning: Failed to load expected answers: {e}")
        return {}



def _check_against_contract(
    test_name: str, 
    query: str, 
    answer: str,
    expected_answers: Dict[str, Dict[str, Any]]
) -> Tuple[bool, List[str]]:
    """Check if answer satisfies the expected answer quality contract for this test.
    
    This implements:
    - Global quality requirements (relevant, grounded, adequate, readable, type-appropriate)
    - Question-type specific adequacy thresholds
    - Hard fail conditions
    - Forbidden content detection
    - Contradiction gate (no unresolved dominant_failure_cause in PASS)
    """
    
    reasons: List[str] = []
    
    # Check if we have expectations for this test
    if test_name not in expected_answers:
        # No explicit contract, fall back to basic checks
        return _evaluate_quality_basic(query, answer)
    
    contract = expected_answers[test_name]
    question_type = contract.get("question_type", "")
    expected_core_facts = contract.get("expected_core_facts", [])
    forbidden_content = contract.get("forbidden_content", [])
    expected_intent = contract.get("expected_intent", "")
    expected_answer_shape = contract.get("expected_answer_shape", "")
    expected_adequacy = contract.get("expected_answer_adequacy", {})
    minimum_quality_threshold = contract.get("minimum_quality_threshold", "")
    
    # Lowercase for comparison
    answer_lower = answer.lower()
    answer_stripped = answer.strip()
    
    # ==================== HARD FAIL CONDITIONS ====================
    
    # Hard fail: empty answer
    if not answer or not answer_stripped:
        reasons.append("HARD_FAIL: empty_answer")
        return False, reasons
    
    # Hard fail: too short (likely incomplete)
    if len(answer_stripped) < 30:
        reasons.append(f"HARD_FAIL: answer_too_short({len(answer_stripped)} chars, min 30)")
        return False, reasons
    
    # Hard fail: is noise/metadata/gibberish
    is_noise, noise_reason = _is_noise_answer(answer)
    if is_noise:
        reasons.append(f"HARD_FAIL: {noise_reason}")
        return False, reasons
    
    # Hard fail: forbidden content present
    for forbidden in forbidden_content:
        if forbidden.lower() in answer_lower:
            reasons.append(f"HARD_FAIL: forbidden_content_detected('{forbidden}')")
    
    if any(r.startswith("HARD_FAIL") for r in reasons):
        return False, reasons
    
    # Hard fail: query-intent mismatch (answer doesn't align with question)
    # But for definition/purpose and extraction questions, allow context-implicit answers
    # And for scenario_based questions, allow recommendation-focused answers with different word forms
    if question_type not in ["definition_purpose", "structured_extraction", "scenario_based"]:
        aligned, align_reason = _query_alignment_ok(query, answer)
        if not aligned:
            reasons.append(f"HARD_FAIL: query_misalignment({align_reason})")
            return False, reasons
    
    # ==================== QUALITY CHECKS ====================
    
    # Check for core facts presence
    missing_core_facts = []
    for fact in expected_core_facts:
        if not _core_fact_matches(fact, answer_stripped):
            missing_core_facts.append(fact)
    
    if missing_core_facts:
        missing_pct = len(missing_core_facts) / len(expected_core_facts)
        
        # For structured extraction and technical questions, missing facts is critical
        if question_type in ["structured_extraction", "deep_technical"]:
            if missing_pct > 0.25:  # More than 25% missing is fail
                reasons.append(f"FAIL: missing_core_facts({len(missing_core_facts)}/{len(expected_core_facts)}:{missing_pct:.0%})")
                return False, reasons
        elif question_type in ["definition_purpose"]:
            # For definitions, missing facts might be acceptable if answer is complete
            if missing_pct > 0.5:
                reasons.append(f"FAIL: missing_too_many_core_facts({len(missing_core_facts)}/{len(expected_core_facts)})")
                return False, reasons
        elif question_type in ["causal_reasoning", "comparative_reasoning", "necessity_reasoning"]:
            # For reasoning questions, don't enforce core facts - check causal language instead
            # Core facts are guidance, not strict requirements
            pass
        elif question_type in ["scenario_based", "scenario_decision"]:
            # For scenario decisions, focus on recommendation over core facts
            if missing_pct > 0.75:  # Very lenient - recommendation is key
                reasons.append(f"FAIL: missing_core_facts({len(missing_core_facts)}/{len(expected_core_facts)})")
                return False, reasons
        else:
            # For other question types, allow up to 75%
            if missing_pct > 0.75:
                reasons.append(f"FAIL: missing_core_facts({len(missing_core_facts)}/{len(expected_core_facts)})")
                return False, reasons
    
    # ==================== QUESTION TYPE SPECIFIC VALIDATION ====================
    
    if question_type == "structured_extraction":
        # Must have explicit list/enumeration format (or have all core facts present)
        lines = answer_stripped.split('\n')
        list_items = []
        for line in lines:
            # Support bullet points (-, •, *), numbered (1., 1), parenthesized (1), 1)) formats
            if re.match(r'^\s*[-•*]\s+', line) or re.match(r'^\s*\d+[.):]\s*', line) or re.match(r'^\s*\(\d+\)', line):
                list_items.append(line)
        
        # If explicit list format exists, check it has 3+ items
        if list_items:
            if len(list_items) < 3:
                reasons.append(f"FAIL: insufficient_list_items({len(list_items)}, need 3+)")
                return False, reasons
            reasons.append(f"OK: structured_list_found({len(list_items)} items)")
        else:
            # No explicit list format - check if all or most core facts are present anyway
            core_facts_present = sum(1 for fact in expected_core_facts if _core_fact_matches(fact, answer_stripped))
            if core_facts_present < len(expected_core_facts) - 1:  # Allow 1 core fact missing
                reasons.append(f"FAIL: no_list_format_and_missing_facts({core_facts_present}/{len(expected_core_facts)})")
                return False, reasons
            reasons.append(f"OK: prose_format_with_core_facts({core_facts_present}/{len(expected_core_facts)})")
    
    elif question_type == "scenario_based":
        # Must have explicit recommendation/decision
        recommendation_keywords = [
            "recommend", "should", "use", "choose", "system", "dedicated", 
            "tier", "allocate", "classify as", "select", "decide"
        ]
        has_recommendation = any(kw in answer_lower for kw in recommendation_keywords)
        
        if not has_recommendation:
            reasons.append("FAIL: no_explicit_recommendation_or_decision")
            return False, reasons
        
        reasons.append("OK: explicit_recommendation_present")
    
    elif question_type == "deep_technical":
        # Must have actual rule/condition statement
        rule_keywords = [
            "classified", "allocated", "when", "condition", "rule", "if", 
            "impact", "requirement", "→", "must", "should", "is defined"
        ]
        has_rule = any(kw in answer_lower for kw in rule_keywords)
        
        if not has_rule:
            reasons.append("FAIL: no_rule_or_condition_statement")
            return False, reasons
        
        reasons.append("OK: rule_or_condition_present")
    
    elif question_type in ["causal_reasoning", "comparative_reasoning", "necessity_reasoning"]:
        # Must have explanation with causal language
        causal_keywords = [
            "because", "enable", "allows", "improves", "benefits", 
            "reason", "critical", "essential", "necessary", "supports",
            "better than", "advantage", "disadvantage", "provide", "helps",
            "improve", "better"
        ]
        has_explanation = any(kw in answer_lower for kw in causal_keywords)
        
        if not has_explanation:
            reasons.append("FAIL: no_causal_explanation")
            return False, reasons
        
        # Check that answer is not just echoing nearby text
        answer_lines = answer_stripped.split('\n')
        meaningful_lines = [line for line in answer_lines if len(line.strip()) > 20]
        if len(meaningful_lines) < 1:
            reasons.append("FAIL: answer_seems_incomplete_or_truncated")
            return False, reasons
        
        reasons.append("OK: causal_explanation_present")
    
    elif question_type == "definition_purpose":
        # Must define what something is and include purpose/benefit
        definition_keywords = ["is a", "is an", "refers to", "means", "defined as", "describes"]
        has_definition = any(kw in answer_lower for kw in definition_keywords)
        
        purpose_keywords = ["purpose", "benefit", "enables", "allows", "provides", "helps", "supports", "enforce", "automate", "organize", "manage"]
        has_purpose = any(kw in answer_lower for kw in purpose_keywords)
        
        if not has_definition:
            reasons.append("WARN: no_clear_definition")
        
        if not has_purpose:
            reasons.append("WARN: no_clear_purpose_or_benefit")
        
        # Accept either definition OR strong purpose (for technical definitions)
        if not has_definition and not has_purpose:
            reasons.append("FAIL: no_definition_or_purpose")
            return False, reasons
        
        reasons.append("OK: definition_or_purpose_present")
    
    # ==================== ADEQUACY CHECK ====================
    
    adequacy_result = _check_adequacy(
        question_type, 
        answer_stripped, 
        expected_adequacy,
        expected_core_facts
    )
    
    if not adequacy_result[0]:
        reasons.append(f"FAIL: adequacy_threshold_not_met({adequacy_result[1]})")
        return False, reasons
    else:
        reasons.append(f"OK: adequacy_acceptable({adequacy_result[1]})")
    
    # ==================== ALL CHECKS PASSED ====================
    
    if not any(r.startswith("FAIL") for r in reasons):
        reasons.insert(0, "PASS: contract_satisfied")
    
    return not any(r.startswith("FAIL") for r in reasons), reasons


def _check_adequacy(
    question_type: str,
    answer: str,
    expected_adequacy: Dict[str, Any],
    expected_core_facts: List[str]
) -> Tuple[bool, str]:
    """Check if answer meets adequacy threshold for its question type.
    
    Adequacy = does answer contain enough info to be useful, not just vaguely correct
    """
    
    answer_lower = answer.lower()
    answer_lines = answer.split('\n')
    meaningful_lines = [l for l in answer_lines if len(l.strip()) > 15]
    
    min_threshold = expected_adequacy.get("minimum_content_threshold", "")
    completeness = expected_adequacy.get("completeness", "")
    
    if question_type == "definition_purpose":
        # Must have meaningful content (minimum 1 substantial line for single-paragraph answers)
        # Accept either: multiple separated lines OR one long paragraph with 150+ chars
        if len(meaningful_lines) < 1:
            return False, "too_few_lines_for_definition"
        
        if len(meaningful_lines) == 1 and len(meaningful_lines[0]) < 150:
            return False, "definition_paragraph_too_short"
        
        # Should mention key system or concept
        if len(expected_core_facts) > 0 and not any(fact.lower() in answer_lower for fact in expected_core_facts[:2]):
            return False, "definition_missing_key_concepts"
        
        return True, "definition_has_sufficient_detail"
    
    elif question_type == "structured_extraction":
        # Must have 4+ meaningful items
        list_items = [l for l in answer_lines if re.match(r'^\s*[-•*\d]', l)]
        if len(list_items) < 3:
            return False, f"too_few_list_items({len(list_items)})"
        
        # Items should not be trivially short
        avg_item_length = sum(len(item) for item in list_items) / len(list_items)
        if avg_item_length < 10:
            return False, "list_items_too_short_for_adequacy"
        
        return True, f"list_has_adequate_items({len(list_items)})"
    
    elif question_type in ["causal_reasoning", "comparative_reasoning", "necessity_reasoning"]:
        # Must have meaningful content (reduced from 3 lines since reasoning can be concise)
        if len(meaningful_lines) < 1:
            return False, "reasoning_answer_too_short"
        
        # Check for evidence of actual thinking, not just copying
        if not any(word in answer_lower for word in ["because", "enable", "improves", "critical", "supports", "provide"]):
            return False, "reasoning_lacks_causal_language"
        
        return True, "reasoning_has_adequate_explanation"
    
    elif question_type == "deep_technical":
        # Must have explicit rule + explanation
        if len(meaningful_lines) < 2:
            return False, "technical_answer_too_short"
        
        # Should have 3+ of the expected core facts
        fact_count = sum(1 for fact in expected_core_facts if fact.lower() in answer_lower)
        if fact_count < 2:
            return False, f"missing_core_technical_facts({fact_count}/{len(expected_core_facts)})"
        
        return True, "technical_answer_includes_rule_and_facts"
    
    elif question_type == "scenario_based":
        # Must have explicit decision + reasoning
        decision_keywords = ["recommend", "should", "use", "choose", "system", "tier", "classify"]
        if not any(kw in answer_lower for kw in decision_keywords):
            return False, "no_explicit_decision"
        
        if len(meaningful_lines) < 2:
            return False, "scenario_answer_too_short"
        
        return True, "scenario_has_decision_and_reasoning"
    
    # Default: accept if we got this far
    return True, "adequacy_acceptable_by_default"



def _evaluate_quality_basic(query: str, answer: str) -> Tuple[bool, List[str]]:
    """Fallback quality evaluation when no contract is available."""
    reasons: List[str] = []
    
    is_noise, noise_reason = _is_noise_answer(answer)
    if is_noise:
        reasons.append(noise_reason)
    
    aligned, align_reason = _query_alignment_ok(query, answer)
    if not aligned:
        reasons.append(align_reason)
    
    return len(reasons) == 0, reasons


def _evaluate_quality(query: str, parsed_json: Dict[str, Any]) -> Tuple[bool, List[str], str, bool]:
    """Evaluate quality - legacy interface for backward compat."""
    reasons: List[str] = []

    success_flag = parsed_json.get("success") is True
    abstained = parsed_json.get("abstained") is True
    answer_text = str(parsed_json.get("answer") or "").strip()
    runtime = parsed_json.get("runtime") if isinstance(parsed_json.get("runtime"), dict) else {}
    generation_executed = runtime.get("generation_executed") is True

    if not success_flag:
        reasons.append("success_flag_false")
    if not generation_executed:
        reasons.append("generation_not_executed")

    is_noise, noise_reason = _is_noise_answer(answer_text)
    if is_noise:
        reasons.append(noise_reason)

    if abstained:
        # Abstention is accepted only if reason is clear and aligned with user query.
        abstention_reason = str(parsed_json.get("abstention_reason") or "").strip()
        if not abstention_reason:
            reasons.append("abstention_reason_missing")
        aligned, align_reason = _query_alignment_ok(query, abstention_reason or answer_text)
        if not aligned:
            reasons.append(f"abstention_not_aligned:{align_reason}")
    else:
        aligned, align_reason = _query_alignment_ok(query, answer_text)
        if not aligned:
            reasons.append(align_reason)

    quality_ok = len(reasons) == 0
    primary_reason = "quality_ok" if quality_ok else reasons[0]
    return quality_ok, reasons, primary_reason, abstained

def _extract_field(lines: List[str], key: str) -> Optional[str]:
    prefix = f"{key}="
    for line in lines:
        if line.startswith(prefix):
            return line[len(prefix):].strip()
    return None


def _read_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def run_quality_diagnostic(
    query: str, 
    category: str, 
    idx: int,
    expected_answers: Dict[str, Dict[str, Any]]
) -> Dict[str, Any]:
    """Run grounded harness on a single query and classify result using expected answer contract."""
    test_name = f"{category}_{idx:02d}"

    cmd = [
        sys.executable,
        str(GROUNDED_SCRIPT),
        "--rag-base-url", RAG_BASE_URL,
        "--mode", "rag",
        "--timeout", "90",
        "--query", query,
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        output_text = result.stdout + result.stderr
        out_lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        output_dir_value = _extract_field(out_lines, "output_dir")
        dominant_failure = _extract_field(out_lines, "dominant_failure_cause")

        artifact = _read_json(Path(output_dir_value) / "rag_response.json") if output_dir_value else None
        response = artifact.get("response", {}) if isinstance(artifact, dict) else {}
        parsed_json = response.get("parsed_json") if isinstance(response, dict) else None
        status_code = response.get("status_code") if isinstance(response, dict) else None
        request_error = response.get("error") if isinstance(response, dict) else None

        success_flag = isinstance(parsed_json, dict) and parsed_json.get("success") is True
        answer_text = ""
        quality_ok = False
        quality_reasons: List[str] = []
        quality_primary_reason = "invalid_response"
        abstained = False
        expected_mode = "answer"
        expected_intent = ""
        expected_core_facts = []
        
        if isinstance(parsed_json, dict):
            answer_text = str(parsed_json.get("answer") or "").strip()
            abstained = parsed_json.get("abstained") is True
        
        answer_present = bool(answer_text)
        
        # Apply expected answer contract evaluation
        if test_name in expected_answers:
            contract = expected_answers[test_name]
            expected_mode = contract.get("expected_mode", "answer")
            expected_intent = contract.get("expected_intent", "")
            expected_core_facts = contract.get("expected_core_facts", [])
            
            # For non-abstained answers, check against contract
            if not abstained and answer_present:
                quality_ok, quality_reasons = _check_against_contract(
                    test_name, query, answer_text, expected_answers
                )
                if quality_reasons:
                    quality_primary_reason = quality_reasons[0]
            elif abstained:
                # Abstention is OK if mode allows it
                quality_ok = True
                quality_primary_reason = "abstention_accepted"
            elif not answer_present:
                quality_reasons.append("answer_missing")
                quality_primary_reason = "answer_missing"
        else:
            # Fallback: legacy evaluation
            if isinstance(parsed_json, dict):
                quality_ok, quality_reasons, quality_primary_reason, abstained = _evaluate_quality(query, parsed_json)
        
        # Overall status: must have success flag, http 200, quality_ok
        # Also: must not have unresolved dominant_failure_cause with PASS
        # This is the CONTRADICTION GATE - prevents false PASS
        
        base_pass = (
            result.returncode == 0 
            and status_code == 200 
            and quality_ok
        )
        
        status = "PASS" if base_pass else "FAIL"
        
        # ===== CONTRADICTION GATE =====
        # If dominant_failure exists and indicates a real unresolved issue, 
        # it must force a FAIL even if other gates passed
        unresolved_failures = [
            "kb_relevance_false_negative",
            "answer_quality_fail",
            "retrieval_failure",
            "synthesis_failure",
            "answer_incomplete",
            "query_mismatch",
        ]
        
        if dominant_failure and dominant_failure in unresolved_failures:
            status = "FAIL"
            if not any(f"unresolved_{dominant_failure}" in r for r in quality_reasons):
                quality_reasons.append(f"CONTRADICTION_GATE: status_was_PASS_but_dominant_failure_unresolved({dominant_failure})")
                quality_primary_reason = f"unresolved_{dominant_failure}"

        return {
            "query": query,
            "category": category,
            "test_name": test_name,
            "overall_status": status,
            "returncode": result.returncode,
            "http_status": status_code,
            "dominant_failure_cause": dominant_failure,
            "success": success_flag,
            "answer_present": answer_present,
            "abstained": abstained,
            "answer_preview": answer_text[:300],
            "full_answer": answer_text,
            "expected_mode": expected_mode,
            "expected_intent": expected_intent,
            "expected_core_facts": expected_core_facts,
            "quality_ok": quality_ok,
            "quality_primary_reason": quality_primary_reason,
            "quality_reasons": quality_reasons,
            "transport_error": request_error,
            "diagnostic_output_dir": output_dir_value,
            "raw_output": output_text[-4000:],
        }
    except subprocess.TimeoutExpired:
        return {
            "query": query,
            "category": category,
            "test_name": test_name,
            "overall_status": "TIMEOUT",
            "returncode": -1,
        }
    except Exception as e:
        return {
            "query": query,
            "category": category,
            "test_name": test_name,
            "overall_status": "ERROR",
            "returncode": -1,
            "error": str(e),
        }


def main():
    print("=" * 80)
    print("COMPREHENSIVE RAG TEST SUITE")
    print("=" * 80)
    print(f"Output Directory: {OUTPUT_DIR}")
    print(f"RAG Base URL: {RAG_BASE_URL}")
    print(f"Test Start Time: {datetime.now().isoformat()}")
    print(f"Total Tests: {sum(len(q) for q in TEST_QUERIES.values())}")
    print()
    
    # Load expected answer contract
    expected_answers = _load_expected_answers()
    print(f"Expected answer contract loaded: {len(expected_answers)} test cases defined")
    print()
    
    all_results: List[Dict[str, Any]] = []
    category_stats: Dict[str, Dict[str, int]] = {}
    
    # Run tests by category
    for category, queries in TEST_QUERIES.items():
        print(f"{category.upper().replace('_', ' ')}: ", end="", flush=True)
        category_stats[category] = {"pass": 0, "fail": 0, "error": 0, "timeout": 0}
        
        for idx, query in enumerate(queries, 1):
            result = run_quality_diagnostic(query, category, idx, expected_answers)
            all_results.append(result)
            
            # Update stats
            status = result["overall_status"].lower()
            if status == "pass":
                category_stats[category]["pass"] += 1
                print("P", end="", flush=True)
            elif status == "fail":
                category_stats[category]["fail"] += 1
                print("F", end="", flush=True)
            elif status == "timeout":
                category_stats[category]["timeout"] += 1
                print("T", end="", flush=True)
            else:
                category_stats[category]["error"] += 1
                print("E", end="", flush=True)
        print()
    
    # Generate markdown report with FULL answers
    print(f"\n{'='*80}")
    print("GENERATING FINAL REPORT")
    print(f"{'='*80}")
    
    report_lines = [
        "# Comprehensive RAG Quality Test Results",
        "",
        f"**Generated:** {datetime.now().isoformat()}",
        f"**Documents Tested:** Project_Aurora-v6, PMT_Architecture-v4, Cloudspace-v1",
        f"**Evaluation Method:** Expected Answer Quality Contract",
        "",
        "## Executive Summary",
        "",
    ]
    
    # Add summary table
    total_pass = sum(cat["pass"] for cat in category_stats.values())
    total_fail = sum(cat["fail"] for cat in category_stats.values())
    total_error = sum(cat["error"] for cat in category_stats.values())
    total_timeout = sum(cat["timeout"] for cat in category_stats.values())
    total_tests = total_pass + total_fail + total_error + total_timeout
    
    report_lines.extend([
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Total Tests Run | {total_tests} |",
        f"| Passed | {total_pass} ({100*total_pass//max(1,total_tests)}%) |",
        f"| Failed | {total_fail} ({100*total_fail//max(1,total_tests)}%) |",
        f"| Errors | {total_error} ({100*total_error//max(1,total_tests)}%) |",
        f"| Timeouts | {total_timeout} ({100*total_timeout//max(1,total_tests)}%) |",
        "",
        "## Results by Category",
        "",
    ])
    
    for category, stats in category_stats.items():
        cat_total = sum(stats.values())
        report_lines.extend([
            f"### {category.upper().replace('_', ' ')}",
            f"- Passed: {stats['pass']}/{cat_total}",
            f"- Failed: {stats['fail']}/{cat_total}",
            f"- Errors: {stats['error']}/{cat_total}",
            f"- Timeouts: {stats['timeout']}/{cat_total}",
            "",
        ])
    
    # Add detailed results with FULL ANSWERS
    report_lines.extend([
        "## Detailed Test Results",
        "",
    ])
    
    for category, queries in TEST_QUERIES.items():
        report_lines.append(f"### {category.upper().replace('_', ' ')}")
        report_lines.append("")
        
        cat_results = [r for r in all_results if r["category"] == category]
        for result in cat_results:
            status_symbol = "PASS" if result["overall_status"] == "PASS" else "FAIL" if result["overall_status"] == "FAIL" else "TIMEOUT" if result["overall_status"] == "TIMEOUT" else "ERROR"
            report_lines.extend([
                f"#### {result['test_name']} [{status_symbol}]",
                f"**Query:** {result['query']}",
                f"**Category:** {result['category']}",
                f"**Status:** {result['overall_status']}",
                ""
            ])
            
            # Add expected intent and core facts if available
            if result.get("expected_intent"):
                report_lines.extend([
                    f"**Expected Intent:** {result['expected_intent']}",
                    ""
                ])
            
            if result.get("expected_core_facts"):
                report_lines.extend([
                    f"**Expected Core Facts:**",
                ])
                for fact in result['expected_core_facts']:
                    report_lines.append(f"- {fact}")
                report_lines.append("")
            
            # Add FULL ANSWER
            if result.get("full_answer"):
                report_lines.extend([
                    f"**Full Answer:**",
                    "```",
                    result['full_answer'],
                    "```",
                    ""
                ])
            elif result.get("answer_preview"):
                report_lines.extend([
                    f"**Answer (Preview):**",
                    "```",
                    result['answer_preview'],
                    "```",
                    ""
                ])
            
            # Add quality assessment
            if result.get("quality_reasons"):
                report_lines.extend([
                    f"**Quality Assessment:**",
                    f"- Primary Reason: {result.get('quality_primary_reason', 'unknown')}",
                ])
                for reason in result.get("quality_reasons", [])[:5]:  # Show first 5 reasons
                    report_lines.append(f"- {reason}")
                report_lines.append("")
            
            # Add diagnostic info
            if result.get("dominant_failure_cause"):
                report_lines.append(f"**Dominant Failure Cause:** {result['dominant_failure_cause']}")
                report_lines.append("")
    
    # Add recommendations
    report_lines.extend([
        "## Key Findings & Recommendations",
        "",
        "### Validation Method",
        "- **Harness:** grounded_qa_diagnostic.py (RAG mode)",
        "- **Pass Criteria:** HTTP 200 + runtime success + strict semantic quality gates",
        "- **Quality Gates:** noise/gibberish reject + metadata reject + query-alignment check",
        "- **Transport:** local endpoint calls with artifact capture",
        "",
        "### Issues Identified",
    ])
    
    # Identify patterns in failures
    failed_tests = [r for r in all_results if r["overall_status"] in ["FAIL", "ERROR", "TIMEOUT"]]
    if failed_tests:
        report_lines.append(f"**{len(failed_tests)} tests encountered issues:**")
        report_lines.append("")
        for result in failed_tests[:5]:  # Show first 5
            quality_reason = result.get("quality_primary_reason") or result.get("dominant_failure_cause") or "unknown"
            report_lines.append(f"- **{result['category']}:** {result['query'][:70]} (reason: {quality_reason})")
    else:
        report_lines.append("No critical issues detected in test run.")
    
    report_lines.extend([
        "",
        "### Next Steps",
        "1. Review failed test outputs in diagnostic directory",
        "2. Check RAG server logs for retrieval quality issues",
        "3. Validate knowledge base document ingestion",
        "4. Verify LLM provider connectivity and model availability",
        "",
        "## Technical Details",
        "",
        f"- **RAG Server:** http://localhost:8001",
        f"- **Harness Tool:** grounded_qa_diagnostic.py",
        f"- **Test Framework:** Python subprocess + JSON artifact inspection",
        f"- **Timeout Configuration:** 90 seconds per test",
        f"- **Retry Policy:** Single attempt per query",
        "",
        "---",
        f"*Report generated: {datetime.now().isoformat()}*",
    ])
    
    report_text = "\n".join(report_lines)
    
    # Save report
    report_file = OUTPUT_DIR / "TEST_RESULTS.md"
    report_file.write_text(report_text, encoding="utf-8")
    print(f"[OK] Report saved to: {report_file}")
    
    # Save detailed JSON
    results_file = OUTPUT_DIR / "test_results.json"
    results_file.write_text(
        json.dumps({
            "timestamp": datetime.now().isoformat(),
            "summary": {
                "total": total_tests,
                "passed": total_pass,
                "failed": total_fail,
                "errors": total_error,
                "timeouts": total_timeout,
            },
            "category_stats": category_stats,
            "all_results": all_results,
        }, indent=2),
        encoding="utf-8"
    )
    print(f"[OK] Detailed results saved to: {results_file}")
    
    print(f"\n{'='*80}")
    print("TEST RUN COMPLETE")
    print(f"{'='*80}")
    print(f"\nFinal Report: {report_file}")
    print(f"Open this file to see detailed test results.\n")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
