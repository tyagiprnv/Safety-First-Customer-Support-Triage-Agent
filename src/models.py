"""Data models for the triage agent."""
from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class PIIType(str, Enum):
    """Types of PII that can be detected."""

    EMAIL = "email"
    PHONE = "phone"
    SSN = "ssn"
    CREDIT_CARD = "credit_card"
    ACCOUNT_ID = "account_id"
    NAME = "name"
    ADDRESS = "address"
    DATE_OF_BIRTH = "date_of_birth"


class PIIMetadata(BaseModel):
    """Metadata about detected PII."""

    type: PIIType
    original_value: str
    marker: str
    position_start: int
    position_end: int
    is_high_risk: bool = False


class RedactionResult(BaseModel):
    """Result of PII redaction."""

    redacted_message: str
    pii_metadata: List[PIIMetadata] = Field(default_factory=list)
    has_high_risk_pii: bool = False
    redaction_count: int = 0

    @property
    def has_pii(self) -> bool:
        """Check if any PII was detected."""
        return len(self.pii_metadata) > 0

    @property
    def pii_types(self) -> List[str]:
        """Get list of PII types detected."""
        return list(set([p.type for p in self.pii_metadata]))


class Intent(str, Enum):
    """Supported customer support intents."""

    # Supported intents (safe to automate)
    BILLING_QUESTION = "billing_question"
    FEATURE_QUESTION = "feature_question"
    SUBSCRIPTION_INFO = "subscription_info"
    POLICY_QUESTION = "policy_question"
    ACCOUNT_ACCESS = "account_access"
    TECHNICAL_SUPPORT = "technical_support"

    # Forbidden intents (always escalate)
    REFUND_REQUEST = "refund_request"
    ACCOUNT_MODIFICATION = "account_modification"
    LEGAL_DISPUTE = "legal_dispute"
    SECURITY_INCIDENT = "security_incident"

    # Unknown or ambiguous
    UNKNOWN = "unknown"


class ClassificationResult(BaseModel):
    """Result of intent classification."""

    intent: Intent
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: Optional[str] = None
    is_forbidden: bool = False
    adjusted_confidence: Optional[float] = None


class Action(str, Enum):
    """Possible actions for the triage agent."""

    TEMPLATE = "TEMPLATE"
    GENERATED = "GENERATED"
    ESCALATE = "ESCALATE"


class RoutingDecision(BaseModel):
    """Result of routing decision."""

    action: Action
    reason: str
    template_id: Optional[str] = None
    retrieval_context: Optional[List[str]] = None
    risk_score: float = Field(ge=0.0, le=1.0)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ChatRequest(BaseModel):
    """Request to the chat endpoint."""

    message: str = Field(min_length=10, max_length=2000)


class ChatResponse(BaseModel):
    """Response from the chat endpoint."""

    action: Action
    response: Optional[str] = None
    reason: str
    escalation_ticket_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class MetricsResponse(BaseModel):
    """Metrics endpoint response."""

    total_requests: int
    action_distribution: Dict[str, int]
    avg_latency_ms: Dict[str, float]
    escalation_rate: float
    safety: Dict[str, int]


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    vector_db_connected: bool
    llm_provider_status: str
