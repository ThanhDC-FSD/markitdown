"""FastAPI application for RAG pipeline with document ingestion and query endpoints."""

# === CRITICAL: Disable SSL verification BEFORE any other imports ===
import ssl
import urllib.request
import urllib3

# Create unverified SSL context
unverified_context = ssl.create_default_context()
unverified_context.check_hostname = False
unverified_context.verify_mode = ssl.CERT_NONE

# Replace SSL context globally
ssl._create_default_https_context = ssl._create_unverified_context
urllib3.disable_warnings()

# Patch urllib to bypass SSL
https_handler = urllib.request.HTTPSHandler(context=unverified_context)
urllib.request._opener = urllib.request.build_opener(https_handler)

# Monkeypatch requests library to disable SSL verification
import requests
from urllib3.poolmanager import PoolManager
from urllib3.util.ssl_ import create_urllib3_context

# Create a custom HTTPAdapter that doesn't verify SSL
class NoVerifyHTTPSAdapter(requests.adapters.HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        ctx = create_urllib3_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        kwargs['ssl_context'] = ctx
        return super().init_poolmanager(*args, **kwargs)

# Apply the adapter to all requests
requests.Session.trust_env = False
for scheme in ('https://', 'http://'):
    requests.adapters.DEFAULT_POOLMANAGER_CLS = PoolManager
    if 'https' in scheme:
        session = requests.Session()
        session.mount('https://', NoVerifyHTTPSAdapter())
        session.verify = False

from fastapi import FastAPI, File, UploadFile, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional
import uvicorn
import tempfile
import os
import uuid
from pathlib import Path
import logging
import warnings
import requests

# === SSL CERTIFICATE VERIFICATION FIX ===
# Disable SSL verification for HuggingFace Hub downloads and other HTTPS requests
# This is needed if your system doesn't have proper SSL certificates configured

# Set environment variables
os.environ['PYTHONHTTPSVERIFY'] = '0'
os.environ['REQUESTS_CA_BUNDLE'] = ''
os.environ['CURL_CA_BUNDLE'] = ''
os.environ['HF_HUB_OFFLINE'] = '1'  # Disable HuggingFace Hub online checks
os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
os.environ['TRANSFORMERS_OFFLINE'] = '1'  # Disable transformers library online checks

# Disable urllib3 warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
requests.packages.urllib3.disable_warnings()

# Override SSL context creation
try:
    _create_unverified_https_context = ssl._create_unverified_context
except AttributeError:
    pass
else:
    ssl._create_default_https_context = _create_unverified_https_context

# For httplib2 and similar
if hasattr(ssl, '_create_default_context'):
    ssl._create_default_context = _create_unverified_https_context

# Suppress pydub ffmpeg warning (not needed for this project)
warnings.filterwarnings("ignore", message=".*Couldn't find ffmpeg or avconv.*", category=RuntimeWarning)

# Suppress urllib3 SSL warnings
warnings.filterwarnings("ignore", category=urllib3.exceptions.InsecureRequestWarning)

from .config import (
    setup_logger,
    API_HOST,
    API_PORT,
    API_LOG_FILE,
    CHROMA_DB_DIR,
    CHUNK_SIZE,
    CHUNK_OVERLAP,
    COPILOT_API_BASE_URL,
    GROUNDED_QA_ENDPOINT,
    DEFAULT_GROUNDED_MODEL,
    DEFAULT_GROUNDED_ANSWER_POLICY,
    DEFAULT_GROUNDED_GENERATION_OPTIONS,
)
from pipeline.rag_pipeline import (
    DocumentConverter,
    TextChunker,
    Embedder,
    Retriever,
    CrossEncoderReranker,
    IntentAnalyzer,
)
from pipeline.rag_pipeline.quality_gates import QualityGates
from pipeline.rag_pipeline.grounded_qa import GroundedQAClient, run_grounded_query
from pipeline.rag_pipeline.query_contract import ErrorDetail, normalize_grounded_query_response_payload

# Setup logging
logger = setup_logger(__name__, API_LOG_FILE)
logger.info(f"RAG Pipeline API initialized - API will run on {API_HOST}:{API_PORT}")


# ============================================================================
# Pydantic Models
# ============================================================================

class IngestRequest(BaseModel):
    """Request model for document ingestion.
    
    Supports ingesting documents from local files or URLs.
    Documents are automatically converted to markdown, chunked, embedded, and stored in the vector DB.
    """
    source_type: str = "file"  # 'file' or 'url'
    source: str  # file path (e.g., './docs/guide.pdf') or URL (e.g., 'https://example.com/article')
    doc_id: Optional[str] = None  # optional custom document ID; auto-generated if not provided
    
    class Config:
        json_schema_extra = {
            "example": {
                "source_type": "file",
                "source": "./sample_docs/machine_learning_basics.md",
                "doc_id": "ml_basics_001"
            }
        }


class IngestResponse(BaseModel):
    """Response model for document ingestion."""
    status: str  # 'success' or 'error'
    message: str  # descriptive message
    doc_id: Optional[str] = None  # unique document identifier
    chunks_added: int = 0  # number of chunks created
    
    class Config:
        json_schema_extra = {
            "example": {
                "status": "success",
                "message": "Document ingested with 12 chunks",
                "doc_id": "doc_0_5234",
                "chunks_added": 12
            }
        }


class QueryRequest(BaseModel):
    """Request model for RAG queries with cross-encoder re-ranking.
    
    Submits a question to retrieve relevant documents and generate an answer
    using the LLM API with context from the knowledge base.
    """
    query: str  # user's question
    top_k: int = 5  # initial number of documents to retrieve (before re-ranking)
    rerank_top_k: int = 3  # number of documents after cross-encoder re-ranking
    request_id: Optional[str] = None  # optional request identifier for traceability
    model: Optional[str] = None  # optional grounded QA model override
    answer_policy: Optional[Dict[str, Any]] = None  # optional grounded QA policy override
    generation_options: Optional[Dict[str, Any]] = None  # optional generation override
    
    class Config:
        json_schema_extra = {
            "example": {
                "query": "What are the fundamentals of deep learning?",
                "top_k": 5,
                "rerank_top_k": 3
            }
        }


class QueryResponse(BaseModel):
    """Response model for RAG queries with rich context and analysis."""
    query: str  # echoed query
    answer: str  # LLM-generated answer
    context_chunks: List[dict]  # top re-ranked documents (text + scores + metadata)
    intent_analysis: Dict[str, Any]  # query intent analysis (relevance to KB, keywords, etc.)
    llm_api_used: bool  # whether grounded QA API was attempted
    llm_invocation_attempted: bool
    gateway_http_status: Optional[int] = None
    provider_http_status: Optional[int] = None
    llm_transport_success: bool
    llm_response_json_valid: bool
    llm_response_schema_valid: bool
    answer_extraction_success: bool
    generation_executed: bool
    generation_failure_reason: Optional[ErrorDetail] = None
    failure_class: str
    model_requested: str
    model_used: Optional[str] = None
    abstained: bool
    abstention_reason: Optional[str] = None
    citations: List[dict] = Field(default_factory=list)
    request_id: str
    success: bool
    result_status: str
    grounding_summary: Dict[str, Any] = Field(default_factory=dict)
    runtime: Dict[str, Any] = Field(default_factory=dict)
    error: Optional[ErrorDetail] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "query": "What are the fundamentals of deep learning?",
                "answer": "Deep learning is a subset of machine learning...",
                "context_chunks": [
                    {
                        "rank": 1,
                        "text": "Deep learning is inspired by biological neural networks...",
                        "distance": 0.15,
                        "cross_encoder_score": 8.5,
                        "metadata": {"source": "deep_learning_guide.md", "doc_id": "doc_1"}
                    }
                ],
                "intent_analysis": {"is_kb_relevant": True, "keywords": ["deep learning", "fundamentals"]},
                "llm_api_used": True
            }
        }


class StatusResponse(BaseModel):
    """Response model for pipeline status."""
    status: str  # overall pipeline status
    kb_documents: int  # total documents in knowledge base
    kb_topics: List[str]  # top keywords/topics in the KB
    
    class Config:
        json_schema_extra = {
            "example": {
                "status": "ready",
                "kb_documents": 3,
                "kb_topics": ["machine learning", "deep learning", "neural networks"]
            }
        }


# ============================================================================
# Global Pipeline Components
# ============================================================================

app = FastAPI(
    title="RAG Pipeline API",
    description="""
# RAG Pipeline API - Retrieval Augmented Generation System

A production-grade API for document ingestion, semantic search, and question-answering using cross-encoder re-ranking and LLM integration.

## Features
- **Multi-format document support**: PDF, Word, Markdown, HTML, CSV, JSON, and more (via MarkItdown)
- **Intelligent chunking**: Configurable text segmentation with overlap
- **Semantic embeddings**: All-MiniLM-L6-v2 model for fast, accurate embeddings
- **Cross-encoder re-ranking**: MS-Marco cross-encoder for improved retrieval quality
- **Intent analysis**: Automatic KB relevance checking for each query
- **LLM integration**: Context-aware answer generation with external LLM API

## Quick Start

### 1. Ingest Documents
POST `/api/ingest` with a file path or URL to add documents to the knowledge base.

```json
{
  "source_type": "file",
  "source": "./sample_docs/guide.pdf",
  "doc_id": "optional_custom_id"
}
```

### 2. Query the System
POST `/api/query` to ask questions and get answers grounded in your documents.

```json
{
  "query": "What are the key features?",
  "top_k": 5,
  "rerank_top_k": 3
}
```

### 3. Check Status
GET `/api/status` to see how many documents are in the KB and top topics.

## Architecture
- **Retriever**: ChromaDB vector store with DuckDB+Parquet persistence
- **Embedder**: Sentence-Transformers for semantic similarity
- **Reranker**: CrossEncoder for precision ranking
- **Intent Analyzer**: Relevance filtering to reduce hallucination
- **LLM Caller**: External LLM API (GPT-4o) for final answer generation

## Response Format
All responses include metadata, intent analysis, and cross-encoder scores for transparency and debugging.
    """,
    version="1.0.0",
    contact={
        "name": "RAG Pipeline Support",
        "url": "https://github.com/your-repo",
    },
    tags_metadata=[
        {
            "name": "Info",
            "description": "System information and status endpoints",
        },
        {
            "name": "Ingestion",
            "description": "Add documents to the knowledge base",
        },
        {
            "name": "Query",
            "description": "Search and query the knowledge base",
        },
    ],
)

# Initialize pipeline components
logger.info("Initializing RAG pipeline components...")
converter = DocumentConverter()
logger.info("✓ DocumentConverter initialized")

chunker = TextChunker(chunk_size=CHUNK_SIZE, overlap=CHUNK_OVERLAP)
logger.info(f"✓ TextChunker initialized (chunk_size={CHUNK_SIZE}, overlap={CHUNK_OVERLAP})")

embedder = Embedder(model_name="all-MiniLM-L6-v2")
logger.info("✓ Embedder initialized (all-MiniLM-L6-v2)")

retriever = Retriever(persist_dir=str(CHROMA_DB_DIR), collection_name="documents")
logger.info(f"✓ Retriever initialized (persist_dir={CHROMA_DB_DIR})")

reranker = CrossEncoderReranker(model_name="cross-encoder/ms-marco-MiniLM-L-12-v2")
logger.info("✓ CrossEncoderReranker initialized")

grounded_qa_client = GroundedQAClient(
    base_url=COPILOT_API_BASE_URL,
    endpoint=GROUNDED_QA_ENDPOINT,
)
logger.info(f"✓ GroundedQAClient initialized ({COPILOT_API_BASE_URL}{GROUNDED_QA_ENDPOINT})")

intent_analyzer = IntentAnalyzer()
logger.info("✓ IntentAnalyzer initialized")

# Quality gates for runtime checks (used for abstention fallback)
quality_gates = QualityGates()
logger.info("✓ QualityGates initialized")

# Track processed documents
processed_docs: List[str] = []


# ============================================================================
# Helper Functions
# ============================================================================

def update_intent_baseline():
    """Update the intent analyzer baseline with current KB documents."""
    try:
        # Get current collection stats
        stats = retriever.get_collection_stats()
        if stats.get("count", 0) > 0:
            # Build baseline from processed documents
            intent_analyzer.build_baseline(processed_docs)
            logger.info(f"Intent baseline updated: {len(processed_docs)} documents")
    except Exception as e:
        logger.error(f"Error updating intent baseline: {e}", exc_info=True)


def ingest_document(source_type: str, source: str, doc_id: Optional[str]) -> tuple[str, int]:
    """
    Ingest a document, chunk it, embed it, and store in vector DB.

    Returns:
        Tuple of (doc_id, chunks_added)
    """
    # Convert document to markdown
    logger.info(f"Converting {source_type}: {source}")
    if source_type == "url":
        markdown_content = converter.convert_url(source)
    else:
        markdown_content = converter.convert_file(source)

    if not markdown_content:
        logger.error(f"Failed to convert {source}")
        raise ValueError(f"Failed to convert {source}")

    # Generate doc_id if not provided
    if not doc_id:
        doc_id = f"doc_{len(processed_docs)}_{hash(source) % 10000}"

    logger.info(f"Document ID: {doc_id}, Content length: {len(markdown_content)} chars")

    # Store converted content
    processed_docs.append(markdown_content)

    # Chunk the content
    logger.info(f"Chunking document: {doc_id}")
    chunks = chunker.chunk(markdown_content, method="sentences")

    if not chunks:
        logger.warning(f"No chunks generated for {doc_id}")
        return doc_id, 0

    logger.info(f"Generated {len(chunks)} chunks")

    # Embed chunks
    logger.info(f"Embedding {len(chunks)} chunks")
    embeddings = embedder.embed_texts(chunks)
    logger.info(f"Successfully embedded {len(embeddings)} chunks")

    # Prepare metadata
    metadatas = [
        {
            "source": source,
            "source_type": source_type,
            "doc_id": doc_id,
            "chunk_index": i,
        }
        for i in range(len(chunks))
    ]

    # Generate IDs
    chunk_ids = [f"{doc_id}_chunk_{i}" for i in range(len(chunks))]

    # Store in vector DB (pass embeddings to prevent ChromaDB from trying to download models)
    logger.info(f"Storing {len(chunks)} chunks in vector DB")
    retriever.add_documents(
        documents=chunks,
        embeddings=embeddings,
        metadatas=metadatas,
        ids=chunk_ids,
    )

    # Note: PersistentClient automatically persists data to disk
    logger.info(f"✓ Document ingested successfully: {doc_id} ({len(chunks)} chunks)")
    return doc_id, len(chunks)


# ============================================================================
# API Endpoints
# ============================================================================

@app.get("/", tags=["Info"])
async def root():
    """Root endpoint - API overview and available endpoints.
    
    Returns a summary of the API and links to key endpoints.
    """
    return {
        "name": "RAG Pipeline API",
        "version": "1.0.0",
        "status": "operational",
        "endpoints": {
            "docs": "/docs - Interactive Swagger UI",
            "redoc": "/redoc - ReDoc documentation",
            "ingest": "POST /api/ingest - Add documents to KB",
            "ingest_batch": "POST /api/ingest-batch - Batch upload multiple files",
            "query": "POST /api/query - Query the knowledge base",
            "status": "GET /api/status - Check KB and pipeline status",
        },
        "examples": {
            "ingest": {"source_type": "file", "source": "./docs/guide.pdf"},
            "query": {"query": "What are the main topics?", "top_k": 5, "rerank_top_k": 3},
        }
    }


@app.post("/api/ingest", response_model=IngestResponse, tags=["Ingestion"])
async def ingest(request: IngestRequest, background_tasks: BackgroundTasks):
    """Ingest a document from file or URL.
    
    ## Steps performed:
    1. **Convert**: Converts document to markdown (supports 30+ formats)
    2. **Chunk**: Splits text into semantic chunks (default: 512 tokens with 64-token overlap)
    3. **Embed**: Generates embeddings using all-MiniLM-L6-v2 model
    4. **Store**: Persists embeddings and metadata to ChromaDB vector store
    5. **Index**: Updates intent analyzer baseline
    
    ## Parameters:
    - **source_type**: 'file' (local path) or 'url' (web address)
    - **source**: File path or URL to ingest
    - **doc_id**: (Optional) Custom identifier; auto-generated if omitted
    
    ## Supported formats:
    PDF, Word (.docx, .doc), Markdown, HTML, CSV, JSON, Excel, JSON, and more.
    
    ## Example response:
    ```json
    {
      "status": "success",
      "message": "Document ingested with 12 chunks",
      "doc_id": "doc_0_5234",
      "chunks_added": 12
    }
    ```
    """
    try:
        doc_id, chunks_added = ingest_document(
            request.source_type,
            request.source,
            request.doc_id,
        )

        # Update intent baseline in background
        background_tasks.add_task(update_intent_baseline)

        return IngestResponse(
            status="success",
            message=f"Document ingested with {chunks_added} chunks",
            doc_id=doc_id,
            chunks_added=chunks_added,
        )

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/query", response_model=QueryResponse, tags=["Query"])
async def query(request: QueryRequest):
    """Query the RAG system with intelligent re-ranking.
    
    ## Processing pipeline:
    1. **Intent Analysis**: Checks if query is relevant to KB content
    2. **Retrieval**: Retrieves top-k documents using semantic similarity
    3. **Re-ranking**: Cross-encoder model re-ranks for relevance (more accurate)
    4. **Context Preparation**: Formats documents with source attribution
    5. **LLM Generation**: Calls LLM API with context to generate answer
    
    ## Parameters:
    - **query**: Your question or search query
    - **top_k**: Initial documents to retrieve (5-20 recommended; default: 5)
    - **rerank_top_k**: Final documents after re-ranking (2-5 recommended; default: 3)
    
    ## Response includes:
    - **answer**: LLM-generated answer grounded in KB
    - **context_chunks**: Retrieved documents with:
      - `distance`: Vector similarity (lower is better)
      - `cross_encoder_score`: Relevance score by cross-encoder (higher is better)
      - `metadata`: Source document info
    - **intent_analysis**: Query relevance check and extracted keywords
    - **llm_api_used**: Whether external LLM was called successfully
    
    ## Tips:
    - Use natural language questions (e.g., "What is X?", "How do I...?")
    - Increase top_k if results are poor
    - Check context_chunks to verify sources
    - If KB is small, query results may be limited
    """
    try:
        request_id = request.request_id or f"qa_{uuid.uuid4().hex}"
        model_requested = request.model or DEFAULT_GROUNDED_MODEL
        answer_policy = request.answer_policy if request.answer_policy is not None else DEFAULT_GROUNDED_ANSWER_POLICY
        generation_options = request.generation_options if request.generation_options is not None else DEFAULT_GROUNDED_GENERATION_OPTIONS

        result = run_grounded_query(
            query=request.query,
            top_k=request.top_k,
            rerank_top_k=request.rerank_top_k,
            intent_analyzer=intent_analyzer,
            embedder=embedder,
            retriever=retriever,
            reranker=reranker,
            qa_client=grounded_qa_client,
            quality_gates=quality_gates,
            request_id=request_id,
            model=model_requested,
            answer_policy=answer_policy,
            generation_options=generation_options,
            logger_instance=logger,
        )

        logger.info(
            "Query request %s finished: endpoint=%s, model=%s, chunks=%d, result_status=%s, failure_class=%s, abstained=%s, gateway_http_status=%s, provider_http_status=%s, failure_reason=%s",
            result.request_id,
            f"{COPILOT_API_BASE_URL}{GROUNDED_QA_ENDPOINT}",
            result.model_requested,
            len(result.context_chunks),
            result.result_status,
            result.failure_class,
            result.abstained,
            result.gateway_http_status,
            result.provider_http_status,
            result.generation_failure_reason,
        )

        response_payload = normalize_grounded_query_response_payload(result.to_dict())
        return QueryResponse(**response_payload)

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/status", response_model=StatusResponse, tags=["Info"])
async def status():
    """Check the pipeline status and knowledge base statistics.
    
    ## Returns:
    - **status**: Overall system status ("ready", "busy", etc.)
    - **kb_documents**: Total unique documents in the knowledge base
    - **kb_topics**: Top keywords/topics extracted from the KB (helps understand content)
    
    ## Use cases:
    - Verify the API is running before ingesting/querying
    - Check how many documents are loaded
    - Get an overview of KB topics to ensure relevant documents exist
    """
    try:
        stats = retriever.get_collection_stats()
        baseline_info = intent_analyzer.get_baseline_info()

        return StatusResponse(
            status="ready",
            kb_documents=stats.get("count", 0),
            kb_topics=baseline_info.get("top_keywords", [])[:10],
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/ingest-batch", tags=["Ingestion"])
async def ingest_batch(files: List[UploadFile] = File(...), background_tasks: BackgroundTasks = None):
    """Ingest multiple files at once (bulk upload).
    
    ## How to use in Swagger:
    1. Click "Try it out"
    2. Click "Select files" to choose multiple documents
    3. Click "Execute" to upload all files
    
    ## Processing:
    - Each file is processed independently
    - Failed files don't block others (partial success possible)
    - All files are converted, chunked, and embedded in parallel
    - Results include success/failure status for each file
    
    ## Response format:
    ```json
    {
      "results": [
        {"filename": "guide.pdf", "status": "success", "doc_id": "guide_001", "chunks_added": 15},
        {"filename": "faq.md", "status": "success", "doc_id": "faq_001", "chunks_added": 8}
      ],
      "total": 2,
      "succeeded": 2
    }
    ```
    
    ## Tips:
    - Supports any format that MarkItdown supports (PDF, Word, HTML, etc.)
    - Total file size should be reasonable (avoid ingesting 100s of large PDFs at once)
    - Check the results array for individual file status
    """
    results = []

    for file in files:
        try:
            # Save uploaded file temporarily
            with tempfile.NamedTemporaryFile(delete=False, suffix=Path(file.filename).suffix) as tmp:
                contents = await file.read()
                tmp.write(contents)
                tmp_path = tmp.name

            try:
                doc_id, chunks_added = ingest_document(
                    "file",
                    tmp_path,
                    doc_id=file.filename,
                )
                results.append({
                    "filename": file.filename,
                    "status": "success",
                    "doc_id": doc_id,
                    "chunks_added": chunks_added,
                })
            finally:
                # Clean up temp file
                os.unlink(tmp_path)

        except Exception as e:
            results.append({
                "filename": file.filename,
                "status": "error",
                "message": str(e),
            })

    # Update intent baseline
    if background_tasks:
        background_tasks.add_task(update_intent_baseline)

    return {"results": results, "total": len(files), "succeeded": sum(1 for r in results if r["status"] == "success")}


# ============================================================================
# Startup and Shutdown
# ============================================================================

@app.on_event("startup")
async def startup_event():
    """Initialize intent analyzer on startup."""
    logger.info("RAG Pipeline API starting up...")
    if processed_docs:
        update_intent_baseline()


if __name__ == "__main__":
    logger.info("="*80)
    logger.info("RAG Pipeline API Server Starting")
    logger.info("="*80)
    logger.info(f"Host: {API_HOST}")
    logger.info(f"Port: {API_PORT}")
    logger.info(f"Docs URL: http://localhost:{API_PORT}/docs")
    logger.info(f"Log file: {API_LOG_FILE}")
    logger.info(f"ChromaDB: {CHROMA_DB_DIR}")
    logger.info("="*80)
    
    uvicorn.run(
        app,
        host=API_HOST,
        port=API_PORT,
        log_level="info",
    )
