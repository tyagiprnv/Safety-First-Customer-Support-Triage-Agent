"""Vector store management using ChromaDB."""
import chromadb
from chromadb.config import Settings
from typing import List, Dict, Any, Optional
from pathlib import Path
import openai
from src.config import get_settings


class VectorStore:
    """ChromaDB wrapper for document storage and retrieval."""

    def __init__(self, persist_directory: Optional[str] = None):
        """
        Initialize ChromaDB vector store.

        Args:
            persist_directory: Directory for persistent storage
        """
        settings_config = get_settings()

        if persist_directory is None:
            persist_directory = settings_config.vector_db_path

        # Ensure directory exists
        Path(persist_directory).mkdir(parents=True, exist_ok=True)

        # Initialize ChromaDB client with persistence
        self.client = chromadb.PersistentClient(
            path=persist_directory,
            settings=Settings(
                anonymized_telemetry=False,
                allow_reset=True
            )
        )

        # Initialize OpenAI client for embeddings
        self.openai_client = openai.OpenAI(api_key=settings_config.openai_api_key)
        self.embedding_model = settings_config.embedding_model

        # Get or create collection
        self.collection = self.client.get_or_create_collection(
            name="knowledge_base",
            metadata={"description": "Customer support knowledge base"}
        )

    def add_documents(
        self,
        documents: List[str],
        metadatas: List[Dict[str, Any]],
        ids: List[str]
    ):
        """
        Add documents to the vector store.

        Args:
            documents: List of document texts
            metadatas: List of metadata dicts
            ids: List of unique document IDs
        """
        # Generate embeddings
        embeddings = self._get_embeddings(documents)

        # Add to collection
        self.collection.add(
            documents=documents,
            embeddings=embeddings,
            metadatas=metadatas,
            ids=ids
        )

    def search(
        self,
        query: str,
        top_k: int = 3,
        filter_metadata: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Search for relevant documents.

        Args:
            query: Search query
            top_k: Number of results to return
            filter_metadata: Optional metadata filter

        Returns:
            List of search results with documents and metadata
        """
        # Generate query embedding
        query_embedding = self._get_embeddings([query])[0]

        # Search collection
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=filter_metadata
        )

        # Format results
        formatted_results = []
        if results['documents']:
            for i, doc in enumerate(results['documents'][0]):
                formatted_results.append({
                    'document': doc,
                    'metadata': results['metadatas'][0][i] if results['metadatas'] else {},
                    'distance': results['distances'][0][i] if results['distances'] else 0.0,
                    'id': results['ids'][0][i] if results['ids'] else None
                })

        return formatted_results

    def count(self) -> int:
        """Get the number of documents in the collection."""
        return self.collection.count()

    def reset(self):
        """Reset the collection (delete all documents)."""
        self.client.delete_collection("knowledge_base")
        self.collection = self.client.get_or_create_collection(
            name="knowledge_base",
            metadata={"description": "Customer support knowledge base"}
        )

    def _get_embeddings(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for texts using OpenAI.

        Args:
            texts: List of texts to embed

        Returns:
            List of embedding vectors
        """
        response = self.openai_client.embeddings.create(
            model=self.embedding_model,
            input=texts
        )

        return [item.embedding for item in response.data]


# Global instance
_vector_store: Optional[VectorStore] = None


def get_vector_store() -> VectorStore:
    """Get the global vector store instance."""
    global _vector_store
    if _vector_store is None:
        _vector_store = VectorStore()
    return _vector_store
