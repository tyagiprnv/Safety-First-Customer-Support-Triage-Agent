"""Regression detection for evaluation metrics."""
import json
import sys
from pathlib import Path
from typing import Dict, Any, List, Tuple
from datetime import datetime


class RegressionDetector:
    """Detect performance regressions by comparing metrics against baseline."""

    # Thresholds for regression detection
    ACCURACY_THRESHOLD = 0.02  # 2% drop in accuracy triggers warning
    ESCALATION_RATE_THRESHOLD = 0.05  # 5% change in escalation rate
    LATENCY_THRESHOLD = 0.15  # 15% increase in latency
    SAFETY_THRESHOLD = 0.01  # Any drop in safety metrics

    def __init__(self, baseline_path: str):
        """
        Initialize regression detector.

        Args:
            baseline_path: Path to baseline metrics JSON file
        """
        self.baseline_path = baseline_path
        self.baseline = self._load_baseline()

    def _load_baseline(self) -> Dict[str, Any]:
        """Load baseline metrics from file."""
        path = Path(self.baseline_path)

        if not path.exists():
            raise FileNotFoundError(f"Baseline file not found: {self.baseline_path}")

        with open(path, 'r') as f:
            data = json.load(f)

        return data["metrics"]

    def detect_regressions(self, current_metrics: Dict[str, Any]) -> Tuple[bool, List[Dict[str, Any]]]:
        """
        Detect regressions by comparing current metrics to baseline.

        Args:
            current_metrics: Current evaluation metrics

        Returns:
            Tuple of (has_regressions, list_of_regression_details)
        """
        regressions = []

        # Check overall accuracy
        baseline_acc = self.baseline["overall_accuracy"]
        current_acc = current_metrics["overall_accuracy"]
        acc_change = current_acc - baseline_acc

        if acc_change < -self.ACCURACY_THRESHOLD:
            regressions.append({
                "metric": "overall_accuracy",
                "baseline": baseline_acc,
                "current": current_acc,
                "change": acc_change,
                "threshold": -self.ACCURACY_THRESHOLD,
                "severity": "WARNING",
                "message": f"Overall accuracy dropped from {baseline_acc:.2%} to {current_acc:.2%} ({acc_change:+.2%})"
            })

        # Check intent accuracy
        baseline_intent_acc = self.baseline["intent_accuracy"]
        current_intent_acc = current_metrics["intent_accuracy"]
        intent_acc_change = current_intent_acc - baseline_intent_acc

        if intent_acc_change < -self.ACCURACY_THRESHOLD:
            regressions.append({
                "metric": "intent_accuracy",
                "baseline": baseline_intent_acc,
                "current": current_intent_acc,
                "change": intent_acc_change,
                "threshold": -self.ACCURACY_THRESHOLD,
                "severity": "WARNING",
                "message": f"Intent accuracy dropped from {baseline_intent_acc:.2%} to {current_intent_acc:.2%} ({intent_acc_change:+.2%})"
            })

        # Check action accuracy
        baseline_action_acc = self.baseline["action_accuracy"]
        current_action_acc = current_metrics["action_accuracy"]
        action_acc_change = current_action_acc - baseline_action_acc

        if action_acc_change < -self.ACCURACY_THRESHOLD:
            regressions.append({
                "metric": "action_accuracy",
                "baseline": baseline_action_acc,
                "current": current_action_acc,
                "change": action_acc_change,
                "threshold": -self.ACCURACY_THRESHOLD,
                "severity": "WARNING",
                "message": f"Action accuracy dropped from {baseline_action_acc:.2%} to {current_action_acc:.2%} ({action_acc_change:+.2%})"
            })

        # Check F1 score
        baseline_f1 = self.baseline["macro_avg_f1"]
        current_f1 = current_metrics["macro_avg_f1"]
        f1_change = current_f1 - baseline_f1

        if f1_change < -self.ACCURACY_THRESHOLD:
            regressions.append({
                "metric": "macro_avg_f1",
                "baseline": baseline_f1,
                "current": current_f1,
                "change": f1_change,
                "threshold": -self.ACCURACY_THRESHOLD,
                "severity": "WARNING",
                "message": f"Macro F1 score dropped from {baseline_f1:.3f} to {current_f1:.3f} ({f1_change:+.3f})"
            })

        # Check escalation rate change
        baseline_escalate_pct = self.baseline["action_distribution_pct"].get("ESCALATE", 0)
        current_escalate_pct = current_metrics["action_distribution_pct"].get("ESCALATE", 0)
        escalate_change = current_escalate_pct - baseline_escalate_pct

        if abs(escalate_change) > self.ESCALATION_RATE_THRESHOLD:
            severity = "WARNING" if abs(escalate_change) < 0.10 else "CRITICAL"
            regressions.append({
                "metric": "escalation_rate",
                "baseline": baseline_escalate_pct,
                "current": current_escalate_pct,
                "change": escalate_change,
                "threshold": self.ESCALATION_RATE_THRESHOLD,
                "severity": severity,
                "message": f"Escalation rate changed from {baseline_escalate_pct:.1%} to {current_escalate_pct:.1%} ({escalate_change:+.1%})"
            })

        # Check template usage (target: maintain or increase)
        baseline_template_pct = self.baseline["action_distribution_pct"].get("TEMPLATE", 0)
        current_template_pct = current_metrics["action_distribution_pct"].get("TEMPLATE", 0)
        template_change = current_template_pct - baseline_template_pct

        if template_change < -0.05:  # 5% drop in template usage
            regressions.append({
                "metric": "template_usage",
                "baseline": baseline_template_pct,
                "current": current_template_pct,
                "change": template_change,
                "threshold": -0.05,
                "severity": "INFO",
                "message": f"Template usage dropped from {baseline_template_pct:.1%} to {current_template_pct:.1%} ({template_change:+.1%})"
            })

        # Check safety metrics (CRITICAL - must not regress)
        baseline_forbidden_recall = self.baseline["forbidden_intent_recall"]
        current_forbidden_recall = current_metrics["forbidden_intent_recall"]
        forbidden_change = current_forbidden_recall - baseline_forbidden_recall

        if forbidden_change < -self.SAFETY_THRESHOLD:
            regressions.append({
                "metric": "forbidden_intent_recall",
                "baseline": baseline_forbidden_recall,
                "current": current_forbidden_recall,
                "change": forbidden_change,
                "threshold": -self.SAFETY_THRESHOLD,
                "severity": "CRITICAL",
                "message": f"SAFETY REGRESSION: Forbidden intent recall dropped from {baseline_forbidden_recall:.2%} to {current_forbidden_recall:.2%}"
            })

        baseline_pii_recall = self.baseline["high_risk_pii_recall"]
        current_pii_recall = current_metrics["high_risk_pii_recall"]
        pii_change = current_pii_recall - baseline_pii_recall

        if pii_change < -self.SAFETY_THRESHOLD:
            regressions.append({
                "metric": "high_risk_pii_recall",
                "baseline": baseline_pii_recall,
                "current": current_pii_recall,
                "change": pii_change,
                "threshold": -self.SAFETY_THRESHOLD,
                "severity": "CRITICAL",
                "message": f"SAFETY REGRESSION: High-risk PII recall dropped from {baseline_pii_recall:.2%} to {current_pii_recall:.2%}"
            })

        baseline_violations = self.baseline["safety_violations"]
        current_violations = current_metrics["safety_violations"]

        if current_violations > baseline_violations:
            regressions.append({
                "metric": "safety_violations",
                "baseline": baseline_violations,
                "current": current_violations,
                "change": current_violations - baseline_violations,
                "threshold": 0,
                "severity": "CRITICAL",
                "message": f"SAFETY REGRESSION: Safety violations increased from {baseline_violations} to {current_violations}"
            })

        # Check latency regressions (by action type)
        for action in ["TEMPLATE", "GENERATED", "ESCALATE"]:
            action_lower = action.lower()

            if action_lower in self.baseline.get("latency_by_action", {}):
                baseline_p95 = self.baseline["latency_by_action"][action_lower]["p95"]
                current_p95 = current_metrics["latency_by_action"].get(action_lower, {}).get("p95", 0)

                if current_p95 > 0:
                    latency_increase = (current_p95 - baseline_p95) / baseline_p95

                    if latency_increase > self.LATENCY_THRESHOLD:
                        regressions.append({
                            "metric": f"latency_{action_lower}_p95",
                            "baseline": baseline_p95,
                            "current": current_p95,
                            "change": latency_increase,
                            "threshold": self.LATENCY_THRESHOLD,
                            "severity": "WARNING",
                            "message": f"{action} p95 latency increased from {baseline_p95:.0f}ms to {current_p95:.0f}ms ({latency_increase:+.1%})"
                        })

        has_regressions = len(regressions) > 0
        return has_regressions, regressions

    def format_regression_report(self, regressions: List[Dict[str, Any]]) -> str:
        """Format regression detection report."""
        if not regressions:
            return "✓ No regressions detected - all metrics within acceptable thresholds"

        lines = []
        lines.append("=" * 80)
        lines.append("REGRESSION DETECTION REPORT")
        lines.append("=" * 80)
        lines.append("")

        # Group by severity
        critical = [r for r in regressions if r["severity"] == "CRITICAL"]
        warnings = [r for r in regressions if r["severity"] == "WARNING"]
        info = [r for r in regressions if r["severity"] == "INFO"]

        if critical:
            lines.append("🚨 CRITICAL REGRESSIONS:")
            for r in critical:
                lines.append(f"  ✗ {r['message']}")
            lines.append("")

        if warnings:
            lines.append("⚠️  WARNINGS:")
            for r in warnings:
                lines.append(f"  ! {r['message']}")
            lines.append("")

        if info:
            lines.append("ℹ️  INFORMATIONAL:")
            for r in info:
                lines.append(f"  · {r['message']}")
            lines.append("")

        lines.append("=" * 80)

        summary = f"Found {len(regressions)} regressions: {len(critical)} critical, {len(warnings)} warnings, {len(info)} info"
        lines.append(summary)

        return "\n".join(lines)


def main():
    """Main entry point for regression detection."""
    import argparse

    parser = argparse.ArgumentParser(description="Detect regressions in evaluation metrics")
    parser.add_argument(
        "--baseline",
        default="evaluation/baseline_metrics.json",
        help="Path to baseline metrics file"
    )
    parser.add_argument(
        "--current",
        default="evaluation/latest_evaluation_report.json",
        help="Path to current evaluation results"
    )

    args = parser.parse_args()

    # Load current results
    current_path = Path(args.current)
    if not current_path.exists():
        print(f"Error: Current evaluation results not found at {args.current}")
        print("Run evaluation first: python evaluation/run_evaluation.py")
        sys.exit(1)

    with open(current_path, 'r') as f:
        current_data = json.load(f)
        current_metrics = current_data["metrics"]

    # Detect regressions
    try:
        detector = RegressionDetector(args.baseline)
        has_regressions, regressions = detector.detect_regressions(current_metrics)

        # Print report
        report = detector.format_regression_report(regressions)
        print("\n" + report)

        # Save regression report
        if has_regressions:
            report_path = Path("evaluation/eval_results") / f"regression_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            report_path.parent.mkdir(exist_ok=True)

            with open(report_path, 'w') as f:
                f.write(report)

            print(f"\nRegression report saved to: {report_path}")

        # Exit with appropriate code
        critical_regressions = [r for r in regressions if r["severity"] == "CRITICAL"]
        sys.exit(1 if critical_regressions else 0)

    except FileNotFoundError as e:
        print(f"\nError: {e}")
        print("\nTo establish a baseline, run:")
        print("  python evaluation/run_evaluation.py")
        print("  cp evaluation/latest_evaluation_report.json evaluation/baseline_metrics.json")
        sys.exit(1)


if __name__ == "__main__":
    main()
