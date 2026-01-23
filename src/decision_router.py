"""Decision routing logic with explicit precedence."""
from typing import Optional, Dict, Any, List
import json
import re
from pathlib import Path
from src.models import (
    Action, RoutingDecision, Intent, ClassificationResult,
    RedactionResult
)
from src.config import get_settings
from src.intent_classifier import FORBIDDEN_INTENTS


class Template:
    """Response template."""

    def __init__(self, template_data: dict):
        self.id = template_data["id"]
        self.intent = Intent(template_data["intent"])
        self.risk = template_data["risk"]
        self.confidence_required = template_data["confidence_required"]
        self.keywords = template_data.get("keywords", [])
        self.template = template_data["template"]

    def matches(self, message: str, intent: Intent) -> float:
        """
        Calculate match score for a message using token-level matching.

        Args:
            message: User message (possibly redacted)
            intent: Classified intent

        Returns:
            Match score between 0.0 and 1.0
        """
        if self.intent != intent:
            return 0.0

        if not self.keywords:
            # No keywords means intent match only
            return 0.7

        # Tokenize message and keywords
        message_tokens = self._tokenize(message)
        keyword_tokens = set()
        for keyword in self.keywords:
            keyword_tokens.update(self._tokenize(keyword))

        # Count matching tokens
        matched_tokens = message_tokens & keyword_tokens

        if not keyword_tokens:
            return 0.0

        # Adaptive scoring for templates with many keywords
        if len(keyword_tokens) > 8:
            # For templates with 9+ keyword tokens, use absolute match count
            # Need at least 2-3 matching tokens to reach high score (2.5 for 0.8 threshold)
            absolute_score = min(len(matched_tokens) / 2.5, 1.0)
            ratio_score = len(matched_tokens) / len(keyword_tokens)
            # Use the higher of the two scores
            score = max(absolute_score, ratio_score)
        else:
            # For templates with fewer keywords, use ratio-based scoring
            score = len(matched_tokens) / len(keyword_tokens)

        return score

    @staticmethod
    def _tokenize(text: str) -> set:
        """
        Split text into lowercase word tokens with simple stemming.

        Args:
            text: Text to tokenize

        Returns:
            Set of lowercase word tokens (with plural normalization)
        """
        tokens = re.findall(r'\b\w+\b', text.lower())
        # Simple plural handling: remove trailing 's' for words > 3 chars
        normalized = {t.rstrip('s') if len(t) > 3 else t for t in tokens}
        return normalized


class TemplateStore:
    """Store and retrieve response templates."""

    def __init__(self, templates_path: str):
        """
        Load templates from JSON file.

        Args:
            templates_path: Path to templates JSON file
        """
        self.templates: List[Template] = []
        self._load_templates(templates_path)

    def _load_templates(self, templates_path: str):
        """Load templates from file."""
        path = Path(templates_path)
        if not path.exists():
            return

        with open(path) as f:
            data = json.load(f)

        for template_data in data.get("templates", []):
            self.templates.append(Template(template_data))

    def find_best_match(
        self,
        message: str,
        intent: Intent,
        confidence: float
    ) -> Optional[tuple[Template, float]]:
        """
        Find best matching template.

        Args:
            message: User message
            intent: Classified intent
            confidence: Classification confidence

        Returns:
            Tuple of (template, match_score) or None
        """
        best_template = None
        best_score = 0.0

        for template in self.templates:
            # Check if confidence meets template requirement
            if confidence < template.confidence_required:
                continue

            score = template.matches(message, intent)
            if score > best_score:
                best_score = score
                best_template = template

        if best_template and best_score > 0.0:
            return best_template, best_score

        return None


class DecisionRouter:
    """Route requests to appropriate action with explicit precedence."""

    def __init__(self, template_store: Optional[TemplateStore] = None):
        """
        Initialize the decision router.

        Args:
            template_store: Store of response templates
        """
        settings = get_settings()
        self.min_confidence = settings.min_confidence_threshold
        self.high_confidence = settings.high_confidence_threshold
        self.high_risk_threshold = settings.high_risk_threshold
        self.template_similarity = settings.template_similarity_threshold
        self.min_retrieval_score = settings.min_retrieval_score
        self.pii_medium_confidence = settings.pii_medium_confidence_threshold

        # Load templates if not provided
        if template_store is None:
            templates_path = Path(__file__).parent.parent / "data" / "templates" / "response_templates.json"
            self.template_store = TemplateStore(str(templates_path))
        else:
            self.template_store = template_store

    def route(
        self,
        classification: ClassificationResult,
        redaction: RedactionResult,
        risk_score: float,
        retrieval_score: Optional[float] = None
    ) -> RoutingDecision:
        """
        Route a request to an action with explicit precedence.

        Routing Logic (in order of precedence):
        1. Safety checks (high-risk PII, forbidden intents, high risk score)
        2. Confidence checks (low confidence, medium confidence with PII)
        3. Template matching (preferred for safety)
        4. RAG-based generation (requires good retrieval)
        5. Default: escalate

        Args:
            classification: Intent classification result
            redaction: PII redaction result
            risk_score: Calculated risk score
            retrieval_score: Optional retrieval quality score

        Returns:
            RoutingDecision with action and reason
        """
        # Use adjusted confidence if available
        confidence = classification.adjusted_confidence or classification.confidence

        # === 1. SAFETY CHECKS (HIGHEST PRIORITY) ===

        # 1a. High-risk PII detected (SSN, credit card)
        if redaction.has_high_risk_pii:
            return self._escalate(
                reason="high_risk_pii_detected",
                risk_score=risk_score,
                metadata={
                    "pii_types": redaction.pii_types,
                    "high_risk": True
                }
            )

        # 1b. Forbidden intent
        if classification.is_forbidden or classification.intent in FORBIDDEN_INTENTS:
            return self._escalate(
                reason="forbidden_intent",
                risk_score=risk_score,
                metadata={
                    "intent": classification.intent.value,
                    "forbidden": True
                }
            )

        # 1c. High risk score
        if risk_score > self.high_risk_threshold:
            return self._escalate(
                reason="high_risk_score",
                risk_score=risk_score,
                metadata={
                    "risk_score": risk_score,
                    "threshold": self.high_risk_threshold
                }
            )

        # === 2. CONFIDENCE CHECKS ===

        # 2a. Low confidence
        if confidence < self.min_confidence:
            return self._escalate(
                reason="low_confidence",
                risk_score=risk_score,
                metadata={
                    "confidence": confidence,
                    "threshold": self.min_confidence
                }
            )

        # 2b. Medium confidence with PII (extra conservative)
        if confidence < self.pii_medium_confidence and redaction.has_pii:
            return self._escalate(
                reason="medium_confidence_with_pii",
                risk_score=risk_score,
                metadata={
                    "confidence": confidence,
                    "pii_present": True,
                    "threshold": self.pii_medium_confidence
                }
            )

        # === 3. TEMPLATE MATCHING (PREFERRED) ===

        template_match = self.template_store.find_best_match(
            redaction.redacted_message,
            classification.intent,
            confidence
        )

        if template_match:
            template, match_score = template_match
            if match_score >= self.template_similarity:
                return RoutingDecision(
                    action=Action.TEMPLATE,
                    reason="high_template_match",
                    template_id=template.id,
                    risk_score=risk_score,
                    metadata={
                        "template_id": template.id,
                        "match_score": match_score,
                        "confidence": confidence
                    }
                )

        # === 4. RAG-BASED GENERATION ===

        # 4a. If retrieval_score is provided, check quality
        if retrieval_score is not None and retrieval_score < self.min_retrieval_score:
            return self._escalate(
                reason="insufficient_retrieval",
                risk_score=risk_score,
                metadata={
                    "retrieval_score": retrieval_score,
                    "threshold": self.min_retrieval_score
                }
            )

        # 4b. High confidence -> allow generation (retrieval will be done by API)
        if confidence >= self.high_confidence:
            return RoutingDecision(
                action=Action.GENERATED,
                reason="high_confidence_for_generation",
                risk_score=risk_score,
                metadata={
                    "confidence": confidence,
                    "retrieval_score": retrieval_score
                }
            )

        # === 5. DEFAULT: ESCALATE ===

        return self._escalate(
            reason="default_safe",
            risk_score=risk_score,
            metadata={
                "confidence": confidence,
                "retrieval_score": retrieval_score,
                "note": "No clear path to safe automation"
            }
        )

    def _escalate(
        self,
        reason: str,
        risk_score: float,
        metadata: Optional[Dict[str, Any]] = None
    ) -> RoutingDecision:
        """Create an escalation decision."""
        return RoutingDecision(
            action=Action.ESCALATE,
            reason=reason,
            risk_score=risk_score,
            metadata=metadata or {}
        )


# Global instance
_router: Optional[DecisionRouter] = None


def get_decision_router() -> DecisionRouter:
    """Get the global decision router instance."""
    global _router
    if _router is None:
        _router = DecisionRouter()
    return _router
