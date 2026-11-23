"""
Incident Command System (ICS) Roles
====================================
Adapts ICS structure for software incident response with clear role definitions,
responsibilities, and handoff procedures.
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class ICSRole(Enum):
    """Standard ICS roles adapted for software incidents."""
    INCIDENT_COMMANDER = "incident_commander"
    DEPUTY_IC = "deputy_ic"
    SAFETY_OFFICER = "safety_officer"
    LIAISON_OFFICER = "liaison_officer"
    PUBLIC_INFO_OFFICER = "public_info_officer"

    # General Staff
    OPERATIONS_CHIEF = "operations_chief"
    PLANNING_CHIEF = "planning_chief"
    LOGISTICS_CHIEF = "logistics_chief"
    FINANCE_CHIEF = "finance_chief"

    # Technical Roles (software-specific)
    TECH_LEAD = "tech_lead"
    SRE_LEAD = "sre_lead"
    DEVELOPER = "developer"
    DATA_ANALYST = "data_analyst"
    AI_RCA_AGENT = "ai_rca_agent"

    # Support Roles
    COMMUNICATIONS = "communications"
    DOCUMENTATION = "documentation"
    STAKEHOLDER_MGMT = "stakeholder_mgmt"


class RoleStatus(Enum):
    """Current status of a role assignment."""
    UNASSIGNED = "unassigned"
    ASSIGNED = "assigned"
    ACTIVE = "active"
    STANDBY = "standby"
    RELIEVED = "relieved"


@dataclass
class RoleAssignment:
    """Represents a person assigned to an ICS role."""
    role: ICSRole
    person_name: str
    person_id: str  # Slack ID, email, etc.
    status: RoleStatus = RoleStatus.ASSIGNED
    assigned_at: datetime = field(default_factory=datetime.utcnow)
    relieved_at: Optional[datetime] = None
    relieved_by: Optional[str] = None
    notes: str = ""

    def activate(self) -> None:
        """Mark role as active."""
        self.status = RoleStatus.ACTIVE

    def standby(self) -> None:
        """Mark role as standby."""
        self.status = RoleStatus.STANDBY

    def relieve(self, relieved_by: str, notes: str = "") -> None:
        """Relieve this assignment."""
        self.status = RoleStatus.RELIEVED
        self.relieved_at = datetime.utcnow()
        self.relieved_by = relieved_by
        self.notes = notes


@dataclass
class RoleResponsibilities:
    """Defines responsibilities for an ICS role."""
    role: ICSRole
    primary_responsibilities: List[str]
    secondary_responsibilities: List[str] = field(default_factory=list)
    authority: List[str] = field(default_factory=list)
    reports_to: Optional[ICSRole] = None
    coordinates_with: List[ICSRole] = field(default_factory=list)
    required_skills: List[str] = field(default_factory=list)
    backup_roles: List[ICSRole] = field(default_factory=list)


# Define standard ICS responsibilities for software incidents
ICS_RESPONSIBILITIES: Dict[ICSRole, RoleResponsibilities] = {
    ICSRole.INCIDENT_COMMANDER: RoleResponsibilities(
        role=ICSRole.INCIDENT_COMMANDER,
        primary_responsibilities=[
            "Overall incident management and decision authority",
            "Set incident objectives and priorities",
            "Authorize resource allocation and escalation",
            "Maintain situational awareness",
            "Coordinate with executive leadership",
            "Declare incident severity and status changes",
            "Approve communication to stakeholders",
            "Ensure incident documentation completeness"
        ],
        authority=[
            "Final decision on mitigation actions",
            "Authority to pull any engineer into incident",
            "Can declare incident resolved",
            "Escalation to executive leadership"
        ],
        required_skills=[
            "Incident command experience",
            "System architecture knowledge",
            "Decision making under pressure",
            "Stakeholder communication"
        ],
        backup_roles=[ICSRole.DEPUTY_IC, ICSSRole.OPERATIONS_CHIEF]
    ),

    ICSRole.DEPUTY_IC: RoleResponsibilities(
        role=ICSRole.DEPUTY_IC,
        primary_responsibilities=[
            "Support Incident Commander in all duties",
            "Manage specific functional areas as delegated",
            "Assume IC role if IC becomes unavailable",
            "Track action items and follow-ups",
            "Monitor incident timeline and milestones"
        ],
        reports_to=ICSRole.INCIDENT_COMMANDER,
        required_skills=["Incident command knowledge", "System knowledge"],
        backup_roles=[ICSRole.OPERATIONS_CHIEF]
    ),

    ICSRole.SAFETY_OFFICER: RoleResponsibilities(
        role=ICSRole.SAFETY_OFFICER,
        primary_responsibilities=[
            "Monitor for safety/impact risks in mitigation actions",
            "Assess blast radius of proposed changes",
            "Authorize emergency stops on dangerous actions",
            "Track customer impact and data integrity risks",
            "Ensure rollback plans exist for all mitigations"
        ],
        authority=[
            "Can halt any mitigation action deemed unsafe",
            "Requires sign-off on production changes during SEV-1"
        ],
        coordinates_with=[ICSRole.OPERATIONS_CHIEF, ICSSRole.TECH_LEAD],
        required_skills=["Risk assessment", "System architecture", "Change management"]
    ),

    ICSRole.LIAISON_OFFICER: RoleResponsibilities(
        role=ICSRole.LIAISON_OFFICER,
        primary_responsibilities=[
            "Coordinate with external teams (vendor, security, legal)",
            "Manage cross-team dependencies",
            "Track commitments from other teams",
            "Facilitate handoffs between teams"
        ],
        coordinates_with=[ICSRole.INCIDENT_COMMANDER, ICSSRole.STACKHOLDER_MGMT],
        required_skills=["Cross-team coordination", "Vendor management"]
    ),

    ICSRole.PUBLIC_INFO_OFFICER: RoleResponsibilities(
        role=ICSRole.PUBLIC_INFO_OFFICER,
        primary_responsibilities=[
            "Manage external communications (status page, social media)",
            "Coordinate with PR/Marketing on customer messaging",
            "Ensure consistent messaging across channels",
            "Manage stakeholder notification cadence"
        ],
        reports_to=ICSRole.INCIDENT_COMMANDER,
        coordinates_with=[ICSRole.LIAISON_OFFICER, ICSSRole.COMMUNICATIONS],
        required_skills=["Crisis communication", "Technical writing"]
    ),

    ICSRole.OPERATIONS_CHIEF: RoleResponsibilities(
        role=ICSRole.OPERATIONS_CHIEF,
        primary_responsibilities=[
            "Direct all tactical mitigation activities",
            "Coordinate technical responders",
            "Manage deployment of fixes and rollbacks",
            "Track mitigation progress and effectiveness",
            "Ensure runbook execution follows procedure"
        ],
        reports_to=ICSRole.INCIDENT_COMMANDER,
        coordinates_with=[ICSRole.TECH_LEAD, ICSSRole.SRE_LEAD, ICSSRole.DEVELOPER, ICSSRole.SAFETY_OFFICER],
        authority=[
            "Directs technical mitigation work",
            "Approves production changes during incident"
        ],
        required_skills=["Production operations", "Kubernetes", "Deployment", "Rollback procedures"],
        backup_roles=[ICSRole.TECH_LEAD, ICSSRole.SRE_LEAD]
    ),

    ICSRole.PLANNING_CHIEF: RoleResponsibilities(
        role=ICSRole.PLANNING_CHIEF,
        primary_responsibilities=[
            "Develop incident action plan (IAP)",
            "Track incident timeline and milestones",
            "Forecast resource needs",
            "Plan for incident resolution and recovery",
            "Coordinate shift handoffs",
            "Maintain incident documentation"
        ],
        reports_to=ICSRole.INCIDENT_COMMANDER,
        coordinates_with=[ICSRole.OPERATIONS_CHIEF, ICSSRole.DOCUMENTATION, ICSSRole.DATA_ANALYST],
        required_skills=["Incident planning", "Documentation", "Resource forecasting"]
    ),

    ICSRole.LOGISTICS_CHIEF: RoleResponsibilities(
        role=ICSRole.LOGISTICS_CHIEF,
        primary_responsibilities=[
            "Provision tools, access, and environments",
            "Manage war room setup (physical/virtual)",
            "Coordinate access to systems and data",
            "Arrange food/rest for extended incidents",
            "Manage communication channels (Slack, Zoom, etc.)"
        ],
        reports_to=ICSRole.INCIDENT_COMMANDER,
        coordinates_with=[ICSRole.COMMUNICATIONS],
        required_skills=["Tooling knowledge", "Access management"]
    ),

    ICSRole.FINANCE_CHIEF: RoleResponsibilities(
        role=ICSRole.FINANCE_CHIEF,
        primary_responsibilities=[
            "Track incident costs (engineering time, infra, business impact)",
            "Manage procurement for emergency resources",
            "Coordinate with finance on cost tracking",
            "Estimate financial impact"
        ],
        reports_to=ICSRole.INCIDENT_COMMANDER,
        required_skills=["Cost analysis", "Finance coordination"]
    ),

    # Software-specific roles
    ICSRole.TECH_LEAD: RoleResponsibilities(
        role=ICSRole.TECH_LEAD,
        primary_responsibilities=[
            "Technical authority on affected systems",
            "Guide root cause analysis",
            "Review and approve code/config changes",
            "Coordinate with service owners",
            "Maintain technical context for IC"
        ],
        reports_to=ICSRole.OPERATIONS_CHIEF,
        coordinates_with=[ICSRole.SRE_LEAD, ICSSRole.DEVELOPER, ICSSRole.AI_RCA_AGENT],
        required_skills=["Deep system knowledge", "Code review", "Architecture"],
        backup_roles=[ICSRole.SRE_LEAD]
    ),

    ICSRole.SRE_LEAD: RoleResponsibilities(
        role=ICSRole.SRE_LEAD,
        primary_responsibilities=[
            "Infrastructure and platform expertise",
            "Kubernetes/cluster operations",
            "Observability platform management",
            "Capacity and scaling decisions",
            "SLO/error budget awareness"
        ],
        reports_to=ICSRole.OPERATIONS_CHIEF,
        coordinates_with=[ICSRole.TECH_LEAD, ICSSRole.DATA_ANALYST],
        required_skills=["Kubernetes", "Cloud infrastructure", "Observability", "Capacity planning"]
    ),

    ICSRole.DEVELOPER: RoleResponsibilities(
        role=ICSRole.DEVELOPER,
        primary_responsibilities=[
            "Implement code fixes under direction",
            "Execute deployments and rollbacks",
            "Provide service-specific knowledge",
            "Write and run verification tests"
        ],
        reports_to=ICSRole.OPERATIONS_CHIEF,
        coordinates_with=[ICSRole.TECH_LEAD, ICSSRole.SRE_LEAD],
        required_skills=["Service codebase", "Deployment", "Testing"]
    ),

    ICSRole.DATA_ANALYST: RoleResponsibilities(
        role=ICSRole.DATA_ANALYST,
        primary_responsibilities=[
            "Query and analyze metrics, logs, traces",
            "Build ad-hoc dashboards for incident",
            "Correlate data sources",
            "Support hypothesis validation with data"
        ],
        reports_to=ICSRole.PLANNING_CHIEF,
        coordinates_with=[ICSRole.AI_RCA_AGENT, ICSSRole.TECH_LEAD],
        required_skills=["SQL/PromQL", "Data visualization", "Statistical analysis"]
    ),

    ICSRole.AI_RCA_AGENT: RoleResponsibilities(
        role=ICSRole.AI_RCA_AGENT,
        primary_responsibilities=[
            "Automated evidence collection from observability stack",
            "Generate root cause hypotheses with confidence scores",
            "Search historical incidents for similar patterns",
            "Suggest runbook matches",
            "Provide real-time timeline reconstruction"
        ],
        reports_to=ICSRole.OPERATIONS_CHIEF,
        coordinates_with=[ICSRole.TECH_LEAD, ICSSRole.DATA_ANALYST, ICSSRole.DOCUMENTATION],
        required_skills=["MCP integration", "Vector search", "LLM prompting"],
        authority=["Can query any observability data source"]
    ),

    ICSRole.COMMUNICATIONS: RoleResponsibilities(
        role=ICSRole.COMMUNICATIONS,
        primary_responsibilities=[
            "Manage incident Slack channel / war room",
            "Broadcast updates to stakeholders",
            "Maintain incident timeline in chat",
            "Coordinate status page updates",
            "Facilitate handoff communications"
        ],
        reports_to=ICSRole.LOGISTICS_CHIEF,
        coordinates_with=[ICSRole.PUBLIC_INFO_OFFICER, ICSSRole.DOCUMENTATION],
        required_skills=["Communication tools", "Technical writing", "Stakeholder management"]
    ),

    ICSRole.DOCUMENTATION: RoleResponsibilities(
        role=ICSRole.DOCUMENTATION,
        primary_responsibilities=[
            "Maintain incident timeline and decisions log",
            "Record all actions taken and outcomes",
            "Capture evidence and artifacts",
            "Prepare post-incident report draft",
            "Track action items for follow-up"
        ],
        reports_to=ICSRole.PLANNING_CHIEF,
        coordinates_with=[ICSRole.COMMUNICATIONS, ICSSRole.AI_RCA_AGENT],
        required_skills=["Documentation", "Attention to detail", "Technical writing"]
    ),

    ICSRole.STACKHOLDER_MGMT: RoleResponsibilities(
        role=ICSRole.STACKHOLDER_MGMT,
        primary_responsibilities=[
            "Manage executive and customer communications",
            "Coordinate with Customer Success/Support",
            "Track SLA commitments",
            "Escalate to leadership per policy"
        ],
        reports_to=ICSRole.INCIDENT_COMMANDER,
        coordinates_with=[ICSRole.LIAISON_OFFICER, ICSSRole.PUBLIC_INFO_OFFICER],
        required_skills=["Executive communication", "Customer management", "SLA knowledge"]
    ),
}


class ICSRoleManager:
    """
    Manages ICS role assignments for an incident.
    Handles activation, handoffs, and role coordination.
    """

    def __init__(self):
        self.assignments: Dict[ICSRole, RoleAssignment] = {}
        self.role_order = self._define_role_order()

    def _define_role_order(self) -> List[ICSRole]:
        """Define activation priority order for roles."""
        return [
            ICSRole.INCIDENT_COMMANDER,
            ICSRole.DEPUTY_IC,
            ICSRole.SAFETY_OFFICER,
            ICSRole.OPERATIONS_CHIEF,
            ICSRole.TECH_LEAD,
            ICSRole.SRE_LEAD,
            ICSRole.COMMUNICATIONS,
            ICSRole.DOCUMENTATION,
            ICSRole.PLANNING_CHIEF,
            ICSRole.LIAISON_OFFICER,
            ICSRole.PUBLIC_INFO_OFFICER,
            ICSRole.STACKHOLDER_MGMT,
            ICSRole.LOGISTICS_CHIEF,
            ICSRole.AI_RCA_AGENT,
            ICSRole.DATA_ANALYST,
            ICSRole.DEVELOPER,
            ICSRole.FINANCE_CHIEF,
        ]

    def assign_role(
        self,
        role: ICSRole,
        person_name: str,
        person_id: str,
        notes: str = ""
    ) -> RoleAssignment:
        """Assign a person to an ICS role."""
        # Check if role already assigned
        if role in self.assignments:
            existing = self.assignments[role]
            if existing.status in [RoleStatus.ASSIGNED, RoleStatus.ACTIVE]:
                logger.warning(f"Role {role.value} already assigned to {existing.person_name}")
                # Relieve existing assignment
                existing.relieve(person_name, f"Reassigned to {person_name}")

        assignment = RoleAssignment(
            role=role,
            person_name=person_name,
            person_id=person_id,
            notes=notes
        )
        assignment.activate()
        self.assignments[role] = assignment
        logger.info(f"Assigned {person_name} to {role.value}")
        return assignment

    def relieve_role(self, role: ICSRole, relieved_by: str, notes: str = "") -> bool:
        """Relieve a person from an ICS role."""
        if role not in self.assignments:
            return False

        self.assignments[role].relieve(relieved_by, notes)
        logger.info(f"Relieved {role.value} by {relieved_by}")
        return True

    def reassign_role(self, role: ICSRole, new_person: str, new_person_id: str, notes: str = "") -> RoleAssignment:
        """Reassign a role to a new person (handoff)."""
        old_assignment = self.assignments.get(role)
        if old_assignment:
            old_assignment.relieve(new_person, f"Handoff to {new_person}: {notes}")

        return self.assign_role(role, new_person, new_person_id, notes)

    def get_assignment(self, role: ICSRole) -> Optional[RoleAssignment]:
        """Get current assignment for a role."""
        return self.assignments.get(role)

    def get_active_assignments(self) -> List[RoleAssignment]:
        """Get all active role assignments."""
        return [a for a in self.assignments.values() if a.status == RoleStatus.ACTIVE]

    def get_role_summary(self) -> Dict[str, Any]:
        """Get summary of all role assignments."""
        summary = {}
        for role in self.role_order:
            assignment = self.assignments.get(role)
            if assignment:
                summary[role.value] = {
                    "person": assignment.person_name,
                    "person_id": assignment.person_id,
                    "status": assignment.status.value,
                    "assigned_at": assignment.assigned_at.isoformat(),
                    "notes": assignment.notes
                }
            else:
                summary[role.value] = {"status": "unassigned"}
        return summary

    def get_reporting_chain(self, role: ICSRole) -> List[ICSRole]:
        """Get the reporting chain for a role up to IC."""
        chain = []
        current = role
        responsibilities = ICS_RESPONSIBILITIES.get(role)

        while responsibilities and responsibilities.reports_to:
            chain.append(responsibilities.reports_to)
            current = responsibilities.reports_to
            responsibilities = ICS_RESPONSIBILITIES.get(current)

        return chain

    def get_coordination_roles(self, role: ICSRole) -> List[ICSRole]:
        """Get roles this role coordinates with."""
        responsibilities = ICS_RESPONSIBILITIES.get(role)
        if responsibilities:
            return responsibilities.coordinates_with
        return []

    def validate_assignments(self, required_roles: List[ICSRole]) -> Dict[str, Any]:
        """Validate that required roles are filled."""
        missing = []
        unfilled = []
        issues = []

        for role in required_roles:
            assignment = self.assignments.get(role)
            if not assignment:
                missing.append(role.value)
            elif assignment.status != RoleStatus.ACTIVE:
                unfilled.append(f"{role.value} ({assignment.status.value})")

        # Check for IC without Deputy
        ic = self.assignments.get(ICSRole.INCIDENT_COMMANDER)
        deputy = self.assignments.get(ICSRole.DEPUTY_IC)
        if ic and ic.status == RoleStatus.ACTIVE and (not deputy or deputy.status != RoleStatus.ACTIVE):
            issues.append("Incident Commander active without active Deputy IC")

        # Check for Operations Chief without Tech Lead
        ops = self.assignments.get(ICSRole.OPERATIONS_CHIEF)
        tech = self.assignments.get(ICSRole.TECH_LEAD)
        if ops and ops.status == RoleStatus.ACTIVE and (not tech or tech.status != RoleStatus.ACTIVE):
            issues.append("Operations Chief active without Tech Lead")

        return {
            "valid": len(missing) == 0 and len(unfilled) == 0 and len(issues) == 0,
            "missing_roles": missing,
            "unfilled_roles": unfilled,
            "issues": issues,
            "total_assigned": len([a for a in self.assignments.values() if a.status == RoleStatus.ACTIVE])
        }

    def generate_handoff_document(self, role: ICSRole) -> str:
        """Generate handoff document for a role."""
        assignment = self.assignments.get(role)
        if not assignment:
            return f"No assignment for {role.value}"

        responsibilities = ICS_RESPONSIBILITIES.get(role)

        doc = f"""# Role Handoff: {role.value}

## Current Assignment
- **Role**: {role.value}
- **Current Owner**: {assignment.person_name} ({assignment.person_id})
- **Assigned**: {assignment.assigned_at.isoformat()}
- **Status**: {assignment.status.value}

## Key Responsibilities
"""
        if responsibilities:
            for resp in responsibilities.primary_responsibilities:
                doc += f"- {resp}\n"

        doc += "\n## Coordination Points\n"
        if responsibilities:
            for coord in responsibilities.coordinates_with:
                coord_assignment = self.assignments.get(coord)
                if coord_assignment:
                    doc += f"- {coord.value}: {coord_assignment.person_name}\n"
                else:
                    doc += f"- {coord.value}: UNASSIGNED\n"

        doc += "\n## Reporting Chain\n"
        chain = self.get_reporting_chain(role)
        for r in chain:
            r_assignment = self.assignments.get(r)
            if r_assignment:
                doc += f"- Reports to {r.value}: {r_assignment.person_name}\n"
            else:
                doc += f"- Reports to {r.value}: UNASSIGNED\n"

        doc += f"\n## Notes\n{assignment.notes or 'None'}\n"

        return doc


# Minimum role sets for different incident severities
SEVERITY_ROLE_REQUIREMENTS = {
    "SEV-1": [
        ICSRole.INCIDENT_COMMANDER,
        ICSRole.DEPUTY_IC,
        ICSRole.SAFETY_OFFICER,
        ICSRole.OPERATIONS_CHIEF,
        ICSRole.TECH_LEAD,
        ICSRole.SRE_LEAD,
        ICSRole.COMMUNICATIONS,
        ICSRole.DOCUMENTATION,
        ICSRole.PLANNING_CHIEF,
        ICSRole.LIAISON_OFFICER,
        ICSRole.PUBLIC_INFO_OFFICER,
        ICSRole.STACKHOLDER_MGMT,
        ICSRole.AI_RCA_AGENT,
    ],
    "SEV-2": [
        ICSRole.INCIDENT_COMMANDER,
        ICSRole.OPERATIONS_CHIEF,
        ICSRole.TECH_LEAD,
        ICSRole.SRE_LEAD,
        ICSRole.COMMUNICATIONS,
        ICSRole.DOCUMENTATION,
        ICSRole.AI_RCA_AGENT,
    ],
    "SEV-3": [
        ICSRole.INCIDENT_COMMANDER,
        ICSRole.TECH_LEAD,
        ICSRole.COMMUNICATIONS,
        ICSRole.DOCUMENTATION,
    ],
    "SEV-4": [
        ICSRole.INCIDENT_COMMANDER,
        ICSRole.TECH_LEAD,
    ],
}


def create_ics_manager() -> ICSRoleManager:
    """Factory function to create an ICSRoleManager."""
    return ICSRoleManager()


if __name__ == "__main__":
    # Demo
    logging.basicConfig(level=logging.INFO)

    manager = create_ics_manager()

    # Assign roles for SEV-1
    print("=== Assigning SEV-1 Roles ===")
    for role in SEVERITY_ROLE_REQUIREMENTS["SEV-1"][:5]:
        manager.assign_role(role, f"Engineer-{role.value}", f"slack-id-{role.value}")

    # Show summary
    print("\n=== Role Summary ===")
    for role, info in manager.get_role_summary().items():
        if info.get("status") != "unassigned":
            print(f"  {role}: {info['person']} ({info['status']})")

    # Validate
    print("\n=== Validation ===")
    validation = manager.validate_assignments(SEVERITY_ROLE_REQUIREMENTS["SEV-1"])
    print(f"  Valid: {validation['valid']}")
    print(f"  Missing: {validation['missing_roles']}")
    print(f"  Issues: {validation['issues']}")

    # Generate handoff
    print("\n=== Handoff Document for Operations Chief ===")
    print(manager.generate_handoff_document(ICSRole.OPERATIONS_CHIEF))

    # Test reassignment
    print("\n=== Reassigning Tech Lead ===")
    manager.reassign_role(ICSRole.TECH_LEAD, "New-Tech-Lead", "slack-new-tech")
    print(f"  New assignment: {manager.get_assignment(ICSRole.TECH_LEAD).person_name}")