# RAG Pipeline API - Complete Testing Guide

## Quick Start

**API Base URL**: `http://localhost:8001`  
**Swagger UI**: `http://localhost:8001/docs`  
**ReDoc**: `http://localhost:8001/redoc`

---

## Available APIs & Testing Plan

### 1. ✅ **GET /** - Root Endpoint (Info)
**Purpose**: Get API overview and available endpoints  
**URL**: `http://localhost:8001/`  
**Method**: `GET`  
**No Parameters Required**

**Expected Response**:
```json
{
  "name": "RAG Pipeline API",
  "version": "1.0.0",
  "status": "operational",
  "endpoints": {
    "docs": "/docs - Interactive Swagger UI",
    "redoc": "/redoc - ReDoc documentation",
    "ingest": "POST /api/ingest - Add documents to KB",
    "ingest_batch": "POST /api/ingest-batch - Batch upload multiple files",
    "query": "POST /api/query - Query the knowledge base",
    "status": "GET /api/status - Check KB and pipeline status"
  }
}
```

**Test in Swagger**: ✓ Available at `/docs`

---

### 2. 🟢 **GET /api/status** - Check System Status
**Purpose**: Check pipeline status and KB statistics  
**URL**: `http://localhost:8001/api/status`  
**Method**: `GET`  
**No Parameters Required**

**Expected Response** (before ingestion):
```json
{
  "status": "ready",
  "kb_documents": 0,
  "kb_topics": []
}
```

**Test Order**: Run this **FIRST** to verify the API is working

---

### 3. 📥 **POST /api/ingest** - Add a Document to Knowledge Base
**Purpose**: Ingest a single document (file or URL) into the KB  
**URL**: `http://localhost:8001/api/ingest`  
**Method**: `POST`  
**Content-Type**: `application/json`

#### **Sample Test Data - Option A: Local File**
```json
{
  "source_type": "file",
  "source": "./sample_docs/machine_learning_basics.md",
  "doc_id": "ml_basics_001"
}
```

#### **Sample Test Data - Option B: Another Local File**
```json
{
  "source_type": "file",
  "source": "./sample_docs/deep_learning_guide.md",
  "doc_id": "dl_guide_001"
}
```

#### **Sample Test Data - Option C: Remote URL**
```json
{
  "source_type": "url",
  "source": "https://raw.githubusercontent.com/microsoft/markitdown/main/README.md",
  "doc_id": "markitdown_readme"
}
```

**Expected Response**:
```json
{
  "status": "success",
  "message": "Document ingested with 12 chunks",
  "doc_id": "ml_basics_001",
  "chunks_added": 12
}
```

**Test Sequence**:
1. First ingest `machine_learning_basics.md`
2. Then ingest `deep_learning_guide.md`
3. Then ingest `nlp_fundamentals.md`
4. (Optional) Try a remote URL

---

### 4. 🔍 **POST /api/query** - Query the Knowledge Base
**Purpose**: Ask questions about ingested documents with intelligent re-ranking  
**URL**: `http://localhost:8001/api/query`  
**Method**: `POST`  
**Content-Type**: `application/json`

#### **Query Test Set 1: Basic ML Questions** (test after ingesting ML files)
```json
{
  "query": "What is machine learning?",
  "top_k": 5,
  "rerank_top_k": 3
}
```

```json
{
  "query": "What are neural networks?",
  "top_k": 5,
  "rerank_top_k": 3
}
```

```json
{
  "query": "What is deep learning?",
  "top_k": 5,
  "rerank_top_k": 3
}
```

#### **Query Test Set 2: NLP Questions** (test after ingesting NLP file)
```json
{
  "query": "What is natural language processing?",
  "top_k": 5,
  "rerank_top_k": 3
}
```

```json
{
  "query": "How do computers understand language?",
  "top_k": 5,
  "rerank_top_k": 3
}
```

#### **Query Test Set 3: Edge Cases**
```json
{
  "query": "What is something not in the documents?",
  "top_k": 5,
  "rerank_top_k": 3
}
```

```json
{
  "query": "Explain the difference between ML and AI",
  "top_k": 5,
  "rerank_top_k": 3
}
```

**Expected Response** (after ingestion):
```json
{
  "request_id": "qa_a1b2c3d4e5f6...",
  "query": "What is machine learning?",
  "answer": "Machine learning is a subset of artificial intelligence...",
  "context_chunks": [
    {
      "text": "Machine learning (ML) is a subset of artificial intelligence...",
      "metadata": {
        "source": "machine_learning_basics.md",
        "chunk_id": 0
      },
      "distance": 0.15,
      "cross_encoder_score": 0.92
    },
    {
      "text": "ML systems learn patterns from data...",
      "metadata": {...},
      "distance": 0.28,
      "cross_encoder_score": 0.78
    }
  ],
  "intent_analysis": {
    "is_relevant": true,
    "keywords": ["machine learning", "artificial intelligence"],
    "confidence": 0.95
  },
  "llm_api_used": true,
  "retrieval_relevant": true,
  "retrieval_sufficient": true,
  "success": true
}
```

**Response Fields Explanation**:
- `answer`: Generated answer grounded in KB
- `context_chunks`: Retrieved documents with similarity scores
- `distance`: Vector similarity (lower = more relevant)
- `cross_encoder_score`: Re-ranking score (higher = more relevant)
- `intent_analysis`: Query relevance check
- `retrieval_relevant`: Whether KB contains relevant info
- `retrieval_sufficient`: Whether KB has enough info to answer
- `success`: Overall success status

**Test Order**:
1. Test after first ingestion
2. Add more documents and test progressively
3. Test edge cases after full KB is loaded

---

### 5. 📤 **POST /api/ingest-batch** - Batch Upload Multiple Files
**Purpose**: Upload multiple documents at once  
**URL**: `http://localhost:8001/api/ingest-batch`  
**Method**: `POST`  
**Content-Type**: `multipart/form-data`

**How to test in Swagger**:
1. Go to `/docs`
2. Find "POST /api/ingest-batch"
3. Click "Try it out"
4. Click "Select files"
5. Choose: `machine_learning_basics.md`, `deep_learning_guide.md`, `nlp_fundamentals.md`
6. Click "Execute"

**Expected Response**:
```json
{
  "results": [
    {
      "filename": "machine_learning_basics.md",
      "status": "success",
      "doc_id": "machine_learning_basics.md",
      "chunks_added": 12
    },
    {
      "filename": "deep_learning_guide.md",
      "status": "success",
      "doc_id": "deep_learning_guide.md",
      "chunks_added": 15
    },
    {
      "filename": "nlp_fundamentals.md",
      "status": "success",
      "doc_id": "nlp_fundamentals.md",
      "chunks_added": 11
    }
  ],
  "total": 3,
  "succeeded": 3
}
```

---

## Recommended Testing Sequence

### Phase 1: System Verification (5 min)
1. **GET /** - Verify API is responding
2. **GET /api/status** - Check initial KB (should be empty)

### Phase 2: Single Document Ingestion (5 min)
3. **POST /api/ingest** - Ingest `machine_learning_basics.md`
4. **GET /api/status** - Verify document count increased
5. **POST /api/query** - Test with ML-related questions

### Phase 3: Progressive Ingestion (5 min)
6. **POST /api/ingest** - Ingest `deep_learning_guide.md`
7. **POST /api/query** - Test with DL-related questions
8. **POST /api/ingest** - Ingest `nlp_fundamentals.md`

### Phase 4: Comprehensive Querying (10 min)
9. **POST /api/query** - Run all test queries from Query Test Sets 1-3
10. Verify:
    - Answers are grounded in retrieved context
    - Context chunks have appropriate similarity scores
    - Intent analysis is working
    - LLM is being used correctly

### Phase 5: Batch Operations (5 min)
11. **POST /api/ingest-batch** - Clear and re-ingest all files at once
12. **POST /api/query** - Run final verification queries

---

## Sample Documents Available for Testing

### 1. **machine_learning_basics.md** (11-15 chunks)
- What is Machine Learning?
- Machine learning types (supervised, unsupervised, reinforcement)
- ML applications and use cases
- Learning algorithms

**Good queries to test**:
- "What is machine learning?"
- "What are the types of machine learning?"
- "What are ML applications?"

### 2. **deep_learning_guide.md** (14-18 chunks)
- Introduction to Deep Learning
- Neural Networks architecture
- Training and optimization
- Real-world applications

**Good queries to test**:
- "What is deep learning?"
- "What are neural networks?"
- "How do we train neural networks?"

### 3. **nlp_fundamentals.md** (10-14 chunks)
- What is NLP?
- NLP tasks and applications
- Text processing techniques
- Language models

**Good queries to test**:
- "What is natural language processing?"
- "What are NLP applications?"
- "How do language models work?"

---

## Testing Checklist

### Ingestion Tests
- [ ] Ingest single file successfully
- [ ] Ingest multiple files one at a time
- [ ] Batch ingest multiple files
- [ ] Verify chunk counts are reasonable (>5 per doc)
- [ ] Ingest from URL (if connected)

### Query Tests
- [ ] Query returns answer for relevant questions
- [ ] Context chunks are related to query
- [ ] Similarity scores (distance, cross_encoder_score) make sense
- [ ] Intent analysis identifies keywords correctly
- [ ] LLM is invoked (llm_api_used=true)
- [ ] Edge case: Query about non-existent topics

### Status Tests
- [ ] Status shows correct document count after ingestion
- [ ] Status shows extracted keywords/topics
- [ ] Status updates after each ingestion

### Response Quality Tests
- [ ] Answers are grounded (based on context)
- [ ] Answers cite sources from metadata
- [ ] Multiple relevant chunks appear when appropriate
- [ ] Distance scores: 0.0-0.3 (very relevant), 0.3-0.6 (relevant), 0.6+ (less relevant)
- [ ] Cross-encoder scores: >0.8 (very relevant), 0.5-0.8 (relevant), <0.5 (less relevant)

---

## Testing with curl (Command Line)

### 1. Get Status
```bash
curl -X GET "http://localhost:8001/api/status" \
  -H "Content-Type: application/json"
```

### 2. Ingest a Document
```bash
curl -X POST "http://localhost:8001/api/ingest" \
  -H "Content-Type: application/json" \
  -d '{
    "source_type": "file",
    "source": "./sample_docs/machine_learning_basics.md",
    "doc_id": "ml_basics"
  }'
```

### 3. Query the KB
```bash
curl -X POST "http://localhost:8001/api/query" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What is machine learning?",
    "top_k": 5,
    "rerank_top_k": 3
  }'
```

---

## Notes

- **Initial KB is empty** - Must ingest documents first
- **Sample docs are in**: `src/sample_docs/`
- **Swagger UI** is the easiest way to test (click Try it out)
- **Processing time** varies:
  - Small docs (< 5 KB): 1-2 seconds
  - Large docs (100+ KB): 5-30 seconds
  - Query response: 2-5 seconds (depends on LLM API)
- **ChromaDB** stores embeddings locally - persists between restarts
