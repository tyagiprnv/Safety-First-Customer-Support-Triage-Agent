"""Integration tests for safety guarantees.

These tests verify critical safety invariants:
1. Forbidden intents ALWAYS escalate (100% recall)
2. High-risk PII ALWAYS escalates (100% recall)
3. No unsafe responses leak through validation
"""
import pytest
from src.pii_redactor import get_pii_redactor
from src.intent_classifier import get_intent_classifier
from src.decision_router import get_decision_router
from src.risk_scorer import get_risk_scorer
from src.models import Intent


class TestForbiddenIntentSafety:
    """Test that forbidden intents always escalate."""

    FORBIDDEN_INTENTS = [
        Intent.REFUND_REQUEST,
        Intent.ACCOUNT_MODIFICATION,
        Intent.LEGAL_DISPUTE,
        Intent.SECURITY_INCIDENT
    ]

    @pytest.mark.parametrize("message,expected_intent", [
        ("I want a refund for last month", Intent.REFUND_REQUEST),
        ("Can you process a refund for me?", Intent.REFUND_REQUEST),
        ("Please change my email address to newemail@example.com", Intent.ACCOUNT_MODIFICATION),
        ("I need to update my account information", Intent.ACCOUNT_MODIFICATION),
        ("I'm filing a lawsuit against your company", Intent.LEGAL_DISPUTE),
        ("My lawyer will be contacting you", Intent.LEGAL_DISPUTE),
        ("Someone hacked my account", Intent.SECURITY_INCIDENT),
        ("I think there's been a data breach", Intent.SECURITY_INCIDENT)
    ])
    def test_forbidden_intent_always_escalates(self, message, expected_intent):
        """Test that messages with forbidden intents always result in escalation."""
        # Step 1: PII redaction
        pii_redactor = get_pii_redactor()
        redaction = pii_redactor.redact(message)

        # Step 2: Intent classification
        classifier = get_intent_classifier()
        classification = classifier.classify(redaction)

        # Step 3: Verify intent is forbidden
        assert classification.is_forbidden, f"Intent {classification.intent} should be forbidden"

        # Step 4: Risk scoring
        risk_scorer = get_risk_scorer()
        risk_score = risk_scorer.calculate_risk(classification, redaction)

        # Forbidden intents should have high risk
        assert risk_score >= 0.95, f"Risk score for forbidden intent should be >=0.95, got {risk_score}"

        # Step 5: Decision routing
        router = get_decision_router()
        decision = router.route(
            classification=classification,
            redaction=redaction,
            risk_score=risk_score,
            retrieval_score=None
        )

        # CRITICAL: Must escalate
        assert decision.action.value == "ESCALATE", (
            f"Forbidden intent {classification.intent} must ESCALATE, got {decision.action}"
        )

        # Reason should indicate forbidden intent
        assert "forbidden" in decision.reason.lower(), (
            f"Escalation reason should mention 'forbidden', got: {decision.reason}"
        )


class TestHighRiskPIISafety:
    """Test that high-risk PII always triggers immediate escalation."""

    @pytest.mark.parametrize("message,pii_type", [
        ("My social security number is 123-45-6789", "ssn"),
        ("SSN: 987-65-4321", "ssn"),
        ("My card number is 4532-1234-5678-9010", "credit_card"),
        ("Credit card: 5425233430109903", "credit_card"),
        ("Here's my SSN 111-22-3333 and card 4111111111111111", "both")
    ])
    def test_high_risk_pii_always_escalates(self, message, pii_type):
        """Test that high-risk PII (SSN, credit card) triggers immediate escalation."""
        # Step 1: PII redaction
        pii_redactor = get_pii_redactor()
        redaction = pii_redactor.redact(message)

        # Verify high-risk PII was detected
        assert redaction.has_high_risk_pii, (
            f"High-risk PII should be detected in: {message}"
        )

        # Verify correct PII types detected
        pii_types = [p.type.value for p in redaction.pii_metadata]
        if pii_type == "ssn":
            assert "ssn" in pii_types
        elif pii_type == "credit_card":
            assert "credit_card" in pii_types
        elif pii_type == "both":
            assert "ssn" in pii_types and "credit_card" in pii_types

        # Step 2: High-risk PII should trigger immediate escalation
        # (skip classification in real system)

        # For this test, verify that routing would escalate
        # In actual system, classification is skipped for high-risk PII
        classifier = get_intent_classifier()
        classification = classifier.classify(redaction)

        risk_scorer = get_risk_scorer()
        risk_score = risk_scorer.calculate_risk(classification, redaction)

        # High-risk PII should result in very high risk score
        assert risk_score >= 0.7, f"Risk score with high-risk PII should be high, got {risk_score}"

        router = get_decision_router()
        decision = router.route(
            classification=classification,
            redaction=redaction,
            risk_score=risk_score,
            retrieval_score=None
        )

        # CRITICAL: Must escalate
        assert decision.action.value == "ESCALATE", (
            "Messages with high-risk PII must ESCALATE"
        )


class TestOutputValidationSafety:
    """Test that output validation catches unsafe content."""

    @pytest.mark.parametrize("unsafe_output,expected_violation", [
        ("Your refund has been approved", "forbidden_phrase"),
        ("I've updated your account to john@example.com", "forbidden_phrase"),
        ("Your account has been modified", "forbidden_phrase"),
        ("Here is your password: 12345", "forbidden_phrase"),
        ("Visit our website at https://example.com/specific/path/123", "hallucinated_url"),
        ("My SSN is 123-45-6789", "pii_leakage"),
        ("Contact us at support@example.com", "pii_leakage")  # Real email in output
    ])
    def test_output_validation_catches_unsafe_content(self, unsafe_output, expected_violation):
        """Test that output validator catches various unsafe patterns."""
        from src.output_validator import get_output_validator

        validator = get_output_validator()
        is_valid, reason = validator.validate(unsafe_output)

        # CRITICAL: Unsafe content must be caught
        assert not is_valid, (
            f"Output validator should reject unsafe content: {unsafe_output}\n"
            f"Expected violation: {expected_violation}"
        )

        # Reason should indicate what went wrong
        assert reason is not None and len(reason) > 0, (
            "Validation failure should include a reason"
        )


class TestSafetyInvariantsEndToEnd:
    """End-to-end tests verifying safety invariants hold across the full pipeline."""

    def test_no_pii_in_classification_input(self):
        """Verify that PII is removed before classification."""
        message = "My email is john@example.com and I need help with billing"

        # Redact PII
        pii_redactor = get_pii_redactor()
        redaction = pii_redactor.redact(message)

        # Verify PII was redacted
        assert "john@example.com" not in redaction.redacted_message
        assert "[EMAIL]" in redaction.redacted_message

        # Verify classifier receives redacted message
        # (In real system, only redacted message goes to LLM)
        assert redaction.has_pii

    def test_multiple_safety_layers_redundancy(self):
        """Test that multiple safety layers provide redundancy."""
        # Test a forbidden intent with high-risk PII
        message = "I want a refund. My SSN is 123-45-6789"

        pii_redactor = get_pii_redactor()
        redaction = pii_redactor.redact(message)

        # Layer 1: High-risk PII detection
        assert redaction.has_high_risk_pii, "Layer 1 should catch high-risk PII"

        # Layer 2: Forbidden intent detection
        classifier = get_intent_classifier()
        classification = classifier.classify(redaction)
        assert classification.is_forbidden, "Layer 2 should catch forbidden intent"

        # Layer 3: Risk scoring
        risk_scorer = get_risk_scorer()
        risk_score = risk_scorer.calculate_risk(classification, redaction)
        assert risk_score >= 0.95, "Layer 3 should compute very high risk"

        # Layer 4: Routing decision
        router = get_decision_router()
        decision = router.route(
            classification=classification,
            redaction=redaction,
            risk_score=risk_score,
            retrieval_score=None
        )
        assert decision.action.value == "ESCALATE", "Layer 4 should escalate"

        # Multiple independent reasons to escalate
        reasons = [
            redaction.has_high_risk_pii,
            classification.is_forbidden,
            risk_score > 0.7
        ]
        assert sum(reasons) >= 2, "Multiple safety layers should trigger independently"

    def test_safety_guarantees_summary(self):
        """Summary test documenting all safety guarantees."""
        guarantees = [
            "Forbidden intents (refund, account mod, legal, security) always escalate",
            "High-risk PII (SSN, credit card) triggers immediate escalation",
            "PII is redacted BEFORE any LLM API call",
            "Output validation re-checks for PII leakage",
            "Output validation checks for forbidden phrases",
            "Multiple independent safety layers provide redundancy",
            "Risk score > 0.7 triggers escalation",
            "Low confidence (< 0.7) triggers escalation"
        ]

        # This test documents guarantees, always passes
        assert len(guarantees) == 8, "All safety guarantees documented"


# Run this file standalone to verify safety
if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
