#!/usr/bin/env python3
"""Grounded QA diagnostic harness for correlated RAG and Copilot evidence.

This script is intentionally standalone. It does not change server runtime behavior;
it only sends diagnostic requests, captures responses, and correlates logs.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import subprocess
import sys
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import requests


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_ROOT = ROOT / "diagnostics" / "grounded_qa"
DEFAULT_CASES_FILE = Path(__file__).with_name("grounded_qa_cases.json")
DEFAULT_RAG_BASE_URL = "http://127.0.0.1:8001"
DEFAULT_COPILOT_BASE_URL = "http://localhost:8080"
DEFAULT_RAG_LOG_GLOB = str(ROOT / "logs" / "api_*.log")

REQUEST_ID_HEADER = "x-request-id"
CORRELATION_HEADER = "x-correlation-id"
DIAGNOSTIC_HEADER = "x-diagnostic-request-id"


@dataclass
class DiagnosticCase:
    name: str
    query: str
    mode: str = "both"
    top_k: int = 5
    rerank_top_k: int = 3
    model: Optional[str] = None
    request_id: Optional[str] = None
    expected_failure_class: Optional[str] = None
    notes: Optional[str] = None
    answer_policy: Optional[Dict[str, Any]] = None
    generation_options: Optional[Dict[str, Any]] = None
    context_chunks: Optional[List[Dict[str, Any]]] = None


@dataclass
class RequestSnapshot:
    timestamp: str
    request_id: str
    url: str
    headers: Dict[str, Any]
    body: Any


@dataclass
class ResponseSnapshot:
    timestamp: str
    status_code: Optional[int]
    headers: Dict[str, Any]
    raw_text: str
    parsed_json: Optional[Any] = None
    json_parse_error: Optional[str] = None
    error: Optional[str] = None


@dataclass
class HttpCallArtifact:
    label: str
    request: RequestSnapshot
    response: ResponseSnapshot


@dataclass
class LogExcerpt:
    source: str
    request_id: str
    files_scanned: List[str] = field(default_factory=list)
    matches_found: int = 0
    excerpt: str = ""
    unavailable_reason: Optional[str] = None


@dataclass
class DiagnosticBundle:
    request_id: str
    case: DiagnosticCase
    generated_at: str
    output_dir: str
    request_payload: Dict[str, Any]
    rag_call: Optional[HttpCallArtifact] = None
    copilot_call: Optional[HttpCallArtifact] = None
    rag_log_excerpt: LogExcerpt = field(default_factory=lambda: LogExcerpt(source="rag", request_id=""))
    copilot_log_excerpt: LogExcerpt = field(default_factory=lambda: LogExcerpt(source="copilot", request_id=""))
    merged_timeline: List[Dict[str, Any]] = field(default_factory=list)
    classifications: List[str] = field(default_factory=list)
    dominant_failure_cause: str = "runtime_failure"
    next_fix_target: str = "investigate runtime failure"
    stage_failure_details: Dict[str, Any] = field(default_factory=dict)
    diagnosis_summary: str = ""
    notes: List[str] = field(default_factory=list)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def generate_request_id(case_name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", case_name.lower()).strip("_") or "diag"
    short_id = uuid.uuid4().hex[:8]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    return f"diag_{slug}_{stamp}_{short_id}"


def json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [json_safe(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def load_cases(cases_file: Path) -> List[DiagnosticCase]:
    if not cases_file.exists():
        return [
            DiagnosticCase(
                name="current_grounding_summary_schema_mismatch",
                query="Why are internet based clients important in the Cloud Age?",
                mode="both",
                top_k=5,
                rerank_top_k=3,
                model="gpt-5-mini",
                expected_failure_class="response_schema_mismatch",
                notes="Current failing case reported by the user; Copilot logs groundingsummary schema mismatch.",
            )
        ]

    raw = json.loads(cases_file.read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        raw_cases = raw.get("cases", [])
    else:
        raw_cases = raw

    cases: List[DiagnosticCase] = []
    for index, item in enumerate(raw_cases, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"Case {index} must be an object")
        cases.append(
            DiagnosticCase(
                name=str(item.get("name") or f"case_{index}"),
                query=str(item["query"]),
                mode=str(item.get("mode") or "both"),
                top_k=int(item.get("top_k", 5)),
                rerank_top_k=int(item.get("rerank_top_k", 3)),
                model=item.get("model"),
                request_id=item.get("request_id"),
                expected_failure_class=item.get("expected_failure_class"),
                notes=item.get("notes"),
                answer_policy=item.get("answer_policy"),
                generation_options=item.get("generation_options"),
                context_chunks=item.get("context_chunks"),
            )
        )
    return cases


def load_json_file(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def ensure_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def build_rag_request_payload(case: DiagnosticCase, request_id: str) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "query": case.query,
        "top_k": case.top_k,
        "rerank_top_k": case.rerank_top_k,
        "request_id": request_id,
    }
    if case.model:
        payload["model"] = case.model
    if case.answer_policy is not None:
        payload["answer_policy"] = case.answer_policy
    if case.generation_options is not None:
        payload["generation_options"] = case.generation_options
    return payload


def normalize_context_chunk_for_copilot(chunk: Dict[str, Any], rank: int) -> Dict[str, Any]:
    text = chunk.get("text")
    metadata = chunk.get("metadata") if isinstance(chunk.get("metadata"), dict) else {}
    retrieval_score = chunk.get("retrieval_score")
    if retrieval_score is None and isinstance(chunk.get("distance"), (int, float)):
        retrieval_score = max(0.0, 1.0 - min(1.0, float(chunk["distance"])))
    reranker_score = chunk.get("reranker_score")
    if reranker_score is None and isinstance(chunk.get("cross_encoder_score"), (int, float)):
        reranker_score = float(chunk["cross_encoder_score"])
    return {
        "rank": int(chunk.get("rank") or rank),
        "text": str(text or ""),
        "metadata": metadata,
        "retrieval_score": float(retrieval_score or 0.0),
        "reranker_score": float(reranker_score or 0.0),
    }


def build_copilot_request_payload(case: DiagnosticCase, request_id: str, context_chunks: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "request_id": request_id,
        "query": case.query,
        "context_chunks": [normalize_context_chunk_for_copilot(chunk, index) for index, chunk in enumerate(context_chunks, start=1)],
    }
    if case.model:
        payload["model"] = case.model
    if case.answer_policy is not None:
        payload["answer_policy"] = case.answer_policy
    if case.generation_options is not None:
        payload["generation_options"] = case.generation_options
    return payload


def build_headers(request_id: str) -> Dict[str, str]:
    return {
        "accept": "application/json",
        "content-type": "application/json",
        REQUEST_ID_HEADER: request_id,
        CORRELATION_HEADER: request_id,
        DIAGNOSTIC_HEADER: request_id,
    }


def is_local_endpoint(url: str) -> bool:
    lower = url.lower()
    return (
        lower.startswith("http://127.0.0.1")
        or lower.startswith("http://localhost")
        or lower.startswith("https://127.0.0.1")
        or lower.startswith("https://localhost")
    )


def post_json(label: str, url: str, request_id: str, payload: Dict[str, Any], timeout_seconds: float) -> HttpCallArtifact:
    request_snapshot = RequestSnapshot(
        timestamp=utc_now(),
        request_id=request_id,
        url=url,
        headers=build_headers(request_id),
        body=json_safe(payload),
    )
    response_timestamp = utc_now()
    try:
        session = requests.Session()
        # Local diagnostics should not inherit corporate proxy settings.
        if is_local_endpoint(url):
            session.trust_env = False
        response = session.post(url, json=payload, headers=request_snapshot.headers, timeout=timeout_seconds)
        status_code = response.status_code
        response_headers = dict(response.headers)
        raw_text = response.text
        parsed_json: Optional[Any]
        json_error: Optional[str] = None
        try:
            parsed_json = response.json()
        except Exception as exc:  # pragma: no cover - JSON parsing fallback
            parsed_json = None
            json_error = str(exc)
        return HttpCallArtifact(
            label=label,
            request=request_snapshot,
            response=ResponseSnapshot(
                timestamp=response_timestamp,
                status_code=status_code,
                headers=json_safe(response_headers),
                raw_text=raw_text,
                parsed_json=json_safe(parsed_json) if parsed_json is not None else None,
                json_parse_error=json_error,
            ),
        )
    except Exception as exc:
        return HttpCallArtifact(
            label=label,
            request=request_snapshot,
            response=ResponseSnapshot(
                timestamp=response_timestamp,
                status_code=None,
                headers={},
                raw_text="",
                parsed_json=None,
                json_parse_error=None,
                error=str(exc),
            ),
        )


def get_nested(value: Any, path: Sequence[str]) -> Any:
    current = value
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def extract_context_from_rag_response(response_json: Optional[Any]) -> List[Dict[str, Any]]:
    if not isinstance(response_json, dict):
        return []
    context_chunks = response_json.get("context_chunks")
    if isinstance(context_chunks, list):
        return [chunk for chunk in context_chunks if isinstance(chunk, dict)]
    return []


def response_error_code(response_json: Optional[Any]) -> Optional[str]:
    if not isinstance(response_json, dict):
        return None
    error = response_json.get("error")
    if isinstance(error, dict):
        code = error.get("code")
        if isinstance(code, str):
            return code
    return None


def response_error_field(response_json: Optional[Any]) -> Optional[str]:
    if not isinstance(response_json, dict):
        return None
    error = response_json.get("error")
    if not isinstance(error, dict):
        return None
    detail = error.get("detail")
    if isinstance(detail, dict):
        field = detail.get("field")
        if isinstance(field, str):
            return field
    return None


def request_failure_reason(response_json: Optional[Any]) -> Optional[str]:
    if not isinstance(response_json, dict):
        return None
    generation_failure_reason = response_json.get("generation_failure_reason")
    if isinstance(generation_failure_reason, dict):
        code = generation_failure_reason.get("code")
        if isinstance(code, str):
            return code
        message = generation_failure_reason.get("message")
        if isinstance(message, str):
            return message
    if isinstance(generation_failure_reason, str):
        return generation_failure_reason
    return None


def summarize_chunks(chunks: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    ranks = [chunk.get("rank") for chunk in chunks if isinstance(chunk.get("rank"), int)]
    top_reranker = None
    top_score = None
    for chunk in chunks:
        score = chunk.get("reranker_score")
        if score is None:
            score = chunk.get("cross_encoder_score")
        if isinstance(score, (int, float)):
            if top_score is None or float(score) > float(top_score):
                top_score = score
                top_reranker = chunk
    return {
        "chunk_count": len(chunks),
        "ranks": ranks,
        "top_reranker_score": top_score,
        "top_chunk": top_reranker,
    }


def classify_bundle(bundle: DiagnosticBundle) -> None:
    classifications: List[str] = []
    notes: List[str] = []

    rag_json = bundle.rag_call.response.parsed_json if bundle.rag_call else None
    copilot_json = bundle.copilot_call.response.parsed_json if bundle.copilot_call else None

    rag_error_code = response_error_code(rag_json)
    copilot_error_code = response_error_code(copilot_json)
    rag_failure_reason = request_failure_reason(rag_json)
    copilot_failure_reason = request_failure_reason(copilot_json)
    copilot_error_field = response_error_field(copilot_json)

    copilot_log_text = bundle.copilot_log_excerpt.excerpt.lower()
    rag_log_text = bundle.rag_log_excerpt.excerpt.lower()

    if bundle.rag_call and bundle.rag_call.response.status_code == 422:
        classifications.append("request_schema_failure")
        notes.append("RAG request was rejected with HTTP 422.")

    if any(token in (rag_failure_reason or "").lower() for token in ["request_build_failure", "request_validation_failure"]):
        classifications.append("request_schema_failure")

    if copilot_error_code == "RESPONSE_SCHEMA_MISMATCH" or "normalized response schema mismatch" in copilot_log_text:
        classifications.append("response_schema_mismatch")
        if copilot_error_field:
            notes.append(f"schema mismatch field={copilot_error_field}")
        elif "grounding_summary" in copilot_log_text:
            notes.append("schema mismatch field=grounding_summary")

    if copilot_error_field == "grounding_summary" or "grounding_summary field has invalid type" in copilot_log_text:
        classifications.append("response_schema_mismatch")
        notes.append("provider succeeded but normalization failed for grounding_summary")

    if any(token in (copilot_error_code or "").lower() for token in ["model_not_supported", "provider_failure"]):
        classifications.append("provider_model_failure")

    if any(token in (copilot_failure_reason or "").lower() for token in ["model_not_supported", "provider_failure"]):
        classifications.append("provider_model_failure")

    if any(token in (rag_failure_reason or "").lower() for token in ["response_contract_failure", "response_json_invalid"]):
        classifications.append("response_schema_mismatch")

    if any(token in (rag_failure_reason or "").lower() for token in ["transport_failure", "runtime_failure", "http_", "timeout"]):
        classifications.append("runtime_failure")

    if any(token in (copilot_failure_reason or "").lower() for token in ["semantic_failure", "answer_extraction_failure"]):
        classifications.append("semantic_failure")

    if bundle.rag_call and isinstance(rag_json, dict):
        result_status = str(rag_json.get("result_status") or "").lower()
        if result_status == "answer_extraction_failure":
            classifications.append("answer_extraction_failure")
        if result_status == "runtime_failure":
            classifications.append("runtime_failure")

        runtime = rag_json.get("runtime") if isinstance(rag_json.get("runtime"), dict) else {}
        retrieval_answerable = runtime.get("retrieval_answerable") if isinstance(runtime, dict) else None
        retrieval_sufficient = runtime.get("retrieval_sufficient") if isinstance(runtime, dict) else None
        if rag_json.get("abstained") is True and (retrieval_answerable is True or retrieval_sufficient is True):
            classifications.append("false_abstention")
        intent_analysis = rag_json.get("intent_analysis") if isinstance(rag_json.get("intent_analysis"), dict) else {}
        if isinstance(intent_analysis, dict) and intent_analysis.get("is_kb_relevant") is False and (intent_analysis.get("retrieval_answerable") is True or intent_analysis.get("retrieval_sufficient") is True):
            classifications.append("kb_relevance_false_negative")

    if copilot_json and isinstance(copilot_json, dict):
        if copilot_json.get("success") is False and copilot_json.get("abstained") is False and copilot_error_code == "RESPONSE_SCHEMA_MISMATCH":
            classifications.append("response_schema_mismatch")

    if not classifications:
        classifications.append("runtime_failure")

    priority = [
        "request_schema_failure",
        "provider_model_failure",
        "response_schema_mismatch",
        "answer_extraction_failure",
        "false_abstention",
        "semantic_failure",
        "kb_relevance_false_negative",
        "runtime_failure",
    ]
    for item in priority:
        if item in classifications:
            bundle.dominant_failure_cause = item
            break

    unique_classifications: List[str] = []
    for item in classifications:
        if item not in unique_classifications:
            unique_classifications.append(item)
    bundle.classifications = unique_classifications

    if bundle.dominant_failure_cause == "request_schema_failure":
        bundle.next_fix_target = "fix request builder"
    elif bundle.dominant_failure_cause == "provider_model_failure":
        bundle.next_fix_target = "fix model routing"
    elif bundle.dominant_failure_cause == "response_schema_mismatch":
        bundle.next_fix_target = "fix response adapter schema"
    elif bundle.dominant_failure_cause == "answer_extraction_failure":
        bundle.next_fix_target = "fix answer extraction"
    elif bundle.dominant_failure_cause == "false_abstention":
        bundle.next_fix_target = "tune grounding / abstention policy"
    elif bundle.dominant_failure_cause == "semantic_failure":
        bundle.next_fix_target = "inspect semantic failure classification"
    elif bundle.dominant_failure_cause == "kb_relevance_false_negative":
        bundle.next_fix_target = "inspect retrieval relevance thresholds"
    else:
        bundle.next_fix_target = "investigate runtime failure"

    if copilot_error_code == "RESPONSE_SCHEMA_MISMATCH" or "grounding_summary" in copilot_log_text:
        notes.append("provider succeeded but normalization failed")
        notes.append("inspect raw provider output and normalize grounding_summary into the expected dict schema")

    if "model_not_supported" in copilot_log_text or copilot_error_code == "model_not_supported":
        notes.append("provider/model routing failure detected")

    if bundle.copilot_call and bundle.copilot_call.response.error:
        notes.append(f"copilot capture error: {bundle.copilot_call.response.error}")

    bundle.notes = notes


def parse_log_timestamp(line: str) -> Optional[str]:
    match = re.match(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", line)
    if match:
        return match.group(1)
    return None


def collect_log_excerpt(source: str, request_id: str, paths: Sequence[Path], query: str) -> LogExcerpt:
    def _search(terms: Sequence[str]) -> Tuple[List[str], List[str], int]:
        excerpt_parts: List[str] = []
        scanned_files: List[str] = []
        match_count = 0
        lower_terms = [term.lower() for term in terms if term]
        for path in paths:
            if not path.exists():
                continue
            try:
                lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            except Exception as exc:
                excerpt_parts.append(f"# {path} (unreadable: {exc})")
                continue

            match_indexes: set[int] = set()
            for index, line in enumerate(lines):
                lower_line = line.lower()
                if any(term in lower_line for term in lower_terms):
                    start = max(0, index - 2)
                    end = min(len(lines), index + 3)
                    for excerpt_index in range(start, end):
                        match_indexes.add(excerpt_index)

            if not match_indexes:
                continue

            scanned_files.append(str(path))
            match_count += len(match_indexes)
            excerpt_parts.append(f"# {path}")
            for index in sorted(match_indexes):
                timestamp = parse_log_timestamp(lines[index]) or ""
                prefix = f"[{timestamp}] " if timestamp else ""
                excerpt_parts.append(f"{index + 1}: {prefix}{lines[index]}")
            excerpt_parts.append("")

        return excerpt_parts, scanned_files, match_count

    request_terms = [request_id]
    fallback_terms = [
        "grounded_qa.py",
        "api.py",
        "result_status",
        "failure_reason",
        "runtime diagnostics",
        "response schema mismatch",
        "normalized response schema mismatch",
        "grounding_summary",
        "RESPONSE_SCHEMA_MISMATCH",
        "model_not_supported",
        "provider_failure",
        "request_build_failure",
        "request_validation_failure",
        "transport_failure",
        "timeout",
    ]

    excerpt_lines, files_scanned, total_matches = _search(request_terms)
    unavailable_reason: Optional[str] = None
    if not files_scanned:
        excerpt_lines, files_scanned, total_matches = _search(fallback_terms)
    if not files_scanned and query:
        excerpt_lines, files_scanned, total_matches = _search([query])

    if not files_scanned:
        unavailable_reason = "no log files were available"
    elif not excerpt_lines:
        unavailable_reason = f"no matching log lines found for request_id={request_id}"

    return LogExcerpt(
        source=source,
        request_id=request_id,
        files_scanned=files_scanned,
        matches_found=total_matches,
        excerpt="\n".join(excerpt_lines).strip(),
        unavailable_reason=unavailable_reason,
    )


def analyze_grounding_summary_schema(copilot_json: Optional[Any]) -> Dict[str, Any]:
    """Analyze grounding_summary field for schema compliance and provide debugging info."""
    analysis: Dict[str, Any] = {
        "grounding_summary_present": False,
        "grounding_summary_type": None,
        "grounding_summary_value": None,
        "expected_fields": ["used_context_ranks", "light_semantic_inference_used"],
        "present_fields": [],
        "missing_fields": [],
        "field_types": {},
        "schema_valid": False,
        "issues": [],
        "debug_info": "",
    }

    if not isinstance(copilot_json, dict):
        analysis["debug_info"] = "Response is not a dict"
        return analysis

    grounding_summary = copilot_json.get("grounding_summary")
    if grounding_summary is None:
        analysis["issues"].append("grounding_summary field is missing from response")
        analysis["debug_info"] = "grounding_summary=None"
        return analysis

    analysis["grounding_summary_present"] = True
    analysis["grounding_summary_type"] = type(grounding_summary).__name__
    analysis["grounding_summary_value"] = grounding_summary

    if not isinstance(grounding_summary, dict):
        analysis["issues"].append(f"grounding_summary is {type(grounding_summary).__name__}, expected dict")
        analysis["debug_info"] = f"Type mismatch: {type(grounding_summary).__name__} instead of dict"
        return analysis

    # Check expected fields
    for field in analysis["expected_fields"]:
        if field in grounding_summary:
            analysis["present_fields"].append(field)
            value = grounding_summary[field]
            analysis["field_types"][field] = type(value).__name__

            # Type validation
            if field == "used_context_ranks" and not isinstance(value, list):
                analysis["issues"].append(f"Field '{field}' should be list, got {type(value).__name__}")
            elif field == "light_semantic_inference_used" and not isinstance(value, bool):
                analysis["issues"].append(f"Field '{field}' should be bool, got {type(value).__name__}")
        else:
            analysis["missing_fields"].append(field)
            analysis["issues"].append(f"Expected field '{field}' is missing")

    # Extra fields (might indicate versioning issue)
    extra_fields = [k for k in grounding_summary.keys() if k not in analysis["expected_fields"]]
    if extra_fields:
        analysis["issues"].append(f"Unexpected fields in grounding_summary: {extra_fields}")

    analysis["schema_valid"] = len(analysis["issues"]) == 0

    # Generate debug string
    if analysis["schema_valid"]:
        analysis["debug_info"] = "✓ grounding_summary schema is valid"
    else:
        analysis["debug_info"] = "; ".join(analysis["issues"])

    return analysis


def build_timeline(bundle: DiagnosticBundle) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []

    def add_request_event(label: str, artifact: HttpCallArtifact) -> None:
        events.append(
            {
                "timestamp": artifact.request.timestamp,
                "source": label,
                "kind": "request",
                "request_id": artifact.request.request_id,
                "url": artifact.request.url,
                "body": artifact.request.body,
            }
        )

    def add_response_event(label: str, artifact: HttpCallArtifact) -> None:
        events.append(
            {
                "timestamp": artifact.response.timestamp,
                "source": label,
                "kind": "response",
                "request_id": artifact.request.request_id,
                "status_code": artifact.response.status_code,
                "json_parse_error": artifact.response.json_parse_error,
                "error": artifact.response.error,
                "body": artifact.response.parsed_json if artifact.response.parsed_json is not None else artifact.response.raw_text,
            }
        )

    if bundle.rag_call:
        add_request_event("rag", bundle.rag_call)
        add_response_event("rag", bundle.rag_call)
    if bundle.copilot_call:
        add_request_event("copilot", bundle.copilot_call)
        add_response_event("copilot", bundle.copilot_call)

    def add_log_events(label: str, excerpt: LogExcerpt) -> None:
        if not excerpt.excerpt:
            return
        for line in excerpt.excerpt.splitlines():
            if not line or line.startswith("# "):
                continue
            line_number, _, remainder = line.partition(": ")
            timestamp = parse_log_timestamp(remainder)
            events.append(
                {
                    "timestamp": timestamp,
                    "source": label,
                    "kind": "log_line",
                    "line_number": line_number,
                    "line": remainder,
                    "request_id": excerpt.request_id,
                }
            )

    add_log_events("rag_log", bundle.rag_log_excerpt)
    add_log_events("copilot_log", bundle.copilot_log_excerpt)

    def sort_key(event: Dict[str, Any]) -> Tuple[str, str, str]:
        return (str(event.get("timestamp") or ""), str(event.get("source") or ""), str(event.get("kind") or ""))

    events.sort(key=sort_key)
    return events


def make_summary(bundle: DiagnosticBundle) -> str:
    rag_json = bundle.rag_call.response.parsed_json if bundle.rag_call else None
    copilot_json = bundle.copilot_call.response.parsed_json if bundle.copilot_call else None

    rag_status = bundle.rag_call.response.status_code if bundle.rag_call else None
    copilot_status = bundle.copilot_call.response.status_code if bundle.copilot_call else None
    rag_error = response_error_code(rag_json)
    copilot_error = response_error_code(copilot_json)
    copilot_field = response_error_field(copilot_json)

    # Analyze grounding_summary schema for better diagnostics
    grounding_analysis = analyze_grounding_summary_schema(copilot_json)

    rag_chunks = extract_context_from_rag_response(rag_json)
    retrieval = summarize_chunks(rag_chunks)
    rag_intent = rag_json.get("intent_analysis", {}) if isinstance(rag_json, dict) else {}
    rag_runtime = rag_json.get("runtime", {}) if isinstance(rag_json, dict) else {}

    lines = [
        f"# Grounded QA Diagnostic Summary",
        "",
        f"## Request Metadata",
        f"- request_id: {bundle.request_id}",
        f"- case: {bundle.case.name}",
        f"- query: {bundle.case.query}",
        f"- mode: {bundle.case.mode}",
        f"- timestamp: {bundle.generated_at}",
        f"- endpoints: {DEFAULT_RAG_BASE_URL}/api/query, {DEFAULT_COPILOT_BASE_URL}/qa/answer",
        f"- expected_failure_class: {bundle.case.expected_failure_class or 'n/a'}",
        "",
        f"## Retrieval Summary",
        f"- chunk_count: {retrieval['chunk_count']}",
        f"- ranks: {retrieval['ranks']}",
        f"- top_reranker_score: {retrieval['top_reranker_score']}",
        f"- retrieval_sufficient: {rag_intent.get('retrieval_sufficient')}",
        f"- retrieval_answerable: {rag_intent.get('retrieval_answerable')}",
        f"- is_kb_relevant: {rag_intent.get('is_kb_relevant')}",
        "",
        f"## Response Summary",
        f"- rag_http_status: {rag_status}",
        f"- copilot_http_status: {copilot_status}",
        f"- rag_result_status: {rag_json.get('result_status') if isinstance(rag_json, dict) else None}",
        f"- rag_success: {rag_json.get('success') if isinstance(rag_json, dict) else None}",
        f"- rag_answer_present: {bool((rag_json or {}).get('answer')) if isinstance(rag_json, dict) else None}",
        f"- rag_gateway_http_status: {rag_json.get('gateway_http_status') if isinstance(rag_json, dict) else None}",
        f"- rag_provider_http_status: {rag_json.get('provider_http_status') if isinstance(rag_json, dict) else None}",
        f"- copilot_success: {copilot_json.get('success') if isinstance(copilot_json, dict) else None}",
        f"- copilot_error_code: {copilot_error}",
        f"- copilot_error_field: {copilot_field}",
        f"- copilot_error_message: {get_nested(copilot_json, ['error', 'message']) if isinstance(copilot_json, dict) else None}",
        f"- copilot_runtime_generation_executed: {get_nested(copilot_json, ['runtime', 'generation_executed']) if isinstance(copilot_json, dict) else None}",
        f"- copilot_runtime_answer_extraction_success: {get_nested(copilot_json, ['runtime', 'answer_extraction_success']) if isinstance(copilot_json, dict) else None}",
        f"- rag_runtime_generation_executed: {rag_runtime.get('generation_executed') if isinstance(rag_runtime, dict) else None}",
        f"- rag_runtime_generation_failure_reason: {rag_runtime.get('generation_failure_reason') if isinstance(rag_runtime, dict) else None}",
        "",
        f"## Answer Normalization Diagnostics",
    ]
    
    # Add empty answer detection
    rag_answer = (rag_json or {}).get("answer") if isinstance(rag_json, dict) else None
    rag_abstained = (rag_json or {}).get("abstained") if isinstance(rag_json, dict) else None
    rag_abstention_reason = (rag_json or {}).get("abstention_reason") if isinstance(rag_json, dict) else None
    rag_generation_executed = rag_runtime.get("generation_executed") if isinstance(rag_runtime, dict) else None
    
    rag_answer_is_empty = not (rag_answer and isinstance(rag_answer, str) and rag_answer.strip())
    
    lines.extend([
        f"- rag_answer_empty: {rag_answer_is_empty}",
        f"- rag_answer_length: {len(rag_answer) if isinstance(rag_answer, str) else 'N/A'}",
        f"- rag_abstained: {rag_abstained}",
        f"- rag_abstention_reason: {rag_abstention_reason or 'N/A'}",
        f"- rag_generation_executed: {rag_generation_executed}",
    ])
    
    # Critical: Check for the bug condition
    if rag_generation_executed and rag_answer_is_empty:
        lines.append(f"- CRITICAL_ISSUE: generation_executed=true but answer is empty!")
        if rag_abstained:
            lines.append(f"  ⚠️  INVARIANT VIOLATION: abstained=true with empty answer and generation_executed=true")
            lines.append(f"      → Fix applied in _normalize_final_answer() should prevent this")
        else:
            lines.append(f"  ⚠️  INVARIANT VIOLATION: non-abstention with empty answer and generation_executed=true")
    else:
        lines.append(f"- empty_answer_invariant: ✓ OK")
    
    lines.extend([
        "",
        f"## Probable Failure Classification",
        f"- dominant_failure_cause: {bundle.dominant_failure_cause}",
        f"- all_classifications: {bundle.classifications}",
        f"- next_recommended_fix_target: {bundle.next_fix_target}",
        "",
        f"## Special Pattern Detection",
    ])

    if copilot_error == "RESPONSE_SCHEMA_MISMATCH" or copilot_field == "grounding_summary":
        lines.extend(
            [
                "- detected: response_schema_mismatch",
                f"- field_causing_mismatch: {copilot_field or 'grounding_summary'}",
                "- provider_succeeded_but_normalization_failed: yes",
                "- recommendation: inspect raw provider output and normalize grounding_summary into the expected dict schema",
                "",
                f"## Grounding Summary Schema Analysis",
                f"- schema_valid: {grounding_analysis['schema_valid']}",
                f"- grounding_summary_present: {grounding_analysis['grounding_summary_present']}",
                f"- grounding_summary_type: {grounding_analysis['grounding_summary_type']}",
                f"- expected_fields: {grounding_analysis['expected_fields']}",
                f"- present_fields: {grounding_analysis['present_fields']}",
                f"- missing_fields: {grounding_analysis['missing_fields']}",
                f"- field_types: {grounding_analysis['field_types']}",
                f"- issues: {grounding_analysis['issues']}",
                f"- debug_info: {grounding_analysis['debug_info']}",
            ]
        )
    else:
        lines.append("- detected: no special schema mismatch pattern confirmed")

    lines.extend(
        [
            "",
            f"## Evidence Notes",
        ]
    )

    if bundle.rag_log_excerpt.unavailable_reason:
        lines.append(f"- rag_log_excerpt: {bundle.rag_log_excerpt.unavailable_reason}")
    else:
        lines.append(f"- rag_log_excerpt: {bundle.rag_log_excerpt.matches_found} matching lines across {len(bundle.rag_log_excerpt.files_scanned)} file(s)")

    if bundle.copilot_log_excerpt.unavailable_reason:
        lines.append(f"- copilot_log_excerpt: {bundle.copilot_log_excerpt.unavailable_reason}")
    else:
        lines.append(f"- copilot_log_excerpt: {bundle.copilot_log_excerpt.matches_found} matching lines across {len(bundle.copilot_log_excerpt.files_scanned)} file(s)")

    if bundle.notes:
        lines.append(f"- additional_notes: {bundle.notes}")

    lines.extend(
        [
            "",
            f"## Limitations",
            "- Raw provider-internal payload before Copilot schema validation is only available if the Copilot API logs include it.",
            "- If the Copilot log path is not configured, the script will still preserve the HTTP response body and mark the log source as unavailable.",
        ]
    )
    return "\n".join(lines).strip() + "\n"


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(json_safe(data), indent=2, ensure_ascii=True), encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def run_case(
    case: DiagnosticCase,
    rag_base_url: str,
    copilot_base_url: str,
    output_root: Path,
    rag_log_glob: str,
    copilot_log_paths: Sequence[Path],
    timeout_seconds: float,
    context_preload: bool,
) -> DiagnosticBundle:
    request_id = case.request_id or generate_request_id(case.name)
    generated_at = utc_now()
    case_output_dir = output_root / request_id
    ensure_directory(case_output_dir)

    rag_request = build_rag_request_payload(case, request_id)
    request_payload: Dict[str, Any] = {
        "request_id": request_id,
        "generated_at": generated_at,
        "case": json_safe(asdict(case)),
        "rag_request": rag_request,
        "copilot_request": None,
    }

    rag_call: Optional[HttpCallArtifact] = None
    copilot_call: Optional[HttpCallArtifact] = None
    bundle = DiagnosticBundle(
        request_id=request_id,
        case=case,
        generated_at=generated_at,
        output_dir=str(case_output_dir),
        request_payload=request_payload,
        rag_log_excerpt=LogExcerpt(source="rag", request_id=request_id),
        copilot_log_excerpt=LogExcerpt(source="copilot", request_id=request_id),
    )

    mode = case.mode.lower().strip()
    if mode not in {"rag", "direct", "both"}:
        raise ValueError(f"Unsupported mode '{case.mode}'. Use rag, direct, or both.")

    if mode in {"rag", "both"}:
        rag_call = post_json("rag", f"{rag_base_url.rstrip('/')}/api/query", request_id, rag_request, timeout_seconds)

    direct_context_chunks = case.context_chunks or extract_context_from_rag_response(rag_call.response.parsed_json if rag_call else None)
    if not direct_context_chunks and mode in {"direct", "both"} and context_preload and rag_call is None:
        rag_call = post_json("rag_preload", f"{rag_base_url.rstrip('/')}/api/query", request_id, rag_request, timeout_seconds)
        direct_context_chunks = case.context_chunks or extract_context_from_rag_response(rag_call.response.parsed_json if rag_call else None)

    if mode in {"direct", "both"}:
        if direct_context_chunks:
            copilot_request = build_copilot_request_payload(case, request_id, direct_context_chunks)
            request_payload["copilot_request"] = copilot_request
            copilot_call = post_json("copilot", f"{copilot_base_url.rstrip('/')}/qa/answer", request_id, copilot_request, timeout_seconds)
        else:
            bundle.notes.append("Direct /qa/answer call skipped because no context_chunks were available.")

    bundle.rag_call = rag_call
    bundle.copilot_call = copilot_call

    rag_paths = [Path(path) for path in glob.glob(rag_log_glob)]
    rag_paths.sort(key=lambda path: path.stat().st_mtime if path.exists() else 0, reverse=True)
    bundle.rag_log_excerpt = collect_log_excerpt("rag", request_id, rag_paths, case.query)
    bundle.copilot_log_excerpt = collect_log_excerpt("copilot", request_id, copilot_log_paths, case.query)

    classify_bundle(bundle)
    bundle.merged_timeline = build_timeline(bundle)
    bundle.diagnosis_summary = make_summary(bundle)

    # Analyze grounding_summary for detailed schema insights
    copilot_json = bundle.copilot_call.response.parsed_json if bundle.copilot_call else None
    grounding_analysis = analyze_grounding_summary_schema(copilot_json)

    write_json(case_output_dir / "request_payload.json", bundle.request_payload)
    if bundle.rag_call is not None:
        write_json(case_output_dir / "rag_response.json", asdict(bundle.rag_call))
    if bundle.copilot_call is not None:
        write_json(case_output_dir / "copilot_response.json", asdict(bundle.copilot_call))
    write_text(case_output_dir / "rag_log_excerpt.txt", bundle.rag_log_excerpt.excerpt or bundle.rag_log_excerpt.unavailable_reason or "")
    write_text(case_output_dir / "copilot_log_excerpt.txt", bundle.copilot_log_excerpt.excerpt or bundle.copilot_log_excerpt.unavailable_reason or "")
    write_json(case_output_dir / "merged_timeline.json", {"request_id": request_id, "events": bundle.merged_timeline})
    write_text(case_output_dir / "diagnosis_summary.md", bundle.diagnosis_summary)
    write_json(case_output_dir / "grounding_summary_analysis.json", grounding_analysis)

    return bundle


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run correlated grounded QA diagnostics.")
    parser.add_argument("--cases-file", type=Path, default=DEFAULT_CASES_FILE, help="JSON file containing diagnostic cases.")
    parser.add_argument("--query", type=str, help="Run a single inline test case query.")
    parser.add_argument("--mode", choices=["rag", "direct", "both"], default=None, help="Override mode for an inline test case.")
    parser.add_argument("--name", type=str, default="inline_case", help="Name for an inline case.")
    parser.add_argument("--request-id", type=str, default=None, help="Override request_id for a single inline case.")
    parser.add_argument("--top-k", type=int, default=5, help="Override top_k for a single inline case.")
    parser.add_argument("--rerank-top-k", type=int, default=3, help="Override rerank_top_k for a single inline case.")
    parser.add_argument("--model", type=str, default=None, help="Override model for a single inline case.")
    parser.add_argument("--expected-failure-class", type=str, default=None, help="Expected failure class for a single inline case.")
    parser.add_argument("--notes", type=str, default=None, help="Notes for a single inline case.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_ROOT, help="Directory where diagnostic bundles are written.")
    parser.add_argument("--rag-base-url", type=str, default=DEFAULT_RAG_BASE_URL, help="Base URL for the MarkItDown RAG server.")
    parser.add_argument("--copilot-base-url", type=str, default=DEFAULT_COPILOT_BASE_URL, help="Base URL for the Copilot API server.")
    parser.add_argument("--rag-log-glob", type=str, default=DEFAULT_RAG_LOG_GLOB, help="Glob for MarkItDown log files.")
    parser.add_argument("--copilot-log-file", type=Path, action="append", default=[], help="Explicit Copilot log file path. Can be passed multiple times.")
    parser.add_argument("--copilot-log-glob", type=str, default=None, help="Optional glob for Copilot log files.")
    parser.add_argument("--timeout", type=float, default=120.0, help="HTTP timeout in seconds for each request.")
    parser.add_argument("--no-context-preload", action="store_true", help="Do not call /api/query to preload context for direct /qa/answer mode.")
    return parser.parse_args()


def build_inline_case(args: argparse.Namespace) -> DiagnosticCase:
    if not args.query:
        raise ValueError("--query is required when not using --cases-file")
    return DiagnosticCase(
        name=args.name,
        query=args.query,
        mode=args.mode or "both",
        top_k=args.top_k,
        rerank_top_k=args.rerank_top_k,
        model=args.model,
        request_id=args.request_id,
        expected_failure_class=args.expected_failure_class,
        notes=args.notes,
    )


def collect_copilot_log_paths(args: argparse.Namespace) -> List[Path]:
    paths: List[Path] = []
    paths.extend(args.copilot_log_file or [])
    if args.copilot_log_glob:
        paths.extend(Path(path) for path in glob.glob(args.copilot_log_glob))
    unique_paths: List[Path] = []
    seen: set[str] = set()
    for path in paths:
        resolved = str(path)
        if resolved in seen:
            continue
        seen.add(resolved)
        unique_paths.append(path)
    unique_paths.sort(key=lambda path: path.stat().st_mtime if path.exists() else 0, reverse=True)
    return unique_paths


def main() -> int:
    args = parse_args()
    ensure_directory(args.output_dir)

    if args.query:
        cases = [build_inline_case(args)]
    else:
        cases = load_cases(args.cases_file)

    copilot_log_paths = collect_copilot_log_paths(args)
    bundles: List[DiagnosticBundle] = []
    for case in cases:
        bundle = run_case(
            case=case,
            rag_base_url=args.rag_base_url,
            copilot_base_url=args.copilot_base_url,
            output_root=args.output_dir,
            rag_log_glob=args.rag_log_glob,
            copilot_log_paths=copilot_log_paths,
            timeout_seconds=args.timeout,
            context_preload=not args.no_context_preload,
        )
        bundles.append(bundle)

    for bundle in bundles:
        print(f"request_id={bundle.request_id}")
        print(f"output_dir={bundle.output_dir}")
        print(f"dominant_failure_cause={bundle.dominant_failure_cause}")
        print(f"next_fix_target={bundle.next_fix_target}")
        print(f"classifications={bundle.classifications}")
        print("-")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())