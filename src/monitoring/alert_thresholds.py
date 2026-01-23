"""Alert threshold configuration for production monitoring.

This module documents alert rules that should be configured in your monitoring system
(e.g., Prometheus Alertmanager, Grafana alerts, CloudWatch alarms).

For Prometheus/Grafana implementation, these thresholds can be used to create alerting rules.
"""

from typing import Dict, Any


# Alert severity levels
class Severity:
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


# Alert threshold definitions
ALERT_THRESHOLDS = {
    # Escalation rate alerts
    "escalation_rate_warning": {
        "metric": "escalation_rate",
        "threshold": 0.45,  # 45%
        "comparison": ">",
        "duration": "5m",  # Must be above threshold for 5 minutes
        "severity": Severity.WARNING,
        "description": "Escalation rate is higher than expected (>45%)",
        "action": "Investigate low confidence classifications or retrieval issues"
    },
    "escalation_rate_critical": {
        "metric": "escalation_rate",
        "threshold": 0.60,  # 60%
        "comparison": ">",
        "duration": "5m",
        "severity": Severity.CRITICAL,
        "description": "Escalation rate is critically high (>60%)",
        "action": "System may be degraded - check LLM availability, confidence thresholds, and vector DB"
    },

    # Template usage alerts (we want high template usage)
    "template_usage_low": {
        "metric": "template_usage_rate",
        "threshold": 0.30,  # 30%
        "comparison": "<",
        "duration": "15m",
        "severity": Severity.INFO,
        "description": "Template usage is below target (<30%)",
        "action": "Review template coverage - may need more templates or lower similarity threshold"
    },

    # Latency alerts
    "latency_template_p95_high": {
        "metric": "latency_template_p95",
        "threshold": 500,  # 500ms
        "comparison": ">",
        "duration": "5m",
        "severity": Severity.WARNING,
        "description": "Template p95 latency exceeds 500ms",
        "action": "Check system resources - templates should be <200ms typically"
    },
    "latency_generated_p95_high": {
        "metric": "latency_generated_p95",
        "threshold": 5000,  # 5s
        "comparison": ">",
        "duration": "5m",
        "severity": Severity.WARNING,
        "description": "Generated response p95 latency exceeds 5s",
        "action": "Check OpenAI API latency or vector DB performance"
    },
    "latency_generated_p99_high": {
        "metric": "latency_generated_p99",
        "threshold": 8000,  # 8s
        "comparison": ">",
        "duration": "5m",
        "severity": Severity.CRITICAL,
        "description": "Generated response p99 latency exceeds 8s",
        "action": "Critical latency issue - investigate OpenAI API or timeout errors"
    },

    # Error rate alerts
    "error_rate_warning": {
        "metric": "error_rate",
        "threshold": 0.01,  # 1%
        "comparison": ">",
        "duration": "5m",
        "severity": Severity.WARNING,
        "description": "Error rate exceeds 1%",
        "action": "Check logs for error patterns"
    },
    "error_rate_critical": {
        "metric": "error_rate",
        "threshold": 0.05,  # 5%
        "comparison": ">",
        "duration": "5m",
        "severity": Severity.CRITICAL,
        "description": "Error rate exceeds 5%",
        "action": "System is experiencing high error rates - check LLM API, vector DB, and application logs"
    },

    # Safety alerts (CRITICAL - should never fire)
    "safety_violation_detected": {
        "metric": "safety_violations",
        "threshold": 0,
        "comparison": ">",
        "duration": "1m",
        "severity": Severity.CRITICAL,
        "description": "SAFETY VIOLATION: Unsafe response detected",
        "action": "IMMEDIATE ACTION REQUIRED - Review logs, escalate to on-call engineer"
    },

    # Cost alerts
    "daily_cost_high": {
        "metric": "daily_cost_usd",
        "threshold": 50.0,  # $50/day
        "comparison": ">",
        "duration": "1h",
        "severity": Severity.WARNING,
        "description": "Daily API cost projection exceeds $50",
        "action": "Review cost efficiency - check if traffic increased or costs per request rose"
    },
    "daily_cost_critical": {
        "metric": "daily_cost_usd",
        "threshold": 100.0,  # $100/day
        "comparison": ">",
        "duration": "1h",
        "severity": Severity.CRITICAL,
        "description": "Daily API cost projection exceeds $100",
        "action": "Cost spike detected - investigate immediately"
    },

    # Request volume alerts
    "request_volume_low": {
        "metric": "requests_per_minute",
        "threshold": 0.1,  # <0.1 req/min (less than 1 request per 10 minutes)
        "comparison": "<",
        "duration": "30m",
        "severity": Severity.INFO,
        "description": "Very low request volume",
        "action": "Service may not be receiving traffic - check upstream services"
    },
    "request_volume_high": {
        "metric": "requests_per_minute",
        "threshold": 100,  # >100 req/min
        "comparison": ">",
        "duration": "5m",
        "severity": Severity.WARNING,
        "description": "High request volume detected",
        "action": "Monitor for capacity issues - may need to scale horizontally"
    },

    # Support deflection rate
    "deflection_rate_low": {
        "metric": "support_deflection_rate",
        "threshold": 0.50,  # 50%
        "comparison": "<",
        "duration": "30m",
        "severity": Severity.INFO,
        "description": "Support deflection rate below 50%",
        "action": "System is escalating more than expected - review confidence thresholds or template coverage"
    }
}


def get_alert_rules_for_prometheus() -> str:
    """
    Generate Prometheus alerting rules YAML.

    Returns:
        YAML string with Prometheus alert rules
    """
    yaml_lines = ["groups:", "- name: triage_agent_alerts", "  interval: 30s", "  rules:"]

    for alert_name, config in ALERT_THRESHOLDS.items():
        yaml_lines.append(f"  - alert: {alert_name}")
        yaml_lines.append(f"    expr: {config['metric']} {config['comparison']} {config['threshold']}")
        yaml_lines.append(f"    for: {config['duration']}")
        yaml_lines.append(f"    labels:")
        yaml_lines.append(f"      severity: {config['severity']}")
        yaml_lines.append(f"    annotations:")
        yaml_lines.append(f"      summary: \"{config['description']}\"")
        yaml_lines.append(f"      description: \"{config['action']}\"")
        yaml_lines.append("")

    return "\n".join(yaml_lines)


def check_thresholds(metrics: Dict[str, Any]) -> Dict[str, Any]:
    """
    Check if current metrics violate any alert thresholds.

    Args:
        metrics: Current system metrics

    Returns:
        Dict with triggered alerts
    """
    triggered_alerts = []

    for alert_name, config in ALERT_THRESHOLDS.items():
        metric_value = metrics.get(config["metric"])

        if metric_value is None:
            continue

        # Check threshold
        triggered = False
        if config["comparison"] == ">":
            triggered = metric_value > config["threshold"]
        elif config["comparison"] == "<":
            triggered = metric_value < config["threshold"]
        elif config["comparison"] == ">=":
            triggered = metric_value >= config["threshold"]
        elif config["comparison"] == "<=":
            triggered = metric_value <= config["threshold"]

        if triggered:
            triggered_alerts.append({
                "alert": alert_name,
                "severity": config["severity"],
                "description": config["description"],
                "action": config["action"],
                "metric": config["metric"],
                "threshold": config["threshold"],
                "current_value": metric_value
            })

    return {
        "triggered_count": len(triggered_alerts),
        "alerts": triggered_alerts
    }


# Example usage for documentation
if __name__ == "__main__":
    print("=== Alert Thresholds Configuration ===\n")

    for alert_name, config in ALERT_THRESHOLDS.items():
        print(f"{alert_name}:")
        print(f"  Metric: {config['metric']}")
        print(f"  Threshold: {config['comparison']} {config['threshold']}")
        print(f"  Duration: {config['duration']}")
        print(f"  Severity: {config['severity']}")
        print(f"  Description: {config['description']}")
        print(f"  Action: {config['action']}")
        print()

    print("\n=== Prometheus Alert Rules ===\n")
    print(get_alert_rules_for_prometheus())
