"""Main FastAPI application."""
import time
import uuid
from datetime import datetime
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from typing import Dict, Any
import structlog

from src.models import (
    ChatRequest, ChatResponse, MetricsResponse, HealthResponse,
    Action
)
from src.config import get_settings
from src.logging_config import configure_logging, get_logger
from src.pii_redactor import get_pii_redactor
from src.intent_classifier import get_intent_classifier
from src.risk_scorer import get_risk_scorer
from src.decision_router import get_decision_router
from src.retrieval import get_retrieval_pipeline
from src.generation import get_response_generator
from src.output_validator import get_output_validator
from src.escalation import get_escalation_system
from src.vector_store import get_vector_store
from src.monitoring.cost_tracker import get_cost_tracker
from src.agent.graph import create_triage_graph, create_agentic_triage_graph

# Configure logging
configure_logging()
logger = get_logger(__name__)

# Global graph instances (initialized on startup)
triage_graph = None  # Phase 1: Basic LangGraph
agentic_triage_graph = None  # Phase 2: Tool-calling

# Create FastAPI app
app = FastAPI(
    title="Safety-First Customer Support Triage Agent",
    description="Privacy-first customer support automation with PII redaction",
    version="1.0.0"
)

# Global metrics storage (in-memory for demo)
metrics_store: Dict[str, Any] = {
    "total_requests": 0,
    "action_counts": {
        "TEMPLATE": 0,
        "GENERATED": 0,
        "ESCALATE": 0
    },
    "latencies": {
        "template": [],
        "generated": [],
        "escalate": []
    },
    "safety_metrics": {
        "unsafe_responses": 0,
        "high_risk_pii_escalations": 0,
        "forbidden_intent_escalations": 0
    }
}


@app.on_event("startup")
async def startup_event():
    """Initialize components on startup."""
    global triage_graph, agentic_triage_graph

    logger.info("application_starting")

    # Initialize all components
    get_pii_redactor()
    get_intent_classifier()
    get_risk_scorer()
    get_decision_router()
    get_retrieval_pipeline()
    get_response_generator()
    get_output_validator()
    get_escalation_system()

    # Check vector store connection
    try:
        vector_store = get_vector_store()
        doc_count = vector_store.count()
        logger.info("vector_store_initialized", document_count=doc_count)
    except Exception as e:
        logger.error("vector_store_initialization_failed", error=str(e))

    # Initialize Phase 1 LangGraph agent
    try:
        triage_graph = create_triage_graph()
        logger.info("triage_graph_initialized")
    except Exception as e:
        logger.error("triage_graph_initialization_failed", error=str(e))

    # Initialize Phase 2 Agentic LangGraph with tool-calling
    try:
        agentic_triage_graph = create_agentic_triage_graph()
        logger.info("agentic_triage_graph_initialized")
    except Exception as e:
        logger.error("agentic_triage_graph_initialization_failed", error=str(e))

    logger.info("application_started")


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    """
    Process a customer support message.

    Args:
        request: Chat request with user message

    Returns:
        Chat response with action and response or escalation
    """
    start_time = time.time()
    request_id = str(uuid.uuid4())

    # Bind request context to logger
    log = logger.bind(
        request_id=request_id
    )

    log.info("request_received", message_length=len(request.message))

    try:
        # 1. Input validation
        if len(request.message) < 10:
            raise HTTPException(status_code=400, detail="Message too short (minimum 10 characters)")

        if len(request.message) > 2000:
            raise HTTPException(status_code=400, detail="Message too long (maximum 2000 characters)")

        # 2. PII redaction
        pii_redactor = get_pii_redactor()
        redaction = pii_redactor.redact(request.message)

        log.info(
            "pii_redaction_complete",
            has_pii=redaction.has_pii,
            has_high_risk_pii=redaction.has_high_risk_pii,
            pii_types=redaction.pii_types,
            redaction_count=redaction.redaction_count
        )

        # 3. High-risk PII check (immediate escalation)
        if redaction.has_high_risk_pii:
            escalation_system = get_escalation_system()
            ticket_id = escalation_system.create_ticket(
                redaction=redaction,
                reason="high_risk_pii_detected",
                metadata={"request_id": request_id}
            )

            metrics_store["total_requests"] += 1
            metrics_store["action_counts"]["ESCALATE"] += 1
            metrics_store["safety_metrics"]["high_risk_pii_escalations"] += 1

            latency_ms = (time.time() - start_time) * 1000
            metrics_store["latencies"]["escalate"].append(latency_ms)

            log.info(
                "request_processed",
                action="ESCALATE",
                reason="high_risk_pii_detected",
                ticket_id=ticket_id,
                latency_ms=latency_ms
            )

            return ChatResponse(
                action=Action.ESCALATE,
                response=None,
                reason="high_risk_pii_detected",
                escalation_ticket_id=ticket_id,
                metadata={
                    "pii_detected": redaction.pii_types,
                    "latency_ms": latency_ms
                }
            )

        # 4. Intent classification
        classifier = get_intent_classifier()
        classification = classifier.classify(redaction)

        log.info(
            "intent_classified",
            intent=classification.intent.value,
            confidence=classification.confidence,
            adjusted_confidence=classification.adjusted_confidence,
            is_forbidden=classification.is_forbidden
        )

        # 5. Risk scoring
        risk_scorer = get_risk_scorer()
        risk_score = risk_scorer.calculate_risk(classification, redaction)

        log.info("risk_score_calculated", risk_score=risk_score)

        # 6. Decision routing
        router = get_decision_router()
        decision = router.route(
            classification=classification,
            redaction=redaction,
            risk_score=risk_score,
            retrieval_score=None  # Will be set if needed
        )

        log.info(
            "routing_decision_made",
            action=decision.action.value,
            reason=decision.reason
        )

        # 7. Execute action
        if decision.action == Action.ESCALATE:
            # Create escalation ticket
            escalation_system = get_escalation_system()
            ticket_id = escalation_system.create_ticket(
                redaction=redaction,
                reason=decision.reason,
                metadata={
                    "request_id": request_id,
                    "intent": classification.intent.value,
                    "confidence": classification.confidence,
                    "risk_score": risk_score
                }
            )

            # Update metrics
            metrics_store["total_requests"] += 1
            metrics_store["action_counts"]["ESCALATE"] += 1

            if classification.is_forbidden:
                metrics_store["safety_metrics"]["forbidden_intent_escalations"] += 1

            latency_ms = (time.time() - start_time) * 1000
            metrics_store["latencies"]["escalate"].append(latency_ms)

            log.info(
                "request_processed",
                action="ESCALATE",
                reason=decision.reason,
                ticket_id=ticket_id,
                latency_ms=latency_ms
            )

            return ChatResponse(
                action=Action.ESCALATE,
                response=None,
                reason=decision.reason,
                escalation_ticket_id=ticket_id,
                metadata={
                    "intent": classification.intent.value,
                    "confidence": classification.confidence,
                    "risk_score": risk_score,
                    "latency_ms": latency_ms
                }
            )

        elif decision.action == Action.TEMPLATE:
            # Use template response
            from src.decision_router import TemplateStore
            template_store = router.template_store
            template = next(
                (t for t in template_store.templates if t.id == decision.template_id),
                None
            )

            if not template:
                raise HTTPException(status_code=500, detail="Template not found")

            response_text = template.template

            # Update metrics
            metrics_store["total_requests"] += 1
            metrics_store["action_counts"]["TEMPLATE"] += 1

            latency_ms = (time.time() - start_time) * 1000
            metrics_store["latencies"]["template"].append(latency_ms)

            log.info(
                "request_processed",
                action="TEMPLATE",
                template_id=decision.template_id,
                latency_ms=latency_ms
            )

            return ChatResponse(
                action=Action.TEMPLATE,
                response=response_text,
                reason=decision.reason,
                metadata={
                    "intent": classification.intent.value,
                    "confidence": classification.confidence,
                    "risk_score": risk_score,
                    "template_id": decision.template_id,
                    "latency_ms": latency_ms
                }
            )

        elif decision.action == Action.GENERATED:
            # Generate response with RAG
            retrieval_pipeline = get_retrieval_pipeline()
            retrieval_result = retrieval_pipeline.retrieve(
                query=redaction.redacted_message,
                intent=classification.intent
            )

            if not retrieval_result or not retrieval_result.has_good_retrieval:
                # Fallback to escalation
                escalation_system = get_escalation_system()
                ticket_id = escalation_system.create_ticket(
                    redaction=redaction,
                    reason="insufficient_retrieval",
                    metadata={
                        "request_id": request_id,
                        "retrieval_score": retrieval_result.average_score if retrieval_result else 0.0
                    }
                )

                metrics_store["total_requests"] += 1
                metrics_store["action_counts"]["ESCALATE"] += 1

                latency_ms = (time.time() - start_time) * 1000

                log.info(
                    "request_processed",
                    action="ESCALATE",
                    reason="insufficient_retrieval",
                    ticket_id=ticket_id,
                    latency_ms=latency_ms
                )

                return ChatResponse(
                    action=Action.ESCALATE,
                    response=None,
                    reason="insufficient_retrieval",
                    escalation_ticket_id=ticket_id,
                    metadata={"latency_ms": latency_ms}
                )

            # Generate response
            generator = get_response_generator()
            response_text, sources, gen_metadata = generator.generate(
                query=redaction.redacted_message,
                retrieval_result=retrieval_result
            )

            # Check if generation itself suggests escalation
            if gen_metadata and gen_metadata.get("requires_escalation", False):
                escalation_system = get_escalation_system()
                ticket_id = escalation_system.create_ticket(
                    redaction=redaction,
                    reason="generation_suggested_escalation",
                    metadata={
                        "request_id": request_id,
                        "confidence_level": gen_metadata.get("confidence_level", "unknown")
                    }
                )

                metrics_store["total_requests"] += 1
                metrics_store["action_counts"]["ESCALATE"] += 1

                latency_ms = (time.time() - start_time) * 1000

                log.info(
                    "request_processed",
                    action="ESCALATE",
                    reason="generation_suggested_escalation",
                    ticket_id=ticket_id,
                    latency_ms=latency_ms
                )

                return ChatResponse(
                    action=Action.ESCALATE,
                    response=None,
                    reason="generation_suggested_escalation",
                    escalation_ticket_id=ticket_id,
                    metadata={"latency_ms": latency_ms, "generation_metadata": gen_metadata}
                )

            # Validate output
            validator = get_output_validator()
            is_valid, validation_reason = validator.validate(response_text)

            if not is_valid:
                # Output validation failed - escalate
                escalation_system = get_escalation_system()
                ticket_id = escalation_system.create_ticket(
                    redaction=redaction,
                    reason="output_validation_failed",
                    metadata={
                        "request_id": request_id,
                        "validation_reason": validation_reason
                    }
                )

                metrics_store["total_requests"] += 1
                metrics_store["action_counts"]["ESCALATE"] += 1

                latency_ms = (time.time() - start_time) * 1000

                log.warning(
                    "output_validation_failed",
                    reason=validation_reason,
                    ticket_id=ticket_id
                )

                log.info(
                    "request_processed",
                    action="ESCALATE",
                    reason="output_validation_failed",
                    ticket_id=ticket_id,
                    latency_ms=latency_ms
                )

                return ChatResponse(
                    action=Action.ESCALATE,
                    response=None,
                    reason="output_validation_failed",
                    escalation_ticket_id=ticket_id,
                    metadata={"latency_ms": latency_ms}
                )

            # Success - return generated response
            metrics_store["total_requests"] += 1
            metrics_store["action_counts"]["GENERATED"] += 1

            latency_ms = (time.time() - start_time) * 1000
            metrics_store["latencies"]["generated"].append(latency_ms)

            log.info(
                "request_processed",
                action="GENERATED",
                retrieval_score=retrieval_result.average_score,
                latency_ms=latency_ms
            )

            return ChatResponse(
                action=Action.GENERATED,
                response=response_text,
                reason=decision.reason,
                metadata={
                    "intent": classification.intent.value,
                    "confidence": classification.confidence,
                    "risk_score": risk_score,
                    "retrieval_score": retrieval_result.average_score,
                    "latency_ms": latency_ms,
                    "generation": gen_metadata
                }
            )

    except HTTPException:
        raise
    except Exception as e:
        log.error("request_processing_failed", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@app.post("/chat/agent", response_model=ChatResponse)
async def chat_agent(request: ChatRequest) -> ChatResponse:
    """
    Process a customer support message using LangGraph agent (A/B test endpoint).

    This endpoint uses the new LangGraph-based agentic system while maintaining
    all safety guarantees from the original system.

    Args:
        request: Chat request with user message

    Returns:
        Chat response with action and response or escalation
    """
    start_time = time.time()
    request_id = str(uuid.uuid4())

    # Bind request context to logger
    log = logger.bind(
        request_id=request_id,
        endpoint="chat_agent"
    )

    log.info("agent_request_received", message_length=len(request.message))

    try:
        # Input validation
        if len(request.message) < 10:
            raise HTTPException(status_code=400, detail="Message too short (minimum 10 characters)")

        if len(request.message) > 2000:
            raise HTTPException(status_code=400, detail="Message too long (maximum 2000 characters)")

        # Check if graph is initialized
        if triage_graph is None:
            raise HTTPException(status_code=503, detail="Agent graph not initialized")

        # Initialize state
        initial_state = {
            "messages": [request.message],
            "request_id": request_id,
            "original_message": request.message,
            "safety_violations": [],
            "tool_calls": [],
            "start_time": start_time
        }

        # Execute graph
        log.info("executing_graph")
        final_state = await triage_graph.ainvoke(initial_state)

        # Calculate latency
        latency_ms = (time.time() - start_time) * 1000

        # Extract results from final state
        action = final_state.get("action", Action.ESCALATE)
        response_text = final_state.get("response")
        reason = final_state.get("reason", "unknown")
        escalation_ticket_id = final_state.get("escalation_ticket_id")

        # Build metadata
        metadata = {
            "latency_ms": latency_ms,
            "tool_calls": final_state.get("tool_calls", [])
        }

        classification = final_state.get("classification")
        if classification:
            metadata["intent"] = classification.intent.value
            metadata["confidence"] = classification.confidence

        risk_score = final_state.get("risk_score")
        if risk_score is not None:
            metadata["risk_score"] = risk_score

        if action == Action.TEMPLATE:
            metadata["template_id"] = final_state.get("template_id")
            metadata["template_match_score"] = final_state.get("template_match_score")

        if action == Action.GENERATED:
            retrieval_score = final_state.get("retrieval_score")
            if retrieval_score is not None:
                metadata["retrieval_score"] = retrieval_score

            gen_metadata = final_state.get("generation_metadata")
            if gen_metadata:
                metadata["generation"] = gen_metadata

        # Update metrics
        metrics_store["total_requests"] += 1
        metrics_store["action_counts"][action.value] += 1

        action_type_key = action.value.lower()
        if action_type_key in metrics_store["latencies"]:
            metrics_store["latencies"][action_type_key].append(latency_ms)

        # Update safety metrics
        if action == Action.ESCALATE:
            redaction = final_state.get("redaction")
            if redaction and redaction.has_high_risk_pii:
                metrics_store["safety_metrics"]["high_risk_pii_escalations"] += 1

            if classification and classification.is_forbidden:
                metrics_store["safety_metrics"]["forbidden_intent_escalations"] += 1

        log.info(
            "agent_request_processed",
            action=action.value,
            reason=reason,
            latency_ms=latency_ms
        )

        return ChatResponse(
            action=action,
            response=response_text,
            reason=reason,
            escalation_ticket_id=escalation_ticket_id,
            metadata=metadata
        )

    except HTTPException:
        raise
    except Exception as e:
        log.error("agent_request_processing_failed", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@app.post("/chat/agent/v2", response_model=ChatResponse)
async def chat_agent_v2(request: ChatRequest) -> ChatResponse:
    """
    Process a customer support message using Agentic LangGraph with tool-calling (Phase 2).

    This endpoint uses the new tool-calling framework where the LLM decides which
    tools to call based on the customer's query. Enables parallel tool execution
    for improved latency.

    Args:
        request: Chat request with user message

    Returns:
        Chat response with action and response or escalation
    """
    start_time = time.time()
    request_id = str(uuid.uuid4())

    # Bind request context to logger
    log = logger.bind(
        request_id=request_id,
        endpoint="chat_agent_v2"
    )

    log.info("agentic_request_received", message_length=len(request.message))

    try:
        # Input validation
        if len(request.message) < 10:
            raise HTTPException(status_code=400, detail="Message too short (minimum 10 characters)")

        if len(request.message) > 2000:
            raise HTTPException(status_code=400, detail="Message too long (maximum 2000 characters)")

        # Check if agentic graph is initialized
        if agentic_triage_graph is None:
            raise HTTPException(status_code=503, detail="Agentic graph not initialized")

        # Initialize state
        initial_state = {
            "messages": [request.message],
            "request_id": request_id,
            "original_message": request.message,
            "safety_violations": [],
            "tool_calls": [],
            "start_time": start_time,
            "agent_reasoning_attempt": 0,
            "agent_messages": []
        }

        # Execute agentic graph
        log.info("executing_agentic_graph")
        final_state = await agentic_triage_graph.ainvoke(initial_state)

        # Calculate latency
        latency_ms = (time.time() - start_time) * 1000

        # Extract results from final state
        action = final_state.get("action", Action.ESCALATE)
        response_text = final_state.get("response")
        reason = final_state.get("reason", "unknown")
        escalation_ticket_id = final_state.get("escalation_ticket_id")

        # Build metadata
        metadata = {
            "latency_ms": latency_ms,
            "tool_calls": final_state.get("tool_calls", []),
            "agent_reasoning_attempts": final_state.get("agent_reasoning_attempt", 0)
        }

        classification = final_state.get("classification")
        if classification:
            metadata["intent"] = classification.intent.value
            metadata["confidence"] = classification.confidence

        risk_score = final_state.get("risk_score")
        if risk_score is not None:
            metadata["risk_score"] = risk_score

        if action == Action.TEMPLATE:
            metadata["template_id"] = final_state.get("template_id")
            metadata["template_match_score"] = final_state.get("template_match_score")

        if action == Action.GENERATED:
            retrieval_score = final_state.get("retrieval_score")
            if retrieval_score is not None:
                metadata["retrieval_score"] = retrieval_score

            gen_metadata = final_state.get("generation_metadata")
            if gen_metadata:
                metadata["generation"] = gen_metadata

        # Update metrics
        metrics_store["total_requests"] += 1
        metrics_store["action_counts"][action.value] += 1

        action_type_key = action.value.lower()
        if action_type_key in metrics_store["latencies"]:
            metrics_store["latencies"][action_type_key].append(latency_ms)

        # Update safety metrics
        if action == Action.ESCALATE:
            redaction = final_state.get("redaction")
            if redaction and redaction.has_high_risk_pii:
                metrics_store["safety_metrics"]["high_risk_pii_escalations"] += 1

            if classification and classification.is_forbidden:
                metrics_store["safety_metrics"]["forbidden_intent_escalations"] += 1

        log.info(
            "agentic_request_processed",
            action=action.value,
            reason=reason,
            latency_ms=latency_ms,
            tool_calls_count=len(metadata["tool_calls"])
        )

        return ChatResponse(
            action=action,
            response=response_text,
            reason=reason,
            escalation_ticket_id=escalation_ticket_id,
            metadata=metadata
        )

    except HTTPException:
        raise
    except Exception as e:
        log.error("agentic_request_processing_failed", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@app.get("/metrics")
async def get_metrics() -> Dict[str, Any]:
    """Get comprehensive system metrics including costs and business metrics."""
    # Calculate average latencies
    avg_latencies = {}
    for action_type, latencies in metrics_store["latencies"].items():
        if latencies:
            avg_latencies[action_type] = sum(latencies) / len(latencies)
        else:
            avg_latencies[action_type] = 0.0

    # Calculate escalation rate
    total = metrics_store["total_requests"]
    escalations = metrics_store["action_counts"]["ESCALATE"]
    escalation_rate = escalations / total if total > 0 else 0.0

    # Get cost tracking data
    cost_tracker = get_cost_tracker()
    cost_summary = cost_tracker.get_summary()

    # Calculate business metrics
    template_count = metrics_store["action_counts"]["TEMPLATE"]
    generated_count = metrics_store["action_counts"]["GENERATED"]
    successful_responses = template_count + generated_count

    # Support deflection rate (% of requests answered without human)
    support_deflection_rate = successful_responses / total if total > 0 else 0.0

    # Template usage rate
    template_usage_rate = template_count / total if total > 0 else 0.0

    # Average cost per request
    avg_cost_per_request = cost_tracker.get_cost_per_request(total)

    # Template cost savings (templates cost $0, generation costs money)
    avg_generation_cost = cost_summary.get("by_action", {}).get("GENERATED", {}).get("cost_usd", 0.0)
    avg_generation_cost_per_request = avg_generation_cost / generated_count if generated_count > 0 else 0.015

    template_cost_savings = template_count * avg_generation_cost_per_request

    # Projected monthly cost (assuming current request rate)
    projected_monthly_cost = cost_summary["total_cost_usd"] * 30 if total > 0 else 0.0

    return {
        # Standard metrics
        "total_requests": total,
        "action_distribution": metrics_store["action_counts"],
        "avg_latency_ms": avg_latencies,
        "escalation_rate": escalation_rate,
        "safety": metrics_store["safety_metrics"],

        # Cost metrics
        "cost_tracking": cost_summary,

        # Business metrics
        "business_metrics": {
            "support_deflection_rate": round(support_deflection_rate, 4),
            "template_usage_rate": round(template_usage_rate, 4),
            "average_cost_per_request": round(avg_cost_per_request, 6),
            "total_cost_usd": cost_summary["total_cost_usd"],
            "template_cost_savings": round(template_cost_savings, 6),
            "projected_monthly_cost": round(projected_monthly_cost, 2),
            "successful_responses": successful_responses,
            "automated_resolution_rate": round(support_deflection_rate, 4)
        }
    }


@app.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Health check endpoint."""
    # Check vector store
    vector_db_connected = False
    try:
        vector_store = get_vector_store()
        vector_store.count()
        vector_db_connected = True
    except Exception:
        pass

    # Check LLM provider (simple check)
    llm_status = "ok"
    try:
        settings = get_settings()
        if not settings.openai_api_key:
            llm_status = "no_api_key"
    except Exception:
        llm_status = "error"

    return HealthResponse(
        status="healthy" if vector_db_connected else "degraded",
        vector_db_connected=vector_db_connected,
        llm_provider_status=llm_status
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler."""
    logger.error(
        "unhandled_exception",
        path=request.url.path,
        method=request.method,
        error=str(exc),
        exc_info=True
    )

    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"}
    )
