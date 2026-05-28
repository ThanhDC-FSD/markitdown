# Grounding Summary Schema Mismatch - Quick Fix Reference

## The Problem in 30 Seconds

Your Copilot API's LLM is returning a `grounding_summary` that doesn't match the expected schema.

**Evidence**:
```json
"runtime": {
  "llm_response_schema_valid": false,  ← LLM response FAILED validation
  "generation_failure_reason": "RESPONSE_SCHEMA_MISMATCH",
  "attempted_models": ["gpt-5-mini", "gpt-4.1", "gpt-4o", "claude-sonnet-4.6"]
}
```

The fallback response you see is valid, but it's hiding the real issue: **the LLM never generated a valid response**.

---

## What the LLM Should Return

```json
{
  "request_id": "...",
  "success": true,
  "answer": "Internet based clients are important because...",
  "citations": [
    {"rank": 1, "doc_id": "...", "chunk_index": ...}
  ],
  "grounding_summary": {
    "used_context_ranks": [1, 2],                    // Indices of context used
    "light_semantic_inference_used": false           // Did you infer beyond context?
  }
}
```

---

## The Fix

### Option 1: Update Copilot LLM System Prompt ⭐ RECOMMENDED
**File**: `copilot-api/python/src/...` (wherever LLM prompting happens)

**Change**:
```python
# Before (vague)
system_prompt = """Generate a grounded QA response with citations."""

# After (explicit)
system_prompt = """You are a grounded QA assistant.

Your JSON response MUST have this exact structure:
{
  "request_id": "...",
  "success": true,
  "answer": "Your answer here",
  "citations": [{"rank": 1, ...}, ...],
  "grounding_summary": {
    "used_context_ranks": [1, 2, 3],  // Numbers: which context chunks (1-indexed) did you use?
    "light_semantic_inference_used": false  // Boolean: true if you inferred beyond provided text
  }
}

CRITICAL SCHEMA REQUIREMENTS:
- grounding_summary: MUST be a dict (object), NOT null or array
- used_context_ranks: MUST be an array of integers [1, 2, 3]
- light_semantic_inference_used: MUST be a boolean true/false

Example:
If you used only the first context chunk with direct quotes:
{
  "used_context_ranks": [1],
  "light_semantic_inference_used": false
}

If you combined context chunks 1 and 2 and made logical inferences:
{
  "used_context_ranks": [1, 2],
  "light_semantic_inference_used": true
}
"""
```

### Option 2: Add Response Normalization
**File**: `src/rag_pipeline/grounded_qa.py` (RAG adapter)

**Change**:
```python
def normalize_provider_response(raw_response):
    """Normalize provider response to handle grounding_summary variations."""
    
    if not isinstance(raw_response.get("grounding_summary"), dict):
        # Provider returned invalid grounding_summary, normalize it
        raw_response["grounding_summary"] = {
            "used_context_ranks": [],
            "light_semantic_inference_used": False
        }
    
    gs = raw_response["grounding_summary"]
    
    # Ensure required fields exist with correct types
    if "used_context_ranks" not in gs:
        gs["used_context_ranks"] = []
    if "light_semantic_inference_used" not in gs:
        gs["light_semantic_inference_used"] = False
    
    # Type coercion
    if not isinstance(gs["used_context_ranks"], list):
        gs["used_context_ranks"] = list(gs["used_context_ranks"]) if gs["used_context_ranks"] else []
    
    if not isinstance(gs["light_semantic_inference_used"], bool):
        gs["light_semantic_inference_used"] = bool(gs["light_semantic_inference_used"])
    
    return raw_response
```

### Option 3: Relax Provider Schema Validation
**File**: `copilot-api/python/...` (response validator)

**Change**:
```python
# Before (strict)
def validate_response_schema(response):
    assert isinstance(response["grounding_summary"], dict), "grounding_summary must be dict"
    assert all(k in response["grounding_summary"] for k in [...]), "Missing fields"
    # Fails if any check fails

# After (lenient with fallback)
def validate_response_schema(response):
    if not isinstance(response.get("grounding_summary"), dict):
        # Log warning but don't fail - use fallback
        logger.warning("grounding_summary is not dict, using fallback")
        response["grounding_summary"] = {
            "used_context_ranks": [],
            "light_semantic_inference_used": False
        }
        return response
    
    # Soft validation with coercion
    gs = response["grounding_summary"]
    if "used_context_ranks" not in gs:
        gs["used_context_ranks"] = []
    if "light_semantic_inference_used" not in gs:
        gs["light_semantic_inference_used"] = False
    
    return response
```

---

## Test the Fix

### Before Fix
```bash
$ python src/diagnostics/grounded_qa_diagnostic.py ...

Output:
llm_response_schema_valid: false ❌
answer: ""
generation_failure_reason: "RESPONSE_SCHEMA_MISMATCH"
```

### After Fix
```bash
$ python src/diagnostics/grounded_qa_diagnostic.py ...

Output:
llm_response_schema_valid: true ✅
answer: "Internet based clients are important because..." ✅
grounding_summary: {
  "used_context_ranks": [1],
  "light_semantic_inference_used": false
}
```

---

## Why This Happened

The **LLM prompt** in the Copilot API likely doesn't clearly specify the `grounding_summary` format, so:
1. LLM generates response with missing/wrong `grounding_summary`
2. Provider's schema validator rejects it
3. Provider returns error response instead of answer
4. RAG pipeline sees error and returns empty answer

---

## Debugging Checklist

- [ ] Check Copilot API logs for actual LLM output BEFORE schema validation
- [ ] Look for what the LLM is returning for `grounding_summary` field
- [ ] Is it null? Array? Dict with wrong fields?
- [ ] Update system prompt with explicit format (Option 1)
- [ ] Or add normalization (Option 2)
- [ ] Rerun diagnostic to verify fix
- [ ] Check `grounding_summary_analysis.json` shows `schema_valid: true`

---

## Files to Check/Modify

1. **LLM System Prompt** (Copilot API)
   - Add explicit grounding_summary format
   - Include JSON schema example

2. **Response Validator** (Copilot API)
   - Relax strict validation OR
   - Add graceful fallback

3. **Response Adapter** (MarkItDown RAG)
   - Add normalization function
   - Handle provider variations

---

## The Schema Expected

```typescript
interface GroundingSummary {
  used_context_ranks: number[];        // [1], [1, 2], [1, 2, 3], etc.
  light_semantic_inference_used: boolean // true if inferred, false if direct
}
```

That's it. Two fields. Both required. No extras.

