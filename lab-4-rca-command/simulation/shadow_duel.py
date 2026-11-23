"""
Shadow Duel Framework - Human vs AI Parallel Investigation
============================================================

This module implements the Shadow Duel exercise where a human investigator
and an AI RCA agent investigate the same incident scenario in parallel,
with their processes and outcomes compared for learning purposes.

Key Components:
- DuelScenario: Scenario configuration for shadow duels
- Investigator: Base class for both human and AI investigators
- HumanInvestigator: Tracks human investigation steps (manual input)
- AIInvestigator: Wraps the RCA agent for automated investigation
- DuelOrchestrator: Runs parallel investigations, collects comparison metrics
- ComparisonMetrics: Detailed comparison of investigation approaches
- DuelReport: Comprehensive report with findings, learnings, recommendations

Pedagogical Goals:
- Demonstrate AI-assisted incident response capabilities
- Identify human cognitive biases in incident investigation
- Show where AI excels (pattern matching, speed) vs humans (context, judgment)
- Train investigators to effectively collaborate with AI tools
- Build trust in AI-assisted RCA through controlled comparison
"""

import asyncio
import json
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Any, Callable, Set
from pathlib import Path
import threading
from collections import defaultdict
import logging

# Import RCA agent components
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "rca-agent"))
from agent import RCAAgent, InvestigationState, RCAResult
from evidence_collector import EvidenceCollector, EvidenceBundle
from hypothesis_engine import HypothesisEngine, Hypothesis
from confidence_scorer import ConfidenceScorer, ConfidenceScore

# Import knowledge base
sys.path.insert(0, str(Path(__file__).parent.parent / "knowledge-base"))
from vector_store import VectorStore, SearchResult
from incident_ingest import IncidentIngestPipeline, IngestedIncident
from runbook_parser import RunbookParser, ParsedRunbook, RunbookIngestor
from architecture_docs import ArchitectureDocParser, ArchitectureDocIngestor

# Import incident command
sys.path.insert(0, str(Path(__file__).parent.parent / "incident-command"))
from ics_roles import ICSRoleManager, ICSRole, RoleAssignment, IncidentSeverity
from incident_timeline import IncidentTimeline, TimelineEvent, EventType, EventSeverity
from escalation_policy import EscalationPolicy, EscalationExecution, EscalationRule
from communication_channels import CommunicationManager, ChannelType

logger = logging.getLogger(__name__)


class InvestigatorType(Enum):
    HUMAN = "human"
    AI = "ai"


class InvestigationPhase(Enum):
    """Phases of investigation in shadow duel"""
    INITIALIZATION = "initialization"
    EVIDENCE_GATHERING = "evidence_gathering"
    HYPOTHESIS_FORMATION = "hypothesis_formation"
    HYPOTHESIS_TESTING = "hypothesis_testing"
    ROOT_CAUSE_IDENTIFICATION = "root_cause_identification"
    MITIGATION_PLANNING = "mitigation_planning"
    DOCUMENTATION = "documentation"
    COMPLETE = "complete"


class StepType(Enum):
    """Types of investigation steps"""
    QUERY_METRICS = "query_metrics"
    QUERY_LOGS = "query_logs"
    QUERY_TRACES = "query_traces"
    CHECK_RUNBOOK = "check_runbook"
    CHECK_KB = "check_knowledge_base"
    CHECK_ARCHITECTURE = "check_architecture"
    FORM_HYPOTHESIS = "form_hypothesis"
    TEST_HYPOTHESIS = "test_hypothesis"
    CONSULT_TEAM = "consult_team"
    ESCALATE = "escalate"
    DOCUMENT_FINDING = "document_finding"
    DECIDE_ACTION = "decide_action"
    EXECUTE_MITIGATION = "execute_mitigation"
    VERIFY_FIX = "verify_fix"


@dataclass
class InvestigationStep:
    """A single step in an investigation"""
    step_id: str
    investigator_id: str
    investigator_type: InvestigatorType
    phase: InvestigationPhase
    step_type: StepType
    timestamp: datetime
    description: str
    input_data: Dict[str, Any] = field(default_factory=dict)
    output_data: Dict[str, Any] = field(default_factory=dict)
    duration_ms: int = 0
    success: bool = True
    confidence: float = 0.0
    notes: str = ""
    # For human investigator
    human_reasoning: str = ""
    # For AI investigator
    ai_prompt: str = ""
    ai_response: str = ""
    tokens_used: int = 0


@dataclass
class InvestigatorState:
    """Current state of an investigator"""
    investigator_id: str
    investigator_type: InvestigatorType
    current_phase: InvestigationPhase
    steps: List[InvestigationStep] = field(default_factory=list)
    active_hypotheses: List[str] = field(default_factory=list)
    evidence_collected: List[str] = field(default_factory=list)
    knowledge_accessed: List[str] = field(default_factory=list)
    start_time: datetime = field(default_factory=datetime.now)
    last_update: datetime = field(default_factory=datetime.now)
    is_complete: bool = False
    final_root_cause: str = ""
    final_confidence: float = 0.0
    mitigation_actions: List[str] = field(default_factory=list)


@dataclass
class DuelScenario:
    """Configuration for a shadow duel scenario"""
    scenario_id: str
    name: str
    description: str
    incident_context: Dict[str, Any]
    injected_failures: List[Dict[str, Any]]
    expected_root_cause: str
    expected_mitigations: List[str]
    learning_objectives: List[str]
    difficulty: str  # "beginner", "intermediate", "advanced"
    estimated_duration_minutes: int
    # Constraints
    time_limit_minutes: int = 60
    max_human_steps: int = 50
    max_ai_steps: int = 100
    # Knowledge base access
    allow_kb_access: bool = True
    allow_runbook_access: bool = True
    allow_architecture_access: bool = True
    allow_team_consultation: bool = True
    # Scoring weights
    scoring_weights: Dict[str, float] = field(default_factory=lambda: {
        "accuracy": 0.4,
        "speed": 0.2,
        "process_quality": 0.2,
        "completeness": 0.1,
        "collaboration": 0.1
    })


@dataclass
class ComparisonMetrics:
    """Metrics comparing human vs AI investigation"""
    scenario_id: str
    human_investigator_id: str
    ai_investigator_id: str

    # Timing
    human_total_time_ms: int = 0
    ai_total_time_ms: int = 0
    human_phase_times: Dict[str, int] = field(default_factory=dict)
    ai_phase_times: Dict[str, int] = field(default_factory=dict)

    # Accuracy
    human_root_cause_correct: bool = False
    ai_root_cause_correct: bool = False
    human_root_cause_similarity: float = 0.0  # 0-1 similarity to expected
    ai_root_cause_similarity: float = 0.0

    # Process
    human_step_count: int = 0
    ai_step_count: int = 0
    human_unique_steps: int = 0  # Steps AI didn't take
    ai_unique_steps: int = 0     # Steps human didn't take
    common_steps: int = 0

    # Evidence
    human_evidence_count: int = 0
    ai_evidence_count: int = 0
    human_evidence_coverage: float = 0.0  # % of relevant evidence found
    ai_evidence_coverage: float = 0.0

    # Hypotheses
    human_hypothesis_count: int = 0
    ai_hypothesis_count: int = 0
    human_correct_hypotheses: int = 0
    ai_correct_hypotheses: int = 0

    # Knowledge access
    human_kb_queries: int = 0
    ai_kb_queries: int = 0
    human_runbook_queries: int = 0
    ai_runbook_queries: int = 0
    human_architecture_queries: int = 0
    ai_architecture_queries: int = 0

    # Quality scores (0-1)
    human_process_quality: float = 0.0
    ai_process_quality: float = 0.0
    human_completeness: float = 0.0
    ai_completeness: float = 0.0

    # Collaboration (if applicable)
    human_consulted_ai: bool = False
    ai_consulted_human: bool = False
    handoff_points: List[str] = field(default_factory=list)

    # Overall scores (weighted)
    human_overall_score: float = 0.0
    ai_overall_score: float = 0.0

    # Detailed findings
    human_strengths: List[str] = field(default_factory=list)
    human_weaknesses: List[str] = field(default_factory=list)
    ai_strengths: List[str] = field(default_factory=list)
    ai_weaknesses: List[str] = field(default_factory=list)
    key_learnings: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)


@dataclass
class DuelReport:
    """Comprehensive shadow duel report"""
    duel_id: str
    scenario: DuelScenario
    human_state: InvestigatorState
    ai_state: InvestigatorState
    metrics: ComparisonMetrics
    started_at: datetime
    completed_at: Optional[datetime] = None
    status: str = "in_progress"  # in_progress, completed, timeout, error
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "duel_id": self.duel_id,
            "scenario": asdict(self.scenario),
            "human_state": asdict(self.human_state),
            "ai_state": asdict(self.ai_state),
            "metrics": asdict(self.metrics),
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "status": self.status,
            "notes": self.notes
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, default=str)


class Investigator:
    """Base class for investigators"""

    def __init__(self, investigator_id: str, investigator_type: InvestigatorType,
                 scenario: DuelScenario, knowledge_base: VectorStore):
        self.investigator_id = investigator_id
        self.investigator_type = investigator_type
        self.scenario = scenario
        self.knowledge_base = knowledge_base
        self.state = InvestigatorState(
            investigator_id=investigator_id,
            investigator_type=investigator_type,
            current_phase=InvestigationPhase.INITIALIZATION
        )
        self._lock = threading.Lock()
        self._callbacks: List[Callable[[InvestigationStep], None]] = []

    def add_callback(self, callback: Callable[[InvestigationStep], None]):
        self._callbacks.append(callback)

    def _record_step(self, step: InvestigationStep):
        with self._lock:
            self.state.steps.append(step)
            self.state.last_update = datetime.now()
            if step.phase != self.state.current_phase:
                self.state.current_phase = step.phase
        for callback in self._callbacks:
            try:
                callback(step)
            except Exception as e:
                logger.error(f"Callback error: {e}")

    def get_state(self) -> InvestigatorState:
        with self._lock:
            return self.state

    async def investigate(self) -> InvestigatorState:
        raise NotImplementedError


class HumanInvestigator(Investigator):
    """
    Human investigator - tracks manual investigation steps.
    In practice, this would integrate with a UI for real-time step recording.
    For simulation, we can replay recorded human sessions or simulate.
    """

    def __init__(self, investigator_id: str, scenario: DuelScenario,
                 knowledge_base: VectorStore,
                 runbook_parser: RunbookParser,
                 architecture_parser: 'ArchitectureDocParser',
                 incident_timeline: IncidentTimeline,
                 communication_manager: CommunicationManager,
                 escalation_policy: EscalationPolicy):
        super().__init__(investigator_id, InvestigatorType.HUMAN, scenario, knowledge_base)
        self.runbook_parser = runbook_parser
        self.architecture_parser = architecture_parser
        self.incident_timeline = incident_timeline
        self.communication_manager = communication_manager
        self.escalation_policy = escalation_policy
        self._step_queue: asyncio.Queue = asyncio.Queue()
        self._running = False

    def record_step(self, phase: InvestigationPhase, step_type: StepType,
                    description: str, input_data: Dict[str, Any] = None,
                    output_data: Dict[str, Any] = None, duration_ms: int = 0,
                    success: bool = True, confidence: float = 0.0,
                    notes: str = "", human_reasoning: str = ""):
        """Record a human investigation step (called from UI or simulation)"""
        step = InvestigationStep(
            step_id=str(uuid.uuid4())[:8],
            investigator_id=self.investigator_id,
            investigator_type=InvestigatorType.HUMAN,
            phase=phase,
            step_type=step_type,
            timestamp=datetime.now(),
            description=description,
            input_data=input_data or {},
            output_data=output_data or {},
            duration_ms=duration_ms,
            success=success,
            confidence=confidence,
            notes=notes,
            human_reasoning=human_reasoning
        )
        self._record_step(step)
        return step

    async def simulate_investigation(self, steps: List[Dict[str, Any]]) -> InvestigatorState:
        """Simulate a human investigation from pre-recorded steps"""
        self._running = True
        for i, step_data in enumerate(steps):
            if not self._running:
                break
            await asyncio.sleep(step_data.get("delay_ms", 100) / 1000.0)
            self.record_step(
                phase=InvestigationPhase(step_data.get("phase", "evidence_gathering")),
                step_type=StepType(step_data.get("step_type", "query_metrics")),
                description=step_data.get("description", f"Step {i+1}"),
                input_data=step_data.get("input_data", {}),
                output_data=step_data.get("output_data", {}),
                duration_ms=step_data.get("duration_ms", 1000),
                success=step_data.get("success", True),
                confidence=step_data.get("confidence", 0.5),
                notes=step_data.get("notes", ""),
                human_reasoning=step_data.get("human_reasoning", "")
            )
        self.state.is_complete = True
        return self.state

    def stop(self):
        self._running = False

    async def investigate(self) -> InvestigatorState:
        """Wait for human steps to be recorded (for real-time use)"""
        self._running = True
        while self._running and not self.state.is_complete:
            try:
                step_data = await asyncio.wait_for(self._step_queue.get(), timeout=1.0)
                self.record_step(**step_data)
            except asyncio.TimeoutError:
                continue
        return self.state


class AIInvestigator(Investigator):
    """
    AI investigator - uses the RCA agent for automated investigation.
    """

    def __init__(self, investigator_id: str, scenario: DuelScenario,
                 knowledge_base: VectorStore,
                 rca_agent: RCAAgent,
                 evidence_collector: EvidenceCollector,
                 hypothesis_engine: HypothesisEngine,
                 confidence_scorer: ConfidenceScorer,
                 runbook_parser: RunbookParser,
                 architecture_parser: 'ArchitectureDocParser'):
        super().__init__(investigator_id, InvestigatorType.AI, scenario, knowledge_base)
        self.rca_agent = rca_agent
        self.evidence_collector = evidence_collector
        self.hypothesis_engine = hypothesis_engine
        self.confidence_scorer = confidence_scorer
        self.runbook_parser = runbook_parser
        self.architecture_parser = architecture_parser
        self._tokens_used = 0

    async def investigate(self) -> InvestigatorState:
        """Run full automated investigation using RCA agent"""
        start_time = time.time()

        # Phase 1: Evidence Gathering
        await self._phase_evidence_gathering()

        # Phase 2: Hypothesis Formation
        await self._phase_hypothesis_formation()

        # Phase 3: Hypothesis Testing
        await self._phase_hypothesis_testing()

        # Phase 4: Root Cause Identification
        await self._phase_root_cause_identification()

        # Phase 5: Mitigation Planning
        await self._phase_mitigation_planning()

        # Phase 6: Documentation
        await self._phase_documentation()

        self.state.is_complete = True
        return self.state

    async def _phase_evidence_gathering(self):
        self.state.current_phase = InvestigationPhase.EVIDENCE_GATHERING

        # Query metrics
        step = self._create_step(
            InvestigationPhase.EVIDENCE_GATHERING,
            StepType.QUERY_METRICS,
            "Collect metrics from Prometheus via MCP",
            {"time_range": "1h", "services": "all"}
        )
        evidence_bundle = await self.evidence_collector.collect_evidence(
            incident_id=self.scenario.scenario_id,
            time_window_minutes=60
        )
        step.output_data = {"evidence_count": len(evidence_bundle.metrics),
                           "services_covered": list(set(m.service for m in evidence_bundle.metrics))}
        step.duration_ms = int((time.time() - start_time) * 1000)
        self._record_step(step)
        self.state.evidence_collected.extend([f"metric:{m.name}" for m in evidence_bundle.metrics])

        # Query logs
        step = self._create_step(
            InvestigationPhase.EVIDENCE_GATHERING,
            StepType.QUERY_LOGS,
            "Collect logs from Loki via MCP",
            {"time_range": "1h", "level": "error"}
        )
        # Logs already in evidence_bundle
        step.output_data = {"log_entries": len(evidence_bundle.logs),
                           "error_count": len([l for l in evidence_bundle.logs if l.level == "error"])}
        step.duration_ms = int((time.time() - start_time) * 1000)
        self._record_step(step)
        self.state.evidence_collected.extend([f"log:{l.service}" for l in evidence_bundle.logs])

        # Query traces
        step = self._create_step(
            InvestigationPhase.EVIDENCE_GATHERING,
            StepType.QUERY_TRACES,
            "Collect traces from Tempo via MCP",
            {"time_range": "1h", "min_duration_ms": 100}
        )
        step.output_data = {"traces_collected": len(evidence_bundle.traces),
                           "spans_analyzed": sum(len(t.spans) for t in evidence_bundle.traces)}
        step.duration_ms = int((time.time() - start_time) * 1000)
        self._record_step(step)
        self.state.evidence_collected.extend([f"trace:{t.trace_id}" for t in evidence_bundle.traces])

    async def _phase_hypothesis_formation(self):
        self.state.current_phase = InvestigationPhase.HYPOTHESIS_FORMATION

        # Check knowledge base for similar incidents
        step = self._create_step(
            InvestigationPhase.HYPOTHESIS_FORMATION,
            StepType.CHECK_KB,
            "Search knowledge base for similar incidents",
            {"query": self.scenario.incident_context.get("symptoms", ""), "top_k": 5}
        )
        similar = self.knowledge_base.search_similar_incidents(
            self.scenario.incident_context.get("symptoms", ""), top_k=5
        )
        step.output_data = {"similar_incidents": len(similar),
                           "top_match_score": similar[0].score if similar else 0}
        step.duration_ms = 500
        self._record_step(step)
        self.state.knowledge_accessed.extend([f"incident:{s.document.id}" for s in similar])

        # Check runbooks
        step = self._create_step(
            InvestigationPhase.HYPOTHESIS_FORMATION,
            StepType.CHECK_RUNBOOK,
            "Search runbooks for relevant procedures",
            {"symptoms": self.scenario.incident_context.get("symptoms", "")}
        )
        runbooks = self.runbook_parser.search_runbooks(
            self.scenario.incident_context.get("symptoms", ""), top_k=3
        )
        step.output_data = {"relevant_runbooks": len(runbooks)}
        step.duration_ms = 300
        self._record_step(step)
        self.state.knowledge_accessed.extend([f"runbook:{r.title}" for r in runbooks])

        # Check architecture docs
        step = self._create_step(
            InvestigationPhase.HYPOTHESIS_FORMATION,
            StepType.CHECK_ARCHITECTURE,
            "Search architecture docs for relevant components",
            {"components": self.scenario.incident_context.get("affected_services", [])}
        )
        arch_docs = self.architecture_parser.search_architecture(
            " ".join(self.scenario.incident_context.get("affected_services", [])), top_k=3
        )
        step.output_data = {"relevant_docs": len(arch_docs)}
        step.duration_ms = 300
        self._record_step(step)
        self.state.knowledge_accessed.extend([f"arch:{d.title}" for d in arch_docs])

        # Generate hypotheses using hypothesis engine
        step = self._create_step(
            InvestigationPhase.HYPOTHESIS_FORMATION,
            StepType.FORM_HYPOTHESIS,
            "Generate root cause hypotheses using AI",
            {"evidence_count": len(self.state.evidence_collected)}
        )
        hypotheses = await self.hypothesis_engine.generate_hypotheses(
            evidence=self._get_evidence_bundle(),
            context=self.scenario.incident_context
        )
        step.output_data = {"hypotheses_generated": len(hypotheses),
                           "top_hypothesis": hypotheses[0].description if hypotheses else "None"}
        step.duration_ms = 2000
        self._record_step(step)
        self.state.active_hypotheses = [h.hypothesis_id for h in hypotheses]

    async def _phase_hypothesis_testing(self):
        self.state.current_phase = InvestigationPhase.HYPOTHESIS_TESTING

        hypotheses = await self.hypothesis_engine.generate_hypotheses(
            evidence=self._get_evidence_bundle(),
            context=self.scenario.incident_context
        )

        for hypothesis in hypotheses[:3]:  # Test top 3
            step = self._create_step(
                InvestigationPhase.HYPOTHESIS_TESTING,
                StepType.TEST_HYPOTHESIS,
                f"Test hypothesis: {hypothesis.description}",
                {"hypothesis_id": hypothesis.hypothesis_id, "type": hypothesis.category.value}
            )
            # Score confidence
            confidence = await self.confidence_scorer.score_hypothesis(
                hypothesis=hypothesis,
                evidence=self._get_evidence_bundle(),
                historical_data=self._get_historical_data()
            )
            step.output_data = {
                "confidence_score": confidence.final_score,
                "confidence_level": confidence.confidence_level.value,
                "supporting_evidence": len(confidence.supporting_evidence),
                "contradicting_evidence": len(confidence.contradicting_evidence)
            }
            step.confidence = confidence.final_score
            step.duration_ms = 1500
            self._record_step(step)

    async def _phase_root_cause_identification(self):
        self.state.current_phase = InvestigationPhase.ROOT_CAUSE_IDENTIFICATION

        step = self._create_step(
            InvestigationPhase.ROOT_CAUSE_IDENTIFICATION,
            StepType.FORM_HYPOTHESIS,
            "Determine final root cause from tested hypotheses",
            {"tested_hypotheses": len(self.state.active_hypotheses)}
        )

        # Run full RCA agent to get final result
        rca_result = await self.rca_agent.investigate(
            incident_id=self.scenario.scenario_id,
            context=self.scenario.incident_context
        )

        self.state.final_root_cause = rca_result.root_cause
        self.state.final_confidence = rca_result.confidence
        self.state.active_hypotheses = [h.hypothesis_id for h in rca_result.hypotheses]

        step.output_data = {
            "root_cause": rca_result.root_cause,
            "confidence": rca_result.confidence,
            "contributing_factors": rca_result.contributing_factors
        }
        step.confidence = rca_result.confidence
        step.duration_ms = 3000
        self._record_step(step)

    async def _phase_mitigation_planning(self):
        self.state.current_phase = InvestigationPhase.MITIGATION_PLANNING

        step = self._create_step(
            InvestigationPhase.MITIGATION_PLANNING,
            StepType.DECIDE_ACTION,
            "Plan mitigation actions based on root cause",
            {"root_cause": self.state.final_root_cause}
        )

        # Get mitigation suggestions from runbooks
        runbooks = self.runbook_parser.search_runbooks(
            self.state.final_root_cause, top_k=2
        )
        mitigations = []
        for rb in runbooks:
            mitigations.extend([s.description for s in rb.mitigation_steps])

        self.state.mitigation_actions = mitigations[:5]  # Top 5

        step.output_data = {
            "mitigation_actions": self.state.mitigation_actions,
            "runbooks_referenced": [r.title for r in runbooks]
        }
        step.duration_ms = 1000
        self._record_step(step)

    async def _phase_documentation(self):
        self.state.current_phase = InvestigationPhase.DOCUMENTATION

        step = self._create_step(
            InvestigationPhase.DOCUMENTATION,
            StepType.DOCUMENT_FINDING,
            "Document investigation findings and timeline",
            {"steps_count": len(self.state.steps)}
        )

        # Create summary
        summary = {
            "incident_id": self.scenario.scenario_id,
            "root_cause": self.state.final_root_cause,
            "confidence": self.state.final_confidence,
            "evidence_collected": len(self.state.evidence_collected),
            "hypotheses_tested": len(self.state.active_hypotheses),
            "mitigations": self.state.mitigation_actions,
            "duration_ms": int((time.time() - self.state.start_time.timestamp()) * 1000),
            "steps": len(self.state.steps)
        }

        step.output_data = summary
        step.duration_ms = 500
        self._record_step(step)

        self.state.current_phase = InvestigationPhase.COMPLETE

    def _create_step(self, phase: InvestigationPhase, step_type: StepType,
                     description: str, input_data: Dict[str, Any]) -> InvestigationStep:
        return InvestigationStep(
            step_id=str(uuid.uuid4())[:8],
            investigator_id=self.investigator_id,
            investigator_type=InvestigatorType.AI,
            phase=phase,
            step_type=step_type,
            timestamp=datetime.now(),
            description=description,
            input_data=input_data,
            output_data={},
            duration_ms=0,
            success=True,
            confidence=0.0,
            ai_prompt="",
            ai_response="",
            tokens_used=0
        )

    def _get_evidence_bundle(self) -> EvidenceBundle:
        # Re-collect evidence for hypothesis testing
        return asyncio.run(self.evidence_collector.collect_evidence(
            incident_id=self.scenario.scenario_id,
            time_window_minutes=60
        ))

    def _get_historical_data(self) -> List[Dict[str, Any]]:
        # Get historical incidents from knowledge base
        similar = self.knowledge_base.search_similar_incidents(
            self.scenario.incident_context.get("symptoms", ""), top_k=10
        )
        return [{"incident_id": s.document.id, "root_cause": s.document.metadata.get("root_cause", ""),
                 "resolution": s.document.metadata.get("resolution", "")} for s in similar]


class DuelOrchestrator:
    """
    Orchestrates shadow duel - runs human and AI investigations in parallel,
    collects comparison metrics, generates comprehensive report.
    """

    def __init__(self, scenario: DuelScenario, knowledge_base: VectorStore,
                 rca_agent: RCAAgent,
                 evidence_collector: EvidenceCollector,
                 hypothesis_engine: HypothesisEngine,
                 confidence_scorer: ConfidenceScorer,
                 runbook_parser: RunbookParser,
                 architecture_parser: 'ArchitectureDocParser',
                 incident_timeline: IncidentTimeline,
                 communication_manager: CommunicationManager,
                 escalation_policy: EscalationPolicy):
        self.scenario = scenario
        self.knowledge_base = knowledge_base
        self.rca_agent = rca_agent
        self.evidence_collector = evidence_collector
        self.hypothesis_engine = hypothesis_engine
        self.confidence_scorer = confidence_scorer
        self.runbook_parser = runbook_parser
        self.architecture_parser = architecture_parser
        self.incident_timeline = incident_timeline
        self.communication_manager = communication_manager
        self.escalation_policy = escalation_policy

        self.human_investigator: Optional[HumanInvestigator] = None
        self.ai_investigator: Optional[AIInvestigator] = None
        self.metrics: Optional[ComparisonMetrics] = None
        self.duel_report: Optional[DuelReport] = None
        self._start_time: Optional[datetime] = None
        _callbacks: List[Callable[[str, InvestigationStep], None]] = []

    def add_observer(self, callback: Callable[[str, InvestigationStep], None]):
        """Add observer for step events: callback(investigator_type, step)"""
        _callbacks.append(callback)

    async def run_duel(self, human_steps: Optional[List[Dict[str, Any]]] = None) -> DuelReport:
        """Run the shadow duel with optional pre-recorded human steps"""
        self._start_time = datetime.now()
        duel_id = f"duel-{self.scenario.scenario_id}-{uuid.uuid4().hex[:8]}"

        # Initialize investigators
        self.human_investigator = HumanInvestigator(
            investigator_id=f"human-{uuid.uuid4().hex[:8]}",
            scenario=self.scenario,
            knowledge_base=self.knowledge_base,
            runbook_parser=self.runbook_parser,
            architecture_parser=self.architecture_parser,
            incident_timeline=self.incident_timeline,
            communication_manager=self.communication_manager,
            escalation_policy=self.escalation_policy
        )

        self.ai_investigator = AIInvestigator(
            investigator_id=f"ai-{uuid.uuid4().hex[:8]}",
            scenario=self.scenario,
            knowledge_base=self.knowledge_base,
            rca_agent=self.rca_agent,
            evidence_collector=self.evidence_collector,
            hypothesis_engine=self.hypothesis_engine,
            confidence_scorer=self.confidence_scorer,
            runbook_parser=self.runbook_parser,
            architecture_parser=self.architecture_parser
        )

        # Add observers
        def human_observer(step):
            for cb in _callbacks:
                try:
                    cb("human", step)
                except Exception:
                    pass

        def ai_observer(step):
            for cb in _callbacks:
                try:
                    cb("ai", step)
                except Exception:
                    pass

        self.human_investigator.add_callback(human_observer)
        self.ai_investigator.add_callback(ai_observer)

        # Run investigations in parallel
        human_task = asyncio.create_task(
            self.human_investigator.simulate_investigation(human_steps or [])
        )
        ai_task = asyncio.create_task(self.ai_investigator.investigate())

        # Wait for both with timeout
        try:
            await asyncio.wait_for(
                asyncio.gather(human_task, ai_task),
                timeout=self.scenario.time_limit_minutes * 60
            )
        except asyncio.TimeoutError:
            logger.warning(f"Duel {duel_id} timed out after {self.scenario.time_limit_minutes} minutes")

        # Compute comparison metrics
        self.metrics = self._compute_metrics()

        # Generate report
        self.duel_report = DuelReport(
            duel_id=duel_id,
            scenario=self.scenario,
            human_state=self.human_investigator.get_state(),
            ai_state=self.ai_investigator.get_state(),
            metrics=self.metrics,
            started_at=self._start_time,
            completed_at=datetime.now(),
            status="completed"
        )

        return self.duel_report

    def _compute_metrics(self) -> ComparisonMetrics:
        """Compute detailed comparison metrics between human and AI"""
        human_state = self.human_investigator.get_state()
        ai_state = self.ai_investigator.get_state()

        metrics = ComparisonMetrics(
            scenario_id=self.scenario.scenario_id,
            human_investigator_id=human_state.investigator_id,
            ai_investigator_id=ai_state.investigator_id
        )

        # Timing
        human_duration = (human_state.last_update - human_state.start_time).total_seconds() * 1000
        ai_duration = (ai_state.last_update - ai_state.start_time).total_seconds() * 1000
        metrics.human_total_time_ms = int(human_duration)
        metrics.ai_total_time_ms = int(ai_duration)

        # Phase times
        for phase in InvestigationPhase:
            human_phase_steps = [s for s in human_state.steps if s.phase == phase]
            ai_phase_steps = [s for s in ai_state.steps if s.phase == phase]
            if human_phase_steps:
                metrics.human_phase_times[phase.value] = sum(s.duration_ms for s in human_phase_steps)
            if ai_phase_steps:
                metrics.ai_phase_times[phase.value] = sum(s.duration_ms for s in ai_phase_steps)

        # Step counts
        metrics.human_step_count = len(human_state.steps)
        metrics.ai_step_count = len(ai_state.steps)

        # Step type comparison
        human_step_types = set((s.phase, s.step_type) for s in human_state.steps)
        ai_step_types = set((s.phase, s.step_type) for s in ai_state.steps)
        metrics.human_unique_steps = len(human_step_types - ai_step_types)
        metrics.ai_unique_steps = len(ai_step_types - human_step_types)
        metrics.common_steps = len(human_step_types & ai_step_types)

        # Accuracy - compare root cause to expected
        expected = self.scenario.expected_root_cause.lower()
        metrics.human_root_cause_correct = expected in human_state.final_root_cause.lower()
        metrics.ai_root_cause_correct = expected in ai_state.final_root_cause.lower()

        # Similarity scoring (simple keyword overlap)
        metrics.human_root_cause_similarity = self._compute_similarity(
            human_state.final_root_cause, self.scenario.expected_root_cause)
        metrics.ai_root_cause_similarity = self._compute_similarity(
            ai_state.final_root_cause, self.scenario.expected_root_cause)

        # Evidence
        metrics.human_evidence_count = len(human_state.evidence_collected)
        metrics.ai_evidence_count = len(ai_state.evidence_collected)

        # Hypotheses
        metrics.human_hypothesis_count = len([s for s in human_state.steps
                                              if s.step_type == StepType.FORM_HYPOTHESIS])
        metrics.ai_hypothesis_count = len([s for s in ai_state.steps
                                           if s.step_type == StepType.FORM_HYPOTHESIS])

        # Knowledge access
        metrics.human_kb_queries = len([s for s in human_state.steps
                                        if s.step_type == StepType.CHECK_KB])
        metrics.ai_kb_queries = len([s for s in ai_state.steps
                                     if s.step_type == StepType.CHECK_KB])
        metrics.human_runbook_queries = len([s for s in human_state.steps
                                             if s.step_type == StepType.CHECK_RUNBOOK])
        metrics.ai_runbook_queries = len([s for s in ai_state.steps
                                          if s.step_type == StepType.CHECK_RUNBOOK])
        metrics.human_architecture_queries = len([s for s in human_state.steps
                                                  if s.step_type == StepType.CHECK_ARCHITECTURE])
        metrics.ai_architecture_queries = len([s for s in ai_state.steps
                                               if s.step_type == StepType.CHECK_ARCHITECTURE])

        # Process quality scores
        metrics.human_process_quality = self._score_process_quality(human_state)
        metrics.ai_process_quality = self._score_process_quality(ai_state)

        # Completeness
        metrics.human_completeness = self._score_completeness(human_state)
        metrics.ai_completeness = self._score_completeness(ai_state)

        # Overall weighted scores
        weights = self.scenario.scoring_weights
        metrics.human_overall_score = (
            weights["accuracy"] * metrics.human_root_cause_similarity +
            weights["speed"] * (1 - min(metrics.human_total_time_ms / (self.scenario.time_limit_minutes * 60 * 1000), 1)) +
            weights["process_quality"] * metrics.human_process_quality +
            weights["completeness"] * metrics.human_completeness +
            weights["collaboration"] * 0.5  # Placeholder
        )
        metrics.ai_overall_score = (
            weights["accuracy"] * metrics.ai_root_cause_similarity +
            weights["speed"] * (1 - min(metrics.ai_total_time_ms / (self.scenario.time_limit_minutes * 60 * 1000), 1)) +
            weights["process_quality"] * metrics.ai_process_quality +
            weights["completeness"] * metrics.ai_completeness +
            weights["collaboration"] * 0.5
        )

        # Generate qualitative findings
        self._generate_qualitative_findings(metrics, human_state, ai_state)

        return metrics

    def _compute_similarity(self, text1: str, text2: str) -> float:
        """Simple keyword-based similarity"""
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())
        if not words1 or not words2:
            return 0.0
        intersection = words1 & words2
        union = words1 | words2
        return len(intersection) / len(union) if union else 0.0

    def _score_process_quality(self, state: InvestigatorState) -> float:
        """Score investigation process quality (0-1)"""
        if not state.steps:
            return 0.0

        score = 0.0
        # Phase coverage
        phases_covered = set(s.phase for s in state.steps)
        expected_phases = [InvestigationPhase.EVIDENCE_GATHERING,
                          InvestigationPhase.HYPOTHESIS_FORMATION,
                          InvestigationPhase.HYPOTHESIS_TESTING,
                          InvestigationPhase.ROOT_CAUSE_IDENTIFICATION]
        phase_score = len(phases_covered & set(expected_phases)) / len(expected_phases)
        score += phase_score * 0.4

        # Step diversity
        step_types = set(s.step_type for s in state.steps)
        diversity_score = min(len(step_types) / 8, 1.0)  # 8 major step types
        score += diversity_score * 0.3

        # Success rate
        success_rate = sum(1 for s in state.steps if s.success) / len(state.steps)
        score += success_rate * 0.2

        # Confidence progression
        confidences = [s.confidence for s in state.steps if s.confidence > 0]
        if confidences:
            avg_confidence = sum(confidences) / len(confidences)
            score += avg_confidence * 0.1

        return min(score, 1.0)

    def _score_completeness(self, state: InvestigatorState) -> float:
        """Score investigation completeness (0-1)"""
        score = 0.0

        # Has root cause
        if state.final_root_cause:
            score += 0.3

        # Has confidence
        if state.final_confidence > 0:
            score += 0.2

        # Has mitigation actions
        if state.mitigation_actions:
            score += 0.2

        # Covered all phases
        phases = set(s.phase for s in state.steps)
        required = {InvestigationPhase.EVIDENCE_GATHERING,
                   InvestigationPhase.HYPOTHESIS_FORMATION,
                   InvestigationPhase.HYPOTHESIS_TESTING,
                   InvestigationPhase.ROOT_CAUSE_IDENTIFICATION}
        if required.issubset(phases):
            score += 0.3

        return min(score, 1.0)

    def _generate_qualitative_findings(self, metrics: ComparisonMetrics,
                                        human_state: InvestigatorState,
                                        ai_state: InvestigatorState):
        """Generate qualitative findings and recommendations"""

        # Human strengths
        if metrics.human_root_cause_similarity > metrics.ai_root_cause_similarity:
            metrics.human_strengths.append("Better root cause identification accuracy")
        if metrics.human_unique_steps > metrics.ai_unique_steps:
            metrics.human_strengths.append("Explored unique investigation paths")
        if metrics.human_process_quality > metrics.ai_process_quality:
            metrics.human_strengths.append("Higher investigation process quality")
        if metrics.human_kb_queries > 0 and metrics.ai_kb_queries == 0:
            metrics.human_strengths.append("Effectively leveraged knowledge base")

        # Human weaknesses
        if metrics.human_total_time_ms > metrics.ai_total_time_ms * 2:
            metrics.human_weaknesses.append("Significantly slower than AI")
        if metrics.human_evidence_count < metrics.ai_evidence_count * 0.5:
            metrics.human_weaknesses.append("Collected less evidence than AI")
        if metrics.human_step_count < 5:
            metrics.human_weaknesses.append("Investigation may be too shallow")

        # AI strengths
        if metrics.ai_total_time_ms < metrics.human_total_time_ms:
            metrics.ai_strengths.append(f"Faster investigation ({metrics.ai_total_time_ms/1000:.1f}s vs {metrics.human_total_time_ms/1000:.1f}s)")
        if metrics.ai_evidence_count > metrics.human_evidence_count:
            metrics.ai_strengths.append("More comprehensive evidence collection")
        if metrics.ai_step_count > metrics.human_step_count:
            metrics.ai_strengths.append("More thorough step-by-step process")
        if metrics.ai_kb_queries > metrics.human_kb_queries:
            metrics.ai_strengths.append("Better knowledge base utilization")

        # AI weaknesses
        if metrics.ai_root_cause_similarity < metrics.human_root_cause_similarity:
            metrics.ai_weaknesses.append("Lower root cause accuracy than human")
        if metrics.ai_unique_steps == 0:
            metrics.ai_weaknesses.append("No unique investigation paths explored")
        if metrics.ai_process_quality < 0.5:
            metrics.ai_weaknesses.append("Process quality below threshold")

        # Key learnings
        if metrics.human_root_cause_correct and not metrics.ai_root_cause_correct:
            metrics.key_learnings.append("Human intuition outperformed AI on this scenario - review AI hypothesis generation")
        elif metrics.ai_root_cause_correct and not metrics.human_root_cause_correct:
            metrics.key_learnings.append("AI outperformed human - consider AI-first triage for similar incidents")
        else:
            metrics.key_learnings.append("Both human and AI reached similar conclusions - good calibration")

        if metrics.human_unique_steps > 0 and metrics.ai_unique_steps > 0:
            metrics.key_learnings.append("Complementary approaches - human+AI collaboration would be optimal")

        # Recommendations
        if metrics.ai_root_cause_similarity > 0.7:
            metrics.recommendations.append("Deploy AI RCA agent for initial triage on similar incident types")
        if metrics.human_process_quality > metrics.ai_process_quality:
            metrics.recommendations.append("Incorporate human investigation patterns into AI agent training")
        if metrics.common_steps / max(metrics.human_step_count, metrics.ai_step_count, 1) > 0.7:
            metrics.recommendations.append("High process alignment - AI can reliably replicate human investigation flow")
        metrics.recommendations.append("Run shadow duels regularly to maintain AI-human calibration")
        metrics.recommendations.append("Document unique human insights as runbooks for AI knowledge base")


# ============================================================
# Pre-built Shadow Duel Scenarios
# ============================================================

def create_shadow_duel_scenarios(knowledge_base: VectorStore) -> List[DuelScenario]:
    """Create standard shadow duel scenarios for training"""

    scenarios = []

    # Scenario 1: Latency Spike - Beginner
    scenarios.append(DuelScenario(
        scenario_id="shadow-duel-01",
        name="Latency Spike in Payment Service",
        description="Payment service latency increases 10x. Simple single-service issue.",
        incident_context={
            "symptoms": "Payment service p99 latency increased from 200ms to 2s",
            "affected_services": ["payment-service"],
            "severity": "SEV-2",
            "start_time": "2024-01-15T10:00:00Z"
        },
        injected_failures=[{
            "type": "latency_spike",
            "target": "payment-service",
            "parameters": {"multiplier": 10, "duration_seconds": 300}
        }],
        expected_root_cause="Database connection pool exhaustion in payment-service due to missing connection cleanup",
        expected_mitigations=[
            "Fix connection leak in payment-service",
            "Add connection pool monitoring",
            "Implement circuit breaker for database calls"
        ],
        learning_objectives=[
            "Practice basic evidence gathering from metrics and logs",
            "Learn to correlate latency spikes with resource exhaustion",
            "Compare human vs AI hypothesis generation for simple issues"
        ],
        difficulty="beginner",
        estimated_duration_minutes=20,
        time_limit_minutes=30
    ))

    # Scenario 2: Pod Crash Cascade - Intermediate
    scenarios.append(DuelScenario(
        scenario_id="shadow-duel-02",
        name="Pod Crash Cascade in Order Processing",
        description="Order service pods crashing causing cascade to inventory and notification services",
        incident_context={
            "symptoms": "Order service pods OOMKilled, inventory service errors, notification delays",
            "affected_services": ["order-service", "inventory-service", "notification-service"],
            "severity": "SEV-1",
            "start_time": "2024-02-20T14:30:00Z"
        },
        injected_failures=[{
            "type": "memory_leak",
            "target": "order-service",
            "parameters": {"leak_rate_mb_per_min": 50, "duration_seconds": 600}
        }, {
            "type": "pod_crash",
            "target": "order-service",
            "parameters": {"crash_probability": 0.3, "duration_seconds": 600}
        }],
        expected_root_cause="Memory leak in order-service XML parser causing OOM kills, cascading to downstream services via timeout retries",
        expected_mitigations=[
            "Fix memory leak in XML parser",
            "Add memory limits and OOM alerts",
            "Implement bulkhead pattern for downstream calls",
            "Add circuit breakers to prevent cascade"
        ],
        learning_objectives=[
            "Practice multi-service incident investigation",
            "Learn blast radius analysis using service dependency graph",
            "Compare human vs AI on cascade failure analysis"
        ],
        difficulty="intermediate",
        estimated_duration_minutes=40,
        time_limit_minutes=60
    ))

    # Scenario 3: CPU Exhaustion - Intermediate
    scenarios.append(DuelScenario(
        scenario_id="shadow-duel-03",
        name="CPU Exhaustion in Recommendation Engine",
        description="Recommendation service CPU at 100%, affecting all dependent services",
        incident_context={
            "symptoms": "Recommendation service CPU 100%, downstream timeouts, increased error rates",
            "affected_services": ["recommendation-service", "api-gateway", "user-service"],
            "severity": "SEV-2",
            "start_time": "2024-03-10T09:15:00Z"
        },
        injected_failures=[{
            "type": "cpu_exhaustion",
            "target": "recommendation-service",
            "parameters": {"cpu_percent": 95, "duration_seconds": 900}
        }],
        expected_root_cause="Inefficient recommendation algorithm triggered by new ML model version causing CPU saturation",
        expected_mitigations=[
            "Rollback ML model version",
            "Add CPU resource limits and autoscaling",
            "Optimize recommendation algorithm",
            "Add canary deployment for ML models"
        ],
        learning_objectives=[
            "Practice resource exhaustion diagnosis",
            "Learn to correlate deployments with performance regressions",
            "Compare AI's ability to detect deployment correlations"
        ],
        difficulty="intermediate",
        estimated_duration_minutes=35,
        time_limit_minutes=50
    ))

    # Scenario 4: Network Partition - Advanced
    scenarios.append(DuelScenario(
        scenario_id="shadow-duel-04",
        name="Network Partition Between Availability Zones",
        description="AZ network partition causing split-brain in distributed services",
        incident_context={
            "symptoms": "Intermittent service failures, data inconsistency, leader election thrashing",
            "affected_services": ["user-service", "order-service", "payment-service", "inventory-service"],
            "severity": "SEV-1",
            "start_time": "2024-04-05T16:45:00Z"
        },
        injected_failures=[{
            "type": "network_partition",
            "target": "az-b",
            "parameters": {"partition_duration_seconds": 1200, "packet_loss_percent": 80}
        }],
        expected_root_cause="Network partition between AZ-A and AZ-B causing consensus failures in etcd and database replication lag",
        expected_mitigations=[
            "Implement multi-AZ consensus with proper quorum",
            "Add network partition detection and automatic failover",
            "Configure database synchronous replication",
            "Add chaos engineering for network partition testing"
        ],
        learning_objectives=[
            "Practice complex distributed systems failure analysis",
            "Learn to identify split-brain and consensus issues",
            "Compare human vs AI on complex multi-AZ failures"
        ],
        difficulty="advanced",
        estimated_duration_minutes=60,
        time_limit_minutes=90
    ))

    # Scenario 5: Black Friday Multi-Failure - Advanced
    scenarios.append(DuelScenario(
        scenario_id="shadow-duel-05",
        name="Black Friday Multi-Service Degradation",
        description="Multiple simultaneous failures during peak traffic: latency, errors, resource exhaustion",
        incident_context={
            "symptoms": "High error rates across services, latency spikes, capacity exhaustion, queue backlogs",
            "affected_services": ["api-gateway", "auth-service", "payment-service", "order-service", "inventory-service", "notification-service"],
            "severity": "SEV-1",
            "start_time": "2024-11-29T12:00:00Z"
        },
        injected_failures=[{
            "type": "latency_spike",
            "target": "api-gateway",
            "parameters": {"multiplier": 5, "duration_seconds": 1800}
        }, {
            "type": "cpu_exhaustion",
            "target": "payment-service",
            "parameters": {"cpu_percent": 90, "duration_seconds": 1800}
        }, {
            "type": "pod_crash",
            "target": "inventory-service",
            "parameters": {"crash_probability": 0.2, "duration_seconds": 1800}
        }],
        expected_root_cause="Traffic surge 10x normal combined with insufficient autoscaling and missing circuit breakers causing cascade failure",
        expected_mitigations=[
            "Scale up all services immediately",
            "Enable aggressive circuit breakers",
            "Implement request queuing with priority",
            "Add predictive autoscaling for known events",
            "Conduct capacity planning for peak events"
        ],
        learning_objectives=[
            "Practice incident command under extreme pressure",
            "Learn multi-failure correlation and prioritization",
            "Compare human vs AI under high cognitive load"
        ],
        difficulty="advanced",
        estimated_duration_minutes=90,
        time_limit_minutes=120
    ))

    return scenarios


# ============================================================
# Demo / Test Functions
# ============================================================

async def run_shadow_duel_demo():
    """Run a demonstration shadow duel"""
    print("=" * 60)
    print("SHADOW DUEL DEMONSTRATION")
    print("=" * 60)

    # Setup mock components (in reality these would be real instances)
    class MockVectorStore:
        def search_similar_incidents(self, query, top_k=5):
            return []

    class MockRCAAgent:
        async def investigate(self, incident_id, context):
            class MockResult:
                root_cause = "Database connection pool exhaustion in payment-service"
                confidence = 0.92
                hypotheses = []
                contributing_factors = ["Missing connection cleanup", "High request volume"]
            return MockResult()

    class MockEvidenceCollector:
        async def collect_evidence(self, incident_id, time_window_minutes):
            class MockBundle:
                metrics = []
                logs = []
                traces = []
            return MockBundle()

    class MockHypothesisEngine:
        async def generate_hypotheses(self, evidence, context):
            return []

    class MockConfidenceScorer:
        async def score_hypothesis(self, hypothesis, evidence, historical_data):
            class MockScore:
                final_score = 0.85
                confidence_level = type('obj', (object,), {'value': 'high'})()
                supporting_evidence = []
                contradicting_evidence = []
            return MockScore()

    class MockRunbookParser:
        def search_runbooks(self, query, top_k=3):
            return []

    class MockArchitectureParser:
        def search_architecture(self, query, top_k=3):
            return []

    class MockTimeline:
        pass

    class MockCommManager:
        pass

    class MockEscalationPolicy:
        pass

    # Create components
    kb = MockVectorStore()
    rca_agent = MockRCAAgent()
    evidence_collector = MockEvidenceCollector()
    hypothesis_engine = MockHypothesisEngine()
    confidence_scorer = MockConfidenceScorer()
    runbook_parser = MockRunbookParser()
    architecture_parser = MockArchitectureParser()
    incident_timeline = MockTimeline()
    communication_manager = MockCommManager()
    escalation_policy = MockEscalationPolicy()

    # Get scenarios
    scenarios = create_shadow_duel_scenarios(kb)

    # Run first scenario
    scenario = scenarios[0]
    print(f"\nRunning scenario: {scenario.name}")
    print(f"Difficulty: {scenario.difficulty}")
    print(f"Expected duration: {scenario.estimated_duration_minutes} minutes")

    # Simulated human steps (what a human might do)
    human_steps = [
        {
            "phase": "evidence_gathering",
            "step_type": "query_metrics",
            "description": "Check payment service latency dashboard",
            "input_data": {"dashboard": "payment-service-latency"},
            "output_data": {"p99_latency": "2.1s", "normal": "200ms"},
            "duration_ms": 30000,
            "human_reasoning": "Starting with latency dashboard to confirm symptoms"
        },
        {
            "phase": "evidence_gathering",
            "step_type": "query_logs",
            "description": "Check payment service logs for errors",
            "input_data": {"service": "payment-service", "level": "error"},
            "output_data": {"errors": ["connection pool exhausted", "timeout acquiring connection"]},
            "duration_ms": 45000,
            "human_reasoning": "Logs show connection pool issues - likely root cause"
        },
        {
            "phase": "hypothesis_formation",
            "step_type": "form_hypothesis",
            "description": "Form hypothesis: connection pool exhaustion",
            "input_data": {"hypothesis": "Database connection pool exhausted due to leak"},
            "output_data": {"confidence": 0.8},
            "duration_ms": 15000,
            "human_reasoning": "Logs show 'connection pool exhausted' - strong signal"
        },
        {
            "phase": "hypothesis_testing",
            "step_type": "test_hypothesis",
            "description": "Verify connection pool metrics",
            "input_data": {"metric": "db_connection_pool_active"},
            "output_data": {"active": 100, "max": 100, "idle": 0},
            "duration_ms": 20000,
            "human_reasoning": "Pool at 100% capacity with 0 idle - confirms hypothesis"
        },
        {
            "phase": "root_cause_identification",
            "step_type": "form_hypothesis",
            "description": "Identify root cause: missing connection cleanup",
            "input_data": {},
            "output_data": {"root_cause": "Missing connection cleanup in payment-service after DB calls"},
            "duration_ms": 10000,
            "confidence": 0.9,
            "human_reasoning": "Code review shows missing finally block for connection close"
        },
        {
            "phase": "mitigation_planning",
            "step_type": "decide_action",
            "description": "Plan mitigation: fix connection leak",
            "input_data": {},
            "output_data": {"actions": ["Add try-finally for connections", "Add pool monitoring", "Deploy fix"]},
            "duration_ms": 15000,
            "human_reasoning": "Fix the leak, add monitoring to prevent recurrence"
        }
    ]

    # Create orchestrator
    orchestrator = DuelOrchestrator(
        scenario=scenario,
        knowledge_base=kb,
        rca_agent=rca_agent,
        evidence_collector=evidence_collector,
        hypothesis_engine=hypothesis_engine,
        confidence_scorer=confidence_scorer,
        runbook_parser=runbook_parser,
        architecture_parser=architecture_parser,
        incident_timeline=incident_timeline,
        communication_manager=communication_manager,
        escalation_policy=escalation_policy
    )

    # Run duel
    print("\nStarting shadow duel...")
    report = await orchestrator.run_duel(human_steps=human_steps)

    # Print results
    print("\n" + "=" * 60)
    print("SHADOW DUEL RESULTS")
    print("=" * 60)

    print(f"\nDuel ID: {report.duel_id}")
    print(f"Scenario: {report.scenario.name}")
    print(f"Status: {report.status}")
    print(f"Duration: {(report.completed_at - report.started_at).total_seconds():.1f}s")

    print(f"\n--- Human Investigator ---")
    print(f"  Steps: {report.metrics.human_step_count}")
    print(f"  Time: {report.metrics.human_total_time_ms/1000:.1f}s")
    print(f"  Root Cause Correct: {report.metrics.human_root_cause_correct}")
    print(f"  Root Cause Similarity: {report.metrics.human_root_cause_similarity:.2f}")
    print(f"  Process Quality: {report.metrics.human_process_quality:.2f}")
    print(f"  Completeness: {report.metrics.human_completeness:.2f}")
    print(f"  Overall Score: {report.metrics.human_overall_score:.2f}")
    print(f"  Strengths: {', '.join(report.metrics.human_strengths) or 'None'}")
    print(f"  Weaknesses: {', '.join(report.metrics.human_weaknesses) or 'None'}")

    print(f"\n--- AI Investigator ---")
    print(f"  Steps: {report.metrics.ai_step_count}")
    print(f"  Time: {report.metrics.ai_total_time_ms/1000:.1f}s")
    print(f"  Root Cause Correct: {report.metrics.ai_root_cause_correct}")
    print(f"  Root Cause Similarity: {report.metrics.ai_root_cause_similarity:.2f}")
    print(f"  Process Quality: {report.metrics.ai_process_quality:.2f}")
    print(f"  Completeness: {report.metrics.ai_completeness:.2f}")
    print(f"  Overall Score: {report.metrics.ai_overall_score:.2f}")
    print(f"  Strengths: {', '.join(report.metrics.ai_strengths) or 'None'}")
    print(f"  Weaknesses: {', '.join(report.metrics.ai_weaknesses) or 'None'}")

    print(f"\n--- Key Learnings ---")
    for learning in report.metrics.key_learnings:
        print(f"  * {learning}")

    print(f"\n--- Recommendations ---")
    for rec in report.metrics.recommendations:
        print(f"  * {rec}")

    return report


if __name__ == "__main__":
    asyncio.run(run_shadow_duel_demo())