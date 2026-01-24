"""Tests comparing /chat and /chat/agent endpoint outputs."""
import pytest
from fastapi.testclient import TestClient
from src.api import main
from src.agent.graph import create_triage_graph


@pytest.fixture
def client():
    """Create a test client with initialized graph."""
    # Initialize the graph before creating test client
    main.triage_graph = create_triage_graph()

    # Create test client
    return TestClient(main.app)


class TestEndpointParity:
    """Test that /chat and /chat/agent produce similar outputs."""

    def test_simple_question_parity(self, client):
        """Test that both endpoints handle simple questions similarly."""
        message = "What are your business hours?"

        # Call legacy endpoint
        response_legacy = client.post("/chat", json={"message": message})
        assert response_legacy.status_code == 200
        legacy_data = response_legacy.json()

        # Call agent endpoint
        response_agent = client.post("/chat/agent", json={"message": message})
        assert response_agent.status_code == 200
        agent_data = response_agent.json()

        # Compare actions (should be the same)
        assert legacy_data["action"] == agent_data["action"], \
            f"Action mismatch: legacy={legacy_data['action']}, agent={agent_data['action']}"

        # Both should have responses if action is TEMPLATE or GENERATED
        if legacy_data["action"] in ["TEMPLATE", "GENERATED"]:
            assert legacy_data["response"] is not None
            assert agent_data["response"] is not None

    def test_high_risk_pii_parity(self, client):
        """Test that both endpoints escalate high-risk PII."""
        message = "My SSN is 123-45-6789"

        # Call legacy endpoint
        response_legacy = client.post("/chat", json={"message": message})
        assert response_legacy.status_code == 200
        legacy_data = response_legacy.json()

        # Call agent endpoint
        response_agent = client.post("/chat/agent", json={"message": message})
        assert response_agent.status_code == 200
        agent_data = response_agent.json()

        # Both should escalate
        assert legacy_data["action"] == "ESCALATE"
        assert agent_data["action"] == "ESCALATE"

        # Both should have ticket IDs
        assert legacy_data["escalation_ticket_id"] is not None
        assert agent_data["escalation_ticket_id"] is not None

    def test_forbidden_intent_parity(self, client):
        """Test that both endpoints escalate forbidden intents."""
        message = "I want a refund for my last purchase"

        # Call legacy endpoint
        response_legacy = client.post("/chat", json={"message": message})
        assert response_legacy.status_code == 200
        legacy_data = response_legacy.json()

        # Call agent endpoint
        response_agent = client.post("/chat/agent", json={"message": message})
        assert response_agent.status_code == 200
        agent_data = response_agent.json()

        # Both should escalate
        assert legacy_data["action"] == "ESCALATE"
        assert agent_data["action"] == "ESCALATE"

        # Both should have ticket IDs
        assert legacy_data["escalation_ticket_id"] is not None
        assert agent_data["escalation_ticket_id"] is not None

    def test_billing_question_parity(self, client):
        """Test that both endpoints handle billing questions similarly."""
        message = "Why was I charged twice this month?"

        # Call legacy endpoint
        response_legacy = client.post("/chat", json={"message": message})
        assert response_legacy.status_code == 200
        legacy_data = response_legacy.json()

        # Call agent endpoint
        response_agent = client.post("/chat/agent", json={"message": message})
        assert response_agent.status_code == 200
        agent_data = response_agent.json()

        # Actions should match
        assert legacy_data["action"] == agent_data["action"], \
            f"Action mismatch: legacy={legacy_data['action']}, agent={agent_data['action']}"

        # Metadata should include intent
        assert "intent" in legacy_data["metadata"]
        assert "intent" in agent_data["metadata"]


class TestAgentMetadata:
    """Test that agent endpoint includes additional metadata."""

    def test_agent_includes_tool_calls(self, client):
        """Test that agent endpoint tracks tool calls."""
        message = "What are your subscription plans?"

        response = client.post("/chat/agent", json={"message": message})
        assert response.status_code == 200
        data = response.json()

        # Should have tool_calls in metadata
        assert "metadata" in data
        assert "tool_calls" in data["metadata"]
        assert isinstance(data["metadata"]["tool_calls"], list)

    def test_agent_includes_latency(self, client):
        """Test that agent endpoint includes latency metrics."""
        message = "How do I reset my password?"

        response = client.post("/chat/agent", json={"message": message})
        assert response.status_code == 200
        data = response.json()

        # Should have latency_ms in metadata
        assert "metadata" in data
        assert "latency_ms" in data["metadata"]
        assert data["metadata"]["latency_ms"] > 0


class TestSafetyGuarantees:
    """Test that safety guarantees are maintained in both endpoints."""

    @pytest.mark.parametrize("message", [
        "My SSN is 123-45-6789",
        "My credit card 4532-1234-5678-9010",
        "I want a refund",
        "Can I get my money back?",
        "Please delete my account",
    ])
    def test_both_endpoints_escalate_unsafe_requests(self, client, message):
        """Test that both endpoints escalate unsafe requests."""
        # Call legacy endpoint
        response_legacy = client.post("/chat", json={"message": message})
        assert response_legacy.status_code == 200
        legacy_data = response_legacy.json()

        # Call agent endpoint
        response_agent = client.post("/chat/agent", json={"message": message})
        assert response_agent.status_code == 200
        agent_data = response_agent.json()

        # Both should escalate
        assert legacy_data["action"] == "ESCALATE", \
            f"Legacy endpoint did not escalate: {message}"
        assert agent_data["action"] == "ESCALATE", \
            f"Agent endpoint did not escalate: {message}"


class TestInputValidation:
    """Test input validation on both endpoints."""

    def test_message_too_short(self, client):
        """Test that messages shorter than 10 characters are rejected."""
        message = "Hi"

        # Legacy endpoint (422 is Pydantic validation error)
        response_legacy = client.post("/chat", json={"message": message})
        assert response_legacy.status_code == 422

        # Agent endpoint
        response_agent = client.post("/chat/agent", json={"message": message})
        assert response_agent.status_code == 422

    def test_message_too_long(self, client):
        """Test that messages longer than 2000 characters are rejected."""
        message = "x" * 2001

        # Legacy endpoint (422 is Pydantic validation error)
        response_legacy = client.post("/chat", json={"message": message})
        assert response_legacy.status_code == 422

        # Agent endpoint
        response_agent = client.post("/chat/agent", json={"message": message})
        assert response_agent.status_code == 422
