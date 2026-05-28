# Grounded QA Diagnostic Summary

## Request Metadata
- request_id: diag_inline_case_20260528042042_9c67dba1
- case: inline_case
- query: Why are internet based clients important in the Cloud Age?
- mode: both
- timestamp: 2026-05-28T04:20:42.844266+00:00
- endpoints: http://127.0.0.1:8001/api/query, http://localhost:8080/qa/answer
- expected_failure_class: n/a

## Retrieval Summary
- chunk_count: 0
- ranks: []
- top_reranker_score: None
- retrieval_sufficient: None
- retrieval_answerable: None
- is_kb_relevant: None

## Response Summary
- rag_http_status: None
- copilot_http_status: None
- rag_result_status: None
- rag_success: None
- rag_answer_present: None
- rag_gateway_http_status: None
- rag_provider_http_status: None
- copilot_success: None
- copilot_error_code: None
- copilot_error_field: None
- copilot_error_message: None
- copilot_runtime_generation_executed: None
- copilot_runtime_answer_extraction_success: None
- rag_runtime_generation_executed: None
- rag_runtime_generation_failure_reason: None

## Probable Failure Classification
- dominant_failure_cause: runtime_failure
- all_classifications: ['runtime_failure']
- next_recommended_fix_target: investigate runtime failure

## Special Pattern Detection
- detected: no special schema mismatch pattern confirmed

## Evidence Notes
- rag_log_excerpt: 2407 matching lines across 135 file(s)
- copilot_log_excerpt: no log files were available

## Limitations
- Raw provider-internal payload before Copilot schema validation is only available if the Copilot API logs include it.
- If the Copilot log path is not configured, the script will still preserve the HTTP response body and mark the log source as unavailable.
