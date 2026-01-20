"""Deterministic PII detection and redaction using regex patterns.

This module implements privacy-first PII redaction that happens BEFORE any LLM calls.
Uses semantic markers to preserve context while removing sensitive information.
"""
import re
from typing import List, Tuple
from src.models import PIIType, PIIMetadata, RedactionResult


class DeterministicPIIRedactor:
    """Deterministic PII detector using regex patterns with semantic markers."""

    # High-risk PII patterns (always escalate)
    HIGH_RISK_PII = {PIIType.SSN, PIIType.CREDIT_CARD}

    def __init__(self):
        """Initialize PII patterns."""
        # Email pattern
        self.email_pattern = re.compile(
            r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        )

        # Phone patterns (various formats)
        self.phone_patterns = [
            re.compile(r'\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b'),  # 123-456-7890
            re.compile(r'\(\d{3}\)\s?\d{3}[-.\s]?\d{4}'),  # (123) 456-7890
            re.compile(r'\b\d{10}\b'),  # 1234567890
        ]

        # SSN patterns
        self.ssn_patterns = [
            re.compile(r'\b\d{3}-\d{2}-\d{4}\b'),  # 123-45-6789
            re.compile(r'\b\d{9}\b'),  # 123456789 (only if preceded by SSN context)
        ]

        # Credit card patterns (major card types)
        self.credit_card_patterns = [
            re.compile(r'\b4\d{3}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b'),  # Visa
            re.compile(r'\b5[1-5]\d{2}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b'),  # MasterCard
            re.compile(r'\b3[47]\d{2}[\s-]?\d{6}[\s-]?\d{5}\b'),  # AmEx
            re.compile(r'\b6011[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b'),  # Discover
        ]

        # Account ID patterns (common formats)
        self.account_id_patterns = [
            re.compile(r'\b[Aa]ccount[\s#:]*([A-Z0-9]{6,})\b'),  # Account #ABC123
            re.compile(r'\b[Aa]cc[\s#:]*([A-Z0-9]{6,})\b'),  # Acc #ABC123
            re.compile(r'\b[Uu]ser[\s#:]*([A-Z0-9]{6,})\b'),  # User #ABC123
            re.compile(r'\b[Cc]ustomer[\s#:]*([A-Z0-9]{6,})\b'),  # Customer #ABC123
            re.compile(r'\b[Ii][Dd][\s#:]*([A-Z0-9]{6,})\b'),  # ID #ABC123
        ]

        # Common name patterns (simple heuristic - capitalized words)
        self.name_pattern = re.compile(
            r'\b[A-Z][a-z]+ [A-Z][a-z]+\b'  # First Last
        )

        # Date of birth patterns
        self.dob_patterns = [
            re.compile(r'\b\d{2}/\d{2}/\d{4}\b'),  # MM/DD/YYYY
            re.compile(r'\b\d{4}-\d{2}-\d{2}\b'),  # YYYY-MM-DD
            re.compile(r'\b\d{2}-\d{2}-\d{4}\b'),  # MM-DD-YYYY
        ]

        # Address pattern (simple heuristic)
        self.address_pattern = re.compile(
            r'\b\d+\s+[A-Za-z\s]+(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Lane|Ln|Drive|Dr|Court|Ct)\b',
            re.IGNORECASE
        )

    def redact(self, message: str) -> RedactionResult:
        """
        Detect and redact PII from a message using deterministic patterns.

        Args:
            message: Original user message

        Returns:
            RedactionResult with redacted message and PII metadata
        """
        redacted = message
        pii_list: List[PIIMetadata] = []
        offset = 0  # Track offset changes due to replacements

        # Sort all detections by position to maintain correct offsets
        all_detections: List[Tuple[int, int, PIIType, str, str]] = []

        # Detect emails
        for match in self.email_pattern.finditer(message):
            marker = "[EMAIL_ADDRESS]"
            all_detections.append(
                (match.start(), match.end(), PIIType.EMAIL, match.group(), marker)
            )

        # Detect phone numbers
        for pattern in self.phone_patterns:
            for match in pattern.finditer(message):
                marker = "[PHONE_NUMBER]"
                all_detections.append(
                    (match.start(), match.end(), PIIType.PHONE, match.group(), marker)
                )

        # Detect SSN
        for pattern in self.ssn_patterns:
            for match in pattern.finditer(message):
                marker = "[SSN]"
                all_detections.append(
                    (match.start(), match.end(), PIIType.SSN, match.group(), marker)
                )

        # Detect credit cards
        for pattern in self.credit_card_patterns:
            for match in pattern.finditer(message):
                # Validate using Luhn algorithm
                card_number = re.sub(r'[\s-]', '', match.group())
                if self._is_valid_luhn(card_number):
                    marker = "[CREDIT_CARD]"
                    all_detections.append(
                        (match.start(), match.end(), PIIType.CREDIT_CARD,
                         match.group(), marker)
                    )

        # Detect account IDs
        for pattern in self.account_id_patterns:
            for match in pattern.finditer(message):
                marker = "[ACCOUNT_ID]"
                all_detections.append(
                    (match.start(), match.end(), PIIType.ACCOUNT_ID,
                     match.group(), marker)
                )

        # Detect names (conservative - only obvious patterns)
        # Skip common false positives like company names
        for match in self.name_pattern.finditer(message):
            name = match.group()
            # Skip if it looks like a company (contains LLC, Inc, etc.)
            if not re.search(r'\b(LLC|Inc|Corp|Ltd|Company)\b', name, re.IGNORECASE):
                marker = "[PERSON_NAME]"
                all_detections.append(
                    (match.start(), match.end(), PIIType.NAME, name, marker)
                )

        # Detect dates of birth
        for pattern in self.dob_patterns:
            for match in pattern.finditer(message):
                # Check if preceded by DOB/birth context
                context_start = max(0, match.start() - 20)
                context = message[context_start:match.start()].lower()
                if any(keyword in context for keyword in ['dob', 'birth', 'born']):
                    marker = "[DATE_OF_BIRTH]"
                    all_detections.append(
                        (match.start(), match.end(), PIIType.DATE_OF_BIRTH,
                         match.group(), marker)
                    )

        # Detect addresses
        for match in self.address_pattern.finditer(message):
            marker = "[ADDRESS]"
            all_detections.append(
                (match.start(), match.end(), PIIType.ADDRESS, match.group(), marker)
            )

        # Sort by start position and remove overlaps (keep first match)
        all_detections.sort(key=lambda x: x[0])
        filtered_detections = []
        last_end = -1
        for detection in all_detections:
            if detection[0] >= last_end:
                filtered_detections.append(detection)
                last_end = detection[1]

        # Apply redactions
        for start, end, pii_type, original, marker in filtered_detections:
            # Adjust positions based on offset
            adjusted_start = start + offset
            adjusted_end = end + offset

            # Create PII metadata
            pii_meta = PIIMetadata(
                type=pii_type,
                original_value=original,
                marker=marker,
                position_start=adjusted_start,
                position_end=adjusted_end,
                is_high_risk=pii_type in self.HIGH_RISK_PII
            )
            pii_list.append(pii_meta)

            # Replace in redacted message
            redacted = redacted[:adjusted_start] + marker + redacted[adjusted_end:]

            # Update offset
            offset += len(marker) - (end - start)

        # Check for high-risk PII
        has_high_risk = any(p.is_high_risk for p in pii_list)

        return RedactionResult(
            redacted_message=redacted,
            pii_metadata=pii_list,
            has_high_risk_pii=has_high_risk,
            redaction_count=len(pii_list)
        )

    def _is_valid_luhn(self, card_number: str) -> bool:
        """
        Validate credit card number using Luhn algorithm.

        Args:
            card_number: Credit card number (digits only)

        Returns:
            True if valid, False otherwise
        """
        if not card_number.isdigit():
            return False

        digits = [int(d) for d in card_number]
        checksum = 0

        # Process from right to left
        for i in range(len(digits) - 2, -1, -2):
            doubled = digits[i] * 2
            checksum += doubled if doubled < 10 else doubled - 9

        for i in range(len(digits) - 1, -1, -2):
            checksum += digits[i]

        return checksum % 10 == 0


# Global instance
_redactor = None


def get_pii_redactor() -> DeterministicPIIRedactor:
    """Get the global PII redactor instance."""
    global _redactor
    if _redactor is None:
        _redactor = DeterministicPIIRedactor()
    return _redactor
