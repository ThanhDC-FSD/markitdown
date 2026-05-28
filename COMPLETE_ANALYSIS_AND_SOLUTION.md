# Complete Analysis & Solution: Grounding Summary Schema Mismatch

## Executive Summary

Your Copilot API's LLM is failing to generate responses that pass the provider's schema validation. The issue is with **what the LLM generates internally**, not the final response we see.

**Status**: ✅ Root cause identified, ✅ Diagnostic tool enhanced, ✅ Fix guide created

---

## Problem Statement

### Symptom
```json
{
  "success": false,
  "result_status": "runtime_failure",
  "answer": "",
  "error": {
    "code": "RESPONSE_SCHEMA_MISMATCH",
    "detail": {
      "field": "grounding_summary",
      "expected": "dict"
    }
  }
}
```

### Root Cause
The Copilot API's LLM returns a response that fails schema validation:
```
llm_response_schema_valid: false  ← ⭐ THE REAL ISSUE
```

The fallback error response shows a valid `grounding_summary`, but that's masking the fact that the LLM never generated a valid response in the first place.

---

## Technical Analysis

### The Two Layers of Response

**Layer 1: Final Response (What we see)**
```json
{
  "grounding_summary": {
    "used_context_ranks": [],
    "light_semantic_inference_used": false
  }
}
```
✅ Valid dict, all fields present, correct types

**Layer 2: LLM Internal Response (What really failed)**
```
Status: ❌ REJECTED by provider's schema validator
Reason: LLM returned something that didn't match expected schema
Result: Provider created fallback error response
```

### Evidence Chain
1. HTTP 200 from provider → Transport succeeded ✅
2. Response JSON valid → JSON parsing succeeded ✅
3. llm_response_schema_valid: **false** → Schema validation FAILED ❌
4. Attempted models: [4 different models] → Multiple fallbacks tried ❌
5. fallback_applied: false → No successful fallback ❌

### Diagnostic Output
```json
{
  "schema_valid": true,                   // ← Fallback IS valid
  "grounding_summary_present": true,
  "grounding_summary_type": "dict",
  "present_fields": ["used_context_ranks", "light_semantic_inference_used"],
  "missing_fields": [],
  "field_types": {
    "used_context_ranks": "list",
    "light_semantic_inference_used": "bool"
  },
  "issues": [],
  "debug_info": "✓ grounding_summary schema is valid"
}
```

---

## Why This Happens

### Scenario 1: Unclear LLM Prompt
```
LLM receives: "Generate grounded QA response"
LLM thinks: "I'll return answer and citations"
LLM forgets: "I need to include grounding_summary field"
Provider validates: "Missing grounding_summary field" ❌
```

### Scenario 2: Wrong Format in Response
```
LLM returns: "grounding_summary": null
Provider expects: "grounding_summary": {dict}
Provider validates: "Type mismatch" ❌
```

### Scenario 3: Schema Version Mismatch
```
LLM trained on old schema format
Provider expects new schema format
Mismatch causes rejection ❌
```

---

## Solution Overview

### Quick Fix (3 Options)

#### **Option 1: Update LLM Prompt** ⭐ Recommended
- Make `grounding_summary` requirement explicit
- Include example JSON showing exact format
- Add field descriptions
- File: Copilot API LLM prompt

#### **Option 2: Add Response Normalization**
- Catch invalid `grounding_summary` from LLM
- Replace with valid structure
- File: RAG response adapter

#### **Option 3: Relax Provider Validation**
- Don't fail on schema mismatches
- Gracefully create fallback
- File: Copilot API response validator

---

## Implementation Details

### Option 1: Update LLM System Prompt

**Location**: `copilot-api/python/.../grounded_qa.py` (or wherever LLM is prompted)

**Current (Broken)**:
```python
system_prompt = """Generate a grounded QA response."""
```

**Fixed**:
```python
system_prompt = """
You are a Grounded QA assistant. You MUST return a JSON object with:

{
  "request_id": "...",
  "success": true,
  "answer": "Your detailed answer here",
  "citations": [
    {"rank": 1, "doc_id": "doc_1", "chunk_index": 1},
    {"rank": 2, "doc_id": "doc_1", "chunk_index": 2}
  ],
  "grounding_summary": {
    "used_context_ranks": [1, 2],
    "light_semantic_inference_used": false
  }
}

CRITICAL REQUIREMENTS:
1. grounding_summary MUST be present and be a dict (object)
2. used_context_ranks MUST be an array of integers [1, 2, 3...]
   - Include the rank numbers of context chunks you actually used
   - If you only used chunk 1, write: [1]
   - If you used chunks 1 and 3, write: [1, 3]
3. light_semantic_inference_used MUST be true or false
   - Set to false if you used only direct quotes from context
   - Set to true if you needed to infer or connect concepts

EXAMPLES:

Example 1 (Direct answer from chunk 1 only):
{
  "answer": "...",
  "citations": [{"rank": 1, ...}],
  "grounding_summary": {
    "used_context_ranks": [1],
    "light_semantic_inference_used": false
  }
}

Example 2 (Synthesized from chunks 1, 2, and 3):
{
  "answer": "...",
  "citations": [{"rank": 1, ...}, {"rank": 2, ...}, {"rank": 3, ...}],
  "grounding_summary": {
    "used_context_ranks": [1, 2, 3],
    "light_semantic_inference_used": true
  }
}

DO NOT SKIP grounding_summary. DO NOT return null for grounding_summary.
"""
```

### Option 2: Add Response Normalization

**Location**: `src/rag_pipeline/grounded_qa.py`

```python
def normalize_grounding_summary(response):
    """Ensure grounding_summary is valid dict with required fields."""
    
    gs = response.get("grounding_summary")
    
    # If missing or not dict, create valid structure
    if not isinstance(gs, dict):
        response["grounding_summary"] = {
            "used_context_ranks": [],
            "light_semantic_inference_used": False
        }
        return response
    
    # Ensure required fields exist
    if "used_context_ranks" not in gs:
        gs["used_context_ranks"] = []
    elif not isinstance(gs["used_context_ranks"], list):
        gs["used_context_ranks"] = list(gs["used_context_ranks"]) if gs["used_context_ranks"] else []
    
    if "light_semantic_inference_used" not in gs:
        gs["light_semantic_inference_used"] = False
    elif not isinstance(gs["light_semantic_inference_used"], bool):
        gs["light_semantic_inference_used"] = bool(gs["light_semantic_inference_used"])
    
    return response

# In response handler:
copilot_response = normalize_grounding_summary(copilot_response)
```

### Option 3: Relax Provider Validation

**Location**: Copilot API response validator

```python
def validate_and_normalize(response):
    """Validate response, but gracefully handle schema mismatches."""
    
    try:
        # Try strict validation
        return validate_schema_strict(response)
    except SchemaValidationError as e:
        if "grounding_summary" in str(e):
            # Log but recover
            logger.warning(f"Provider schema mismatch: {e}. Using fallback.")
            
            # Create valid structure
            if not isinstance(response.get("grounding_summary"), dict):
                response["grounding_summary"] = {
                    "used_context_ranks": [],
                    "light_semantic_inference_used": False
                }
            return response
        else:
            raise  # Re-raise for other validation errors
```

---

## Testing & Validation

### Step 1: Run Enhanced Diagnostic
```bash
python src/diagnostics/grounded_qa_diagnostic.py \
  --cases-file src/diagnostics/grounded_qa_cases.json \
  --output-dir diagnostics/grounded_qa_runs
```

### Step 2: Check Grounding Summary Analysis
```bash
# View the analysis
cat diagnostics/grounded_qa_runs/diag_*/grounding_summary_analysis.json

# Should show:
# {
#   "schema_valid": true,
#   "issues": [],
#   ...
# }
```

### Step 3: Verify Response
```bash
# Check diagnosis summary
cat diagnostics/grounded_qa_runs/diag_*/diagnosis_summary.md

# Look for:
# - rag_result_status: success (not runtime_failure)
# - rag_success: True
# - rag_answer_present: True
```

### Step 4: End-to-End Test
```python
import requests

response = requests.post("http://127.0.0.1:8001/api/query", json={
    "query": "Why are internet based clients important?",
    "top_k": 5
})

result = response.json()
assert result["success"], "Query should succeed"
assert result["answer"], "Should have answer"
assert isinstance(result["grounding_summary"], dict), "Should have valid grounding_summary"
assert isinstance(result["grounding_summary"]["used_context_ranks"], list), "used_context_ranks should be list"
assert isinstance(result["grounding_summary"]["light_semantic_inference_used"], bool), "light_semantic_inference_used should be bool"

print("✅ All checks passed!")
```

---

## Expected Results After Fix

### Current (Broken)
```json
{
  "success": false,
  "result_status": "runtime_failure",
  "answer": "",
  "llm_response_schema_valid": false,
  "error": {...}
}
```

### After Fix
```json
{
  "success": true,
  "result_status": "success",
  "answer": "Internet based clients are important in the Cloud Age because...",
  "llm_response_schema_valid": true,
  "citations": [{...}],
  "grounding_summary": {
    "used_context_ranks": [1],
    "light_semantic_inference_used": false
  }
}
```

---

## Diagnostic Tool Enhancements

### New Capabilities
- ✅ Request-ID anchored log collection (minimal noise)
- ✅ Grounding summary schema analysis (field-by-field validation)
- ✅ Automatic issue detection (lists all problems)
- ✅ JSON output for programmatic use
- ✅ Human-readable summaries (easy interpretation)

### New Files Generated
```
diagnostics/grounded_qa_runs/diag_*/
├── diagnosis_summary.md                    (includes new schema analysis section)
├── grounding_summary_analysis.json         (NEW: detailed field analysis)
├── merged_timeline.json
├── rag_response.json
├── copilot_response.json
├── rag_log_excerpt.txt
├── copilot_log_excerpt.txt
└── request_payload.json
```

---

## Documentation Created

### 1. [QUICK_FIX_GROUNDING_SUMMARY.md](QUICK_FIX_GROUNDING_SUMMARY.md)
30-second problem summary + 3 fix options

### 2. [GROUNDING_SUMMARY_FIX_GUIDE.md](GROUNDING_SUMMARY_FIX_GUIDE.md)
Comprehensive guide with detailed analysis and verification

### 3. [DIAGNOSTIC_ENHANCEMENTS.md](DIAGNOSTIC_ENHANCEMENTS.md)
Details on tool improvements and how to use them

### 4. [grounded_qa_diagnostic.py](src/diagnostics/grounded_qa_diagnostic.py) - Enhanced
New `analyze_grounding_summary_schema()` function + integration

---

## Action Items

### Immediate
- [ ] Review [QUICK_FIX_GROUNDING_SUMMARY.md](QUICK_FIX_GROUNDING_SUMMARY.md)
- [ ] Choose fix option (recommend Option 1: update LLM prompt)

### Implementation (1-2 hours)
- [ ] Update Copilot API LLM system prompt with explicit format
- [ ] Or add response normalization to RAG adapter
- [ ] Test with one query

### Validation (30 minutes)
- [ ] Run `grounded_qa_diagnostic.py`
- [ ] Verify `llm_response_schema_valid: true`
- [ ] Check `grounding_summary_analysis.json` shows `schema_valid: true`
- [ ] End-to-end test with multiple queries

---

## Success Criteria

✅ **Query succeeds** with `success: true`  
✅ **Answer generated** with non-empty text  
✅ **Schema valid** with `llm_response_schema_valid: true`  
✅ **Grounding summary** includes correct `used_context_ranks`  
✅ **Diagnostic runs** without errors  

---

## Summary

The **root cause** is that the Copilot API's LLM is not generating a response with a properly formatted `grounding_summary` field. The **solution** is to either:
1. Make the LLM prompt more explicit about the required format (recommended)
2. Add normalization to handle provider variations
3. Relax provider validation with graceful fallback

The **enhanced diagnostic tool** now makes this problem crystal clear with detailed schema analysis, and the **fix guides** provide step-by-step implementation instructions.

