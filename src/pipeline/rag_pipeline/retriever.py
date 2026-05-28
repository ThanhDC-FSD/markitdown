"""Vector store retrieval using ChromaDB."""

from typing import List, Tuple, Optional
import chromadb
from pathlib import Path
import ssl
import urllib3
import logging

# Disable SSL verification for ChromaDB operations
urllib3.disable_warnings()
ssl._create_default_https_context = ssl._create_unverified_context

logger = logging.getLogger(__name__)


class Retriever:
    """Retrieve relevant documents from ChromaDB vector store."""

    def __init__(self, persist_dir: str = "./chroma_db", collection_name: str = "documents"):
        """
        Initialize the retriever with ChromaDB.

        Args:
            persist_dir: Directory to persist ChromaDB data
            collection_name: Name of the collection to use
        """
        self.persist_dir = persist_dir
        self.collection_name = collection_name

        # Ensure persist_dir exists
        Path(persist_dir).mkdir(parents=True, exist_ok=True)

        # Initialize ChromaDB with new PersistentClient API (compatible with latest Chroma)
        self.client = chromadb.PersistentClient(path=persist_dir)
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"}
        )

    def add_documents(
        self,
        documents: List[str],
        embeddings: Optional[List[List[float]]] = None,
        metadatas: Optional[List[dict]] = None,
        ids: Optional[List[str]] = None,
    ) -> None:
        """
        Add documents to the vector store.

        Args:
            documents: List of document texts
            embeddings: Optional list of pre-computed embeddings. If provided, ChromaDB won't try to download models.
            metadatas: Optional list of metadata dictionaries
            ids: Optional list of unique IDs for documents
        """
        if not documents:
            return

        # Generate IDs if not provided
        if ids is None:
            ids = [f"doc_{i}" for i in range(len(documents))]

        # Use empty metadata if not provided
        if metadatas is None:
            metadatas = [{} for _ in documents]

        # Add to collection
        try:
            logger.info(f"Adding {len(documents)} documents to ChromaDB...")
            
            if embeddings is not None:
                # If embeddings provided, add them to prevent ChromaDB from downloading models
                self.collection.add(
                    ids=ids,
                    documents=documents,
                    embeddings=embeddings,
                    metadatas=metadatas,
                )
            else:
                # Without embeddings, ChromaDB will try to auto-embed (may fail with SSL errors)
                self.collection.add(
                    ids=ids,
                    documents=documents,
                    metadatas=metadatas,
                )
            logger.info(f"Successfully added {len(documents)} documents")
        except Exception as e:
            logger.error(f"Error adding documents to ChromaDB: {str(e)}", exc_info=True)
            raise

    def retrieve(
        self,
        query: str,
        query_embedding: Optional[List[float]] = None,
        top_k: int = 5,
    ) -> List[Tuple[str, float, dict]]:
        """
        Retrieve top-k most relevant documents for a query.

        Args:
            query: Query text
            query_embedding: Optional pre-computed embedding for the query. If provided, avoids auto-embedding.
            top_k: Number of results to retrieve

        Returns:
            List of tuples (document_text, distance, metadata)
        """
        try:
            if query_embedding is not None:
                # Use pre-computed embedding to avoid SSL issues with auto-embedding
                results = self.collection.query(
                    query_embeddings=[query_embedding],
                    n_results=top_k,
                )
            else:
                # Without embedding, ChromaDB will try to auto-embed (may fail with SSL errors)
                results = self.collection.query(
                    query_texts=[query],
                    n_results=top_k,
                )

            if not results or not results["documents"] or len(results["documents"][0]) == 0:
                return []

            retrieved = []
            for i, doc in enumerate(results["documents"][0]):
                distance = results["distances"][0][i] if results.get("distances") else 0.0
                metadata = results["metadatas"][0][i] if results.get("metadatas") else {}
                retrieved.append((doc, distance, metadata))

            return retrieved
        except Exception as e:
            logger.error(f"Error retrieving documents: {e}", exc_info=True)
            return []

    def persist(self) -> None:
        """Persist the collection to disk."""
        self.client.persist()

    def get_collection_stats(self) -> dict:
        """
        Get statistics about the collection.

        Returns:
            Dictionary with collection stats
        """
        try:
            count = self.collection.count()
            return {"count": count, "collection_name": self.collection_name}
        except Exception as e:
            print(f"Error getting collection stats: {e}")
            return {}
