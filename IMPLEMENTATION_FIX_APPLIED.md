# Grounding Summary Fix Implementation - Applied

## What Was Done ✅

### 1. Enhanced RAG Pipeline Response Handler
**File**: `src/rag_pipeline/grounded_qa.py`

**Added Function**:
```python
def _normalize_grounding_summary(grounding_summary: Any) -> Dict[str, Any]:
    """Ensure grounding_summary is a valid dict with required fields."""
```

**Key Features**:
- Validates input is a dict (if not, creates valid fallback)
- Validates `used_context_ranks` is a list of integers
- Validates `light_semantic_inference_used` is a boolean
- Logs warnings for invalid inputs
- Returns properly formed dict: `{"used_context_ranks": [...], "light_semantic_inference_used": false}`

**Integration**: Called at line 748 during response processing:
```python
grounding_summary = _normalize_grounding_summary(response_data.get("grounding_summary"))
```

**Result**: Even if the LLM returns malformed grounding_summary, the RAG pipeline will normalize it before processing

---

## Current Status 🔍

### Issue Still Present
The diagnostic shows the error is happening **INSIDE the Copilot API** before responses reach the RAG adapter:

```
2026-05-28 12:18:21 - copilot-api - ERROR - [QA] grounding_summary field has invalid type
```

Timeline:
1. ✅ LLM generates response with malformed grounding_summary
2. ✅ Copilot API validates response schema
3. ❌ **FAILS** at: "grounding_summary field has invalid type"
4. ❌ Creates error response with fallback grounding_summary
5. ✅ RAG adapter receives response

**Where the problem occurs**: Copilot API response validation layer, not in RAG adapter

---

## Why RAG Normalization Alone Isn't Enough

The Copilot API has **TWO validation points**:

```
LLM Output
    ↓
[Copilot API] Validate grounding_summary schema  ← FAILS HERE
    ↓
Error Response with Fallback
    ↓
RAG Adapter (our normalization) ← Would help here, but too late
```

The error happens before we get to apply our normalization.

---

## What Still Needs Fixing 🔧

### Root Cause: Copilot API LLM Response Validation

The Copilot API code needs to:

1. **Option A (Recommended)**: Update LLM system prompt to explicitly require valid grounding_summary
   - File: `copilot-api/python/.../grounded_qa.py` or similar
   - Add format specification with examples
   - Include field type requirements

2. **Option B**: Add normalization in Copilot API BEFORE validation
   - File: Copilot API response handler
   - Normalize grounding_summary before schema validation
   - Use same normalization approach as we added to RAG adapter

3. **Option C**: Relax validation with graceful fallback
   - File: Copilot API schema validator
   - Allow schema mismatch but log warning
   - Use fallback instead of error

---

## Evidence from Logs

### Copilot API Error Log
```
[QA] grounding_summary field has invalid type for request_id=...
```

### Response Data Shows Issue
- HTTP 200 from Copilot API ✅
- Response JSON valid ✅
- `llm_response_schema_valid: false` ❌ (LLM response failed validation)
- `attempted_models: [4 different models]` (All failed)
- Fallback response created with valid grounding_summary (defensive)

### Diagnostic Output
```
llm_response_schema_valid: false
generation_failure_reason: RESPONSE_SCHEMA_MISMATCH
answer_extraction_success: false
generation_executed: false
```

---

## Implementation Path Forward

### Step 1: Locate Copilot API Code
```
Path: C:\Users\DIH8HC\ThanhDC\1.Project\96.tool\8.Copilot-api\copilot-api\python\
Look for: grounded_qa.py or similar
Find: Response validation, schema check, or normalization code
```

### Step 2: Find Where Error Is Generated
Search for: `"grounding_summary field has invalid type"` in Copilot API logs
This is the exact error message being logged

### Step 3: Apply One of Three Fixes

#### Fix A: Update LLM Prompt (RECOMMENDED)
```python
system_prompt = """
You MUST include grounding_summary in your response as a JSON object:

{
  "grounding_summary": {
    "used_context_ranks": [1, 2, 3],  // List of integers
    "light_semantic_inference_used": false  // Boolean
  }
}

CRITICAL: grounding_summary is NOT optional and MUST be a dict (object).
DO NOT return null, string, array, or any other type.
"""
```

#### Fix B: Add Normalization Before Validation
```python
def normalize_response_before_validation(response):
    gs = response.get("grounding_summary")
    if not isinstance(gs, dict):
        # Log and create valid structure
        response["grounding_summary"] = {
            "used_context_ranks": [],
            "light_semantic_inference_used": False
        }
    return response

# Then validate
response = normalize_response_before_validation(response)
validated = validate_schema(response)
```

#### Fix C: Relax Validation
```python
try:
    validate_schema_strict(response)
except SchemaValidationError as e:
    if "grounding_summary" in str(e):
        logger.warning(f"Schema mismatch in grounding_summary: {e}. Using fallback.")
        response["grounding_summary"] = {"used_context_ranks": [], "light_semantic_inference_used": False}
    else:
        raise
```

---

## Testing the Fix

After applying Copilot API fix, run diagnostic:

```bash
python src/diagnostics/grounded_qa_diagnostic.py \
  --cases-file src/diagnostics/grounded_qa_cases.json \
  --output-dir diagnostics\grounded_qa_runs \
  --copilot-log-file 'C:\Users\DIH8HC\ThanhDC\1.Project\96.tool\8.Copilot-api\copilot-api\python\logs\copilot-api-20260528.log'
```

**Success criteria**:
- ✅ `llm_response_schema_valid: true` (was: false)
- ✅ `answer` is not empty (was: empty string)
- ✅ `generation_executed: true` (was: false)
- ✅ `success: true` (was: false)
- ✅ Diagnostic shows no errors

---

## Summary

### What's Done
- ✅ Enhanced RAG pipeline with defensive grounding_summary normalization
- ✅ Added comprehensive schema validation to diagnostic tool
- ✅ Identified root cause: Copilot API LLM validation

### What's Left
- ⏳ Fix Copilot API LLM prompt or response handler
- ⏳ Rerun diagnostic to verify fix
- ⏳ End-to-end testing with multiple queries

### Files Modified
- `src/rag_pipeline/grounded_qa.py` (+50 lines, added normalization function)

### Files NOT Modified (Require Copilot API Access)
- `copilot-api/python/.../grounded_qa.py` (need to apply Option A, B, or C)

---

## Quick Reference

| Issue | Evidence | Solution |
|-------|----------|----------|
| LLM returns invalid grounding_summary | `[QA] grounding_summary field has invalid type` | Update LLM prompt |
| grounding_summary is null/string/array | `llm_response_schema_valid: false` | Normalize before validation |
| Validation fails on schema mismatch | All 4 models fail | Relax validation with fallback |

---

## Next Steps

1. **Access Copilot API code** in `copilot-api/python/`
2. **Search** for "grounding_summary" validation
3. **Apply one fix** (Option A recommended)
4. **Restart Copilot API server**
5. **Run diagnostic** to verify
6. **Test** end-to-end queries

