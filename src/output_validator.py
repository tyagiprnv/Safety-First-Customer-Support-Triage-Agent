"""Output validation to prevent unsafe responses."""
import re
from typing import Optional, List
from src.pii_redactor import DeterministicPIIRedactor
from src.config import get_settings


class OutputValidator:
    """Validate generated responses for safety."""

    # Forbidden phrases that should never appear in responses
    FORBIDDEN_PHRASES = [
        "refund approved",
        "refund processed",
        "account modified",
        "email changed",
        "password changed",
        "we've updated your",
        "account has been updated",
        "changes have been made",
        "successfully processed your refund",
        "money has been returned",
    ]

    # Phrases indicating uncertainty (acceptable)
    UNCERTAINTY_PHRASES = [
        "i don't have enough information",
        "let me connect you",
        "contact support",
        "escalate",
        "specialist",
        "representative",
    ]

    def __init__(self):
        """Initialize the validator."""
        settings = get_settings()
        self.pii_redactor = DeterministicPIIRedactor()
        self.max_length = settings.max_output_length
        self.min_length = 20  # Minimum reasonable response length

    def validate(self, response: str) -> tuple[bool, Optional[str]]:
        """
        Validate a generated response.

        Args:
            response: Generated response text

        Returns:
            Tuple of (is_valid, reason)
            - is_valid: True if response is safe to send
            - reason: None if valid, otherwise explanation of failure
        """
        # 1. Check length
        if len(response) < self.min_length:
            return False, "Response too short"

        if len(response) > self.max_length:
            return False, "Response exceeds maximum length"

        # 2. Check for PII leakage
        redaction_result = self.pii_redactor.redact(response)
        if redaction_result.has_pii:
            return False, f"Response contains PII: {redaction_result.pii_types}"

        # 3. Check for forbidden phrases
        response_lower = response.lower()
        for phrase in self.FORBIDDEN_PHRASES:
            if phrase in response_lower:
                return False, f"Response contains forbidden phrase: '{phrase}'"

        # 4. Check for signs of hallucination (making up specific details)
        if self._likely_hallucination(response):
            return False, "Response may contain hallucinated details"

        # 5. Check that response is substantive (not just "I don't know")
        if self._is_non_answer(response):
            return False, "Response is not substantive"

        return True, None

    def _likely_hallucination(self, response: str) -> bool:
        """
        Check if response likely contains hallucinated details.

        Args:
            response: Generated response

        Returns:
            True if likely hallucination detected
        """
        # Check for specific URLs (we don't provide these in context)
        # Allow general domain mentions but not specific paths
        specific_url_pattern = r'https?://[^\s]+/[^\s]+'
        if re.search(specific_url_pattern, response):
            return True

        # Check for specific dates (context uses relative terms)
        specific_date_pattern = r'\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4}\b'
        if re.search(specific_date_pattern, response):
            return True

        # Check for specific employee names (we don't use these)
        if re.search(r'\b(contact|call|email|reach out to)\s+[A-Z][a-z]+ [A-Z][a-z]+\b', response):
            return True

        return False

    def _is_non_answer(self, response: str) -> bool:
        """
        Check if response is just saying "I don't know" without escalating.

        Args:
            response: Generated response

        Returns:
            True if response is non-substantive
        """
        response_lower = response.lower()

        # If response is very short and doesn't mention escalation
        if len(response) < 50:
            has_uncertainty = any(phrase in response_lower for phrase in self.UNCERTAINTY_PHRASES)
            if not has_uncertainty:
                # Short response without offering help
                if any(phrase in response_lower for phrase in ["i don't know", "i'm not sure", "no information"]):
                    return True

        return False


# Global instance
_validator: Optional[OutputValidator] = None


def get_output_validator() -> OutputValidator:
    """Get the global output validator instance."""
    global _validator
    if _validator is None:
        _validator = OutputValidator()
    return _validator
