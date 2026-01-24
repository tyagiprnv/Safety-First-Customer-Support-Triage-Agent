"""Integration tests for LangGraph flow."""
import pytest
from src.agent.graph import create_triage_graph
from src.agent.state import AgentState
from src.models import Action


@pytest.fixture
def graph():
    """Create a fresh graph instance for each test."""
    return create_triage_graph()


class TestGraphFlow:
    """Test full graph execution flow."""

    @pytest.mark.asyncio
    async def test_simple_question_flow(self, graph):
        """Test flow for a simple question that should use a template."""
        initial_state: AgentState = {
            "messages": ["What are your business hours?"],
            "request_id": "test-flow-001",
            "original_message": "What are your business hours?",
            "safety_violations": [],
            "tool_calls": []
        }

        final_state = await graph.ainvoke(initial_state)

        # Should complete successfully
        assert "action" in final_state
        assert final_state["action"] in [Action.TEMPLATE, Action.GENERATED, Action.ESCALATE]

        # Should have gone through all expected stages
        assert "redaction" in final_state
        assert "classification" in final_state
        assert "risk_score" in final_state
        assert "decision" in final_state

    @pytest.mark.asyncio
    async def test_high_risk_pii_immediate_escalation(self, graph):
        """Test that high-risk PII triggers immediate escalation."""
        initial_state: AgentState = {
            "messages": ["My SSN is 123-45-6789"],
            "request_id": "test-flow-002",
            "original_message": "My SSN is 123-45-6789",
            "safety_violations": [],
            "tool_calls": []
        }

        final_state = await graph.ainvoke(initial_state)

        # Should escalate due to high-risk PII
        assert final_state["action"] == Action.ESCALATE
        assert "high_risk_pii_detected" in final_state.get("safety_violations", [])
        assert "escalation_ticket_id" in final_state

        # Should NOT have gone through generation (stopped early)
        assert "generated_response" not in final_state or final_state["generated_response"] is None

    @pytest.mark.asyncio
    async def test_forbidden_intent_escalation(self, graph):
        """Test that forbidden intents always escalate."""
        initial_state: AgentState = {
            "messages": ["I want a refund for my last purchase"],
            "request_id": "test-flow-003",
            "original_message": "I want a refund for my last purchase",
            "safety_violations": [],
            "tool_calls": []
        }

        final_state = await graph.ainvoke(initial_state)

        # Should escalate due to forbidden intent
        assert final_state["action"] == Action.ESCALATE
        assert "forbidden_intent" in final_state.get("safety_violations", [])
        assert "escalation_ticket_id" in final_state

    @pytest.mark.asyncio
    async def test_billing_question_with_pii(self, graph):
        """Test billing question with email PII."""
        initial_state: AgentState = {
            "messages": ["Why was I charged at my.email@example.com?"],
            "request_id": "test-flow-004",
            "original_message": "Why was I charged at my.email@example.com?",
            "safety_violations": [],
            "tool_calls": []
        }

        final_state = await graph.ainvoke(initial_state)

        # Should process (not high-risk PII)
        assert "action" in final_state

        # PII should be redacted
        assert "redaction" in final_state
        assert final_state["redaction"].has_pii
        assert not final_state["redaction"].has_high_risk_pii
        assert "EMAIL_ADDRESS" in final_state["redaction"].redacted_message

    @pytest.mark.asyncio
    async def test_template_response_flow(self, graph):
        """Test full flow for template-based response."""
        initial_state: AgentState = {
            "messages": ["What are your business hours?"],
            "request_id": "test-flow-005",
            "original_message": "What are your business hours?",
            "safety_violations": [],
            "tool_calls": []
        }

        final_state = await graph.ainvoke(initial_state)

        # Check if template was used (depends on template configuration)
        if final_state["action"] == Action.TEMPLATE:
            assert "template_id" in final_state
            assert "template_text" in final_state
            assert final_state["response"] is not None
            assert len(final_state["response"]) > 0


class TestGraphSafety:
    """Test safety guarantees are maintained in the graph."""

    @pytest.mark.asyncio
    async def test_ssn_always_escalates(self, graph):
        """Test that SSN always triggers escalation."""
        test_cases = [
            "My SSN is 123-45-6789",
            "SSN: 123456789",
            "Social security number 123-45-6789",
        ]

        for message in test_cases:
            initial_state: AgentState = {
                "messages": [message],
                "request_id": f"test-ssn-{hash(message)}",
                "original_message": message,
                "safety_violations": [],
                "tool_calls": []
            }

            final_state = await graph.ainvoke(initial_state)

            assert final_state["action"] == Action.ESCALATE, f"Failed for message: {message}"
            assert "escalation_ticket_id" in final_state

    @pytest.mark.asyncio
    async def test_credit_card_always_escalates(self, graph):
        """Test that credit card numbers always trigger escalation."""
        message = "My card 4532-1234-5678-9010 was charged"

        initial_state: AgentState = {
            "messages": [message],
            "request_id": "test-cc-001",
            "original_message": message,
            "safety_violations": [],
            "tool_calls": []
        }

        final_state = await graph.ainvoke(initial_state)

        assert final_state["action"] == Action.ESCALATE
        assert "escalation_ticket_id" in final_state

    @pytest.mark.asyncio
    async def test_refund_requests_always_escalate(self, graph):
        """Test that refund requests always escalate."""
        test_cases = [
            "I want a refund",
            "Can I get my money back?",
            "Please refund my purchase",
        ]

        for message in test_cases:
            initial_state: AgentState = {
                "messages": [message],
                "request_id": f"test-refund-{hash(message)}",
                "original_message": message,
                "safety_violations": [],
                "tool_calls": []
            }

            final_state = await graph.ainvoke(initial_state)

            assert final_state["action"] == Action.ESCALATE, f"Failed for message: {message}"
            assert "escalation_ticket_id" in final_state


class TestGraphRouting:
    """Test routing logic in the graph."""

    @pytest.mark.asyncio
    async def test_state_propagation(self, graph):
        """Test that state is properly propagated through the graph."""
        initial_state: AgentState = {
            "messages": ["What are your business hours?"],
            "request_id": "test-propagation-001",
            "original_message": "What are your business hours?",
            "safety_violations": [],
            "tool_calls": []
        }

        final_state = await graph.ainvoke(initial_state)

        # Verify all expected state fields are present
        assert "request_id" in final_state
        assert final_state["request_id"] == "test-propagation-001"

        assert "original_message" in final_state
        assert final_state["original_message"] == "What are your business hours?"

        assert "redaction" in final_state
        assert "classification" in final_state
        assert "risk_score" in final_state
        assert "decision" in final_state
        assert "action" in final_state

    @pytest.mark.asyncio
    async def test_no_response_leakage_on_escalation(self, graph):
        """Test that escalations don't return generated responses."""
        initial_state: AgentState = {
            "messages": ["I want a refund now"],
            "request_id": "test-leakage-001",
            "original_message": "I want a refund now",
            "safety_violations": [],
            "tool_calls": []
        }

        final_state = await graph.ainvoke(initial_state)

        # Should escalate
        assert final_state["action"] == Action.ESCALATE

        # Should not have a response (None is acceptable)
        assert final_state.get("response") is None
