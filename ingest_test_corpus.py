#!/usr/bin/env python3
"""
Ingest synthetic test corpus into Chroma for evaluation testing.

This creates a clean test corpus that allows evaluation methodology validation
without being blocked by real corpus ingestion issues.
"""

import sys
import json
from pathlib import Path
import logging

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent


def split_into_chunks(text: str, chunk_size: int = 512, overlap: int = 64) -> list:
    """Split text into overlapping chunks."""
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start = end - overlap if end < len(text) else end
    return chunks


def ingest_test_corpus():
    """Ingest synthetic test corpus into Chroma."""
    
    # Import here to avoid issues if dependencies aren't available
    try:
        import chromadb
    except ImportError as e:
        logger.error(f"Required package not available: {e}")
        logger.error("Please install: pip install chromadb")
        return False
    
    import random
    import numpy as np
    
    # Read test corpus
    corpus_file = ROOT / "test_corpus.md"
    if not corpus_file.exists():
        logger.error(f"Test corpus not found: {corpus_file}")
        return False
    
    corpus_text = corpus_file.read_text(encoding='utf-8')
    logger.info(f"Loaded test corpus: {len(corpus_text)} characters")
    
    # Initialize Chroma client
    chroma_dir = ROOT / "chroma_db_test"
    chroma_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        client = chromadb.PersistentClient(path=str(chroma_dir))
        logger.info(f"Initialized Chroma client at {chroma_dir}")
    except Exception as e:
        logger.error(f"Failed to initialize Chroma: {e}")
        return False
    
    # Create or get collection
    collection_name = "test_corpus"
    try:
        # Delete existing collection if it exists (for fresh start)
        existing = client.list_collections()
        existing_names = [c.name for c in existing]
        if collection_name in existing_names:
            client.delete_collection(name=collection_name)
            logger.info(f"Deleted existing collection: {collection_name}")
        
        collection = client.create_collection(
            name=collection_name,
            metadata={"description": "Test corpus for evaluation methodology validation"}
        )
        logger.info(f"Created collection: {collection_name}")
    except Exception as e:
        logger.error(f"Failed to create collection: {e}")
        return False
    
    # Split corpus into chunks
    chunks = split_into_chunks(corpus_text, chunk_size=512, overlap=64)
    logger.info(f"Split corpus into {len(chunks)} chunks")
    
    # Add chunks with random embeddings (for testing retrieval logic, not embedding quality)
    try:
        logger.info("Adding chunks with random embeddings...")
        chunk_ids = []
        embeddings = []
        metadatas = []
        
        # Use random embeddings for testing (384-dimensional like MiniLM)
        embedding_dim = 384
        
        for i, chunk in enumerate(chunks):
            chunk_id = f"chunk_{i:04d}"
            chunk_ids.append(chunk_id)
            
            # Generate random embedding (for testing, actual embeddings not critical)
            embedding = [random.uniform(-1, 1) for _ in range(embedding_dim)]
            embeddings.append(embedding)
            
            # Metadata
            metadatas.append({
                "chunk_index": i,
                "doc_id": "test_corpus",
                "source": "test_corpus.md",
                "source_type": "test",
                "text_length": len(chunk)
            })
        
        # Add to collection in batches
        batch_size = 100
        for batch_start in range(0, len(chunk_ids), batch_size):
            batch_end = min(batch_start + batch_size, len(chunk_ids))
            batch_ids = chunk_ids[batch_start:batch_end]
            batch_embeddings = embeddings[batch_start:batch_end]
            batch_metadatas = metadatas[batch_start:batch_end]
            batch_documents = chunks[batch_start:batch_end]
            
            collection.add(
                ids=batch_ids,
                embeddings=batch_embeddings,
                documents=batch_documents,
                metadatas=batch_metadatas
            )
            logger.info(f"Added batch {batch_start//batch_size + 1}: chunks {batch_start}-{batch_end}")
        
        logger.info(f"Successfully added {len(chunk_ids)} chunks to collection")
        
        # Verify
        count = collection.count()
        logger.info(f"Collection now contains {count} items")
        
        # Test retrieval (with random embedding for test query)
        test_query = "What is Aurora WP3.1?"
        test_embedding = [random.uniform(-1, 1) for _ in range(embedding_dim)]
        results = collection.query(query_embeddings=[test_embedding], n_results=3)
        
        logger.info(f"Test query: '{test_query}'")
        logger.info(f"Retrieved {len(results['documents'][0])} results (random order due to random embeddings)")
        for i, doc in enumerate(results['documents'][0]):
            logger.info(f"  Result {i+1}: {doc[:80]}...")
        
        logger.warning("NOTE: Retrieved chunks are in random order because embeddings are random.")
        logger.warning("This is fine for testing retrieval logic - real queries would use semantic embeddings.")
        
        return True
        
    except Exception as e:
        logger.error(f"Failed to add chunks to collection: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Main entry point."""
    logger.info("=" * 80)
    logger.info("TEST CORPUS INGESTION")
    logger.info("=" * 80)
    
    success = ingest_test_corpus()
    
    logger.info("=" * 80)
    if success:
        logger.info("TEST CORPUS INGESTION SUCCESSFUL")
        logger.info("Test corpus is ready for evaluation")
        logger.info("")
        logger.info("To use this corpus for testing:")
        logger.info("1. Modify grounded_qa.py or API to use 'chroma_db_test' instead of 'chroma_db'")
        logger.info("2. Re-run run_comprehensive_tests.py")
        logger.info("3. Expected: Higher pass rate due to clean corpus")
        return 0
    else:
        logger.error("TEST CORPUS INGESTION FAILED")
        logger.error("Check logs above for details")
        return 1


if __name__ == "__main__":
    sys.exit(main())
