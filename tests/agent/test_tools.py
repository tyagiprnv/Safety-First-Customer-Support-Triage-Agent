"""Unit tests for LangChain tools."""
import pytest
from src.agent.tools import (
    intent_classifier_tool,
    template_retrieval_tool,
    knowledge_search_tool,
    AGENT_TOOLS
)


class TestIntentClassifierTool:
    """Test intent classifier tool."""

    def test_intent_classifier_billing_question(self):
        """Test classification of a billing question."""
        result = intent_classifier_tool.invoke({
            "query": "Why was I charged twice this month?",
            "has_pii": False
        })

        assert "intent" in result
        assert "confidence" in result
        assert "is_forbidden" in result
        assert result["intent"] == "billing_question"
        assert result["confidence"] > 0.0
        assert result["is_forbidden"] is False

    def test_intent_classifier_refund_request(self):
        """Test classification of a refund request (forbidden)."""
        result = intent_classifier_tool.invoke({
            "query": "I want a refund for my last purchase",
            "has_pii": False
        })

        assert "intent" in result
        assert "is_forbidden" in result
        assert result["intent"] == "refund_request"
        assert result["is_forbidden"] is True

    def test_intent_classifier_with_pii(self):
        """Test classification with PII flag."""
        result = intent_classifier_tool.invoke({
            "query": "What are your business hours?",
            "has_pii": True
        })

        assert "intent" in result
        assert "confidence" in result
        # Should still work, just flagged
        assert result["confidence"] > 0.0

    def test_intent_classifier_error_handling(self):
        """Test error handling in classifier tool."""
        # Test with invalid input
        result = intent_classifier_tool.invoke({
            "query": "",
            "has_pii": False
        })

        # Should not crash, should return result or error
        assert "intent" in result


class TestTemplateRetrievalTool:
    """Test template retrieval tool."""

    def test_template_retrieval_business_hours(self):
        """Test template retrieval for business hours question."""
        result = template_retrieval_tool.invoke({
            "query": "What are your business hours?",
            "intent": "policy_question",
            "confidence": 0.9
        })

        # Should find a template or return None
        if result is not None:
            assert "template_id" in result
            assert "template_text" in result
            assert "match_score" in result
            assert result["match_score"] > 0.0

    def test_template_retrieval_no_match(self):
        """Test template retrieval with no matching template."""
        result = template_retrieval_tool.invoke({
            "query": "This is a very specific unique question that has no template",
            "intent": "unknown",
            "confidence": 0.5
        })

        # Should return None for no match
        assert result is None

    def test_template_retrieval_invalid_intent(self):
        """Test template retrieval with invalid intent."""
        result = template_retrieval_tool.invoke({
            "query": "What are your hours?",
            "intent": "invalid_intent_name",
            "confidence": 0.9
        })

        # Should handle gracefully and return None
        assert result is None

    def test_template_retrieval_low_confidence(self):
        """Test template retrieval with low confidence."""
        result = template_retrieval_tool.invoke({
            "query": "What are your business hours?",
            "intent": "policy_question",
            "confidence": 0.3  # Below typical threshold
        })

        # May not find template due to low confidence
        # Just verify it doesn't crash
        assert result is None or "template_id" in result


class TestKnowledgeSearchTool:
    """Test knowledge search tool."""

    def test_knowledge_search_subscription(self):
        """Test knowledge search for subscription question."""
        result = knowledge_search_tool.invoke({
            "query": "What are your subscription plans?",
            "intent": "subscription_info",
            "top_k": 3
        })

        assert "chunks" in result
        assert "scores" in result
        assert "average_score" in result
        assert "has_good_retrieval" in result
        assert isinstance(result["chunks"], list)

    def test_knowledge_search_billing(self):
        """Test knowledge search for billing question."""
        result = knowledge_search_tool.invoke({
            "query": "How does billing work?",
            "intent": "billing_question",
            "top_k": 3
        })

        assert "chunks" in result
        assert "scores" in result
        # Should retrieve some results
        if result["chunks"]:
            assert len(result["chunks"]) <= 3

    def test_knowledge_search_custom_top_k(self):
        """Test knowledge search with custom top_k."""
        result = knowledge_search_tool.invoke({
            "query": "What are your policies?",
            "intent": "policy_question",
            "top_k": 5
        })

        assert "chunks" in result
        # Should retrieve at most top_k results
        if result["chunks"]:
            assert len(result["chunks"]) <= 5

    def test_knowledge_search_invalid_intent(self):
        """Test knowledge search with invalid intent."""
        result = knowledge_search_tool.invoke({
            "query": "Tell me about your service",
            "intent": "invalid_intent",
            "top_k": 3
        })

        # Should handle gracefully
        assert "chunks" in result
        assert "has_good_retrieval" in result


class TestToolRegistry:
    """Test tool registry."""

    def test_all_tools_registered(self):
        """Test that all tools are in AGENT_TOOLS."""
        assert len(AGENT_TOOLS) == 3

        tool_names = [tool.name for tool in AGENT_TOOLS]
        assert "intent_classifier_tool" in tool_names
        assert "template_retrieval_tool" in tool_names
        assert "knowledge_search_tool" in tool_names

    def test_all_tools_have_descriptions(self):
        """Test that all tools have descriptions."""
        for tool in AGENT_TOOLS:
            assert tool.description is not None
            assert len(tool.description) > 0

    def test_all_tools_are_callable(self):
        """Test that all tools are callable."""
        for tool in AGENT_TOOLS:
            assert callable(tool.invoke)
