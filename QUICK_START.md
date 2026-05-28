# RAG Pipeline - Quick Start Guide

## 📋 Prerequisites
- Python 3.11+ installed
- 8.58 MB PDF document (AUTOSAR/ADD Software Sharing)
- VS Code or any text editor

## 🚀 Quick Start (5 minutes)

### Step 1: Activate Virtual Environment
```powershell
cd C:\Users\DIH8HC\ThanhDC\1.Project\97.Dev_for_learn\20.Markitdown\markitdown
.\.venv\Scripts\Activate.ps1
```

### Step 2: Run the Demo
```powershell
cd src
$env:PYTHONIOENCODING = "utf-8"
python test_autosar_full.py
```

**Expected Output**:
```
================================================================================
ENHANCED RAG PIPELINE - AUTOSAR DOCUMENT PROCESSING
================================================================================

[1] Converting PDF to Markdown...
[OK] Converted: AUTOSAR Document
[OK] Content length: 84,276 characters

[2] Chunking document with intelligent strategy...
[OK] Created 330 chunks

[3] Generating embeddings...
[OK] Generated 330 embeddings

[4] Storing in ChromaDB...
[OK] Stored 330 chunks in ChromaDB

[5] Building intent analyzer baseline...
[OK] Baseline built with 1672 terms

[6] Testing queries with retrieval...
Query 1: What is the main goal of AUTOSAR?
    Intent Type: question
    Relevance Score: 40.00%
    Top 3 Retrieved Chunks: [Similarities: 0.887, 0.880, 0.878]
```

### Step 3: View Results
```powershell
# View summary
Get-Content ..\chroma_db\autosar_summary_*.json

# View logs
Get-Content ..\logs\demo_*.log -Tail 100
```

## 🔧 Configuration Changes

### Change API Port (from 8001)
Edit `src/config.py`:
```python
API_PORT = 8002  # Change to any available port
```

### Change Chunk Size
Edit `src/config.py`:
```python
CHUNK_SIZE = 256  # Smaller chunks for finer detail
# or
CHUNK_SIZE = 1024  # Larger chunks for broader context
```

### Process Different Document
Edit `src/test_autosar_full.py`:
```python
pdf_path = r"C:\Path\To\Your\Document.pdf"
```

## 📊 Results Summary

| Metric | Value |
|--------|-------|
| **Document Size** | 8.58 MB |
| **Converted Content** | 84,276 characters |
| **Total Chunks** | 330 |
| **Unique Terms** | 1,672 |
| **Query Success Rate** | 100% (5/5) |
| **Avg Similarity Score** | 0.917 |
| **Processing Time** | ~3 seconds |

## 🧪 Test Queries (Built-in)

```
1. "What is the main goal of AUTOSAR?"                              → 40% relevance ✓
2. "Why was AUTOSAR created?"                                       → 25% relevance ✓
3. "What problem does AUTOSAR try to solve?"                        → 17% relevance ✓
4. "What is the purpose of a standardized software architecture?"   → 43% relevance ✓
5. "What does AUTOSAR aim to improve in automotive ECUs?"           → 14% relevance ✓
```

## 🌐 API Server (Advanced)

### Start the API Server
```powershell
.\start_api.ps1
```

**Server starts at**: `http://localhost:8001`  
**Swagger UI**: `http://localhost:8001/docs`

### Test with Swagger UI
1. Open `http://localhost:8001/docs`
2. Click "Try it out" on any endpoint
3. Enter test parameters
4. Click "Execute"

### Example API Calls

**Ingest Document**:
```bash
curl -X POST "http://localhost:8001/api/ingest" \
  -H "Content-Type: application/json" \
  -d '{
    "source_type": "file",
    "source": "C:\\path\\to\\document.pdf",
    "doc_id": "my_doc"
  }'
```

**Query the KB**:
```bash
curl -X POST "http://localhost:8001/api/query" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What is the main goal?",
    "top_k": 5,
    "rerank_top_k": 3
  }'
```

**Check Status**:
```bash
curl -X GET "http://localhost:8001/api/status"
```

## 📁 File Structure

```
markitdown/
├── .venv/                          # Virtual environment
├── src/
│   ├── config.py                   # Configuration (PORT: 8001)
│   ├── api.py                      # FastAPI server (with logging)
│   ├── test_autosar_full.py        # Demo script (with logging)
│   ├── rag_pipeline/
│   │   ├── converter.py            # Document conversion
│   │   ├── chunker.py              # Text chunking
│   │   ├── embedder.py             # Vector embeddings
│   │   ├── retriever.py            # ChromaDB storage
│   │   ├── intent_analyzer.py      # Query analysis
│   │   ├── reranker.py             # Re-ranking (ready)
│   │   └── llm_caller.py           # LLM integration (ready)
│   └── requirements.txt            # Dependencies
├── chroma_db/
│   ├── autosar_doc.json            # Embedded document
│   └── autosar_summary_*.json      # Results summary
├── logs/
│   ├── demo_*.log                  # Demo execution logs
│   └── api_*.log                   # API server logs
├── start_api.ps1                   # Startup script (Windows)
├── start_api.sh                    # Startup script (Unix)
└── IMPLEMENTATION_SUMMARY.md       # Full documentation
```

## 🔍 Logging Features

### What Gets Logged
- ✅ Document conversion progress
- ✅ Chunking statistics
- ✅ Embedding generation
- ✅ Storage operations
- ✅ Query processing
- ✅ Retrieval results
- ✅ Error stack traces
- ✅ Timestamps and line numbers

### View Logs
```powershell
# Real-time tail
Get-Content -Path logs/demo_*.log -Tail 20 -Wait

# Search for specific message
Get-Content logs/demo_*.log | Select-String "ERROR"

# Full log with line numbers
Get-Content logs/demo_*.log | Select-String ".*" | Select -First 100
```

## 🛠️ Environment Management

### Reset Everything
```powershell
# Remove virtual environment
Remove-Item -Recurse .venv

# Remove database
Remove-Item -Recurse chroma_db

# Remove logs
Remove-Item -Recurse logs

# Create fresh venv
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r src/requirements.txt
```

## ✅ Troubleshooting

| Issue | Solution |
|-------|----------|
| `ModuleNotFoundError: No module named 'markitdown'` | Run: `pip install -e packages/markitdown` |
| Port 8001 already in use | Edit `src/config.py` and change `API_PORT` |
| Encoding errors in output | Set: `$env:PYTHONIOENCODING = "utf-8"` |
| Missing venv | Run: `python -m venv .venv` |
| Logs not appearing | Check `./logs/` directory exists and is writable |

## 📞 Support

For detailed information, see:
- `IMPLEMENTATION_SUMMARY.md` - Full documentation
- `src/config.py` - Configuration reference
- `src/test_autosar_full.py` - Demo implementation
- Log files - `./logs/demo_*.log`

---

**Status**: ✅ Production Ready  
**Last Updated**: 2026-05-27
