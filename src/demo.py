"""Example script demonstrating the RAG pipeline."""

import requests
import json
from pathlib import Path


def demo_rag_pipeline():
    """Run a complete RAG pipeline demo."""

    print("=" * 80)
    print("RAG PIPELINE DEMO")
    print("=" * 80)

    # Configuration
    API_URL = "http://localhost:8000"
    SAMPLE_DOCS_DIR = "./sample_docs"

    # Step 1: Check API Status
    print("\n[1] Checking API Status...")
    try:
        response = requests.get(f"{API_URL}/api/status")
        status = response.json()
        print(f"  Status: {status['status']}")
        print(f"  Documents in KB: {status['kb_documents']}")
        print(f"  Top topics: {', '.join(status['kb_topics'][:5])}")
    except Exception as e:
        print(f"  Error: {e}")
        print("  Make sure the API is running at http://localhost:8000")
        return

    # Step 2: Ingest Sample Documents
    print("\n[2] Ingesting Sample Documents...")

    sample_files = list(Path(SAMPLE_DOCS_DIR).glob("*.md"))
    if not sample_files:
        print(f"  No markdown files found in {SAMPLE_DOCS_DIR}")
        print(f"  Run: python crawler.py --mode sample")
        return

    ingested_count = 0
    for doc_path in sample_files:
        try:
            response = requests.post(
                f"{API_URL}/api/ingest",
                json={
                    "source_type": "file",
                    "source": str(doc_path),
                    "doc_id": doc_path.stem,
                }
            )
            result = response.json()
            if result["status"] == "success":
                print(f"  ✓ {doc_path.name}: {result['chunks_added']} chunks")
                ingested_count += 1
            else:
                print(f"  ✗ {doc_path.name}: {result.get('message', 'Unknown error')}")
        except Exception as e:
            print(f"  ✗ {doc_path.name}: {e}")

    print(f"  Total ingested: {ingested_count}/{len(sample_files)}")

    # Step 3: Check Updated Status
    print("\n[3] Updated KB Status...")
    try:
        response = requests.get(f"{API_URL}/api/status")
        status = response.json()
        print(f"  Documents in KB: {status['kb_documents']}")
        print(f"  Top topics: {', '.join(status['kb_topics'][:10])}")
    except Exception as e:
        print(f"  Error: {e}")

    # Step 4: Run Example Queries
    print("\n[4] Running Example Queries...\n")

    queries = [
        "What is machine learning?",
        "Explain the difference between supervised and unsupervised learning",
        "What are neural networks and how do they work?",
        "What is the purpose of the attention mechanism in transformers?",
        "What are the main applications of deep learning?",
    ]

    for i, query in enumerate(queries, 1):
        print(f"\n--- Query {i} ---")
        print(f"Q: {query}")

        try:
            response = requests.post(
                f"{API_URL}/api/query",
                json={
                    "query": query,
                    "top_k": 5,
                    "rerank_top_k": 3,
                }
            )

            if response.status_code == 200:
                result = response.json()

                # Print intent analysis
                intent = result["intent_analysis"]
                print(f"\nIntent Analysis:")
                print(f"  Type: {intent['intent_type']}")
                print(f"  Relevance: {intent['relevance_score']:.2%}")
                print(f"  KB Overlap: {intent['overlap_ratio']:.2%}")
                print(f"  Is KB Relevant: {intent['is_kb_relevant']}")

                # Print answer
                print(f"\nAnswer:")
                answer = result["answer"]
                # Truncate long answers
                if len(answer) > 300:
                    print(f"  {answer[:300]}...")
                else:
                    print(f"  {answer}")

                # Print context sources
                print(f"\nContext Sources:")
                for chunk in result["context_chunks"]:
                    print(f"  [{chunk['rank']}] Score: {chunk['cross_encoder_score']:.2f}, "
                          f"Distance: {chunk['distance']:.4f}")
                    print(f"      Source: {chunk['metadata'].get('source', 'unknown')}")
                    print(f"      Text: {chunk['text'][:80]}...")

            else:
                print(f"  Error: {response.status_code} - {response.text}")

        except Exception as e:
            print(f"  Error: {e}")

    print("\n" + "=" * 80)
    print("DEMO COMPLETED")
    print("=" * 80)
    print("\nNext Steps:")
    print("1. Visit http://localhost:8000/docs for Swagger UI")
    print("2. Try custom queries in the /api/query endpoint")
    print("3. Ingest more documents via /api/ingest-batch")
    print("4. Check API status at /api/status")


if __name__ == "__main__":
    demo_rag_pipeline()
