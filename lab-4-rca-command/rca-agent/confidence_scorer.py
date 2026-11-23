"""
Confidence Scorer - Weights Evidence to Rank Hypotheses

This module computes confidence scores for root cause hypotheses by:
1. Weighting different evidence types (metrics, logs, traces, topology, history)
2. Applying evidence quality factors (freshness, coverage, consistency)
3. Combining with pattern match strength and historical similarity
4. Normalizing to 0-1 scale with calibrated thresholds

Architecture:
┌─────────────────────────────────────────────────────────────────────┐
│                    CONFIDENCE SCORER                                │
├─────────────────────────────────────────────────────────────────────┤
│  score(hypothesis, evidence, context)                               │
│    ├─▶ Evidence Type Weights                                        │
│    │   ├─ Metrics (anomalous): 0.30                                │
│    │   ├─ Logs (error/critical): 0.25                              │
│    │   ├─ Traces (error/timeout): 0.15                             │
│    │   ├─ Topology (cascade match): 0.15                           │
│    │   └─ Historical (similar incidents): 0.15                     │
│    ├─▶ Quality Factors                                              │
│    │   ├─ Freshness: Recent evidence weighted higher               │
│    │   ├─ Coverage: How many services/components covered           │
│    │   ├─ Consistency: Evidence agrees vs conflicts                │
│    │   └─ Specificity: Specific vs generic evidence                │
│    ├─▶ Pattern Match Bonus                                          │
│    │   ├─ Catalog match strength                                   │
│    │   └─ Threshold exceedance degree                              │
│    └─▶ Calibration: Map raw score → calibrated confidence          │
└─────────────────────────────────────────────────────────────────────┘
"""

import math
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from enum import Enum

from hypothesis_engine import Hypothesis, HypothesisCategory
from evidence_collector import CollectedEvidence, MetricsEvidence, LogEvidence, TraceEvidence

logger = logging.getLogger(__name__)


class EvidenceType(str, Enum):
    METRICS = "metrics"
    LOGS = "logs"
    TRACES = "traces"
    TOPOLOGY = "topology"
    HISTORICAL = "historical"
    LLM = "llm"


# Default evidence type weights (sum = 1.0)
DEFAULT_EVIDENCE_WEIGHTS = {
    EvidenceType.METRICS: 0.30,
    EvidenceType.LOGS: 0.25,
    EvidenceType.TRACES: 0.15,
    EvidenceType.TOPOLOGY: 0.15,
    EvidenceType.HISTORICAL: 0.15,
    EvidenceType.LLM: 0.05,  # Lower weight for LLM-generated
}


# Category-specific weight adjustments
CATEGORY_WEIGHT_ADJUSTMENTS = {
    HypothesisCategory.RESOURCE_EXHAUSTION: {
        EvidenceType.METRICS: 0.10,      # Metrics very strong for resource issues
        EvidenceType.LOGS: 0.05,
        EvidenceType.TRACES: -0.05,
        EvidenceType.TOPOLOGY: -0.05,
    },
    HypothesisCategory.DEPENDENCY_FAILURE: {
        EvidenceType.METRICS: -0.05,
        EvidenceType.LOGS: 0.05,
        EvidenceType.TRACES: 0.10,       # Traces show downstream calls
        EvidenceType.TOPOLOGY: 0.15,     # Topology critical for dependency
    },
    HypothesisCategory.DEPLOYMENT: {
        EvidenceType.METRICS: 0.05,
        EvidenceType.LOGS: 0.10,         # Deploy events in logs
        EvidenceType.TRACES: -0.05,
        EvidenceType.TOPOLOGY: -0.05,
        EvidenceType.HISTORICAL: 0.10,   # Historical deploy issues
    },
    HypothesisCategory.CONFIGURATION: {
        EvidenceType.METRICS: -0.10,
        EvidenceType.LOGS: 0.15,         # Config errors in logs
        EvidenceType.TRACES: -0.05,
        EvidenceType.TOPOLOGY: -0.05,
    },
    HypothesisCategory.NETWORK: {
        EvidenceType.METRICS: 0.05,
        EvidenceType.LOGS: 0.10,
        EvidenceType.TRACES: 0.10,       # Network timeouts in traces
        EvidenceType.TOPOLOGY: 0.10,     # Cross-service network issues
    },
}


@dataclass
class EvidenceScore:
    """Score breakdown for a single evidence type."""
    evidence_type: EvidenceType
    raw_score: float           # 0-1 raw evidence support
    weight: float              # Applied weight
    quality_factor: float      # 0-1 quality multiplier
    weighted_score: float      # raw * weight * quality
    supporting_items: int      # Count of supporting evidence items
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ConfidenceResult:
    """Complete confidence scoring result for a hypothesis."""
    hypothesis_id: str
    total_confidence: float                    # Final calibrated 0-1
    evidence_scores: List[EvidenceScore]       # Breakdown by evidence type
    pattern_match_bonus: float                 # 0-0.15 bonus
    calibration_factor: float                  # Applied calibration
    threshold_met: bool                        # Meets action threshold (0.7)
    recommendation: str                        # "high_confidence", "needs_validation", "low_confidence"
    score_breakdown: Dict[str, float]          # Human-readable breakdown


class ConfidenceScorer:
    """
    Computes calibrated confidence scores for root cause hypotheses.

    Scoring pipeline:
    1. Score each evidence type independently (0-1)
    2. Apply category-specific weight adjustments
    3. Apply quality factors (freshness, coverage, consistency)
    4. Add pattern match bonus
    5. Calibrate to operational thresholds
    """

    def __init__(
        self,
        evidence_weights: Optional[Dict[EvidenceType, float]] = None,
        action_threshold: float = 0.7,
        high_confidence_threshold: float = 0.85,
        calibration_mode: str = "production"  # "production" | "conservative" | "aggressive"
    ):
        self.evidence_weights = evidence_weights or DEFAULT_EVIDENCE_WEIGHTS.copy()
        self.action_threshold = action_threshold
        self.high_confidence_threshold = high_confidence_threshold
        self.calibration_mode = calibration_mode

        # Validate weights sum to ~1.0
        total = sum(self.evidence_weights.values())
        if abs(total - 1.0) > 0.01:
            logger.warning(f"Evidence weights sum to {total}, not 1.0. Normalizing.")
            self.evidence_weights = {k: v/total for k, v in self.evidence_weights.items()}

        logger.info(f"Confidence Scorer initialized (mode: {calibration_mode}, action_threshold: {action_threshold})")

    def score(
        self,
        hypothesis: Hypothesis,
        evidence: CollectedEvidence,
        topology: Dict[str, Any],
        similar_incidents: List[Dict[str, Any]],
        correlated_alerts: List[Dict[str, Any]]
    ) -> ConfidenceResult:
        """
        Score a hypothesis against collected evidence.

        Args:
            hypothesis: Hypothesis to score
            evidence: Collected evidence from EvidenceCollector
            topology: Service topology
            similar_incidents: Historical incidents from KB
            correlated_alerts: Pre-correlated alert groups

        Returns:
            ConfidenceResult with total confidence and breakdown
        """
        evidence_scores = []

        # Score each evidence type
        metrics_score = self._score_metrics(hypothesis, evidence)
        evidence_scores.append(metrics_score)

        logs_score = self._score_logs(hypothesis, evidence)
        evidence_scores.append(logs_score)

        traces_score = self._score_traces(hypothesis, evidence)
        evidence_scores.append(traces_score)

        topology_score = self._score_topology(hypothesis, evidence, topology, correlated_alerts)
        evidence_scores.append(topology_score)

        historical_score = self._score_historical(hypothesis, similar_incidents)
        evidence_scores.append(historical_score)

        # LLM bonus if hypothesis was LLM-generated
        llm_score = self._score_llm(hypothesis)
        if llm_score.weight > 0:
            evidence_scores.append(llm_score)

        # Calculate weighted sum
        weighted_sum = sum(es.weighted_score for es in evidence_scores)

        # Apply pattern match bonus
        pattern_bonus = self._calculate_pattern_bonus(hypothesis)

        # Apply calibration
        raw_confidence = min(1.0, weighted_sum + pattern_bonus)
        calibrated_confidence = self._calibrate(raw_confidence, hypothesis.category)

        # Determine recommendation
        if calibrated_confidence >= self.high_confidence_threshold:
            recommendation = "high_confidence"
        elif calibrated_confidence >= self.action_threshold:
            recommendation = "needs_validation"
        else:
            recommendation = "low_confidence"

        # Build human-readable breakdown
        breakdown = self._build_breakdown(evidence_scores, pattern_bonus, calibrated_confidence)

        return ConfidenceResult(
            hypothesis_id=hypothesis.hypothesis_id,
            total_confidence=calibrated_confidence,
            evidence_scores=evidence_scores,
            pattern_match_bonus=pattern_bonus,
            calibration_factor=calibrated_confidence / raw_confidence if raw_confidence > 0 else 1.0,
            threshold_met=calibrated_confidence >= self.action_threshold,
            recommendation=recommendation,
            score_breakdown=breakdown
        )

    def _get_effective_weights(self, category: HypothesisCategory) -> Dict[EvidenceType, float]:
        """Get weights adjusted for hypothesis category."""
        weights = self.evidence_weights.copy()

        adjustments = CATEGORY_WEIGHT_ADJUSTMENTS.get(category, {})
        for ev_type, adj in adjustments.items():
            if ev_type in weights:
                weights[ev_type] = max(0.01, weights[ev_type] + adj)

        # Renormalize
        total = sum(weights.values())
        return {k: v/total for k, v in weights.items()}

    def _score_metrics(self, hypothesis: Hypothesis, evidence: CollectedEvidence) -> EvidenceScore:
        """Score metrics evidence for hypothesis."""
        weights = self._get_effective_weights(hypothesis.category)
        weight = weights.get(EvidenceType.METRICS, 0.3)

        if not evidence.metrics:
            return EvidenceScore(
                evidence_type=EvidenceType.METRICS,
                raw_score=0.0,
                weight=weight,
                quality_factor=0.0,
                weighted_score=0.0,
                supporting_items=0,
                details={"reason": "no_metrics"}
            )

        # Find metrics that support this hypothesis
        supporting_metrics = []
        hypothesis_keywords = self._hypothesis_to_keywords(hypothesis)

        for metric in evidence.metrics:
            if metric.is_anomalous:
                # Check if metric name matches hypothesis
                match_score = self._metric_matches_hypothesis(metric.metric_name, hypothesis_keywords)
                if match_score > 0:
                    supporting_metrics.append({
                        "metric": metric.metric_name,
                        "value": metric.value,
                        "threshold": metric.threshold,
                        "exceedance": metric.value / metric.threshold if metric.threshold > 0 else 1,
                        "match_score": match_score
                    })

        if not supporting_metrics:
            return EvidenceScore(
                evidence_type=EvidenceType.METRICS,
                raw_score=0.0,
                weight=weight,
                quality_factor=0.0,
                weighted_score=0.0,
                supporting_items=0,
                details={"anomalous_count": len([m for m in evidence.metrics if m.is_anomalous])}
            )

        # Raw score based on match strength and exceedance
        avg_match = sum(m["match_score"] for m in supporting_metrics) / len(supporting_metrics)
        avg_exceedance = min(2.0, sum(m["exceedance"] for m in supporting_metrics) / len(supporting_metrics))
        raw_score = min(1.0, avg_match * (1 + avg_exceedance) / 2)

        # Quality factors
        freshness = self._calculate_freshness([m.timestamp for m in evidence.metrics if m.is_anomalous])
        coverage = min(1.0, len(supporting_metrics) / 3)  # Expect at least 3 supporting metrics
        quality = (freshness + coverage) / 2

        weighted_score = raw_score * weight * quality

        return EvidenceScore(
            evidence_type=EvidenceType.METRICS,
            raw_score=raw_score,
            weight=weight,
            quality_factor=quality,
            weighted_score=weighted_score,
            supporting_items=len(supporting_metrics),
            details={
                "supporting_metrics": [m["metric"] for m in supporting_metrics],
                "avg_match": avg_match,
                "avg_exceedance": avg_exceedance,
                "freshness": freshness,
                "coverage": coverage
            }
        )

    def _score_logs(self, hypothesis: Hypothesis, evidence: CollectedEvidence) -> EvidenceScore:
        """Score log evidence for hypothesis."""
        weights = self._get_effective_weights(hypothesis.category)
        weight = weights.get(EvidenceType.LOGS, 0.25)

        if not evidence.logs:
            return EvidenceScore(
                evidence_type=EvidenceType.LOGS,
                raw_score=0.0,
                weight=weight,
                quality_factor=0.0,
                weighted_score=0.0,
                supporting_items=0,
                details={"reason": "no_logs"}
            )

        # Filter error/critical logs
        error_logs = [l for l in evidence.logs if l.severity in ("error", "critical")]
        if not error_logs:
            return EvidenceScore(
                evidence_type=EvidenceType.LOGS,
                raw_score=0.0,
                weight=weight,
                quality_factor=0.0,
                weighted_score=0.0,
                supporting_items=0,
                details={"total_logs": len(evidence.logs), "error_logs": 0}
            )

        # Match log messages against hypothesis
        hypothesis_keywords = self._hypothesis_to_keywords(hypothesis)
        supporting_logs = []

        for log in error_logs:
            match_score = self._text_matches_hypothesis(log.message, hypothesis_keywords)
            if match_score > 0:
                supporting_logs.append({
                    "message": log.message[:200],
                    "severity": log.severity,
                    "match_score": match_score
                })

        if not supporting_logs:
            return EvidenceScore(
                evidence_type=EvidenceType.LOGS,
                raw_score=0.0,
                weight=weight,
                quality_factor=0.0,
                weighted_score=0.0,
                supporting_items=0,
                details={"error_logs": len(error_logs)}
            )

        # Raw score based on match strength and severity
        avg_match = sum(l["match_score"] for l in supporting_logs) / len(supporting_logs)
        severity_boost = sum(1.5 if l["severity"] == "critical" else 1.0 for l in supporting_logs) / len(supporting_logs)
        raw_score = min(1.0, avg_match * severity_boost)

        # Quality factors
        freshness = self._calculate_freshness([l.timestamp for l in error_logs])
        coverage = min(1.0, len(supporting_logs) / 5)  # Expect at least 5 supporting logs
        consistency = self._calculate_log_consistency(supporting_logs)
        quality = (freshness + coverage + consistency) / 3

        weighted_score = raw_score * weight * quality

        return EvidenceScore(
            evidence_type=EvidenceType.LOGS,
            raw_score=raw_score,
            weight=weight,
            quality_factor=quality,
            weighted_score=weighted_score,
            supporting_items=len(supporting_logs),
            details={
                "supporting_logs": len(supporting_logs),
                "avg_match": avg_match,
                "severity_boost": severity_boost,
                "freshness": freshness,
                "coverage": coverage,
                "consistency": consistency
            }
        )

    def _score_traces(self, hypothesis: Hypothesis, evidence: CollectedEvidence) -> EvidenceScore:
        """Score trace evidence for hypothesis."""
        weights = self._get_effective_weights(hypothesis.category)
        weight = weights.get(EvidenceType.TRACES, 0.15)

        if not evidence.traces:
            return EvidenceScore(
                evidence_type=EvidenceType.TRACES,
                raw_score=0.0,
                weight=weight,
                quality_factor=0.0,
                weighted_score=0.0,
                supporting_items=0,
                details={"reason": "no_traces"}
            )

        # Filter error/timeout traces
        error_traces = [t for t in evidence.traces if t.status in ("error", "timeout")]
        if not error_traces:
            return EvidenceScore(
                evidence_type=EvidenceType.TRACES,
                raw_score=0.0,
                weight=weight,
                quality_factor=0.0,
                weighted_score=0.0,
                supporting_items=0,
                details={"total_traces": len(evidence.traces), "error_traces": 0}
            )

        # Match trace spans against hypothesis
        hypothesis_keywords = self._hypothesis_to_keywords(hypothesis)
        supporting_traces = []

        for trace in error_traces:
            match_score = self._text_matches_hypothesis(trace.span_name, hypothesis_keywords)
            # Also check attributes
            for attr_key, attr_val in trace.attributes.items():
                attr_match = self._text_matches_hypothesis(f"{attr_key}: {attr_val}", hypothesis_keywords)
                match_score = max(match_score, attr_match)

            if match_score > 0:
                supporting_traces.append({
                    "span": trace.span_name,
                    "status": trace.status,
                    "duration_ms": trace.duration_ms,
                    "match_score": match_score
                })

        if not supporting_traces:
            return EvidenceScore(
                evidence_type=EvidenceType.TRACES,
                raw_score=0.0,
                weight=weight,
                quality_factor=0.0,
                weighted_score=0.0,
                supporting_items=0,
                details={"error_traces": len(error_traces)}
            )

        # Raw score based on match strength and duration anomaly
        avg_match = sum(t["match_score"] for t in supporting_traces) / len(supporting_traces)
        duration_factor = min(2.0, sum(t["duration_ms"] for t in supporting_traces) / len(supporting_traces) / 1000)  # Normalize to seconds
        raw_score = min(1.0, avg_match * (1 + duration_factor) / 2)

        # Quality factors
        freshness = self._calculate_freshness([t.timestamp for t in error_traces])
        coverage = min(1.0, len(supporting_traces) / 3)
        quality = (freshness + coverage) / 2

        weighted_score = raw_score * weight * quality

        return EvidenceScore(
            evidence_type=EvidenceType.TRACES,
            raw_score=raw_score,
            weight=weight,
            quality_factor=quality,
            weighted_score=weighted_score,
            supporting_items=len(supporting_traces),
            details={
                "supporting_traces": len(supporting_traces),
                "avg_match": avg_match,
                "avg_duration_ms": sum(t["duration_ms"] for t in supporting_traces) / len(supporting_traces),
                "freshness": freshness,
                "coverage": coverage
            }
        )

    def _score_topology(
        self,
        hypothesis: Hypothesis,
        evidence: CollectedEvidence,
        topology: Dict[str, Any],
        correlated_alerts: List[Dict[str, Any]]
    ) -> EvidenceScore:
        """Score topology/cascade evidence for hypothesis."""
        weights = self._get_effective_weights(hypothesis.category)
        weight = weights.get(EvidenceType.TOPOLOGY, 0.15)

        score_components = []
        details = {"components": []}

        # Check upstream cascade
        upstream = topology.get("upstream", [])
        upstream_alerts = []
        for ag in correlated_alerts:
            for alert in ag.get("alerts", []):
                if alert.get("service") in upstream:
                    upstream_alerts.append(alert)

        if upstream_alerts and hypothesis.category in (HypothesisCategory.DEPENDENCY_FAILURE, HypothesisCategory.RESOURCE_EXHAUSTION):
            cascade_score = min(1.0, len(upstream_alerts) / len(upstream))
            score_components.append(("upstream_cascade", cascade_score))
            details["components"].append(f"upstream_cascade: {cascade_score:.2f} ({len(upstream_alerts)}/{len(upstream)})")

        # Check downstream impact
        downstream = topology.get("downstream", [])
        downstream_alerts = []
        for ag in correlated_alerts:
            for alert in ag.get("alerts", []):
                if alert.get("service") in downstream:
                    downstream_alerts.append(alert)

        if downstream_alerts and hypothesis.category == HypothesisCategory.DEPENDENCY_FAILURE:
            # This service causing downstream issues
            cascade_score = min(1.0, len(downstream_alerts) / max(1, len(downstream)))
            score_components.append(("downstream_impact", cascade_score))
            details["components"].append(f"downstream_impact: {cascade_score:.2f}")

        # Check blast radius (multiple services)
        all_affected = set()
        for ag in correlated_alerts:
            for alert in ag.get("alerts", []):
                all_affected.add(alert.get("service"))

        if len(all_affected) > 3 and hypothesis.category == HypothesisCategory.RESOURCE_EXHAUSTION:
            blast_score = min(1.0, (len(all_affected) - 3) / 10)
            score_components.append(("blast_radius", blast_score))
            details["components"].append(f"blast_radius: {blast_score:.2f} ({len(all_affected)} services)")

        if not score_components:
            return EvidenceScore(
                evidence_type=EvidenceType.TOPOLOGY,
                raw_score=0.0,
                weight=weight,
                quality_factor=0.0,
                weighted_score=0.0,
                supporting_items=0,
                details=details
            )

        raw_score = sum(s for _, s in score_components) / len(score_components)
        quality = 0.8  # Topology evidence is generally reliable
        weighted_score = raw_score * weight * quality

        return EvidenceScore(
            evidence_type=EvidenceType.TOPOLOGY,
            raw_score=raw_score,
            weight=weight,
            quality_factor=quality,
            weighted_score=weighted_score,
            supporting_items=len(score_components),
            details=details
        )

    def _score_historical(self, hypothesis: Hypothesis, similar_incidents: List[Dict[str, Any]]) -> EvidenceScore:
        """Score historical similarity evidence."""
        weights = self._get_effective_weights(hypothesis.category)
        weight = weights.get(EvidenceType.HISTORICAL, 0.15)

        if not similar_incidents:
            return EvidenceScore(
                evidence_type=EvidenceType.HISTORICAL,
                raw_score=0.0,
                weight=weight,
                quality_factor=0.0,
                weighted_score=0.0,
                supporting_items=0,
                details={"reason": "no_historical_incidents"}
            )

        # Find incidents matching this hypothesis category or root cause
        matches = []
        hypothesis_keywords = self._hypothesis_to_keywords(hypothesis)

        for incident in similar_incidents:
            root_cause = incident.get("root_cause", "").lower()
            incident_service = incident.get("service", "")

            # Match by root cause keywords
            rc_match = self._text_matches_hypothesis(root_cause, hypothesis_keywords)

            # Boost if same service
            service_boost = 1.5 if incident_service == hypothesis.affected_services[0] else 1.0

            if rc_match > 0:
                matches.append({
                    "incident_id": incident.get("incident_id"),
                    "service": incident_service,
                    "root_cause": root_cause[:100],
                    "match_score": rc_match * service_boost,
                    "similarity": incident.get("similarity", 0.5)
                })

        if not matches:
            return EvidenceScore(
                evidence_type=EvidenceType.HISTORICAL,
                raw_score=0.0,
                weight=weight,
                quality_factor=0.0,
                weighted_score=0.0,
                supporting_items=0,
                details={"total_incidents": len(similar_incidents)}
            )

        # Raw score based on best match and number of matches
        best_match = max(m["match_score"] for m in matches)
        match_count_factor = min(1.0, len(matches) / 3)
        raw_score = min(1.0, best_match * match_count_factor)

        # Quality: recent incidents weighted higher
        quality = 0.7  # Historical evidence is suggestive but not definitive
        weighted_score = raw_score * weight * quality

        return EvidenceScore(
            evidence_type=EvidenceType.HISTORICAL,
            raw_score=raw_score,
            weight=weight,
            quality_factor=quality,
            weighted_score=weighted_score,
            supporting_items=len(matches),
            details={
                "matches": [m["incident_id"] for m in matches],
                "best_match": best_match,
                "match_count": len(matches)
            }
        )

    def _score_llm(self, hypothesis: Hypothesis) -> EvidenceScore:
        """Score LLM-generated hypothesis (lower weight)."""
        if hypothesis.metadata.get("type") != "llm_generated":
            return EvidenceScore(
                evidence_type=EvidenceType.LLM,
                raw_score=0.0,
                weight=0.0,
                quality_factor=0.0,
                weighted_score=0.0,
                supporting_items=0,
                details={"reason": "not_llm_generated"}
            )

        weight = 0.05  # Low weight for LLM
        raw_score = hypothesis.confidence  # Use LLM's own confidence
        quality = 0.5  # LLM is speculative
        weighted_score = raw_score * weight * quality

        return EvidenceScore(
            evidence_type=EvidenceType.LLM,
            raw_score=raw_score,
            weight=weight,
            quality_factor=quality,
            weighted_score=weighted_score,
            supporting_items=1,
            details={"model": hypothesis.metadata.get("model", "unknown")}
        )

    def _calculate_pattern_bonus(self, hypothesis: Hypothesis) -> float:
        """Calculate bonus for strong pattern matches."""
        pattern_score = hypothesis.metadata.get("pattern_score", 0)

        if pattern_score >= 10:
            return 0.15
        elif pattern_score >= 7:
            return 0.10
        elif pattern_score >= 4:
            return 0.05
        return 0.0

    def _calibrate(self, raw_confidence: float, category: HypothesisCategory) -> float:
        """Calibrate raw confidence to operational thresholds."""
        if self.calibration_mode == "conservative":
            # More conservative: require stronger evidence
            return raw_confidence ** 1.3
        elif self.calibration_mode == "aggressive":
            # More aggressive: lower threshold for action
            return min(1.0, raw_confidence ** 0.8)
        else:
            # Production: slight conservative bias
            return raw_confidence ** 1.1

    def _hypothesis_to_keywords(self, hypothesis: Hypothesis) -> List[str]:
        """Extract keywords from hypothesis for matching."""
        keywords = []

        # Category keywords
        cat_keywords = {
            HypothesisCategory.RESOURCE_EXHAUSTION: ["pool", "memory", "cpu", "thread", "connection", "exhaust", "oom", "limit", "quota", "capacity"],
            HypothesisCategory.DEPENDENCY_FAILURE: ["downstream", "upstream", "dependenc", "cascade", "database", "redis", "kafka", "timeout", "unavailable"],
            HypothesisCategory.DEPLOYMENT: ["deploy", "release", "version", "rollback", "config", "change"],
            HypothesisCategory.CONFIGURATION: ["config", "configmap", "secret", "flag", "environment", "variable"],
            HypothesisCategory.CODE_DEFECT: ["bug", "null", "exception", "error", "defect", "logic"],
            HypothesisCategory.NETWORK: ["network", "dns", "connect", "timeout", "unreachable", "latency"],
            HypothesisCategory.DATA_ISSUE: ["data", "corrupt", "migration", "schema"],
            HypothesisCategory.SECURITY: ["auth", "cert", "security", "permission", "breach"],
            HypothesisCategory.CAPACITY: ["scale", "quota", "limit", "capacity"],
        }
        keywords.extend(cat_keywords.get(hypothesis.category, []))

        # Root cause keywords
        rc_words = hypothesis.root_cause.lower().split()
        keywords.extend([w for w in rc_words if len(w) > 3])

        # Title keywords
        title_words = hypothesis.title.lower().split()
        keywords.extend([w for w in title_words if len(w) > 3])

        # Evidence references
        for ref in hypothesis.evidence_references:
            if ":" in ref:
                keywords.append(ref.split(":")[1])

        return list(set(keywords))

    def _metric_matches_hypothesis(self, metric_name: str, keywords: List[str]) -> float:
        """Score how well a metric name matches hypothesis keywords."""
        metric_lower = metric_name.lower()

        # Direct keyword matches
        matches = sum(1 for kw in keywords if kw in metric_lower)
        if matches > 0:
            return min(1.0, matches / 2)

        # Fuzzy matches for common patterns
        patterns = {
            "pool": ["pool", "connection", "hikari"],
            "memory": ["memory", "heap", "jvm", "rss"],
            "cpu": ["cpu", "processor", "throttl"],
            "thread": ["thread", "executor", "queue"],
            "latency": ["latency", "duration", "response_time", "rt_"],
            "error": ["error", "fail", "5xx", "exception"],
            "queue": ["queue", "pending", "wait", "backlog"],
        }

        for pattern, terms in patterns.items():
            if any(t in metric_lower for t in terms):
                if any(t in " ".join(keywords) for t in terms):
                    return 0.6

        return 0.0

    def _text_matches_hypothesis(self, text: str, keywords: List[str]) -> float:
        """Score how well text matches hypothesis keywords."""
        text_lower = text.lower()

        matches = sum(1 for kw in keywords if kw in text_lower)
        if matches == 0:
            return 0.0

        # Score based on match count and text length
        return min(1.0, matches / max(1, len(keywords) / 5))

    def _calculate_freshness(self, timestamps: List[datetime]) -> float:
        """Calculate freshness factor (1.0 = very recent, 0.0 = old)."""
        if not timestamps:
            return 0.0

        now = datetime.utcnow()
        ages = [(now - ts).total_seconds() / 60 for ts in timestamps]  # Age in minutes
        avg_age = sum(ages) / len(ages)

        # Freshness decays over 30 minutes
        return max(0.0, 1.0 - avg_age / 30)

    def _calculate_log_consistency(self, supporting_logs: List[Dict]) -> float:
        """Check if supporting logs are consistent (similar messages)."""
        if len(supporting_logs) < 2:
            return 0.5

        # Simple: check if messages share common terms
        messages = [l["message"] for l in supporting_logs]
        words_sets = [set(m.lower().split()) for m in messages]

        # Jaccard similarity between first and rest
        first = words_sets[0]
        similarities = []
        for ws in words_sets[1:]:
            intersection = len(first & ws)
            union = len(first | ws)
            if union > 0:
                similarities.append(intersection / union)

        return sum(similarities) / len(similarities) if similarities else 0.5

    def _build_breakdown(
        self,
        evidence_scores: List[EvidenceScore],
        pattern_bonus: float,
        final_confidence: float
    ) -> Dict[str, float]:
        """Build human-readable score breakdown."""
        breakdown = {}

        for es in evidence_scores:
            if es.supporting_items > 0:
                breakdown[f"{es.evidence_type.value}_score"] = round(es.raw_score, 3)
                breakdown[f"{es.evidence_type.value}_weight"] = round(es.weight, 3)
                breakdown[f"{es.evidence_type.value}_quality"] = round(es.quality_factor, 3)
                breakdown[f"{es.evidence_type.value}_contribution"] = round(es.weighted_score, 4)
                breakdown[f"{es.evidence_type.value}_items"] = es.supporting_items

        breakdown["pattern_bonus"] = round(pattern_bonus, 3)
        breakdown["raw_total"] = round(sum(es.weighted_score for es in evidence_scores) + pattern_bonus, 4)
        breakdown["final_confidence"] = round(final_confidence, 3)

        return breakdown

    def rank_hypotheses(
        self,
        hypotheses: List[Hypothesis],
        evidence: CollectedEvidence,
        topology: Dict[str, Any],
        similar_incidents: List[Dict[str, Any]],
        correlated_alerts: List[Dict[str, Any]]
    ) -> List[Tuple[Hypothesis, ConfidenceResult]]:
        """Score and rank all hypotheses by confidence."""
        results = []

        for hypothesis in hypotheses:
            confidence = self.score(hypothesis, evidence, topology, similar_incidents, correlated_alerts)
            # Update hypothesis with confidence
            hypothesis.confidence = confidence.total_confidence
            results.append((hypothesis, confidence))

        # Sort by confidence descending
        results.sort(key=lambda x: x[1].total_confidence, reverse=True)

        return results


# Standalone test function
async def test_confidence_scorer():
    """Test confidence scorer with mock data."""
    from evidence_collector import CollectedEvidence, MetricsEvidence, LogEvidence, TraceEvidence
    from hypothesis_engine import Hypothesis, HypothesisCategory
    from datetime import datetime

    # Create mock evidence
    evidence = CollectedEvidence()
    now = datetime.utcnow()

    evidence.metrics = [
        MetricsEvidence(
            service="java-service",
            timestamp=now,
            metric_name="hikaricp_connections_pending",
            value=15,
            threshold=1,
            unit="count",
            promql_query="test"
        ),
        MetricsEvidence(
            service="java-service",
            timestamp=now,
            metric_name="error_rate",
            value=0.12,
            threshold=0.05,
            unit="ratio",
            promql_query="test"
        ),
        MetricsEvidence(
            service="java-service",
            timestamp=now,
            metric_name="cpu_usage",
            value=45,
            threshold=80,
            unit="percent",
            promql_query="test"
        )
    ]

    evidence.logs = [
        LogEvidence(
            service="java-service",
            timestamp=now,
            metric_name="log_connection_errors",
            value=1,
            threshold=0,
            severity="error",
            message="HikariCP - Connection not available, timeout after 30000ms"
        ),
        LogEvidence(
            service="java-service",
            timestamp=now,
            metric_name="log_connection_errors",
            value=1,
            threshold=0,
            severity="error",
            message="Pool exhausted - failing to acquire connection"
        )
    ]

    evidence.traces = [
        TraceEvidence(
            service="java-service",
            timestamp=now,
            metric_name="trace_db_query",
            value=1,
            threshold=0,
            span_name="SELECT orders",
            duration_ms=35000,
            status="timeout",
            attributes={"db.system": "postgresql"}
        )
    ]

    topology = {
        "upstream": [],
        "downstream": ["python-service"]
    }

    similar_incidents = [
        {
            "incident_id": "INC-2024-015",
            "service": "java-service",
            "root_cause": "Connection pool exhaustion - HikariCP maxPoolSize=10, no timeout config",
            "similarity": 0.9
        }
    ]

    correlated_alerts = [{
        "alerts": [
            {"service": "java-service", "alert": "HighErrorRate"},
            {"service": "python-service", "alert": "HighLatency"}
        ]
    }]

    # Create test hypothesis
    hypothesis = Hypothesis(
        hypothesis_id="connection_pool_exhaustion_java-service_0",
        title="Connection Pool Exhaustion",
        description="Database connection pool exhausted causing request failures",
        category=HypothesisCategory.RESOURCE_EXHAUSTION,
        root_cause="Connection pool size too small for load; missing timeout configuration; connection leak in code",
        evidence_summary="Matched evidence: metric:connection_pool_pending, log:connection_errors, pattern:HikariCP (pattern score: 10)",
        affected_services=["java-service"],
        upstream_services=[],
        downstream_services=["python-service"],
        recommended_actions=["Increase connection pool size", "Add connectionTimeout"],
        evidence_references=["metric:connection_pool_pending", "log:connection_errors", "pattern:HikariCP"],
        metadata={"pattern_score": 10, "failure_mode_id": "connection_pool_exhaustion"}
    )

    scorer = ConfidenceScorer(calibration_mode="production")
    confidence = scorer.score(hypothesis, evidence, topology, similar_incidents, correlated_alerts)

    print(f"\nHypothesis: {hypothesis.title}")
    print(f"Final Confidence: {confidence.total_confidence:.3f}")
    print(f"Recommendation: {confidence.recommendation}")
    print(f"Threshold Met: {confidence.threshold_met}")
    print("\nBreakdown:")
    for k, v in confidence.score_breakdown.items():
        print(f"  {k}: {v}")

    print("\nEvidence Scores:")
    for es in confidence.evidence_scores:
        if es.supporting_items > 0:
            print(f"  {es.evidence_type.value}: raw={es.raw_score:.3f}, weight={es.weight:.3f}, quality={es.quality_factor:.3f}, contribution={es.weighted_score:.4f}, items={es.supporting_items}")


if __name__ == "__main__":
    import asyncio
    logging.basicConfig(level=logging.INFO)
    asyncio.run(test_confidence_scorer())