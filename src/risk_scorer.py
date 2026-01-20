"""Risk scoring for customer support requests."""
from src.models import Intent, ClassificationResult, RedactionResult, PIIType
from src.config import get_settings


class RiskScorer:
    """Calculate risk scores based on intent, confidence, and PII."""

    # Base risk scores by intent type (0.0-1.0)
    INTENT_BASE_RISK = {
        Intent.FEATURE_QUESTION: 0.1,
        Intent.POLICY_QUESTION: 0.2,
        Intent.TECHNICAL_SUPPORT: 0.3,
        Intent.BILLING_QUESTION: 0.4,
        Intent.SUBSCRIPTION_INFO: 0.4,
        Intent.ACCOUNT_ACCESS: 0.6,
        Intent.ACCOUNT_MODIFICATION: 0.9,
        Intent.REFUND_REQUEST: 0.95,
        Intent.LEGAL_DISPUTE: 1.0,
        Intent.SECURITY_INCIDENT: 1.0,
        Intent.UNKNOWN: 0.7,  # High risk for unknown intents
    }

    # High-risk PII types
    HIGH_RISK_PII = {PIIType.SSN, PIIType.CREDIT_CARD}

    # Medium-risk PII types
    MEDIUM_RISK_PII = {
        PIIType.EMAIL,
        PIIType.PHONE,
        PIIType.ACCOUNT_ID,
        PIIType.NAME,
        PIIType.ADDRESS,
        PIIType.DATE_OF_BIRTH,
    }

    def __init__(self):
        """Initialize the risk scorer with config."""
        settings = get_settings()
        self.high_risk_pii_weight = settings.high_risk_pii_weight
        self.medium_risk_pii_weight = settings.medium_risk_pii_weight
        self.max_pii_contribution = settings.max_pii_contribution
        self.confidence_penalty_multiplier = settings.confidence_penalty_multiplier

    def calculate_risk(
        self,
        classification: ClassificationResult,
        redaction: RedactionResult
    ) -> float:
        """
        Calculate overall risk score for a request.

        Args:
            classification: Intent classification result
            redaction: PII redaction result

        Returns:
            Risk score between 0.0 and 1.0
        """
        # 1. Start with base risk from intent
        base_risk = self.INTENT_BASE_RISK.get(classification.intent, 0.7)

        # 2. Calculate PII risk contribution
        pii_risk = self._calculate_pii_risk(redaction)

        # 3. Calculate confidence penalty
        # Use adjusted confidence if available, otherwise use raw confidence
        confidence = classification.adjusted_confidence or classification.confidence
        confidence_penalty = (1.0 - confidence) * self.confidence_penalty_multiplier

        # 4. Combine risks (additive with cap at 1.0)
        total_risk = base_risk + pii_risk + confidence_penalty
        total_risk = min(1.0, total_risk)

        return round(total_risk, 3)

    def _calculate_pii_risk(self, redaction: RedactionResult) -> float:
        """
        Calculate risk contribution from PII.

        Args:
            redaction: PII redaction result

        Returns:
            PII risk score (capped at max_pii_contribution)
        """
        if not redaction.has_pii:
            return 0.0

        pii_risk = 0.0

        # Count high and medium risk PII
        high_risk_count = sum(
            1 for p in redaction.pii_metadata
            if p.type in self.HIGH_RISK_PII
        )
        medium_risk_count = sum(
            1 for p in redaction.pii_metadata
            if p.type in self.MEDIUM_RISK_PII
        )

        # Add risk for each PII item
        pii_risk += high_risk_count * self.high_risk_pii_weight
        pii_risk += medium_risk_count * self.medium_risk_pii_weight

        # Cap PII contribution
        pii_risk = min(pii_risk, self.max_pii_contribution)

        return pii_risk


# Global instance
_risk_scorer = None


def get_risk_scorer() -> RiskScorer:
    """Get the global risk scorer instance."""
    global _risk_scorer
    if _risk_scorer is None:
        _risk_scorer = RiskScorer()
    return _risk_scorer
