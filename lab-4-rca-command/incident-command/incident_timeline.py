"""
Incident Timeline Manager
=========================
Tracks all events, decisions, actions, and communications during an incident.
Provides structured timeline for post-incident analysis and reporting.
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Set
from datetime import datetime, timedelta
from collections import defaultdict
import json
import uuid
import logging

logger = logging.getLogger(__name__)


class TimelineEventType(Enum):
    """Types of events in the incident timeline."""
    # Incident lifecycle
    INCIDENT_DETECTED = "incident_detected"
    INCIDENT_DECLARED = "incident_declared"
    SEVERITY_CHANGED = "severity_changed"
    STATUS_CHANGED = "status_changed"
    INCIDENT_RESOLVED = "incident_resolved"
    INCIDENT_CLOSED = "incident_closed"

    # Role management
    ROLE_ASSIGNED = "role_assigned"
    ROLE_RELIEVED = "role_relieved"
    ROLE_HANDOFF = "role_handoff"

    # Technical actions
    INVESTIGATION_STARTED = "investigation_started"
    HYPOTHESIS_PROPOSED = "hypothesis_proposed"
    HYPOTHESIS_VALIDATED = "hypothesis_validated"
    HYPOTHESIS_REJECTED = "hypothesis_rejected"
    ROOT_CAUSE_IDENTIFIED = "root_cause_identified"

    # Mitigation actions
    MITIGATION_ATTEMPTED = "mitigation_attempted"
    MITIGATION_SUCCEEDED = "mitigation_succeeded"
    MITIGATION_FAILED = "mitigation_failed"
    ROLLBACK_INITIATED = "rollback_initiated"
    ROLLBACK_COMPLETED = "rollback_completed"
    DEPLOYMENT_EXECUTED = "deployment_executed"
    CONFIG_CHANGE = "config_change"
    SCALING_ACTION = "scaling_action"

    # Communications
    STATUS_UPDATE = "status_update"
    STAKEHOLDER_NOTIFIED = "stakeholder_notified"
    EXTERNAL_COMMS = "external_comms"
    WAR_ROOM_CREATED = "war_room_created"
    HANDOFF_COMMUNICATION = "handoff_communication"

    # Evidence & Analysis
    EVIDENCE_COLLECTED = "evidence_collected"
    LOG_ANALYSIS = "log_analysis"
    METRICS_ANALYSIS = "metrics_analysis"
    TRACE_ANALYSIS = "trace_analysis"
    RUNBOOK_EXECUTED = "runbook_executed"
    AI_RCA_INSIGHT = "ai_rca_insight"

    # Decisions
    DECISION_MADE = "decision_made"
    ESCALATION = "escalation"
    APPROVAL_REQUESTED = "approval_requested"
    APPROVAL_GRANTED = "approval_granted"
    APPROVAL_DENIED = "approval_denied"

    # Post-incident
    POSTMORTEM_STARTED = "postmortem_started"
    ACTION_ITEM_CREATED = "action_item_created"
    LESSON_LEARNED = "lesson_learned"


class EventSeverity(Enum):
    """Severity of timeline event (not incident severity)."""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
    MILESTONE = "milestone"


@dataclass
class TimelineEvent:
    """A single event in the incident timeline."""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    event_type: TimelineEventType = TimelineEventType.INFO
    timestamp: datetime = field(default_factory=datetime.utcnow)
    title: str = ""
    description: str = ""
    severity: EventSeverity = EventSeverity.INFO

    # Actor information
    actor_name: str = ""
    actor_role: str = ""
    actor_id: str = ""

    # Context
    incident_id: str = ""
    related_event_ids: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)

    # Technical details
    service: str = ""
    component: str = ""
    command_executed: str = ""
    command_output: str = ""
    links: List[str] = field(default_factory=list)  # URLs to dashboards, logs, etc.

    # Decision tracking
    decision: str = ""
    decision_rationale: str = ""
    alternatives_considered: List[str] = field(default_factory=list)

    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)
    source: str = "manual"  # manual, automated, ai_agent

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "event_type": self.event_type.value,
            "timestamp": self.timestamp.isoformat(),
            "title": self.title,
            "description": self.description,
            "severity": self.severity.value,
            "actor_name": self.actor_name,
            "actor_role": self.actor_role,
            "actor_id": self.actor_id,
            "incident_id": self.incident_id,
            "related_event_ids": self.related_event_ids,
            "tags": self.tags,
            "service": self.service,
            "component": self.component,
            "command_executed": self.command_executed,
            "command_output": self.command_output[:1000] if self.command_output else "",
            "links": self.links,
            "decision": self.decision,
            "decision_rationale": self.decision_rationale,
            "alternatives_considered": self.alternatives_considered,
            "metadata": self.metadata,
            "source": self.source
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TimelineEvent":
        """Create event from dictionary."""
        event = cls(
            id=data.get("id", str(uuid.uuid4())[:8]),
            event_type=TimelineEventType(data.get("event_type", "info")),
            timestamp=datetime.fromisoformat(data["timestamp"]) if "timestamp" in data else datetime.utcnow(),
            title=data.get("title", ""),
            description=data.get("description", ""),
            severity=EventSeverity(data.get("severity", "info")),
            actor_name=data.get("actor_name", ""),
            actor_role=data.get("actor_role", ""),
            actor_id=data.get("actor_id", ""),
            incident_id=data.get("incident_id", ""),
            related_event_ids=data.get("related_event_ids", []),
            tags=data.get("tags", []),
            service=data.get("service", ""),
            component=data.get("component", ""),
            command_executed=data.get("command_executed", ""),
            command_output=data.get("command_output", ""),
            links=data.get("links", []),
            decision=data.get("decision", ""),
            decision_rationale=data.get("decision_rationale", ""),
            alternatives_considered=data.get("alternatives_considered", []),
            metadata=data.get("metadata", {}),
            source=data.get("source", "manual")
        )
        return event

    def format_for_display(self, include_metadata: bool = False) -> str:
        """Format event for human-readable display."""
        time_str = self.timestamp.strftime("%H:%M:%S")
        severity_marker = {
            EventSeverity.INFO: "ℹ️",
            EventSeverity.WARNING: "⚠️",
            EventSeverity.CRITICAL: "🔴",
            EventSeverity.MILESTONE: "🎯"
        }.get(self.severity, "•")

        lines = [
            f"[{time_str}] {severity_marker} {self.event_type.value.replace('_', ' ').title()}: {self.title}"
        ]

        if self.description:
            lines.append(f"         {self.description}")

        if self.actor_name:
            role_str = f" ({self.actor_role})" if self.actor_role else ""
            lines.append(f"         By: {self.actor_name}{role_str}")

        if self.service:
            lines.append(f"         Service: {self.service}")

        if self.command_executed:
            lines.append(f"         Command: {self.command_executed}")
            if self.command_output:
                output_preview = self.command_output[:200].replace("\n", " ")
                lines.append(f"         Output: {output_preview}...")

        if self.decision:
            lines.append(f"         Decision: {self.decision}")
            if self.decision_rationale:
                lines.append(f"         Rationale: {self.decision_rationale}")

        if self.links:
            lines.append(f"         Links: {', '.join(self.links)}")

        if include_metadata and self.metadata:
            lines.append(f"         Metadata: {json.dumps(self.metadata, default=str)}")

        return "\n".join(lines)


@dataclass
class IncidentTimeline:
    """Complete timeline for an incident."""
    incident_id: str
    title: str = ""
    severity: str = "SEV-3"
    status: str = "open"  # open, investigating, mitigating, resolved, closed
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    resolved_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None

    events: List[TimelineEvent] = field(default_factory=list)
    event_index: Dict[str, int] = field(default_factory=dict)  # event_id -> index

    # Summary fields
    services_affected: List[str] = field(default_factory=list)
    root_cause: str = ""
    resolution_summary: str = ""
    action_items: List[Dict[str, Any]] = field(default_factory=list)

    def add_event(self, event: TimelineEvent) -> str:
        """Add an event to the timeline."""
        event.incident_id = self.incident_id
        self.events.append(event)
        self.event_index[event.id] = len(self.events) - 1
        self.updated_at = datetime.utcnow()

        # Update affected services
        if event.service and event.service not in self.services_affected:
            self.services_affected.append(event.service)

        logger.debug(f"Added event {event.id} to incident {self.incident_id}")
        return event.id

    def get_event(self, event_id: str) -> Optional[TimelineEvent]:
        """Get event by ID."""
        idx = self.event_index.get(event_id)
        if idx is not None and idx < len(self.events):
            return self.events[idx]
        return None

    def get_events_by_type(self, event_type: TimelineEventType) -> List[TimelineEvent]:
        """Get all events of a specific type."""
        return [e for e in self.events if e.event_type == event_type]

    def get_events_by_actor(self, actor_name: str) -> List[TimelineEvent]:
        """Get all events by a specific actor."""
        return [e for e in self.events if e.actor_name == actor_name]

    def get_events_by_service(self, service: str) -> List[TimelineEvent]:
        """Get all events related to a service."""
        return [e for e in self.events if e.service == service]

    def get_events_in_range(self, start: datetime, end: datetime) -> List[TimelineEvent]:
        """Get events within a time range."""
        return [e for e in self.events if start <= e.timestamp <= end]

    def get_recent_events(self, minutes: int = 60) -> List[TimelineEvent]:
        """Get events from the last N minutes."""
        cutoff = datetime.utcnow() - timedelta(minutes=minutes)
        return [e for e in self.events if e.timestamp >= cutoff]

    def link_events(self, event_id_1: str, event_id_2: str) -> bool:
        """Create bidirectional link between two events."""
        e1 = self.get_event(event_id_1)
        e2 = self.get_event(event_id_2)
        if e1 and e2:
            if event_id_2 not in e1.related_event_ids:
                e1.related_event_ids.append(event_id_2)
            if event_id_1 not in e2.related_event_ids:
                e2.related_event_ids.append(event_id_1)
            return True
        return False

    def set_root_cause(self, root_cause: str, identified_by: str, event_id: Optional[str] = None) -> None:
        """Set the root cause and create a milestone event."""
        self.root_cause = root_cause

        event = TimelineEvent(
            event_type=TimelineEventType.ROOT_CAUSE_IDENTIFIED,
            title="Root Cause Identified",
            description=root_cause,
            severity=EventSeverity.MILESTONE,
            actor_name=identified_by,
            tags=["root_cause", "milestone"]
        )
        if event_id:
            event.related_event_ids.append(event_id)
        self.add_event(event)

    def set_resolution(self, resolution: str, resolved_by: str) -> None:
        """Mark incident as resolved."""
        self.status = "resolved"
        self.resolved_at = datetime.utcnow()
        self.resolution_summary = resolution

        event = TimelineEvent(
            event_type=TimelineEventType.INCIDENT_RESOLVED,
            title="Incident Resolved",
            description=resolution,
            severity=EventSeverity.MILESTONE,
            actor_name=resolved_by,
            tags=["resolution", "milestone"]
        )
        self.add_event(event)

    def close_incident(self, closed_by: str) -> None:
        """Close the incident."""
        self.status = "closed"
        self.closed_at = datetime.utcnow()

        event = TimelineEvent(
            event_type=TimelineEventType.INCIDENT_CLOSED,
            title="Incident Closed",
            description="Incident formally closed after resolution verification",
            severity=EventSeverity.MILESTONE,
            actor_name=closed_by,
            tags=["closure", "milestone"]
        )
        self.add_event(event)

    def add_action_item(
        self,
        description: str,
        owner: str,
        due_date: Optional[datetime] = None,
        priority: str = "P2",
        tags: List[str] = None
    ) -> Dict[str, Any]:
        """Add a follow-up action item."""
        action_item = {
            "id": str(uuid.uuid4())[:8],
            "description": description,
            "owner": owner,
            "due_date": due_date.isoformat() if due_date else None,
            "priority": priority,
            "status": "open",
            "tags": tags or [],
            "created_at": datetime.utcnow().isoformat()
        }
        self.action_items.append(action_item)

        event = TimelineEvent(
            event_type=TimelineEventType.ACTION_ITEM_CREATED,
            title=f"Action Item: {description[:50]}...",
            description=description,
            severity=EventSeverity.INFO,
            actor_name=owner,
            metadata={"action_item_id": action_item["id"], "priority": priority},
            tags=["action_item", priority.lower()]
        )
        self.add_event(event)

        return action_item

    def get_duration(self) -> Optional[timedelta]:
        """Get incident duration."""
        if self.resolved_at:
            return self.resolved_at - self.created_at
        if self.closed_at:
            return self.closed_at - self.created_at
        return datetime.utcnow() - self.created_at

    def get_milestone_events(self) -> List[TimelineEvent]:
        """Get all milestone events."""
        return [e for e in self.events if e.severity == EventSeverity.MILESTONE]

    def get_decision_events(self) -> List[TimelineEvent]:
        """Get all decision events."""
        return [e for e in self.events if e.event_type == TimelineEventType.DECISION_MADE]

    def generate_summary(self) -> str:
        """Generate a human-readable timeline summary."""
        duration = self.get_duration()
        duration_str = str(duration).split(".")[0] if duration else "ongoing"

        lines = [
            f"# Incident Timeline: {self.incident_id}",
            f"**Title**: {self.title}",
            f"**Severity**: {self.severity}",
            f"**Status**: {self.status}",
            f"**Duration**: {duration_str}",
            f"**Services Affected**: {', '.join(self.services_affected) or 'None'}",
            f"**Root Cause**: {self.root_cause or 'Not yet identified'}",
            f"**Resolution**: {self.resolution_summary or 'Not yet resolved'}",
            "",
            "## Key Milestones"
        ]

        for event in self.get_milestone_events():
            time_str = event.timestamp.strftime("%H:%M:%S")
            lines.append(f"- [{time_str}] {event.title}: {event.description[:100]}")

        lines.append("\n## Decisions Made")
        for event in self.get_decision_events():
            time_str = event.timestamp.strftime("%H:%M:%S")
            lines.append(f"- [{time_str}] {event.decision} (by {event.actor_name})")
            if event.decision_rationale:
                lines.append(f"  Rationale: {event.decision_rationale}")

        if self.action_items:
            lines.append("\n## Action Items")
            for item in self.action_items:
                due = f" (Due: {item['due_date'][:10]})" if item['due_date'] else ""
                lines.append(f"- [{item['priority']}] {item['description']} - Owner: {item['owner']}{due}")

        return "\n".join(lines)

    def generate_detailed_timeline(self) -> str:
        """Generate full detailed timeline."""
        lines = [self.generate_summary(), "\n## Detailed Timeline"]

        for event in self.events:
            lines.append(event.format_for_display())
            lines.append("")

        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "incident_id": self.incident_id,
            "title": self.title,
            "severity": self.severity,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "closed_at": self.closed_at.isoformat() if self.closed_at else None,
            "services_affected": self.services_affected,
            "root_cause": self.root_cause,
            "resolution_summary": self.resolution_summary,
            "action_items": self.action_items,
            "events": [e.to_dict() for e in self.events]
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "IncidentTimeline":
        """Deserialize from dictionary."""
        timeline = cls(
            incident_id=data["incident_id"],
            title=data.get("title", ""),
            severity=data.get("severity", "SEV-3"),
            status=data.get("status", "open"),
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
            resolved_at=datetime.fromisoformat(data["resolved_at"]) if data.get("resolved_at") else None,
            closed_at=datetime.fromisoformat(data["closed_at"]) if data.get("closed_at") else None,
            services_affected=data.get("services_affected", []),
            root_cause=data.get("root_cause", ""),
            resolution_summary=data.get("resolution_summary", ""),
            action_items=data.get("action_items", [])
        )

        timeline.events = [TimelineEvent.from_dict(e) for e in data.get("events", [])]
        timeline.event_index = {e.id: i for i, e in enumerate(timeline.events)}

        return timeline

    def export_json(self, filepath: str) -> None:
        """Export timeline to JSON file."""
        with open(filepath, "w") as f:
            json.dump(self.to_dict(), f, indent=2, default=str)

    @classmethod
    def import_json(cls, filepath: str) -> "IncidentTimeline":
        """Import timeline from JSON file."""
        with open(filepath, "r") as f:
            data = json.load(f)
        return cls.from_dict(data)


class TimelineManager:
    """Manages multiple incident timelines."""

    def __init__(self):
        self.timelines: Dict[str, IncidentTimeline] = {}

    def create_timeline(
        self,
        incident_id: str,
        title: str = "",
        severity: str = "SEV-3"
    ) -> IncidentTimeline:
        """Create a new incident timeline."""
        if incident_id in self.timelines:
            logger.warning(f"Timeline {incident_id} already exists")
            return self.timelines[incident_id]

        timeline = IncidentTimeline(
            incident_id=incident_id,
            title=title,
            severity=severity
        )
        self.timelines[incident_id] = timeline
        logger.info(f"Created timeline for incident {incident_id}")
        return timeline

    def get_timeline(self, incident_id: str) -> Optional[IncidentTimeline]:
        """Get timeline by incident ID."""
        return self.timelines.get(incident_id)

    def list_timelines(self, status: Optional[str] = None) -> List[IncidentTimeline]:
        """List all timelines, optionally filtered by status."""
        timelines = list(self.timelines.values())
        if status:
            timelines = [t for t in timelines if t.status == status]
        return sorted(timelines, key=lambda t: t.created_at, reverse=True)

    def add_event_to_incident(
        self,
        incident_id: str,
        event: TimelineEvent
    ) -> Optional[str]:
        """Add event to an incident timeline."""
        timeline = self.timelines.get(incident_id)
        if timeline:
            return timeline.add_event(event)
        return None

    def search_events(
        self,
        query: str,
        incident_id: Optional[str] = None,
        event_type: Optional[TimelineEventType] = None,
        actor: Optional[str] = None,
        service: Optional[str] = None,
        since: Optional[datetime] = None,
        limit: int = 50
    ) -> List[TimelineEvent]:
        """Search events across timelines."""
        results = []

        timelines = [self.timelines[incident_id]] if incident_id else self.timelines.values()

        for timeline in timelines:
            for event in timeline.events:
                # Apply filters
                if event_type and event.event_type != event_type:
                    continue
                if actor and event.actor_name != actor:
                    continue
                if service and event.service != service:
                    continue
                if since and event.timestamp < since:
                    continue

                # Text search
                searchable = f"{event.title} {event.description} {event.command_executed} {event.decision}".lower()
                if query.lower() in searchable:
                    results.append(event)

        # Sort by timestamp descending
        results.sort(key=lambda e: e.timestamp, reverse=True)
        return results[:limit]


def create_timeline_manager() -> TimelineManager:
    """Factory function to create a TimelineManager."""
    return TimelineManager()


if __name__ == "__main__":
    # Demo
    logging.basicConfig(level=logging.INFO)

    manager = create_timeline_manager()

    # Create incident timeline
    timeline = manager.create_timeline("INC-2024-001", "Payment Service Latency Spike", "SEV-1")

    # Add events
    events = [
        TimelineEvent(
            event_type=TimelineEventType.INCIDENT_DETECTED,
            title="Alert triggered: payment-service p99 latency > 5s",
            description="PagerDuty alert from Prometheus rule payment_service_high_latency",
            severity=EventSeverity.CRITICAL,
            actor_name="alertmanager",
            actor_role="monitoring",
            source="automated",
            service="payment-service",
            tags=["alert", "detection"]
        ),
        TimelineEvent(
            event_type=TimelineEventType.INCIDENT_DECLARED,
            title="SEV-1 declared by IC",
            description="Incident Commander declared SEV-1 based on customer impact",
            severity=EventSeverity.MILESTONE,
            actor_name="Sarah Chen",
            actor_role="Incident Commander",
            actor_id="sarah.chen",
            tags=["declaration", "severity"]
        ),
        TimelineEvent(
            event_type=TimelineEventType.ROLE_ASSIGNED,
            title="Roles assigned",
            description="Assigned Tech Lead, SRE Lead, Communications, Documentation",
            severity=EventSeverity.INFO,
            actor_name="Sarah Chen",
            actor_role="Incident Commander",
            tags=["roles", "assignment"]
        ),
        TimelineEvent(
            event_type=TimelineEventType.INVESTIGATION_STARTED,
            title="Started investigation",
            description="Checking payment-service metrics and logs",
            severity=EventSeverity.INFO,
            actor_name="Mike Torres",
            actor_role="Tech Lead",
            service="payment-service",
            tags=["investigation"]
        ),
        TimelineEvent(
            event_type=TimelineEventType.METRICS_ANALYSIS,
            title="Found connection pool exhaustion",
            description="HikariCP metrics show connections_active=50, connections_idle=0, connections_pending=127",
            severity=EventSeverity.WARNING,
            actor_name="Mike Torres",
            actor_role="Tech Lead",
            service="payment-service",
            command_executed="kubectl exec -n payment deployment/payment-service -- curl localhost:8080/actuator/metrics/hikaricp.connections.active",
            tags=["metrics", "connection_pool"]
        ),
        TimelineEvent(
            event_type=TimelineEventType.HYPOTHESIS_PROPOSED,
            title="Hypothesis: Recent deployment changed pool config",
            description="Deployment v2.3.1 removed connectionTimeout and idleTimeout settings",
            severity=EventSeverity.INFO,
            actor_name="Mike Torres",
            actor_role="Tech Lead",
            decision="Investigate deployment v2.3.1 changes",
            decision_rationale="Config change correlates with incident start time",
            tags=["hypothesis", "deployment"]
        ),
        TimelineEvent(
            event_type=TimelineEventType.DECISION_MADE,
            title="Decision: Rollback to v2.3.0",
            description="Rollback deployment to restore connection pool settings",
            severity=EventSeverity.MILESTONE,
            actor_name="Sarah Chen",
            actor_role="Incident Commander",
            decision="Rollback payment-service to v2.3.0",
            decision_rationale="Fastest mitigation; config fix will follow in v2.3.2",
            alternatives_considered=["Scale replicas", "Manual config patch", "Wait for v2.3.2"],
            tags=["decision", "rollback"]
        ),
        TimelineEvent(
            event_type=TimelineEventType.MITIGATION_ATTEMPTED,
            title="Rollback initiated",
            description="ArgoCD rollback to v2.3.0",
            severity=EventSeverity.INFO,
            actor_name="Alex Kumar",
            actor_role="SRE Lead",
            service="payment-service",
            command_executed="argocd app rollback payment-service 2",
            tags=["mitigation", "rollback"]
        ),
        TimelineEvent(
            event_type=TimelineEventType.MITIGATION_SUCCEEDED,
            title="Rollback successful - latency normalized",
            description="Payment service p99 latency dropped from 8.2s to 120ms",
            severity=EventSeverity.MILESTONE,
            actor_name="Alex Kumar",
            actor_role="SRE Lead",
            service="payment-service",
            tags=["mitigation", "success"]
        ),
        TimelineEvent(
            event_type=TimelineEventType.ROOT_CAUSE_IDENTIFIED,
            title="Root cause confirmed",
            description="Missing connectionTimeout and idleTimeout in HikariCP config in v2.3.1 caused pool exhaustion under load",
            severity=EventSeverity.MILESTONE,
            actor_name="Mike Torres",
            actor_role="Tech Lead",
            service="payment-service",
            tags=["root_cause"]
        ),
    ]

    for event in events:
        timeline.add_event(event)

    # Set resolution
    timeline.set_resolution(
        "Rolled back to v2.3.0. Will deploy v2.3.2 with proper HikariCP config (connectionTimeout=5000, idleTimeout=300000, maxPoolSize=50)",
        "Sarah Chen"
    )

    # Add action items
    timeline.add_action_item(
        "Deploy v2.3.2 with fixed connection pool config",
        "Mike Torres",
        due_date=datetime.utcnow() + timedelta(days=1),
        priority="P1",
        tags=["config_fix", "deployment"]
    )
    timeline.add_action_item(
        "Add connection pool validation to CI pipeline",
        "Alex Kumar",
        due_date=datetime.utcnow() + timedelta(days=3),
        priority="P2",
        tags=["ci", "validation"]
    )
    timeline.add_action_item(
        "Update runbook for connection pool exhaustion",
        "Documentation Team",
        due_date=datetime.utcnow() + timedelta(days=2),
        priority="P2",
        tags=["runbook", "documentation"]
    )

    # Close incident
    timeline.close_incident("Sarah Chen")

    # Display summary
    print(timeline.generate_summary())
    print("\n" + "="*60)
    print("DETAILED TIMELINE (last 5 events)")
    print("="*60)
    for event in timeline.events[-5:]:
        print(event.format_for_display())
        print()

    # Search demo
    print("\n=== Search for 'connection pool' ===")
    results = manager.search_events("connection pool", incident_id="INC-2024-001")
    for event in results:
        print(f"  [{event.timestamp.strftime('%H:%M:%S')}] {event.title}")

    print("\n=== Search for decisions ===")
    results = manager.search_events("", incident_id="INC-2024-001", event_type=TimelineEventType.DECISION_MADE)
    for event in results:
        print(f"  [{event.timestamp.strftime('%H:%M:%S')}] {event.decision}")