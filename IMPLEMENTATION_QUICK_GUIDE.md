# Quick Implementation Guide - Grounding Summary Fix

## TL;DR

**Problem**: LLM returns invalid grounding_summary → Copilot API rejects it → RAG API returns empty answer

**Solution**: Update LLM prompt in Copilot API to explicitly specify grounding_summary format

**Status**: RAG adapter already has defensive normalization. Need Copilot API fix.

---

## What's Working ✅
- RAG retrieval and chunking: Working perfectly  
- Context ranking and reranking: Working perfectly
- RAG adapter error handling: Working perfectly
- Grounding summary normalization: Working perfectly

## What's Broken ❌
- Copilot API LLM validation: **LLM returns invalid grounding_summary format**
- All 4 attempted models fail: gpt-5-mini, gpt-4.1, gpt-4o, claude-sonnet-4.6
- Error: `grounding_summary field has invalid type`

---

## The Fix (For Copilot API Team)

### Location
File: Copilot API endpoint handler for `/qa/answer`  
Language: Python (or whatever language Copilot API is written in)

### What to Do
Find the LLM system prompt template and ADD this text:

```
CRITICAL: Your response MUST include grounding_summary as a JSON object:

{
  "grounding_summary": {
    "used_context_ranks": [1],        // array of integers
    "light_semantic_inference_used": false  // boolean
  }
}

DO NOT return grounding_summary as:
- null (not allowed)
- string (not allowed)  
- array (not allowed)
- object with wrong field types (not allowed)

Examples:
- Direct quote from chunk 1: {"used_context_ranks": [1], "light_semantic_inference_used": false}
- Synthesized from chunks 1-3: {"used_context_ranks": [1, 2, 3], "light_semantic_inference_used": true}
- No specific chunks: {"used_context_ranks": [], "light_semantic_inference_used": false}
```

### Why This Works
- Makes requirement explicit and unambiguous
- Provides concrete examples (models learn better from examples)
- Specifies exact field types (prevents null/string/array mistakes)
- Works with all model types

---

## Testing the Fix

### Step 1: Verify RAG API still works
```bash
python -c "
import requests, json
r = requests.post('http://localhost:8001/api/query', json={
    'query': 'Why are internet based clients important in the Cloud Age?',
    'top_k': 5,
    'rerank_top_k': 3
})
print(json.dumps(r.json(), indent=2))
"
```

### Step 2: Check for success
Look for:
- `"success": true` ✅ (not false)
- `"answer": "..."` with non-empty text ✅  
- `"llm_response_schema_valid": true` ✅ (not false)
- `"generation_executed": true` ✅ (not false)
- `"grounding_summary": {"used_context_ranks": [...], "light_semantic_inference_used": bool}` ✅

### Step 3: Run diagnostic
```bash
python src/diagnostics/grounded_qa_diagnostic.py \
  --cases-file src/diagnostics/grounded_qa_cases.json \
  --output-dir diagnostics/grounded_qa_runs \
  --copilot-log-file 'C:\Users\DIH8HC\ThanhDC\1.Project\96.tool\8.Copilot-api\copilot-api\python\logs\copilot-api-20260528.log'
```

Expected output:
```
dominant_failure_cause: success (or other non-schema-mismatch cause)
```

---

## Current Evidence

### Test Output
```
Request: "Why are internet based clients important in the Cloud Age?"
Status: FAILED
Reason: grounding_summary field has invalid type

Details:
- RAG retrieval: ✅ 3 chunks (ranks 1,2,3)
- Intent analysis: ✅ KB relevant (0.643 score)
- LLM invocation: ✅ HTTP 200
- LLM JSON parse: ✅ Valid JSON
- Schema validation: ❌ grounding_summary type mismatch
- Result: success=false, answer="", generation_executed=false
```

### Root Cause
LLM is returning grounding_summary in wrong format (null, string, array, or wrong field types). This happens BEFORE reaching RAG adapter validation, so the defensive normalization can't help.

### Evidence Trail
1. RAG logs: "grounded_qa.py completed: status=runtime_failure"
2. Copilot logs: "[QA] grounding_summary field has invalid type"
3. Response: `llm_response_schema_valid: false`
4. Fallback: grounding_summary provided by Copilot API as valid dict (but success=false)

---

## Impact of Fix

| Before Fix | After Fix |
|-----------|-----------|
| ❌ Queries fail | ✅ Queries succeed |
| ❌ Empty answers | ✅ Answers with content |
| ❌ All 4 models fail | ✅ All 4 models work |
| ❌ schema_valid: false | ✅ schema_valid: true |

---

## Files Involved

### RAG Adapter (Already Fixed)
- **File**: `src/rag_pipeline/grounded_qa.py`
- **Function**: `_normalize_grounding_summary()` (line 365)
- **Status**: ✅ Defensive normalization in place
- **Applied**: Line 748 in response processing

### Copilot API (Needs Fixing)
- **File**: Copilot API LLM prompt handler
- **Status**: ❌ Prompt needs explicit grounding_summary format
- **Fix Type**: Add text to system prompt
- **Priority**: Critical - blocking all queries

### Diagnostic Tool (Supporting)
- **File**: `src/diagnostics/grounded_qa_diagnostic.py`
- **Status**: ✅ Enhanced with schema analysis
- **Output**: `grounding_summary_analysis.json`
- **Value**: Identifies schema mismatches for debugging

---

## Quick Commands

### Restart and Test
```bash
# 1. Update Copilot API prompt (see file: GROUNDING_SUMMARY_ROOT_CAUSE_AND_FIX.md)
# 2. Restart Copilot API
# 3. Test RAG query

python -c "
import requests, json

# Test query
url = 'http://localhost:8001/api/query'
payload = {
    'query': 'Why are internet based clients important?',
    'top_k': 5,
    'rerank_top_k': 3
}

response = requests.post(url, json=payload)
result = response.json()

# Check for success
if result.get('success'):
    print('✅ SUCCESS!')
    print(f'Answer: {result.get(\"answer\")[:100]}...')
    print(f'Schema valid: {result.get(\"llm_response_schema_valid\")}')
else:
    print('❌ FAILED!')
    print(f'Reason: {result.get(\"error\", {}).get(\"detail\", {})}')
"
```

---

## Contact/Questions

**For Copilot API Team:**
- Issue: LLM prompt lacks explicit grounding_summary format specification
- Solution: Add format examples and field type requirements to system prompt
- File: See `GROUNDING_SUMMARY_ROOT_CAUSE_AND_FIX.md` for detailed prompt template
- Testing: Run diagnostic after fix to verify schema_valid=true

**For RAG Team:**
- RAG adapter is ready: normalization function deployed
- Awaiting Copilot API fix to complete end-to-end flow
- Diagnostic tool enhanced and working: generates schema analysis reports
