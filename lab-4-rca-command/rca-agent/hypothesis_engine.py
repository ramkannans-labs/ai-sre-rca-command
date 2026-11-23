"""
Hypothesis Engine - Generates Root Cause Hypotheses

This module generates ranked root cause hypotheses by combining:
1. Evidence from telemetry (metrics, logs, traces)
2. Service topology (upstream/downstream dependencies)
3. Historical patterns from Knowledge Base
4. Correlated alert groups

Architecture:
┌─────────────────────────────────────────────────────────────────────┐
│                    HYPOTHESIS ENGINE                                │
├─────────────────────────────────────────────────────────────────────┤
│  generate()                                                         │
│    ├─▶ Analyze evidence patterns                                    │
│    ├─▶ Match against failure mode catalog                           │
│    ├─▶ Query Knowledge Base for similar incidents                   │
│    ├─▶ Apply topology reasoning (blast radius, cascades)            │
│    ├─▶ Use LLM for hypothesis synthesis                             │
│    └─▶ Return ranked hypotheses with evidence mapping               │
└─────────────────────────────────────────────────────────────────────┘
"""

import asyncio
import json
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Set
from enum import Enum

import httpx
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class HypothesisCategory(str, Enum):
    """Categories of failure hypotheses."""
    DEPLOYMENT = "deployment"           # Bad deployment, config change
    RESOURCE_EXHAUSTION = "resource_exhaustion"  # CPU, memory, disk, connections
    DEPENDENCY_FAILURE = "dependency_failure"    # Upstream/downstream service
    CONFIGURATION = "configuration"     # Config drift, missing config
    CODE_DEFECT = "code_defect"         # Bug in application code
    NETWORK = "network"                 # DNS, latency, connectivity
    DATA_ISSUE = "data_issue"           # Corruption, migration, schema
    SECURITY = "security"               # Auth, certs, breach
    CAPACITY = "capacity"               # Scaling limits, quotas
    UNKNOWN = "unknown"                 # Unable to categorize


@dataclass
class Hypothesis:
    """A root cause hypothesis with supporting evidence."""
    hypothesis_id: str
    title: str
    description: str
    category: HypothesisCategory
    root_cause: str
    evidence_summary: str
    affected_services: List[str] = field(default_factory=list)
    upstream_services: List[str] = field(default_factory=list)
    downstream_services: List[str] = field(default_factory=list)
    recommended_actions: List[str] = field(default_factory=list)
    similar_incidents: List[Dict[str, Any]] = field(default_factory=list)
    confidence: float = 0.0  # Will be set by ConfidenceScorer
    evidence_references: List[str] = field(default_factory=list)  # IDs of supporting evidence
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "hypothesis_id": self.hypothesis_id,
            "title": self.title,
            "description": self.description,
            "category": self.category.value,
            "root_cause": self.root_cause,
            "evidence_summary": self.evidence_summary,
            "affected_services": self.affected_services,
            "upstream_services": self.upstream_services,
            "downstream_services": self.downstream_services,
            "recommended_actions": self.recommended_actions,
            "similar_incidents": self.similar_incidents,
            "confidence": self.confidence,
            "evidence_references": self.evidence_references,
            "metadata": self.metadata
        }


class FailureModeCatalog:
    """
    Catalog of known failure modes with pattern matching rules.

    Each failure mode defines:
    - Symptom patterns (metrics, logs, traces)
    - Topology patterns (upstream/downstream effects)
    - Typical root causes
    - Recommended actions
    """

    FAILURE_MODES = [
        {
            "id": "connection_pool_exhaustion",
            "category": HypothesisCategory.RESOURCE_EXHAUSTION,
            "title": "Connection Pool Exhaustion",
            "description": "Database connection pool exhausted causing request failures",
            "symptoms": {
                "metrics": ["connection_pool_pending", "connection_pool_active"],
                "logs": ["connection_errors", "database_errors"],
                "thresholds": {"connection_pool_pending": 1, "connection_pool_active": 80}
            },
            "topology": {"affects_downstream": True, "cascade_pattern": "fan_out"},
            "root_cause": "Connection pool size too small for load; missing timeout configuration; connection leak in code",
            "actions": [
                "Increase connection pool size (maxPoolSize)",
                "Add connectionTimeout and idleTimeout",
                "Fix connection leak in application code",
                "Add connection pool monitoring alerts"
            ],
            "similar_patterns": ["HikariCP", "pool exhausted", "connection not available", "timeout waiting for connection"]
        },
        {
            "id": "memory_leak",
            "category": HypothesisCategory.RESOURCE_EXHAUSTION,
            "title": "Memory Leak / OOM",
            "description": "Gradual memory growth leading to OOM kills or GC thrashing",
            "symptoms": {
                "metrics": ["memory_usage", "gc_pause"],
                "logs": ["memory_errors"],
                "thresholds": {"memory_usage": 85, "gc_pause": 0.5}
            },
            "topology": {"affects_downstream": False, "cascade_pattern": "self_contained"},
            "root_cause": "Unclosed resources (DB connections, streams); cache without eviction; classloader leak",
            "actions": [
                "Analyze heap dump for retained objects",
                "Add memory profiling to CI",
                "Set memory limits and requests",
                "Fix resource cleanup in finally blocks"
            ],
            "similar_patterns": ["OOM", "OutOfMemoryError", "heap space", "GC overhead limit", "memory growing"]
        },
        {
            "id": "cpu_saturation",
            "category": HypothesisCategory.RESOURCE_EXHAUSTION,
            "title": "CPU Saturation",
            "description": "CPU at 100% causing latency spikes and timeouts",
            "symptoms": {
                "metrics": ["cpu_usage", "latency_p99", "latency_p95"],
                "logs": ["thread_errors"],
                "thresholds": {"cpu_usage": 80, "latency_p99": 1.0}
            },
            "topology": {"affects_downstream": True, "cascade_pattern": "fan_out"},
            "root_cause": "Inefficient query/algorithm; infinite loop; missing indexes; thread pool contention",
            "actions": [
                "Profile CPU hotspots (async-profiler, py-spy)",
                "Check for bad database queries (missing indexes)",
                "Review recent code changes for algorithmic complexity",
                "Scale horizontally or increase CPU limits"
            ],
            "similar_patterns": ["high cpu", "cpu spike", "throttling", "latency spike", "timeout"]
        },
        {
            "id": "thread_pool_exhaustion",
            "category": HypothesisCategory.RESOURCE_EXHAUSTION,
            "title": "Thread Pool Exhaustion",
            "description": "Application thread pool saturated, requests queued or rejected",
            "symptoms": {
                "metrics": ["thread_pool_active", "thread_pool_queue"],
                "logs": ["thread_errors"],
                "thresholds": {"thread_pool_queue": 10}
            },
            "topology": {"affects_downstream": True, "cascade_pattern": "fan_out"},
            "root_cause": "Downstream service slow causing thread backup; pool size too small; blocking calls in async code",
            "actions": [
                "Increase thread pool size",
                "Add timeouts to downstream calls",
                "Implement circuit breaker pattern",
                "Scale service replicas"
            ],
            "similar_patterns": ["thread pool", "queue full", "rejected execution", "task rejected", "executor"]
        },
        {
            "id": "bad_deployment",
            "category": HypothesisCategory.DEPLOYMENT,
            "title": "Bad Deployment / Config Change",
            "description": "Recent deployment introduced regression",
            "symptoms": {
                "metrics": ["error_rate", "latency_p99", "request_rate"],
                "logs": ["deployment_events", "errors"],
                "thresholds": {"error_rate": 0.05}
            },
            "topology": {"affects_downstream": True, "cascade_pattern": "fan_out"},
            "root_cause": "New code version has bug; config change broke behavior; dependency version mismatch",
            "actions": [
                "Rollback to previous version",
                "Compare configs between versions",
                "Run integration tests against failing version",
                "Check deployment artifacts for completeness"
            ],
            "similar_patterns": ["deploy", "rollback", "version", "release", "v2.", "v3."]
        },
        {
            "id": "downstream_failure",
            "category": HypothesisCategory.DEPENDENCY_FAILURE,
            "title": "Downstream Service Failure",
            "description": "Upstream service failure causing cascade to this service",
            "symptoms": {
                "metrics": ["error_rate", "latency_p99", "request_rate"],
                "logs": ["errors", "timeout"],
                "thresholds": {"error_rate": 0.05, "latency_p99": 5.0}
            },
            "topology": {"affects_downstream": False, "cascade_pattern": "fan_in"},
            "root_cause": "Downstream service (DB, cache, API) unavailable or slow; circuit breaker open; DNS resolution failure",
            "actions": [
                "Check downstream service health",
                "Verify network connectivity",
                "Implement fallback/circuit breaker",
                "Scale downstream service"
            ],
            "similar_patterns": ["downstream", "upstream", "dependency", "cascade", "timeout calling"]
        },
        {
            "id": "database_issues",
            "category": HypothesisCategory.DEPENDENCY_FAILURE,
            "title": "Database Performance Issues",
            "description": "Database slow or unavailable causing service degradation",
            "symptoms": {
                "metrics": ["db_connections", "latency_p99", "error_rate"],
                "logs": ["database_errors", "connection_errors"],
                "thresholds": {"db_connections": 80, "latency_p99": 2.0}
            },
            "topology": {"affects_downstream": True, "cascade_pattern": "fan_out"},
            "root_cause": "Long-running queries; lock contention; missing indexes; vacuum needed; replica lag",
            "actions": [
                "Check pg_stat_activity for blocking queries",
                "Analyze slow query log",
                "Add missing indexes",
                "Scale read replicas",
                "Check for connection leaks"
            ],
            "similar_patterns": ["database", "postgres", "postgresql", "mysql", "sql", "query", "lock", "deadlock"]
        },
        {
            "id": "kafka_consumer_lag",
            "category": HypothesisCategory.RESOURCE_EXHAUSTION,
            "title": "Kafka Consumer Lag",
            "description": "Kafka consumers falling behind producing backlog",
            "symptoms": {
                "metrics": ["kafka_consumer_lag"],
                "logs": ["errors", "warnings"],
                "thresholds": {"kafka_consumer_lag": 1000}
            },
            "topology": {"affects_downstream": True, "cascade_pattern": "fan_out"},
            "root_cause": "Consumer processing slower than producer; consumer crashed; partition imbalance; rebalance storm",
            "actions": [
                "Scale consumer instances",
                "Check consumer processing time",
                "Add consumer group monitoring",
                "Investigate rebalance frequency"
            ],
            "similar_patterns": ["kafka", "consumer lag", "rebalance", "partition", "offset"]
        },
        {
            "id": "redis_issues",
            "category": HypothesisCategory.DEPENDENCY_FAILURE,
            "title": "Redis Connection / Performance Issues",
            "description": "Redis unavailable or slow causing cache misses and latency",
            "symptoms": {
                "metrics": ["redis_connections", "latency_p99", "error_rate"],
                "logs": ["errors", "connection_errors"],
                "thresholds": {"redis_connections": 8000}
            },
            "topology": {"affects_downstream": True, "cascade_pattern": "fan_out"},
            "root_cause": "Connection pool exhausted; Redis OOM; slow commands (KEYS, FLUSHALL); network partition",
            "actions": [
                "Check Redis memory usage",
                "Increase connection pool",
                "Use SCAN instead of KEYS",
                "Add Redis read replicas"
            ],
            "similar_patterns": ["redis", "cache", "connection refused", "timeout", "OOM"]
        },
        {
            "id": "config_drift",
            "category": HypothesisCategory.CONFIGURATION,
            "title": "Configuration Drift / Missing Config",
            "description": "Configuration mismatch between environments or missing required config",
            "symptoms": {
                "metrics": ["error_rate", "latency_p99"],
                "logs": ["errors", "warnings"],
                "thresholds": {"error_rate": 0.01}
            },
            "topology": {"affects_downstream": False, "cascade_pattern": "self_contained"},
            "root_cause": "ConfigMap/Secret not updated; environment variable missing; feature flag misconfigured; version skew",
            "actions": [
                "Compare config between working/non-working environments",
                "Verify ConfigMap/Secret values",
                "Check feature flag states",
                "Validate config schema in CI"
            ],
            "similar_patterns": ["config", "configuration", "configmap", "secret", "environment variable", "feature flag"]
        },
        {
            "id": "network_issues",
            "category": HypothesisCategory.NETWORK,
            "title": "Network Connectivity / DNS Issues",
            "description": "Network partition, DNS resolution failure, or latency spike",
            "symptoms": {
                "metrics": ["error_rate", "latency_p99"],
                "logs": ["errors", "connection_errors"],
                "thresholds": {"error_rate": 0.05, "latency_p99": 5.0}
            },
            "topology": {"affects_downstream": True, "cascade_pattern": "fan_out"},
            "root_cause": "Security group / NACL misconfiguration; DNS outage; service mesh misconfig; CNI issues; MTU mismatch",
            "actions": [
                "Check security groups and NACLs",
                "Verify DNS resolution",
                "Check service mesh (Istio/Linkerd) config",
                "Test connectivity with kubectl exec",
                "Check CNI plugin health"
            ],
            "similar_patterns": ["network", "dns", "connection refused", "timeout", "unreachable", "service mesh", "istio"]
        },
    ]


class HypothesisEngine:
    """
    Generates root cause hypotheses from evidence, topology, and historical patterns.

    The engine uses a multi-stage approach:
    1. Pattern matching against failure mode catalog
    2. Topology-based reasoning (blast radius, cascade direction)
    3. Knowledge base similarity search
    4. LLM-assisted synthesis for complex cases
    """

    def __init__(
        self,
        knowledge_base_url: str,
        anthropic_api_key: Optional[str] = None,
        model: str = "claude-3-5-sonnet-20241022"
    ):
        self.knowledge_base_url = knowledge_base_url.rstrip("/")
        self.anthropic_api_key = anthropic_api_key or os.getenv("ANTHROPIC_API_KEY")
        self.model = model
        self.catalog = FailureModeCatalog()
        self.client = httpx.AsyncClient(timeout=30)

        logger.info(f"Hypothesis Engine initialized with KB: {self.knowledge_base_url}")

    async def generate(
        self,
        alert: str,
        service: str,
        evidence: Any,
        topology: Dict[str, Any],
        similar_incidents: List[Dict[str, Any]],
        correlated_alerts: List[Dict[str, Any]]
    ) -> List[Hypothesis]:
        """
        Generate ranked hypotheses for the incident.

        Args:
            alert: The triggering alert description
            service: Primary affected service
            evidence: CollectedEvidence from EvidenceCollector
            topology: Service topology from Knowledge Graph
            similar_incidents: Historical incidents from Knowledge Base
            correlated_alerts: Pre-correlated alert groups

        Returns:
            List of Hypothesis objects (unsorted, ConfidenceScorer will rank)
        """
        hypotheses = []

        # Stage 1: Pattern matching against failure mode catalog
        pattern_hypotheses = self._match_failure_modes(evidence, topology, service)
        hypotheses.extend(pattern_hypotheses)

        # Stage 2: Topology-based hypotheses (cascade, blast radius)
        topology_hypotheses = self._generate_topology_hypotheses(
            evidence, topology, service, correlated_alerts
        )
        hypotheses.extend(topology_hypotheses)

        # Stage 3: Historical pattern hypotheses
        history_hypotheses = self._generate_historical_hypotheses(
            similar_incidents, evidence, service
        )
        hypotheses.extend(history_hypotheses)

        # Stage 4: LLM synthesis for complex/novel cases
        if len(hypotheses) < 3 or not any(h.confidence > 0.5 for h in hypotheses):
            llm_hypotheses = await self._generate_llm_hypotheses(
                alert, service, evidence, topology, similar_incidents
            )
            hypotheses.extend(llm_hypotheses)

        # Deduplicate by root cause similarity
        unique_hypotheses = self._deduplicate_hypotheses(hypotheses)

        logger.info(f"Generated {len(unique_hypotheses)} unique hypotheses")
        return unique_hypotheses

    def _match_failure_modes(
        self,
        evidence: Any,
        topology: Dict[str, Any],
        service: str
    ) -> List[Hypothesis]:
        """Match evidence patterns against failure mode catalog."""
        hypotheses = []

        # Build evidence index for quick lookup
        metric_names = {m.metric_name for m in evidence.metrics}
        log_types = {l.metric_name for l in evidence.logs}
        trace_types = {t.metric_name for t in evidence.traces}

        # Check anomalous metrics
        anomalous_metrics = {m.metric_name: m for m in evidence.metrics if m.is_anomalous}
        error_logs = [l for l in evidence.logs if l.severity in ("error", "critical")]
        error_traces = [t for t in evidence.traces if t.status in ("error", "timeout")]

        for mode in self.catalog.FAILURE_MODES:
            score = 0
            matched_evidence = []

            # Check metric symptoms
            for metric_symptom in mode["symptoms"]["metrics"]:
                if metric_symptom in anomalous_metrics:
                    score += 3
                    matched_evidence.append(f"metric:{metric_symptom}")
                elif metric_symptom in metric_names:
                    score += 1
                    matched_evidence.append(f"metric:{metric_symptom}(normal)")

            # Check log symptoms
            for log_symptom in mode["symptoms"]["logs"]:
                if log_symptom in log_types:
                    score += 2
                    matched_evidence.append(f"log:{log_symptom}")

            # Check trace symptoms
            if error_traces and "error_traces" in mode["symptoms"].get("traces", []):
                score += 2
                matched_evidence.append("trace:error")

            # Check similar patterns in alert/logs
            alert_lower = alert.lower() if alert else ""
            log_text = " ".join([l.message for l in error_logs]).lower()
            for pattern in mode.get("similar_patterns", []):
                if pattern.lower() in alert_lower or pattern.lower() in log_text:
                    score += 2
                    matched_evidence.append(f"pattern:{pattern}")

            # Topology bonus
            if mode["topology"]["affects_downstream"]:
                downstream = topology.get("downstream", [])
                if downstream:
                    score += 1

            # Only create hypothesis if we have some evidence match
            if score > 0:
                hypothesis = Hypothesis(
                    hypothesis_id=f"{mode['id']}_{service}_{len(hypotheses)}",
                    title=mode["title"],
                    description=mode["description"],
                    category=mode["category"],
                    root_cause=mode["root_cause"],
                    evidence_summary=f"Matched evidence: {', '.join(matched_evidence)} (pattern score: {score})",
                    affected_services=[service],
                    upstream_services=topology.get("upstream", []),
                    downstream_services=topology.get("downstream", []),
                    recommended_actions=mode["actions"].copy(),
                    similar_incidents=[],
                    evidence_references=matched_evidence,
                    metadata={"pattern_score": score, "failure_mode_id": mode["id"]}
                )
                hypotheses.append(hypothesis)

        return hypotheses

    def _generate_topology_hypotheses(
        self,
        evidence: Any,
        topology: Dict[str, Any],
        service: str,
        correlated_alerts: List[Dict[str, Any]]
    ) -> List[Hypothesis]:
        """Generate hypotheses based on service topology and alert correlation."""
        hypotheses = []

        upstream = topology.get("upstream", [])
        downstream = topology.get("downstream", [])

        # Check for correlated alerts in upstream services
        upstream_alerts = []
        for alert_group in correlated_alerts:
            for alert in alert_group.get("alerts", []):
                if alert.get("service") in upstream:
                    upstream_alerts.append(alert)

        if upstream_alerts:
            # Upstream failure causing downstream impact
            affected_upstream = list(set(a["service"] for a in upstream_alerts))
            hypothesis = Hypothesis(
                hypothesis_id=f"upstream_cascade_{service}",
                title="Upstream Service Failure Causing Cascade",
                description=f"Upstream services {affected_upstream} failing, causing cascade to {service}",
                category=HypothesisCategory.DEPENDENCY_FAILURE,
                root_cause=f"Upstream service(s) {', '.join(affected_upstream)} degraded/unavailable",
                evidence_summary=f"Correlated alerts in upstream: {', '.join(affected_upstream)}",
                affected_services=[service],
                upstream_services=affected_upstream,
                downstream_services=downstream,
                recommended_actions=[
                    f"Investigate root cause in upstream service(s): {', '.join(affected_upstream)}",
                    "Implement circuit breaker for upstream calls",
                    "Add fallback responses for degraded upstream",
                    "Scale upstream service capacity"
                ],
                evidence_references=[f"correlated_alert:{a['service']}" for a in upstream_alerts],
                metadata={"type": "topology_cascade", "direction": "upstream_to_downstream"}
            )
            hypotheses.append(hypothesis)

        # Check for correlated alerts in downstream services (reverse cascade)
        downstream_alerts = []
        for alert_group in correlated_alerts:
            for alert in alert_group.get("alerts", []):
                if alert.get("service") in downstream:
                    downstream_alerts.append(alert)

        if downstream_alerts and not upstream_alerts:
            # This service might be causing downstream issues
            affected_downstream = list(set(a["service"] for a in downstream_alerts))
            hypothesis = Hypothesis(
                hypothesis_id=f"downstream_impact_{service}",
                title="This Service Causing Downstream Degradation",
                description=f"{service} issues causing cascade to downstream services: {affected_downstream}",
                category=HypothesisCategory.DEPENDENCY_FAILURE,
                root_cause=f"{service} degraded, causing timeout/errors in downstream consumers",
                evidence_summary=f"Correlated alerts in downstream: {', '.join(affected_downstream)}",
                affected_services=[service] + affected_downstream,
                upstream_services=upstream,
                downstream_services=affected_downstream,
                recommended_actions=[
                    f"Focus investigation on {service} as root cause",
                    "Check if {service} changes caused regression",
                    "Verify downstream circuit breakers are configured",
                    "Consider graceful degradation for downstream"
                ],
                evidence_references=[f"correlated_alert:{a['service']}" for a in downstream_alerts],
                metadata={"type": "topology_cascade", "direction": "downstream_from_service"}
            )
            hypotheses.append(hypothesis)

        # Check for blast radius (multiple services affected)
        all_affected = set()
        for alert_group in correlated_alerts:
            for alert in alert_group.get("alerts", []):
                all_affected.add(alert.get("service"))

        if len(all_affected) > 3:
            hypothesis = Hypothesis(
                hypothesis_id=f"wide_blast_radius_{service}",
                title="Wide Blast Radius - Platform/Infrastructure Issue",
                description=f"Multiple services affected ({len(all_affected)}), suggesting platform/infrastructure root cause",
                category=HypothesisCategory.RESOURCE_EXHAUSTION,
                root_cause="Shared infrastructure issue (node, network, DNS, K8s control plane, cloud provider)",
                evidence_summary=f"Alerts across {len(all_affected)} services: {', '.join(sorted(all_affected))}",
                affected_services=list(all_affected),
                upstream_services=[],
                downstream_services=[],
                recommended_actions=[
                    "Check Kubernetes node health (Ready condition)",
                    "Verify cloud provider status page",
                    "Check CNI/network plugin health",
                    "Check service mesh control plane",
                    "Investigate recent cluster changes"
                ],
                evidence_references=[f"correlated_alert:{s}" for s in all_affected],
                metadata={"type": "blast_radius", "affected_count": len(all_affected)}
            )
            hypotheses.append(hypothesis)

        return hypotheses

    def _generate_historical_hypotheses(
        self,
        similar_incidents: List[Dict[str, Any]],
        evidence: Any,
        service: str
    ) -> List[Hypothesis]:
        """Generate hypotheses based on similar historical incidents."""
        hypotheses = []

        for incident in similar_incidents[:5]:  # Top 5 similar
            # Extract key info from historical incident
            incident_id = incident.get("incident_id", "unknown")
            root_cause = incident.get("root_cause", "")
            historical_service = incident.get("service", "")
            lessons = incident.get("lessons", "")
            actions = incident.get("actions", [])

            # Calculate similarity boost based on evidence overlap
            similarity_boost = 0
            if historical_service == service:
                similarity_boost += 2

            hypothesis = Hypothesis(
                hypothesis_id=f"historical_{incident_id}_{service}",
                title=f"Similar to {incident_id}: {root_cause[:80]}",
                description=f"Historical incident {incident_id} had similar symptoms. Root cause: {root_cause}",
                category=self._infer_category(root_cause),
                root_cause=root_cause,
                evidence_summary=f"Similar to {incident_id} (service: {historical_service}). Lessons: {lessons[:200]}",
                affected_services=[service],
                upstream_services=[],
                downstream_services=[],
                recommended_actions=actions[:5] if actions else [
                    f"Review {incident_id} post-incident report",
                    f"Apply lessons learned: {lessons[:200]}"
                ],
                similar_incidents=[incident],
                evidence_references=[f"historical:{incident_id}"],
                metadata={
                    "type": "historical",
                    "historical_incident_id": incident_id,
                    "similarity_boost": similarity_boost,
                    "historical_service": historical_service
                }
            )
            hypotheses.append(hypothesis)

        return hypotheses

    def _infer_category(self, root_cause: str) -> HypothesisCategory:
        """Infer hypothesis category from root cause text."""
        root_cause_lower = root_cause.lower()

        if any(kw in root_cause_lower for kw in ["deploy", "release", "version", "rollback"]):
            return HypothesisCategory.DEPLOYMENT
        if any(kw in root_cause_lower for kw in ["pool", "memory", "cpu", "thread", "connection", "exhaust", "oom"]):
            return HypothesisCategory.RESOURCE_EXHAUSTION
        if any(kw in root_cause_lower for kw in ["downstream", "upstream", "dependenc", "cascade", "database", "redis", "kafka"]):
            return HypothesisCategory.DEPENDENCY_FAILURE
        if any(kw in root_cause_lower for kw in ["config", "configmap", "secret", "flag", "environment"]):
            return HypothesisCategory.CONFIGURATION
        if any(kw in root_cause_lower for kw in ["bug", "code", "logic", "null", "exception", "defect"]):
            return HypothesisCategory.CODE_DEFECT
        if any(kw in root_cause_lower for kw in ["network", "dns", "connect", "timeout", "unreachable"]):
            return HypothesisCategory.NETWORK
        if any(kw in root_cause_lower for kw in ["data", "corrupt", "migration", "schema"]):
            return HypothesisCategory.DATA_ISSUE
        if any(kw in root_cause_lower for kw in ["auth", "cert", "security", "breach", "permission"]):
            return HypothesisCategory.SECURITY
        if any(kw in root_cause_lower for kw in ["scale", "quota", "limit", "capacity"]):
            return HypothesisCategory.CAPACITY

        return HypothesisCategory.UNKNOWN

    async def _generate_llm_hypotheses(
        self,
        alert: str,
        service: str,
        evidence: Any,
        topology: Dict[str, Any],
        similar_incidents: List[Dict[str, Any]]
    ) -> List[Hypothesis]:
        """Use LLM to generate hypotheses for complex cases."""
        if not self.anthropic_api_key:
            logger.warning("No Anthropic API key, skipping LLM hypothesis generation")
            return []

        try:
            # Build context for LLM
            context = self._build_llm_context(alert, service, evidence, topology, similar_incidents)

            prompt = f"""You are an expert Site Reliability Engineer performing root cause analysis.
Given the following incident context, generate 2-3 plausible root cause hypotheses.

INCIDENT CONTEXT:
{context}

OUTPUT FORMAT (JSON array):
[
  {{
    "title": "Concise hypothesis title",
    "description": "Detailed explanation",
    "category": "deployment|resource_exhaustion|dependency_failure|configuration|code_defect|network|data_issue|security|capacity|unknown",
    "root_cause": "Specific root cause statement",
    "evidence_summary": "Key evidence supporting this hypothesis",
    "recommended_actions": ["action1", "action2", "action3"],
    "confidence": 0.0-1.0
  }}
]

Focus on hypotheses NOT already covered by pattern matching. Think about:
- Complex interaction failures
- Configuration drift
- Recent changes not in deployment history
- Environmental factors (noisy neighbors, clock skew, etc.)"""

            response = await self.client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": self.anthropic_api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json"
                },
                json={
                    "model": self.model,
                    "max_tokens": 2000,
                    "messages": [{"role": "user", "content": prompt}]
                }
            )

            if response.status_code == 200:
                result = response.json()
                content = result["content"][0]["text"]

                # Parse JSON from response
                json_match = re.search(r'\[.*\]', content, re.DOTALL)
                if json_match:
                    llm_hypotheses = json.loads(json_match.group())

                    hypotheses = []
                    for i, h in enumerate(llm_hypotheses):
                        hypothesis = Hypothesis(
                            hypothesis_id=f"llm_{service}_{i}",
                            title=h.get("title", "LLM Hypothesis"),
                            description=h.get("description", ""),
                            category=HypothesisCategory(h.get("category", "unknown")),
                            root_cause=h.get("root_cause", ""),
                            evidence_summary=h.get("evidence_summary", ""),
                            affected_services=[service],
                            upstream_services=topology.get("upstream", []),
                            downstream_services=topology.get("downstream", []),
                            recommended_actions=h.get("recommended_actions", []),
                            similar_incidents=[],
                            evidence_references=["llm_generated"],
                            confidence=h.get("confidence", 0.5),
                            metadata={"type": "llm_generated", "model": self.model}
                        )
                        hypotheses.append(hypothesis)

                    return hypotheses

        except Exception as e:
            logger.warning(f"LLM hypothesis generation failed: {e}")

        return []

    def _build_llm_context(
        self,
        alert: str,
        service: str,
        evidence: Any,
        topology: Dict[str, Any],
        similar_incidents: List[Dict[str, Any]]
    ) -> str:
        """Build context string for LLM prompt."""
        lines = [
            f"Alert: {alert}",
            f"Primary Service: {service}",
            f"Upstream Services: {', '.join(topology.get('upstream', [])) or 'none'}",
            f"Downstream Services: {', '.join(topology.get('downstream', [])) or 'none'}",
            "",
            "ANOMALOUS METRICS:"
        ]

        for m in evidence.metrics:
            if m.is_anomalous:
                lines.append(f"  - {m.metric_name}: {m.value} {m.unit} (threshold: {m.threshold})")

        lines.append("\nERROR LOGS (sample):")
        for l in evidence.logs[:5]:
            if l.severity in ("error", "critical"):
                lines.append(f"  - [{l.severity}] {l.message[:200]}")

        lines.append("\nERROR TRACES (sample):")
        for t in evidence.traces[:3]:
            if t.status in ("error", "timeout"):
                lines.append(f"  - {t.span_name}: {t.duration_ms}ms ({t.status})")

        if similar_incidents:
            lines.append("\nSIMILAR HISTORICAL INCIDENTS:")
            for inc in similar_incidents[:3]:
                lines.append(f"  - {inc.get('incident_id')}: {inc.get('root_cause', '')[:150]}")

        return "\n".join(lines)

    def _deduplicate_hypotheses(self, hypotheses: List[Hypothesis]) -> List[Hypothesis]:
        """Remove duplicate hypotheses based on root cause similarity."""
        seen = set()
        unique = []

        for h in hypotheses:
            # Create signature from root cause + category
            sig = f"{h.category.value}:{h.root_cause[:100].lower()}"
            # Normalize
            sig = re.sub(r'\s+', ' ', sig)

            if sig not in seen:
                seen.add(sig)
                unique.append(h)

        return unique

    async def close(self):
        """Close HTTP client."""
        await self.client.aclose()


# Standalone test function
async def test_hypothesis_engine():
    """Test hypothesis engine with mock evidence."""
    from evidence_collector import CollectedEvidence, MetricsEvidence, LogEvidence
    from datetime import datetime

    # Create mock evidence
    evidence = CollectedEvidence()
    evidence.metrics = [
        MetricsEvidence(
            service="java-service",
            timestamp=datetime.utcnow(),
            metric_name="connection_pool_pending",
            value=15,
            threshold=1,
            unit="count",
            promql_query="test"
        ),
        MetricsEvidence(
            service="java-service",
            timestamp=datetime.utcnow(),
            metric_name="error_rate",
            value=0.12,
            threshold=0.05,
            unit="ratio",
            promql_query="test"
        )
    ]
    evidence.logs = [
        LogEvidence(
            service="java-service",
            timestamp=datetime.utcnow(),
            metric_name="log_connection_errors",
            value=1,
            threshold=0,
            severity="error",
            message="HikariCP - Connection not available, timeout after 30000ms"
        )
    ]

    topology = {
        "upstream": [],
        "downstream": ["python-service"]
    }

    engine = HypothesisEngine(
        knowledge_base_url="http://chroma:8000",
        anthropic_api_key=None
    )

    hypotheses = await engine.generate(
        alert="java-service error rate > 5%",
        service="java-service",
        evidence=evidence,
        topology=topology,
        similar_incidents=[],
        correlated_alerts=[]
    )

    for h in hypotheses:
        print(f"\n{h.title} ({h.category.value})")
        print(f"  Root cause: {h.root_cause}")
        print(f"  Evidence: {h.evidence_summary}")
        print(f"  Actions: {h.recommended_actions}")
        print(f"  Pattern score: {h.metadata.get('pattern_score', 'N/A')}")

    await engine.close()


if __name__ == "__main__":
    import asyncio
    logging.basicConfig(level=logging.INFO)
    asyncio.run(test_hypothesis_engine())