"""Grounded QA request/response orchestration for the RAG server.

This module owns the structured /qa/answer contract, response normalization,
and the query orchestration used by the FastAPI API layer.
"""

from __future__ import annotations

import copy
import logging
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple
from uuid import uuid4

import requests

from ...core.config import (
    COPILOT_API_BASE_URL,
    COPILOT_API_RETRY_BACKOFF_SECONDS,
    COPILOT_API_RETRY_COUNT,
    COPILOT_API_TIMEOUT_SECONDS,
    COPILOT_API_USER_AGENT,
    DEFAULT_GROUNDED_ANSWER_POLICY,
    DEFAULT_GROUNDED_GENERATION_OPTIONS,
    DEFAULT_GROUNDED_MODEL,
    GROUNDED_QA_ENDPOINT,
)
from .query_contract import (
    classify_grounded_failure_class,
    classify_grounded_result_status,
    coerce_error_detail,
    is_provider_failure_detail,
)

logger = logging.getLogger(__name__)

REQUIRED_RESPONSE_KEYS = {
    "request_id",
    "success",
    "model_requested",
    "model_used",
    "query",
    "answer",
    "abstained",
    "abstention_reason",
    "citations",
    "grounding_summary",
    "runtime",
    "error",
}

REQUIRED_RUNTIME_KEYS = {
    "llm_invocation_attempted",
    "llm_http_status",
    "llm_transport_success",
    "llm_response_json_valid",
    "llm_response_schema_valid",
    "answer_extraction_success",
    "generation_executed",
    "generation_failure_reason",
}

VALID_REQUEST_FAILURE_STATUSES = {
    "request_build_failure",
    "request_validation_failure",
    "provider_failure",
    "runtime_failure",
    "semantic_failure",
    "answer_extraction_failure",
    "success",
    "abstention",
}


def generate_request_id(prefix: str = "qa") -> str:
    return f"{prefix}_{uuid4().hex}"


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _normalize_query(query: Any) -> Tuple[Optional[str], List[str]]:
    errors: List[str] = []
    if not isinstance(query, str):
        return None, ["query must be a non-empty string"]
    normalized = query.strip()
    if not normalized:
        errors.append("query must be a non-empty string")
    return normalized or None, errors


def _normalize_context_chunks_for_request(
    context_chunks: Sequence[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[str], List[int]]:
    normalized_chunks: List[Dict[str, Any]] = []
    errors: List[str] = []
    ranks: List[int] = []

    if not isinstance(context_chunks, Sequence) or isinstance(context_chunks, (str, bytes)):
        return [], ["context_chunks must be an array of chunk objects"], []

    for index, chunk in enumerate(context_chunks, start=1):
        if not isinstance(chunk, dict):
            errors.append(f"context_chunks[{index - 1}] must be an object")
            continue

        text = chunk.get("text")
        if not isinstance(text, str):
            errors.append(f"context_chunks[{index - 1}].text must be a string")
            continue

        normalized_text = text.strip()
        if not normalized_text:
            errors.append(f"context_chunks[{index - 1}].text must be non-empty")
            continue

        metadata = chunk.get("metadata")
        if metadata is None:
            metadata = {}
        elif not isinstance(metadata, dict):
            errors.append(f"context_chunks[{index - 1}].metadata must be an object")
            continue

        retrieval_score = chunk.get("retrieval_score", 0.0)
        reranker_score = chunk.get("reranker_score", 0.0)
        if not _is_number(retrieval_score):
            errors.append(f"context_chunks[{index - 1}].retrieval_score must be numeric")
            continue
        if not _is_number(reranker_score):
            errors.append(f"context_chunks[{index - 1}].reranker_score must be numeric")
            continue

        normalized_rank = index
        if normalized_rank < 1:
            errors.append(f"context_chunks[{index - 1}].rank must be greater than or equal to 1")
            continue

        ranks.append(normalized_rank)
        normalized_chunks.append(
            {
                "rank": normalized_rank,
                "text": normalized_text,
                "metadata": copy.deepcopy(metadata),
                "retrieval_score": max(0.0, min(1.0, float(retrieval_score))),
                "reranker_score": float(reranker_score),
            }
        )

    if not normalized_chunks:
        errors.append("context_chunks must not be empty")

    return normalized_chunks, errors, ranks


def _normalize_answer_policy(overrides: Optional[Dict[str, Any]] = None) -> Tuple[Dict[str, Any], List[str]]:
    policy = copy.deepcopy(DEFAULT_GROUNDED_ANSWER_POLICY)
    errors: List[str] = []

    if overrides is not None and not isinstance(overrides, dict):
        return policy, ["answer_policy must be an object"]

    merged = copy.deepcopy(overrides or {})
    if "grounded_only" in merged:
        if isinstance(merged["grounded_only"], bool):
            policy["grounded_only"] = merged["grounded_only"]
        else:
            errors.append("answer_policy.grounded_only must be boolean")
    if "allow_light_semantic_inference" in merged:
        if isinstance(merged["allow_light_semantic_inference"], bool):
            policy["allow_light_semantic_inference"] = merged["allow_light_semantic_inference"]
        else:
            errors.append("answer_policy.allow_light_semantic_inference must be boolean")
    if "abstain_if_insufficient" in merged:
        if isinstance(merged["abstain_if_insufficient"], bool):
            policy["abstain_if_insufficient"] = merged["abstain_if_insufficient"]
        else:
            errors.append("answer_policy.abstain_if_insufficient must be boolean")
    if "return_citations" in merged:
        if isinstance(merged["return_citations"], bool):
            policy["return_citations"] = merged["return_citations"]
        else:
            errors.append("answer_policy.return_citations must be boolean")
    if "max_answer_sentences" in merged:
        value = merged["max_answer_sentences"]
        if _is_positive_int(value):
            policy["max_answer_sentences"] = int(value)
        else:
            errors.append("answer_policy.max_answer_sentences must be a positive integer")
    forbidden_topics = merged.get("forbidden_topics")
    if forbidden_topics is not None:
        if isinstance(forbidden_topics, list) and all(isinstance(topic, str) for topic in forbidden_topics):
            policy["forbidden_topics"] = [topic.strip() for topic in forbidden_topics if topic.strip()]
        else:
            errors.append("answer_policy.forbidden_topics must be a list of strings")

    policy.setdefault("grounded_only", True)
    policy.setdefault("allow_light_semantic_inference", True)
    policy.setdefault("abstain_if_insufficient", True)
    policy.setdefault("return_citations", True)
    policy.setdefault("max_answer_sentences", 4)
    policy.setdefault("forbidden_topics", ["GitHub", "repositories", "version control"])
    return policy, errors


def _normalize_generation_options(
    overrides: Optional[Dict[str, Any]] = None,
) -> Tuple[Dict[str, Any], List[str], Dict[str, Any]]:
    options: Dict[str, Any] = {}
    errors: List[str] = []
    summary: Dict[str, Any] = {"max_tokens_included": False, "max_tokens_valid": False}

    if overrides is not None and not isinstance(overrides, dict):
        return {}, ["generation_options must be an object"], summary

    merged = copy.deepcopy(DEFAULT_GROUNDED_GENERATION_OPTIONS)
    if overrides:
        merged.update({key: value for key, value in overrides.items() if value is not None})

    temperature = merged.get("temperature", 0.2)
    if _is_number(temperature):
        temperature_value = float(temperature)
        if temperature_value < 0.0:
            temperature_value = 0.0
        if temperature_value > 2.0:
            temperature_value = 2.0
        options["temperature"] = temperature_value
    else:
        errors.append("generation_options.temperature must be numeric")

    stream = merged.get("stream", False)
    if isinstance(stream, bool):
        options["stream"] = stream
    elif stream is not None:
        errors.append("generation_options.stream must be boolean")

    top_p = merged.get("top_p")
    if top_p is None:
        options["top_p"] = 1.0
    elif _is_number(top_p):
        options["top_p"] = max(0.0, min(1.0, float(top_p)))
    else:
        errors.append("generation_options.top_p must be numeric")

    max_tokens = merged.get("max_tokens")
    if max_tokens is None:
        summary["max_tokens_valid"] = True
    elif _is_positive_int(max_tokens):
        options["max_tokens"] = int(max_tokens)
        summary["max_tokens_included"] = True
        summary["max_tokens_valid"] = True
    elif isinstance(max_tokens, int) and not isinstance(max_tokens, bool) and max_tokens <= 0:
        summary["max_tokens_valid"] = True
    elif max_tokens is not None:
        errors.append("generation_options.max_tokens must be a positive integer if provided")

    return options, errors, summary


def _validate_preflight_payload(payload: Dict[str, Any]) -> List[str]:
    errors: List[str] = []

    request_id = payload.get("request_id")
    if not isinstance(request_id, str) or not request_id.strip():
        errors.append("request_id must be a non-empty string")

    model = payload.get("model")
    if not isinstance(model, str) or not model.strip():
        errors.append("model must be a non-empty string")

    query = payload.get("query")
    if not isinstance(query, str) or not query.strip():
        errors.append("query must be a non-empty string")

    context_chunks = payload.get("context_chunks")
    if not isinstance(context_chunks, list) or not context_chunks:
        errors.append("context_chunks must be a non-empty array")
    else:
        for index, chunk in enumerate(context_chunks):
            if not isinstance(chunk, dict):
                errors.append(f"context_chunks[{index}] must be an object")
                continue
            rank = chunk.get("rank")
            if not _is_positive_int(rank):
                errors.append(f"context_chunks[{index}].rank must be greater than or equal to 1")
            if not isinstance(chunk.get("text"), str) or not chunk.get("text", "").strip():
                errors.append(f"context_chunks[{index}].text must be a non-empty string")
            if not isinstance(chunk.get("metadata", {}), dict):
                errors.append(f"context_chunks[{index}].metadata must be an object")
            if not _is_number(chunk.get("retrieval_score")):
                errors.append(f"context_chunks[{index}].retrieval_score must be numeric")
            if not _is_number(chunk.get("reranker_score")):
                errors.append(f"context_chunks[{index}].reranker_score must be numeric")

    answer_policy = payload.get("answer_policy")
    if not isinstance(answer_policy, dict):
        errors.append("answer_policy must be an object")
    else:
        for key in ["grounded_only", "allow_light_semantic_inference", "abstain_if_insufficient", "return_citations"]:
            if key in answer_policy and not isinstance(answer_policy[key], bool):
                errors.append(f"answer_policy.{key} must be boolean")
        if "max_answer_sentences" in answer_policy and not _is_positive_int(answer_policy["max_answer_sentences"]):
            errors.append("answer_policy.max_answer_sentences must be a positive integer")

    generation_options = payload.get("generation_options")
    if not isinstance(generation_options, dict):
        errors.append("generation_options must be an object")
    else:
        temperature = generation_options.get("temperature")
        if temperature is not None and not _is_number(temperature):
            errors.append("generation_options.temperature must be numeric")
        stream = generation_options.get("stream")
        if stream is not None and not isinstance(stream, bool):
            errors.append("generation_options.stream must be boolean")
        top_p = generation_options.get("top_p")
        if top_p is not None and not _is_number(top_p):
            errors.append("generation_options.top_p must be numeric")
        max_tokens = generation_options.get("max_tokens")
        if max_tokens is not None and not _is_positive_int(max_tokens):
            errors.append("generation_options.max_tokens must be a positive integer if provided")

    return errors


def _extract_validation_errors(response_body: Any, response_text: str) -> str:
    if isinstance(response_body, dict):
        detail = response_body.get("detail")
        if isinstance(detail, list):
            messages: List[str] = []
            for item in detail:
                if isinstance(item, dict):
                    location = item.get("loc", [])
                    message = item.get("msg") or item.get("message") or str(item)
                    if location:
                        messages.append(f"{'.'.join(str(part) for part in location)}: {message}")
                    else:
                        messages.append(str(message))
                else:
                    messages.append(str(item))
            if messages:
                return "; ".join(messages)
        if isinstance(detail, str):
            return detail
        if response_body.get("error"):
            return str(response_body.get("error"))
    return response_text


def _infer_failure_code(*values: Any, fallback: str = "runtime_failure") -> str:
    for value in values:
        if isinstance(value, dict):
            code = value.get("code") or value.get("type")
            if code:
                return str(code)
        elif isinstance(value, str) and value.strip():
            return value.strip()
    return fallback


def _normalize_grounding_summary(grounding_summary: Any) -> Dict[str, Any]:
    """Ensure grounding_summary is a valid dict with required fields.
    
    This normalization is based on the diagnostic tool's schema analysis.
    It ensures that even if the LLM returns an invalid grounding_summary,
    we have a well-formed structure for downstream processing.
    
    Args:
        grounding_summary: The grounding_summary from the LLM response (may be None, string, list, dict, etc.)
        
    Returns:
        A valid dict with fields: used_context_ranks (list) and light_semantic_inference_used (bool)
    """
    # If not a dict, create valid structure
    if not isinstance(grounding_summary, dict):
        logger.warning(f"grounding_summary is {type(grounding_summary).__name__}, expected dict. Using valid fallback.")
        return {
            "used_context_ranks": [],
            "light_semantic_inference_used": False
        }
    
    # Validate and fix field types
    normalized: Dict[str, Any] = {}
    
    # Ensure used_context_ranks is a list of integers
    used_context_ranks = grounding_summary.get("used_context_ranks")
    if isinstance(used_context_ranks, list):
        # Validate all elements are integers
        normalized["used_context_ranks"] = [int(r) for r in used_context_ranks if isinstance(r, (int, float))]
    else:
        logger.warning(f"used_context_ranks is {type(used_context_ranks).__name__}, expected list. Using empty list.")
        normalized["used_context_ranks"] = []
    
    # Ensure light_semantic_inference_used is a boolean
    light_semantic = grounding_summary.get("light_semantic_inference_used")
    if isinstance(light_semantic, bool):
        normalized["light_semantic_inference_used"] = light_semantic
    else:
        logger.warning(f"light_semantic_inference_used is {type(light_semantic).__name__}, expected bool. Using False.")
        normalized["light_semantic_inference_used"] = False
    
    return normalized


def _extract_provider_http_status(*values: Any) -> Optional[int]:
    candidate_keys = ("provider_http_status", "provider_status", "status_code", "status", "http_status")

    def _search_status(value: Any) -> Optional[int]:
        if isinstance(value, dict):
            for key in candidate_keys:
                candidate = value.get(key)
                if isinstance(candidate, int) and candidate > 0:
                    return candidate
                if isinstance(candidate, str) and candidate.isdigit():
                    return int(candidate)
            for nested_value in value.values():
                extracted = _search_status(nested_value)
                if extracted is not None:
                    return extracted
        elif isinstance(value, (list, tuple, set)):
            for item in value:
                extracted = _search_status(item)
                if extracted is not None:
                    return extracted
        return None

    for value in values:
        extracted = _search_status(value)
        if extracted is not None:
            return extracted

    for value in values:
        if is_provider_failure_detail(value):
            return 400

    return None


@dataclass
class PreparedGroundedQARequest:
    request_id: str
    payload: Dict[str, Any]
    preflight_errors: List[str] = field(default_factory=list)
    preflight_warnings: List[str] = field(default_factory=list)
    normalized_ranks: List[int] = field(default_factory=list)
    summary: Dict[str, Any] = field(default_factory=dict)


def build_answer_policy(overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    policy, errors = _normalize_answer_policy(overrides)
    if errors:
        raise ValueError("; ".join(errors))
    return policy


def build_generation_options(overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    options, errors, _summary = _normalize_generation_options(overrides)
    if errors:
        raise ValueError("; ".join(errors))
    return options


def _coerce_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _build_request_context_chunk(
    index: int,
    chunk: Tuple[str, float, Dict[str, Any], float],
) -> Dict[str, Any]:
    text, distance, metadata, reranker_score = chunk
    return {
        "rank": index,
        "text": text,
        "metadata": metadata or {},
        "retrieval_score": max(0.0, 1.0 - min(1.0, _coerce_float(distance, 1.0))),
        "reranker_score": _coerce_float(reranker_score, 0.0),
    }


def build_request_context_chunks(
    reranked_chunks: Sequence[Tuple[str, float, Dict[str, Any], float]],
) -> List[Dict[str, Any]]:
    return [_build_request_context_chunk(index, chunk) for index, chunk in enumerate(reranked_chunks, start=1)]


def build_response_context_chunks(
    reranked_chunks: Sequence[Tuple[str, float, Dict[str, Any], float]],
) -> List[Dict[str, Any]]:
    response_chunks: List[Dict[str, Any]] = []
    for index, chunk in enumerate(reranked_chunks, start=1):
        text, distance, metadata, reranker_score = chunk
        response_chunks.append(
            {
                "rank": index,
                "text": text[:200] + "..." if len(text) > 200 else text,
                "distance": _coerce_float(distance, 0.0),
                "retrieval_score": max(0.0, 1.0 - min(1.0, _coerce_float(distance, 1.0))),
                "reranker_score": _coerce_float(reranker_score, 0.0),
                "cross_encoder_score": _coerce_float(reranker_score, 0.0),
                "metadata": metadata or {},
            }
        )
    return response_chunks


def _build_runtime(
    *,
    llm_invocation_attempted: bool,
    llm_http_status: Optional[int],
    llm_transport_success: bool,
    llm_response_json_valid: bool,
    llm_response_schema_valid: bool,
    answer_extraction_success: bool,
    generation_executed: bool,
    generation_failure_reason: Any,
    transport_error: Optional[str] = None,
) -> Dict[str, Any]:
    runtime = {
        "llm_invocation_attempted": llm_invocation_attempted,
        "llm_http_status": llm_http_status,
        "llm_transport_success": llm_transport_success,
        "llm_response_json_valid": llm_response_json_valid,
        "llm_response_schema_valid": llm_response_schema_valid,
        "answer_extraction_success": answer_extraction_success,
        "generation_executed": generation_executed,
        "generation_failure_reason": generation_failure_reason,
    }
    if transport_error:
        runtime["transport_error"] = transport_error
    return runtime


@dataclass
class GroundedQAResult:
    request_id: str
    query: str
    answer: str = ""
    context_chunks: List[Dict[str, Any]] = field(default_factory=list)
    intent_analysis: Dict[str, Any] = field(default_factory=dict)
    llm_api_used: bool = False
    llm_invocation_attempted: bool = False
    llm_http_status: Optional[int] = None
    gateway_http_status: Optional[int] = None
    provider_http_status: Optional[int] = None
    llm_transport_success: bool = False
    llm_response_json_valid: bool = False
    llm_response_schema_valid: bool = False
    answer_extraction_success: bool = False
    generation_executed: bool = False
    generation_failure_reason: Any = None
    failure_class: str = "runtime_failure"
    model_requested: str = DEFAULT_GROUNDED_MODEL
    model_used: Optional[str] = None
    abstained: bool = False
    abstention_reason: Optional[str] = None
    citations: List[Dict[str, Any]] = field(default_factory=list)
    success: bool = False
    result_status: str = "runtime_failure"
    grounding_summary: Dict[str, Any] = field(default_factory=dict)
    runtime: Dict[str, Any] = field(default_factory=dict)
    error: Any = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _build_failure_result(
    *,
    request_id: str,
    query: str,
    model_requested: str,
    context_chunks: List[Dict[str, Any]],
    intent_analysis: Dict[str, Any],
    llm_invocation_attempted: bool,
    llm_http_status: Optional[int],
    llm_transport_success: bool,
    llm_response_json_valid: bool,
    llm_response_schema_valid: bool,
    answer_extraction_success: bool,
    generation_failure_reason: Any,
    error: Any = None,
    transport_error: Optional[str] = None,
    runtime_overrides: Optional[Dict[str, Any]] = None,
    http_status: Optional[int] = None,
    response_body: Any = None,
) -> GroundedQAResult:
    structured_generation_failure_reason = coerce_error_detail(
        generation_failure_reason,
        default_code=_infer_failure_code(generation_failure_reason, response_body, fallback="runtime_failure"),
        detail_fallback=runtime_overrides or response_body,
    )
    structured_error = coerce_error_detail(
        error,
        default_code=_infer_failure_code(generation_failure_reason, response_body, error, fallback="runtime_failure"),
        detail_fallback=response_body or runtime_overrides,
    )
    gateway_http_status = llm_http_status if llm_http_status is not None else http_status
    provider_http_status = _extract_provider_http_status(response_body, runtime_overrides, structured_generation_failure_reason, structured_error)

    runtime = _build_runtime(
        llm_invocation_attempted=llm_invocation_attempted,
        llm_http_status=gateway_http_status,
        llm_transport_success=llm_transport_success,
        llm_response_json_valid=llm_response_json_valid,
        llm_response_schema_valid=llm_response_schema_valid,
        answer_extraction_success=answer_extraction_success,
        generation_executed=False,
        generation_failure_reason=structured_generation_failure_reason,
        transport_error=transport_error,
    )
    explicit_status = _infer_failure_code(structured_generation_failure_reason, fallback="runtime_failure")
    if explicit_status in {"response_contract_failure", "response_json_invalid", "request_build_failure", "request_validation_failure", "answer_extraction_failure"}:
        result_status = explicit_status
    else:
        classification_payload = {
            "success": False,
            "result_status": explicit_status,
            "runtime": runtime,
            "gateway_http_status": gateway_http_status,
            "provider_http_status": provider_http_status,
            "error": structured_error,
            "generation_failure_reason": structured_generation_failure_reason,
            "answer_extraction_success": answer_extraction_success,
        }
        result_status = classify_grounded_result_status(classification_payload)
    failure_class = classify_grounded_failure_class(
        {
            "success": False,
            "result_status": result_status,
            "runtime": runtime,
            "gateway_http_status": gateway_http_status,
            "provider_http_status": provider_http_status,
            "error": structured_error,
            "generation_failure_reason": structured_generation_failure_reason,
            "answer_extraction_success": answer_extraction_success,
        }
    )
    runtime.update(runtime_overrides or {})
    return GroundedQAResult(
        request_id=request_id,
        query=query,
        answer="",
        context_chunks=context_chunks,
        intent_analysis=intent_analysis,
        llm_api_used=llm_invocation_attempted,
        llm_invocation_attempted=llm_invocation_attempted,
        llm_http_status=gateway_http_status,
        gateway_http_status=gateway_http_status,
        provider_http_status=provider_http_status,
        llm_transport_success=llm_transport_success,
        llm_response_json_valid=llm_response_json_valid,
        llm_response_schema_valid=llm_response_schema_valid,
        answer_extraction_success=answer_extraction_success,
        generation_executed=False,
        generation_failure_reason=structured_generation_failure_reason,
        failure_class=failure_class,
        model_requested=model_requested,
        model_used=None,
        abstained=False,
        abstention_reason=None,
        citations=[],
        success=False,
        result_status=result_status,
        grounding_summary={},
        runtime=runtime,
        error=structured_error,
    )


def _normalize_successful_response(
    *,
    request_id: str,
    query: str,
    model_requested: str,
    context_chunks: List[Dict[str, Any]],
    intent_analysis: Dict[str, Any],
    response_data: Dict[str, Any],
    http_status: int,
) -> GroundedQAResult:
    missing = [key for key in REQUIRED_RESPONSE_KEYS if key not in response_data]
    if missing:
        return _build_failure_result(
            request_id=request_id,
            query=query,
            model_requested=model_requested,
            context_chunks=context_chunks,
            intent_analysis=intent_analysis,
            llm_invocation_attempted=True,
            llm_http_status=http_status,
            llm_transport_success=True,
            llm_response_json_valid=True,
            llm_response_schema_valid=False,
            answer_extraction_success=False,
            generation_failure_reason="response_contract_failure",
            error=f"Missing required response keys: {', '.join(sorted(missing))}",
        )

    runtime = response_data.get("runtime")
    if not isinstance(runtime, dict):
        return _build_failure_result(
            request_id=request_id,
            query=query,
            model_requested=model_requested,
            context_chunks=context_chunks,
            intent_analysis=intent_analysis,
            llm_invocation_attempted=True,
            llm_http_status=http_status,
            llm_transport_success=True,
            llm_response_json_valid=True,
            llm_response_schema_valid=False,
            answer_extraction_success=False,
            generation_failure_reason="response_contract_failure",
            error="Response runtime section is missing or invalid",
        )

    missing_runtime = [key for key in REQUIRED_RUNTIME_KEYS if key not in runtime]
    if missing_runtime:
        return _build_failure_result(
            request_id=request_id,
            query=query,
            model_requested=model_requested,
            context_chunks=context_chunks,
            intent_analysis=intent_analysis,
            llm_invocation_attempted=True,
            llm_http_status=http_status,
            llm_transport_success=True,
            llm_response_json_valid=True,
            llm_response_schema_valid=False,
            answer_extraction_success=False,
            generation_failure_reason="response_contract_failure",
            error=f"Missing required runtime keys: {', '.join(sorted(missing_runtime))}",
        )

    success = bool(response_data.get("success"))
    abstained = bool(response_data.get("abstained"))
    answer = response_data.get("answer") or ""
    citations = response_data.get("citations") or []
    grounding_summary = _normalize_grounding_summary(response_data.get("grounding_summary"))
    model_used = response_data.get("model_used") or model_requested
    abstention_reason = response_data.get("abstention_reason")
    raw_error = response_data.get("error")
    raw_generation_failure_reason = response_data.get("generation_failure_reason") or runtime.get("generation_failure_reason")
    gateway_http_status = http_status
    provider_http_status = _extract_provider_http_status(response_data, runtime, raw_error, raw_generation_failure_reason)

    if success and not answer.strip() and not abstained:
        result_status = "answer_extraction_failure"
        generation_failure_reason = coerce_error_detail(
            raw_generation_failure_reason or "empty_answer",
            default_code="answer_extraction_failure",
            default_message="empty_answer",
            detail_fallback=runtime,
        )
        error = coerce_error_detail(
            raw_error or generation_failure_reason,
            default_code="answer_extraction_failure",
            default_message="empty_answer",
            detail_fallback=runtime,
        )
        success = False
    elif success and abstained:
        result_status = "abstention"
        generation_failure_reason = coerce_error_detail(
            raw_generation_failure_reason,
            default_code="abstention",
            default_message="abstention",
            detail_fallback=runtime,
        )
        error = coerce_error_detail(
            raw_error,
            default_code="abstention",
            default_message="abstention",
            detail_fallback=runtime,
        )
    elif success:
        result_status = "success"
        generation_failure_reason = coerce_error_detail(
            raw_generation_failure_reason,
            default_code="success",
            detail_fallback=runtime,
        )
        error = coerce_error_detail(
            raw_error,
            default_code="success",
            detail_fallback=runtime,
        )
    else:
        generation_failure_reason = coerce_error_detail(
            raw_generation_failure_reason,
            default_code=_infer_failure_code(raw_error, runtime.get("generation_failure_reason"), fallback="runtime_failure"),
            detail_fallback=runtime,
        )
        error = coerce_error_detail(
            raw_error,
            default_code=_infer_failure_code(generation_failure_reason, fallback="runtime_failure"),
            detail_fallback=response_data,
        )
        result_status = classify_grounded_result_status(
            {
                "success": False,
                "result_status": response_data.get("result_status"),
                "runtime": runtime,
                "gateway_http_status": gateway_http_status,
                "provider_http_status": provider_http_status,
                "error": error,
                "generation_failure_reason": generation_failure_reason,
                "answer_extraction_success": runtime.get("answer_extraction_success"),
            }
        )

    normalized_runtime = _build_runtime(
        llm_invocation_attempted=bool(runtime.get("llm_invocation_attempted", True)),
        llm_http_status=http_status,
        llm_transport_success=bool(runtime.get("llm_transport_success", True)),
        llm_response_json_valid=bool(runtime.get("llm_response_json_valid", True)),
        llm_response_schema_valid=bool(runtime.get("llm_response_schema_valid", True)),
        answer_extraction_success=bool(runtime.get("answer_extraction_success", success or abstained)),
        generation_executed=bool(runtime.get("generation_executed", success or abstained)),
        generation_failure_reason=generation_failure_reason,
    )

    return GroundedQAResult(
        request_id=response_data.get("request_id") or request_id,
        query=response_data.get("query") or query,
        answer=answer,
        context_chunks=context_chunks,
        intent_analysis=intent_analysis,
        llm_api_used=True,
        llm_invocation_attempted=True,
        llm_http_status=http_status,
        llm_transport_success=True,
        llm_response_json_valid=True,
        llm_response_schema_valid=True,
        answer_extraction_success=bool(normalized_runtime["answer_extraction_success"]),
        generation_executed=bool(normalized_runtime["generation_executed"] and success),
        generation_failure_reason=generation_failure_reason,
        failure_class=classify_grounded_failure_class(
            {
                "success": success,
                "result_status": result_status,
                "runtime": normalized_runtime,
                "gateway_http_status": gateway_http_status,
                "provider_http_status": provider_http_status,
                "error": error,
                "generation_failure_reason": generation_failure_reason,
                "answer_extraction_success": normalized_runtime.get("answer_extraction_success"),
            }
        ),
        model_requested=model_requested,
        model_used=model_used,
        abstained=abstained,
        abstention_reason=abstention_reason,
        citations=[citation for citation in citations if isinstance(citation, dict)],
        success=success,
        result_status=result_status,
        grounding_summary=grounding_summary,
        runtime=normalized_runtime,
        error=error,
        gateway_http_status=gateway_http_status,
        provider_http_status=provider_http_status,
    )


class GroundedQAClient:
    """Structured client for the grounded QA API endpoint."""

    def __init__(
        self,
        base_url: str = COPILOT_API_BASE_URL,
        endpoint: str = GROUNDED_QA_ENDPOINT,
        timeout_seconds: float = COPILOT_API_TIMEOUT_SECONDS,
        retry_count: int = COPILOT_API_RETRY_COUNT,
        retry_backoff_seconds: float = COPILOT_API_RETRY_BACKOFF_SECONDS,
        logger_instance: Optional[logging.Logger] = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.endpoint = endpoint if endpoint.startswith("/") else f"/{endpoint}"
        self.timeout_seconds = timeout_seconds
        self.retry_count = retry_count
        self.retry_backoff_seconds = retry_backoff_seconds
        self.logger = logger_instance or logger

    def build_request_payload(
        self,
        query: str,
        context_chunks: Sequence[Dict[str, Any]],
        request_id: Optional[str] = None,
        model: Optional[str] = None,
        answer_policy: Optional[Dict[str, Any]] = None,
        generation_options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        prepared = self.prepare_request_payload(
            query=query,
            context_chunks=context_chunks,
            request_id=request_id,
            model=model,
            answer_policy=answer_policy,
            generation_options=generation_options,
        )
        return prepared.payload

    def prepare_request_payload(
        self,
        query: str,
        context_chunks: Sequence[Dict[str, Any]],
        request_id: Optional[str] = None,
        model: Optional[str] = None,
        answer_policy: Optional[Dict[str, Any]] = None,
        generation_options: Optional[Dict[str, Any]] = None,
    ) -> PreparedGroundedQARequest:
        resolved_request_id = request_id.strip() if isinstance(request_id, str) and request_id.strip() else generate_request_id()
        normalized_query, query_errors = _normalize_query(query)
        normalized_context_chunks, chunk_errors, normalized_ranks = _normalize_context_chunks_for_request(context_chunks)
        normalized_answer_policy, answer_policy_errors = _normalize_answer_policy(answer_policy)
        normalized_generation_options, generation_option_errors, generation_summary = _normalize_generation_options(
            generation_options
        )

        payload = {
            "request_id": resolved_request_id,
            "model": (model.strip() if isinstance(model, str) and model.strip() else DEFAULT_GROUNDED_MODEL),
            "query": normalized_query or "",
            "context_chunks": normalized_context_chunks,
            "answer_policy": normalized_answer_policy,
            "generation_options": normalized_generation_options,
        }

        preflight_errors = []
        preflight_errors.extend(query_errors)
        preflight_errors.extend(chunk_errors)
        preflight_errors.extend(answer_policy_errors)
        preflight_errors.extend(generation_option_errors)
        preflight_errors.extend(_validate_preflight_payload(payload))

        summary = {
            "request_id": resolved_request_id,
            "model": payload["model"],
            "query_length": len(payload["query"]),
            "context_chunks_count": len(payload["context_chunks"]),
            "ranks": normalized_ranks,
            "max_tokens_present": "max_tokens" in payload["generation_options"],
            "max_tokens_valid": generation_summary.get("max_tokens_valid", False),
        }

        return PreparedGroundedQARequest(
            request_id=resolved_request_id,
            payload=payload,
            preflight_errors=preflight_errors,
            preflight_warnings=[],
            normalized_ranks=normalized_ranks,
            summary=summary,
        )

    def answer(
        self,
        query: str,
        context_chunks: Sequence[Dict[str, Any]],
        request_id: Optional[str] = None,
        model: Optional[str] = None,
        answer_policy: Optional[Dict[str, Any]] = None,
        generation_options: Optional[Dict[str, Any]] = None,
        intent_analysis: Optional[Dict[str, Any]] = None,
    ) -> GroundedQAResult:
        payload = self.build_request_payload(
            query=query,
            context_chunks=context_chunks,
            request_id=request_id,
            model=model,
            answer_policy=answer_policy,
            generation_options=generation_options,
        )

        intent_analysis = copy.deepcopy(intent_analysis or {})

        prepared = self.prepare_request_payload(
            query=query,
            context_chunks=context_chunks,
            request_id=payload["request_id"],
            model=payload["model"],
            answer_policy=answer_policy,
            generation_options=generation_options,
        )

        if prepared.preflight_errors:
            self.logger.warning(
                "Grounded QA request %s preflight failed: model=%s chunks=%d ranks=%s errors=%s",
                prepared.request_id,
                prepared.payload["model"],
                len(prepared.payload["context_chunks"]),
                prepared.normalized_ranks,
                prepared.preflight_errors,
            )
            return _build_failure_result(
                request_id=prepared.request_id,
                query=prepared.payload["query"],
                model_requested=prepared.payload["model"],
                context_chunks=prepared.payload["context_chunks"],
                intent_analysis=intent_analysis,
                llm_invocation_attempted=False,
                llm_http_status=None,
                llm_transport_success=False,
                llm_response_json_valid=False,
                llm_response_schema_valid=False,
                answer_extraction_success=False,
                generation_failure_reason="request_build_failure",
                error="; ".join(prepared.preflight_errors),
                runtime_overrides={"preflight_errors": prepared.preflight_errors},
                response_body={"preflight_errors": prepared.preflight_errors},
            )

        url = f"{self.base_url}{self.endpoint}"
        headers = {
            "accept": "application/json",
            "content-type": "application/json",
            "user-agent": COPILOT_API_USER_AGENT,
        }

        self.logger.info(
            "Grounded QA outbound payload request_id=%s endpoint=%s model=%s query_length=%d context_chunks=%d ranks=%s max_tokens_present=%s max_tokens_valid=%s preflight_passed=%s",
            prepared.request_id,
            url,
            prepared.payload["model"],
            len(prepared.payload["query"]),
            len(prepared.payload["context_chunks"]),
            prepared.normalized_ranks,
            prepared.summary.get("max_tokens_present"),
            prepared.summary.get("max_tokens_valid"),
            not prepared.preflight_errors,
        )

        last_error: Optional[str] = None
        response = None
        last_response_body: Optional[Dict[str, Any]] = None
        for attempt in range(self.retry_count + 1):
            try:
                response = requests.post(
                    url,
                    json=prepared.payload,
                    headers=headers,
                    timeout=self.timeout_seconds,
                )
                break
            except requests.exceptions.RequestException as exc:  # pragma: no cover - transport handling
                last_error = str(exc)
                if attempt < self.retry_count:
                    time.sleep(self.retry_backoff_seconds)
                else:
                    break

        if response is None:
            return _build_failure_result(
                request_id=prepared.request_id,
                query=query,
                model_requested=prepared.payload["model"],
                context_chunks=list(prepared.payload["context_chunks"]),
                intent_analysis=intent_analysis,
                llm_invocation_attempted=True,
                llm_http_status=None,
                llm_transport_success=False,
                llm_response_json_valid=False,
                llm_response_schema_valid=False,
                answer_extraction_success=False,
                generation_failure_reason="transport_failure",
                error=last_error or "Transport failure while calling grounded QA API",
                transport_error=last_error,
                response_body={"transport_error": last_error} if last_error else None,
            )

        http_status = response.status_code
        try:
            response_body = response.json()
            json_valid = True
        except ValueError:
            response_body = None
            json_valid = False

        last_response_body = response_body if isinstance(response_body, dict) else None

        if http_status == 422:
            validation_details = _extract_validation_errors(response_body, response.text)
            repair_summary = self._repair_from_validation_details(prepared.payload, validation_details)
            if repair_summary.get("repaired") and repair_summary.get("payload") is not None:
                self.logger.warning(
                    "Grounded QA request %s repaired after 422: details=%s",
                    prepared.request_id,
                    validation_details,
                )
                repaired_payload = repair_summary["payload"]
                try:
                    repaired_response = requests.post(
                        url,
                        json=repaired_payload,
                        headers=headers,
                        timeout=self.timeout_seconds,
                    )
                    response = repaired_response
                    http_status = response.status_code
                    try:
                        response_body = response.json()
                        json_valid = True
                    except ValueError:
                        response_body = None
                        json_valid = False
                except requests.exceptions.RequestException as exc:
                    last_error = str(exc)

            if http_status == 422:
                return _build_failure_result(
                    request_id=prepared.request_id,
                    query=query,
                    model_requested=prepared.payload["model"],
                    context_chunks=list(prepared.payload["context_chunks"]),
                    intent_analysis=intent_analysis,
                    llm_invocation_attempted=True,
                    llm_http_status=http_status,
                    llm_transport_success=True,
                    llm_response_json_valid=json_valid,
                    llm_response_schema_valid=False,
                    answer_extraction_success=False,
                    generation_failure_reason="request_validation_failure",
                    error=validation_details,
                    runtime_overrides={"request_validation_details": validation_details},
                    http_status=http_status,
                    response_body=response_body,
                )

        if http_status != 200:
            generation_failure_reason = f"http_{http_status}"
            if http_status == 422:
                generation_failure_reason = "request_validation_failure"
            elif 400 <= http_status < 500:
                generation_failure_reason = "runtime_failure"
                if isinstance(response_body, dict):
                    provider_error = response_body.get("error")
                    provider_failure_reason = response_body.get("generation_failure_reason")
                    if is_provider_failure_detail(provider_error) or is_provider_failure_detail(provider_failure_reason):
                        generation_failure_reason = provider_error or provider_failure_reason or "provider_failure"
            return _build_failure_result(
                request_id=prepared.request_id,
                query=query,
                model_requested=prepared.payload["model"],
                context_chunks=list(prepared.payload["context_chunks"]),
                intent_analysis=intent_analysis,
                llm_invocation_attempted=True,
                llm_http_status=http_status,
                llm_transport_success=True,
                llm_response_json_valid=json_valid,
                llm_response_schema_valid=False,
                answer_extraction_success=False,
                generation_failure_reason=generation_failure_reason,
                error=(response_body.get("error") if isinstance(response_body, dict) else None) or response.text,
                runtime_overrides={"response_body": last_response_body},
                http_status=http_status,
                response_body=response_body,
            )

        if not json_valid or not isinstance(response_body, dict):
            return _build_failure_result(
                request_id=prepared.request_id,
                query=query,
                model_requested=prepared.payload["model"],
                context_chunks=list(prepared.payload["context_chunks"]),
                intent_analysis=intent_analysis,
                llm_invocation_attempted=True,
                llm_http_status=http_status,
                llm_transport_success=True,
                llm_response_json_valid=False,
                llm_response_schema_valid=False,
                answer_extraction_success=False,
                generation_failure_reason="response_json_invalid",
                error=response.text,
                http_status=http_status,
                response_body={"response_text": response.text},
            )

        normalized = _normalize_successful_response(
            request_id=prepared.request_id,
            query=query,
            model_requested=prepared.payload["model"],
            context_chunks=list(prepared.payload["context_chunks"]),
            intent_analysis=intent_analysis,
            response_data=response_body,
            http_status=http_status,
        )

        if normalized.result_status == "answer_extraction_failure" and not normalized.error:
            normalized.error = {
                "code": "answer_extraction_failure",
                "message": "empty_answer",
                "detail": None,
            }

        return normalized

    def _repair_from_validation_details(self, payload: Dict[str, Any], details: str) -> Dict[str, Any]:
        repaired_payload = copy.deepcopy(payload)
        repaired = False

        if "context_chunks" in details and "rank" in details:
            repaired_payload["context_chunks"] = [
                {**chunk, "rank": index}
                for index, chunk in enumerate(repaired_payload.get("context_chunks", []), start=1)
            ]
            repaired = True

        if "generation_options.max_tokens" in details:
            repaired_payload.setdefault("generation_options", {}).pop("max_tokens", None)
            repaired = True

        return {"repaired": repaired, "payload": repaired_payload}


def _score_retrieval(
    retrieved_chunks: Sequence[Tuple[str, float, Dict[str, Any], float]],
) -> Dict[str, Any]:
    lexical_tokens = set()
    evidence_tokens = set()
    semantic_scores: List[float] = []
    reranker_scores: List[float] = []
    for chunk in retrieved_chunks:
        text, distance, _metadata, reranker_score = chunk
        semantic_scores.append(max(0.0, 1.0 - min(1.0, _coerce_float(distance, 1.0))))
        reranker_scores.append(_coerce_float(reranker_score, 0.0))
        evidence_tokens.update(text.lower().split())
    return {
        "semantic_scores": semantic_scores,
        "reranker_scores": reranker_scores,
        "evidence_tokens": evidence_tokens,
        "lexical_tokens": lexical_tokens,
        "semantic_relevance_score": sum(semantic_scores) / len(semantic_scores) if semantic_scores else 0.0,
        "reranker_score": max(reranker_scores) if reranker_scores else 0.0,
        "top_k_consistency": semantic_scores[:3],
    }


def _reconcile_retrieval_quality_with_generation(
    *,
    pre_generation_retrieval_quality: Dict[str, Any],
    qa_result: "GroundedQAResult",
    logger_instance: Optional[logging.Logger] = None,
) -> Dict[str, Any]:
    """Reconcile pre-generation retrieval quality assessment with actual generation outcome.
    
    Purpose:
    - Align retrieval_relevant, retrieval_answerable, retrieval_sufficient with reality
    - Detect cases where strong generation succeeded despite low pre-gen scores (promote flags)
    - Detect cases where generation failed despite high pre-gen scores (demote flags)
    - Prevent contradictory states like: success=true but retrieval_sufficient=false
    
    Args:
        pre_generation_retrieval_quality: Initial quality gates output
        qa_result: Final QA generation result with success/citations/grounding_summary
        logger_instance: Optional logger
    
    Returns:
        Updated retrieval quality dict with reconciled flags and explanation fields
    """
    log = logger_instance or logger
    
    # Extract pre-generation scores
    pre_gen = pre_generation_retrieval_quality.copy()
    pre_relevant = pre_gen.get("retrieval_relevant", False)
    pre_answerable = pre_gen.get("retrieval_answerable", False)
    pre_sufficient = pre_gen.get("retrieval_sufficient", False)
    
    # Extract generation outcome signals
    success = qa_result.success
    generation_executed = qa_result.generation_executed
    answer_extraction_success = qa_result.answer_extraction_success
    abstained = qa_result.abstained
    citations = qa_result.citations or []
    grounding_summary = qa_result.grounding_summary or {}
    answer = qa_result.answer or ""
    
    # ============================================================
    # Analyze generation outcome quality
    # ============================================================
    
    # Signal 1: Generation success
    strong_success = success and generation_executed and answer_extraction_success
    
    # Signal 2: Answer quality
    answer_is_substantive = bool(answer.strip()) and len(answer.strip()) > 20
    
    # Signal 3: Citations/grounding quality
    used_ranks = grounding_summary.get("used_context_ranks", [])
    has_strong_top_citations = any(rank in [1, 2, 3] for rank in used_ranks)
    has_primary_citation = 1 in used_ranks
    
    # Signal 4: Inference type
    used_inference = grounding_summary.get("light_semantic_inference_used", False)
    direct_answer = not used_inference  # Direct quote without synthesis
    
    # Signal 5: Abstention pattern
    properly_abstained = abstained and not answer_is_substantive
    
    # ============================================================
    # Reconciliation Rule 1: retrieval_relevant
    # ============================================================
    reconciled_relevant = pre_relevant
    relevant_change_reason = None
    
    # Promote to true if generation used strong primary citation despite low pre-gen score
    if not pre_relevant and strong_success and has_primary_citation and answer_is_substantive:
        reconciled_relevant = True
        relevant_change_reason = "Generation succeeded using primary chunk despite low pre-gen relevance score"
        log.info(
            "[RECONCILE] Promoted retrieval_relevant to true: generation succeeded with primary citation, "
            "pre-gen=%s", pre_relevant
        )
    
    # Demote to false if generation failed despite high pre-gen score (only in extreme cases)
    elif pre_relevant and not success and not properly_abstained:
        # But check: maybe it's just an abstention, which is valid
        if not abstained:
            reconciled_relevant = False
            relevant_change_reason = "Generation failed despite high pre-gen relevance score"
            log.warning(
                "[RECONCILE] Demoted retrieval_relevant to false: generation failed without proper abstention"
            )
    
    # ============================================================
    # Reconciliation Rule 2: retrieval_answerable
    # ============================================================
    reconciled_answerable = pre_answerable
    answerable_change_reason = None
    
    # Promote to true if generation extracted a substantive answer with grounding
    if not pre_answerable and strong_success and answer_is_substantive and (has_strong_top_citations or direct_answer):
        reconciled_answerable = True
        answerable_change_reason = "Generation produced substantive grounded answer despite low pre-gen answerability"
        log.info(
            "[RECONCILE] Promoted retrieval_answerable to true: substantive answer generated with grounding"
        )
    
    # Demote if generation couldn't extract answer despite high pre-gen answerability
    elif pre_answerable and not answer_is_substantive and not properly_abstained:
        if not abstained:
            reconciled_answerable = False
            answerable_change_reason = "Could not extract substantive answer despite high pre-gen answerability"
            log.warning(
                "[RECONCILE] Demoted retrieval_answerable to false: no substantive answer extracted"
            )
    
    # ============================================================
    # Reconciliation Rule 3: retrieval_sufficient
    # ============================================================
    reconciled_sufficient = pre_sufficient
    sufficient_change_reason = None
    
    # PROMOTE: Strong generation success with evidence from top chunks
    # This is the KEY FIX: successful grounded generation is strong signal of sufficiency
    if not pre_sufficient and strong_success and answer_is_substantive:
        # Additional checks to avoid false promotion
        has_top_evidence = has_strong_top_citations or (len(used_ranks) > 0 and 1 in used_ranks)
        reasonable_inference = not (used_inference and len(used_ranks) < 1)  # Avoid pure synthesis
        
        if has_top_evidence or direct_answer:
            reconciled_sufficient = True
            sufficient_change_reason = (
                f"Generation succeeded with grounded evidence: used_ranks={used_ranks}, "
                f"inference={used_inference}, direct_answer={direct_answer}"
            )
            log.info(
                "[RECONCILE] Promoted retrieval_sufficient to true: successful grounded generation "
                "with strong evidence from top chunks"
            )
    
    # DEMOTE: Generation failed or hallucinated despite high pre-gen score
    elif pre_sufficient and not success:
        # Only demote if it's not a proper abstention
        if not properly_abstained:
            reconciled_sufficient = False
            sufficient_change_reason = "Generation failed despite high pre-gen sufficiency score"
            log.warning(
                "[RECONCILE] Demoted retrieval_sufficient to false: generation failed without proper abstention"
            )
    
    # Special case: Proper abstention should keep sufficiency as initially assessed
    # (it just means "this question can't be answered", not "retrieval was insufficient")
    
    # ============================================================
    # Detect contradictions and flag them
    # ============================================================
    contradictions = []
    
    # Contradiction 1: success=true but retrieval_sufficient=false (with nuance for abstention)
    if success and not reconciled_sufficient:
        # This is expected/acceptable for proper abstention
        if properly_abstained:
            # Not a real contradiction, just proper abstention
            pass
        else:
            # This IS a contradiction: success without proper abstention but insufficient retrieval
            contradictions.append(
                "success=true but retrieval_sufficient=false (this should not happen for non-abstained answers)"
            )
            # Force sufficiency to true if this is a real success (not abstention)
            if answer_is_substantive and not abstained:
                reconciled_sufficient = True
                sufficient_change_reason = "Forced to true due to success contradiction"
                log.warning(
                    "[RECONCILE] Forced retrieval_sufficient=true due to success contradiction: "
                    "success=true but sufficiency was false (non-abstained)"
                )
    
    # Contradiction 2: answer present but retrieval_relevant=false
    if answer_is_substantive and not reconciled_relevant:
        contradictions.append(
            "Substantive answer generated but retrieval_relevant=false"
        )
        if not abstained:
            reconciled_relevant = True
            relevant_change_reason = "Forced to true due to answer contradiction"
    
    if contradictions:
        log.warning("[RECONCILE] Detected contradictions: %s", contradictions)
    
    # ============================================================
    # Build reconciled output
    # ============================================================
    reconciled_quality = {
        "retrieval_relevant": reconciled_relevant,
        "retrieval_answerable": reconciled_answerable,
        "retrieval_sufficient": reconciled_sufficient,
        
        # Pre-generation scores for comparison
        "pre_generation_retrieval_relevant": pre_relevant,
        "pre_generation_retrieval_answerable": pre_answerable,
        "pre_generation_retrieval_sufficient": pre_sufficient,
        
        # Change explanations
        "retrieval_relevant_change_reason": relevant_change_reason,
        "retrieval_answerable_change_reason": answerable_change_reason,
        "retrieval_sufficiency_change_reason": sufficient_change_reason,
        
        # Generation outcome signals
        "generation_success": success,
        "generation_executed": generation_executed,
        "answer_extraction_success": answer_extraction_success,
        "answer_is_substantive": answer_is_substantive,
        "used_context_ranks": used_ranks,
        "has_primary_citation": has_primary_citation,
        "used_inference": used_inference,
        "direct_answer": direct_answer,
        "properly_abstained": properly_abstained,
        
        # Diagnostics
        "contradictions_detected": len(contradictions) > 0,
        "contradiction_details": contradictions,
        
        # Retain pre-gen explanation fields
        "retrieval_relevance_reasons": pre_gen.get("retrieval_relevance_reasons", []),
        "retrieval_answerability_reasons": pre_gen.get("retrieval_answerability_reasons", []),
        "retrieval_sufficiency_reasons": pre_gen.get("retrieval_sufficiency_reasons", []),
    }
    
    return reconciled_quality


def run_grounded_query(
    *,
    query: str,
    top_k: int,
    rerank_top_k: int,
    intent_analyzer: Any,
    embedder: Any,
    retriever: Any,
    reranker: Any,
    qa_client: GroundedQAClient,
    quality_gates: Any,
    request_id: Optional[str] = None,
    model: Optional[str] = None,
    answer_policy: Optional[Dict[str, Any]] = None,
    generation_options: Optional[Dict[str, Any]] = None,
    logger_instance: Optional[logging.Logger] = None,
) -> GroundedQAResult:
    log = logger_instance or logger
    request_id = request_id or generate_request_id()
    model = model or DEFAULT_GROUNDED_MODEL

    log.info("Grounded QA request %s started via %s", request_id, f"{qa_client.base_url}{qa_client.endpoint}")

    intent_analysis = intent_analyzer.analyze_query(query)

    query_embedding = embedder.embed_texts([query])[0]
    retrieved = retriever.retrieve(query, query_embedding=query_embedding, top_k=top_k)

    if retrieved:
        reranked = reranker.rerank(query, retrieved, top_k=rerank_top_k)
    else:
        reranked = []

    request_context_chunks = build_request_context_chunks(reranked)
    response_context_chunks = build_response_context_chunks(reranked)

    retrieval_metrics = _score_retrieval(reranked)
    lexical_tokens = set(query.lower().split())
    evidence_tokens = retrieval_metrics["evidence_tokens"]
    lexical_overlap_score = len({token for token in lexical_tokens if token in evidence_tokens}) / max(1, len(lexical_tokens))

    kb_gate = quality_gates.kb_relevance_gate(
        query=query,
        lexical_overlap_score=lexical_overlap_score,
        semantic_similarity_score=retrieval_metrics["semantic_relevance_score"],
        reranker_score=retrieval_metrics["reranker_score"],
        domain_match=None,
        top_k_consistency=retrieval_metrics["top_k_consistency"],
    )

    retrieval_gate = quality_gates.retrieval_sufficiency_gate(
        top_chunks=response_context_chunks,
        query=query,
        semantic_scores=retrieval_metrics["semantic_scores"],
        cross_encoder_scores=retrieval_metrics["reranker_scores"],
    )

    intent_analysis.update(
        {
            "kb_overlap": sorted(list({token for token in lexical_tokens if token in evidence_tokens}))[:10],
            "overlap_ratio": lexical_overlap_score,
            "relevance_score": kb_gate.score,
            "hybrid_kb_relevance_score": kb_gate.score,
            "is_kb_relevant": kb_gate.pass_flag,
            "evidence_semantic_similarity": retrieval_metrics["semantic_relevance_score"],
            "evidence_reranker_score": retrieval_metrics["reranker_score"],
            "evidence_kb_relevance_reasons": kb_gate.reasons,
            "retrieval_relevant": retrieval_gate.details.get("retrieval_relevant", False),
            "retrieval_answerable": retrieval_gate.details.get("retrieval_answerable", False),
            "retrieval_sufficient": retrieval_gate.details.get("retrieval_sufficient", False),
        }
    )

    log.info(
        "Grounded QA request %s context summary: endpoint=%s, model=%s, context_chunks=%d, ranks=%s",
        request_id,
        f"{qa_client.base_url}{qa_client.endpoint}",
        model,
        len(request_context_chunks),
        [chunk.get("rank") for chunk in request_context_chunks[:5]],
    )

    qa_result = qa_client.answer(
        query=query,
        context_chunks=request_context_chunks,
        request_id=request_id,
        model=model,
        answer_policy=answer_policy,
        generation_options=generation_options,
        intent_analysis=intent_analysis,
    )

    qa_result.context_chunks = response_context_chunks
    qa_result.intent_analysis = intent_analysis
    qa_result.model_requested = model
    qa_result.llm_api_used = qa_result.llm_invocation_attempted

    # ============================================================
    # POST-GENERATION RECONCILIATION
    # Align retrieval quality with actual generation outcome
    # ============================================================
    pre_gen_retrieval_quality = {
        "retrieval_relevant": intent_analysis.get("retrieval_relevant", False),
        "retrieval_answerable": intent_analysis.get("retrieval_answerable", False),
        "retrieval_sufficient": intent_analysis.get("retrieval_sufficient", False),
        "retrieval_relevance_reasons": retrieval_gate.details.get("retrieval_relevance_reasons", []),
        "retrieval_answerability_reasons": retrieval_gate.details.get("retrieval_answerability_reasons", []),
        "retrieval_sufficiency_reasons": retrieval_gate.details.get("retrieval_sufficiency_reasons", []),
        "top1_semantic": retrieval_gate.details.get("top1_semantic", 0.0),
        "top1_reranker": retrieval_gate.details.get("top1_reranker", 0.0),
        "avg_semantic": retrieval_gate.details.get("avg_semantic", 0.0),
        "avg_reranker": retrieval_gate.details.get("avg_reranker", 0.0),
    }
    
    reconciled_retrieval_quality = _reconcile_retrieval_quality_with_generation(
        pre_generation_retrieval_quality=pre_gen_retrieval_quality,
        qa_result=qa_result,
        logger_instance=log,
    )
    
    # Update intent_analysis with reconciled quality
    intent_analysis.update(reconciled_retrieval_quality)

    log.info(
        "Grounded QA request %s completed: status=%s, success=%s, abstained=%s, model=%s, chunks=%d, failure_reason=%s",
        request_id,
        qa_result.result_status,
        qa_result.success,
        qa_result.abstained,
        qa_result.model_used or qa_result.model_requested,
        len(request_context_chunks),
        qa_result.generation_failure_reason,
    )
    log.info("Grounded QA request %s runtime diagnostics: %s", request_id, qa_result.runtime)

    return qa_result