"""
AI RCA Agent - Main Orchestration Module

This module coordinates the automated root cause analysis workflow:
1. Evidence Collection - Queries telemetry via MCP
2. Hypothesis Generation - Uses topology and historical patterns
3. Confidence Scoring - Weights evidence to rank hypotheses
4. Report Generation - Structured RCA output for Incident Commander

Architecture:
┌─────────────┐     ┌──────────────────┐     ┌──────────────────┐
│   Alert     │────▶│  Evidence        │────▶│  Hypothesis      │
│  (input)    │     │  Collector       │     │  Engine          │
└─────────────┘     └──────────────────┘     └────────┬─────────┘
                                                      │
                        ┌──────────────────┐          │
                        │  Confidence      │◀─────────┘
                        │  Scorer          │
                        └────────┬─────────┘
                                 │
                                 ▼
                        ┌──────────────────┐
                        │  RCA Report      │
                        │  (output)        │
                        └──────────────────┘
"""

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from enum import Enum

import httpx
from pydantic import BaseModel, Field

from evidence_collector import EvidenceCollector, TelemetryEvidence
from hypothesis_engine import HypothesisEngine, Hypothesis
from confidence_scorer import ConfidenceScorer, ScoredHypothesis

logger = logging.getLogger(__name__)


class Severity(str, Enum):
    """Incident severity levels."""
    SEV1 = "SEV-1"
    SEV2 = "SEV-2"
    SEV3 = "SEV-3"


class IncidentStatus(str, Enum):
    """Investigation status."""
    PENDING = "pending"
    COLLECTING_EVIDENCE = "collecting_evidence"
    GENERATING_HYPOTHESES = "generating_hypotheses"
    SCORING = "scoring"
    VALIDATING = "validating"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class InvestigationRequest:
    """Input for an RCA investigation."""
    incident_id: str
    alert: str
    service: str
    severity: Severity
    affected_services: List[str] = field(default_factory=list)
    time_range_minutes: int = 30
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RCAReport:
    """Structured RCA report output."""
    incident_id: str
    timestamp: datetime
    status: IncidentStatus
    alert: str
    service: str
    severity: Severity

    # Evidence
    metrics_evidence: List[TelemetryEvidence] = field(default_factory=list)
    log_evidence: List[TelemetryEvidence] = field(default_factory=list)
    trace_evidence: List[TelemetryEvidence] = field(default_factory=list)
    topology_evidence: Dict[str, Any] = field(default_factory=dict)

    # Hypotheses
    hypotheses: List[ScoredHypothesis] = field(default_factory=list)
    top_hypothesis: Optional[ScoredHypothesis] = None

    # Validation
    validation_results: Dict[str, Any] = field(default_factory=dict)

    # Recommendations
    recommended_actions: List[str] = field(default_factory=list)
    runbook_references: List[str] = field(default_factory=list)

    # Metadata
    investigation_duration_seconds: float = 0.0
    evidence_collected_count: int = 0
    error: Optional[str] = None


class RCAAgent:
    """
    Main RCA Agent orchestrating the investigation workflow.

    The agent integrates with:
    - MCP Server for unified telemetry access (metrics, logs, traces)
    - Knowledge Base (ChromaDB) for historical incident similarity
    - Knowledge Graph (Week 2) for service topology and blast radius
    """

    def __init__(
        self,
        mcp_url: str,
        knowledge_base_url: str,
        knowledge_graph_url: str,
        correlation_engine_url: str,
        anthropic_api_key: Optional[str] = None,
        model: str = "claude-3-5-sonnet-20241022",
        timeout: int = 30
    ):
        self.mcp_url = mcp_url.rstrip("/")
        self.knowledge_base_url = knowledge_base_url.rstrip("/")
        self.knowledge_graph_url = knowledge_graph_url.rstrip("/")
        self.correlation_engine_url = correlation_engine_url.rstrip("/")
        self.anthropic_api_key = anthropic_api_key or os.getenv("ANTHROPIC_API_KEY")
        self.model = model
        self.timeout = timeout

        # Initialize sub-components
        self.evidence_collector = EvidenceCollector(
            mcp_url=self.mcp_url,
            knowledge_graph_url=self.knowledge_graph_url,
            correlation_engine_url=self.correlation_engine_url,
            timeout=timeout
        )
        self.hypothesis_engine = HypothesisEngine(
            knowledge_base_url=self.knowledge_base_url,
            anthropic_api_key=self.anthropic_api_key,
            model=self.model
        )
        self.confidence_scorer = ConfidenceScorer()

        # HTTP client for external calls
        self.client = httpx.AsyncClient(timeout=timeout)

        logger.info(f"RCA Agent initialized with MCP: {self.mcp_url}, KB: {self.knowledge_base_url}")

    async def investigate(self, request: InvestigationRequest) -> RCAReport:
        """
        Execute full RCA investigation workflow.

        Flow:
        1. Get correlated alerts from correlation engine
        2. Collect evidence (metrics, logs, traces, topology) in parallel
        3. Search knowledge base for similar historical incidents
        4. Generate hypotheses using evidence + topology + history
        5. Score hypotheses with confidence weights
        6. Validate top hypotheses with targeted queries
        7. Generate structured RCA report
        """
        start_time = time.time()
        report = RCAReport(
            incident_id=request.incident_id,
            timestamp=datetime.utcnow(),
            status=IncidentStatus.PENDING,
            alert=request.alert,
            service=request.service,
            severity=request.severity,
        )

        try:
            # Step 1: Get correlated alerts
            logger.info(f"[{request.incident_id}] Fetching correlated alerts")
            correlated_alerts = await self._get_correlated_alerts(request)
            report.metadata["correlated_alerts"] = correlated_alerts

            # Step 2: Collect evidence in parallel
            report.status = IncidentStatus.COLLECTING_EVIDENCE
            logger.info(f"[{request.incident_id}] Collecting evidence")
            evidence = await self.evidence_collector.collect_all(
                service=request.service,
                affected_services=request.affected_services,
                time_range_minutes=request.time_range_minutes,
                correlated_alerts=correlated_alerts
            )

            report.metrics_evidence = evidence.metrics
            report.log_evidence = evidence.logs
            report.trace_evidence = evidence.traces
            report.topology_evidence = evidence.topology
            report.evidence_collected_count = (
                len(evidence.metrics) + len(evidence.logs) + len(evidence.traces)
            )

            # Step 3: Search knowledge base for similar incidents
            logger.info(f"[{request.incident_id}] Searching knowledge base")
            similar_incidents = await self._search_knowledge_base(request, evidence)
            report.metadata["similar_incidents"] = similar_incidents

            # Step 4: Generate hypotheses
            report.status = IncidentStatus.GENERATING_HYPOTHESES
            logger.info(f"[{request.incident_id}] Generating hypotheses")
            hypotheses = await self.hypothesis_engine.generate(
                alert=request.alert,
                service=request.service,
                evidence=evidence,
                topology=evidence.topology,
                similar_incidents=similar_incidents,
                correlated_alerts=correlated_alerts
            )

            # Step 5: Score hypotheses
            report.status = IncidentStatus.SCORING
            logger.info(f"[{request.incident_id}] Scoring hypotheses")
            scored_hypotheses = self.confidence_scorer.score_hypotheses(
                hypotheses=hypotheses,
                evidence=evidence,
                similar_incidents=similar_incidents
            )
            report.hypotheses = scored_hypotheses
            report.top_hypothesis = scored_hypotheses[0] if scored_hypotheses else None

            # Step 6: Validate top hypotheses
            report.status = IncidentStatus.VALIDATING
            logger.info(f"[{request.incident_id}] Validating top hypotheses")
            validation_results = await self._validate_hypotheses(
                request, evidence, scored_hypotheses[:3]  # Top 3
            )
            report.validation_results = validation_results

            # Step 7: Generate recommendations
            report.recommended_actions = self._generate_recommendations(
                report.top_hypothesis, evidence, similar_incidents
            )
            report.runbook_references = self._get_runbook_references(report.top_hypothesis)

            report.status = IncidentStatus.COMPLETED
            report.investigation_duration_seconds = time.time() - start_time

            logger.info(
                f"[{request.incident_id}] Investigation completed in "
                f"{report.investigation_duration_seconds:.1f}s. "
                f"Top hypothesis: {report.top_hypothesis.title if report.top_hypothesis else 'None'} "
                f"(confidence: {report.top_hypothesis.confidence if report.top_hypothesis else 0:.1%})"
            )

        except Exception as e:
            logger.exception(f"[{request.incident_id}] Investigation failed")
            report.status = IncidentStatus.FAILED
            report.error = str(e)
            report.investigation_duration_seconds = time.time() - start_time

        return report

    async def _get_correlated_alerts(self, request: InvestigationRequest) -> List[Dict[str, Any]]:
        """Fetch pre-correlated alert groups from correlation engine."""
        try:
            response = await self.client.get(
                f"{self.correlation_engine_url}/api/v1/alerts/correlated",
                params={
                    "service": request.service,
                    "time_range": f"{request.time_range_minutes}m",
                    "severity": request.severity.value
                }
            )
            if response.status_code == 200:
                return response.json().get("alert_groups", [])
        except Exception as e:
            logger.warning(f"Failed to fetch correlated alerts: {e}")
        return []

    async def _search_knowledge_base(
        self,
        request: InvestigationRequest,
        evidence: Any
    ) -> List[Dict[str, Any]]:
        """Search knowledge base for similar historical incidents."""
        try:
            # Build query from alert + key symptoms
            symptoms = self._extract_symptoms(evidence)
            query = f"{request.alert} {' '.join(symptoms)}"

            response = await self.client.post(
                f"{self.knowledge_base_url}/api/v1/search",
                json={
                    "query": query,
                    "k": 5,
                    "filters": {
                        "service": request.service,
                        "severity": request.severity.value
                    }
                }
            )
            if response.status_code == 200:
                return response.json().get("results", [])
        except Exception as e:
            logger.warning(f"Knowledge base search failed: {e}")
        return []

    def _extract_symptoms(self, evidence: Any) -> List[str]:
        """Extract key symptoms from evidence for KB search."""
        symptoms = []
        for m in evidence.metrics:
            if m.value > m.threshold:
                symptoms.append(f"{m.metric_name}:{m.value}")
        for l in evidence.logs:
            if l.severity in ("error", "critical"):
                symptoms.append(l.message[:100])
        return symptoms[:10]

    async def _validate_hypotheses(
        self,
        request: InvestigationRequest,
        evidence: Any,
        hypotheses: List[ScoredHypothesis]
    ) -> Dict[str, Any]:
        """Validate top hypotheses with targeted MCP queries."""
        results = {}
        for hyp in hypotheses:
            try:
                validation = await self.evidence_collector.validate_hypothesis(
                    hypothesis=hyp,
                    service=request.service,
                    time_range_minutes=request.time_range_minutes
                )
                results[hyp.hypothesis_id] = validation
            except Exception as e:
                logger.warning(f"Validation failed for {hyp.hypothesis_id}: {e}")
                results[hyp.hypothesis_id] = {"validated": False, "error": str(e)}
        return results

    def _generate_recommendations(
        self,
        top_hypothesis: Optional[ScoredHypothesis],
        evidence: Any,
        similar_incidents: List[Dict]
    ) -> List[str]:
        """Generate actionable recommendations based on investigation."""
        recommendations = []

        if top_hypothesis:
            # Add hypothesis-specific actions
            recommendations.extend(top_hypothesis.recommended_actions)

            # Add evidence-based actions
            if any("connection pool" in str(e).lower() for e in evidence.metrics):
                recommendations.append("Check and tune connection pool configuration (maxPoolSize, timeouts)")
            if any("memory" in str(e).lower() for e in evidence.metrics):
                recommendations.append("Investigate memory leak; check heap dumps and GC logs")
            if any("cpu" in str(e).lower() for e in evidence.metrics):
                recommendations.append("Profile CPU hotspots; check for infinite loops or bad queries")

        # Add historical lessons
        for incident in similar_incidents[:2]:
            if "lessons" in incident:
                recommendations.append(f"Lesson from {incident.get('incident_id')}: {incident['lessons'][:200]}")

        # Deduplicate while preserving order
        seen = set()
        unique = []
        for r in recommendations:
            if r not in seen:
                seen.add(r)
                unique.append(r)

        return unique[:10]  # Limit to top 10

    def _get_runbook_references(self, top_hypothesis: Optional[ScoredHypothesis]) -> List[str]:
        """Get relevant runbook references for the top hypothesis."""
        if not top_hypothesis:
            return []

        runbooks = []
        hypothesis_lower = top_hypothesis.title.lower()

        runbook_map = {
            "connection pool": "java-service-connection-pool-exhaustion",
            "memory leak": "java-service-memory-leak",
            "cpu saturation": "java-service-high-cpu",
            "thread pool": "python-service-thread-pool-exhaustion",
            "database": "database-connection-issues",
            "kafka": "kafka-consumer-lag",
            "redis": "redis-connection-errors",
            "timeout": "service-timeout-configuration",
            "circuit breaker": "circuit-breaker-tripped",
        }

        for keyword, runbook in runbook_map.items():
            if keyword in hypothesis_lower:
                runbooks.append(runbook)

        return runbooks[:3]

    async def verify_recovery(
        self,
        incident_id: str,
        services: List[str],
        expected_duration_seconds: int = 300
    ) -> Dict[str, Any]:
        """Verify services have recovered after mitigation."""
        results = {}
        for service in services:
            try:
                # Query MCP for current health
                response = await self.client.get(
                    f"{self.mcp_url}/api/v1/health/{service}",
                    params={"window": f"{expected_duration_seconds}s"}
                )
                if response.status_code == 200:
                    health = response.json()
                    results[service] = {
                        "healthy": health.get("error_rate", 1) < 0.01,
                        "error_rate": health.get("error_rate"),
                        "latency_p99": health.get("latency_p99"),
                        "details": health
                    }
                else:
                    results[service] = {"healthy": False, "error": "Health check failed"}
            except Exception as e:
                results[service] = {"healthy": False, "error": str(e)}

        all_healthy = all(r.get("healthy", False) for r in results.values())
        return {"all_healthy": all_healthy, "services": results}

    async def close(self):
        """Cleanup resources."""
        await self.client.aclose()
        await self.evidence_collector.close()


# CLI Entry Point
async def main():
    import argparse

    parser = argparse.ArgumentParser(description="RCA Agent CLI")
    parser.add_argument("--incident-id", required=True, help="Incident ID")
    parser.add_argument("--alert", required=True, help="Alert description")
    parser.add_argument("--service", required=True, help="Primary affected service")
    parser.add_argument("--severity", choices=["SEV-1", "SEV-2", "SEV-3"], default="SEV-2")
    parser.add_argument("--mcp-url", default=os.getenv("MCP_URL", "http://mcp-server:8082"))
    parser.add_argument("--kb-url", default=os.getenv("KNOWLEDGE_BASE_URL", "http://chroma:8000"))
    parser.add_argument("--kg-url", default=os.getenv("KNOWLEDGE_GRAPH_URL", "http://knowledge-graph:8083"))
    parser.add_argument("--ce-url", default=os.getenv("CORRELATION_ENGINE_URL", "http://correlation-engine:8084"))
    parser.add_argument("--output", help="Output file for JSON report")

    args = parser.parse_args()

    agent = RCAAgent(
        mcp_url=args.mcp_url,
        knowledge_base_url=args.kb_url,
        knowledge_graph_url=args.kg_url,
        correlation_engine_url=args.ce_url
    )

    request = InvestigationRequest(
        incident_id=args.incident_id,
        alert=args.alert,
        service=args.service,
        severity=Severity(args.severity)
    )

    report = await agent.investigate(request)

    # Output report
    output = {
        "incident_id": report.incident_id,
        "timestamp": report.timestamp.isoformat(),
        "status": report.status.value,
        "alert": report.alert,
        "service": report.service,
        "severity": report.severity.value,
        "investigation_duration_seconds": report.investigation_duration_seconds,
        "evidence_collected": report.evidence_collected_count,
        "top_hypothesis": {
            "title": report.top_hypothesis.title if report.top_hypothesis else None,
            "confidence": report.top_hypothesis.confidence if report.top_hypothesis else 0,
            "root_cause": report.top_hypothesis.root_cause if report.top_hypothesis else None,
            "evidence_summary": report.top_hypothesis.evidence_summary if report.top_hypothesis else None
        } if report.top_hypothesis else None,
        "all_hypotheses": [
            {
                "title": h.title,
                "confidence": h.confidence,
                "root_cause": h.root_cause,
                "category": h.category
            } for h in report.hypotheses
        ],
        "recommended_actions": report.recommended_actions,
        "runbook_references": report.runbook_references,
        "validation_results": report.validation_results,
        "error": report.error
    }

    if args.output:
        with open(args.output, "w") as f:
            json.dump(output, f, indent=2)
    else:
        print(json.dumps(output, indent=2))

    await agent.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())