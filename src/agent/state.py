"""Agent state schema for LangGraph-based triage system."""
from typing import TypedDict, Optional, List, Dict, Any
from src.models import (
    RedactionResult,
    ClassificationResult,
    RoutingDecision,
    Action
)


class AgentState(TypedDict, total=False):
    """
    State that flows through the LangGraph triage agent.

    All fields are optional (total=False) to allow partial updates.
    """
    # Input
    messages: List[str]
    request_id: str
    original_message: str

    # PII Stage
    redaction: Optional[RedactionResult]

    # Classification Stage
    classification: Optional[ClassificationResult]

    # Risk Scoring Stage
    risk_score: Optional[float]

    # Routing Stage
    decision: Optional[RoutingDecision]
    chosen_action: Optional[Action]

    # Template Stage
    template_id: Optional[str]
    template_text: Optional[str]
    template_match_score: Optional[float]

    # Retrieval Stage
    retrieval_result: Optional[Any]  # RetrievalResult
    retrieval_score: Optional[float]

    # Generation Stage
    generated_response: Optional[str]
    generation_metadata: Optional[Dict[str, Any]]

    # Validation Stage
    validation_passed: Optional[bool]
    validation_reason: Optional[str]

    # Escalation Stage
    escalation_ticket_id: Optional[str]
    escalation_reason: Optional[str]

    # Output
    action: Optional[Action]
    response: Optional[str]
    reason: Optional[str]

    # Metadata
    latency_ms: Optional[float]
    safety_violations: List[str]
    tool_calls: List[str]
    start_time: Optional[float]
