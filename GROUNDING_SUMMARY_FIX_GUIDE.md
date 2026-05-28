# Grounding Summary Schema Mismatch - Root Cause & Fix Guide

## Problem Summary

The diagnostic reveals a **two-layer issue**:

### Layer 1: Response Layer (What We See)
```json
"grounding_summary": {
  "used_context_ranks": [],
  "light_semantic_inference_used": false
}
```
✓ **This is valid** - correct type (dict), all expected fields present, correct types

### Layer 2: Provider Layer (What Actually Failed)
```
runtime.llm_response_schema_valid: false  ← Provider's LLM response failed validation
generation_failure_reason: "RESPONSE_SCHEMA_MISMATCH"
attempted_models: ["gpt-5-mini", "gpt-4.1", "gpt-4o", "claude-sonnet-4.6"]
fallback_applied: false
```

**The Real Issue**: The Copilot API's LLM returned a response that didn't conform to the expected `grounding_summary` schema. The error response we see is the provider's fallback after all model attempts failed.

---

## Root Causes

### 1. **LLM Not Generating Proper grounding_summary**
The LLM is returning a response where `grounding_summary` is:
- `null` instead of a dict
- An array instead of a dict
- A dict with unexpected fields
- Missing the required fields

### 2. **Provider Schema Validation Too Strict**
The provider's schema validator may reject valid responses due to:
- Version mismatch between request/response specs
- Unexpected field presence causing rejection
- Type coercion not applied

### 3. **Provider Prompt Not Clear About grounding_summary Format**
The LLM prompt may not clearly specify:
```json
{
  "grounding_summary": {
    "used_context_ranks": [1, 2],  // Array of ranked context indices used
    "light_semantic_inference_used": true  // Boolean: was inference needed?
  }
}
```

---

## Diagnostic Evidence

### Analysis Output
```json
{
  "grounding_summary_present": true,
  "grounding_summary_type": "dict",
  "schema_valid": true,          ← Fallback response IS valid
  "issues": []
}
```

### Key Observation
- ✓ `grounding_summary_present: true`
- ✓ `schema_valid: true`
- **BUT** `llm_response_schema_valid: false` (in runtime)

This **proves** the issue is at the provider's LLM output validation stage, not the final response schema.

---

## How to Fix

### Option 1: Update LLM System Prompt (Recommended)
Make the LLM prompt explicit about `grounding_summary` format:

```python
# In Copilot API LLM prompt generation
system_prompt = """
You are a grounded QA assistant. Your response MUST include:
{
  "answer": "...",
  "citations": [...],
  "grounding_summary": {
    "used_context_ranks": [1, 2, 3],  // List of context rank indices (1-indexed)
    "light_semantic_inference_used": false  // Boolean: true if inference beyond context
  }
}

CRITICAL: grounding_summary MUST be a dict with exactly these fields:
- used_context_ranks: Array<number> - indices of context chunks used
- light_semantic_inference_used: Boolean - true if you inferred beyond provided context
"""
```

### Option 2: Add Response Normalization (Fallback)
If the LLM returns malformed `grounding_summary`, normalize it:

```python
def normalize_grounding_summary(raw_response):
    if not isinstance(raw_response.get("grounding_summary"), dict):
        # Fallback: create valid structure
        return {
            "used_context_ranks": [],
            "light_semantic_inference_used": False
        }
    return raw_response["grounding_summary"]
```

### Option 3: Relax Provider Schema Validation
If validation is too strict, update provider's response contract to accept:
- Extra fields (with warning but no failure)
- Slightly different field types (with coercion)
- Partial grounding_summary (fill missing fields with defaults)

---

## Verification Steps

### Step 1: Check Copilot API Logs
```bash
# Look for LLM response before schema validation
grep -i "grounding_summary" copilot-api.log | grep -A2 "llm.*response"
```
Expected to find what format the LLM actually returned.

### Step 2: Run Diagnostic with Debug
```bash
python src/diagnostics/grounded_qa_diagnostic.py \
  --query "Why are internet based clients important?" \
  --copilot-log-file /path/to/copilot-api.log
```

### Step 3: Inspect Generated Analysis
```json
// diagnostics/grounded_qa_runs/diag_*/grounding_summary_analysis.json
{
  "schema_valid": true,          // If false, check issues[]
  "issues": [],                  // Any field mismatches listed here
  "field_types": {...}           // Actual types received
}
```

---

## Implementation Checklist

- [ ] **Phase 1: Diagnosis**
  - [ ] Review Copilot API LLM prompt
  - [ ] Check what the LLM actually returns for `grounding_summary`
  - [ ] Look at Copilot logs for validation errors

- [ ] **Phase 2: Fix**
  - [ ] Update LLM system prompt with explicit `grounding_summary` format
  - [ ] Add response normalization function
  - [ ] OR relax provider schema validation with graceful fallback

- [ ] **Phase 3: Test**
  - [ ] Run diagnostic again: `grounded_qa_diagnostic.py`
  - [ ] Verify `llm_response_schema_valid: true`
  - [ ] Verify `grounding_summary_analysis.json` shows `schema_valid: true`
  - [ ] Check answer is generated (not empty)

- [ ] **Phase 4: Validate**
  - [ ] Test with multiple queries
  - [ ] Verify citations are properly extracted
  - [ ] Confirm grounding_summary reflects actual grounding behavior

---

## Files Involved

### Copilot API Components
- **File**: `copilot-api/python/...grounded_qa.py`  (LLM request/response handling)
- **Fix**: Update system prompt + add response normalization

### MarkItDown RAG Components
- **File**: `src/rag_pipeline/grounded_qa.py`  (RAG-side adapter)
- **Fix**: Enhance response contract to handle provider variations

### Diagnostic Tool
- **File**: `src/diagnostics/grounded_qa_diagnostic.py`  (Enhanced with grounding_summary analyzer)
- **Output**: `grounding_summary_analysis.json` (Schema validation report)

---

## Expected Behavior After Fix

### Diagnostic Output
```
result_status: success              (was: runtime_failure)
llm_response_schema_valid: true     (was: false)
answer: "Internet based clients..." (was: empty)
grounding_summary: {
  "used_context_ranks": [1],
  "light_semantic_inference_used": false
}
```

### Grounding Summary Analysis
```json
{
  "schema_valid": true,
  "issues": [],
  "debug_info": "✓ grounding_summary schema is valid"
}
```

---

## Questions to Answer

1. **What does the provider's LLM actually return for grounding_summary?**
   → Check Copilot API logs before schema validation

2. **Why is the schema validation failing?**
   → Could be null, wrong type, missing fields, or extra fields

3. **Is this a version mismatch?**
   → Check if provider and RAG use matching response contracts

4. **Can we make the LLM prompt more explicit?**
   → Add example JSON to system prompt showing exact expected format

---

## Next Steps

1. **Review Provider Logs**: Check what the LLM is actually returning
2. **Identify Exact Mismatch**: Use `grounding_summary_analysis.json` to see what's wrong
3. **Implement Fix**: Update prompt or add normalization
4. **Rerun Diagnostic**: Verify with `grounded_qa_diagnostic.py`
5. **Test End-to-End**: Ensure full query pipeline works

