"""PII-aware intent classification using LLM."""
import json
import openai
from typing import Optional
from src.models import Intent, ClassificationResult, RedactionResult
from src.prompts.classification_prompt import get_classification_prompt, create_pii_summary
from src.config import get_settings
from src.monitoring.cost_tracker import get_cost_tracker


# Forbidden intents that should always escalate
FORBIDDEN_INTENTS = {
    Intent.REFUND_REQUEST,
    Intent.ACCOUNT_MODIFICATION,
    Intent.LEGAL_DISPUTE,
    Intent.SECURITY_INCIDENT,
}


class PIIAwareIntentClassifier:
    """Intent classifier that accounts for PII redaction."""

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize the classifier.

        Args:
            api_key: OpenAI API key (defaults to config)
        """
        settings = get_settings()
        self.api_key = api_key or settings.openai_api_key
        self.model = settings.classification_model
        self.temperature = settings.classification_temperature
        self.pii_confidence_reduction = settings.pii_confidence_reduction
        self.client = openai.OpenAI(api_key=self.api_key)
        self.cost_tracker = get_cost_tracker()

    def classify(self, redaction_result: RedactionResult) -> ClassificationResult:
        """
        Classify intent of a redacted message.

        Args:
            redaction_result: Result from PII redaction

        Returns:
            ClassificationResult with intent, confidence, and metadata
        """
        # Create PII summary for prompt
        pii_summary = create_pii_summary(redaction_result.pii_metadata)

        # Get classification prompts
        system_prompt, user_prompt = get_classification_prompt(
            redaction_result.redacted_message,
            pii_summary
        )

        try:
            # Call LLM for classification
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=self.temperature,
                response_format={"type": "json_object"}
            )

            # Parse response
            result_text = response.choices[0].message.content
            result_data = json.loads(result_text)

            # Track token usage and cost
            input_text = system_prompt + user_prompt
            output_text = result_text
            token_usage = self.cost_tracker.track_completion(
                model=self.model,
                input_text=input_text,
                output_text=output_text,
                action="classification"
            )

            # Extract classification
            intent_str = result_data.get("intent", "unknown")
            confidence = float(result_data.get("confidence", 0.5))
            reasoning = result_data.get("reasoning", "No reasoning provided")

            # Map string to Intent enum
            try:
                intent = Intent(intent_str)
            except ValueError:
                intent = Intent.UNKNOWN

            # Check if forbidden
            is_forbidden = intent in FORBIDDEN_INTENTS

            # Adjust confidence if PII likely removed critical context
            adjusted_confidence = confidence
            if redaction_result.has_pii and self._pii_affects_context(redaction_result):
                adjusted_confidence = max(0.0, confidence - self.pii_confidence_reduction)
                reasoning += f" (Confidence reduced by {self.pii_confidence_reduction} due to PII redaction)"

            return ClassificationResult(
                intent=intent,
                confidence=confidence,
                reasoning=reasoning,
                is_forbidden=is_forbidden,
                adjusted_confidence=adjusted_confidence
            )

        except Exception as e:
            # On error, return unknown with low confidence
            return ClassificationResult(
                intent=Intent.UNKNOWN,
                confidence=0.3,
                reasoning=f"Classification failed: {str(e)}",
                is_forbidden=False,
                adjusted_confidence=0.3
            )

    def _pii_affects_context(self, redaction_result: RedactionResult) -> bool:
        """
        Determine if PII redaction likely removed critical context.

        Args:
            redaction_result: Result from PII redaction

        Returns:
            True if PII redaction may have affected understanding
        """
        # If message is short and has PII, redaction likely affects context
        message_length = len(redaction_result.redacted_message)
        if message_length < 50 and redaction_result.has_pii:
            return True

        # If PII makes up >30% of message, context likely affected
        marker_chars = sum(len(p.marker) for p in redaction_result.pii_metadata)
        if marker_chars / message_length > 0.3:
            return True

        # If multiple PII items, more likely to affect context
        if redaction_result.redaction_count >= 3:
            return True

        return False


# Global classifier instance
_classifier: Optional[PIIAwareIntentClassifier] = None


def get_intent_classifier() -> PIIAwareIntentClassifier:
    """Get the global intent classifier instance."""
    global _classifier
    if _classifier is None:
        _classifier = PIIAwareIntentClassifier()
    return _classifier
