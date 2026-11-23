"""
Escalation Policy Engine
========================
Manages automated and manual escalation policies for incidents.
Supports time-based, condition-based, and severity-based escalations.
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime, timedelta
from abc import ABC, abstractmethod
import logging

logger = logging.getLogger(__name__)


class EscalationTrigger(Enum):
    """What triggers an escalation."""
    TIME_ELAPSED = "time_elapsed"           # Time since incident start/last update
    SEVERITY_INCREASE = "severity_increase"  # Incident severity increased
    CONDITION_MET = "condition_met"         # Custom condition evaluated true
    MANUAL = "manual"                       # Manual escalation request
    SLA_BREACH = "sla_breach"              # SLA/SLO breach detected
    STAKEHOLDER_REQUEST = "stakeholder_request"  # Stakeholder asked for escalation
    NO_PROGRESS = "no_progress"            # No meaningful progress in timeframe
    RESOURCE_EXHAUSTED = "resource_exhausted"    # Team resources exhausted


class EscalationAction(Enum):
    """Actions to take on escalation."""
    NOTIFY = "notify"                       # Send notification
    PAGE = "page"                           # Page on-call
    ADD_RESPONDER = "add_responder"         # Add specific responder
    ADD_ROLE = "add_role"                   # Activate ICS role
    EXECUTIVE_NOTIFY = "executive_notify"   # Notify executives
    CUSTOMER_NOTIFY = "customer_notify"     # Notify customers
    RUNBOOK_TRIGGER = "runbook_trigger"     # Trigger specific runbook
    WAR_ROOM = "war_room"                   # Create/expand war room
    STATUS_PAGE = "status_page"             # Update status page
    EXTERNAL_VENDOR = "external_vendor"     # Engage external vendor
    CUSTOM = "custom"                       # Custom action


class EscalationLevel(Enum):
    """Escalation levels."""
    L1_TEAM = "l1_team"           # Team level
    L2_MANAGER = "l2_manager"     # Engineering manager
    L3_DIRECTOR = "l3_director"   # Director/VP
    L4_EXECUTIVE = "l4_executive" # C-level
    L5_EXTERNAL = "l5_external"   # External/vendor


@dataclass
class EscalationTarget:
    """Target for escalation notification/action."""
    name: str
    contact_method: str  # slack, email, pagerduty, phone, webhook
    contact_value: str   # channel, email, phone number, webhook URL
    role: str = ""
    timezone: str = "UTC"
    availability: Dict[str, Any] = field(default_factory=dict)  # schedule constraints

    def is_available(self, at: datetime = None) -> bool:
        """Check if target is available at given time."""
        if not self.availability:
            return True
        at = at or datetime.utcnow()
        # Simple schedule check (can be extended)
        if "hours" in self.availability:
            hours = self.availability["hours"]  # e.g., {"start": 9, "end": 17, "days": [0,1,2,3,4]}
            current_hour = at.hour
            current_day = at.weekday()
            if current_day not in hours.get("days", list(range(7))):
                return False
            if not (hours.get("start", 0) <= current_hour < hours.get("end", 24)):
                return False
        return True


@dataclass
class EscalationRule:
    """A single escalation rule."""
    id: str
    name: str
    description: str
    trigger: EscalationTrigger
    conditions: Dict[str, Any] = field(default_factory=dict)
    actions: List[EscalationAction] = field(default_factory=list)
    targets: List[EscalationTarget] = field(default_factory=list)

    # Timing
    delay_minutes: int = 0           # Delay before firing
    repeat_interval_minutes: int = 0 # Repeat if not acknowledged (0 = no repeat)
    max_repeats: int = 3

    # Scope
    severity_levels: List[str] = field(default_factory=lambda: ["SEV-1", "SEV-2", "SEV-3", "SEV-4"])
    services: List[str] = field(default_factory=list)  # Empty = all services
    tags: List[str] = field(default_factory=list)

    # State
    enabled: bool = True
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_triggered: Optional[datetime] = None
    trigger_count: int = 0

    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)

    def matches_incident(self, incident: "IncidentContext") -> bool:
        """Check if rule matches incident context."""
        if not self.enabled:
            return False

        # Check severity
        if incident.severity not in self.severity_levels:
            return False

        # Check service
        if self.services and incident.service not in self.services:
            return False

        # Check tags
        if self.tags and not any(tag in incident.tags for tag in self.tags):
            return False

        return True

    def evaluate_trigger(self, incident: "IncidentContext", trigger_data: Dict[str, Any]) -> bool:
        """Evaluate if trigger condition is met."""
        if self.trigger == EscalationTrigger.TIME_ELAPSED:
            elapsed = trigger_data.get("elapsed_minutes", 0)
            threshold = self.conditions.get("threshold_minutes", 30)
            return elapsed >= threshold

        elif self.trigger == EscalationTrigger.SEVERITY_INCREASE:
            return trigger_data.get("severity_increased", False)

        elif self.trigger == EscalationTrigger.SLA_BREACH:
            return trigger_data.get("sla_breached", False)

        elif self.trigger == EscalationTrigger.NO_PROGRESS:
            last_progress = trigger_data.get("last_progress_minutes", 0)
            threshold = self.conditions.get("no_progress_threshold_minutes", 60)
            return last_progress >= threshold

        elif self.trigger == EscalationTrigger.CONDITION_MET:
            # Custom condition - evaluate expression
            condition_expr = self.conditions.get("expression", "")
            if condition_expr:
                try:
                    # Simple expression evaluation (extend with safe eval)
                    return eval(condition_expr, {"incident": incident, "data": trigger_data})
                except Exception as e:
                    logger.error(f"Condition evaluation failed: {e}")
            return False

        elif self.trigger == EscalationTrigger.MANUAL:
            return trigger_data.get("manual_escalation", False)

        return False


@dataclass
class EscalationExecution:
    """Record of an escalation execution."""
    id: str
    rule_id: str
    incident_id: str
    triggered_at: datetime
    trigger_data: Dict[str, Any]
    actions_taken: List[Dict[str, Any]] = field(default_factory=list)
    acknowledged: bool = False
    acknowledged_at: Optional[datetime] = None
    acknowledged_by: str = ""
    repeat_count: int = 0
    status: str = "fired"  # fired, acknowledged, resolved, cancelled


@dataclass
class IncidentContext:
    """Context object for escalation evaluation."""
    incident_id: str
    title: str
    severity: str
    status: str
    service: str
    created_at: datetime
    updated_at: datetime
    assigned_roles: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Computed fields
    elapsed_minutes: int = 0
    last_progress_minutes: int = 0
    severity_increased: bool = False
    sla_breached: bool = False


class EscalationPolicy:
    """Manages a set of escalation rules for an organization/team."""

    def __init__(self, name: str, description: str = ""):
        self.name = name
        self.description = description
        self.rules: Dict[str, EscalationRule] = {}
        self.executions: List[EscalationExecution] = []
        self.notification_handlers: Dict[str, Callable] = {}

    def add_rule(self, rule: EscalationRule) -> None:
        """Add an escalation rule."""
        self.rules[rule.id] = rule
        logger.info(f"Added escalation rule: {rule.id} - {rule.name}")

    def remove_rule(self, rule_id: str) -> bool:
        """Remove an escalation rule."""
        if rule_id in self.rules:
            del self.rules[rule_id]
            return True
        return False

    def get_rule(self, rule_id: str) -> Optional[EscalationRule]:
        """Get rule by ID."""
        return self.rules.get(rule_id)

    def list_rules(self, enabled_only: bool = True) -> List[EscalationRule]:
        """List all rules."""
        rules = list(self.rules.values())
        if enabled_only:
            rules = [r for r in rules if r.enabled]
        return sorted(rules, key=lambda r: (r.trigger.value, r.delay_minutes))

    def register_notification_handler(
        self,
        method: str,
        handler: Callable[[EscalationTarget, str, Dict], bool]
    ) -> None:
        """Register a notification handler for a contact method."""
        self.notification_handlers[method] = handler
        logger.info(f"Registered notification handler for {method}")

    def evaluate_incident(self, incident: IncidentContext) -> List[EscalationExecution]:
        """Evaluate all rules against incident and fire matching ones."""
        executions = []

        for rule in self.rules.values():
            if not rule.matches_incident(incident):
                continue

            # Build trigger data
            trigger_data = {
                "elapsed_minutes": incident.elapsed_minutes,
                "last_progress_minutes": incident.last_progress_minutes,
                "severity_increased": incident.severity_increased,
                "sla_breached": incident.sla_breached,
                "manual_escalation": incident.metadata.get("manual_escalation", False),
            }

            if rule.evaluate_trigger(incident, trigger_data):
                execution = self._execute_rule(rule, incident, trigger_data)
                executions.append(execution)

        return executions

    def _execute_rule(
        self,
        rule: EscalationRule,
        incident: IncidentContext,
        trigger_data: Dict[str, Any]
    ) -> EscalationExecution:
        """Execute an escalation rule."""
        execution = EscalationExecution(
            id=f"esc-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{rule.id[:8]}",
            rule_id=rule.id,
            incident_id=incident.incident_id,
            triggered_at=datetime.utcnow(),
            trigger_data=trigger_data
        )

        # Execute each action
        for action in rule.actions:
            result = self._execute_action(action, rule, incident, execution)
            execution.actions_taken.append(result)

        # Update rule state
        rule.last_triggered = datetime.utcnow()
        rule.trigger_count += 1

        # Record execution
        self.executions.append(execution)

        logger.warning(f"Escalation fired: {rule.name} for incident {incident.incident_id}")
        return execution

    def _execute_action(
        self,
        action: EscalationAction,
        rule: EscalationRule,
        incident: IncidentContext,
        execution: EscalationExecution
    ) -> Dict[str, Any]:
        """Execute a single escalation action."""
        result = {
            "action": action.value,
            "timestamp": datetime.utcnow().isoformat(),
            "success": False,
            "details": {}
        }

        try:
            if action == EscalationAction.NOTIFY:
                result = self._execute_notify(rule, incident, execution)
            elif action == EscalationAction.PAGE:
                result = self._execute_page(rule, incident, execution)
            elif action == EscalationAction.ADD_RESPONDER:
                result = self._execute_add_responder(rule, incident, execution)
            elif action == EscalationAction.ADD_ROLE:
                result = self._execute_add_role(rule, incident, execution)
            elif action == EscalationAction.EXECUTIVE_NOTIFY:
                result = self._execute_executive_notify(rule, incident, execution)
            elif action == EscalationAction.CUSTOMER_NOTIFY:
                result = self._execute_customer_notify(rule, incident, execution)
            elif action == EscalationAction.RUNBOOK_TRIGGER:
                result = self._execute_runbook_trigger(rule, incident, execution)
            elif action == EscalationAction.WAR_ROOM:
                result = self._execute_war_room(rule, incident, execution)
            elif action == EscalationAction.STATUS_PAGE:
                result = self._execute_status_page(rule, incident, execution)
            elif action == EscalationAction.EXTERNAL_VENDOR:
                result = self._execute_external_vendor(rule, incident, execution)
            elif action == EscalationAction.CUSTOM:
                result = self._execute_custom(rule, incident, execution)

            result["success"] = True

        except Exception as e:
            logger.error(f"Escalation action {action.value} failed: {e}")
            result["details"]["error"] = str(e)

        return result

    def _execute_notify(self, rule: EscalationRule, incident: IncidentContext, execution: EscalationExecution) -> Dict:
        """Send notifications to targets."""
        results = []
        for target in rule.targets:
            if not target.is_available():
                results.append({"target": target.name, "skipped": True, "reason": "unavailable"})
                continue

            message = self._format_notification(rule, incident, execution)
            handler = self.notification_handlers.get(target.contact_method)

            if handler:
                success = handler(target, message, {
                    "incident_id": incident.incident_id,
                    "rule_id": rule.id,
                    "execution_id": execution.id
                })
                results.append({"target": target.name, "method": target.contact_method, "success": success})
            else:
                results.append({"target": target.name, "success": False, "error": f"No handler for {target.contact_method}"})

        return {"action": "notify", "results": results}

    def _execute_page(self, rule: EscalationRule, incident: IncidentContext, execution: EscalationExecution) -> Dict:
        """Page on-call targets (high urgency)."""
        # Pages are notifications with high urgency/priority
        results = []
        for target in rule.targets:
            message = f"🚨 PAGE: {incident.severity} - {incident.title}\nIncident: {incident.incident_id}\nRule: {rule.name}"
            handler = self.notification_handlers.get("pagerduty") or self.notification_handlers.get(target.contact_method)

            if handler:
                success = handler(target, message, {
                    "incident_id": incident.incident_id,
                    "rule_id": rule.id,
                    "priority": "high",
                    "execution_id": execution.id
                })
                results.append({"target": target.name, "success": success})
            else:
                results.append({"target": target.name, "success": False, "error": "No paging handler"})

        return {"action": "page", "results": results}

    def _execute_add_responder(self, rule: EscalationRule, incident: IncidentContext, execution: EscalationExecution) -> Dict:
        """Add specific responders to incident."""
        responders = rule.conditions.get("responders", [])
        return {"action": "add_responder", "responders": responders}

    def _execute_add_role(self, rule: EscalationRule, incident: IncidentContext, execution: EscalationExecution) -> Dict:
        """Activate ICS roles."""
        roles = rule.conditions.get("roles", [])
        return {"action": "add_role", "roles": roles}

    def _execute_executive_notify(self, rule: EscalationRule, incident: IncidentContext, execution: EscalationExecution) -> Dict:
        """Notify executives."""
        exec_targets = [t for t in rule.targets if "executive" in t.role.lower() or "director" in t.role.lower() or "vp" in t.role.lower()]
        if not exec_targets:
            exec_targets = rule.targets

        results = []
        for target in exec_targets:
            message = f"📊 EXECUTIVE ESCALATION: {incident.severity} - {incident.title}\nIncident: {incident.incident_id}\nDuration: {incident.elapsed_minutes} min"
            handler = self.notification_handlers.get(target.contact_method)
            if handler:
                success = handler(target, message, {"priority": "executive", "incident_id": incident.incident_id})
                results.append({"target": target.name, "success": success})

        return {"action": "executive_notify", "results": results}

    def _execute_customer_notify(self, rule: EscalationRule, incident: IncidentContext, execution: EscalationExecution) -> Dict:
        """Notify customers via status page or direct communication."""
        return {"action": "customer_notify", "incident_id": incident.incident_id, "status_page_update": True}

    def _execute_runbook_trigger(self, rule: EscalationRule, incident: IncidentContext, execution: EscalationExecution) -> Dict:
        """Trigger a specific runbook."""
        runbook_id = rule.conditions.get("runbook_id", "")
        return {"action": "runbook_trigger", "runbook_id": runbook_id}

    def _execute_war_room(self, rule: EscalationRule, incident: IncidentContext, execution: EscalationExecution) -> Dict:
        """Create or expand war room."""
        return {"action": "war_room", "incident_id": incident.incident_id, "create": True}

    def _execute_status_page(self, rule: EscalationRule, incident: IncidentContext, execution: EscalationExecution) -> Dict:
        """Update status page."""
        return {"action": "status_page", "incident_id": incident.incident_id, "update": True}

    def _execute_external_vendor(self, rule: EscalationRule, incident: IncidentContext, execution: EscalationExecution) -> Dict:
        """Engage external vendor."""
        vendor = rule.conditions.get("vendor", "")
        return {"action": "external_vendor", "vendor": vendor}

    def _execute_custom(self, rule: EscalationRule, incident: IncidentContext, execution: EscalationExecution) -> Dict:
        """Custom action - defined in rule metadata."""
        custom_action = rule.metadata.get("custom_action", {})
        return {"action": "custom", "details": custom_action}

    def _format_notification(self, rule: EscalationRule, incident: IncidentContext, execution: EscalationExecution) -> str:
        """Format notification message."""
        return (
            f"⚠️ Escalation: {rule.name}\n"
            f"Incident: {incident.incident_id} - {incident.title}\n"
            f"Severity: {incident.severity} | Service: {incident.service}\n"
            f"Elapsed: {incident.elapsed_minutes} min\n"
            f"Trigger: {rule.trigger.value}"
        )

    def acknowledge_execution(self, execution_id: str, acknowledged_by: str) -> bool:
        """Acknowledge an escalation execution."""
        for execution in self.executions:
            if execution.id == execution_id:
                execution.acknowledged = True
                execution.acknowledged_at = datetime.utcnow()
                execution.acknowledged_by = acknowledged_by
                execution.status = "acknowledged"
                logger.info(f"Escalation {execution_id} acknowledged by {acknowledged_by}")
                return True
        return False

    def get_executions_for_incident(self, incident_id: str) -> List[EscalationExecution]:
        """Get all executions for an incident."""
        return [e for e in self.executions if e.incident_id == incident_id]

    def get_pending_escalations(self, incident_id: str) -> List[EscalationExecution]:
        """Get unacknowledged escalations for an incident."""
        return [
            e for e in self.executions
            if e.incident_id == incident_id and not e.acknowledged
        ]


# Pre-defined escalation policies
def create_standard_escalation_policy() -> EscalationPolicy:
    """Create a standard escalation policy with common rules."""
    policy = EscalationPolicy("Standard SRE Escalation Policy", "Default escalation rules for SRE team")

    # Rule 1: SEV-1 immediate page
    policy.add_rule(EscalationRule(
        id="sev1-immediate-page",
        name="SEV-1 Immediate Page",
        description="Page on-call immediately for SEV-1 incidents",
        trigger=EscalationTrigger.SEVERITY_INCREASE,
        conditions={"severity": "SEV-1"},
        actions=[EscalationAction.PAGE, EscalationAction.WAR_ROOM],
        targets=[
            EscalationTarget("On-Call Primary", "pagerduty", "PRIMARY_ONCALL", role="oncall_primary"),
            EscalationTarget("On-Call Secondary", "pagerduty", "SECONDARY_ONCALL", role="oncall_secondary"),
        ],
        severity_levels=["SEV-1"],
        delay_minutes=0
    ))

    # Rule 2: SEV-1 escalate to manager at 15 min
    policy.add_rule(EscalationRule(
        id="sev1-manager-15min",
        name="SEV-1 Manager Escalation (15 min)",
        description="Escalate to engineering manager if SEV-1 not acknowledged in 15 min",
        trigger=EscalationTrigger.TIME_ELAPSED,
        conditions={"threshold_minutes": 15},
        actions=[EscalationAction.NOTIFY, EscalationAction.ADD_ROLE],
        targets=[
            EscalationTarget("Engineering Manager", "slack", "#eng-managers", role="manager"),
        ],
        severity_levels=["SEV-1"],
        delay_minutes=15,
        conditions={"threshold_minutes": 15, "roles": ["INCIDENT_COMMANDER", "COMMUNICATIONS"]}
    ))

    # Rule 3: SEV-1 escalate to director at 30 min
    policy.add_rule(EscalationRule(
        id="sev1-director-30min",
        name="SEV-1 Director Escalation (30 min)",
        description="Escalate to director if SEV-1 not resolved in 30 min",
        trigger=EscalationTrigger.TIME_ELAPSED,
        conditions={"threshold_minutes": 30},
        actions=[EscalationAction.EXECUTIVE_NOTIFY, EscalationAction.STATUS_PAGE],
        targets=[
            EscalationTarget("Engineering Director", "slack", "#eng-directors", role="director"),
            EscalationTarget("VP Engineering", "email", "vp-eng@company.com", role="vp"),
        ],
        severity_levels=["SEV-1"],
        delay_minutes=30
    ))

    # Rule 4: SEV-2 page on-call
    policy.add_rule(EscalationRule(
        id="sev2-page",
        name="SEV-2 Page On-Call",
        description="Page on-call for SEV-2 incidents",
        trigger=EscalationTrigger.SEVERITY_INCREASE,
        conditions={"severity": "SEV-2"},
        actions=[EscalationAction.PAGE],
        targets=[
            EscalationTarget("On-Call Primary", "pagerduty", "PRIMARY_ONCALL", role="oncall_primary"),
        ],
        severity_levels=["SEV-2"],
        delay_minutes=0
    ))

    # Rule 5: No progress escalation
    policy.add_rule(EscalationRule(
        id="no-progress-60min",
        name="No Progress Escalation (60 min)",
        description="Escalate if no meaningful progress in 60 minutes",
        trigger=EscalationTrigger.NO_PROGRESS,
        conditions={"no_progress_threshold_minutes": 60},
        actions=[EscalationAction.NOTIFY, EscalationAction.ADD_RESPONDER],
        targets=[
            EscalationTarget("Tech Lead", "slack", "#tech-leads", role="tech_lead"),
            EscalationTarget("SRE Lead", "slack", "#sre-leads", role="sre_lead"),
        ],
        severity_levels=["SEV-1", "SEV-2"],
        delay_minutes=60,
        conditions={"no_progress_threshold_minutes": 60, "responders": ["tech-lead", "sre-lead"]}
    ))

    # Rule 6: SLA breach escalation
    policy.add_rule(EscalationRule(
        id="sla-breach",
        name="SLA Breach Escalation",
        description="Escalate when SLA/SLO breach detected",
        trigger=EscalationTrigger.SLA_BREACH,
        conditions={},
        actions=[EscalationAction.EXECUTIVE_NOTIFY, EscalationAction.CUSTOMER_NOTIFY, EscalationAction.STATUS_PAGE],
        targets=[
            EscalationTarget("Engineering Director", "slack", "#eng-directors", role="director"),
            EscalationTarget("Customer Success", "slack", "#customer-success", role="customer_success"),
        ],
        severity_levels=["SEV-1", "SEV-2", "SEV-3"],
        delay_minutes=0
    ))

    # Rule 7: SEV-1 executive notification at 60 min
    policy.add_rule(EscalationRule(
        id="sev1-executive-60min",
        name="SEV-1 Executive Notification (60 min)",
        description="Notify C-level executives for extended SEV-1",
        trigger=EscalationTrigger.TIME_ELAPSED,
        conditions={"threshold_minutes": 60},
        actions=[EscalationAction.EXECUTIVE_NOTIFY],
        targets=[
            EscalationTarget("CTO", "email", "cto@company.com", role="cto"),
            EscalationTarget("COO", "email", "coo@company.com", role="coo"),
        ],
        severity_levels=["SEV-1"],
        delay_minutes=60
    ))

    return policy


def create_custom_escalation_policy(team_name: str, config: Dict[str, Any]) -> EscalationPolicy:
    """Create a custom escalation policy from configuration."""
    policy = EscalationPolicy(f"{team_name} Escalation Policy", config.get("description", ""))

    for rule_config in config.get("rules", []):
        rule = EscalationRule(
            id=rule_config["id"],
            name=rule_config["name"],
            description=rule_config.get("description", ""),
            trigger=EscalationTrigger(rule_config["trigger"]),
            conditions=rule_config.get("conditions", {}),
            actions=[EscalationAction(a) for a in rule_config.get("actions", [])],
            targets=[
                EscalationTarget(
                    name=t["name"],
                    contact_method=t["contact_method"],
                    contact_value=t["contact_value"],
                    role=t.get("role", ""),
                    timezone=t.get("timezone", "UTC"),
                    availability=t.get("availability", {})
                )
                for t in rule_config.get("targets", [])
            ],
            delay_minutes=rule_config.get("delay_minutes", 0),
            repeat_interval_minutes=rule_config.get("repeat_interval_minutes", 0),
            max_repeats=rule_config.get("max_repeats", 3),
            severity_levels=rule_config.get("severity_levels", ["SEV-1", "SEV-2", "SEV-3", "SEV-4"]),
            services=rule_config.get("services", []),
            tags=rule_config.get("tags", []),
            enabled=rule_config.get("enabled", True),
            metadata=rule_config.get("metadata", {})
        )
        policy.add_rule(rule)

    return policy


if __name__ == "__main__":
    # Demo
    logging.basicConfig(level=logging.INFO)

    # Create standard policy
    policy = create_standard_escalation_policy()

    # Register mock notification handlers
    def mock_slack_handler(target, message, context):
        print(f"  [SLACK -> {target.contact_value}] {message[:80]}...")
        return True

    def mock_pagerduty_handler(target, message, context):
        print(f"  [PAGERDUTY -> {target.contact_value}] {message[:80]}...")
        return True

    def mock_email_handler(target, message, context):
        print(f"  [EMAIL -> {target.contact_value}] {message[:80]}...")
        return True

    policy.register_notification_handler("slack", mock_slack_handler)
    policy.register_notification_handler("pagerduty", mock_pagerduty_handler)
    policy.register_notification_handler("email", mock_email_handler)

    # Create incident context
    incident = IncidentContext(
        incident_id="INC-2024-001",
        title="Payment Service Latency Spike",
        severity="SEV-1",
        status="investigating",
        service="payment-service",
        created_at=datetime.utcnow() - timedelta(minutes=20),
        updated_at=datetime.utcnow() - timedelta(minutes=5),
        elapsed_minutes=20,
        last_progress_minutes=10,
        tags=["payment", "latency"]
    )

    print("=== Evaluating Incident at 20 minutes ===")
    executions = policy.evaluate_incident(incident)
    for exec in executions:
        print(f"  Fired: {exec.rule_id}")
        for action in exec.actions_taken:
            print(f"    Action: {action['action']} - Success: {action.get('success', False)}")

    # Simulate 40 minutes later
    incident.elapsed_minutes = 40
    incident.last_progress_minutes = 30
    incident.updated_at = datetime.utcnow()

    print("\n=== Evaluating Incident at 40 minutes ===")
    executions = policy.evaluate_incident(incident)
    for exec in executions:
        print(f"  Fired: {exec.rule_id}")
        for action in exec.actions_taken:
            print(f"    Action: {action['action']} - Success: {action.get('success', False)}")

    # Show all rules
    print("\n=== All Rules ===")
    for rule in policy.list_rules():
        print(f"  {rule.id}: {rule.name} (trigger: {rule.trigger.value}, delay: {rule.delay_minutes}min)")