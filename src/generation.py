"""Response generation with grounding."""
import json
import openai
from typing import Optional, Dict, Any
from src.retrieval import RetrievalResult
from src.config import get_settings
from src.monitoring.cost_tracker import get_cost_tracker


GENERATION_SYSTEM_PROMPT = """You are a helpful customer support agent. Your job is to answer customer questions based ONLY on the provided context from our policy documents.

CRITICAL RULES:
1. Answer ONLY based on the provided context
2. If the context doesn't contain the answer, say "I don't have enough information to answer that. Let me connect you with a specialist."
3. Be concise and professional
4. Do not make assumptions or add information not in the context
5. Do not mention that PII was redacted
6. Do not make up URLs, dates, or specific details not in the context
7. If you're uncertain, escalate rather than guessing

You must respond with JSON in the following format:
{
  "answer": "Your response text here (2-4 sentences maximum)",
  "confidence_level": "high|medium|low",
  "requires_escalation": true|false,
  "sources_used": [0, 1, 2]
}

- answer: The actual response to the customer (friendly, professional, no greetings/sign-offs)
- confidence_level: "high" if fully answered, "medium" if partial, "low" if uncertain
- requires_escalation: true if you cannot answer or are uncertain
- sources_used: Array of document indices (0-indexed) that you used to answer"""


GENERATION_USER_PROMPT_TEMPLATE = """Context from our policy documents:

{context}

---

Customer question (PII has been redacted for privacy):
{query}

Provide a helpful response based ONLY on the context above. If the context doesn't fully answer the question, say so and offer to escalate."""


class ResponseGenerator:
    """Generate responses using LLM with retrieved context."""

    def __init__(self):
        """Initialize the response generator."""
        settings = get_settings()
        self.client = openai.OpenAI(api_key=settings.get_api_key(), base_url=settings.get_base_url())
        self.model = settings.generation_model
        self.temperature = settings.generation_temperature
        self.max_tokens = 500  # Increased for JSON structure and DeepSeek compatibility
        self.cost_tracker = get_cost_tracker()

    def generate(
        self,
        query: str,
        retrieval_result: RetrievalResult
    ) -> tuple[str, list[dict], Optional[Dict[str, Any]]]:
        """
        Generate a response based on retrieved context.

        Args:
            query: User query (redacted)
            retrieval_result: Retrieved context

        Returns:
            Tuple of (response_text, sources, metadata)
            metadata includes: token_usage, cost_usd, confidence_level, requires_escalation
        """
        # Combine retrieved chunks into context
        context = "\n\n".join([
            f"[Document {i}]\n{chunk}"
            for i, chunk in enumerate(retrieval_result.chunks)
        ])

        # Create user prompt
        user_prompt = GENERATION_USER_PROMPT_TEMPLATE.format(
            context=context,
            query=query
        )

        try:
            # Generate response with structured output
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": GENERATION_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                response_format={"type": "json_object"}
            )

            response_text = response.choices[0].message.content.strip()

            # Parse structured JSON response
            try:
                structured_output = json.loads(response_text)
                answer = structured_output.get("answer", response_text)
                confidence_level = structured_output.get("confidence_level", "medium")
                requires_escalation = structured_output.get("requires_escalation", False)
                sources_used = structured_output.get("sources_used", list(range(len(retrieval_result.chunks))))
            except json.JSONDecodeError:
                # Fallback if JSON parsing fails
                answer = response_text
                confidence_level = "medium"
                requires_escalation = False
                sources_used = list(range(len(retrieval_result.chunks)))

            # Track token usage and cost
            input_text = GENERATION_SYSTEM_PROMPT + user_prompt
            output_text = response_text
            token_usage = self.cost_tracker.track_completion(
                model=self.model,
                input_text=input_text,
                output_text=output_text,
                action="GENERATED"
            )

            metadata = {
                "input_tokens": token_usage.input_tokens,
                "output_tokens": token_usage.output_tokens,
                "cost_usd": token_usage.cost_usd,
                "confidence_level": confidence_level,
                "requires_escalation": requires_escalation,
                "sources_used": sources_used
            }

            return answer, retrieval_result.sources, metadata

        except Exception as e:
            # On error, return None to trigger escalation
            raise Exception(f"Generation failed: {str(e)}")


# Global instance
_generator: Optional[ResponseGenerator] = None


def get_response_generator() -> ResponseGenerator:
    """Get the global response generator instance."""
    global _generator
    if _generator is None:
        _generator = ResponseGenerator()
    return _generator
