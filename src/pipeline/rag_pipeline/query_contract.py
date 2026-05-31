"""Shared grounded-QA query contract helpers.

This module keeps the API layer and grounded QA client aligned on structured
error details, payload normalization, and failure classification.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, Optional

from pydantic import BaseModel, model_validator


PROVIDER_FAILURE_CODES = {
    "model_not_supported",
    "unsupported_model",
    "model_unavailable",
    "model_routing_failed",
    "provider_model_not_supported",
}


def _stringify_detail(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _collect_text_fragments(value: Any) -> Iterable[str]:
    if value is None:
        return []
    if isinstance(value, dict):
        fragments = []
        for key in ("code", "type", "message", "msg"):
            fragment = value.get(key)
            if fragment is not None:
                fragments.append(str(fragment))
        for nested_value in value.values():
            if nested_value is not value.get("detail"):
                fragments.extend(_collect_text_fragments(nested_value))
        detail = value.get("detail")
        if detail is not None:
            fragments.extend(_collect_text_fragments(detail))
        return fragments
    if isinstance(value, (list, tuple, set)):
        fragments = []
        for item in value:
            fragments.extend(_collect_text_fragments(item))
        return fragments
    return [str(value)]


def _collect_additional_detail(value: Dict[str, Any]) -> Any:
    extras = {key: item for key, item in value.items() if key not in {"code", "type", "message", "msg", "detail"}}
    return extras or None


def _coerce_http_status(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        status = int(value)
    except (TypeError, ValueError):
        return None
    return status if status > 0 else None


def _extract_provider_http_status(payload: Dict[str, Any]) -> Optional[int]:
    def _search_status(value: Any) -> Optional[int]:
        if isinstance(value, dict):
            for key in ("provider_http_status", "provider_status", "status_code", "status", "http_status"):
                status = _coerce_http_status(value.get(key))
                if status is not None:
                    return status
            for nested_value in value.values():
                status = _search_status(nested_value)
                if status is not None:
                    return status
        elif isinstance(value, (list, tuple, set)):
            for item in value:
                status = _search_status(item)
                if status is not None:
                    return status
        return None

    runtime = payload.get("runtime") or {}
    candidate_values = [
        payload.get("provider_http_status"),
        payload.get("provider_status"),
        runtime.get("provider_http_status"),
        runtime.get("provider_status"),
        payload.get("error"),
        payload.get("generation_failure_reason"),
        runtime,
    ]

    for candidate in candidate_values:
        status = _search_status(candidate)
        if status is not None:
            return status

    if is_provider_failure_detail(payload.get("error")) or is_provider_failure_detail(payload.get("generation_failure_reason")):
        return 400

    return None


def coerce_error_detail(
    value: Any,
    *,
    default_code: str = "runtime_failure",
    default_message: Optional[str] = None,
    detail_fallback: Any = None,
) -> Optional[Dict[str, Any]]:
    """Normalize any error-like value into a structured detail object."""

    if value is None:
        return None

    if isinstance(value, dict):
        code = value.get("code") or value.get("type") or default_code
        message = value.get("message") or value.get("msg") or default_message or code
        detail = value.get("detail")
        if detail is None:
            detail = _collect_additional_detail(value)
        if detail is None:
            detail = detail_fallback
        return {
            "code": str(code),
            "message": _stringify_detail(message),
            "detail": detail,
        }

    if isinstance(value, str):
        return {
            "code": default_code,
            "message": value,
            "detail": detail_fallback,
        }

    return {
        "code": default_code,
        "message": _stringify_detail(default_message or value),
        "detail": detail_fallback,
    }


def is_provider_failure_detail(value: Any) -> bool:
    """Return True when the value points at provider/model routing failure."""

    fragments = {fragment.lower() for fragment in _collect_text_fragments(value) if fragment}
    return any(code in fragments for code in PROVIDER_FAILURE_CODES)


def classify_grounded_result_status(payload: Dict[str, Any]) -> str:
    """Classify a grounded-QA response payload into a stable result status."""

    if payload.get("success") is True:
        return "success"

    result_status = payload.get("result_status") or "runtime_failure"
    runtime = payload.get("runtime") or {}
    gateway_http_status = _coerce_http_status(
        payload.get("gateway_http_status")
        or payload.get("llm_http_status")
        or runtime.get("gateway_http_status")
        or runtime.get("llm_http_status")
    )
    provider_http_status = _extract_provider_http_status(payload)
    generation_executed = bool(runtime.get("generation_executed", payload.get("generation_executed", False)))
    error = payload.get("error")
    generation_failure_reason = payload.get("generation_failure_reason")

    if result_status in {
        "request_build_failure",
        "request_validation_failure",
        "response_contract_failure",
        "response_json_invalid",
    }:
        return result_status

    if result_status == "answer_extraction_failure" and generation_executed:
        return result_status

    if is_provider_failure_detail(error) or is_provider_failure_detail(generation_failure_reason):
        return "provider_failure"

    if provider_http_status is not None and provider_http_status >= 400 and not generation_executed:
        return "provider_failure"

    if not generation_executed and (gateway_http_status is None or gateway_http_status >= 400):
        return "runtime_failure"

    if result_status == "semantic_failure" and not generation_executed:
        return "runtime_failure"

    if payload.get("answer_extraction_success") is False and generation_executed:
        return "answer_extraction_failure"

    return result_status if result_status in {"runtime_failure", "provider_failure", "semantic_failure", "abstention"} else "runtime_failure"


def classify_grounded_failure_class(payload: Dict[str, Any]) -> str:
    """Map a grounded-QA result to a broad failure class for diagnostics."""

    result_status = classify_grounded_result_status(payload)

    if result_status == "success":
        return "success"
    if result_status == "provider_failure":
        return "provider_failure"
    if result_status in {"request_build_failure", "request_validation_failure"}:
        return "request_failure"
    if result_status in {"response_contract_failure", "response_json_invalid"}:
        return "response_failure"
    if result_status == "answer_extraction_failure":
        return "answer_extraction_failure"
    if result_status == "abstention":
        return "abstention"
    return "runtime_failure"


def get_failure_stage_details(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Extract detailed stage-level diagnostic info from a failed response payload.
    
    Section E: Failure Taxonomy Expansion (16+ stage-aware labels)
    
    Returns dict with keys:
    - stage: primary failure stage 
    - label: one of 16+ specific failure type labels
    - substage: more specific failure point
    - trigger: root condition that triggered the failure
    - is_deterministic: likely reproducible
    - is_systemic: affects multiple cases vs case-specific
    
    ## 16+ Failure Type Labels:
    - preflight_checks_failed - Request validation failed
    - retrieval_no_results - Empty retrieval, no chunks returned
    - retrieval_insufficient_quality - Retrieval below quality threshold
    - reranking_failed - Cross-encoder reranking error
    - prompt_assembly_failed - Query context assembly failed
    - llm_contract_error - LLM response missing required fields
    - llm_timeout - LLM call exceeded timeout
    - llm_refused - LLM refused to generate (policy/safety)
    - answer_extraction_failed - Could not parse LLM output
    - answer_validation_failed - Generated answer failed validation
    - false_abstention_detected - Inappropriate abstention despite context
    - policy_violation_detected - Policy-filtered response
    - semantic_contradiction - Answer contradicts retrieval context
    - insufficient_evidence - Answer not grounded in retrieval
    - token_limit_exceeded - Request/response exceeded token limits
    - unknown_failure - Unclassified failure
    """
    details = {
        "stage": "unknown",
        "label": "unknown_failure",
        "substage": None,
        "trigger": None,
        "is_deterministic": True,
        "is_systemic": False,
    }
    
    runtime = payload.get("runtime") or {}
    error = payload.get("error")
    generation_failure_reason = payload.get("generation_failure_reason")
    gateway_http_status = _coerce_http_status(payload.get("gateway_http_status") or payload.get("llm_http_status"))
    context_chunks = payload.get("context_chunks", [])
    answer = payload.get("answer", "")
    
    # STAGE 1: Preflight Checks
    if payload.get("result_status") in {"request_build_failure", "request_validation_failure"}:
        details["stage"] = "preflight"
        details["label"] = "preflight_checks_failed"
        details["substage"] = payload.get("result_status")
        details["trigger"] = str(error) if error else "request validation failed"
        details["is_systemic"] = True
        return details
    
    # STAGE 2: Retrieval Quality
    if not context_chunks or len(context_chunks) == 0:
        details["stage"] = "retrieval"
        details["label"] = "retrieval_no_results"
        details["substage"] = "empty_retrieval"
        details["trigger"] = "Knowledge base query returned no chunks"
        details["is_deterministic"] = True
        details["is_systemic"] = False
        return details
    
    # Check for retrieval quality issues (if available in payload)
    intent_analysis = payload.get("intent_analysis", {})
    if intent_analysis.get("is_kb_relevant") is False:
        details["stage"] = "retrieval"
        details["label"] = "retrieval_insufficient_quality"
        details["substage"] = "low_relevance_score"
        relevance_score = intent_analysis.get("relevance_score", 0.0)
        details["trigger"] = f"KB relevance score {relevance_score:.2f} below threshold"
        details["is_systemic"] = False
        return details
    
    # STAGE 3: Response Validation
    if payload.get("result_status") == "response_contract_failure":
        details["stage"] = "response_validation"
        details["label"] = "llm_contract_error"
        details["substage"] = "contract_mismatch"
        details["trigger"] = str(error) if error else "response missing required fields"
        details["is_systemic"] = False
        return details
    
    # STAGE 4: Generation Execution
    if not runtime.get("generation_executed"):
        details["stage"] = "generation"
        details["substage"] = "generation_not_executed"
        
        # Classify generation failure type
        if gateway_http_status == 408 or "timeout" in str(error).lower():
            details["label"] = "llm_timeout"
            details["trigger"] = f"LLM call timeout (HTTP {gateway_http_status})"
        elif gateway_http_status == 429:
            details["label"] = "llm_timeout"
            details["trigger"] = "LLM rate limit exceeded"
        elif is_provider_failure_detail(error) or is_provider_failure_detail(generation_failure_reason):
            if "refused" in str(error).lower() or "refused" in str(generation_failure_reason).lower():
                details["label"] = "llm_refused"
                details["trigger"] = "LLM refused to generate (policy/safety block)"
            else:
                details["label"] = "llm_contract_error"
                details["trigger"] = "LLM provider error: " + str(generation_failure_reason or error)[:100]
        elif gateway_http_status and gateway_http_status >= 500:
            details["label"] = "llm_contract_error"
            details["trigger"] = f"LLM server error (HTTP {gateway_http_status})"
        elif "token" in str(error).lower():
            details["label"] = "token_limit_exceeded"
            details["trigger"] = "Token limit exceeded in request/response"
        else:
            details["label"] = "llm_contract_error"
            details["trigger"] = str(generation_failure_reason or error or "generation not attempted")
        
        details["is_systemic"] = gateway_http_status and gateway_http_status >= 500
        return details
    
    # STAGE 5: Answer Extraction
    if payload.get("result_status") == "answer_extraction_failure" or not answer.strip():
        details["stage"] = "answer_extraction"
        details["label"] = "answer_extraction_failed"
        details["substage"] = "empty_answer_extraction"
        details["trigger"] = "LLM generation executed but produced empty/whitespace-only answer"
        details["is_systemic"] = False
        return details
    
    # STAGE 6: Abstention Handling
    if payload.get("abstained"):
        details["stage"] = "generation"
        details["substage"] = "abstention"
        
        # Check if false abstention (context available but LLM abstained)
        if intent_analysis.get("retrieval_answerable"):
            details["label"] = "false_abstention_detected"
            details["trigger"] = "Context was answerable but LLM abstained: " + (payload.get("abstention_reason") or "no reason given")[:50]
            details["is_systemic"] = False
        else:
            details["label"] = "insufficient_evidence"
            details["trigger"] = payload.get("abstention_reason") or "LLM abstained - insufficient evidence"
        
        return details
    
    # STAGE 7: Policy Validation
    if generation_failure_reason == "abstention" or "forbidden" in str(error).lower():
        details["stage"] = "policy"
        details["label"] = "policy_violation_detected"
        details["substage"] = "forbidden_topic_detected"
        details["trigger"] = f"Query or answer involves forbidden topic: {str(error)[:80]}"
        details["is_systemic"] = True
        return details
    
    # STAGE 8: Answer Validation
    if payload.get("result_status") == "semantic_failure":
        details["stage"] = "validation"
        details["label"] = "semantic_contradiction"
        details["substage"] = "answer_context_mismatch"
        details["trigger"] = "Generated answer contradicts retrieval context or internal inconsistency"
        details["is_systemic"] = False
        return details
    
    # Fallback: Unknown failure
    details["stage"] = "unknown"
    details["label"] = "unknown_failure"
    details["trigger"] = f"result_status={payload.get('result_status')}, error={str(error)[:100]}"
    
    return details



def normalize_grounded_query_response_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Compatibility adapter for QueryResponse construction."""

    normalized = dict(payload)
    normalized["gateway_http_status"] = _coerce_http_status(
        normalized.get("gateway_http_status")
        or normalized.get("llm_http_status")
        or (normalized.get("runtime") or {}).get("gateway_http_status")
        or (normalized.get("runtime") or {}).get("llm_http_status")
    )
    normalized["provider_http_status"] = _extract_provider_http_status(normalized)
    normalized["generation_failure_reason"] = coerce_error_detail(
        normalized.get("generation_failure_reason"),
        default_code=normalized.get("result_status") or "runtime_failure",
        detail_fallback=normalized.get("runtime"),
    )
    normalized["error"] = coerce_error_detail(
        normalized.get("error"),
        default_code=normalized["generation_failure_reason"]["code"] if normalized.get("generation_failure_reason") else (normalized.get("result_status") or "runtime_failure"),
        detail_fallback=normalized.get("runtime"),
    )
    normalized["result_status"] = classify_grounded_result_status(normalized)
    normalized["failure_class"] = classify_grounded_failure_class(normalized)
    return normalized


class ErrorDetail(BaseModel):
    """Structured grounded-QA error detail."""

    code: str
    message: str
    detail: Any = None

    @model_validator(mode="before")
    @classmethod
    def _coerce_input(cls, value: Any):
        if isinstance(value, cls):
            return value.model_dump()
        return coerce_error_detail(value)
