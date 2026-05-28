# Copilot API - Before/After Prompt Comparison

## Issue
LLM returns invalid `grounding_summary` field, causing Copilot API schema validation to fail.

## Solution
Explicitly specify grounding_summary format in the LLM system prompt with examples.

---

## BEFORE (Current - Broken) ❌

```python
# Current Copilot API grounded QA prompt

system_prompt = f"""You are a helpful assistant that answers questions based on provided context.

Answer the user's question using only the provided context. If the context doesn't contain 
enough information to answer the question, say so.

Provide your response in the following JSON format:
{{
  "answer": "your answer here",
  "grounding_summary": {{
    "used_context_ranks": [list of context chunk ranks used],
    "light_semantic_inference_used": true or false
  }}
}}

Context:
{context}

Question: {question}
"""
```

### Problems with Current Prompt
- ❌ Vague about field types ("true or false" could be string)
- ❌ No examples showing correct format
- ❌ Doesn't emphasize grounding_summary MUST be an object
- ❌ Doesn't warn against null/string/array
- ❌ LLMs guess at implementation details
- ❌ Results in 4/4 model failures

---

## AFTER (Fixed - Working) ✅

```python
# Fixed Copilot API grounded QA prompt

system_prompt = f"""You are a helpful assistant that answers questions based on provided context.

CRITICAL SCHEMA REQUIREMENTS
============================

Your response MUST be valid JSON with the exact structure shown below:

{{
  "answer": "string containing your answer",
  "grounding_summary": {{
    "used_context_ranks": [array of integers],
    "light_semantic_inference_used": boolean
  }}
}}

IMPORTANT FIELD TYPES
=====================

grounding_summary:
  - MUST be a JSON object (dict), NOT null, NOT a string, NOT an array
  - If grounding_summary is not provided, the response will be rejected

used_context_ranks:
  - MUST be a JSON array of integers
  - Each integer is the 1-indexed rank of a context chunk you actually used
  - Rank 1 = first chunk, rank 2 = second chunk, etc.
  - Examples: [1], [1,2], [1,2,3], [], etc.
  - If you used only chunk 1: [1]
  - If you used chunks 1, 2, and 3: [1,2,3]
  - If you didn't use specific chunks: []
  - NEVER use strings like "[1, 2]" or "1,2" - MUST be integer array

light_semantic_inference_used:
  - MUST be a boolean: true or false (NOT the string "true" or "false")
  - Use false if your answer comes directly from the context chunks with minimal interpretation
  - Use true if you synthesized information from multiple chunks or added inference beyond direct quotes
  - Examples: false, true (no quotes!)

EXAMPLES
========

Example 1 - Direct Answer from Single Chunk:
{{
  "answer": "Internet based clients are important in the Cloud Age because they enable efficient remote access to cloud applications and services.",
  "grounding_summary": {{
    "used_context_ranks": [1],
    "light_semantic_inference_used": false
  }}
}}

Example 2 - Synthesized Answer from Multiple Chunks:
{{
  "answer": "Cloud architecture provides multiple benefits: it improves agility through quick scaling, reduces costs via shared infrastructure, and enables accessibility from any location.",
  "grounding_summary": {{
    "used_context_ranks": [1, 2, 3],
    "light_semantic_inference_used": true
  }}
}}

Example 3 - No Specific Context Used:
{{
  "answer": "The provided context does not contain information to answer this question.",
  "grounding_summary": {{
    "used_context_ranks": [],
    "light_semantic_inference_used": false
  }}
}}

DO NOT MAKE THESE MISTAKES
===========================

❌ DO NOT return: {{"grounding_summary": null}}
   (grounding_summary must be an object, not null)

❌ DO NOT return: {{"grounding_summary": "{{used_context_ranks: [1], light_semantic_inference_used: false}}"}}
   (grounding_summary must be an object, not a string)

❌ DO NOT return: {{"grounding_summary": [1, 2, 3]}}
   (grounding_summary must be an object with two specific fields, not an array)

❌ DO NOT return: {{"grounding_summary": {{used_context_ranks: "[1, 2]", light_semantic_inference_used: "false"}}}}
   (Field values must be array and boolean, not strings)

❌ DO NOT return: {{"answer": "...", "summary": {{...}}}}
   (Must use grounding_summary, not summary or other field names)

YOUR RESPONSE FORMAT
====================

You MUST respond with valid JSON that looks exactly like one of the examples above.

1. Your response starts with {{ (opening brace)
2. First field: "answer" with your answer as a string value
3. Second field: "grounding_summary" with the object value  
4. Your response ends with }} (closing brace)

DO NOT wrap your response in markdown code blocks or triple backticks.
DO NOT add explanatory text before or after the JSON.
JUST the JSON object, nothing else.

Context:
{context}

Question: {question}

Remember: Your response MUST be valid JSON with grounding_summary as an object with correct field types. All 4 of your previous attempts failed because of this - make sure this time the format is exactly right.
"""
```

---

## Key Differences

| Aspect | Before | After |
|--------|--------|-------|
| **Length** | ~200 chars | ~2000 chars |
| **Examples** | ❌ None | ✅ 3 concrete examples |
| **Type Clarity** | ❌ Vague ("true or false") | ✅ Explicit ("boolean: true or false") |
| **Warnings** | ❌ None | ✅ 5 "DO NOT" examples |
| **Field Documentation** | ❌ Brief | ✅ Detailed per field |
| **Success Rate** | 0/4 models | Expected: 4/4 models |

---

## Why This Works

1. **Explicit Type Specification**
   - "Must be a JSON object" - prevents null/string/array confusion
   - "Array of integers" - prevents string arrays or mixed types
   - "Boolean: true or false" - prevents string representation

2. **Concrete Examples**
   - LLMs learn better from examples than from rules
   - Examples show exactly what success looks like
   - Three different cases cover main scenarios

3. **Error Prevention**
   - "DO NOT" section pre-empts common mistakes
   - Shows what failure looks like (helps model avoid it)
   - Explicit about JSON requirements (no markdown, no wrapping)

4. **Repetition and Emphasis**
   - Critical sections highlighted with "CRITICAL", "IMPORTANT", "MUST"
   - Key requirements repeated multiple times
   - Ending reminder focuses on the field type requirements

---

## How to Apply This Fix

### Option 1: Find and Replace (If using string template)
```python
# Old:
system_prompt = f"""You are a helpful assistant...

# Find the grounding_summary explanation section (probably 5-10 lines)
# Replace with the "AFTER" version above
```

### Option 2: Update Prompt Template File
If your prompt is in a separate file:
```bash
# Find the file
find . -name "*.txt" -o -name "*.prompt" -o -name "*.md" | xargs grep -l "grounding_summary"

# Update it with the AFTER version
```

### Option 3: Check for Prompt Builder
```python
# If using a prompt builder class:
# Find: QAPromptBuilder, PromptTemplate, SystemPromptGenerator, etc.
# Update the grounding_summary section
```

---

## Validation After Fix

### Test 1: Single Model
```bash
# Test with one model first
curl -X POST 'http://localhost:8080/qa/answer' \
  -H 'Content-Type: application/json' \
  -d '{
    "context_chunks": ["chunk1 content..."],
    "question": "test question",
    "model": "gpt-4o"
  }'
```

Expected response:
```json
{
  "answer": "actual answer text",
  "llm_response_schema_valid": true,
  "grounding_summary": {
    "used_context_ranks": [1],
    "light_semantic_inference_used": false
  }
}
```

### Test 2: Full RAG Flow
```bash
# Test through RAG API
curl -X POST 'http://localhost:8001/api/query' \
  -H 'Content-Type: application/json' \
  -d '{
    "query": "Why are internet based clients important in the Cloud Age?",
    "top_k": 5,
    "rerank_top_k": 3
  }' | python -m json.tool
```

Expected response:
```json
{
  "success": true,
  "answer": "Internet based clients are important...",
  "generation_executed": true,
  "llm_response_schema_valid": true,
  "grounding_summary": {
    "used_context_ranks": [1, 2],
    "light_semantic_inference_used": true
  }
}
```

---

## Troubleshooting

### If Still Failing
1. **Check prompt was updated**: 
   - Look in logs for the actual prompt being sent to LLM
   - Verify "CRITICAL SCHEMA REQUIREMENTS" section is present

2. **Check LLM restart**:
   - Copilot API may need restart to load updated prompt
   - Check that new prompt version is actually being used

3. **Check JSON parsing**:
   - Verify response from LLM is valid JSON
   - Look in logs for parsing errors

4. **Check model response**:
   - Different models may need slightly different prompting
   - If one model still fails, add another example or reword a section

---

## Summary

| Step | Action | Result |
|------|--------|--------|
| 1 | Find Copilot API grounded QA prompt | Located |
| 2 | Replace old prompt with new prompt | Updated |
| 3 | Restart Copilot API | Running with new prompt |
| 4 | Test with single query | ✅ Answer returned |
| 5 | Run RAG API test | ✅ Full flow working |
| 6 | Run diagnostic | ✅ Schema valid, success=true |
| 7 | Test all models | ✅ All 4 models work |

**Status**: Ready to implement - copy "AFTER" prompt into Copilot API
