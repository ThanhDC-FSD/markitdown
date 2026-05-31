#!/usr/bin/env python3
"""Local mock Copilot QA server implementing /qa/answer contract.

This server is used for offline diagnostics when upstream Copilot/provider
credentials are unavailable. It returns schema-valid grounded responses.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Dict, List


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def short_text(value: str, limit: int = 320) -> str:
    text = (value or "").strip().replace("\n", " ")
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def build_answer(query: str, context_chunks: List[Dict[str, Any]]) -> str:
    if not context_chunks:
        return f"I could not find supporting context to answer: {query}"

    top = context_chunks[0] if isinstance(context_chunks[0], dict) else {}
    snippet = short_text(str(top.get("text") or ""))
    if snippet:
        return f"Based on the retrieved context, {snippet}"
    return f"Based on the retrieved context, I found relevant information for: {query}"


class MockCopilotQAHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        if self.path != "/qa/answer":
            self.send_response(404)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"error":"not_found"}')
            return

        content_length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(content_length)
        try:
            payload = json.loads(body.decode("utf-8")) if body else {}
        except json.JSONDecodeError:
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"error":"invalid_json"}')
            return

        query = str(payload.get("query") or "")
        request_id = str(payload.get("request_id") or "mock_request")
        model_requested = str(payload.get("model") or "gpt-5-mini")
        context_chunks = payload.get("context_chunks")
        if not isinstance(context_chunks, list):
            context_chunks = []

        ranks: List[int] = []
        citations: List[Dict[str, Any]] = []
        for chunk in context_chunks[:3]:
            if not isinstance(chunk, dict):
                continue
            rank = int(chunk.get("rank") or (len(ranks) + 1))
            ranks.append(rank)
            meta = chunk.get("metadata") if isinstance(chunk.get("metadata"), dict) else {}
            citations.append(
                {
                    "rank": rank,
                    "source": str(meta.get("source") or "mock_context"),
                    "snippet": short_text(str(chunk.get("text") or ""), 180),
                }
            )

        answer = build_answer(query, context_chunks)

        response = {
            "request_id": request_id,
            "success": True,
            "model_requested": model_requested,
            "model_used": "mock-copilot-local",
            "query": query,
            "answer": answer,
            "abstained": False,
            "abstention_reason": None,
            "citations": citations,
            "grounding_summary": {
                "used_context_ranks": ranks,
                "light_semantic_inference_used": False,
            },
            "runtime": {
                "llm_invocation_attempted": True,
                "llm_http_status": 200,
                "llm_transport_success": True,
                "llm_response_json_valid": True,
                "llm_response_schema_valid": True,
                "answer_extraction_success": True,
                "generation_executed": True,
                "generation_failure_reason": {
                    "code": "success",
                    "message": "success",
                    "detail": {"mock": True, "timestamp": utc_now()},
                },
            },
            "error": {
                "code": "success",
                "message": "success",
                "detail": {"mock": True},
            },
        }

        encoded = json.dumps(response).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format: str, *args: Any) -> None:
        return


def main() -> None:
    server = HTTPServer(("127.0.0.1", 18080), MockCopilotQAHandler)
    print("Mock Copilot QA server listening on http://127.0.0.1:18080/qa/answer")
    server.serve_forever()


if __name__ == "__main__":
    main()
