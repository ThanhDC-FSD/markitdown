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
