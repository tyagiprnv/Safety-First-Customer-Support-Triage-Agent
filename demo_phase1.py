#!/usr/bin/env python3
"""
Demo script for Phase 1: LangGraph Foundation

This script demonstrates the new /chat/agent endpoint and compares it with the legacy /chat endpoint.
"""
import requests
import json
from typing import Dict, Any


def chat_legacy(message: str) -> Dict[str, Any]:
    """Call the legacy /chat endpoint."""
    response = requests.post(
        "http://localhost:8000/chat",
        json={"message": message}
    )
    response.raise_for_status()
    return response.json()


def chat_agent(message: str) -> Dict[str, Any]:
    """Call the new /chat/agent endpoint."""
    response = requests.post(
        "http://localhost:8000/chat/agent",
        json={"message": message}
    )
    response.raise_for_status()
    return response.json()


def compare_endpoints(message: str):
    """Compare both endpoints for the same message."""
    print(f"\n{'='*80}")
    print(f"Message: {message}")
    print(f"{'='*80}")

    # Call legacy endpoint
    print("\n🔵 Legacy Endpoint (/chat):")
    try:
        legacy_result = chat_legacy(message)
        print(f"   Action: {legacy_result['action']}")
        print(f"   Reason: {legacy_result['reason']}")
        if legacy_result.get('response'):
            print(f"   Response: {legacy_result['response'][:100]}...")
        if legacy_result.get('escalation_ticket_id'):
            print(f"   Ticket: {legacy_result['escalation_ticket_id']}")
        if 'latency_ms' in legacy_result.get('metadata', {}):
            print(f"   Latency: {legacy_result['metadata']['latency_ms']:.0f}ms")
    except Exception as e:
        print(f"   ERROR: {e}")

    # Call agent endpoint
    print("\n🟢 Agent Endpoint (/chat/agent):")
    try:
        agent_result = chat_agent(message)
        print(f"   Action: {agent_result['action']}")
        print(f"   Reason: {agent_result['reason']}")
        if agent_result.get('response'):
            print(f"   Response: {agent_result['response'][:100]}...")
        if agent_result.get('escalation_ticket_id'):
            print(f"   Ticket: {agent_result['escalation_ticket_id']}")
        if 'latency_ms' in agent_result.get('metadata', {}):
            print(f"   Latency: {agent_result['metadata']['latency_ms']:.0f}ms")
        if 'tool_calls' in agent_result.get('metadata', {}):
            print(f"   Tool Calls: {agent_result['metadata']['tool_calls']}")
    except Exception as e:
        print(f"   ERROR: {e}")

    # Compare
    print("\n📊 Comparison:")
    try:
        if legacy_result['action'] == agent_result['action']:
            print("   ✅ Actions match!")
        else:
            print(f"   ❌ Actions differ: {legacy_result['action']} vs {agent_result['action']}")
    except:
        print("   ⚠️  Could not compare (one endpoint failed)")


def main():
    """Run demo scenarios."""
    print("\n" + "="*80)
    print("Phase 1 Demo: LangGraph Foundation")
    print("Comparing /chat (legacy) vs /chat/agent (new) endpoints")
    print("="*80)

    # Test scenarios
    scenarios = [
        # Simple questions
        "What are your business hours?",

        # Safety checks - high-risk PII
        "My SSN is 123-45-6789",

        # Safety checks - forbidden intents
        "I want a refund for my last purchase",

        # Billing question
        "Why was I charged twice this month?",

        # Technical question
        "How do I reset my password?",
    ]

    for message in scenarios:
        compare_endpoints(message)

    print("\n" + "="*80)
    print("Demo Complete!")
    print("="*80 + "\n")


if __name__ == "__main__":
    try:
        main()
    except requests.exceptions.ConnectionError:
        print("\n❌ Error: Could not connect to server.")
        print("   Please start the server first:")
        print("   uvicorn src.api.main:app --host 0.0.0.0 --port 8000\n")
    except KeyboardInterrupt:
        print("\n\nDemo interrupted by user.\n")
