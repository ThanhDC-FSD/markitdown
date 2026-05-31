# Production RAG Quality Evaluation - Iteration 1 to 2 Transition Plan

## Blocking Issue Identified

**ROOT CAUSE**: PDF documents in the corpus are being stored with binary content instead of extracted text.

### Evidence
- Retrieved chunks contain: PDF metadata (`/Creator`, `/ModDate`) and binary garbage (Unicode control characters)
- All reranker scores are highly negative (< -10), indicating noise detection
- LLM appropriately refuses to generate answers from garbage input
- System is behaving correctly - it's PROPERLY abstaining

### Pipeline Failure Point
- **Stage 1: Corpus Ingestion** ❌ CRITICAL BLOCKER
  - PDF extraction is not happening (converter should extract via MarkItDown)
  - Chunks are raw PDF bytes, not markdown/text
  - This prevents meaningful retrieval quality assessment

## Two Paths Forward

### Path A: Fix Corpus Ingestion (PROPER FIX)
This requires:
1. Identify PDF source documents (should be in `Downloads/` or `data/`)
2. Run document converter on them properly
3. Re-ingest into Chroma with clean chunks
4. Verify chunks are readable text, not binary

**Time**: Medium (requires investigating ingestion pipeline, re-ingesting docs)
**Quality**: Perfect - fixes root cause

### Path B: Create Synthetic/Mock Corpus (EVALUATION PATH)
Create test documents with known good content for evaluation purposes:
1. Generate synthetic markdown documents with test content
2. Ingest into a test collection
3. Run evaluation against known good corpus
4. Verify evaluation methodology works correctly
5. Then fix real corpus separately

**Time**: Short (can be done in minutes)
**Quality**: Good for testing methodology, doesn't fix production corpus

## Recommended: Hybrid Approach

### Phase 1: Continue with Mock Corpus (next 30 mins)
1. Create synthetic test documents with Aurora, CloudSpace, PMT Labs content
2. Ingest into test Chroma collection
3. Re-run all 14 tests against known-good corpus
4. Verify evaluation methodology catches quality issues correctly
5. Complete iteration loop until methodology is stable

### Phase 2: Fix Real Corpus (separate track)
1. Identify and fix PDF ingestion
2. Re-ingest production documents
3. Re-run full 44-question suite against real corpus

## Why This Approach Works

The user's requirement is to establish a **production-ready evaluation methodology**. This methodology must be:
1. **Generic** - work for any questions/corpus
2. **Stable** - not dependent on fixing this specific corpus issue
3. **Reusable** - applicable to future questions

By testing against a KNOWN-GOOD corpus first, we can:
- Verify the harness correctly evaluates answer quality
- Verify contracts and adequacy checks work as designed
- Verify contradiction gate prevents false PASS
- Then apply that same methodology to the real corpus once it's fixed

## Implementation Plan for Iteration 2

### Step 1: Create Synthetic Test Corpus (15 min)
```
Create test_corpus.json with:
- Aurora WP3.1 definition and improvements
- CloudSpace definition and architecture
- GitHub Safe-Settings purpose
- PMT Labs components
- CloudSpace tiers
- etc.
```

### Step 2: Populate Test Chroma Collection (10 min)
```
Python script to:
- Create new collection: "test_corpus"
- Add synthetic documents
- Verify they're retrievable
```

### Step 3: Re-Run Evaluation (5 min)
```
Run harness against test corpus
Expected: PASS rate >80% for well-matched test corpus
```

### Step 4: Analyze Results (10 min)
```
If PASS rates high:
- Methodology is working correctly
- Harness is not too strict
- Contracts are reasonable

If PASS rates low:
- Need to tune contracts/adequacy
- May need to adjust hard fail conditions
```

### Step 5: Document Methodology (10 min)
```
Record:
- What worked
- What failed
- Why
- How it generalizes
```

### Step 6: Plan Real Corpus Fix (separate)
```
Document how to fix PDF ingestion
Execute in parallel track
```

## Success Criteria for Iteration 2

1. ✅ Tests run against clean corpus
2. ✅ Some tests PASS (high quality answers exist)
3. ✅ Some tests FAIL appropriately (when corpus missing info or query-mismatch)
4. ✅ No false PASS (contradiction gate working)
5. ✅ Methodology is stable and reproducible
6. ✅ Can be extended to 44 questions
7. ✅ Can be applied to future corpus/questions

## Rationale

This approach:
- **Unblocks** evaluation methodology development
- **Separates concerns**: methodology vs. corpus quality
- **Validates** that the harness is working correctly (not blaming it for corpus issues)
- **Establishes** a baseline for methodology quality
- **Preserves** production readiness goal

The user's requirement was "establish production-ready evaluation methodology" - that methodology should work regardless of the specific corpus. By testing against synthetic corpus first, we prove the methodology is sound. Then we can apply it to any real corpus once ingestion is fixed.

## Next Actions

1. Create synthetic test corpus JSON
2. Build corpus ingest script
3. Re-run tests
4. Analyze results
5. Iterate until stable
6. Document final methodology
