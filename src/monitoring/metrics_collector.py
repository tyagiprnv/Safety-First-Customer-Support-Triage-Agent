"""Enhanced metrics collection with percentiles and persistence."""
import json
import numpy as np
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime
from collections import defaultdict


class MetricsCollector:
    """
    Collect and persist system metrics with percentile calculations.

    Tracks:
    - Request counts by action type
    - Latency distributions (p50, p95, p99)
    - Safety metrics
    - Action distribution
    - Error rates
    """

    def __init__(self, persistence_path: Optional[str] = None):
        """
        Initialize metrics collector.

        Args:
            persistence_path: Path to save metrics (default: data/metrics_history.json)
        """
        self.persistence_path = persistence_path or "data/metrics_history.json"
        self.reset_metrics()

        # Try to load persisted metrics
        self.load_metrics()

    def reset_metrics(self):
        """Reset all metrics to initial state."""
        self.metrics = {
            "total_requests": 0,
            "action_counts": defaultdict(int),
            "latencies": defaultdict(list),
            "safety_metrics": {
                "unsafe_responses": 0,
                "high_risk_pii_escalations": 0,
                "forbidden_intent_escalations": 0
            },
            "error_count": 0,
            "start_time": datetime.now().isoformat(),
            "last_updated": datetime.now().isoformat()
        }

    def record_request(
        self,
        action: str,
        latency_ms: float,
        is_forbidden: bool = False,
        has_high_risk_pii: bool = False,
        is_error: bool = False
    ):
        """
        Record a single request.

        Args:
            action: Action taken (TEMPLATE, GENERATED, ESCALATE)
            latency_ms: Request latency in milliseconds
            is_forbidden: Whether this was a forbidden intent
            has_high_risk_pii: Whether high-risk PII was detected
            is_error: Whether this request resulted in an error
        """
        self.metrics["total_requests"] += 1
        self.metrics["action_counts"][action] += 1
        self.metrics["latencies"][action.lower()].append(latency_ms)

        if is_forbidden:
            self.metrics["safety_metrics"]["forbidden_intent_escalations"] += 1

        if has_high_risk_pii:
            self.metrics["safety_metrics"]["high_risk_pii_escalations"] += 1

        if is_error:
            self.metrics["error_count"] += 1

        self.metrics["last_updated"] = datetime.now().isoformat()

    def get_latency_percentiles(self, action: Optional[str] = None) -> Dict[str, Dict[str, float]]:
        """
        Calculate latency percentiles.

        Args:
            action: Specific action to get percentiles for (or None for all)

        Returns:
            Dict with p50, p95, p99, mean, min, max for each action type
        """
        result = {}

        actions_to_process = [action] if action else self.metrics["latencies"].keys()

        for act in actions_to_process:
            latencies = self.metrics["latencies"].get(act, [])

            if not latencies:
                result[act] = {
                    "count": 0,
                    "p50": 0.0,
                    "p95": 0.0,
                    "p99": 0.0,
                    "mean": 0.0,
                    "min": 0.0,
                    "max": 0.0
                }
            else:
                result[act] = {
                    "count": len(latencies),
                    "p50": float(np.percentile(latencies, 50)),
                    "p95": float(np.percentile(latencies, 95)),
                    "p99": float(np.percentile(latencies, 99)),
                    "mean": float(np.mean(latencies)),
                    "min": float(np.min(latencies)),
                    "max": float(np.max(latencies))
                }

        return result

    def get_action_distribution(self) -> Dict[str, Any]:
        """
        Get action distribution counts and percentages.

        Returns:
            Dict with counts and percentages for each action
        """
        total = self.metrics["total_requests"]

        distribution = {
            "counts": dict(self.metrics["action_counts"]),
            "percentages": {}
        }

        if total > 0:
            for action, count in self.metrics["action_counts"].items():
                distribution["percentages"][action] = round(count / total, 4)

        return distribution

    def get_escalation_rate(self) -> float:
        """Calculate escalation rate."""
        total = self.metrics["total_requests"]
        escalations = self.metrics["action_counts"].get("ESCALATE", 0)

        return escalations / total if total > 0 else 0.0

    def get_error_rate(self) -> float:
        """Calculate error rate."""
        total = self.metrics["total_requests"]
        errors = self.metrics["error_count"]

        return errors / total if total > 0 else 0.0

    def get_summary(self) -> Dict[str, Any]:
        """
        Get comprehensive metrics summary.

        Returns:
            Dict with all metrics including percentiles
        """
        return {
            "overview": {
                "total_requests": self.metrics["total_requests"],
                "start_time": self.metrics["start_time"],
                "last_updated": self.metrics["last_updated"],
                "error_count": self.metrics["error_count"],
                "error_rate": round(self.get_error_rate(), 4)
            },
            "action_distribution": self.get_action_distribution(),
            "latencies": self.get_latency_percentiles(),
            "escalation_rate": round(self.get_escalation_rate(), 4),
            "safety_metrics": self.metrics["safety_metrics"]
        }

    def save_metrics(self):
        """Persist metrics to disk."""
        path = Path(self.persistence_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        # Convert defaultdicts to regular dicts for JSON serialization
        serializable_metrics = {
            "total_requests": self.metrics["total_requests"],
            "action_counts": dict(self.metrics["action_counts"]),
            "latencies": {k: v for k, v in self.metrics["latencies"].items()},
            "safety_metrics": self.metrics["safety_metrics"],
            "error_count": self.metrics["error_count"],
            "start_time": self.metrics["start_time"],
            "last_updated": self.metrics["last_updated"]
        }

        # Load existing history
        history = []
        if path.exists():
            try:
                with open(path, 'r') as f:
                    history = json.load(f)
            except Exception:
                history = []

        # Append current metrics snapshot
        snapshot = {
            "timestamp": datetime.now().isoformat(),
            "metrics": serializable_metrics,
            "summary": self.get_summary()
        }

        history.append(snapshot)

        # Keep only last 100 snapshots
        history = history[-100:]

        # Save updated history
        with open(path, 'w') as f:
            json.dump(history, f, indent=2)

    def load_metrics(self):
        """Load persisted metrics from disk."""
        path = Path(self.persistence_path)

        if not path.exists():
            return

        try:
            with open(path, 'r') as f:
                history = json.load(f)

            # Load the most recent snapshot
            if history:
                latest = history[-1]["metrics"]

                self.metrics["total_requests"] = latest["total_requests"]
                self.metrics["action_counts"] = defaultdict(int, latest["action_counts"])
                self.metrics["latencies"] = defaultdict(list, {
                    k: list(v) for k, v in latest["latencies"].items()
                })
                self.metrics["safety_metrics"] = latest["safety_metrics"]
                self.metrics["error_count"] = latest["error_count"]
                self.metrics["start_time"] = latest["start_time"]
                self.metrics["last_updated"] = latest["last_updated"]

        except Exception as e:
            # If loading fails, start fresh
            print(f"Failed to load metrics: {e}")

    def get_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get historical metrics snapshots.

        Args:
            limit: Number of recent snapshots to return

        Returns:
            List of historical metric snapshots
        """
        path = Path(self.persistence_path)

        if not path.exists():
            return []

        try:
            with open(path, 'r') as f:
                history = json.load(f)

            return history[-limit:]

        except Exception:
            return []


# Global metrics collector instance
_metrics_collector: Optional[MetricsCollector] = None


def get_metrics_collector() -> MetricsCollector:
    """Get the global metrics collector instance."""
    global _metrics_collector
    if _metrics_collector is None:
        _metrics_collector = MetricsCollector()
    return _metrics_collector
