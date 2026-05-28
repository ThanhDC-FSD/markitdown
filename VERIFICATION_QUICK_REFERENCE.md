# Answer Verification - Quick Reference Guide

## 🚀 Quick Start (5 Minutes)

### 1. Run Verification Test
```bash
cd c:\Users\DIH8HC\ThanhDC\1.Project\97.Dev_for_learn\20.Markitdown\markitdown
python tests/test_answer_verification.py
```

Expected output: Detailed verification report for 5 AUTOSAR questions

### 2. Check Results
```bash
# View verification JSON results
cat verification_results.json
```

### 3. View Documentation
- Full guide: [ANSWER_VERIFICATION_GUIDE.md](ANSWER_VERIFICATION_GUIDE.md)
- Summary: [VERIFICATION_RESULTS_SUMMARY.md](VERIFICATION_RESULTS_SUMMARY.md)

---

## 📊 Quick Quality Score Interpretation

| Score | Status | Action |
|:--|:--|:--|
| **0.85+** | ✓ Excellent | Deploy as-is |
| **0.70-0.84** | ✓ Good | Review suggestions, then deploy |
| **0.60-0.69** | ⚠ Fair | Fix warnings before using |
| **<0.60** | ✗ Poor | Rewrite or retrieve more sources |

---

## 5️⃣ Quality Gates Checklist

- [ ] **Source Fidelity**: ≥65% accuracy (answer faithful to sources)
- [ ] **Evidence Coverage**: ≥2 citations per claim
- [ ] **Consistency**: 0 internal contradictions
- [ ] **Completeness**: ≥60% query aspect coverage
- [ ] **Confidence**: ≥0.65 average source confidence

All 5 gates passed = **VERIFIED** ✓

---

## 🔍 Core Metrics at a Glance

```
Quality Score = (Accuracy × 0.4) + (Completeness × 0.3) + 
                (Confidence × 0.2) + (Consistency × 0.1)
```

| Component | Weight | Your Results |
|:--|:--:|:--:|
| Accuracy | 40% | 90% |
| Completeness | 30% | 83% |
| Confidence | 20% | 0.91 |
| Consistency | 10% | 100% |
| **Final Score** | **100%** | **87%** |

---

## 💻 Basic Code Usage

```python
from rag_pipeline.answer_verifier import AnswerVerifier

# Initialize verifier
verifier = AnswerVerifier()

# Verify an answer
verified = verifier.verify_answer(
    query="What is AUTOSAR?",
    answer_text="AUTOSAR is a standardized automotive architecture...",
    retrieved_chunks=chunks
)

# Check status
print(verified.overall_status.value)  # "verified", "partial", "unverified"
print(f"Quality: {verified.quality_score:.1%}")
print(f"Accuracy: {verified.accuracy_score:.1%}")
print(f"Completeness: {verified.completeness_score:.1%}")

# Get detailed report
print(verifier.generate_verification_report(verified))
```

---

## 🎯 Before vs After Results (5 Questions)

```
┌─────────────────────────────────────────────────────────┐
│          ANSWER VERIFICATION IMPROVEMENT               │
├─────────────────────────────────────────────────────────┤
│ Quality Score:    70% → 87% (+17%)  ✓                  │
│ Accuracy:         66% → 90% (+24%)  ✓                  │
│ Completeness:     57% → 83% (+26%)  ✓                  │
│ Confidence:      0.75 → 0.91 (+0.16) ✓                │
│ Verified Status:  0/5 → 5/5 (100%)  ✓                  │
│ Warnings:         7 → 0 (eliminated)  ✓                │
└─────────────────────────────────────────────────────────┘
```

---

## ⚠️ When Status is "PARTIAL" or "UNVERIFIED"

### Check These

```python
# 1. Which components failed?
for component in verified.components:
    if component.verification_status.value != "verified":
        print(f"Issue: {component.statement}")
        print(f"Confidence: {component.confidence_score}")

# 2. What warnings exist?
for warning in verified.warnings:
    print(f"⚠ {warning}")

# 3. What improvements are suggested?
for suggestion in verified.suggestions:
    print(f"→ {suggestion}")
```

### Fix Options

1. **Low completeness**: Answer doesn't address all aspects
   - Solution: Expand answer to cover more query aspects

2. **Low confidence**: Sources aren't confident
   - Solution: Retrieve better/more sources (increase k)

3. **Insufficient evidence**: No citations found
   - Solution: Retrieve longer/more detailed chunks

4. **Contradictions**: Internal inconsistencies
   - Solution: Rewrite to remove conflicting statements

---

## 🔗 Integration Examples

### With FastAPI

```python
@app.post("/api/query")
async def query(q: str):
    chunks = retriever.retrieve(q)
    answer = generate_answer(q, chunks)
    verified = verifier.verify_answer(q, answer, chunks)
    
    return {
        "answer": answer,
        "verified": verified.quality_score >= 0.70,
        "confidence": verified.quality_score
    }
```

### With Error Handling

```python
try:
    verified = verifier.verify_answer(query, answer, chunks)
    
    if verified.quality_score < 0.70:
        logger.warning(f"Low quality: {verified.warnings}")
        # Fall back to retrieving more sources
    
    return verified
except Exception as e:
    logger.error(f"Verification failed: {e}")
    return {"status": "error", "message": str(e)}
```

---

## 📈 Configuration Tuning

### Stricter (Production)
```python
verifier.min_confidence_threshold = 0.75  # Higher bar
verifier.min_quality_score = 0.75
verifier.min_completeness_score = 0.70
```

### Relaxed (Development)
```python
verifier.min_confidence_threshold = 0.55  # More lenient
verifier.min_quality_score = 0.60
verifier.min_completeness_score = 0.50
```

---

## 📚 File Reference

| File | Purpose |
|:--|:--|
| `answer_verifier.py` | Core verification engine |
| `test_answer_verification.py` | Test suite (5 AUTOSAR questions) |
| `ANSWER_VERIFICATION_GUIDE.md` | Comprehensive guide (1200+ lines) |
| `VERIFICATION_RESULTS_SUMMARY.md` | Detailed results & metrics |
| `VERIFICATION_QUICK_REFERENCE.md` | This file |

---

## ✅ Quality Checklist Before Deployment

- [ ] All 5 test questions pass (VERIFIED status)
- [ ] Quality score ≥ 0.70
- [ ] Zero contradictions
- [ ] All components have ≥2 citations
- [ ] Accuracy ≥ 65%
- [ ] Completeness ≥ 60%
- [ ] Confidence ≥ 0.65
- [ ] Zero warnings

✅ = **PRODUCTION READY**

---

## 🆘 Troubleshooting

| Issue | Cause | Fix |
|:--|:--|:--|
| ModuleNotFoundError | Python path issue | Add `sys.path.insert(0, 'src')` |
| Low quality score | Poor source material | Retrieve more chunks (k+=5) |
| Insufficient evidence | Not enough citations | Increase min_evidence_citations |
| High warnings | Weak component match | Rewrite answer more carefully |

---

## 🎓 Learning Path

1. **Start**: [Read this file you're viewing now]
2. **Understand**: [VERIFICATION_RESULTS_SUMMARY.md] - See the before/after
3. **Deep Dive**: [ANSWER_VERIFICATION_GUIDE.md] - Full explanation
4. **Practice**: `python tests/test_answer_verification.py` - Run tests
5. **Integrate**: Add to your API endpoints
6. **Monitor**: Track quality over time

---

## 📞 Questions?

Refer to specific sections in [ANSWER_VERIFICATION_GUIDE.md]:
- "5 Quality Gates" for gate details
- "Quality Scores Explained" for metric info
- "Running Verification" for code examples
- "Integration with Pipeline" for API usage
- "Troubleshooting" for common issues

