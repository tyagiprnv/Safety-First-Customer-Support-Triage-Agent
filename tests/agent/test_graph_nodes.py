"""Unit tests for LangGraph nodes."""
import pytest
from src.agent.nodes import (
    pii_redaction_node,
    safety_check_node,
    classification_node,
    risk_scoring_node,
    routing_node,
    template_retrieval_node,
    rag_retrieval_node,
    generation_node,
    output_validation_node,
    escalation_node,
)
from src.agent.state import AgentState
from src.models import Intent, Action


class TestPIIRedactionNode:
    """Test PII redaction node."""

    def test_redaction_with_email(self):
        """Test that email addresses are redacted."""
        state: AgentState = {
            "request_id": "test-123",
            "original_message": "My email is john@example.com",
            "messages": ["My email is john@example.com"],
            "safety_violations": [],
            "tool_calls": [],
        }

        result = pii_redaction_node(state)

        assert "redaction" in result
        assert result["redaction"].has_pii
        assert "EMAIL_ADDRESS" in result["redaction"].redacted_message
        assert "john@example.com" not in result["redaction"].redacted_message

    def test_redaction_with_ssn(self):
        """Test that SSN is redacted and marked as high-risk."""
        state: AgentState = {
            "request_id": "test-123",
            "original_message": "My SSN is 123-45-6789",
            "messages": ["My SSN is 123-45-6789"],
            "safety_violations": [],
            "tool_calls": [],
        }

        result = pii_redaction_node(state)

        assert "redaction" in result
        assert result["redaction"].has_pii
        assert result["redaction"].has_high_risk_pii

    def test_redaction_without_pii(self):
        """Test message without PII."""
        state: AgentState = {
            "request_id": "test-123",
            "original_message": "What are your business hours?",
            "messages": ["What are your business hours?"],
            "safety_violations": [],
            "tool_calls": [],
        }

        result = pii_redaction_node(state)

        assert "redaction" in result
        assert not result["redaction"].has_pii
        assert not result["redaction"].has_high_risk_pii


class TestSafetyCheckNode:
    """Test safety check node."""

    def test_high_risk_pii_detected(self):
        """Test that high-risk PII triggers safety violation."""
        from src.models import RedactionResult, PIIMetadata, PIIType

        redaction = RedactionResult(
            redacted_message="My SSN is [SSN]",
            pii_metadata=[
                PIIMetadata(
                    type=PIIType.SSN,
                    original_value="123-45-6789",
                    marker="[SSN]",
                    position_start=10,
                    position_end=21,
                    is_high_risk=True
                )
            ],
            has_high_risk_pii=True,
            redaction_count=1
        )

        state: AgentState = {
            "request_id": "test-123",
            "original_message": "My SSN is 123-45-6789",
            "messages": ["My SSN is 123-45-6789"],
            "redaction": redaction,
            "safety_violations": [],
            "tool_calls": [],
        }

        result = safety_check_node(state)

        assert "safety_violations" in result
        assert "high_risk_pii_detected" in result["safety_violations"]

    def test_no_high_risk_pii(self):
        """Test that no safety violations for regular PII."""
        from src.models import RedactionResult, PIIMetadata, PIIType

        redaction = RedactionResult(
            redacted_message="My email is [EMAIL_ADDRESS]",
            pii_metadata=[
                PIIMetadata(
                    type=PIIType.EMAIL,
                    original_value="john@example.com",
                    marker="[EMAIL_ADDRESS]",
                    position_start=12,
                    position_end=28,
                    is_high_risk=False
                )
            ],
            has_high_risk_pii=False,
            redaction_count=1
        )

        state: AgentState = {
            "request_id": "test-123",
            "original_message": "My email is john@example.com",
            "messages": ["My email is john@example.com"],
            "redaction": redaction,
            "safety_violations": [],
            "tool_calls": [],
        }

        result = safety_check_node(state)

        assert "safety_violations" in result
        assert "high_risk_pii_detected" not in result["safety_violations"]


class TestClassificationNode:
    """Test classification node."""

    def test_billing_question_classification(self):
        """Test classification of a billing question."""
        from src.models import RedactionResult

        redaction = RedactionResult(
            redacted_message="Why was I charged twice this month?",
            pii_metadata=[],
            has_high_risk_pii=False,
            redaction_count=0
        )

        state: AgentState = {
            "request_id": "test-123",
            "original_message": "Why was I charged twice this month?",
            "messages": ["Why was I charged twice this month?"],
            "redaction": redaction,
            "safety_violations": [],
            "tool_calls": [],
        }

        result = classification_node(state)

        assert "classification" in result
        assert result["classification"].intent == Intent.BILLING_QUESTION
        assert result["classification"].confidence > 0.0

    def test_refund_request_classification(self):
        """Test classification of a refund request (forbidden intent)."""
        from src.models import RedactionResult

        redaction = RedactionResult(
            redacted_message="I want a refund for my last purchase",
            pii_metadata=[],
            has_high_risk_pii=False,
            redaction_count=0
        )

        state: AgentState = {
            "request_id": "test-123",
            "original_message": "I want a refund for my last purchase",
            "messages": ["I want a refund for my last purchase"],
            "redaction": redaction,
            "safety_violations": [],
            "tool_calls": [],
        }

        result = classification_node(state)

        assert "classification" in result
        assert result["classification"].intent == Intent.REFUND_REQUEST
        assert "safety_violations" in result
        assert "forbidden_intent" in result["safety_violations"]


class TestRiskScoringNode:
    """Test risk scoring node."""

    def test_risk_scoring_with_pii(self):
        """Test that PII increases risk score."""
        from src.models import RedactionResult, PIIMetadata, PIIType, ClassificationResult

        classification = ClassificationResult(
            intent=Intent.BILLING_QUESTION,
            confidence=0.85,
            is_forbidden=False
        )

        redaction = RedactionResult(
            redacted_message="My email is [EMAIL_ADDRESS]",
            pii_metadata=[
                PIIMetadata(
                    type=PIIType.EMAIL,
                    original_value="john@example.com",
                    marker="[EMAIL_ADDRESS]",
                    position_start=12,
                    position_end=28,
                    is_high_risk=False
                )
            ],
            has_high_risk_pii=False,
            redaction_count=1
        )

        state: AgentState = {
            "request_id": "test-123",
            "classification": classification,
            "redaction": redaction,
            "safety_violations": [],
            "tool_calls": [],
        }

        result = risk_scoring_node(state)

        assert "risk_score" in result
        assert result["risk_score"] > 0.0


class TestRoutingNode:
    """Test routing decision node."""

    def test_routing_to_escalate_for_forbidden_intent(self):
        """Test that forbidden intents route to escalation."""
        from src.models import RedactionResult, ClassificationResult

        classification = ClassificationResult(
            intent=Intent.REFUND_REQUEST,
            confidence=0.95,
            is_forbidden=True
        )

        redaction = RedactionResult(
            redacted_message="I want a refund",
            pii_metadata=[],
            has_high_risk_pii=False,
            redaction_count=0
        )

        state: AgentState = {
            "request_id": "test-123",
            "classification": classification,
            "redaction": redaction,
            "risk_score": 0.85,
            "safety_violations": ["forbidden_intent"],
            "tool_calls": [],
        }

        result = routing_node(state)

        assert "decision" in result
        assert result["decision"].action == Action.ESCALATE
        assert result["chosen_action"] == Action.ESCALATE


class TestTemplateRetrievalNode:
    """Test template retrieval node."""

    def test_template_retrieval_success(self):
        """Test successful template retrieval."""
        from src.models import RoutingDecision

        decision = RoutingDecision(
            action=Action.TEMPLATE,
            reason="high_template_match",
            template_id="template_001",
            risk_score=0.3
        )

        state: AgentState = {
            "request_id": "test-123",
            "decision": decision,
            "safety_violations": [],
            "tool_calls": [],
        }

        result = template_retrieval_node(state)

        assert "template_id" in result
        assert "template_text" in result
        assert "response" in result
        assert result["action"] == Action.TEMPLATE


class TestEscalationNode:
    """Test escalation node."""

    def test_escalation_ticket_creation(self):
        """Test that escalation creates a ticket."""
        from src.models import RedactionResult, ClassificationResult

        classification = ClassificationResult(
            intent=Intent.REFUND_REQUEST,
            confidence=0.95,
            is_forbidden=True
        )

        redaction = RedactionResult(
            redacted_message="I want a refund",
            pii_metadata=[],
            has_high_risk_pii=False,
            redaction_count=0
        )

        state: AgentState = {
            "request_id": "test-123",
            "classification": classification,
            "redaction": redaction,
            "risk_score": 0.85,
            "escalation_reason": "forbidden_intent",
            "reason": "forbidden_intent",
            "safety_violations": ["forbidden_intent"],
            "tool_calls": [],
        }

        result = escalation_node(state)

        assert "escalation_ticket_id" in result
        assert result["escalation_ticket_id"].startswith("TKT-")
        assert result["action"] == Action.ESCALATE
        assert result["reason"] == "forbidden_intent"
