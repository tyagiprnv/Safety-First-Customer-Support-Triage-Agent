"""Mock escalation system for creating support tickets."""
import uuid
from datetime import datetime
from typing import Dict, Any
from src.models import RedactionResult
from src.logging_config import get_logger

logger = get_logger(__name__)


class EscalationSystem:
    """Mock system for creating escalation tickets."""

    def create_ticket(
        self,
        redaction: RedactionResult,
        reason: str,
        metadata: Dict[str, Any]
    ) -> str:
        """
        Create an escalation ticket for human review.

        Args:
            redaction: PII redaction result
            reason: Reason for escalation
            metadata: Additional context

        Returns:
            Ticket ID
        """
        # Generate ticket ID
        ticket_id = f"TKT-{str(uuid.uuid4())[:8].upper()}"

        # Log ticket creation (PII-free)
        logger.info(
            "escalation_ticket_created",
            ticket_id=ticket_id,
            reason=reason,
            has_pii=redaction.has_pii,
            has_high_risk_pii=redaction.has_high_risk_pii,
            pii_types=redaction.pii_types,
            redaction_count=redaction.redaction_count,
            timestamp=datetime.utcnow().isoformat(),
            metadata=metadata
        )

        # In a real system, this would:
        # 1. Store the original (unredacted) message securely
        # 2. Create a ticket in the ticketing system
        # 3. Route to appropriate support queue
        # 4. Notify support agents
        # 5. Track ticket status

        return ticket_id


# Global instance
_escalation_system = None


def get_escalation_system() -> EscalationSystem:
    """Get the global escalation system instance."""
    global _escalation_system
    if _escalation_system is None:
        _escalation_system = EscalationSystem()
    return _escalation_system
