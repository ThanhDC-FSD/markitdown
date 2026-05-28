# RAG Pipeline API - Complete User Guide

Welcome! This guide will show you how to use the RAG (Retrieval Augmented Generation) Pipeline API to ingest documents and ask intelligent questions.

## Table of Contents
1. [Getting Started](#getting-started)
2. [API Endpoints](#api-endpoints)
3. [Step-by-Step Workflow](#step-by-step-workflow)
4. [Examples](#examples)
5. [Tips & Troubleshooting](#tips--troubleshooting)
6. [Architecture Overview](#architecture-overview)

---

## Getting Started

### Starting the Server

Run the start script from the `src/` directory:

```bash
cd src
.\start.bat  # Windows
# or
./start.sh   # Linux/macOS
```

You should see:
```
[3] Starting FastAPI server...
    Swagger UI: http://localhost:8001/docs
    API Base: http://localhost:8001
```

### Accessing the API

**Option 1: Interactive Swagger UI (Recommended)**
- Open your browser: `http://localhost:8001/docs`
- You'll see all endpoints with "Try it out" buttons

**Option 2: Command-line (cURL)**
```bash
curl -X POST "http://localhost:8001/api/ingest" \
  -H "Content-Type: application/json" \
  -d '{
    "source_type": "file",
    "source": "./sample_docs/guide.pdf"
  }'
```

**Option 3: Python requests**
```python
import requests

response = requests.post(
    "http://localhost:8001/api/ingest",
    json={
        "source_type": "file",
        "source": "./sample_docs/guide.pdf"
    }
)
print(response.json())
```

---

## API Endpoints

### 1. Check Status: `GET /api/status`

**Purpose**: Verify the API is running and see KB statistics

**Response**:
```json
{
  "status": "ready",
  "kb_documents": 3,
  "kb_topics": ["machine learning", "deep learning", "neural networks"]
}
```

**Use when**: 
- Starting your workflow
- Verifying the API is responsive
- Understanding what topics are in your KB

---

### 2. Ingest Document: `POST /api/ingest`

**Purpose**: Add a single document to the knowledge base

**Request Body**:
```json
{
  "source_type": "file",          // 'file' or 'url'
  "source": "./docs/guide.pdf",   // file path or URL
  "doc_id": "optional_custom_id"  // (optional)
}
```

**Parameters**:
- `source_type` (required): 
  - `"file"` - Local file path
  - `"url"` - Web URL
- `source` (required): Exact path or URL
- `doc_id` (optional): Custom identifier. If omitted, auto-generated.

**Response**:
```json
{
  "status": "success",
  "message": "Document ingested with 12 chunks",
  "doc_id": "doc_0_5234",
  "chunks_added": 12
}
```

**Supported Formats**:
PDF, Word (.docx, .doc), Markdown, HTML, CSV, JSON, Excel, PowerPoint, and more (30+ formats via MarkItdown).

**How it works**:
1. Downloads/reads the file
2. Converts to markdown
3. Splits into overlapping chunks (512 tokens each)
4. Generates embeddings for each chunk
5. Stores in ChromaDB vector database
6. Updates the intent analyzer

---

### 3. Batch Ingest: `POST /api/ingest-batch`

**Purpose**: Upload multiple files at once

**How to use in Swagger**:
1. Open Swagger UI: `http://localhost:8001/docs`
2. Find "Ingest-batch" endpoint
3. Click "Try it out"
4. Click "Select files"
5. Choose multiple files
6. Click "Execute"

**Response**:
```json
{
  "results": [
    {
      "filename": "guide.pdf",
      "status": "success",
      "doc_id": "guide_001",
      "chunks_added": 15
    },
    {
      "filename": "faq.md",
      "status": "success",
      "doc_id": "faq_001",
      "chunks_added": 8
    }
  ],
  "total": 2,
  "succeeded": 2
}
```

**Notes**:
- Each file is processed independently
- Failed files don't block others
- Check the results array to see which files succeeded

---

### 4. Query: `POST /api/query`

**Purpose**: Ask questions and get answers grounded in your documents

**Request Body**:
```json
{
  "query": "What are the fundamentals of deep learning?",
  "top_k": 5,           // Documents to retrieve initially (5-20 recommended)
  "rerank_top_k": 3     // Final documents after re-ranking (2-5 recommended)
}
```

**Parameters**:
- `query` (required): Your question in natural language
- `top_k` (default: 5): Initial retrieval count
  - Smaller values = faster, less context
  - Larger values = slower, more context
- `rerank_top_k` (default: 3): Final result count after re-ranking
  - Smaller = fewer sources, better quality
  - Larger = more sources, broader coverage

**Response**:
```json
{
  "query": "What are the fundamentals of deep learning?",
  "answer": "Deep learning is a subset of machine learning that uses artificial neural networks...",
  "context_chunks": [
    {
      "rank": 1,
      "text": "Deep learning is inspired by biological neural networks...",
      "distance": 0.15,
      "cross_encoder_score": 8.5,
      "metadata": {
        "source": "deep_learning_guide.md",
        "source_type": "file",
        "doc_id": "doc_1",
        "chunk_index": 0
      }
    },
    {
      "rank": 2,
      "text": "Neural networks consist of layers of interconnected nodes...",
      "distance": 0.22,
      "cross_encoder_score": 7.8,
      "metadata": { /* ... */ }
    }
  ],
  "intent_analysis": {
    "is_kb_relevant": true,
    "keywords": ["deep learning", "fundamentals", "neural networks"]
  },
  "llm_api_used": true
}
```

**Response Fields**:
- `answer`: AI-generated answer based on your documents
- `context_chunks`: Source documents used to generate the answer
  - `distance`: Vector similarity (0-1, lower = more similar)
  - `cross_encoder_score`: Relevance score (higher = more relevant)
  - `metadata`: Source information for verification
- `intent_analysis`: Whether the query is relevant to your KB
- `llm_api_used`: Whether the external LLM API was called

---

## Step-by-Step Workflow

### Scenario: Building a Customer Support Knowledge Base

#### Step 1: Check Status
```
GET /api/status
```
Response shows: `kb_documents: 0` (empty KB)

#### Step 2: Ingest FAQ Document
```
POST /api/ingest
{
  "source_type": "file",
  "source": "./docs/faq.pdf",
  "doc_id": "customer_faq"
}
```
Response: 20 chunks added

#### Step 3: Ingest Troubleshooting Guide
```
POST /api/ingest
{
  "source_type": "file",
  "source": "./docs/troubleshooting.md",
  "doc_id": "troubleshooting_guide"
}
```
Response: 15 chunks added

#### Step 4: Check Updated Status
```
GET /api/status
```
Response: `kb_documents: 35` (2 docs, 35 chunks total)

#### Step 5: Ask Questions
```
POST /api/query
{
  "query": "How do I reset my password?",
  "top_k": 5,
  "rerank_top_k": 3
}
```
Response: Answer with citations

---

## Examples

### Example 1: Simple Query

**Request**:
```json
{
  "query": "What is machine learning?",
  "top_k": 5,
  "rerank_top_k": 3
}
```

**Response Summary**:
```
Answer: Machine learning is a subset of artificial intelligence 
        where systems learn from data without explicit programming...

Sources:
[1] ml_basics.md (distance: 0.12, score: 8.7)
[2] ai_fundamentals.pdf (distance: 0.18, score: 7.5)
[3] algorithms_guide.md (distance: 0.25, score: 6.9)
```

---

### Example 2: Batch Ingestion with Python

```python
import requests
from pathlib import Path

# Prepare files
files = [
    ('files', open('guide.pdf', 'rb')),
    ('files', open('faq.md', 'rb')),
    ('files', open('tutorial.docx', 'rb')),
]

# Upload
response = requests.post(
    "http://localhost:8001/api/ingest-batch",
    files=files
)

# Process results
result = response.json()
print(f"Uploaded {result['succeeded']}/{result['total']} files")

for item in result['results']:
    if item['status'] == 'success':
        print(f"✓ {item['filename']}: {item['chunks_added']} chunks")
    else:
        print(f"✗ {item['filename']}: {item['message']}")

# Close files
for _, file in files:
    file.close()
```

---

### Example 3: Querying from a Script

```python
import requests
import json

def query_kb(question, top_k=5, rerank_top_k=3):
    """Query the knowledge base and return formatted results."""
    
    response = requests.post(
        "http://localhost:8001/api/query",
        json={
            "query": question,
            "top_k": top_k,
            "rerank_top_k": rerank_top_k
        }
    )
    
    if response.status_code == 200:
        result = response.json()
        
        print(f"Q: {result['query']}\n")
        print(f"A: {result['answer']}\n")
        
        print("Sources:")
        for chunk in result['context_chunks']:
            print(f"  [{chunk['rank']}] {chunk['metadata']['source']}")
            print(f"      Relevance: {chunk['cross_encoder_score']:.1f}/10")
            print()
        
        return result
    else:
        print(f"Error: {response.status_code}")
        print(response.text)

# Usage
query_kb("What are the key features of the system?")
```

---

## Tips & Troubleshooting

### Performance Tips

1. **First query is slow** (downloads ML models)
   - Embedder (~200MB): Downloaded on first run
   - CrossEncoder (~400MB): Downloaded on first query
   - This is one-time; subsequent queries are fast

2. **Optimize retrieval parameters**
   - Small KB? Use smaller `top_k` (3-5)
   - Large KB? Use larger `top_k` (10-20)
   - Always set `rerank_top_k` < `top_k`

3. **Batch ingestion**
   - Use `/api/ingest-batch` for multiple files
   - Faster than individual POST requests
   - Failed files don't block others

### Troubleshooting

**Q: "No relevant documents found" in query response**
- Check KB has documents: `GET /api/status`
- Ensure documents are related to your query
- Try increasing `top_k` to get more context

**Q: Query returns incorrect answer**
- Check `context_chunks` to verify source quality
- If sources are wrong, your documents may not be relevant
- Try rephrasing the question
- Add more relevant documents to KB

**Q: Document ingestion fails**
- Verify file exists and is readable
- Check file format is supported (30+ formats supported)
- Check disk space for embeddings storage

**Q: "LLM API not available" error**
- Ensure LLM service running on `http://localhost:8080/prompt`
- The API still returns context chunks even if LLM is unavailable
- You can see retrieved documents in `context_chunks`

**Q: Server stops with errors**
- Check logs: `logs/api_*.log`
- Restart server: `cd src && .\start.bat`
- Ensure dependencies installed: `pip install -r requirements.txt`

---

## Architecture Overview

```
User Input
    ↓
[Query Request] → Intent Analyzer (KB relevance check)
    ↓
[Retrieval] → Embedder (query embedding) + ChromaDB (vector search)
    ↓
[Re-ranking] → CrossEncoder (relevance scoring)
    ↓
[Context Prep] → Format documents with metadata
    ↓
[LLM Call] → GPT-4o API with context
    ↓
[Response] → Answer + sources + metadata
```

### Components

| Component | Purpose | Model |
|-----------|---------|-------|
| **Embedder** | Convert text to vectors | all-MiniLM-L6-v2 |
| **Retriever** | Find similar documents | ChromaDB (vector DB) |
| **Reranker** | Score relevance | cross-encoder/ms-marco-MiniLM-L-12-v2 |
| **Intent Analyzer** | Check KB relevance | Keyword-based + embeddings |
| **LLM Caller** | Generate answers | GPT-4o (external API) |

---

## API Limits & Quotas

| Metric | Limit | Notes |
|--------|-------|-------|
| Document size | Unlimited | Handled by MarkItdown |
| KB size | Disk space | Embeddings stored in `chroma_db/` |
| Query response time | ~5-10 sec | Depends on KB size & LLM latency |
| Batch upload | 10 files/request | No hard limit, adjust as needed |
| Concurrent requests | 1 (no threading) | Single-threaded by default |

---

## Next Steps

1. **Ingest your first document**: Use `POST /api/ingest` or the Swagger UI
2. **Check status**: Run `GET /api/status` to verify
3. **Ask a question**: Use `POST /api/query` with your question
4. **Review sources**: Check `context_chunks` to verify answer quality
5. **Iterate**: Add more documents and refine queries

---

## Support & Documentation

- **Interactive Docs**: `http://localhost:8001/docs` (Swagger UI)
- **Alternative Docs**: `http://localhost:8001/redoc` (ReDoc)
- **API Logs**: `logs/api_*.log` (in project root)
- **Source Code**: [github.com/your-repo]

Happy querying!
