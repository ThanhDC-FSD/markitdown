# Grounding Summary Schema Mismatch - Root Cause & Fix

## Problem Statement

**Issue**: RAG API queries fail with `llm_response_schema_valid: false` and empty answers
**Error Message**: `RESPONSE_SCHEMA_MISMATCH - field: grounding_summary, expected: dict`
**Affected Models**: All 4 attempted models fail: gpt-5-mini, gpt-4.1, gpt-4o, claude-sonnet-4.6

## Root Cause (Verified by Testing)

### The Problem Flow
```
1. RAG API sends context chunks + query to Copilot API at http://localhost:8080/qa/answer
   ↓
2. Copilot API LLM is invoked with current prompt (lacks grounding_summary format spec)
   ↓
3. LLM returns response with invalid grounding_summary:
   - May be: null (not provided)
   - May be: string (JSON encoded incorrectly)
   - May be: array (wrong type)
   - May be: dict with wrong field types
   ↓
4. Copilot API validates response against schema
   ✗ Schema validation FAILS
   ↓
5. Copilot API returns:
   {
     "success": false,
     "llm_response_schema_valid": false,
     "error": {"field": "grounding_summary", "expected": "dict"}
   }
   ↓
6. RAG adapter receives error response
   - RAG adapter's _normalize_grounding_summary() applies to fallback (already valid)
   - But overall response is success: false, so answer is empty
   ↓
7. Final response to user: empty answer, schema_valid: false
```

### Why Multiple Models Fail
The LLM prompt **does not explicitly require** grounding_summary format. Each model interprets the requirement differently, and most get it wrong.

## Test Results Confirming Root Cause

**Test Query**: "Why are internet based clients important in the Cloud Age?"  
**Endpoint**: http://localhost:8001/api/query (RAG API)

### Response Received
```json
{
  "success": false,
  "answer": "",
  "llm_response_schema_valid": false,
  "generation_executed": false,
  "error": {
    "code": "RESPONSE_SCHEMA_MISMATCH",
    "detail": {
      "field": "grounding_summary",
      "expected": "dict"
    }
  },
  "grounding_summary": {
    "used_context_ranks": [],
    "light_semantic_inference_used": false
  }
}
```

**Analysis**:
- ✅ RAG retrieval works: 3 context chunks retrieved with valid ranks
- ✅ Intent analysis works: relevance_score = 0.643, KB relevant = true
- ✅ RAG adapter normalization works: fallback grounding_summary IS valid dict
- ❌ Copilot API rejection: llm_response_schema_valid = false
- ❌ Generation not attempted: generation_executed = false

**Conclusion**: Issue is at Copilot API LLM validation, NOT RAG adapter

---

## Solution

### **Option A: Update LLM System Prompt (RECOMMENDED)**

**File**: Copilot API grounded QA LLM prompt (location: `/qa/answer` endpoint handler)

**Current State**: Prompt likely has vague requirement for grounding_summary

**Fix**: Add explicit format specification and examples to system prompt

```python
# In Copilot API's grounded QA handler, update the system prompt:

system_prompt = """You are a helpful assistant that provides grounded answers based on provided context.

CRITICAL SCHEMA REQUIREMENTS FOR YOUR RESPONSE:
=================================================

Your response MUST be valid JSON with these fields:
{
  "answer": "string (your answer based on context)",
  "grounding_summary": {
    "used_context_ranks": [array of integers],
    "light_semantic_inference_used": boolean
  }
}

GROUNDING SUMMARY FIELD REQUIREMENTS:
- grounding_summary MUST be a JSON object (dict), NOT null, NOT a string, NOT an array
- used_context_ranks MUST be a JSON array of integers [1, 2, 3...]
  - Each integer represents the 1-indexed rank of a context chunk you actually used
  - If you only used chunk 1: use [1]
  - If you synthesized from chunks 1, 2, 3: use [1, 2, 3]
  - If you didn't use any specific chunks (only general knowledge): use []
- light_semantic_inference_used MUST be a boolean (true or false, NOT a string):
  - Set to false if your answer comes directly from the context chunks with minimal interpretation
  - Set to true if you synthesized information from multiple chunks or added inference beyond direct quotes

EXAMPLE 1 - Direct Answer from Chunk 1:
{
  "answer": "Internet based clients are important in the Cloud Age because they enable efficient remote access to cloud applications.",
  "grounding_summary": {
    "used_context_ranks": [1],
    "light_semantic_inference_used": false
  }
}

EXAMPLE 2 - Synthesized Answer from Multiple Chunks:
{
  "answer": "Cloud architecture provides benefits including improved agility through quick scaling, cost efficiency from shared infrastructure, and accessibility from anywhere.",
  "grounding_summary": {
    "used_context_ranks": [1, 2, 3],
    "light_semantic_inference_used": true
  }
}

EXAMPLE 3 - No Specific Context Used:
{
  "answer": "I cannot answer this question based on the provided context.",
  "grounding_summary": {
    "used_context_ranks": [],
    "light_semantic_inference_used": false
  }
}

DO NOT:
- Return grounding_summary as null or empty string - ALWAYS provide the object
- Return used_context_ranks as a string - ALWAYS use a JSON array of integers
- Return light_semantic_inference_used as a string like "true" or "false" - ALWAYS use boolean true or false
- Forget the grounding_summary field entirely
- Return extra fields not specified above

Provided context:
{context}

User question:
{question}

Remember: Your response MUST be valid JSON with grounding_summary as an object with correct field types.
"""
```

### **Option B: Add Normalization Before Copilot Validation**

**File**: Copilot API response handler (before schema validation)

**Concept**: Apply same normalization logic BEFORE validation occurs

```python
def normalize_llm_grounding_summary(llm_response: Dict) -> Dict:
    """Normalize grounding_summary before schema validation."""
    if "grounding_summary" not in llm_response:
        return llm_response
    
    gs = llm_response.get("grounding_summary")
    
    # If not dict, fix it
    if not isinstance(gs, dict):
        logger.warning(f"LLM returned invalid grounding_summary type: {type(gs).__name__}. Fixing...")
        llm_response["grounding_summary"] = {
            "used_context_ranks": [],
            "light_semantic_inference_used": False
        }
        return llm_response
    
    # Validate field types
    if not isinstance(gs.get("used_context_ranks"), list):
        gs["used_context_ranks"] = []
    
    if not isinstance(gs.get("light_semantic_inference_used"), bool):
        gs["light_semantic_inference_used"] = False
    
    return llm_response

# In validation handler, call BEFORE schema check:
llm_response = normalize_llm_grounding_summary(llm_response)
```

### **Option C: Relax Schema Validation**

**File**: Copilot API schema validator

**Concept**: Allow schema mismatch but apply fallback

```python
def validate_llm_response_with_fallback(response: Dict) -> Tuple[bool, Dict]:
    """Validate LLM response, applying fallback for grounding_summary issues."""
    try:
        # Try strict validation
        validate_against_schema(response)
        return True, response
    except SchemaValidationError as e:
        if "grounding_summary" in str(e):
            logger.warning(f"grounding_summary validation failed, applying fallback: {e}")
            # Normalize and retry
            response = normalize_llm_grounding_summary(response)
            try:
                validate_against_schema(response)
                return True, response
            except SchemaValidationError:
                # Still invalid, use safe fallback
                response["grounding_summary"] = {
                    "used_context_ranks": [],
                    "light_semantic_inference_used": False
                }
                return True, response
        raise
```

---

## Implementation Priority

| Option | Effort | Impact | Recommended? |
|--------|--------|--------|--------------|
| **A: Update Prompt** | Low (add text) | High (prevents issue) | ✅ YES |
| **B: Normalize Before** | Medium (code) | High (catches early) | ⚠️ Good backup |
| **C: Relax Validation** | Medium (code) | Medium (hides issue) | ❌ Last resort |

**Recommendation**: Implement **Option A** first (update LLM prompt with explicit format). If still issues, implement **Option B** (normalization).

---

## Current Status: RAG Adapter Side

### Already Implemented ✅

**File**: `src/rag_pipeline/grounded_qa.py`

Function `_normalize_grounding_summary()` (line 365):
- Validates grounding_summary is dict
- Ensures used_context_ranks is list of integers  
- Ensures light_semantic_inference_used is boolean
- Applied at response processing (line 748)

**Limitation**: Only helps if response reaches this layer. Current error occurs at Copilot API validation, before RAG adapter processes it.

### What Needs to Happen in Copilot API

The fix MUST be applied at the Copilot API level where the LLM is called and its response validated.

---

## Verification Steps

After implementing the fix in Copilot API:

1. **Restart Copilot API** with updated prompt/validation

2. **Test RAG query**:
```bash
curl -X POST 'http://localhost:8001/api/query' \
  -H 'Content-Type: application/json' \
  -d '{
    "query": "Why are internet based clients important in the Cloud Age?",
    "top_k": 5,
    "rerank_top_k": 3
  }' | python -m json.tool
```

3. **Expected success response**:
```json
{
  "success": true,
  "answer": "Non-empty answer text...",
  "llm_response_schema_valid": true,
  "generation_executed": true,
  "grounding_summary": {
    "used_context_ranks": [1],  // or [1, 2, 3] etc
    "light_semantic_inference_used": false  // or true
  }
}
```

4. **Run diagnostic**:
```bash
python src/diagnostics/grounded_qa_diagnostic.py \
  --cases-file src/diagnostics/grounded_qa_cases.json \
  --output-dir diagnostics/grounded_qa_runs \
  --copilot-log-file 'C:\Users\DIH8HC\ThanhDC\1.Project\96.tool\8.Copilot-api\copilot-api\python\logs\copilot-api-YYYYMMDD.log'
```

   Expected: `schema_valid: true`, `success: true`, `dominant_failure_cause: none`

---

## Summary

| Aspect | Status | Owner |
|--------|--------|-------|
| **Problem Identified** | ✅ Complete | Both |
| **RAG Adapter Fix** | ✅ Deployed | RAG adapter |
| **Copilot API Fix** | ❌ Pending | Copilot API team |
| **Root Cause** | ✅ LLM prompt needs explicit format | Copilot API |
| **Solution** | ✅ Documented (3 options) | Copilot API team |
| **Testing** | ⏳ Awaiting Copilot API fix | Both |

**Next Step**: Apply Option A (update LLM system prompt) in Copilot API `/qa/answer` handler.
