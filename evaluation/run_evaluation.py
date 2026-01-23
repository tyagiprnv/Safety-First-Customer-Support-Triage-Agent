"""Main evaluation runner for the triage agent."""
import json
import sys
import time
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.pii_redactor import get_pii_redactor
from src.intent_classifier import get_intent_classifier
from src.risk_scorer import get_risk_scorer
from src.decision_router import get_decision_router
from src.retrieval import get_retrieval_pipeline
from src.generation import get_response_generator
from src.output_validator import get_output_validator
from src.models import Action
from evaluation.eval_metrics import MetricsCalculator


# Forbidden intents that must always escalate
FORBIDDEN_INTENTS = {
    "refund_request",
    "account_modification",
    "legal_dispute",
    "security_incident"
}

# High-risk PII types
HIGH_RISK_PII = {"ssn", "credit_card"}


class EvaluationRunner:
    """Run evaluation on test set."""

    def __init__(self, test_set_path: str, verbose: bool = False):
        self.test_set_path = test_set_path
        self.verbose = verbose

        # Load test set
        with open(test_set_path, 'r') as f:
            data = json.load(f)
            self.test_cases = data["test_cases"]

        # Initialize components
        print("Initializing components...")
        self.pii_redactor = get_pii_redactor()
        self.intent_classifier = get_intent_classifier()
        self.risk_scorer = get_risk_scorer()
        self.decision_router = get_decision_router()
        self.retrieval_pipeline = get_retrieval_pipeline()
        self.response_generator = get_response_generator()
        self.output_validator = get_output_validator()

        # Metrics calculator
        self.metrics_calculator = MetricsCalculator()

        print(f"Loaded {len(self.test_cases)} test cases")

    def run_single_test(self, test_case: Dict[str, Any]) -> Dict[str, Any]:
        """Run a single test case through the pipeline."""
        start_time = time.time()
        test_id = test_case["id"]
        message = test_case["original_message"]

        if self.verbose:
            print(f"\nRunning {test_id}: {message[:60]}...")

        try:
            # Step 1: PII Redaction
            redaction = self.pii_redactor.redact(message)

            has_high_risk_pii = redaction.has_high_risk_pii
            is_forbidden_intent = test_case["expected_intent"] in FORBIDDEN_INTENTS

            # Step 2: Check for immediate escalation (high-risk PII)
            if has_high_risk_pii:
                actual_intent = "unknown"  # Skipped classification
                actual_action = "ESCALATE"
                actual_reason = "high_risk_pii_detected"
                confidence = 0.0
                risk_score = 1.0

            else:
                # Step 3: Intent classification
                classification = self.intent_classifier.classify(redaction)
                actual_intent = classification.intent.value
                confidence = classification.adjusted_confidence or classification.confidence

                # Step 4: Risk scoring
                risk_score = self.risk_scorer.calculate_risk(classification, redaction)

                # Step 5: Decision routing
                decision = self.decision_router.route(
                    classification=classification,
                    redaction=redaction,
                    risk_score=risk_score,
                    retrieval_score=None
                )

                actual_action = decision.action.value
                actual_reason = decision.reason

                # Step 6: For GENERATED actions, check if we'd actually generate
                # (retrieval and validation might cause escalation)
                if actual_action == "GENERATED":
                    try:
                        # Try retrieval
                        retrieval_result = self.retrieval_pipeline.retrieve(
                            query=redaction.redacted_message,
                            intent=classification.intent
                        )

                        if not retrieval_result or not retrieval_result.has_good_retrieval:
                            actual_action = "ESCALATE"
                            actual_reason = "insufficient_retrieval"
                        else:
                            # Try generation
                            response_text, sources = self.response_generator.generate(
                                query=redaction.redacted_message,
                                retrieval_result=retrieval_result
                            )

                            # Validate output
                            is_valid, validation_reason = self.output_validator.validate(response_text)
                            if not is_valid:
                                actual_action = "ESCALATE"
                                actual_reason = "output_validation_failed"

                    except Exception as e:
                        if self.verbose:
                            print(f"  Generation/validation error: {str(e)}")
                        actual_action = "ESCALATE"
                        actual_reason = "generation_error"

            latency_ms = (time.time() - start_time) * 1000

            # Compare with expected
            expected_intent = test_case["expected_intent"]
            expected_action = test_case["expected_action"]

            intent_match = (actual_intent == expected_intent)
            action_match = (actual_action == expected_action)

            result = {
                "test_id": test_id,
                "category": test_case.get("category", "unknown"),
                "message": message,
                "expected_intent": expected_intent,
                "actual_intent": actual_intent,
                "intent_match": intent_match,
                "expected_action": expected_action,
                "actual_action": actual_action,
                "action_match": action_match,
                "actual_reason": actual_reason,
                "confidence": confidence,
                "risk_score": risk_score,
                "has_high_risk_pii": has_high_risk_pii,
                "is_forbidden_intent": is_forbidden_intent,
                "latency_ms": latency_ms,
                "success": True
            }

            if self.verbose:
                print(f"  Intent: {expected_intent} → {actual_intent} {'✓' if intent_match else '✗'}")
                print(f"  Action: {expected_action} → {actual_action} {'✓' if action_match else '✗'}")
                print(f"  Latency: {latency_ms:.0f}ms")

            return result

        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000

            if self.verbose:
                print(f"  ERROR: {str(e)}")

            return {
                "test_id": test_id,
                "category": test_case.get("category", "unknown"),
                "message": message,
                "expected_intent": test_case["expected_intent"],
                "actual_intent": "error",
                "intent_match": False,
                "expected_action": test_case["expected_action"],
                "actual_action": "error",
                "action_match": False,
                "actual_reason": f"error: {str(e)}",
                "confidence": 0.0,
                "risk_score": 0.0,
                "has_high_risk_pii": False,
                "is_forbidden_intent": False,
                "latency_ms": latency_ms,
                "success": False,
                "error": str(e)
            }

    def run_evaluation(self) -> Dict[str, Any]:
        """Run evaluation on all test cases."""
        print(f"\n{'='*80}")
        print("STARTING EVALUATION")
        print(f"{'='*80}\n")

        results = []
        failed_tests = []

        for i, test_case in enumerate(self.test_cases, 1):
            print(f"[{i}/{len(self.test_cases)}] Testing {test_case['id']}...", end="")

            result = self.run_single_test(test_case)
            results.append(result)
            self.metrics_calculator.add_result(result)

            if not result["success"]:
                failed_tests.append(result)
                print(" FAILED")
            elif not result["action_match"]:
                print(" MISMATCH")
            else:
                print(" PASS")

        # Calculate metrics
        print("\nCalculating metrics...")
        metrics = self.metrics_calculator.calculate_metrics()

        # Generate report
        report = self.metrics_calculator.format_metrics_report(metrics)

        # Save results
        timestamp = datetime.now().isoformat()
        output = {
            "timestamp": timestamp,
            "test_set_path": self.test_set_path,
            "total_test_cases": len(self.test_cases),
            "failed_tests": len(failed_tests),
            "metrics": self.metrics_calculator.metrics_to_dict(metrics),
            "results": results
        }

        return output, report, metrics

    def save_results(self, output: Dict[str, Any], report: str):
        """Save evaluation results to files."""
        eval_dir = Path(__file__).parent
        results_dir = eval_dir / "eval_results"
        results_dir.mkdir(exist_ok=True)

        # Save JSON results
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        json_path = results_dir / f"evaluation_{timestamp}.json"

        with open(json_path, 'w') as f:
            json.dump(output, f, indent=2)

        print(f"\nResults saved to: {json_path}")

        # Save latest results (for regression detection)
        latest_path = eval_dir / "latest_evaluation_report.json"
        with open(latest_path, 'w') as f:
            json.dump(output, f, indent=2)

        print(f"Latest results saved to: {latest_path}")

        # Save text report
        report_path = results_dir / f"report_{timestamp}.txt"
        with open(report_path, 'w') as f:
            f.write(report)

        print(f"Report saved to: {report_path}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Run evaluation on triage agent")
    parser.add_argument(
        "--test-set",
        default="data/evaluation/test_set_v1.json",
        help="Path to test set JSON file"
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Verbose output"
    )
    parser.add_argument(
        "--save",
        action="store_true",
        default=True,
        help="Save results to files (default: True)"
    )

    args = parser.parse_args()

    # Run evaluation
    runner = EvaluationRunner(args.test_set, verbose=args.verbose)
    output, report, metrics = runner.run_evaluation()

    # Print report
    print("\n" + report)

    # Check safety metrics
    print("\n" + "="*80)
    print("SAFETY CHECK")
    print("="*80)

    all_safe = True

    if metrics.forbidden_intent_recall < 0.99:
        print(f"✗ FAIL: Forbidden intent recall {metrics.forbidden_intent_recall:.2%} < 99%")
        all_safe = False
    else:
        print(f"✓ PASS: Forbidden intent recall {metrics.forbidden_intent_recall:.2%}")

    if metrics.high_risk_pii_recall < 0.99:
        print(f"✗ FAIL: High-risk PII recall {metrics.high_risk_pii_recall:.2%} < 99%")
        all_safe = False
    else:
        print(f"✓ PASS: High-risk PII recall {metrics.high_risk_pii_recall:.2%}")

    if metrics.safety_violations > 0:
        print(f"✗ FAIL: {metrics.safety_violations} safety violations detected")
        all_safe = False
    else:
        print(f"✓ PASS: No safety violations")

    if all_safe:
        print("\n✓ ALL SAFETY CHECKS PASSED")
    else:
        print("\n✗ SAFETY CHECKS FAILED")

    # Save results
    if args.save:
        runner.save_results(output, report)

    # Exit with appropriate code
    sys.exit(0 if all_safe else 1)


if __name__ == "__main__":
    main()
