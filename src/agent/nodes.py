"""Graph nodes for LangGraph-based triage system.

Each node is a pure function that takes AgentState and returns a partial state update dict.
"""
import time
from typing import Dict, Any
import structlog

from src.agent.state import AgentState
from src.models import Action
from src.pii_redactor import get_pii_redactor
from src.intent_classifier import get_intent_classifier, FORBIDDEN_INTENTS
from src.risk_scorer import get_risk_scorer
from src.decision_router import get_decision_router
from src.retrieval import get_retrieval_pipeline
from src.generation import get_response_generator
from src.output_validator import get_output_validator
from src.escalation import get_escalation_system

logger = structlog.get_logger(__name__)


def pii_redaction_node(state: AgentState) -> Dict[str, Any]:
    """
    Node 1: Redact PII from the message using deterministic regex.

    Args:
        state: Current agent state

    Returns:
        Partial state update with redaction result
    """
    message = state["original_message"]
    request_id = state["request_id"]

    log = logger.bind(request_id=request_id, node="pii_redaction")
    log.info("pii_redaction_start")

    pii_redactor = get_pii_redactor()
    redaction = pii_redactor.redact(message)

    log.info(
        "pii_redaction_complete",
        has_pii=redaction.has_pii,
        has_high_risk_pii=redaction.has_high_risk_pii,
        pii_types=redaction.pii_types,
        redaction_count=redaction.redaction_count
    )

    return {"redaction": redaction}


def safety_check_node(state: AgentState) -> Dict[str, Any]:
    """
    Node 2: Check for high-risk PII (immediate escalation trigger).

    This node only checks PII-based safety. Forbidden intents are checked
    after classification.

    Args:
        state: Current agent state

    Returns:
        Partial state update with safety check results
    """
    redaction = state["redaction"]
    request_id = state["request_id"]

    log = logger.bind(request_id=request_id, node="safety_check")

    safety_violations = []
    if redaction.has_high_risk_pii:
        safety_violations.append("high_risk_pii_detected")
        log.warning("high_risk_pii_detected", pii_types=redaction.pii_types)

    return {"safety_violations": safety_violations}


def classification_node(state: AgentState) -> Dict[str, Any]:
    """
    Node 3: Classify intent using LLM.

    Args:
        state: Current agent state

    Returns:
        Partial state update with classification result
    """
    redaction = state["redaction"]
    request_id = state["request_id"]

    log = logger.bind(request_id=request_id, node="classification")
    log.info("classification_start")

    classifier = get_intent_classifier()
    classification = classifier.classify(redaction)

    log.info(
        "classification_complete",
        intent=classification.intent.value,
        confidence=classification.confidence,
        adjusted_confidence=classification.adjusted_confidence,
        is_forbidden=classification.is_forbidden
    )

    # Check if this is a forbidden intent
    safety_violations = state.get("safety_violations", [])
    if classification.is_forbidden or classification.intent in FORBIDDEN_INTENTS:
        safety_violations.append("forbidden_intent")

    return {
        "classification": classification,
        "safety_violations": safety_violations
    }


def risk_scoring_node(state: AgentState) -> Dict[str, Any]:
    """
    Node 4: Calculate risk score based on classification and PII.

    Args:
        state: Current agent state

    Returns:
        Partial state update with risk score
    """
    classification = state["classification"]
    redaction = state["redaction"]
    request_id = state["request_id"]

    log = logger.bind(request_id=request_id, node="risk_scoring")

    risk_scorer = get_risk_scorer()
    risk_score = risk_scorer.calculate_risk(classification, redaction)

    log.info("risk_score_calculated", risk_score=risk_score)

    return {"risk_score": risk_score}


def routing_node(state: AgentState) -> Dict[str, Any]:
    """
    Node 5: Make routing decision using explicit precedence logic.

    Args:
        state: Current agent state

    Returns:
        Partial state update with routing decision
    """
    classification = state["classification"]
    redaction = state["redaction"]
    risk_score = state["risk_score"]
    retrieval_score = state.get("retrieval_score")
    request_id = state["request_id"]

    log = logger.bind(request_id=request_id, node="routing")

    router = get_decision_router()
    decision = router.route(
        classification=classification,
        redaction=redaction,
        risk_score=risk_score,
        retrieval_score=retrieval_score
    )

    log.info(
        "routing_decision_made",
        action=decision.action.value,
        reason=decision.reason
    )

    return {
        "decision": decision,
        "chosen_action": decision.action,
        "reason": decision.reason
    }


def template_retrieval_node(state: AgentState) -> Dict[str, Any]:
    """
    Node 6: Retrieve template response.

    Args:
        state: Current agent state

    Returns:
        Partial state update with template data
    """
    decision = state["decision"]
    request_id = state["request_id"]

    log = logger.bind(request_id=request_id, node="template_retrieval")

    router = get_decision_router()
    template = next(
        (t for t in router.template_store.templates if t.id == decision.template_id),
        None
    )

    if not template:
        log.error("template_not_found", template_id=decision.template_id)
        return {
            "action": Action.ESCALATE,
            "reason": "template_not_found",
            "escalation_reason": "template_not_found"
        }

    log.info("template_retrieved", template_id=template.id)

    return {
        "template_id": template.id,
        "template_text": template.template,
        "response": template.template,
        "action": Action.TEMPLATE
    }


def rag_retrieval_node(state: AgentState) -> Dict[str, Any]:
    """
    Node 7: Retrieve relevant documents from knowledge base.

    Args:
        state: Current agent state

    Returns:
        Partial state update with retrieval results
    """
    redaction = state["redaction"]
    classification = state["classification"]
    request_id = state["request_id"]

    log = logger.bind(request_id=request_id, node="rag_retrieval")
    log.info("retrieval_start")

    retrieval_pipeline = get_retrieval_pipeline()
    retrieval_result = retrieval_pipeline.retrieve(
        query=redaction.redacted_message,
        intent=classification.intent
    )

    if not retrieval_result or not retrieval_result.has_good_retrieval:
        log.warning(
            "insufficient_retrieval",
            retrieval_score=retrieval_result.average_score if retrieval_result else 0.0
        )
        return {
            "retrieval_result": retrieval_result,
            "retrieval_score": retrieval_result.average_score if retrieval_result else 0.0,
            "action": Action.ESCALATE,
            "reason": "insufficient_retrieval",
            "escalation_reason": "insufficient_retrieval"
        }

    log.info(
        "retrieval_complete",
        average_score=retrieval_result.average_score,
        chunk_count=len(retrieval_result.chunks)
    )

    return {
        "retrieval_result": retrieval_result,
        "retrieval_score": retrieval_result.average_score
    }


def generation_node(state: AgentState) -> Dict[str, Any]:
    """
    Node 8: Generate response using RAG.

    Args:
        state: Current agent state

    Returns:
        Partial state update with generated response
    """
    redaction = state["redaction"]
    retrieval_result = state["retrieval_result"]
    request_id = state["request_id"]

    log = logger.bind(request_id=request_id, node="generation")
    log.info("generation_start")

    generator = get_response_generator()
    response_text, sources, gen_metadata = generator.generate(
        query=redaction.redacted_message,
        retrieval_result=retrieval_result
    )

    # Check if generation itself suggests escalation
    if gen_metadata and gen_metadata.get("requires_escalation", False):
        log.info("generation_suggested_escalation")
        return {
            "generated_response": response_text,
            "generation_metadata": gen_metadata,
            "action": Action.ESCALATE,
            "reason": "generation_suggested_escalation",
            "escalation_reason": "generation_suggested_escalation"
        }

    log.info("generation_complete", confidence_level=gen_metadata.get("confidence_level"))

    return {
        "generated_response": response_text,
        "generation_metadata": gen_metadata,
        "response": response_text
    }


def output_validation_node(state: AgentState) -> Dict[str, Any]:
    """
    Node 9: Validate generated output for safety.

    Args:
        state: Current agent state

    Returns:
        Partial state update with validation results
    """
    response_text = state["response"]
    request_id = state["request_id"]

    log = logger.bind(request_id=request_id, node="output_validation")

    validator = get_output_validator()
    is_valid, validation_reason = validator.validate(response_text)

    if not is_valid:
        log.warning("output_validation_failed", reason=validation_reason)
        return {
            "validation_passed": False,
            "validation_reason": validation_reason,
            "action": Action.ESCALATE,
            "reason": "output_validation_failed",
            "escalation_reason": "output_validation_failed"
        }

    log.info("output_validation_passed")

    return {
        "validation_passed": True,
        "action": Action.GENERATED
    }


def escalation_node(state: AgentState) -> Dict[str, Any]:
    """
    Node 10: Create escalation ticket.

    Args:
        state: Current agent state

    Returns:
        Partial state update with escalation ticket ID
    """
    redaction = state["redaction"]
    request_id = state["request_id"]
    reason = state.get("escalation_reason") or state.get("reason", "unknown")

    log = logger.bind(request_id=request_id, node="escalation")

    escalation_system = get_escalation_system()

    # Build metadata
    metadata = {
        "request_id": request_id,
    }

    classification = state.get("classification")
    if classification:
        metadata["intent"] = classification.intent.value
        metadata["confidence"] = classification.confidence

    risk_score = state.get("risk_score")
    if risk_score is not None:
        metadata["risk_score"] = risk_score

    validation_reason = state.get("validation_reason")
    if validation_reason:
        metadata["validation_reason"] = validation_reason

    gen_metadata = state.get("generation_metadata")
    if gen_metadata:
        metadata["confidence_level"] = gen_metadata.get("confidence_level", "unknown")

    retrieval_score = state.get("retrieval_score")
    if retrieval_score is not None:
        metadata["retrieval_score"] = retrieval_score

    ticket_id = escalation_system.create_ticket(
        redaction=redaction,
        reason=reason,
        metadata=metadata
    )

    log.info("escalation_ticket_created", ticket_id=ticket_id, reason=reason)

    return {
        "escalation_ticket_id": ticket_id,
        "action": Action.ESCALATE,
        "response": None,
        "reason": reason
    }
