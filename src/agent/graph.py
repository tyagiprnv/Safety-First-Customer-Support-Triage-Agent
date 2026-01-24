"""LangGraph definition for triage agent.

Defines the state machine with explicit routing and safety guarantees.
"""
import time
from typing import Literal
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
import structlog

from src.agent.state import AgentState
from src.agent.nodes import (
    pii_redaction_node,
    safety_check_node,
    classification_node,
    risk_scoring_node,
    routing_node,
    template_retrieval_node,
    rag_retrieval_node,
    generation_node,
    output_validation_node,
    escalation_node,
    agent_reasoning_node,
    process_tool_results_node,
)
from src.models import Action

logger = structlog.get_logger(__name__)


def should_escalate_safety(state: AgentState) -> Literal["escalate", "continue"]:
    """
    Conditional edge: Check if safety violations require immediate escalation.

    Args:
        state: Current agent state

    Returns:
        "escalate" if high-risk PII detected, "continue" otherwise
    """
    safety_violations = state.get("safety_violations", [])

    # High-risk PII detected -> immediate escalation
    if "high_risk_pii_detected" in safety_violations:
        return "escalate"

    return "continue"


def should_escalate_forbidden(state: AgentState) -> Literal["escalate", "continue"]:
    """
    Conditional edge: Check if forbidden intent requires escalation.

    Args:
        state: Current agent state

    Returns:
        "escalate" if forbidden intent detected, "continue" otherwise
    """
    safety_violations = state.get("safety_violations", [])

    # Forbidden intent -> escalation
    if "forbidden_intent" in safety_violations:
        return "escalate"

    return "continue"


def route_action(state: AgentState) -> Literal["template", "generated", "escalate"]:
    """
    Conditional edge: Route based on routing decision.

    Args:
        state: Current agent state

    Returns:
        Next node name based on chosen action
    """
    chosen_action = state.get("chosen_action")

    if chosen_action == Action.TEMPLATE:
        return "template"
    elif chosen_action == Action.GENERATED:
        return "generated"
    else:
        return "escalate"


def should_escalate_retrieval(state: AgentState) -> Literal["escalate", "generate"]:
    """
    Conditional edge: Check if retrieval quality is sufficient.

    Args:
        state: Current agent state

    Returns:
        "escalate" if insufficient retrieval, "generate" otherwise
    """
    # Check if escalation was already set by retrieval node
    action = state.get("action")
    if action == Action.ESCALATE:
        return "escalate"

    return "generate"


def should_escalate_generation(state: AgentState) -> Literal["escalate", "validate"]:
    """
    Conditional edge: Check if generation suggested escalation.

    Args:
        state: Current agent state

    Returns:
        "escalate" if generation suggested escalation, "validate" otherwise
    """
    action = state.get("action")
    if action == Action.ESCALATE:
        return "escalate"

    return "validate"


def should_escalate_validation(state: AgentState) -> Literal["escalate", "success"]:
    """
    Conditional edge: Check if output validation passed.

    Args:
        state: Current agent state

    Returns:
        "escalate" if validation failed, "success" otherwise
    """
    validation_passed = state.get("validation_passed", False)

    if not validation_passed:
        return "escalate"

    return "success"


def create_triage_graph():
    """
    Create the LangGraph state machine for the triage agent.

    Graph flow:
    1. PII Redaction (deterministic)
    2. Safety Check (high-risk PII) -> escalate or continue
    3. Classification (LLM)
    4. Forbidden Intent Check -> escalate or continue
    5. Risk Scoring
    6. Routing Decision
    7. Action execution:
       - TEMPLATE: retrieve template -> end
       - GENERATED: RAG retrieval -> check quality -> generate -> validate -> end or escalate
       - ESCALATE: create ticket -> end

    Returns:
        Compiled LangGraph
    """
    # Create the state graph
    graph = StateGraph(AgentState)

    # Add all nodes
    graph.add_node("pii_redaction", pii_redaction_node)
    graph.add_node("safety_check", safety_check_node)
    graph.add_node("classify", classification_node)
    graph.add_node("forbidden_check", lambda state: state)  # No-op, just for routing
    graph.add_node("risk_score", risk_scoring_node)
    graph.add_node("route", routing_node)
    graph.add_node("template", template_retrieval_node)
    graph.add_node("retrieve", rag_retrieval_node)
    graph.add_node("generate", generation_node)
    graph.add_node("validate", output_validation_node)
    graph.add_node("escalate", escalation_node)

    # Define flow
    graph.set_entry_point("pii_redaction")

    # PII redaction -> safety check
    graph.add_edge("pii_redaction", "safety_check")

    # Safety check -> escalate or continue to classification
    graph.add_conditional_edges(
        "safety_check",
        should_escalate_safety,
        {
            "escalate": "escalate",
            "continue": "classify"
        }
    )

    # Classification -> forbidden check
    graph.add_edge("classify", "forbidden_check")

    # Forbidden check -> escalate or continue to risk scoring
    graph.add_conditional_edges(
        "forbidden_check",
        should_escalate_forbidden,
        {
            "escalate": "escalate",
            "continue": "risk_score"
        }
    )

    # Risk scoring -> routing
    graph.add_edge("risk_score", "route")

    # Routing -> template, generated, or escalate
    graph.add_conditional_edges(
        "route",
        route_action,
        {
            "template": "template",
            "generated": "retrieve",
            "escalate": "escalate"
        }
    )

    # Template -> end
    graph.add_edge("template", END)

    # Retrieve -> check quality -> generate or escalate
    graph.add_conditional_edges(
        "retrieve",
        should_escalate_retrieval,
        {
            "escalate": "escalate",
            "generate": "generate"
        }
    )

    # Generate -> check if escalation suggested -> validate or escalate
    graph.add_conditional_edges(
        "generate",
        should_escalate_generation,
        {
            "escalate": "escalate",
            "validate": "validate"
        }
    )

    # Validate -> success (end) or escalate
    graph.add_conditional_edges(
        "validate",
        should_escalate_validation,
        {
            "escalate": "escalate",
            "success": END
        }
    )

    # Escalate -> end
    graph.add_edge("escalate", END)

    # Compile the graph
    compiled_graph = graph.compile()

    logger.info("triage_graph_compiled")

    return compiled_graph


def create_agentic_triage_graph():
    """
    Create the LangGraph state machine with tool-calling capabilities (Phase 2).

    Graph flow:
    1. PII Redaction (deterministic)
    2. Safety Check (high-risk PII) -> escalate or continue
    3. Agent Reasoning Loop (LLM selects tools):
       - Calls intent_classifier_tool
       - Calls template_retrieval_tool
       - Calls knowledge_search_tool if needed
    4. Process Tool Results
    5. Forbidden Intent Check -> escalate or continue
    6. Risk Scoring
    7. Routing Decision
    8. Action execution (same as Phase 1)

    Returns:
        Compiled LangGraph with tool-calling
    """
    # Import tools
    from src.agent.tools import AGENT_TOOLS

    # Create the state graph
    graph = StateGraph(AgentState)

    # Create tool node for parallel execution
    tool_node = ToolNode(AGENT_TOOLS)

    # Add all nodes
    graph.add_node("pii_redaction", pii_redaction_node)
    graph.add_node("safety_check", safety_check_node)
    graph.add_node("agent_reasoning", agent_reasoning_node)
    graph.add_node("tools", tool_node)  # Executes tools (potentially in parallel)
    graph.add_node("process_tool_results", process_tool_results_node)
    graph.add_node("classify", classification_node)  # Keep for fallback/safety
    graph.add_node("forbidden_check", lambda state: state)  # No-op, just for routing
    graph.add_node("risk_score", risk_scoring_node)
    graph.add_node("route", routing_node)
    graph.add_node("template", template_retrieval_node)
    graph.add_node("retrieve", rag_retrieval_node)
    graph.add_node("generate", generation_node)
    graph.add_node("validate", output_validation_node)
    graph.add_node("escalate", escalation_node)

    # Define flow
    graph.set_entry_point("pii_redaction")

    # PII redaction -> safety check
    graph.add_edge("pii_redaction", "safety_check")

    # Safety check -> escalate or continue to agent reasoning
    graph.add_conditional_edges(
        "safety_check",
        should_escalate_safety,
        {
            "escalate": "escalate",
            "continue": "agent_reasoning"
        }
    )

    # Agent reasoning loop (max 2 iterations to prevent runaway)
    def should_continue_reasoning(state: AgentState) -> Literal["continue", "done"]:
        """Check if agent should continue calling tools."""
        agent_response = state.get("agent_response")
        attempt = state.get("agent_reasoning_attempt", 0)

        # Max 2 iterations
        if attempt >= 2:
            return "done"

        # If LLM requested tools, continue
        if agent_response and hasattr(agent_response, "tool_calls") and agent_response.tool_calls:
            return "continue"

        return "done"

    graph.add_conditional_edges(
        "agent_reasoning",
        should_continue_reasoning,
        {
            "continue": "tools",
            "done": "classify"  # Fallback to regular classification
        }
    )

    # Tools -> back to agent_reasoning for processing
    graph.add_edge("tools", "process_tool_results")
    graph.add_edge("process_tool_results", "agent_reasoning")

    # After reasoning loop, go to classification (for safety checks)
    graph.add_edge("classify", "forbidden_check")

    # Forbidden check -> escalate or continue to risk scoring
    graph.add_conditional_edges(
        "forbidden_check",
        should_escalate_forbidden,
        {
            "escalate": "escalate",
            "continue": "risk_score"
        }
    )

    # Risk scoring -> routing
    graph.add_edge("risk_score", "route")

    # Routing -> template, generated, or escalate
    graph.add_conditional_edges(
        "route",
        route_action,
        {
            "template": "template",
            "generated": "retrieve",
            "escalate": "escalate"
        }
    )

    # Template -> end
    graph.add_edge("template", END)

    # Retrieve -> check quality -> generate or escalate
    graph.add_conditional_edges(
        "retrieve",
        should_escalate_retrieval,
        {
            "escalate": "escalate",
            "generate": "generate"
        }
    )

    # Generate -> check if escalation suggested -> validate or escalate
    graph.add_conditional_edges(
        "generate",
        should_escalate_generation,
        {
            "escalate": "escalate",
            "validate": "validate"
        }
    )

    # Validate -> success (end) or escalate
    graph.add_conditional_edges(
        "validate",
        should_escalate_validation,
        {
            "escalate": "escalate",
            "success": END
        }
    )

    # Escalate -> end
    graph.add_edge("escalate", END)

    # Compile the graph
    compiled_graph = graph.compile()

    logger.info("agentic_triage_graph_compiled")

    return compiled_graph
