# API TESTING QUICK REFERENCE

## Setup
- **API URL**: http://localhost:8001
- **Swagger UI**: http://localhost:8001/docs (recommended for testing)
- **Port**: 8001 (make sure start.bat or start.sh has finished)

## 5 Quick Test Queries

### After ingesting machine_learning_basics.md:
```json
{"query": "What is machine learning?", "top_k": 5, "rerank_top_k": 3}
{"query": "What are the types of machine learning?", "top_k": 5, "rerank_top_k": 3}
```

### After ingesting deep_learning_guide.md:
```json
{"query": "What is deep learning?", "top_k": 5, "rerank_top_k": 3}
{"query": "What are neural networks?", "top_k": 5, "rerank_top_k": 3}
```

### After ingesting nlp_fundamentals.md:
```json
{"query": "What is natural language processing?", "top_k": 5, "rerank_top_k": 3}
```

## Test Endpoints in Order

| # | Endpoint | Method | Body | Purpose |
|---|----------|--------|------|---------|
| 1 | `/` | GET | - | Verify API running |
| 2 | `/api/status` | GET | - | Check KB (should be 0 docs) |
| 3 | `/api/ingest` | POST | See below | Add first document |
| 4 | `/api/query` | POST | See queries above | Test queries |
| 5 | `/api/ingest-batch` | POST | Select files in UI | Batch upload 3 files |

### POST /api/ingest Body Examples:

**File 1:**
```json
{"source_type": "file", "source": "./sample_docs/machine_learning_basics.md", "doc_id": "ml_basics"}
```

**File 2:**
```json
{"source_type": "file", "source": "./sample_docs/deep_learning_guide.md", "doc_id": "dl_guide"}
```

**File 3:**
```json
{"source_type": "file", "source": "./sample_docs/nlp_fundamentals.md", "doc_id": "nlp_fundamentals"}
```

## Expected Success Indicators

✅ Ingestion:
- `"status": "success"`
- `"chunks_added": 10+` (should create 10+ chunks per doc)
- `"doc_id"` is returned

✅ Status:
- `"kb_documents": 3` (after ingesting all 3 files)
- `"kb_topics"`: Array of extracted keywords

✅ Query:
- `"answer"`: Non-empty string with LLM response
- `"context_chunks"`: Array with retrieved documents
- `"llm_api_used": true`
- `"success": true`

## Problem Troubleshooting

**NumPy Error?** (numpy.exceptions)
```bash
.\.venv\Scripts\python.exe -m pip install "numpy>=1.26.4"
```

**API won't start?**
- Check if port 8001 is available
- Verify .venv is activated
- Try: `python -m uvicorn core.api:app --reload --host 0.0.0.0 --port 8001`

**No chunks added?**
- Verify sample files exist in `src/sample_docs/`
- Check file paths are correct (use `./` prefix)

**Empty query results?**
- Ingest documents first
- Check `/api/status` to verify documents in KB
- Try simpler queries first

## Sample Documents

| File | Chunks | Topics |
|------|--------|--------|
| machine_learning_basics.md | 11-15 | ML types, algorithms, applications |
| deep_learning_guide.md | 14-18 | Neural networks, training, optimization |
| nlp_fundamentals.md | 10-14 | NLP tasks, language models, text processing |

## Performance Notes

- **First ingestion**: 2-5 sec (embeddings generated)
- **Subsequent ingestions**: 1-2 sec
- **Query response**: 2-5 sec (includes LLM call)
- **Total test time**: ~5-10 minutes for full sequence

## Success Flow

1. ✅ GET / → Returns API info
2. ✅ GET /api/status → Returns {documents: 0}
3. ✅ POST /api/ingest ML file → Returns chunks_added: 12
4. ✅ POST /api/query → Returns answer + context chunks
5. ✅ POST /api/ingest DL file → Returns chunks_added: 15
6. ✅ POST /api/query → Returns better answers with more context
7. ✅ POST /api/ingest NLP file → Returns chunks_added: 11
8. ✅ GET /api/status → Returns {documents: 3, kb_topics: [...]}
9. ✅ POST /api/ingest-batch → Returns all 3 files with success status

All green? ✅ API is working correctly!
