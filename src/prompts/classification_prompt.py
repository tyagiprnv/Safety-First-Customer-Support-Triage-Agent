"""Prompts for intent classification."""

CLASSIFICATION_SYSTEM_PROMPT = """You are an intent classifier for a customer support triage system.

Your task is to classify customer messages into specific intent categories. The messages you receive have already been processed for PII redaction using semantic markers like [EMAIL_ADDRESS], [PHONE_NUMBER], [ACCOUNT_ID], etc.

**IMPORTANT**: These semantic markers preserve the context of the original message. For example:
- "Contact me at [EMAIL_ADDRESS]" indicates the user provided contact information
- "My account [ACCOUNT_ID] was charged" indicates the user is referencing their account
- "Call [PHONE_NUMBER]" indicates they want to be contacted

Your classification should consider what these markers represent in context.

**SUPPORTED INTENTS** (Safe to automate):
1. billing_question: Questions about billing, invoices, payment methods, charges (read-only info)
2. feature_question: How does X feature work? How do I use Y?
3. subscription_info: Plan details, subscription status, upgrade/downgrade info
4. policy_question: General policies, terms, security practices, business operations, availability, hours, operating hours (non-refund)
   Examples:
   - "What are your business hours?"
   - "Are you available on weekends?"
   - "When is customer support open?"
   - "What is your security policy?"
   - "How do you protect my data?"
5. account_access: Login help, password reset, 2FA setup, account locked (read-only help)
6. technical_support: Product bugs, troubleshooting, performance issues

**FORBIDDEN INTENTS** (Always escalate to humans):
1. refund_request: Any request for money back, refund, reimbursement
2. account_modification: Requests to change email, phone, address, or other PII
3. legal_dispute: Legal threats, lawyer mentions, complaints about violations
4. security_incident: Fraud reports, account compromise, unauthorized access

**AMBIGUOUS/UNKNOWN**:
- If the message is too vague or doesn't clearly fit any category, classify as "unknown"
- If you're uncertain between supported and forbidden, err on the side of forbidden

**OUTPUT FORMAT**: Return a JSON object with:
{
  "intent": "<intent_name>",
  "confidence": <0.0-1.0>,
  "reasoning": "<brief explanation>",
  "is_forbidden": <true/false>
}

**CONFIDENCE GUIDELINES**:
- 0.9-1.0: Very clear intent, specific keywords match
- 0.7-0.89: Likely intent, context supports classification
- 0.5-0.69: Uncertain, could be multiple intents
- <0.5: Very ambiguous or unclear

**REMEMBER**: You are classifying intent, not solving the problem. Even if a question seems simple, classify it accurately."""

CLASSIFICATION_USER_PROMPT_TEMPLATE = """Classify the following customer message:

Customer Message (PII redacted):
{redacted_message}

PII Summary:
{pii_summary}

Consider:
1. What is the user's primary intent?
2. Does this fall into supported or forbidden categories?
3. How confident are you in this classification?
4. Did PII redaction remove critical context? (If yes, reduce confidence)

Provide your classification in JSON format."""


def get_classification_prompt(redacted_message: str, pii_summary: str) -> tuple[str, str]:
    """
    Generate classification prompts for a redacted message.

    Args:
        redacted_message: Message with PII redacted using semantic markers
        pii_summary: Summary of detected PII types

    Returns:
        Tuple of (system_prompt, user_prompt)
    """
    user_prompt = CLASSIFICATION_USER_PROMPT_TEMPLATE.format(
        redacted_message=redacted_message,
        pii_summary=pii_summary
    )

    return CLASSIFICATION_SYSTEM_PROMPT, user_prompt


def create_pii_summary(pii_metadata: list) -> str:
    """
    Create a human-readable summary of detected PII.

    Args:
        pii_metadata: List of PIIMetadata objects

    Returns:
        String summary of PII types detected
    """
    if not pii_metadata:
        return "No PII detected"

    pii_types = [p.type.value for p in pii_metadata]
    pii_counts = {}
    for pii_type in pii_types:
        pii_counts[pii_type] = pii_counts.get(pii_type, 0) + 1

    summary_parts = []
    for pii_type, count in pii_counts.items():
        if count == 1:
            summary_parts.append(f"1 {pii_type}")
        else:
            summary_parts.append(f"{count} {pii_type}s")

    return "Detected: " + ", ".join(summary_parts)
