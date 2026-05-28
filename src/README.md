```markdown
# RAG Pipeline Demo

A complete Retrieval-Augmented Generation (RAG) pipeline with document ingestion, vector embeddings, cross-encoder re-ranking, and LLM integration.

## Architecture

```
┌─────────────────┐
│  Document Input │
│  (Files/URLs)   │
└────────┬────────┘
         │
         ▼
┌─────────────────────────┐
│  MarkItDown Converter   │ (PDF, DOCX, HTML → Markdown)
└────────┬────────────────┘
         │
         ▼
┌─────────────────┐
│  Text Chunker   │ (512 char chunks, 64 char overlap)
└────────┬────────┘
         │
         ▼
┌──────────────────────────────┐
│  Embedder (all-MiniLM-L6)    │ (Generate embeddings)
└────────┬─────────────────────┘
         │
         ▼
┌──────────────────────────────┐
│  ChromaDB Vector Store       │ (Persistent: ./chroma_db)
│  (Cosine similarity)         │
└──────────────────────────────┘
                │
                ├─ User Query
                │
                ▼
        ┌───────────────────┐
        │  Intent Analyzer  │ (Detect relevance to KB)
        └────────┬──────────┘
                 │
                 ▼
        ┌──────────────────┐
        │  Retriever       │ (Top-5 by cosine similarity)
        └────────┬─────────┘
                 │
                 ▼
        ┌────────────────────────────────────┐
        │  Cross-Encoder Reranker            │
        │  (ms-marco-MiniLM-L-12-v2)        │
        │  Re-rank to top-3                  │
        └────────┬───────────────────────────┘
                 │
                 ▼
        ┌────────────────────┐
        │  Context Assembly  │
        └────────┬───────────┘
                 │
                 ▼
        ┌────────────────────────────────┐
        │  LLM API Caller                │
        │  (http://localhost:8080/prompt)│
        └────────┬───────────────────────┘
                 │
                 ▼
        ┌────────────────────┐
        │  Answer Response   │
        └────────────────────┘
```

## Features

- **Document Ingestion API**: Upload documents (PDF, DOCX, HTML, etc.) via FastAPI
- **Vector Storage**: Persistent ChromaDB with cosine similarity search
- **Intent Analysis**: Analyze query relevance to KB baseline
- **Cross-Encoder Re-ranking**: Semantic re-ranking of retrieved chunks
- **LLM Integration**: Call local LLM API with assembled context
- **Swagger UI**: Interactive API documentation and testing
- **Batch Processing**: Ingest multiple files at once

## Quick Start

### 1. Install Dependencies

```bash
cd src
pip install -r requirements.txt
```

### 2. Create Sample Knowledge Base

```bash
python crawler.py --mode sample --output ./sample_docs
```

This creates three sample markdown documents:
- machine_learning_basics.md
- deep_learning_guide.md
- nlp_fundamentals.md

### 3. Start FastAPI Server

```bash
python -m uvicorn api:app --reload --host 0.0.0.0 --port 8000
```

You should see:
```
Uvicorn running on http://0.0.0.0:8000
```

### 4. Access Swagger UI

Open browser and go to: **http://localhost:8000/docs**

You'll see:
- Swagger UI with all endpoints
- Try-it-out buttons for each endpoint
- Request/response schemas

## API Endpoints

### 1. Ingest Endpoint (Document Ingestion)

**POST** `/api/ingest`

Ingest a single document for embedding and storage.

**Request:**
```json
{
  "source_type": "file",
  "source": "/path/to/document.pdf",
  "doc_id": "optional_doc_id"
}
```

**Response:**
```json
{
  "status": "success",
  "message": "Document ingested with 5 chunks",
  "doc_id": "doc_0_12345",
  "chunks_added": 5
}
```

### 2. Batch Ingest Endpoint

**POST** `/api/ingest-batch`

Ingest multiple files at once.

**Request:** (multipart/form-data)
- Select multiple files

**Response:**
```json
{
  "results": [
    {"filename": "doc1.pdf", "status": "success", "chunks_added": 5},
    {"filename": "doc2.pdf", "status": "success", "chunks_added": 3}
  ],
  "total": 2,
  "succeeded": 2
}
```

### 3. Query Endpoint (RAG Query)

**POST** `/api/query`

Query the RAG system with cross-encoder re-ranking.

**Request:**
```json
{
  "query": "What is machine learning?",
  "top_k": 5,
  "rerank_top_k": 3
}
```

**Response:**
```json
{
  "query": "What is machine learning?",
  "answer": "Machine learning (ML) is a subset of artificial intelligence...",
  "context_chunks": [
    {
      "rank": 1,
      "text": "Machine learning (ML) is a subset of artificial intelligence...",
      "distance": 0.15,
      "cross_encoder_score": 0.92,
      "metadata": {
        "source": "machine_learning_basics.md",
        "chunk_index": 0
      }
    }
  ],
  "intent_analysis": {
    "query": "What is machine learning?",
    "keywords": ["machine", "learning"],
    "kb_overlap": ["machine", "learning"],
    "overlap_ratio": 1.0,
    "intent_type": "definition",
    "relevance_score": 0.95,
    "is_kb_relevant": true
  },
  "llm_api_used": true
}
```

### 4. Status Endpoint

**GET** `/api/status`

Get current pipeline status.

**Response:**
```json
{
  "status": "ready",
  "kb_documents": 42,
  "kb_topics": ["machine", "learning", "neural", "network", ...]
}
```

## Usage Examples

### Example 1: Ingest Documents via Swagger UI

1. Go to http://localhost:8000/docs
2. Click on **POST /api/ingest**
3. Click **Try it out**
4. Fill in the request:
   ```json
   {
     "source_type": "file",
     "source": "./sample_docs/machine_learning_basics.md",
     "doc_id": "ml_basics_v1"
   }
   ```
5. Click **Execute**
6. See the response with chunks added

### Example 2: Query with curl

```bash
curl -X POST "http://localhost:8000/api/query" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Explain the difference between supervised and unsupervised learning",
    "top_k": 5,
    "rerank_top_k": 3
  }'
```

### Example 3: Batch Ingest via Python

```python
import requests

files = []
for doc in ["./sample_docs/machine_learning_basics.md", 
            "./sample_docs/deep_learning_guide.md"]:
    files.append(("files", open(doc, "rb")))

response = requests.post(
    "http://localhost:8000/api/ingest-batch",
    files=files
)

print(response.json())
```

### Example 4: Full Pipeline with Python

```python
import requests
import json

# Ingest document
ingest_resp = requests.post(
    "http://localhost:8000/api/ingest",
    json={
        "source_type": "file",
        "source": "./sample_docs/nlp_fundamentals.md",
        "doc_id": "nlp_v1"
    }
)

print("Ingestion:", json.dumps(ingest_resp.json(), indent=2))

# Query
query_resp = requests.post(
    "http://localhost:8000/api/query",
    json={
        "query": "What are transformers and why are they important?",
        "top_k": 5,
        "rerank_top_k": 3
    }
)

result = query_resp.json()
print("\nQuery:", result["query"])
print("Answer:", result["answer"])
print("\nTop context chunks:")
for chunk in result["context_chunks"]:
    print(f"  [{chunk['rank']}] Score: {chunk['cross_encoder_score']:.2f}")
    print(f"      {chunk['text'][:100]}...")
```

## Configuration

### Modify Parameters in `src/api.py`

**Document Chunking:**
```python
chunker = TextChunker(chunk_size=512, overlap=64)
```

**Embedder Model:**
```python
embedder = Embedder(model_name="all-MiniLM-L6-v2")
```

**Re-ranker Model:**
```python
reranker = CrossEncoderReranker(model_name="cross-encoder/ms-marco-MiniLM-L-12-v2")
```

**LLM API Configuration:**
```python
llm_caller = LLMCaller(
    api_url="http://localhost:8080/prompt",
    model="gpt-4o",
    temperature=0.3,
)
```

**ChromaDB Persistence:**
```python
retriever = Retriever(persist_dir="./chroma_db", collection_name="documents")
```

## Data Flow

### Ingestion Flow
1. **File → Converter**: MarkItDown converts PDF/DOCX/HTML to Markdown
2. **Markdown → Chunker**: Split into ~512-char chunks with 64-char overlap
3. **Chunks → Embedder**: Generate embeddings using all-MiniLM-L6-v2
4. **Embeddings → ChromaDB**: Store with metadata and IDs
5. **ChromaDB → Persist**: Save to `./chroma_db/` directory

### Query Flow
1. **Query → Intent Analyzer**: Check relevance to KB baseline
2. **Query → Retriever**: Find top-5 chunks by cosine similarity
3. **Query + Chunks → Re-ranker**: Cross-encoder re-ranks to top-3
4. **Context Assembly**: Format top-3 chunks as context
5. **Context + Query → LLM**: Call local API with assembled prompt
6. **LLM Response → Answer**: Return to user with chunk metadata

## Troubleshooting

### Issue: "Failed to connect to LLM API"

**Solution**: Ensure your LLM API is running at `http://localhost:8080/prompt`

Test with curl:
```bash
curl -X POST 'http://localhost:8080/prompt' \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "gpt-4o",
    "prompt": "hello",
    "stream": false,
    "temperature": 0.3
  }'
```

### Issue: ChromaDB models downloading slowly

**Solution**: This is normal on first run. Models (~200MB) are cached locally.

### Issue: No results found in query

**Solution**: 
1. Verify documents are ingested: Visit `/api/status`
2. Check intent analysis: `overlap_ratio` should be > 0.1
3. Try different query terms that match KB content

### Issue: High cross-encoder model download

**Solution**: Models (~300MB) are cached. First query may take 1-2 minutes.

## Project Structure

```
src/
├── api.py                 # FastAPI main application
├── crawler.py             # Document crawler for KB population
├── requirements.txt       # Python dependencies
├── rag_pipeline/
│   ├── __init__.py
│   ├── converter.py       # MarkItDown wrapper
│   ├── chunker.py         # Text chunking
│   ├── embedder.py        # Sentence-transformers embeddings
│   ├── retriever.py       # ChromaDB vector store
│   ├── reranker.py        # Cross-encoder re-ranking
│   ├── llm_caller.py      # LLM API integration
│   └── intent_analyzer.py # Intent detection and baseline
├── sample_docs/           # Sample documents for testing
│   ├── machine_learning_basics.md
│   ├── deep_learning_guide.md
│   └── nlp_fundamentals.md
└── chroma_db/            # Persistent ChromaDB storage (created at runtime)
```

## Performance Notes

- **First Run**: Embedding models download (~200MB), takes 1-2 minutes
- **Query Latency**: Typically 2-5 seconds (depends on LLM API response time)
- **Memory Usage**: ~2-3GB for transformer models
- **Storage**: ~10-50MB per 100 documents (embeddings + metadata)

## Next Steps

1. **Add Authentication**: Protect endpoints with API keys
2. **Implement Caching**: Cache frequent queries
3. **Add Feedback Loop**: Learn from user feedback on answers
4. **Multi-language Support**: Support documents in multiple languages
5. **Advanced Metrics**: Track query accuracy and user satisfaction
6. **Streaming Responses**: Support streaming LLM responses
7. **Custom Embedders**: Support domain-specific embedding models
8. **Query Expansion**: Expand queries for better retrieval

## License

MIT

## Support

For issues or questions, please check the troubleshooting section or create an issue in the repository.
```
