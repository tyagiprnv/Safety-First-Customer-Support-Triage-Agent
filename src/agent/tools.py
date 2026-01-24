"""LangChain tools for agent reasoning.

These tools wrap existing modules to enable LLM-based tool selection.
"""
from typing import Dict, Any, Optional
from langchain_core.tools import tool
import structlog

from src.intent_classifier import get_intent_classifier
from src.decision_router import get_decision_router
from src.retrieval import get_retrieval_pipeline
from src.models import Intent, RedactionResult

logger = structlog.get_logger(__name__)


@tool
def intent_classifier_tool(query: str, has_pii: bool = False) -> Dict[str, Any]:
    """
    Classify customer support query intent with confidence score.

    This tool analyzes the customer's message and determines their intent
    (e.g., billing question, refund request, technical support).

    Args:
        query: The customer's message (possibly redacted)
        has_pii: Whether PII was detected in the original message

    Returns:
        Dictionary with intent, confidence, and whether it's forbidden
    """
    logger.info("intent_classifier_tool_called", has_pii=has_pii)

    try:
        # Create a minimal RedactionResult for the classifier
        redaction = RedactionResult(
            redacted_message=query,
            pii_metadata=[],
            has_high_risk_pii=False,
            redaction_count=0
        )

        classifier = get_intent_classifier()
        classification = classifier.classify(redaction)

        result = {
            "intent": classification.intent.value,
            "confidence": classification.confidence,
            "adjusted_confidence": classification.adjusted_confidence,
            "is_forbidden": classification.is_forbidden,
            "reasoning": classification.reasoning or "No reasoning provided"
        }

        logger.info(
            "intent_classifier_tool_result",
            intent=result["intent"],
            confidence=result["confidence"],
            is_forbidden=result["is_forbidden"]
        )

        return result

    except Exception as e:
        logger.error("intent_classifier_tool_error", error=str(e), exc_info=True)
        return {
            "intent": "unknown",
            "confidence": 0.0,
            "adjusted_confidence": 0.0,
            "is_forbidden": False,
            "reasoning": f"Error: {str(e)}"
        }


@tool
def template_retrieval_tool(
    query: str,
    intent: str,
    confidence: float
) -> Optional[Dict[str, Any]]:
    """
    Find matching pre-written template for common questions.

    This tool searches for a template that matches the customer's question.
    Templates are pre-vetted, safe responses for frequently asked questions.

    Args:
        query: The customer's message (possibly redacted)
        intent: The classified intent (e.g., "billing_question")
        confidence: Classification confidence score

    Returns:
        Dictionary with template info if match found, None otherwise
    """
    logger.info("template_retrieval_tool_called", intent=intent, confidence=confidence)

    try:
        # Convert intent string to Intent enum
        try:
            intent_enum = Intent(intent)
        except ValueError:
            logger.warning("template_retrieval_tool_invalid_intent", intent=intent)
            return None

        router = get_decision_router()
        template_match = router.template_store.find_best_match(
            message=query,
            intent=intent_enum,
            confidence=confidence
        )

        if template_match:
            template, match_score = template_match
            result = {
                "template_id": template.id,
                "template_text": template.template,
                "match_score": match_score,
                "intent": template.intent.value,
                "risk": template.risk
            }

            logger.info(
                "template_retrieval_tool_result",
                template_id=result["template_id"],
                match_score=result["match_score"]
            )

            return result

        logger.info("template_retrieval_tool_no_match")
        return None

    except Exception as e:
        logger.error("template_retrieval_tool_error", error=str(e), exc_info=True)
        return None


@tool
def knowledge_search_tool(
    query: str,
    intent: str,
    top_k: int = 3
) -> Dict[str, Any]:
    """
    Search knowledge base for relevant policy/FAQ documents.

    This tool performs semantic search over the knowledge base to find
    relevant context for answering the customer's question.

    Args:
        query: The customer's message (possibly redacted)
        intent: The classified intent (e.g., "subscription_info")
        top_k: Number of top results to retrieve (default: 3)

    Returns:
        Dictionary with retrieved chunks, scores, and sources
    """
    logger.info("knowledge_search_tool_called", intent=intent, top_k=top_k)

    try:
        # Convert intent string to Intent enum
        try:
            intent_enum = Intent(intent)
        except ValueError:
            logger.warning("knowledge_search_tool_invalid_intent", intent=intent)
            intent_enum = Intent.UNKNOWN

        pipeline = get_retrieval_pipeline()
        retrieval_result = pipeline.retrieve(
            query=query,
            intent=intent_enum,
            top_k=top_k
        )

        if not retrieval_result:
            logger.warning("knowledge_search_tool_no_results")
            return {
                "chunks": [],
                "scores": [],
                "average_score": 0.0,
                "sources": [],
                "has_good_retrieval": False
            }

        result = {
            "chunks": retrieval_result.chunks,
            "scores": retrieval_result.scores,
            "average_score": retrieval_result.average_score,
            "sources": retrieval_result.sources,
            "has_good_retrieval": retrieval_result.has_good_retrieval,
            "chunk_count": len(retrieval_result.chunks)
        }

        logger.info(
            "knowledge_search_tool_result",
            chunk_count=result["chunk_count"],
            average_score=result["average_score"],
            has_good_retrieval=result["has_good_retrieval"]
        )

        return result

    except Exception as e:
        logger.error("knowledge_search_tool_error", error=str(e), exc_info=True)
        return {
            "chunks": [],
            "scores": [],
            "average_score": 0.0,
            "sources": [],
            "has_good_retrieval": False,
            "error": str(e)
        }


# List of all available tools for agent
AGENT_TOOLS = [
    intent_classifier_tool,
    template_retrieval_tool,
    knowledge_search_tool
]
