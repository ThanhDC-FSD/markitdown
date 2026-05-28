# Quality Gates Usage Guide

## Overview

This guide explains how to use the quality gate system for evaluating and improving RAG pipeline answers.

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                                                              │
│  1. LOAD TEST CASES                                          │
│     └─ evaluation_test_cases.json                           │
│        (Domain, keywords, expected answers, thresholds)      │
│                                                              │
│  2. RUN QUERY THROUGH RAG PIPELINE                          │
│     └─ /api/query endpoint                                  │
│        (Query → Retrieve → Rerank → Generate)               │
│                                                              │
│  3. VERIFY GENERATED ANSWER                                 │
│     ├─ Domain Gate (stay in correct domain)                │
│     ├─ Hallucination Gate (no forbidden topics)             │
│     ├─ Grounding Gate (supported by context)                │
│     ├─ Expectation Gate (covers expected points)            │
│     └─ Retrieval Gate (top chunks are relevant)             │
│                                                              │
│  4. CALCULATE QUALITY SCORES                                │
│     ├─ domain_consistency_score (0-1)                       │
│     ├─ hallucination_risk_score (0-1, lower=better)        │
│     ├─ grounding_score (0-1)                                │
│     ├─ expectation_coverage_score (0-1)                     │
│     └─ final_quality_score (weighted average)               │
│                                                              │
│  5. DETECT FAILURE PATTERNS                                 │
│     └─ Analyze which gate(s) failed                         │
│                                                              │
│  6. REFINE SYSTEM PROMPT                                    │
│     └─ Generate specialized prompt addressing failures      │
│                                                              │
│  7. ITERATE                                                 │
│     └─ Re-run all test cases with refined prompt            │
│        Stop when converged or max_iterations reached        │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

## Quick Start

### 1. Define Test Cases

Create `evaluation_test_cases.json`:

```json
{
  "test_cases": [
    {
      "test_case_id": "my_test_001",
      "query": "What is the expected question?",
      "expected_domain": "DomainName",
      "expected_answer_points": [
        "Key fact 1",
        "Key fact 2"
      ],
      "required_keywords": [
        "keyword1",
        "keyword2"
      ],
      "optional_keywords": [
        "keyword3"
      ],
      "forbidden_topics": [
        "UnrelatedDomain",
        "WrongProduct"
      ],
      "minimum_grounding_score": 0.80,
      "minimum_semantic_coverage": 0.75,
      "maximum_hallucination_risk": 0.20,
      "notes": "Optional notes"
    }
  ]
}
```

### 2. Run Evaluation

```bash
cd src
python evaluation_runner.py
```

### 3. Review Results

- **Human-readable**: Summary printed to console
- **Machine-readable**: `evaluation_report_final.json`

---

## Test Case Design

### Anatomy of a Test Case

```python
{
    # Identification
    "test_case_id": "unique_identifier",
    
    # The Question
    "query": "What is the user asking?",
    
    # Domain Constraints
    "expected_domain": "DomainName",
    "forbidden_topics": ["WrongDomain1", "WrongDomain2"],
    
    # Expected Answer Content
    "expected_answer_points": [
        "Must-include fact 1",
        "Must-include fact 2"
    ],
    
    # Keyword Requirements
    "required_keywords": ["key1", "key2"],      # Must appear
    "optional_keywords": ["key3", "key4"],      # Nice to have
    
    # Quality Thresholds
    "minimum_grounding_score": 0.80,            # How supported by context
    "minimum_semantic_coverage": 0.75,          # How well expected points covered
    "maximum_hallucination_risk": 0.20,         # How many forbidden topics allowed
    
    # Documentation
    "notes": "Why this test is important..."
}
```

### Example: CloudSpace Test

```json
{
  "test_case_id": "cloudspace_dedicated_001",
  "query": "Why choose dedicated CloudSpace over shared?",
  "expected_domain": "CloudSpace",
  "expected_answer_points": [
    "Dedicated is for high-demand environments",
    "Shared requires quota/limit sharing",
    "Dedicated avoids shared limits"
  ],
  "required_keywords": ["dedicated", "shared", "limits"],
  "optional_keywords": ["high-demand", "subscription"],
  "forbidden_topics": ["github", "repositories", "version control"],
  "minimum_grounding_score": 0.80,
  "minimum_semantic_coverage": 0.75,
  "maximum_hallucination_risk": 0.20,
  "notes": "Critical: Fail if answer drifts to GitHub domain"
}
```

---

## Quality Gate Criteria

### 1. Domain Gate ✓
```
PASS if:
- Answer stays in expected domain
- No forbidden topics detected
- Retrieved chunks match expected domain

FAIL if:
- Answer drifts to different product/domain
- Forbidden topics present in answer
- Domain mismatch between query and answer
```

### 2. Hallucination Gate ✓
```
PASS if:
- Hallucination risk score < 0.20
- No forbidden topics found
- No generic boilerplate phrases

FAIL if:
- Forbidden topic keywords in answer
- Generic phrases like "appears to be", "based on context about"
- Multiple forbidden topics detected
```

### 3. Grounding Gate ✓
```
PASS if:
- Grounding score >= threshold (default 0.80)
- At least 80% of answer is supported by context
- No unsupported facts

FAIL if:
- Grounding score < 0.80
- Many unsupported claims
- Answer contains facts not in retrieved chunks
```

### 4. Expectation Gate ✓
```
PASS if:
- Semantic coverage >= threshold (default 0.75)
- At least 75% of expected points covered
- Required keywords present

FAIL if:
- Missing core expected facts
- Required keywords absent
- Incomplete answer
```

### 5. Retrieval Gate ✓
```
PASS if:
- Top chunk score >= threshold (default 0.80)
- Relevant documents retrieved
- Cross-encoder score acceptable

FAIL if:
- Top chunks not relevant
- Low similarity scores
- No related context found
```

---

## Quality Scores Explained

```python
{
    # Individual Gate Scores (0.0-1.0)
    "retrieval_score": 0.85,
    "domain_consistency_score": 0.95,
    "hallucination_risk_score": 0.05,  # Lower is better
    "grounding_score": 0.70,
    "expectation_coverage_score": 0.85,
    
    # Pass/Fail Flags
    "retrieval_pass": True,
    "domain_pass": True,
    "hallucination_pass": True,
    "grounding_pass": False,            # Grounding < 0.80
    "expectation_pass": True,
    "generation_pass": False,           # Grounding OR expectation failed
    "overall_pass": False,              # Any gate failed
    
    # Final Quality Score (Weighted Average)
    "final_quality_score": 0.84,        # (0.85 + 0.95 + 0.95 + 0.70 + 0.85) / 5
}
```

---

## Prompt Refinement Loop

### How It Works

```
Iteration 0:
  ├─ Run tests with base prompt
  ├─ Detect failures: domain_drift, generic_answers
  ├─ Analyze: "2 out of 3 tests have domain drift"
  └─ Action: Strengthen domain consistency prompt

Iteration 1:
  ├─ Run tests with refined prompt
  ├─ Compare: Pass rate improved? Yes: 0% → 50%
  ├─ Detect: Remaining failures: grounding
  └─ Action: Strengthen grounding requirements

Iteration 2:
  ├─ Run tests with further refined prompt
  ├─ Compare: Pass rate improved? No improvement
  ├─ Decision: Stop (no improvement for 2 iterations)
  └─ Result: Final prompt is "best effort"
```

### Prompt Templates

The engine has specialized prompts for different failure types:

1. **Domain Consistency Prompt**
   - Emphasizes: Stay in the same domain
   - Detects: Topic switching (GitHub ↔ CloudSpace)
   - Used when: Domain drift failures detected

2. **Grounding Prompt**
   - Emphasizes: Answer only from context
   - Detects: Hallucinations, unsupported facts
   - Used when: Grounding failures detected

3. **Specificity Prompt**
   - Emphasizes: No generic boilerplate
   - Detects: "This appears to be...", "Based on context..."
   - Used when: Generic answer patterns found

4. **Expectation Coverage Prompt**
   - Emphasizes: Complete answers with all key facts
   - Detects: Incomplete coverage of expected points
   - Used when: Expectation coverage failures detected

---

## Integration with API

### Using Refined Prompts

The API automatically uses the latest refined prompt:

```python
# In api.py query endpoint:
system_prompt = prompt_engine.get_current_prompt()
answer = llm_caller.call(
    query=request.query,
    context=context_text,
    system_prompt=system_prompt  # ← Uses refined prompt
)
```

### Accessing Quality Scores

The API doesn't currently return quality scores, but you can:

1. **Use the evaluation runner** for periodic quality checks:
   ```bash
   python evaluation_runner.py
   ```

2. **Call the verifier directly**:
   ```python
   from answer_verifier import AnswerVerifier
   
   verifier = AnswerVerifier()
   result = verifier.verify_answer(
       test_case=test_case,
       query=query,
       generated_answer=answer,
       retrieved_chunks=chunks
   )
   
   print(f"Quality: {result.final_quality_score}")
   print(f"Domain: {result.domain_pass}")
   print(f"Hallucination Risk: {result.hallucination_risk_score}")
   ```

---

## Common Issues & Solutions

### Issue: Tests pass but quality score low

**Cause**: Strict thresholds set too high

**Solution**: Adjust thresholds in test case:
```json
{
    "minimum_grounding_score": 0.70,        // Lower from 0.80
    "minimum_semantic_coverage": 0.60,      // Lower from 0.75
    "maximum_hallucination_risk": 0.30      // Higher from 0.20
}
```

### Issue: Grounding always fails for correct answers

**Cause**: Simple word-matching is too strict

**Solution**: Replace word-matching with semantic similarity:
```python
# In answer_verifier.py, _check_grounding():
# Instead of: if matched >= len(words) * 0.5:
# Use: if semantic_similarity(sentence, context) > 0.7:
```

### Issue: Domain gate passes but answer is still off-topic

**Cause**: Forbidden topics not comprehensive enough

**Solution**: Add more forbidden topics:
```json
{
    "forbidden_topics": [
        "github", "repositories",
        "git", "branches", "pull requests",
        "version control", "commits"
    ]
}
```

### Issue: Prompt refinement stops too early

**Cause**: No improvement threshold reached quickly

**Solution**: Adjust runner settings:
```python
runner = EvaluationRunner(
    test_cases_file="evaluation_test_cases.json",
    max_iterations=10,              // More iterations
    improvement_threshold=0.02,     // Lower threshold
)
```

---

## Production Deployment

### Step 1: Prepare Test Suite

Create comprehensive test cases covering:
- Different domains
- Edge cases
- Common failure modes
- Multi-turn scenarios (future)

### Step 2: Establish Baselines

Run evaluation against initial prompt:
```bash
python evaluation_runner.py
# Record: initial_pass_rate, average_quality, critical_failures
```

### Step 3: Deploy Enhanced Pipeline

1. Use refined prompt in API
2. Monitor quality metrics
3. Periodically re-evaluate

### Step 4: Continuous Improvement

Schedule automatic evaluation:
```bash
# Cron job (runs daily)
0 2 * * * cd /path/to/project && python evaluation_runner.py
```

Track metrics over time and alert if quality degrades.

---

## Extending the System

### Add New Test Case

```json
{
  "test_case_id": "new_domain_test_001",
  "query": "New question about new domain",
  "expected_domain": "NewDomain",
  "expected_answer_points": ["Fact1", "Fact2"],
  "required_keywords": ["key1"],
  "forbidden_topics": ["OtherDomain"],
  "minimum_grounding_score": 0.75,
  "minimum_semantic_coverage": 0.70,
  "maximum_hallucination_risk": 0.25,
  "notes": "Test description"
}
```

### Add New Quality Gate

```python
# In answer_verifier.py, add method:
def _check_custom_gate(self, answer, context, threshold):
    """Custom gate for specific requirements."""
    # Your logic here
    pass

# In verify_answer(), call:
custom_pass, custom_score = self._check_custom_gate(...)
overall_pass = overall_pass and custom_pass
```

### Add New Prompt Template

```python
# In prompt_refinement.py:
def _refine_for_custom_requirement(self, patterns):
    """Prompt for specific failure pattern."""
    return """
    Your specialized prompt here...
    """

# In refine_prompt(), detect and use:
elif patterns["custom_failure"] > 0:
    refined_prompt = self._refine_for_custom_requirement(patterns)
```

---

## FAQ

**Q: How strict should thresholds be?**  
A: Start at 0.80 for production. Relax to 0.70 if too many false negatives. Never go below 0.50.

**Q: Should I use all quality gates?**  
A: Yes, initially. Then disable gates that consistently pass (domain gate usually passes).

**Q: How many test cases do I need?**  
A: At least 2-3 per domain/query type. Aim for 20+ in production.

**Q: Can I use this with OpenAI/Claude?**  
A: Yes! Replace mock LLM with actual API endpoint. The quality gates work with any LLM.

**Q: How often should I refine prompts?**  
A: Run evaluation daily. Refine prompt weekly or when quality drops.

---

## References

- `answer_verifier.py` - Quality gate implementation
- `prompt_refinement.py` - Prompt refinement engine
- `evaluation_runner.py` - Test orchestration
- `evaluation_test_cases.json` - Test case format
- `evaluation_report_final.json` - Result format

---

Generated: 2026-05-27  
Version: 1.0  
Status: Production Ready
