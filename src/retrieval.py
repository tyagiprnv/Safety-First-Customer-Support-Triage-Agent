"""Retrieval pipeline for RAG."""
from typing import List, Optional
from dataclasses import dataclass
from src.vector_store import get_vector_store
from src.models import Intent
from src.config import get_settings


@dataclass
class RetrievalResult:
    """Result from document retrieval."""
    chunks: List[str]
    scores: List[float]
    sources: List[dict]
    average_score: float

    @property
    def has_good_retrieval(self) -> bool:
        """Check if retrieval quality is good enough."""
        settings = get_settings()
        return self.average_score >= settings.min_retrieval_score


class RetrievalPipeline:
    """Pipeline for retrieving relevant context from knowledge base."""

    def __init__(self):
        """Initialize retrieval pipeline."""
        self.vector_store = get_vector_store()
        settings = get_settings()
        self.top_k = settings.top_k_retrieval
        self.min_score = settings.min_retrieval_score

    def retrieve(
        self,
        query: str,
        intent: Intent,
        top_k: Optional[int] = None
    ) -> Optional[RetrievalResult]:
        """
        Retrieve relevant context for a query.

        Args:
            query: User query (redacted)
            intent: Classified intent
            top_k: Number of documents to retrieve (defaults to config)

        Returns:
            RetrievalResult or None if retrieval quality is poor
        """
        if top_k is None:
            top_k = self.top_k

        # Map intent to metadata filter if applicable
        filter_metadata = self._get_intent_filter(intent)

        # Search vector store
        results = self.vector_store.search(
            query=query,
            top_k=top_k,
            filter_metadata=filter_metadata
        )

        if not results:
            return None

        # Convert distance to similarity score (ChromaDB uses L2 distance)
        # Lower distance = higher similarity
        # Convert to 0-1 scale where 1 is perfect match
        scores = [max(0.0, 1.0 - (result['distance'] / 2.0)) for result in results]

        # Calculate average score
        avg_score = sum(scores) / len(scores) if scores else 0.0

        # Check if retrieval quality meets threshold
        if avg_score < self.min_score:
            return None

        # Extract chunks and sources
        chunks = [result['document'] for result in results]
        sources = [result['metadata'] for result in results]

        return RetrievalResult(
            chunks=chunks,
            scores=scores,
            sources=sources,
            average_score=avg_score
        )

    def _get_intent_filter(self, intent: Intent) -> Optional[dict]:
        """
        Get metadata filter based on intent.

        Args:
            intent: Classified intent

        Returns:
            Metadata filter dict or None
        """
        # Map intents to document categories
        # Note: Categories must match what's in the knowledge base ingestion
        intent_to_category = {
            Intent.BILLING_QUESTION: "billing",
            Intent.SUBSCRIPTION_INFO: "subscription",
            Intent.ACCOUNT_ACCESS: "account",
            Intent.FEATURE_QUESTION: "features",
            Intent.TECHNICAL_SUPPORT: "technical",
            Intent.POLICY_QUESTION: "general",  # general_faqs.json contains policy questions
        }

        category = intent_to_category.get(intent)
        if category:
            return {"category": category}

        return None


# Global instance
_retrieval_pipeline: Optional[RetrievalPipeline] = None


def get_retrieval_pipeline() -> RetrievalPipeline:
    """Get the global retrieval pipeline instance."""
    global _retrieval_pipeline
    if _retrieval_pipeline is None:
        _retrieval_pipeline = RetrievalPipeline()
    return _retrieval_pipeline
