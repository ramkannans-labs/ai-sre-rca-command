#!/usr/bin/env python3
"""
Shadow Duel Exercise Runner
Executes Shadow Duel exercises for AI SRE training.
Compares human vs AI investigator performance on identical incidents.
"""

import asyncio
import argparse
import json
import sys
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional
import uuid

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from simulation.shadow_duel import (
    DuelOrchestrator, DuelScenario, ScenarioDifficulty,
    HumanInvestigator, AIInvestigator, ComparisonMetrics, DuelReport
)
from simulation.scenario_engine import (
    ScenarioEngine, ChaosScenario, FailureType, InjectionTarget, Severity
)
from simulation.metrics_collector import (
    MetricsCollector, ExerciseMetrics, ReportGenerator, TimingAnalyzer, AccuracyScorer
)

# Pre-built scenarios
SCENARIOS = {
    "latency-spike": DuelScenario(
        scenario_id="sd-001",
        name="Payment Service Latency Spike",
        description="Payment service p99 latency increased from 200ms to 2.5s after deployment",
        difficulty=ScenarioDifficulty.BEGINNER,
        time_limit_minutes=20,
        incident_brief="""
ALERT: payment-service p99 latency > 2s (threshold: 500ms)
START: 2024-01-15T10:30:00Z
SYMPTOMS:
- Payment API p99 latency: 2.5s (baseline: 200ms)
- Error rate: 2% (baseline: 0.1%)
- Throughput: Normal
- Affected endpoints: /api/v1/payments, /api/v1/refunds
RECENT CHANGES:
- payment-service v2.3.1 deployed 25 min ago (feature: new reporting query)
- No database schema changes
- No infrastructure changes
ARCHITECTURE: payment-service (Java Spring Boot) -> PostgreSQL (RDS) -> Redis cache
""",
        ground_truth_root_cause="Database connection pool exhaustion in payment-service v2.3.1 due to missing connection cleanup in new reporting query code path",
        ground_truth_contributing_factors=[
            "High request volume",
            "Missing connection pooling config",
            "Insufficient pre-deployment load testing"
        ],
        key_evidence_sources=["metrics", "logs", "traces", "deployments"],
        learning_objectives=[
            "Practice golden signals investigation",
            "Correlation of deployment timing with symptom onset",
            "Connection pool exhaustion pattern recognition",
            "Runbook consultation for standard mitigation"
        ],
        expected_hypotheses=[
            "Database connection pool exhaustion",
            "Slow database queries from new deployment",
            "Database instance CPU saturation",
            "Network latency between service and DB"
        ]
    ),
    "pod-crash-cascade": DuelScenario(
        scenario_id="sd-002",
        name="Order Service Pod Crash Cascade",
        description="Order service pods crashing causing downstream payment service failures",
        difficulty=ScenarioDifficulty.INTERMEDIATE,
        time_limit_minutes=30,
        incident_brief="""
ALERT: order-service pods crashing, 50% replica loss in 5 min
START: 2024-01-15T14:22:00Z
SYMPTOMS:
- order-service: 3/6 pods Running, 3 CrashLoopBackOff
- Restart count: 12+ per affected pod
- Downstream: payment-service error rate 15% (calls to order-service failing)
- Upstream: api-gateway 5xx errors 8%
RECENT CHANGES:
- order-service v1.4.0 deployed 40 min ago (memory optimization)
- Kafka cluster upgraded to 3.6.0 2 hours ago
- New feature flag "async-processing" enabled 35 min ago
ARCHITECTURE: api-gateway -> order-service (Kafka consumer) -> payment-service, inventory-service
- order-service consumes from Kafka topic "orders"
- Produces to "payment-requests", "inventory-reservations"
""",
        ground_truth_root_cause="order-service v1.4.0 introduced OOM in async processing path when feature flag enabled; Kafka rebalance storms amplify crashes",
        ground_truth_contributing_factors=[
            "Memory optimization removed critical cleanup",
            "Feature flag enabled without canary",
            "Kafka consumer group rebalance behavior under crashes"
        ],
        key_evidence_sources=["metrics", "logs", "traces", "deployments", "kb"],
        learning_objectives=[
            "Multi-service blast radius analysis",
            "Kafka consumer group rebalance behavior under crashes",
            "Feature flag rollout risk assessment",
            "Distinguishing cascade cause vs effect"
        ],
        expected_hypotheses=[
            "OOM in new async processing code path",
            "Kafka upgrade incompatibility",
            "Feature flag causing memory leak",
            "Downstream dependency failure cascading up"
        ]
    ),
    "cpu-exhaustion": DuelScenario(
        scenario_id="sd-003",
        name="Recommendation Engine CPU Exhaustion",
        description="Recommendation service CPU at 95%+ after ML model update and code deployment",
        difficulty=ScenarioDifficulty.INTERMEDIATE,
        time_limit_minutes=25,
        incident_brief="""
ALERT: recommendation-service CPU > 95% sustained, latency degraded
START: 2024-01-15T09:15:00Z
SYMPTOMS:
- recommendation-service: CPU 98% (all cores), p99 latency 5s (baseline: 100ms)
- Error rate: 0% (requests eventually complete)
- HPA: scaling but new pods also hit 95% CPU
- No increase in request volume
RECENT CHANGES:
- recommendation-service v3.2.0 deployed 3 hours ago (algorithm update)
- ML model artifact updated 4 hours ago (v4.1 -> v4.2)
- Traffic shadowing enabled for v3.2.0 3 hours ago
ARCHITECTURE: api-gateway -> recommendation-service (Python Flask + ML inference) -> feature-store (Redis) -> model-registry (S3)
""",
        ground_truth_root_cause="Model v4.2 increased inference complexity 10x (new attention layers); v3.2.0 removed batching optimization that previously masked this",
        ground_truth_contributing_factors=[
            "ML model architecture change increased compute",
            "Code deployment removed batching optimization",
            "No performance testing for model+code combination"
        ],
        key_evidence_sources=["metrics", "logs", "deployments", "profiling"],
        learning_objectives=[
            "CPU profiling in production",
            "ML model performance regression detection",
            "Distinguishing code vs model vs config changes",
            "Capacity planning vs performance bug"
        ],
        expected_hypotheses=[
            "ML model v4.2 inference complexity regression",
            "Code v3.2.0 removed performance optimization",
            "Feature store (Redis) latency increase",
            "Traffic pattern change causing cache misses"
        ]
    ),
    "network-partition": DuelScenario(
        scenario_id="sd-004",
        name="Cross-AZ Network Partition",
        description="Intermittent 5xx errors for services in us-east-1a, cross-AZ calls failing",
        difficulty=ScenarioDifficulty.ADVANCED,
        time_limit_minutes=35,
        incident_brief="""
ALERT: Multiple services degraded in us-east-1a, intermittent 5xx
START: 2024-01-15T16:45:00Z
SYMPTOMS:
- user-service (us-east-1a): 50% requests timeout
- payment-service (us-east-1a): 30% requests timeout
- inventory-service (us-east-1b): Normal
- Cross-service calls between AZs: 40% failure
- Within same AZ: Normal
RECENT CHANGES:
- AWS VPC CNI plugin upgraded 6 hours ago
- New NetworkPolicy applied to user-service namespace 4 hours ago
- EKS cluster control plane upgraded to 1.28 12 hours ago
ARCHITECTURE: 3-AZ EKS cluster, services distributed across AZs, ALB cross-zone load balancing enabled
- user-service: 2 pods in 1a, 2 in 1b, 2 in 1c
- payment-service: 3 pods in 1a, 3 in 1b
- inventory-service: 2 pods in 1b, 2 in 1c
""",
        ground_truth_root_cause="NetworkPolicy on user-service namespace blocked inter-AZ traffic; CNI upgrade changed default allow behavior; only user-service affected directly but payment-service calls user-service cross-AZ",
        ground_truth_contributing_factors=[
            "NetworkPolicy too restrictive (ingress only from same namespace)",
            "CNI upgrade changed default behavior",
            "Cross-AZ dependency not documented",
            "No network policy testing in staging"
        ],
        key_evidence_sources=["metrics", "logs", "kb", "architecture", "deployments"],
        learning_objectives=[
            "Network-level failure diagnosis",
            "Cross-AZ dependency mapping",
            "Kubernetes networking (CNI, NetworkPolicy, Service topology)",
            "Partial failure vs complete outage reasoning"
        ],
        expected_hypotheses=[
            "NetworkPolicy blocking cross-AZ traffic",
            "CNI upgrade breaking connectivity",
            "AZ-specific infrastructure failure",
            "Service mesh misconfiguration"
        ]
    ),
    "black-friday-multi": DuelScenario(
        scenario_id="sd-005",
        name="Black Friday Composite Failure",
        description="Multiple simultaneous failures during Black Friday traffic surge",
        difficulty=ScenarioDifficulty.ADVANCED,
        time_limit_minutes=45,
        incident_brief="""
ALERT: SEV-1 - Checkout flow failing, revenue impact critical
START: 2024-11-29T08:00:00Z (Black Friday)
SYMPTOMS:
- Checkout conversion rate dropped 60% in 10 min
- api-gateway: 25% 5xx errors
- payment-service: p99 latency 8s, error rate 12%
- inventory-service: p99 latency 3s, error rate 5%
- notification-service: 100% queue backlog (50k messages)
- Database (RDS): CPU 95%, connections 900/1000
RECENT CHANGES:
- Black Friday feature flags enabled 07:00 (flash-sales, bundle-offers, guest-checkout)
- payment-service v4.0.0 deployed 06:30 (new fraud detection)
- inventory-service v2.1.0 deployed 06:45 (reservation timeout reduction)
- DB parameter group changed 05:00 (max_connections 1000->500 by mistake)
- Traffic: 5x normal volume since 07:00
ARCHITECTURE: Full microservices (15+ services), event-driven via Kafka, PostgreSQL RDS, Redis ElastiCache
- Checkout flow: api-gateway -> cart -> inventory -> payment -> notification -> order
- Flash sales create burst traffic patterns
""",
        ground_truth_root_cause="Multiple root causes: (1) DB max_connections reduced to 500 (config error) - primary bottleneck, (2) payment-service v4.0.0 fraud detection adds 2s synchronous external API call, (3) inventory-service v2.1.0 reduced reservation TTL causing retry storms, (4) Flash sales traffic 5x exceeds capacity even without bugs",
        ground_truth_contributing_factors=[
            "DB config error reduced capacity",
            "Fraud detection adds synchronous latency",
            "Inventory timeout reduction causes retry amplification",
            "Traffic surge exceeds baseline capacity",
            "Multiple changes deployed simultaneously",
            "No pre-Black Friday load test with all changes"
        ],
        key_evidence_sources=["metrics", "logs", "traces", "deployments", "kb", "architecture", "config"],
        learning_objectives=[
            "Multi-root-cause analysis under time pressure",
            "Prioritization when multiple failures compound",
            "Distinguishing trigger vs amplifier vs independent failures",
            "Executive communication during active incident",
            "Rollback vs fix-forward decision making"
        ],
        expected_hypotheses=[
            "DB connection limit exhausted (config change)",
            "Payment service fraud API latency",
            "Inventory reservation retry storm",
            "Traffic surge overwhelming capacity",
            "Notification queue backlog blocking checkout",
            "Kafka consumer lag from traffic burst"
        ]
    )
}


class ShadowDuelRunner:
    """Main runner for Shadow Duel exercises."""

    def __init__(self, output_dir: str = "./shadow_duel_results"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.orchestrator = DuelOrchestrator()
        self.metrics_collector = MetricsCollector()
        self.report_generator = ReportGenerator()

    def list_scenarios(self):
        """List available scenarios."""
        print("\nAvailable Shadow Duel Scenarios:")
        print("=" * 80)
        for key, scenario in SCENARIOS.items():
            print(f"\n  {key} ({scenario.scenario_id})")
            print(f"    Name: {scenario.name}")
            print(f"    Difficulty: {scenario.difficulty.value}")
            print(f"    Time Limit: {scenario.time_limit_minutes} minutes")
            print(f"    Description: {scenario.description}")
            print(f"    Learning Objectives: {', '.join(scenario.learning_objectives[:3])}...")

    async def run_duel(
        self,
        scenario_key: str,
        human_name: str = "Human Investigator",
        human_role: str = "SRE",
        human_experience_years: int = 3,
        ai_model: str = "claude-sonnet-5.5",
        time_limit_override: Optional[int] = None,
        simulate_human: bool = False
    ) -> DuelReport:
        """Run a complete Shadow Duel exercise."""

        if scenario_key not in SCENARIOS:
            raise ValueError(f"Unknown scenario: {scenario_key}. Available: {list(SCENARIOS.keys())}")

        scenario = SCENARIOS[scenario_key]

        if time_limit_override:
            scenario.time_limit_minutes = time_limit_override

        print(f"\n{'='*80}")
        print(f"SHADOW DUEL EXERCISE: {scenario.name}")
        print(f"Scenario ID: {scenario.scenario_id}")
        print(f"Difficulty: {scenario.difficulty.value}")
        print(f"Time Limit: {scenario.time_limit_minutes} minutes")
        print(f"{'='*80}\n")

        print("Incident Briefing:")
        print("-" * 80)
        print(scenario.incident_brief)
        print("-" * 80)

        # Create investigators
        human = HumanInvestigator(
            investigator_id=f"human-{uuid.uuid4().hex[:8]}",
            name=human_name,
            role=human_role,
            experience_years=human_experience_years
        )

        ai = AIInvestigator(
            investigator_id=f"ai-{uuid.uuid4().hex[:8]}",
            name=f"AI Investigator ({ai_model})",
            model_version=ai_model
        )

        print(f"\nInvestigators:")
        print(f"  Human: {human.name} ({human.role}, {human.experience_years} yrs exp)")
        print(f"  AI: {ai.name}")

        if simulate_human:
            print("\n[SIMULATION MODE] Simulating human investigation...")
            # In simulation mode, we'd run a mock human investigation
            # For now, just run AI
            print("  Note: Human simulation not fully implemented. Running AI only.")

        # Run the duel
        print(f"\nStarting Shadow Duel...")
        print(f"Time limit: {scenario.time_limit_minutes} minutes")
        print("-" * 80)

        try:
            report = await self.orchestrator.run_duel(
                scenario=scenario,
                human_investigator=human,
                ai_investigator=ai,
                time_limit_minutes=scenario.time_limit_minutes
            )

            # Save results
            self._save_results(report, scenario_key)

            # Print summary
            self._print_summary(report)

            return report

        except Exception as e:
            print(f"\nError during duel: {e}")
            raise

    def _save_results(self, report: DuelReport, scenario_key: str):
        """Save duel results to files."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_name = f"{scenario_key}_{timestamp}"

        # Save full report as JSON
        report_file = self.output_dir / f"{base_name}_report.json"
        with open(report_file, 'w') as f:
            json.dump(report.to_dict(), f, indent=2, default=str)
        print(f"\nFull report saved to: {report_file}")

        # Save human-readable summary
        summary_file = self.output_dir / f"{base_name}_summary.md"
        with open(summary_file, 'w') as f:
            f.write(self._generate_markdown_summary(report))
        print(f"Summary saved to: {summary_file}")

        # Save comparison metrics as CSV for analysis
        metrics_file = self.output_dir / f"{base_name}_metrics.csv"
        self._save_metrics_csv(report, metrics_file)
        print(f"Metrics CSV saved to: {metrics_file}")

    def _generate_markdown_summary(self, report: DuelReport) -> str:
        """Generate markdown summary of duel results."""
        lines = [
            f"# Shadow Duel Report: {report.scenario_name}",
            f"**Exercise ID:** {report.exercise_id}",
            f"**Date:** {report.timestamp.strftime('%Y-%m-%d %H:%M:%S')}",
            f"**Duration:** {report.duration_minutes:.1f} minutes",
            "",
            "## Participants",
            f"- **Human:** {report.human_investigator.name} ({report.human_investigator.role}, {report.human_investigator.experience_years} yrs)",
            f"- **AI:** {report.ai_investigator.name} ({report.ai_investigator.model_version})",
            "",
            "## Ground Truth",
            f"- **Root Cause:** {report.ground_truth_root_cause}",
            f"- **Contributing Factors:** {', '.join(report.ground_truth_contributing_factors)}",
            "",
            "## Results Summary",
            "| Metric | Human | AI | Winner |",
            "|--------|-------|-----|--------|",
        ]

        m = report.comparison

        def winner(h, a, lower_better=False):
            if h is None or a is None:
                return "N/A"
            if lower_better:
                return "Human" if h < a else "AI" if a < h else "Tie"
            return "Human" if h > a else "AI" if a > h else "Tie"

        lines.extend([
            f"| Time to First Hypothesis | {m.human_time_to_first_hypothesis_min:.1f} min | {m.ai_time_to_first_hypothesis_min:.1f} min | {winner(m.human_time_to_first_hypothesis_min, m.ai_time_to_first_hypothesis_min, True)} |",
            f"| Time to Root Cause | {m.human_time_to_root_cause_min:.1f} min | {m.ai_time_to_root_cause_min:.1f} min | {winner(m.human_time_to_root_cause_min, m.ai_time_to_root_cause_min, True)} |",
            f"| Hypotheses Formed | {m.human_hypothesis_count} | {m.ai_hypothesis_count} | {winner(m.human_hypothesis_count, m.ai_hypothesis_count)} |",
            f"| Hypothesis Diversity | {m.human_hypothesis_diversity} | {m.ai_hypothesis_diversity} | {winner(m.human_hypothesis_diversity, m.ai_hypothesis_diversity)} |",
            f"| Evidence Sources Used | {m.human_evidence_sources_used}/7 | {m.ai_evidence_sources_used}/7 | {winner(m.human_evidence_sources_used, m.ai_evidence_sources_used)} |",
            f"| Calibration Error | {m.human_calibration_error:.3f} | {m.ai_calibration_error:.3f} | {winner(m.human_calibration_error, m.ai_calibration_error, True)} |",
            f"| Contradicting Evidence Acknowledged | {m.human_contradicting_evidence_acknowledged} | {m.ai_contradicting_evidence_acknowledged} | {winner(m.human_contradicting_evidence_acknowledged, m.ai_contradicting_evidence_acknowledged)} |",
            f"| Process Steps Documented | {m.human_process_steps_documented} | {m.ai_process_steps_documented} | {winner(m.human_process_steps_documented, m.ai_process_steps_documented)} |",
            f"| Root Cause Accuracy | {m.human_root_cause_accuracy:.2f} | {m.ai_root_cause_accuracy:.2f} | {winner(m.human_root_cause_accuracy, m.ai_root_cause_accuracy)} |",
            "",
            "## Qualitative Assessment",
            "",
            "### Process Quality (1-5)",
            "| Dimension | Human | AI |",
            "|-----------|-------|-----|",
            f"| Structure | {m.human_process_structure_score}/5 | {m.ai_process_structure_score}/5 |",
            f"| Documentation | {m.human_documentation_score}/5 | {m.ai_documentation_score}/5 |",
            f"| Falsification | {m.human_falsification_score}/5 | {m.ai_falsification_score}/5 |",
            f"| Collaboration | {m.human_collaboration_score}/5 | {m.ai_collaboration_score}/5 |",
            f"| Adaptability | {m.human_adaptability_score}/5 | {m.ai_adaptability_score}/5 |",
            "",
            "## Key Insights",
        ])

        for i, insight in enumerate(report.key_insights, 1):
            lines.append(f"{i}. {insight}")

        lines.extend([
            "",
            "## Lessons Learned",
            "",
            "### For Human Investigators:",
        ])
        for lesson in report.lessons_learned_human:
            lines.append(f"- {lesson}")

        lines.extend([
            "",
            "### For AI RCA Development:",
        ])
        for lesson in report.lessons_learned_ai:
            lines.append(f"- {lesson}")

        lines.extend([
            "",
            "## Recommendations",
        ])
        for rec in report.recommendations:
            lines.append(f"- {rec}")

        return "\n".join(lines)

    def _save_metrics_csv(self, report: DuelReport, filepath: Path):
        """Save metrics as CSV for longitudinal analysis."""
        import csv

        m = report.comparison
        row = {
            "exercise_id": report.exercise_id,
            "scenario": report.scenario_name,
            "date": report.timestamp.isoformat(),
            "duration_min": report.duration_minutes,
            "human_name": report.human_investigator.name,
            "human_role": report.human_investigator.role,
            "human_experience": report.human_investigator.experience_years,
            "ai_model": report.ai_investigator.model_version,
            "ground_truth_root_cause": report.ground_truth_root_cause,
            # Quantitative metrics
            "human_time_first_hyp_min": m.human_time_to_first_hypothesis_min,
            "ai_time_first_hyp_min": m.ai_time_to_first_hypothesis_min,
            "human_time_root_cause_min": m.human_time_to_root_cause_min,
            "ai_time_root_cause_min": m.ai_time_to_root_cause_min,
            "human_hypothesis_count": m.human_hypothesis_count,
            "ai_hypothesis_count": m.ai_hypothesis_count,
            "human_hypothesis_diversity": m.human_hypothesis_diversity,
            "ai_hypothesis_diversity": m.ai_hypothesis_diversity,
            "human_evidence_sources": m.human_evidence_sources_used,
            "ai_evidence_sources": m.ai_evidence_sources_used,
            "human_calibration_error": m.human_calibration_error,
            "ai_calibration_error": m.ai_calibration_error,
            "human_contradicting_evidence": m.human_contradicting_evidence_acknowledged,
            "ai_contradicting_evidence": m.ai_contradicting_evidence_acknowledged,
            "human_process_steps": m.human_process_steps_documented,
            "ai_process_steps": m.ai_process_steps_documented,
            "human_root_cause_accuracy": m.human_root_cause_accuracy,
            "ai_root_cause_accuracy": m.ai_root_cause_accuracy,
            # Qualitative scores
            "human_structure_score": m.human_process_structure_score,
            "ai_structure_score": m.ai_process_structure_score,
            "human_doc_score": m.human_documentation_score,
            "ai_doc_score": m.ai_documentation_score,
            "human_falsification_score": m.human_falsification_score,
            "ai_falsification_score": m.ai_falsification_score,
            "human_collab_score": m.human_collaboration_score,
            "ai_collab_score": m.ai_collaboration_score,
            "human_adapt_score": m.human_adaptability_score,
            "ai_adapt_score": m.ai_adaptability_score,
        }

        # Write header if file doesn't exist
        file_exists = filepath.exists()
        with open(filepath, 'a', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=row.keys())
            if not file_exists:
                writer.writeheader()
            writer.writerow(row)

    def _print_summary(self, report: DuelReport):
        """Print summary to console."""
        m = report.comparison

        print(f"\n{'='*80}")
        print(f"SHADOW DUEL COMPLETE: {report.scenario_name}")
        print(f"{'='*80}")
        print(f"Duration: {report.duration_minutes:.1f} minutes")
        print()

        print("QUANTITATIVE RESULTS:")
        print("-" * 80)
        print(f"  Time to First Hypothesis:  Human: {m.human_time_to_first_hypothesis_min:.1f} min  |  AI: {m.ai_time_to_first_hypothesis_min:.1f} min")
        print(f"  Time to Root Cause:        Human: {m.human_time_to_root_cause_min:.1f} min  |  AI: {m.ai_time_to_root_cause_min:.1f} min")
        print(f"  Hypotheses Formed:         Human: {m.human_hypothesis_count}  |  AI: {m.ai_hypothesis_count}")
        print(f"  Hypothesis Diversity:      Human: {m.human_hypothesis_diversity}  |  AI: {m.ai_hypothesis_diversity}")
        print(f"  Evidence Sources (of 7):   Human: {m.human_evidence_sources_used}  |  AI: {m.ai_evidence_sources_used}")
        print(f"  Calibration Error:         Human: {m.human_calibration_error:.3f}  |  AI: {m.ai_calibration_error:.3f}")
        print(f"  Contradicting Evidence:    Human: {m.human_contradicting_evidence_acknowledged}  |  AI: {m.ai_contradicting_evidence_acknowledged}")
        print(f"  Root Cause Accuracy:       Human: {m.human_root_cause_accuracy:.2f}  |  AI: {m.ai_root_cause_accuracy:.2f}")
        print()

        print("QUALITATIVE SCORES (1-5):")
        print("-" * 80)
        print(f"  Structure:        Human: {m.human_process_structure_score}  |  AI: {m.ai_process_structure_score}")
        print(f"  Documentation:    Human: {m.human_documentation_score}  |  AI: {m.ai_documentation_score}")
        print(f"  Falsification:    Human: {m.human_falsification_score}  |  AI: {m.ai_falsification_score}")
        print(f"  Collaboration:    Human: {m.human_collaboration_score}  |  AI: {m.ai_collaboration_score}")
        print(f"  Adaptability:     Human: {m.human_adaptability_score}  |  AI: {m.ai_adaptability_score}")
        print()

        print("KEY INSIGHTS:")
        for i, insight in enumerate(report.key_insights, 1):
            print(f"  {i}. {insight}")
        print()

        print(f"Full results saved to: {self.output_dir}")


async def main():
    parser = argparse.ArgumentParser(description="Run Shadow Duel exercise")
    parser.add_argument(
        "scenario",
        nargs="?",
        choices=list(SCENARIOS.keys()) + ["list"],
        help="Scenario to run (or 'list' to show available)"
    )
    parser.add_argument(
        "--human-name",
        default="Human Investigator",
        help="Human investigator name"
    )
    parser.add_argument(
        "--human-role",
        default="SRE",
        help="Human investigator role"
    )
    parser.add_argument(
        "--human-experience",
        type=int,
        default=3,
        help="Human investigator years of experience"
    )
    parser.add_argument(
        "--ai-model",
        default="claude-sonnet-5.5",
        help="AI model version"
    )
    parser.add_argument(
        "--time-limit",
        type=int,
        help="Override time limit in minutes"
    )
    parser.add_argument(
        "--simulate-human",
        action="store_true",
        help="Simulate human investigation (for testing)"
    )
    parser.add_argument(
        "--output-dir",
        default="./shadow_duel_results",
        help="Output directory for results"
    )

    args = parser.parse_args()

    runner = ShadowDuelRunner(output_dir=args.output_dir)

    if not args.scenario or args.scenario == "list":
        runner.list_scenarios()
        return

    await runner.run_duel(
        scenario_key=args.scenario,
        human_name=args.human_name,
        human_role=args.human_role,
        human_experience_years=args.human_experience,
        ai_model=args.ai_model,
        time_limit_override=args.time_limit,
        simulate_human=args.simulate_human
    )


if __name__ == "__main__":
    asyncio.run(main())