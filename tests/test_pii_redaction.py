"""Unit tests for PII redaction."""
import json
import pytest
from pathlib import Path
from src.pii_redactor import DeterministicPIIRedactor
from src.models import PIIType


@pytest.fixture
def redactor():
    """Create a PII redactor instance."""
    return DeterministicPIIRedactor()


@pytest.fixture
def test_cases():
    """Load test cases from JSON."""
    test_file = Path(__file__).parent.parent / "data" / "pii_test_cases.json"
    with open(test_file) as f:
        data = json.load(f)
    return data["test_cases"]


def test_email_detection(redactor):
    """Test email detection."""
    message = "Contact me at john.doe@example.com"
    result = redactor.redact(message)

    assert result.has_pii
    assert PIIType.EMAIL in result.pii_types
    assert "[EMAIL_ADDRESS]" in result.redacted_message
    assert "john.doe@example.com" not in result.redacted_message


def test_phone_detection_formatted(redactor):
    """Test phone detection with various formats."""
    test_cases = [
        "Call 555-123-4567",
        "Call (555) 123-4567",
        "Call 5551234567",
    ]

    for message in test_cases:
        result = redactor.redact(message)
        assert result.has_pii, f"Failed for: {message}"
        assert PIIType.PHONE in result.pii_types
        assert "[PHONE_NUMBER]" in result.redacted_message


def test_ssn_detection(redactor):
    """Test SSN detection and high-risk flagging."""
    message = "My SSN is 123-45-6789"
    result = redactor.redact(message)

    assert result.has_pii
    assert PIIType.SSN in result.pii_types
    assert result.has_high_risk_pii
    assert "[SSN]" in result.redacted_message


def test_credit_card_detection(redactor):
    """Test credit card detection with Luhn validation."""
    # Valid Visa card number
    message = "Card: 4532-1488-0343-6467"
    result = redactor.redact(message)

    assert result.has_pii
    assert PIIType.CREDIT_CARD in result.pii_types
    assert result.has_high_risk_pii
    assert "[CREDIT_CARD]" in result.redacted_message


def test_invalid_credit_card_not_detected(redactor):
    """Test that invalid credit card numbers are not detected."""
    # Invalid card (fails Luhn check)
    message = "Card: 1234-5678-9012-3456"
    result = redactor.redact(message)

    assert PIIType.CREDIT_CARD not in result.pii_types


def test_multiple_pii_types(redactor):
    """Test detection of multiple PII types in one message."""
    message = "Email john@example.com or call 555-123-4567"
    result = redactor.redact(message)

    assert result.has_pii
    assert PIIType.EMAIL in result.pii_types
    assert PIIType.PHONE in result.pii_types
    assert result.redaction_count == 2


def test_high_risk_pii_flagging(redactor):
    """Test that high-risk PII is properly flagged."""
    message = "SSN: 123-45-6789 and card 4532-1488-0343-6467"
    result = redactor.redact(message)

    assert result.has_high_risk_pii
    high_risk_items = [p for p in result.pii_metadata if p.is_high_risk]
    assert len(high_risk_items) >= 2


def test_no_pii_message(redactor):
    """Test message with no PII."""
    message = "What are your business hours?"
    result = redactor.redact(message)

    assert not result.has_pii
    assert result.redaction_count == 0
    assert result.redacted_message == message


def test_false_positive_prevention_version_numbers(redactor):
    """Test that version numbers are not detected as phone numbers."""
    message = "Using version 3.14.1592 of the software"
    result = redactor.redact(message)

    # Should not detect version number as phone
    # (though some patterns might match, this tests our filtering)
    assert result.redacted_message == message or PIIType.PHONE not in result.pii_types


def test_account_id_detection(redactor):
    """Test account ID detection."""
    test_cases = [
        "Account #USER123456",
        "Acc #ABC789XYZ",
        "Customer ID: CUST999888",
    ]

    for message in test_cases:
        result = redactor.redact(message)
        assert result.has_pii, f"Failed for: {message}"
        assert PIIType.ACCOUNT_ID in result.pii_types


def test_name_detection(redactor):
    """Test name detection."""
    message = "I spoke with John Smith yesterday"
    result = redactor.redact(message)

    assert result.has_pii
    assert PIIType.NAME in result.pii_types
    assert "[PERSON_NAME]" in result.redacted_message


def test_address_detection(redactor):
    """Test address detection."""
    message = "Ship to 123 Main Street"
    result = redactor.redact(message)

    assert result.has_pii
    assert PIIType.ADDRESS in result.pii_types
    assert "[ADDRESS]" in result.redacted_message


def test_dob_detection_with_context(redactor):
    """Test date of birth detection with context."""
    message = "My date of birth is 01/15/1990"
    result = redactor.redact(message)

    assert result.has_pii
    assert PIIType.DATE_OF_BIRTH in result.pii_types
    assert "[DATE_OF_BIRTH]" in result.redacted_message


def test_date_without_context_not_detected(redactor):
    """Test that dates without birth context are not detected as DOB."""
    message = "The event is on 01/15/2024"
    result = redactor.redact(message)

    # Should not detect as DOB without context
    assert PIIType.DATE_OF_BIRTH not in result.pii_types


def test_complex_message_with_multiple_pii(redactor):
    """Test complex message with many PII types."""
    message = (
        "Hi, I'm John Doe (john@email.com), account #USER789. "
        "Card 4532-1488-0343-6467 was charged twice. Call 555-123-4567."
    )
    result = redactor.redact(message)

    assert result.has_pii
    assert result.has_high_risk_pii  # Due to credit card
    assert result.redaction_count >= 4
    # Check all PII was redacted
    assert "john@email.com" not in result.redacted_message
    assert "4532-1488-0343-6467" not in result.redacted_message
    assert "555-123-4567" not in result.redacted_message


def test_pii_metadata_completeness(redactor):
    """Test that PII metadata is complete and accurate."""
    message = "Email: test@example.com"
    result = redactor.redact(message)

    assert len(result.pii_metadata) == 1
    pii = result.pii_metadata[0]
    assert pii.type == PIIType.EMAIL
    assert pii.original_value == "test@example.com"
    assert pii.marker == "[EMAIL_ADDRESS]"
    assert not pii.is_high_risk


def test_all_test_cases(redactor, test_cases):
    """Run all test cases from JSON file."""
    for test_case in test_cases:
        message = test_case["message"]
        result = redactor.redact(message)

        # Check if PII should be detected
        if test_case["should_detect"]:
            assert result.has_pii, f"Failed to detect PII in: {test_case['id']}"

            # Check expected PII types
            expected_types = [PIIType(t) for t in test_case["expected_pii_types"]]
            for expected_type in expected_types:
                assert expected_type in result.pii_types, \
                    f"Failed to detect {expected_type} in: {test_case['id']}"

            # Check high-risk flagging if specified
            if test_case.get("is_high_risk"):
                assert result.has_high_risk_pii, \
                    f"Failed to flag high-risk PII in: {test_case['id']}"
        else:
            assert not result.has_pii, \
                f"False positive in: {test_case['id']}"


def test_precision_target(redactor, test_cases):
    """Test that precision meets >95% target."""
    true_positives = 0
    false_positives = 0

    for test_case in test_cases:
        message = test_case["message"]
        result = redactor.redact(message)

        if test_case["should_detect"]:
            if result.has_pii:
                true_positives += 1
        else:
            if result.has_pii:
                false_positives += 1

    # Calculate precision
    total_positives = true_positives + false_positives
    if total_positives > 0:
        precision = true_positives / total_positives
        assert precision >= 0.95, f"Precision {precision:.2%} below 95% target"


def test_high_risk_recall(redactor, test_cases):
    """Test that high-risk PII has 100% recall."""
    high_risk_cases = [tc for tc in test_cases if tc.get("is_high_risk")]

    for test_case in high_risk_cases:
        message = test_case["message"]
        result = redactor.redact(message)

        assert result.has_high_risk_pii, \
            f"Failed to detect high-risk PII in: {test_case['id']}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
