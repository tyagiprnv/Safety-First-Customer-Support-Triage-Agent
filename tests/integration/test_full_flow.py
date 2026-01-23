"""Integration tests for full request flow.

Tests the complete pipeline from input to output:
Input → PII Redaction → Classification → Risk Scoring → Routing → Action → Output
"""
import pytest
from src.pii_redactor import get_pii_redactor
from src.intent_classifier import get_intent_classifier
from src.risk_scorer import get_risk_scorer
from src.decision_router import get_decision_router
from src.models import Intent, Action


class TestSafeAnswerableFlow:
    """Test full flow for safe, answerable questions."""

    @pytest.mark.parametrize("message,expected_intent,expected_action", [
        ("What payment methods do you accept?", Intent.BILLING_QUESTION, Action.TEMPLATE),
        ("How do I reset my password?", Intent.ACCOUNT_ACCESS, Action.TEMPLATE),
        ("What's the difference between Basic and Pro plans?", Intent.SUBSCRIPTION_INFO, Action.TEMPLATE),
        ("How do I add team members?", Intent.FEATURE_QUESTION, Action.TEMPLATE)
    ])
    def test_safe_question_flow(self, message, expected_intent, expected_action):
        """Test that safe questions flow through the system correctly."""
        # Step 1: PII Redaction
        pii_redactor = get_pii_redactor()
        redaction = pii_redactor.redact(message)

        # Should have no PII
        assert not redaction.has_pii, f"Safe question should have no PII: {message}"

        # Step 2: Intent Classification
        classifier = get_intent_classifier()
        classification = classifier.classify(redaction)

        assert classification.intent == expected_intent, (
            f"Expected intent {expected_intent}, got {classification.intent}"
        )

        # Should have reasonable confidence
        confidence = classification.adjusted_confidence or classification.confidence
        assert confidence >= 0.7, f"Confidence should be reasonable for clear question, got {confidence}"

        # Should not be forbidden
        assert not classification.is_forbidden, "Safe question should not be forbidden"

        # Step 3: Risk Scoring
        risk_scorer = get_risk_scorer()
        risk_score = risk_scorer.calculate_risk(classification, redaction)

        # Should have low to medium risk
        assert risk_score < 0.7, f"Safe question should have low risk, got {risk_score}"

        # Step 4: Routing Decision
        router = get_decision_router()
        decision = router.route(
            classification=classification,
            redaction=redaction,
            risk_score=risk_score,
            retrieval_score=None
        )

        # Should route to template or generated (not escalate)
        assert decision.action in [Action.TEMPLATE, Action.GENERATED], (
            f"Safe question should be answered, got {decision.action}"
        )


class TestPIIHandlingFlow:
    """Test full flow for messages containing PII."""

    @pytest.mark.parametrize("message,expected_pii_types", [
        ("My email is john@example.com and I have a question", ["email"]),
        ("Call me at 555-123-4567", ["phone"]),
        ("Account ID: USER123456 - when will I be charged?", ["account_id"]),
        ("My email is test@test.com and phone is 555-0000", ["email", "phone"])
    ])
    def test_pii_redaction_and_handling(self, message, expected_pii_types):
        """Test that PII is correctly detected, redacted, and handled."""
        # Step 1: PII Redaction
        pii_redactor = get_pii_redactor()
        redaction = pii_redactor.redact(message)

        # Verify PII was detected
        assert redaction.has_pii, "PII should be detected"

        # Verify correct PII types
        detected_types = [p.type.value for p in redaction.pii_metadata]
        for expected_type in expected_pii_types:
            assert expected_type in detected_types, (
                f"Expected PII type {expected_type} not detected. Got: {detected_types}"
            )

        # Verify PII was redacted (original values not in redacted message)
        for pii_item in redaction.pii_metadata:
            assert pii_item.original_value not in redaction.redacted_message, (
                f"PII value '{pii_item.original_value}' should be redacted"
            )
            assert pii_item.marker in redaction.redacted_message, (
                f"Marker '{pii_item.marker}' should be in redacted message"
            )

        # Step 2: Classification on redacted message
        classifier = get_intent_classifier()
        classification = classifier.classify(redaction)

        # If PII affects context, confidence should be adjusted
        if len(redaction.redacted_message) < 50 or redaction.redaction_count >= 2:
            assert classification.adjusted_confidence is not None, (
                "Confidence should be adjusted when PII affects context"
            )
            assert classification.adjusted_confidence < classification.confidence, (
                "Adjusted confidence should be lower than original"
            )


class TestEscalationFlow:
    """Test full flow for messages that should escalate."""

    @pytest.mark.parametrize("message,escalation_reason", [
        ("I want a refund", "forbidden_intent"),
        ("Please change my password to 'newpass'", "forbidden_intent"),
        ("what is this even about?", "low_confidence"),  # Ambiguous
        ("asdf qwerty zxcv", "low_confidence"),  # Nonsense
    ])
    def test_escalation_flow(self, message, escalation_reason):
        """Test that messages requiring escalation flow correctly."""
        # Full pipeline
        pii_redactor = get_pii_redactor()
        redaction = pii_redactor.redact(message)

        classifier = get_intent_classifier()
        classification = classifier.classify(redaction)

        risk_scorer = get_risk_scorer()
        risk_score = risk_scorer.calculate_risk(classification, redaction)

        router = get_decision_router()
        decision = router.route(
            classification=classification,
            redaction=redaction,
            risk_score=risk_score,
            retrieval_score=None
        )

        # Must escalate
        assert decision.action == Action.ESCALATE, (
            f"Message should escalate: {message}\n"
            f"Got action: {decision.action}, reason: {decision.reason}"
        )

        # Verify appropriate reason
        if escalation_reason == "forbidden_intent":
            assert classification.is_forbidden, "Should be forbidden intent"
            assert "forbidden" in decision.reason.lower(), (
                f"Reason should mention forbidden: {decision.reason}"
            )
        elif escalation_reason == "low_confidence":
            confidence = classification.adjusted_confidence or classification.confidence
            assert confidence < 0.7, f"Confidence should be low, got {confidence}"


class TestRoutingPrecedence:
    """Test that routing precedence rules are enforced."""

    def test_high_risk_pii_bypasses_classification(self):
        """Test that high-risk PII triggers immediate escalation."""
        message = "My SSN is 123-45-6789"

        pii_redactor = get_pii_redactor()
        redaction = pii_redactor.redact(message)

        # Should detect high-risk PII
        assert redaction.has_high_risk_pii

        # In real system, classification would be skipped
        # But for testing, we verify routing still escalates

        # Even if we classify (we shouldn't in real system)
        classifier = get_intent_classifier()
        classification = classifier.classify(redaction)

        risk_scorer = get_risk_scorer()
        risk_score = risk_scorer.calculate_risk(classification, redaction)

        router = get_decision_router()
        decision = router.route(
            classification=classification,
            redaction=redaction,
            risk_score=risk_score,
            retrieval_score=None
        )

        # Must escalate due to high-risk PII
        assert decision.action == Action.ESCALATE
        assert "high_risk_pii" in decision.reason.lower() or "forbidden" in decision.reason.lower()

    def test_forbidden_intent_overrides_high_confidence(self):
        """Test that forbidden intents escalate even with high confidence."""
        message = "I want a refund for my subscription"

        pii_redactor = get_pii_redactor()
        redaction = pii_redactor.redact(message)

        classifier = get_intent_classifier()
        classification = classifier.classify(redaction)

        # Should be classified as refund (forbidden)
        assert classification.intent == Intent.REFUND_REQUEST
        assert classification.is_forbidden

        # Even with high confidence
        confidence = classification.adjusted_confidence or classification.confidence
        # (Confidence might be high for clear refund request)

        risk_scorer = get_risk_scorer()
        risk_score = risk_scorer.calculate_risk(classification, redaction)

        router = get_decision_router()
        decision = router.route(
            classification=classification,
            redaction=redaction,
            risk_score=risk_score,
            retrieval_score=None
        )

        # Must escalate despite high confidence
        assert decision.action == Action.ESCALATE
        assert "forbidden" in decision.reason.lower()


class TestMetricsTracking:
    """Test that metrics are tracked correctly during requests."""

    def test_action_counts_tracked(self):
        """Test that each action type is counted."""
        from src.api.main import metrics_store

        initial_counts = dict(metrics_store["action_counts"])

        # This is a unit test style - in real integration test,
        # we'd make API calls and verify counts increase

        # For now, just verify structure exists
        assert "TEMPLATE" in metrics_store["action_counts"]
        assert "GENERATED" in metrics_store["action_counts"]
        assert "ESCALATE" in metrics_store["action_counts"]

    def test_safety_metrics_tracked(self):
        """Test that safety metrics are tracked."""
        from src.api.main import metrics_store

        # Verify safety metrics structure
        assert "safety_metrics" in metrics_store
        assert "unsafe_responses" in metrics_store["safety_metrics"]
        assert "high_risk_pii_escalations" in metrics_store["safety_metrics"]
        assert "forbidden_intent_escalations" in metrics_store["safety_metrics"]


class TestSystemIntegration:
    """High-level integration tests for system behavior."""

    def test_system_processes_variety_of_inputs(self):
        """Test that system can process various input types."""
        test_inputs = [
            "What are your business hours?",
            "How much does the Pro plan cost?",
            "I need help",  # Ambiguous - should escalate
            "refund please",  # Forbidden - should escalate
            "My email is test@test.com, when am I charged?"  # PII + question
        ]

        for message in test_inputs:
            try:
                # Run through pipeline
                pii_redactor = get_pii_redactor()
                redaction = pii_redactor.redact(message)

                classifier = get_intent_classifier()
                classification = classifier.classify(redaction)

                risk_scorer = get_risk_scorer()
                risk_score = risk_scorer.calculate_risk(classification, redaction)

                router = get_decision_router()
                decision = router.route(
                    classification=classification,
                    redaction=redaction,
                    risk_score=risk_score,
                    retrieval_score=None
                )

                # Should complete without errors
                assert decision.action in [Action.TEMPLATE, Action.GENERATED, Action.ESCALATE]

            except Exception as e:
                pytest.fail(f"System failed to process input '{message}': {str(e)}")

    def test_deterministic_components(self):
        """Test that deterministic components produce consistent results."""
        message = "What payment methods do you accept?"

        # Run pipeline twice
        results = []
        for _ in range(2):
            pii_redactor = get_pii_redactor()
            redaction = pii_redactor.redact(message)

            classifier = get_intent_classifier()
            classification = classifier.classify(redaction)

            results.append({
                "redacted": redaction.redacted_message,
                "has_pii": redaction.has_pii,
                "intent": classification.intent
            })

        # PII redaction should be deterministic
        assert results[0]["redacted"] == results[1]["redacted"]
        assert results[0]["has_pii"] == results[1]["has_pii"]

        # Intent might vary slightly due to LLM, but should be same
        # (with temperature=0 for classification)
        assert results[0]["intent"] == results[1]["intent"]


class TestBusinessHoursVariations:
    """Test that business hours queries are handled correctly."""

    @pytest.mark.parametrize("query", [
        "Are you available on weekends?",
        "What are your operating hours?",
        "When are you open on Saturday?",
        "Can I reach support on Sunday?",
        "When is customer support available?"
    ])
    def test_business_hours_variations(self, query):
        """Test that business hours queries match template or generate (not escalate)."""
        # Full pipeline
        pii_redactor = get_pii_redactor()
        redaction = pii_redactor.redact(query)

        classifier = get_intent_classifier()
        classification = classifier.classify(redaction)

        # Should classify as policy_question (not unknown)
        assert classification.intent == Intent.POLICY_QUESTION, (
            f"Query '{query}' should be POLICY_QUESTION, got {classification.intent}"
        )

        # Should have reasonable confidence
        confidence = classification.adjusted_confidence or classification.confidence
        assert confidence >= 0.6, (
            f"Query '{query}' should have reasonable confidence, got {confidence}"
        )

        risk_scorer = get_risk_scorer()
        risk_score = risk_scorer.calculate_risk(classification, redaction)

        # Should have low risk (policy_question base_risk is 0.2)
        assert risk_score < 0.7, (
            f"Query '{query}' should have low risk, got {risk_score}"
        )

        router = get_decision_router()
        decision = router.route(
            classification=classification,
            redaction=redaction,
            risk_score=risk_score,
            retrieval_score=0.85  # Assume good retrieval
        )

        # Should match template or generate (NOT escalate)
        assert decision.action in [Action.TEMPLATE, Action.GENERATED], (
            f"Query '{query}' should be answered (TEMPLATE or GENERATED), "
            f"got {decision.action} with reason: {decision.reason}"
        )


class TestTemplateMatchingImprovements:
    """Test various templates with improved keyword matching."""

    @pytest.mark.parametrize("query,expected_intent,min_action_quality", [
        ("When will I be charged?", Intent.BILLING_QUESTION, [Action.TEMPLATE, Action.GENERATED]),
        ("Can I pay with Visa?", Intent.BILLING_QUESTION, [Action.TEMPLATE, Action.GENERATED]),
        ("How do I cancel my subscription?", Intent.SUBSCRIPTION_INFO, [Action.TEMPLATE, Action.GENERATED]),
        ("I forgot my password", Intent.ACCOUNT_ACCESS, [Action.TEMPLATE, Action.GENERATED]),
        ("What browsers do you support?", Intent.FEATURE_QUESTION, [Action.TEMPLATE, Action.GENERATED]),
        ("Is my data secure?", Intent.POLICY_QUESTION, [Action.TEMPLATE, Action.GENERATED]),
    ])
    def test_template_matching_with_variations(self, query, expected_intent, min_action_quality):
        """Test that queries with keyword variations are handled correctly."""
        # Full pipeline
        pii_redactor = get_pii_redactor()
        redaction = pii_redactor.redact(query)

        classifier = get_intent_classifier()
        classification = classifier.classify(redaction)

        # Should classify correctly
        assert classification.intent == expected_intent, (
            f"Query '{query}' should be {expected_intent}, got {classification.intent}"
        )

        risk_scorer = get_risk_scorer()
        risk_score = risk_scorer.calculate_risk(classification, redaction)

        router = get_decision_router()
        decision = router.route(
            classification=classification,
            redaction=redaction,
            risk_score=risk_score,
            retrieval_score=0.85  # Assume good retrieval
        )

        # Should match template or generate (acceptable actions)
        assert decision.action in min_action_quality, (
            f"Query '{query}' should be answered, got {decision.action} with reason: {decision.reason}"
        )


# Run this file standalone
if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
