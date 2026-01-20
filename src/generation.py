"""Response generation with grounding."""
import openai
from typing import Optional
from src.retrieval import RetrievalResult
from src.config import get_settings


GENERATION_SYSTEM_PROMPT = """You are a helpful customer support agent. Your job is to answer customer questions based ONLY on the provided context from our policy documents.

CRITICAL RULES:
1. Answer ONLY based on the provided context
2. If the context doesn't contain the answer, say "I don't have enough information to answer that. Let me connect you with a specialist."
3. Be concise and professional
4. Do not make assumptions or add information not in the context
5. Do not mention that PII was redacted
6. Do not make up URLs, dates, or specific details not in the context
7. If you're uncertain, escalate rather than guessing

Your response should:
- Directly answer the question
- Be 2-4 sentences maximum
- Be friendly and professional
- Not include greetings or sign-offs"""


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
        self.client = openai.OpenAI(api_key=settings.openai_api_key)
        self.model = settings.generation_model
        self.max_tokens = 300  # Keep responses concise

    def generate(
        self,
        query: str,
        retrieval_result: RetrievalResult
    ) -> tuple[str, list[dict]]:
        """
        Generate a response based on retrieved context.

        Args:
            query: User query (redacted)
            retrieval_result: Retrieved context

        Returns:
            Tuple of (response_text, sources)
        """
        # Combine retrieved chunks into context
        context = "\n\n".join([
            f"[Document {i+1}]\n{chunk}"
            for i, chunk in enumerate(retrieval_result.chunks)
        ])

        # Create user prompt
        user_prompt = GENERATION_USER_PROMPT_TEMPLATE.format(
            context=context,
            query=query
        )

        try:
            # Generate response
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": GENERATION_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3,  # Low temperature for consistency
                max_tokens=self.max_tokens
            )

            response_text = response.choices[0].message.content.strip()

            return response_text, retrieval_result.sources

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
