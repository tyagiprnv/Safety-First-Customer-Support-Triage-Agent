"""Token usage and cost tracking for LLM API calls."""
import tiktoken
from typing import Dict, Optional, Tuple
from dataclasses import dataclass, asdict
from collections import defaultdict


# OpenAI API pricing (as of January 2026)
# Prices in USD per 1K tokens
PRICING = {
    "gpt-4o-mini": {
        "input": 0.00015,   # $0.15 per 1M tokens
        "output": 0.0006,   # $0.60 per 1M tokens
    },
    "gpt-4o": {
        "input": 0.0025,    # $2.50 per 1M tokens
        "output": 0.01,     # $10.00 per 1M tokens
    },
    "text-embedding-3-small": {
        "input": 0.00002,   # $0.02 per 1M tokens
        "output": 0.0,      # No output tokens for embeddings
    },
}


@dataclass
class TokenUsage:
    """Token usage for a single API call."""
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float


class CostTracker:
    """Track token usage and costs across all LLM API calls."""

    def __init__(self):
        """Initialize the cost tracker."""
        self.total_cost = 0.0
        self.usage_by_model = defaultdict(lambda: {"input_tokens": 0, "output_tokens": 0, "calls": 0, "cost": 0.0})
        self.usage_by_action = defaultdict(lambda: {"input_tokens": 0, "output_tokens": 0, "calls": 0, "cost": 0.0})

        # Initialize tokenizers for token counting
        self.tokenizers = {}

    def count_tokens(self, text: str, model: str) -> int:
        """
        Count tokens in text using the model's tokenizer.

        Args:
            text: Text to count tokens for
            model: Model name (e.g., "gpt-4o", "gpt-4o-mini")

        Returns:
            Number of tokens
        """
        # Get or create tokenizer for this model
        if model not in self.tokenizers:
            try:
                # Try model-specific encoding
                encoding = tiktoken.encoding_for_model(model)
            except KeyError:
                # Fallback to cl100k_base (used by GPT-4 and GPT-3.5-turbo)
                encoding = tiktoken.get_encoding("cl100k_base")

            self.tokenizers[model] = encoding

        encoding = self.tokenizers[model]
        return len(encoding.encode(text))

    def calculate_cost(self, model: str, input_tokens: int, output_tokens: int) -> float:
        """
        Calculate cost for token usage.

        Args:
            model: Model name
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens

        Returns:
            Cost in USD
        """
        if model not in PRICING:
            # Unknown model, return 0
            return 0.0

        pricing = PRICING[model]
        input_cost = (input_tokens / 1000) * pricing["input"]
        output_cost = (output_tokens / 1000) * pricing["output"]

        return input_cost + output_cost

    def track_completion(
        self,
        model: str,
        input_text: str,
        output_text: str,
        action: Optional[str] = None
    ) -> TokenUsage:
        """
        Track a completion API call.

        Args:
            model: Model used
            input_text: Input prompt text
            output_text: Generated output text
            action: Action type (TEMPLATE, GENERATED, ESCALATE) for grouping

        Returns:
            TokenUsage object with details
        """
        # Count tokens
        input_tokens = self.count_tokens(input_text, model)
        output_tokens = self.count_tokens(output_text, model)

        # Calculate cost
        cost = self.calculate_cost(model, input_tokens, output_tokens)

        # Update totals
        self.total_cost += cost

        # Update by model
        self.usage_by_model[model]["input_tokens"] += input_tokens
        self.usage_by_model[model]["output_tokens"] += output_tokens
        self.usage_by_model[model]["calls"] += 1
        self.usage_by_model[model]["cost"] += cost

        # Update by action if provided
        if action:
            self.usage_by_action[action]["input_tokens"] += input_tokens
            self.usage_by_action[action]["output_tokens"] += output_tokens
            self.usage_by_action[action]["calls"] += 1
            self.usage_by_action[action]["cost"] += cost

        return TokenUsage(
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost
        )

    def track_embedding(
        self,
        model: str,
        text: str,
        action: Optional[str] = None
    ) -> TokenUsage:
        """
        Track an embedding API call.

        Args:
            model: Embedding model used
            text: Text that was embedded
            action: Action type for grouping

        Returns:
            TokenUsage object with details
        """
        # Count tokens
        input_tokens = self.count_tokens(text, model)

        # Calculate cost (embeddings have no output tokens)
        cost = self.calculate_cost(model, input_tokens, 0)

        # Update totals
        self.total_cost += cost

        # Update by model
        self.usage_by_model[model]["input_tokens"] += input_tokens
        self.usage_by_model[model]["calls"] += 1
        self.usage_by_model[model]["cost"] += cost

        # Update by action if provided
        if action:
            self.usage_by_action[action]["input_tokens"] += input_tokens
            self.usage_by_action[action]["calls"] += 1
            self.usage_by_action[action]["cost"] += cost

        return TokenUsage(
            model=model,
            input_tokens=input_tokens,
            output_tokens=0,
            cost_usd=cost
        )

    def get_summary(self) -> Dict:
        """
        Get summary of all tracked usage and costs.

        Returns:
            Dictionary with usage statistics
        """
        return {
            "total_cost_usd": round(self.total_cost, 6),
            "by_model": {
                model: {
                    "input_tokens": stats["input_tokens"],
                    "output_tokens": stats["output_tokens"],
                    "total_tokens": stats["input_tokens"] + stats["output_tokens"],
                    "calls": stats["calls"],
                    "cost_usd": round(stats["cost"], 6)
                }
                for model, stats in self.usage_by_model.items()
            },
            "by_action": {
                action: {
                    "input_tokens": stats["input_tokens"],
                    "output_tokens": stats["output_tokens"],
                    "total_tokens": stats["input_tokens"] + stats["output_tokens"],
                    "calls": stats["calls"],
                    "cost_usd": round(stats["cost"], 6)
                }
                for action, stats in self.usage_by_action.items()
            }
        }

    def get_cost_per_request(self, total_requests: int) -> float:
        """Calculate average cost per request."""
        if total_requests == 0:
            return 0.0
        return self.total_cost / total_requests

    def get_projected_monthly_cost(self, requests_per_day: float) -> float:
        """
        Project monthly cost based on average cost per request.

        Args:
            requests_per_day: Average requests per day

        Returns:
            Projected monthly cost in USD
        """
        if requests_per_day == 0:
            return 0.0

        # Use current average cost per request
        avg_cost = self.total_cost / max(1, sum(stats["calls"] for stats in self.usage_by_action.values()))

        return avg_cost * requests_per_day * 30

    def reset(self):
        """Reset all tracking."""
        self.total_cost = 0.0
        self.usage_by_model.clear()
        self.usage_by_action.clear()


# Global cost tracker instance
_cost_tracker: Optional[CostTracker] = None


def get_cost_tracker() -> CostTracker:
    """Get the global cost tracker instance."""
    global _cost_tracker
    if _cost_tracker is None:
        _cost_tracker = CostTracker()
    return _cost_tracker
