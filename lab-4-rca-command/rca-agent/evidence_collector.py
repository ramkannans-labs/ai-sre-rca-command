"""
Evidence Collector Module - Queries MCP Server for Telemetry Evidence

This module handles all evidence collection from the MCP (Model Context Protocol) server,
which provides a unified interface to Prometheus (metrics), Loki (logs), Tempo (traces),
Knowledge Graph (topology), and Correlation Engine (alert groups).

Architecture:
┌─────────────────────────────────────────────────────────────────────┐
│                    EVIDENCE COLLECTOR                               │
├─────────────────────────────────────────────────────────────────────┤
│  collect_all()                                                      │
│    ├─▶ collect_metrics()     ──▶ MCP ──▶ Prometheus (PromQL)       │
│    ├─▶ collect_logs()        ──▶ MCP ──▶ Loki (LogQL)              │
│    ├─▶ collect_traces()      ──▶ MCP ──▶ Tempo (TraceQL)           │
│    ├─▶ collect_topology()    ──▶ MCP ──▶ Knowledge Graph           │
│    └─▶ validate_hypothesis() ──▶ MCP ──▶ Targeted queries          │
└─────────────────────────────────────────────────────────────────────┘
"""

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Union

import httpx
from pydantic import BaseModel

logger = logging.getLogger(__name__)


@dataclass
class TelemetryEvidence:
    """Base class for telemetry evidence."""
    source: str  # "metrics", "logs", "traces", "topology"
    service: str
    timestamp: datetime
    metric_name: str
    value: Union[float, str, Dict]
    threshold: Optional[float] = None
    unit: str = ""
    labels: Dict[str, str] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_anomalous(self) -> bool:
        """Check if value exceeds threshold."""
        if self.threshold is None:
            return False
        if isinstance(self.value, (int, float)):
            return self.value > self.threshold
        return False


@dataclass
class MetricsEvidence(TelemetryEvidence):
    """Metrics-specific evidence."""
    source: str = "metrics"
    promql_query: str = ""
    time_range: str = "30m"


@dataclass
class LogEvidence(TelemetryEvidence):
    """Logs-specific evidence."""
    source: str = "logs"
    logql_query: str = ""
    severity: str = "info"  # debug, info, warn, error, critical
    message: str = ""


@dataclass
class TraceEvidence(TelemetryEvidence):
    """Traces-specific evidence."""
    source: str = "traces"
    traceql_query: str = ""
    span_name: str = ""
    duration_ms: float = 0.0
    status: str = "ok"  # ok, error, timeout


@dataclass
class CollectedEvidence:
    """Container for all collected evidence."""
    metrics: List[MetricsEvidence] = field(default_factory=list)
    logs: List[LogEvidence] = field(default_factory=list)
    traces: List[TraceEvidence] = field(default_factory=list)
    topology: Dict[str, Any] = field(default_factory=dict)
    correlated_alerts: List[Dict[str, Any]] = field(default_factory=list)


class EvidenceCollector:
    """
    Collects evidence from MCP Server for RCA investigations.

    The MCP Server provides a unified API:
    - GET /api/v1/metrics/query?query=<promql>&service=<svc>&range=<duration>
    - GET /api/v1/logs/query?query=<logql>&service=<svc>&range=<duration>
    - GET /api/v1/traces/query?query=<traceql>&service=<svc>&range=<duration>
    - GET /api/v1/topology/service/<service>
    - POST /api/v1/validate-hypothesis
    """

    # Standard PromQL queries for common failure modes
    METRICS_QUERIES = {
        "error_rate": 'sum(rate(http_requests_total{service="{service}",status=~"5.."}[5m])) by (service) / sum(rate(http_requests_total{service="{service}"}[5m])) by (service)',
        "latency_p50": 'histogram_quantile(0.50, sum(rate(http_request_duration_seconds_bucket{service="{service}"}[5m])) by (le, service))',
        "latency_p95": 'histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket{service="{service}"}[5m])) by (le, service))',
        "latency_p99": 'histogram_quantile(0.99, sum(rate(http_request_duration_seconds_bucket{service="{service}"}[5m])) by (le, service))',
        "cpu_usage": 'sum(rate(container_cpu_usage_seconds_total{service="{service}"}[5m])) by (service) / sum(container_spec_cpu_quota{service="{service}"}/container_spec_cpu_period{service="{service}"}) by (service) * 100',
        "memory_usage": '(sum(container_memory_working_set_bytes{service="{service}"}) by (service) / sum(container_spec_memory_limit_bytes{service="{service}"}) by (service)) * 100',
        "connection_pool_active": 'sum(hikaricp_connections_active{service="{service}"}) by (service)',
        "connection_pool_idle": 'sum(hikaricp_connections_idle{service="{service}"}) by (service)',
        "connection_pool_pending": 'sum(hikaricp_connections_pending{service="{service}"}) by (service)',
        "thread_pool_active": 'sum(jvm_threads_active{service="{service}"}) by (service)',
        "thread_pool_queue": 'sum(jvm_threads_queue_size{service="{service}"}) by (service)',
        "gc_pause": 'sum(rate(jvm_gc_pause_seconds_sum{service="{service}"}[5m])) by (service) / sum(rate(jvm_gc_pause_seconds_count{service="{service}"}[5m])) by (service)',
        "request_rate": 'sum(rate(http_requests_total{service="{service}"}[5m])) by (service)',
        "kafka_consumer_lag": 'sum(kafka_consumergroup_lag{service="{service}"}) by (service, topic)',
        "redis_connections": 'sum(redis_connected_clients{service="{service}"}) by (service)',
        "db_connections": 'sum(pg_stat_activity_count{service="{service}"}) by (service)',
    }

    # Standard LogQL queries for common error patterns
    LOGS_QUERIES = {
        "errors": '{service="{service}"} |= "error" |~ "(?i)(error|exception|fail|timeout)"',
        "warnings": '{service="{service}"} |= "warn" |~ "(?i)(warn|deprecat)"',
        "connection_errors": '{service="{service}"} |~ "(?i)(connection.*(refused|timeout|pool|exhaust|leak))"',
        "memory_errors": '{service="{service}"} |~ "(?i)(oom|out of memory|heap|gc overhead)"',
        "database_errors": '{service="{service}"} |~ "(?i)(sql|database|postgres|jdbc|hikari).*(error|exception|timeout)"',
        "thread_errors": '{service="{service}"} |~ "(?i)(thread|pool|queue).*(exhaust|full|reject)"',
        "deployment_events": '{service="{service}",container=~".*"} |~ "(?i)(start|deploy|rollback|health)"',
    }

    # Standard TraceQL queries for latency analysis
    TRACES_QUERIES = {
        "slow_traces": '{service="{service}"} duration > 1s',
        "error_traces": '{service="{service}"} status = error',
        "timeout_traces": '{service="{service}"} status = timeout',
        "span_errors": '{service="{service}"} .span[status = error]',
    }

    def __init__(
        self,
        mcp_url: str,
        knowledge_graph_url: str,
        correlation_engine_url: str,
        timeout: int = 30
    ):
        self.mcp_url = mcp_url.rstrip("/")
        self.knowledge_graph_url = knowledge_graph_url.rstrip("/")
        self.correlation_engine_url = correlation_engine_url.rstrip("/")
        self.timeout = timeout
        self.client = httpx.AsyncClient(timeout=timeout)

        logger.info(f"Evidence Collector initialized with MCP: {self.mcp_url}")

    async def collect_all(
        self,
        service: str,
        affected_services: List[str],
        time_range_minutes: int = 30,
        correlated_alerts: Optional[List[Dict]] = None
    ) -> CollectedEvidence:
        """
        Collect all evidence types in parallel for maximum speed.

        This is the main entry point for evidence collection during investigation.
        """
        services = [service] + affected_services
        time_range = f"{time_range_minutes}m"

        # Collect in parallel for all affected services
        tasks = []
        for svc in services:
            tasks.append(self._collect_for_service(svc, time_range))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Merge results
        evidence = CollectedEvidence()
        evidence.correlated_alerts = correlated_alerts or []

        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.warning(f"Evidence collection failed for {services[i]}: {result}")
                continue

            svc_evidence = result
            evidence.metrics.extend(svc_evidence.metrics)
            evidence.logs.extend(svc_evidence.logs)
            evidence.traces.extend(svc_evidence.traces)
            evidence.topology.update(svc_evidence.topology)

        logger.info(
            f"Collected evidence: {len(evidence.metrics)} metrics, "
            f"{len(evidence.logs)} logs, {len(evidence.traces)} traces, "
            f"topology for {len(evidence.topology)} services"
        )

        return evidence

    async def _collect_for_service(
        self,
        service: str,
        time_range: str
    ) -> CollectedEvidence:
        """Collect all evidence types for a single service in parallel."""

        # Run all collection methods in parallel
        metrics_task = self.collect_metrics(service, time_range)
        logs_task = self.collect_logs(service, time_range)
        traces_task = self.collect_traces(service, time_range)
        topology_task = self.collect_topology(service)

        metrics, logs, traces, topology = await asyncio.gather(
            metrics_task, logs_task, traces_task, topology_task,
            return_exceptions=True
        )

        evidence = CollectedEvidence()

        if not isinstance(metrics, Exception):
            evidence.metrics = metrics
        else:
            logger.warning(f"Metrics collection failed for {service}: {metrics}")

        if not isinstance(logs, Exception):
            evidence.logs = logs
        else:
            logger.warning(f"Logs collection failed for {service}: {logs}")

        if not isinstance(traces, Exception):
            evidence.traces = traces
        else:
            logger.warning(f"Traces collection failed for {service}: {traces}")

        if not isinstance(topology, Exception):
            evidence.topology = topology
        else:
            logger.warning(f"Topology collection failed for {service}: {topology}")

        return evidence

    async def collect_metrics(self, service: str, time_range: str) -> List[MetricsEvidence]:
        """Collect metrics evidence from Prometheus via MCP."""
        evidence = []

        for metric_name, query_template in self.METRICS_QUERIES.items():
            try:
                query = query_template.format(service=service)

                response = await self.client.get(
                    f"{self.mcp_url}/api/v1/metrics/query",
                    params={
                        "query": query,
                        "service": service,
                        "range": time_range,
                        "step": "15s"
                    }
                )

                if response.status_code != 200:
                    continue

                data = response.json()
                results = data.get("data", {}).get("result", [])

                for result in results:
                    value = self._extract_metric_value(result)
                    if value is not None:
                        threshold = self._get_threshold(metric_name)
                        evidence.append(MetricsEvidence(
                            service=service,
                            timestamp=datetime.utcnow(),
                            metric_name=metric_name,
                            value=value,
                            threshold=threshold,
                            unit=self._get_unit(metric_name),
                            labels=result.get("metric", {}),
                            promql_query=query,
                            time_range=time_range,
                            metadata={"raw_result": result}
                        ))

            except Exception as e:
                logger.debug(f"Metric query failed for {metric_name}: {e}")

        return evidence

    async def collect_logs(self, service: str, time_range: str) -> List[LogEvidence]:
        """Collect log evidence from Loki via MCP."""
        evidence = []

        for log_type, query_template in self.LOGS_QUERIES.items():
            try:
                query = query_template.format(service=service)

                response = await self.client.get(
                    f"{self.mcp_url}/api/v1/logs/query",
                    params={
                        "query": query,
                        "service": service,
                        "range": time_range,
                        "limit": 100
                    }
                )

                if response.status_code != 200:
                    continue

                data = response.json()
                entries = data.get("data", {}).get("result", [])

                for entry in entries:
                    # Loki returns: [timestamp, line, labels]
                    if isinstance(entry, list) and len(entry) >= 2:
                        timestamp_str, line = entry[0], entry[1]
                        severity = self._extract_log_severity(line)

                        evidence.append(LogEvidence(
                            service=service,
                            timestamp=datetime.utcnow(),
                            metric_name=f"log_{log_type}",
                            value=1,
                            threshold=0,
                            severity=severity,
                            message=line[:500],
                            logql_query=query,
                            metadata={"raw_timestamp": timestamp_str, "labels": entry[2] if len(entry) > 2 else {}}
                        ))

            except Exception as e:
                logger.debug(f"Log query failed for {log_type}: {e}")

        return evidence

    async def collect_traces(self, service: str, time_range: str) -> List[TraceEvidence]:
        """Collect trace evidence from Tempo via MCP."""
        evidence = []

        for trace_type, query_template in self.TRACES_QUERIES.items():
            try:
                query = query_template.format(service=service)

                response = await self.client.get(
                    f"{self.mcp_url}/api/v1/traces/query",
                    params={
                        "query": query,
                        "service": service,
                        "range": time_range,
                        "limit": 50
                    }
                )

                if response.status_code != 200:
                    continue

                data = response.json()
                traces = data.get("data", {}).get("traces", [])

                for trace in traces:
                    duration_ms = trace.get("duration_ms", 0)
                    status = trace.get("status", "ok")
                    span_name = trace.get("root_span", "unknown")

                    evidence.append(TraceEvidence(
                        service=service,
                        timestamp=datetime.utcnow(),
                        metric_name=f"trace_{trace_type}",
                        value=duration_ms,
                        threshold=1000 if trace_type == "slow_traces" else 0,
                        unit="ms",
                        span_name=span_name,
                        duration_ms=duration_ms,
                        status=status,
                        traceql_query=query,
                        metadata={"trace_id": trace.get("trace_id"), "spans": trace.get("spans", [])}
                    ))

            except Exception as e:
                logger.debug(f"Trace query failed for {trace_type}: {e}")

        return evidence

    async def collect_topology(self, service: str) -> Dict[str, Any]:
        """Collect service topology from Knowledge Graph."""
        try:
            response = await self.client.get(
                f"{self.knowledge_graph_url}/api/v1/topology/service/{service}"
            )

            if response.status_code == 200:
                return response.json()
        except Exception as e:
            logger.warning(f"Topology collection failed: {e}")

        return {"service": service, "upstream": [], "downstream": [], "error": "Collection failed"}

    async def validate_hypothesis(
        self,
        hypothesis: Any,
        service: str,
        time_range_minutes: int = 30
    ) -> Dict[str, Any]:
        """
        Validate a hypothesis with targeted MCP queries.

        Sends specific queries to confirm/refute the hypothesis.
        """
        hypothesis_text = getattr(hypothesis, 'title', str(hypothesis))
        hypothesis_id = getattr(hypothesis, 'hypothesis_id', 'unknown')

        logger.info(f"Validating hypothesis: {hypothesis_text}")

        try:
            response = await self.client.post(
                f"{self.mcp_url}/api/v1/validate-hypothesis",
                json={
                    "hypothesis": hypothesis_text,
                    "hypothesis_id": hypothesis_id,
                    "service": service,
                    "time_range": f"{time_range_minutes}m"
                }
            )

            if response.status_code == 200:
                return response.json()

            return {"validated": False, "error": f"HTTP {response.status_code}"}

        except Exception as e:
            logger.warning(f"Hypothesis validation failed: {e}")
            return {"validated": False, "error": str(e)}

    def _extract_metric_value(self, result: Dict) -> Optional[float]:
        """Extract numeric value from Prometheus query result."""
        try:
            value = result.get("value", [None, None])[1]
            if value is not None:
                return float(value)
        except (ValueError, TypeError, IndexError):
            pass
        return None

    def _get_threshold(self, metric_name: str) -> Optional[float]:
        """Get alerting threshold for metric."""
        thresholds = {
            "error_rate": 0.05,  # 5%
            "latency_p99": 1.0,  # 1 second
            "latency_p95": 0.5,  # 500ms
            "cpu_usage": 80,  # 80%
            "memory_usage": 85,  # 85%
            "connection_pool_active": 80,  # 80% of pool
            "connection_pool_pending": 1,  # any pending
            "thread_pool_queue": 10,  # queue backing up
            "gc_pause": 0.5,  # 500ms
            "kafka_consumer_lag": 1000,  # 1000 messages
            "redis_connections": 8000,  # near limit
            "db_connections": 80,  # 80% of max
        }
        return thresholds.get(metric_name)

    def _get_unit(self, metric_name: str) -> str:
        """Get unit for metric."""
        units = {
            "error_rate": "ratio",
            "latency_p50": "seconds",
            "latency_p95": "seconds",
            "latency_p99": "seconds",
            "cpu_usage": "percent",
            "memory_usage": "percent",
            "connection_pool_active": "count",
            "connection_pool_idle": "count",
            "connection_pool_pending": "count",
            "thread_pool_active": "count",
            "thread_pool_queue": "count",
            "gc_pause": "seconds",
            "request_rate": "req/s",
            "kafka_consumer_lag": "messages",
            "redis_connections": "count",
            "db_connections": "count",
        }
        return units.get(metric_name, "")

    def _extract_log_severity(self, line: str) -> str:
        """Extract severity from log line."""
        line_lower = line.lower()
        if any(kw in line_lower for kw in ["critical", "fatal", "panic"]):
            return "critical"
        if any(kw in line_lower for kw in ["error", "exception", "fail"]):
            return "error"
        if any(kw in line_lower for kw in ["warn", "deprecat"]):
            return "warn"
        return "info"

    async def close(self):
        """Close HTTP client."""
        await self.client.aclose()


# Standalone validation functions for testing
async def test_evidence_collection():
    """Test evidence collector with mock MCP."""
    # This would be used for local testing
    pass


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Evidence Collector module - import to use")