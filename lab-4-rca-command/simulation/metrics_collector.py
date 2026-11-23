"""
Metrics Collector - Exercise Metrics, Timing, and Accuracy Scoring
===================================================================

This module provides comprehensive metrics collection and analysis for
AI SRE training exercises including shadow duels, chaos scenarios,
and incident response simulations.

Key Components:
- MetricsCollector: Central metrics aggregation and storage
- ExerciseMetrics: Metrics for individual exercises
- TimingAnalyzer: Detailed timing analysis and bottleneck detection
- AccuracyScorer: Root cause accuracy and hypothesis scoring
- PerformanceTracker: Track investigator/agent performance over time
- ReportGenerator: Generate detailed exercise reports with visualizations

Pedagogical Goals:
- Quantify learning progress across training sessions
- Identify skill gaps for targeted coaching
- Compare human vs AI performance objectively
- Track improvement trends over time
- Provide data-driven feedback for curriculum refinement
"""

import asyncio
import json
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Any, Callable, Set, Tuple
from pathlib import Path
from collections import defaultdict, deque
import statistics
import threading
import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class ExerciseType(Enum):
    SHADOW_DUEL = "shadow_duel"
    CHAOS_SCENARIO = "chaos_scenario"
    INCIDENT_RESPONSE = "incident_response"
    RCA_INVESTIGATION = "rca_investigation"
    ICS_ROLEPLAY = "ics_roleplay"
    RUNBOOK_EXECUTION = "runbook_execution"
    WAR_ROOM_SIMULATION = "war_room_simulation"


class MetricCategory(Enum):
    TIMING = "timing"
    ACCURACY = "accuracy"
    PROCESS = "process"
    COMPLETENESS = "completeness"
    COLLABORATION = "collaboration"
    LEARNING = "learning"


class MetricUnit(Enum):
    MILLISECONDS = "ms"
    SECONDS = "s"
    MINUTES = "min"
    PERCENTAGE = "%"
    COUNT = "count"
    SCORE = "score"  # 0-1
    BOOLEAN = "bool"


@dataclass
class MetricDefinition:
    """Definition of a metric"""
    metric_id: str
    name: str
    category: MetricCategory
    unit: MetricUnit
    description: str
    higher_is_better: bool = True
    target_value: Optional[float] = None
    warning_threshold: Optional[float] = None
    critical_threshold: Optional[float] = None


@dataclass
class MetricValue:
    """A single metric measurement"""
    metric_id: str
    value: float
    timestamp: datetime
    context: Dict[str, Any] = field(default_factory=dict)
    exercise_id: str = ""
    participant_id: str = ""
    participant_type: str = ""  # "human", "ai", "team"


@dataclass
class TimingBreakdown:
    """Detailed timing breakdown for an exercise phase"""
    phase: str
    start_time: datetime
    end_time: datetime
    duration_ms: int
    sub_phases: Dict[str, int] = field(default_factory=dict)  # sub-phase -> duration_ms
    wait_time_ms: int = 0
    active_time_ms: int = 0
    idle_periods: List[Tuple[datetime, datetime]] = field(default_factory=list)


@dataclass
class AccuracyAssessment:
    """Accuracy assessment for root cause identification"""
    expected_root_cause: str
    actual_root_cause: str
    similarity_score: float  # 0-1
    keyword_match_score: float  # 0-1
    semantic_similarity: float  # 0-1 (if embeddings available)
    is_correct: bool
    partial_credit: float  # 0-1 for partially correct answers
    feedback: str = ""


@dataclass
class ProcessQualityMetrics:
    """Process quality metrics for an investigation"""
    phase_coverage: float  # 0-1, % of expected phases completed
    step_diversity: float  # 0-1, variety of step types used
    success_rate: float  # 0-1, % of successful steps
    evidence_thoroughness: float  # 0-1, evidence collected vs available
    hypothesis_quality: float  # 0-1, quality of hypotheses generated
    documentation_completeness: float  # 0-1, documentation quality
    tool_usage_effectiveness: float  # 0-1, effective use of tools
    overall_score: float  # 0-1, weighted composite


@dataclass
class ExerciseMetrics:
    """Complete metrics for a single exercise execution"""
    exercise_id: str
    exercise_type: ExerciseType
    scenario_id: str
    participant_id: str
    participant_type: str  # "human", "ai", "team"
    started_at: datetime
    completed_at: Optional[datetime] = None
    status: str = "in_progress"  # in_progress, completed, timeout, failed

    # Timing
    total_duration_ms: int = 0
    phase_timings: List[TimingBreakdown] = field(default_factory=list)
    time_to_first_action_ms: int = 0
    time_to_root_cause_ms: int = 0
    time_to_mitigation_ms: int = 0

    # Accuracy
    accuracy_assessment: Optional[AccuracyAssessment] = None
    hypothesis_accuracy: List[Dict[str, Any]] = field(default_factory=list)

    # Process
    process_quality: Optional[ProcessQualityMetrics] = None
    step_count: int = 0
    unique_step_types: int = 0
    evidence_collected_count: int = 0
    hypotheses_generated: int = 0
    hypotheses_tested: int = 0
    knowledge_base_queries: int = 0
    runbook_queries: int = 0
    team_consultations: int = 0

    # Completeness
    required_phases_completed: List[str] = field(default_factory=list)
    required_phases_missed: List[str] = field(default_factory=list)
    deliverables_produced: List[str] = field(default_factory=list)
    deliverables_missing: List[str] = field(default_factory=list)

    # Collaboration (for team exercises)
    communication_events: int = 0
    role_handoffs: int = 0
    escalation_events: int = 0
    decisions_documented: int = 0

    # Learning
    learning_objectives_met: List[str] = field(default_factory=list)
    learning_objectives_missed: List[str] = field(default_factory=list)
    skills_demonstrated: List[str] = field(default_factory=list)
    skills_needing_improvement: List[str] = field(default_factory=list)

    # Raw metric values
    metric_values: List[MetricValue] = field(default_factory=list)

    # Comparison (for shadow duels)
    comparison_metrics: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, default=str)


@dataclass
class ParticipantProfile:
    """Profile of a participant (human or AI) with historical performance"""
    participant_id: str
    participant_type: str  # "human", "ai"
    name: str
    role: str
    created_at: datetime
    total_exercises: int = 0
    completed_exercises: int = 0

    # Aggregate metrics
    avg_accuracy: float = 0.0
    avg_speed: float = 0.0  # exercises per hour
    avg_process_quality: float = 0.0
    avg_completeness: float = 0.0

    # Trend data (last 10 exercises)
    accuracy_trend: List[float] = field(default_factory=list)
    speed_trend: List[float] = field(default_factory=list)
    quality_trend: List[float] = field(default_factory=list)

    # Strengths and weaknesses
    strengths: List[str] = field(default_factory=list)
    weaknesses: List[str] = field(default_factory=list)
    skill_gaps: List[str] = field(default_factory=list)

    # Exercise history
    exercise_history: List[str] = field(default_factory=list)  # exercise_ids


@dataclass
class CohortMetrics:
    """Aggregate metrics for a cohort of participants"""
    cohort_id: str
    exercise_type: ExerciseType
    scenario_id: str
    participants: List[str]  # participant_ids
    exercise_count: int = 0

    # Aggregate statistics
    avg_accuracy: float = 0.0
    median_accuracy: float = 0.0
    accuracy_stddev: float = 0.0

    avg_duration_ms: int = 0
    median_duration_ms: int = 0
    duration_stddev: int = 0

    avg_process_quality: float = 0.0
    completion_rate: float = 0.0

    # Distribution
    accuracy_distribution: Dict[str, int] = field(default_factory=dict)  # range -> count
    duration_distribution: Dict[str, int] = field(default_factory=dict)

    # Top/bottom performers
    top_performers: List[str] = field(default_factory=list)
    needs_attention: List[str] = field(default_factory=list)


class MetricsStorage(ABC):
    """Abstract storage backend for metrics"""

    @abstractmethod
    async def save_exercise_metrics(self, metrics: ExerciseMetrics):
        pass

    @abstractmethod
    async def load_exercise_metrics(self, exercise_id: str) -> Optional[ExerciseMetrics]:
        pass

    @abstractmethod
    async def query_metrics(self,
                           participant_id: Optional[str] = None,
                           exercise_type: Optional[ExerciseType] = None,
                           scenario_id: Optional[str] = None,
                           start_date: Optional[datetime] = None,
                           end_date: Optional[datetime] = None,
                           limit: int = 100) -> List[ExerciseMetrics]:
        pass

    @abstractmethod
    async def save_participant_profile(self, profile: ParticipantProfile):
        pass

    @abstractmethod
    async def load_participant_profile(self, participant_id: str) -> Optional[ParticipantProfile]:
        pass


class InMemoryMetricsStorage(MetricsStorage):
    """In-memory metrics storage for development/testing"""

    def __init__(self):
        self._exercises: Dict[str, ExerciseMetrics] = {}
        self._profiles: Dict[str, ParticipantProfile] = {}
        self._lock = threading.Lock()

    async def save_exercise_metrics(self, metrics: ExerciseMetrics):
        with self._lock:
            self._exercises[metrics.exercise_id] = metrics

    async def load_exercise_metrics(self, exercise_id: str) -> Optional[ExerciseMetrics]:
        with self._lock:
            return self._exercises.get(exercise_id)

    async def query_metrics(self,
                           participant_id: Optional[str] = None,
                           exercise_type: Optional[ExerciseType] = None,
                           scenario_id: Optional[str] = None,
                           start_date: Optional[datetime] = None,
                           end_date: Optional[datetime] = None,
                           limit: int = 100) -> List[ExerciseMetrics]:
        with self._lock:
            results = list(self._exercises.values())

            if participant_id:
                results = [m for m in results if m.participant_id == participant_id]
            if exercise_type:
                results = [m for m in results if m.exercise_type == exercise_type]
            if scenario_id:
                results = [m for m in results if m.scenario_id == scenario_id]
            if start_date:
                results = [m for m in results if m.started_at >= start_date]
            if end_date:
                results = [m for m in results if m.started_at <= end_date]

            # Sort by start time descending
            results.sort(key=lambda m: m.started_at, reverse=True)
            return results[:limit]

    async def save_participant_profile(self, profile: ParticipantProfile):
        with self._lock:
            self._profiles[profile.participant_id] = profile

    async def load_participant_profile(self, participant_id: str) -> Optional[ParticipantProfile]:
        with self._lock:
            return self._profiles.get(participant_id)


class MetricsCollector:
    """
    Central metrics collection and aggregation system.
    Collects metrics from exercises, computes aggregates, tracks trends.
    """

    def __init__(self, storage: MetricsStorage = None):
        self.storage = storage or InMemoryMetricsStorage()
        self._active_exercises: Dict[str, ExerciseMetrics] = {}
        self._lock = threading.Lock()
        self._metric_definitions = self._initialize_metric_definitions()

    def _initialize_metric_definitions(self) -> Dict[str, MetricDefinition]:
        """Initialize standard metric definitions"""
        return {
            # Timing metrics
            "total_duration": MetricDefinition(
                metric_id="total_duration",
                name="Total Exercise Duration",
                category=MetricCategory.TIMING,
                unit=MetricUnit.MINUTES,
                description="Total time from exercise start to completion",
                higher_is_better=False,
                target_value=30,
                warning_threshold=60,
                critical_threshold=120
            ),
            "time_to_first_action": MetricDefinition(
                metric_id="time_to_first_action",
                name="Time to First Action",
                category=MetricCategory.TIMING,
                unit=MetricUnit.SECONDS,
                description="Time from exercise start to first investigative action",
                higher_is_better=False,
                target_value=30,
                warning_threshold=120,
                critical_threshold=300
            ),
            "time_to_root_cause": MetricDefinition(
                metric_id="time_to_root_cause",
                name="Time to Root Cause",
                category=MetricCategory.TIMING,
                unit=MetricUnit.MINUTES,
                description="Time from exercise start to root cause identification",
                higher_is_better=False,
                target_value=15,
                warning_threshold=30,
                critical_threshold=60
            ),

            # Accuracy metrics
            "root_cause_accuracy": MetricDefinition(
                metric_id="root_cause_accuracy",
                name="Root Cause Accuracy",
                category=MetricCategory.ACCURACY,
                unit=MetricUnit.SCORE,
                description="Similarity score between identified and actual root cause",
                higher_is_better=True,
                target_value=0.8,
                warning_threshold=0.5,
                critical_threshold=0.3
            ),
            "hypothesis_precision": MetricDefinition(
                metric_id="hypothesis_precision",
                name="Hypothesis Precision",
                category=MetricCategory.ACCURACY,
                unit=MetricUnit.SCORE,
                description="Fraction of generated hypotheses that were relevant",
                higher_is_better=True,
                target_value=0.7,
                warning_threshold=0.4,
                critical_threshold=0.2
            ),

            # Process metrics
            "phase_coverage": MetricDefinition(
                metric_id="phase_coverage",
                name="Investigation Phase Coverage",
                category=MetricCategory.PROCESS,
                unit=MetricUnit.PERCENTAGE,
                description="Percentage of expected investigation phases completed",
                higher_is_better=True,
                target_value=100,
                warning_threshold=75,
                critical_threshold=50
            ),
            "step_diversity": MetricDefinition(
                metric_id="step_diversity",
                name="Step Type Diversity",
                category=MetricCategory.PROCESS,
                unit=MetricUnit.COUNT,
                description="Number of different investigation step types used",
                higher_is_better=True,
                target_value=6,
                warning_threshold=3,
                critical_threshold=1
            ),
            "evidence_thoroughness": MetricDefinition(
                metric_id="evidence_thoroughness",
                name="Evidence Thoroughness",
                category=MetricCategory.PROCESS,
                unit=MetricUnit.PERCENTAGE,
                description="Percentage of available evidence collected",
                higher_is_better=True,
                target_value=80,
                warning_threshold=50,
                critical_threshold=25
            ),

            # Completeness metrics
            "deliverable_completeness": MetricDefinition(
                metric_id="deliverable_completeness",
                name="Deliverable Completeness",
                category=MetricCategory.COMPLETENESS,
                unit=MetricUnit.PERCENTAGE,
                description="Percentage of required deliverables produced",
                higher_is_better=True,
                target_value=100,
                warning_threshold=75,
                critical_threshold=50
            ),

            # Collaboration metrics
            "communication_frequency": MetricDefinition(
                metric_id="communication_frequency",
                name="Communication Frequency",
                category=MetricCategory.COLLABORATION,
                unit=MetricUnit.COUNT,
                description="Number of communication events during exercise",
                higher_is_better=True,
                target_value=10,
                warning_threshold=3,
                critical_threshold=1
            ),
        }

    def start_exercise(self, exercise_id: str, exercise_type: ExerciseType,
                       scenario_id: str, participant_id: str,
                       participant_type: str) -> ExerciseMetrics:
        """Start tracking a new exercise"""
        metrics = ExerciseMetrics(
            exercise_id=exercise_id,
            exercise_type=exercise_type,
            scenario_id=scenario_id,
            participant_id=participant_id,
            participant_type=participant_type,
            started_at=datetime.now()
        )

        with self._lock:
            self._active_exercises[exercise_id] = metrics

        return metrics

    def record_step(self, exercise_id: str, phase: str, step_type: str,
                    duration_ms: int, success: bool = True,
                    metadata: Dict[str, Any] = None):
        """Record an investigation step"""
        with self._lock:
            if exercise_id not in self._active_exercises:
                return

            metrics = self._active_exercises[exercise_id]
            metrics.step_count += 1

            # Track first action time
            if metrics.step_count == 1:
                metrics.time_to_first_action_ms = duration_ms

            # Record metric value
            metric_value = MetricValue(
                metric_id=f"step_{step_type}",
                value=duration_ms,
                timestamp=datetime.now(),
                context={"phase": phase, "step_type": step_type, "success": success, **(metadata or {})},
                exercise_id=exercise_id,
                participant_id=metrics.participant_id,
                participant_type=metrics.participant_type
            )
            metrics.metric_values.append(metric_value)

    def record_phase_timing(self, exercise_id: str, phase: str,
                            start_time: datetime, end_time: datetime,
                            sub_phases: Dict[str, int] = None):
        """Record phase timing breakdown"""
        with self._lock:
            if exercise_id not in self._active_exercises:
                return

            metrics = self._active_exercises[exercise_id]
            duration_ms = int((end_time - start_time).total_seconds() * 1000)

            timing = TimingBreakdown(
                phase=phase,
                start_time=start_time,
                end_time=end_time,
                duration_ms=duration_ms,
                sub_phases=sub_phases or {}
            )
            metrics.phase_timings.append(timing)

    def record_evidence_collected(self, exercise_id: str, count: int = 1):
        """Record evidence collection"""
        with self._lock:
            if exercise_id in self._active_exercises:
                self._active_exercises[exercise_id].evidence_collected_count += count

    def record_hypothesis(self, exercise_id: str, generated: bool = True, tested: bool = False):
        """Record hypothesis generation/testing"""
        with self._lock:
            if exercise_id in self._active_exercises:
                metrics = self._active_exercises[exercise_id]
                if generated:
                    metrics.hypotheses_generated += 1
                if tested:
                    metrics.hypotheses_tested += 1

    def record_kb_query(self, exercise_id: str):
        """Record knowledge base query"""
        with self._lock:
            if exercise_id in self._active_exercises:
                self._active_exercises[exercise_id].knowledge_base_queries += 1

    def record_runbook_query(self, exercise_id: str):
        """Record runbook query"""
        with self._lock:
            if exercise_id in self._active_exercises:
                self._active_exercises[exercise_id].runbook_queries += 1

    def record_communication(self, exercise_id: str):
        """Record communication event"""
        with self._lock:
            if exercise_id in self._active_exercises:
                self._active_exercises[exercise_id].communication_events += 1

    def record_escalation(self, exercise_id: str):
        """Record escalation event"""
        with self._lock:
            if exercise_id in self._active_exercises:
                self._active_exercises[exercise_id].escalation_events += 1

    def complete_exercise(self, exercise_id: str,
                          root_cause: str = "",
                          expected_root_cause: str = "",
                          mitigation_actions: List[str] = None,
                          deliverables: List[str] = None,
                          required_deliverables: List[str] = None,
                          required_phases: List[str] = None,
                          learning_objectives: List[str] = None) -> ExerciseMetrics:
        """Complete an exercise and compute final metrics"""
        with self._lock:
            if exercise_id not in self._active_exercises:
                return None

            metrics = self._active_exercises.pop(exercise_id)

        metrics.completed_at = datetime.now()
        metrics.status = "completed"
        metrics.total_duration_ms = int((metrics.completed_at - metrics.started_at).total_seconds() * 1000)

        # Compute phase coverage
        if required_phases:
            completed_phases = set(t.phase for t in metrics.phase_timings)
            metrics.required_phases_completed = [p for p in required_phases if p in completed_phases]
            metrics.required_phases_missed = [p for p in required_phases if p not in completed_phases]

        # Compute deliverable completeness
        if required_deliverables and deliverables:
            metrics.deliverables_produced = deliverables
            metrics.deliverables_missing = [d for d in required_deliverables if d not in deliverables]

        # Compute accuracy assessment
        if expected_root_cause and root_cause:
            metrics.accuracy_assessment = self._compute_accuracy(root_cause, expected_root_cause)

        # Compute process quality
        metrics.process_quality = self._compute_process_quality(metrics, required_phases)

        # Compute learning objectives
        if learning_objectives:
            metrics.learning_objectives_met = learning_objectives  # Simplified - would check actual completion
            metrics.learning_objectives_missed = []

        # Save to storage
        asyncio.create_task(self.storage.save_exercise_metrics(metrics))

        # Update participant profile
        asyncio.create_task(self._update_participant_profile(metrics))

        return metrics

    def _compute_accuracy(self, actual: str, expected: str) -> AccuracyAssessment:
        """Compute accuracy assessment for root cause"""
        # Simple keyword-based similarity
        actual_words = set(actual.lower().split())
        expected_words = set(expected.lower().split())

        if not actual_words or not expected_words:
            similarity = 0.0
        else:
            intersection = actual_words & expected_words
            union = actual_words | expected_words
            similarity = len(intersection) / len(union)

        # Keyword match for key terms
        key_terms = ["database", "connection", "pool", "memory", "cpu", "network",
                     "timeout", "cascade", "leak", "exhaustion", "partition"]
        actual_key_terms = actual_words & set(key_terms)
        expected_key_terms = expected_words & set(key_terms)
        if expected_key_terms:
            keyword_match = len(actual_key_terms & expected_key_terms) / len(expected_key_terms)
        else:
            keyword_match = 1.0 if not actual_key_terms else 0.5

        is_correct = similarity > 0.6 or keyword_match > 0.7
        partial_credit = max(similarity, keyword_match * 0.8)

        return AccuracyAssessment(
            expected_root_cause=expected,
            actual_root_cause=actual,
            similarity_score=similarity,
            keyword_match_score=keyword_match,
            semantic_similarity=similarity,  # Placeholder for embedding-based similarity
            is_correct=is_correct,
            partial_credit=partial_credit,
            feedback=self._generate_accuracy_feedback(similarity, keyword_match, is_correct)
        )

    def _generate_accuracy_feedback(self, similarity: float, keyword_match: float, is_correct: bool) -> str:
        if is_correct:
            return "Root cause correctly identified"
        elif similarity > 0.4:
            return "Partially correct - key concepts identified but missing specifics"
        elif keyword_match > 0.5:
            return "Correct domain identified but root cause not precise"
        else:
            return "Root cause not identified - review investigation approach"

    def _compute_process_quality(self, metrics: ExerciseMetrics,
                                  required_phases: List[str] = None) -> ProcessQualityMetrics:
        """Compute process quality metrics"""
        # Phase coverage
        if required_phases:
            completed = set(t.phase for t in metrics.phase_timings)
            phase_coverage = len(completed & set(required_phases)) / len(required_phases)
        else:
            expected = {"evidence_gathering", "hypothesis_formation", "hypothesis_testing",
                       "root_cause_identification", "mitigation_planning"}
            completed = set(t.phase for t in metrics.phase_timings)
            phase_coverage = len(completed & expected) / len(expected)

        # Step diversity
        step_types = set()
        for mv in metrics.metric_values:
            step_type = mv.context.get("step_type")
            if step_type:
                step_types.add(step_type)
        step_diversity = min(len(step_types) / 8, 1.0)  # Normalize to 8 major types

        # Success rate
        if metrics.metric_values:
            success_count = sum(1 for mv in metrics.metric_values if mv.context.get("success", True))
            success_rate = success_count / len(metrics.metric_values)
        else:
            success_rate = 0.0

        # Evidence thoroughness (simplified)
        evidence_thoroughness = min(metrics.evidence_collected_count / 10, 1.0)

        # Hypothesis quality
        if metrics.hypotheses_generated > 0:
            hypothesis_quality = min(metrics.hypotheses_tested / metrics.hypotheses_generated, 1.0)
        else:
            hypothesis_quality = 0.0

        # Documentation completeness
        deliverable_total = len(metrics.deliverables_produced) + len(metrics.deliverables_missing)
        if deliverable_total > 0:
            doc_completeness = len(metrics.deliverables_produced) / deliverable_total
        else:
            doc_completeness = 1.0 if metrics.step_count > 0 else 0.0

        # Tool usage effectiveness
        tool_usage = 0.0
        if metrics.knowledge_base_queries > 0:
            tool_usage += 0.3
        if metrics.runbook_queries > 0:
            tool_usage += 0.3
        if metrics.evidence_collected_count > 0:
            tool_usage += 0.4
        tool_usage = min(tool_usage, 1.0)

        # Overall weighted score
        overall = (
            phase_coverage * 0.25 +
            step_diversity * 0.15 +
            success_rate * 0.15 +
            evidence_thoroughness * 0.15 +
            hypothesis_quality * 0.10 +
            doc_completeness * 0.10 +
            tool_usage * 0.10
        )

        return ProcessQualityMetrics(
            phase_coverage=phase_coverage,
            step_diversity=step_diversity,
            success_rate=success_rate,
            evidence_thoroughness=evidence_thoroughness,
            hypothesis_quality=hypothesis_quality,
            documentation_completeness=doc_completeness,
            tool_usage_effectiveness=tool_usage,
            overall_score=overall
        )

    async def _update_participant_profile(self, metrics: ExerciseMetrics):
        """Update participant profile with new exercise data"""
        profile = await self.storage.load_participant_profile(metrics.participant_id)

        if not profile:
            profile = ParticipantProfile(
                participant_id=metrics.participant_id,
                participant_type=metrics.participant_type,
                name=metrics.participant_id,
                role="investigator",
                created_at=datetime.now()
            )

        profile.total_exercises += 1
        if metrics.status == "completed":
            profile.completed_exercises += 1

        profile.exercise_history.append(metrics.exercise_id)
        if len(profile.exercise_history) > 50:
            profile.exercise_history = profile.exercise_history[-50:]

        # Update aggregates (running average)
        n = profile.completed_exercises
        if n > 0:
            # Accuracy
            if metrics.accuracy_assessment:
                profile.avg_accuracy = ((n-1) * profile.avg_accuracy +
                                       metrics.accuracy_assessment.similarity_score) / n
                profile.accuracy_trend.append(metrics.accuracy_assessment.similarity_score)
                if len(profile.accuracy_trend) > 10:
                    profile.accuracy_trend = profile.accuracy_trend[-10:]

            # Speed (exercises per hour)
            if metrics.total_duration_ms > 0:
                speed = 3600000 / metrics.total_duration_ms  # exercises per hour
                profile.avg_speed = ((n-1) * profile.avg_speed + speed) / n
                profile.speed_trend.append(speed)
                if len(profile.speed_trend) > 10:
                    profile.speed_trend = profile.speed_trend[-10:]

            # Process quality
            if metrics.process_quality:
                profile.avg_process_quality = ((n-1) * profile.avg_process_quality +
                                             metrics.process_quality.overall_score) / n
                profile.quality_trend.append(metrics.process_quality.overall_score)
                if len(profile.quality_trend) > 10:
                    profile.quality_trend = profile.quality_trend[-10:]

        # Identify strengths/weaknesses from trends
        self._analyze_strengths_weaknesses(profile)

        await self.storage.save_participant_profile(profile)

    def _analyze_strengths_weaknesses(self, profile: ParticipantProfile):
        """Analyze trends to identify strengths and weaknesses"""
        profile.strengths.clear()
        profile.weaknesses.clear()
        profile.skill_gaps.clear()

        if len(profile.accuracy_trend) >= 3:
            recent_avg = statistics.mean(profile.accuracy_trend[-3:])
            overall_avg = profile.avg_accuracy
            if recent_avg > overall_avg + 0.1:
                profile.strengths.append("Improving root cause accuracy")
            elif recent_avg < overall_avg - 0.1:
                profile.weaknesses.append("Declining root cause accuracy")

        if len(profile.speed_trend) >= 3:
            recent_avg = statistics.mean(profile.speed_trend[-3:])
            if recent_avg > profile.avg_speed * 1.2:
                profile.strengths.append("Improving investigation speed")
            elif recent_avg < profile.avg_speed * 0.8:
                profile.weaknesses.append("Investigation speed declining")

        if len(profile.quality_trend) >= 3:
            recent_avg = statistics.mean(profile.quality_trend[-3:])
            if recent_avg > 0.8:
                profile.strengths.append("Consistently high process quality")
            elif recent_avg < 0.5:
                profile.weaknesses.append("Process quality needs improvement")
                profile.skill_gaps.append("Investigation methodology")

        # Check for specific skill gaps
        if profile.avg_accuracy < 0.5:
            profile.skill_gaps.append("Root cause analysis")
        if profile.avg_process_quality < 0.5:
            profile.skill_gaps.append("Structured investigation process")
        if profile.avg_speed < 0.5:  # Less than 1 exercise per 2 hours
            profile.skill_gaps.append("Time management under pressure")

    async def get_participant_profile(self, participant_id: str) -> Optional[ParticipantProfile]:
        return await self.storage.load_participant_profile(participant_id)

    async def get_exercise_metrics(self, exercise_id: str) -> Optional[ExerciseMetrics]:
        return await self.storage.load_exercise_metrics(exercise_id)

    async def get_participant_history(self, participant_id: str, limit: int = 20) -> List[ExerciseMetrics]:
        return await self.storage.query_metrics(participant_id=participant_id, limit=limit)

    async def get_scenario_history(self, scenario_id: str, limit: int = 50) -> List[ExerciseMetrics]:
        return await self.storage.query_metrics(scenario_id=scenario_id, limit=limit)

    async def get_cohort_metrics(self, cohort_id: str, participant_ids: List[str],
                                  exercise_type: ExerciseType, scenario_id: str) -> CohortMetrics:
        """Compute aggregate metrics for a cohort"""
        all_metrics = []
        for pid in participant_ids:
            history = await self.storage.query_metrics(
                participant_id=pid,
                exercise_type=exercise_type,
                scenario_id=scenario_id,
                limit=10
            )
            all_metrics.extend(history)

        if not all_metrics:
            return CohortMetrics(
                cohort_id=cohort_id,
                exercise_type=exercise_type,
                scenario_id=scenario_id,
                participants=participant_ids
            )

        completed = [m for m in all_metrics if m.status == "completed"]

        accuracies = [m.accuracy_assessment.similarity_score for m in completed if m.accuracy_assessment]
        durations = [m.total_duration_ms for m in completed]
        qualities = [m.process_quality.overall_score for m in completed if m.process_quality]

        cohort = CohortMetrics(
            cohort_id=cohort_id,
            exercise_type=exercise_type,
            scenario_id=scenario_id,
            participants=participant_ids,
            exercise_count=len(completed)
        )

        if accuracies:
            cohort.avg_accuracy = statistics.mean(accuracies)
            cohort.median_accuracy = statistics.median(accuracies)
            cohort.accuracy_stddev = statistics.stdev(accuracies) if len(accuracies) > 1 else 0

            # Distribution
            for acc in accuracies:
                if acc >= 0.8:
                    cohort.accuracy_distribution["excellent"] = cohort.accuracy_distribution.get("excellent", 0) + 1
                elif acc >= 0.6:
                    cohort.accuracy_distribution["good"] = cohort.accuracy_distribution.get("good", 0) + 1
                elif acc >= 0.4:
                    cohort.accuracy_distribution["fair"] = cohort.accuracy_distribution.get("fair", 0) + 1
                else:
                    cohort.accuracy_distribution["needs_improvement"] = cohort.accuracy_distribution.get("needs_improvement", 0) + 1

        if durations:
            cohort.avg_duration_ms = int(statistics.mean(durations))
            cohort.median_duration_ms = int(statistics.median(durations))
            cohort.duration_stddev = int(statistics.stdev(durations)) if len(durations) > 1 else 0

        if qualities:
            cohort.avg_process_quality = statistics.mean(qualities)

        cohort.completion_rate = len(completed) / len(all_metrics) if all_metrics else 0

        # Identify top/bottom performers
        participant_scores = defaultdict(list)
        for m in completed:
            if m.accuracy_assessment:
                participant_scores[m.participant_id].append(m.accuracy_assessment.similarity_score)

        avg_scores = {pid: statistics.mean(scores) for pid, scores in participant_scores.items() if scores}
        sorted_participants = sorted(avg_scores.items(), key=lambda x: x[1], reverse=True)

        cohort.top_performers = [pid for pid, _ in sorted_participants[:3]]
        cohort.needs_attention = [pid for pid, _ in sorted_participants[-3:]] if len(sorted_participants) > 3 else []

        return cohort


class TimingAnalyzer:
    """Analyze timing patterns and identify bottlenecks"""

    def __init__(self, collector: MetricsCollector):
        self.collector = collector

    def analyze_exercise_timing(self, metrics: ExerciseMetrics) -> Dict[str, Any]:
        """Analyze timing breakdown for an exercise"""
        if not metrics.phase_timings:
            return {"error": "No phase timing data"}

        analysis = {
            "total_duration_ms": metrics.total_duration_ms,
            "phase_breakdown": [],
            "bottlenecks": [],
            "idle_time_ms": 0,
            "efficiency_score": 0.0
        }

        total_active = 0
        for phase in metrics.phase_timings:
            phase_data = {
                "phase": phase.phase,
                "duration_ms": phase.duration_ms,
                "duration_min": round(phase.duration_ms / 60000, 2),
                "sub_phases": phase.sub_phases,
                "wait_time_ms": phase.wait_time_ms,
                "active_time_ms": phase.active_time_ms,
                "percentage": round(phase.duration_ms / metrics.total_duration_ms * 100, 1) if metrics.total_duration_ms > 0 else 0
            }
            analysis["phase_breakdown"].append(phase_data)
            total_active += phase.active_time_ms
            analysis["idle_time_ms"] += phase.wait_time_ms

        # Identify bottlenecks (phases taking >30% of time)
        for phase_data in analysis["phase_breakdown"]:
            if phase_data["percentage"] > 30:
                analysis["bottlenecks"].append({
                    "phase": phase_data["phase"],
                    "percentage": phase_data["percentage"],
                    "duration_min": phase_data["duration_min"]
                })

        # Efficiency score
        if metrics.total_duration_ms > 0:
            analysis["efficiency_score"] = total_active / metrics.total_duration_ms

        return analysis

    def compare_timing(self, metrics_list: List[ExerciseMetrics]) -> Dict[str, Any]:
        """Compare timing across multiple exercises"""
        if not metrics_list:
            return {"error": "No metrics provided"}

        completed = [m for m in metrics_list if m.status == "completed" and m.total_duration_ms > 0]
        if not completed:
            return {"error": "No completed exercises"}

        durations = [m.total_duration_ms for m in completed]
        first_action_times = [m.time_to_first_action_ms for m in completed if m.time_to_first_action_ms > 0]
        root_cause_times = [m.time_to_root_cause_ms for m in completed if m.time_to_root_cause_ms > 0]

        return {
            "count": len(completed),
            "total_duration": {
                "mean_ms": statistics.mean(durations),
                "median_ms": statistics.median(durations),
                "stddev_ms": statistics.stdev(durations) if len(durations) > 1 else 0,
                "min_ms": min(durations),
                "max_ms": max(durations)
            },
            "time_to_first_action": {
                "mean_ms": statistics.mean(first_action_times) if first_action_times else 0,
                "median_ms": statistics.median(first_action_times) if first_action_times else 0
            },
            "time_to_root_cause": {
                "mean_ms": statistics.mean(root_cause_times) if root_cause_times else 0,
                "median_ms": statistics.median(root_cause_times) if root_cause_times else 0
            },
            "improvement_trend": self._compute_trend([m.total_duration_ms for m in sorted(completed, key=lambda x: x.started_at)])
        }

    def _compute_trend(self, values: List[float]) -> Dict[str, Any]:
        """Compute trend direction"""
        if len(values) < 3:
            return {"direction": "insufficient_data"}

        # Simple linear trend
        n = len(values)
        x = list(range(n))
        x_mean = statistics.mean(x)
        y_mean = statistics.mean(values)

        numerator = sum((x[i] - x_mean) * (values[i] - y_mean) for i in range(n))
        denominator = sum((x[i] - x_mean) ** 2 for i in range(n))

        if denominator == 0:
            slope = 0
        else:
            slope = numerator / denominator

        if slope < -0.05 * y_mean:
            direction = "improving"
        elif slope > 0.05 * y_mean:
            direction = "degrading"
        else:
            direction = "stable"

        return {
            "direction": direction,
            "slope": slope,
            "recent_avg": statistics.mean(values[-3:]),
            "overall_avg": y_mean
        }


class AccuracyScorer:
    """Score accuracy of root cause identification and hypotheses"""

    def __init__(self, collector: MetricsCollector):
        self.collector = collector

    def score_root_cause(self, actual: str, expected: str,
                         use_embeddings: bool = False) -> AccuracyAssessment:
        """Score root cause accuracy"""
        return self.collector._compute_accuracy(actual, expected)

    def score_hypotheses(self, hypotheses: List[str], expected_root_cause: str,
                         evidence: List[str] = None) -> List[Dict[str, Any]]:
        """Score multiple hypotheses against expected root cause"""
        results = []
        expected_words = set(expected_root_cause.lower().split())

        for i, hypothesis in enumerate(hypotheses):
            hyp_words = set(hypothesis.lower().split())

            if not hyp_words or not expected_words:
                similarity = 0.0
            else:
                intersection = hyp_words & expected_words
                union = hyp_words | expected_words
                similarity = len(intersection) / len(union)

            # Check if hypothesis is on right track
            key_concepts = ["database", "connection", "memory", "cpu", "network",
                           "timeout", "cascade", "leak", "exhaustion"]
            hyp_concepts = hyp_words & set(key_concepts)
            expected_concepts = expected_words & set(key_concepts)
            concept_match = len(hyp_concepts & expected_concepts) / max(len(expected_concepts), 1)

            results.append({
                "hypothesis_index": i,
                "hypothesis": hypothesis,
                "similarity_score": similarity,
                "concept_match": concept_match,
                "is_relevant": similarity > 0.3 or concept_match > 0.5,
                "rank": i + 1
            })

        # Sort by relevance
        results.sort(key=lambda x: (x["is_relevant"], x["similarity_score"]), reverse=True)
        for i, r in enumerate(results):
            r["rank"] = i + 1

        return results

    def compute_hypothesis_precision_recall(self, generated_hypotheses: List[str],
                                             expected_root_cause: str,
                                             ground_truth_hypotheses: List[str] = None) -> Dict[str, float]:
        """Compute precision and recall for hypothesis generation"""
        if not generated_hypotheses:
            return {"precision": 0.0, "recall": 0.0, "f1": 0.0}

        # Score each generated hypothesis
        scored = self.score_hypotheses(generated_hypotheses, expected_root_cause)
        relevant_generated = [h for h in scored if h["is_relevant"]]

        precision = len(relevant_generated) / len(generated_hypotheses)

        if ground_truth_hypotheses:
            # Score ground truth
            gt_scored = self.score_hypotheses(ground_truth_hypotheses, expected_root_cause)
            relevant_gt = [h for h in gt_scored if h["is_relevant"]]

            # Recall = relevant generated / relevant ground truth
            recall = len(relevant_generated) / max(len(relevant_gt), 1)
        else:
            # Simplified: assume at least 1 relevant hypothesis exists
            recall = 1.0 if relevant_generated else 0.0

        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

        return {"precision": precision, "recall": recall, "f1": f1}


class PerformanceTracker:
    """Track performance trends over time for participants and cohorts"""

    def __init__(self, collector: MetricsCollector):
        self.collector = collector

    async def get_participant_dashboard(self, participant_id: str) -> Dict[str, Any]:
        """Generate performance dashboard for a participant"""
        profile = await self.collector.get_participant_profile(participant_id)
        if not profile:
            return {"error": "Participant not found"}

        history = await self.collector.get_participant_history(participant_id, limit=20)
        completed = [m for m in history if m.status == "completed"]

        dashboard = {
            "participant_id": participant_id,
            "name": profile.name,
            "role": profile.role,
            "summary": {
                "total_exercises": profile.total_exercises,
                "completed_exercises": profile.completed_exercises,
                "completion_rate": profile.completed_exercises / max(profile.total_exercises, 1),
                "avg_accuracy": round(profile.avg_accuracy, 3),
                "avg_speed_exercises_per_hour": round(profile.avg_speed, 2),
                "avg_process_quality": round(profile.avg_process_quality, 3)
            },
            "trends": {
                "accuracy": profile.accuracy_trend[-10:],
                "speed": profile.speed_trend[-10:],
                "quality": profile.quality_trend[-10:]
            },
            "strengths": profile.strengths,
            "weaknesses": profile.weaknesses,
            "skill_gaps": profile.skill_gaps,
            "recent_exercises": [
                {
                    "exercise_id": m.exercise_id,
                    "scenario_id": m.scenario_id,
                    "type": m.exercise_type.value,
                    "date": m.started_at.isoformat(),
                    "duration_min": round(m.total_duration_ms / 60000, 1),
                    "accuracy": round(m.accuracy_assessment.similarity_score, 3) if m.accuracy_assessment else None,
                    "process_quality": round(m.process_quality.overall_score, 3) if m.process_quality else None
                }
                for m in completed[-5:]
            ]
        }

        # Add trend analysis
        if len(profile.accuracy_trend) >= 3:
            dashboard["trend_analysis"] = {
                "accuracy": self._analyze_trend(profile.accuracy_trend),
                "speed": self._analyze_trend(profile.speed_trend),
                "quality": self._analyze_trend(profile.quality_trend)
            }

        return dashboard

    def _analyze_trend(self, values: List[float]) -> Dict[str, Any]:
        """Analyze trend in a metric"""
        if len(values) < 3:
            return {"status": "insufficient_data"}

        recent = values[-3:]
        older = values[-6:-3] if len(values) >= 6 else values[:-3]

        recent_avg = statistics.mean(recent)
        older_avg = statistics.mean(older) if older else recent_avg

        change_pct = (recent_avg - older_avg) / max(older_avg, 0.001) * 100

        if change_pct > 10:
            status = "improving"
        elif change_pct < -10:
            status = "declining"
        else:
            status = "stable"

        return {
            "status": status,
            "change_percent": round(change_pct, 1),
            "recent_avg": round(recent_avg, 3),
            "previous_avg": round(older_avg, 3)
        }

    async def get_cohort_dashboard(self, cohort_id: str, participant_ids: List[str],
                                    exercise_type: ExerciseType, scenario_id: str) -> Dict[str, Any]:
        """Generate cohort performance dashboard"""
        cohort = await self.collector.get_cohort_metrics(
            cohort_id, participant_ids, exercise_type, scenario_id
        )

        return {
            "cohort_id": cohort_id,
            "scenario_id": scenario_id,
            "exercise_type": exercise_type.value,
            "participant_count": len(participant_ids),
            "exercise_count": cohort.exercise_count,
            "summary": {
                "avg_accuracy": round(cohort.avg_accuracy, 3),
                "median_accuracy": round(cohort.median_accuracy, 3),
                "accuracy_stddev": round(cohort.accuracy_stddev, 3),
                "avg_duration_min": round(cohort.avg_duration_ms / 60000, 1),
                "median_duration_min": round(cohort.median_duration_ms / 60000, 1),
                "avg_process_quality": round(cohort.avg_process_quality, 3),
                "completion_rate": round(cohort.completion_rate, 3)
            },
            "distributions": {
                "accuracy": cohort.accuracy_distribution,
                "duration": cohort.duration_distribution
            },
            "top_performers": cohort.top_performers,
            "needs_attention": cohort.needs_attention
        }


class ReportGenerator:
    """Generate detailed exercise reports with insights"""

    def __init__(self, collector: MetricsCollector):
        self.collector = collector
        self.timing_analyzer = TimingAnalyzer(collector)
        self.accuracy_scorer = AccuracyScorer(collector)
        self.performance_tracker = PerformanceTracker(collector)

    def generate_exercise_report(self, metrics: ExerciseMetrics) -> Dict[str, Any]:
        """Generate comprehensive report for a single exercise"""
        report = {
            "exercise_summary": {
                "exercise_id": metrics.exercise_id,
                "type": metrics.exercise_type.value,
                "scenario_id": metrics.scenario_id,
                "participant": f"{metrics.participant_id} ({metrics.participant_type})",
                "date": metrics.started_at.isoformat(),
                "duration_min": round(metrics.total_duration_ms / 60000, 1),
                "status": metrics.status
            },
            "timing_analysis": self.timing_analyzer.analyze_exercise_timing(metrics),
            "accuracy_analysis": self._generate_accuracy_analysis(metrics),
            "process_analysis": self._generate_process_analysis(metrics),
            "completeness_analysis": self._generate_completeness_analysis(metrics),
            "learning_analysis": self._generate_learning_analysis(metrics),
            "recommendations": self._generate_recommendations(metrics)
        }

        if metrics.comparison_metrics:
            report["comparison_analysis"] = metrics.comparison_metrics

        return report

    def _generate_accuracy_analysis(self, metrics: ExerciseMetrics) -> Dict[str, Any]:
        if not metrics.accuracy_assessment:
            return {"status": "no_accuracy_data"}

        aa = metrics.accuracy_assessment
        return {
            "root_cause_identified": metrics.accuracy_assessment.actual_root_cause,
            "expected_root_cause": metrics.accuracy_assessment.expected_root_cause,
            "similarity_score": round(aa.similarity_score, 3),
            "keyword_match_score": round(aa.keyword_match_score, 3),
            "is_correct": aa.is_correct,
            "partial_credit": round(aa.partial_credit, 3),
            "feedback": aa.feedback,
            "hypothesis_accuracy": metrics.hypothesis_accuracy
        }

    def _generate_process_analysis(self, metrics: ExerciseMetrics) -> Dict[str, Any]:
        if not metrics.process_quality:
            return {"status": "no_process_data"}

        pq = metrics.process_quality
        return {
            "overall_score": round(pq.overall_score, 3),
            "phase_coverage": round(pq.phase_coverage * 100, 1),
            "step_diversity": round(pq.step_diversity * 100, 1),
            "success_rate": round(pq.success_rate * 100, 1),
            "evidence_thoroughness": round(pq.evidence_thoroughness * 100, 1),
            "hypothesis_quality": round(pq.hypothesis_quality * 100, 1),
            "documentation_completeness": round(pq.documentation_completeness * 100, 1),
            "tool_usage_effectiveness": round(pq.tool_usage_effectiveness * 100, 1),
            "step_count": metrics.step_count,
            "unique_step_types": metrics.unique_step_types,
            "evidence_collected": metrics.evidence_collected_count,
            "hypotheses_generated": metrics.hypotheses_generated,
            "hypotheses_tested": metrics.hypotheses_tested,
            "kb_queries": metrics.knowledge_base_queries,
            "runbook_queries": metrics.runbook_queries
        }

    def _generate_completeness_analysis(self, metrics: ExerciseMetrics) -> Dict[str, Any]:
        return {
            "phases_completed": metrics.required_phases_completed,
            "phases_missed": metrics.required_phases_missed,
            "deliverables_produced": metrics.deliverables_produced,
            "deliverables_missing": metrics.deliverables_missing,
            "phase_completion_rate": len(metrics.required_phases_completed) /
                                     max(len(metrics.required_phases_completed) + len(metrics.required_phases_missed), 1)
        }

    def _generate_learning_analysis(self, metrics: ExerciseMetrics) -> Dict[str, Any]:
        return {
            "objectives_met": metrics.learning_objectives_met,
            "objectives_missed": metrics.learning_objectives_missed,
            "skills_demonstrated": metrics.skills_demonstrated,
            "skills_needing_improvement": metrics.skills_needing_improvement
        }

    def _generate_recommendations(self, metrics: ExerciseMetrics) -> List[str]:
        recommendations = []

        if metrics.accuracy_assessment:
            if not metrics.accuracy_assessment.is_correct:
                recommendations.append("Review root cause analysis methodology - practice structured hypothesis testing")
            elif metrics.accuracy_assessment.partial_credit < 0.7:
                recommendations.append("Work on identifying specific root cause details, not just general domain")

        if metrics.process_quality:
            if metrics.process_quality.phase_coverage < 0.75:
                recommendations.append("Ensure all investigation phases are completed - use a checklist")
            if metrics.process_quality.evidence_thoroughness < 0.5:
                recommendations.append("Collect more evidence before forming hypotheses - check metrics, logs, traces")
            if metrics.process_quality.hypothesis_quality < 0.5:
                recommendations.append("Test more hypotheses before concluding - use confidence scoring")
            if metrics.process_quality.tool_usage_effectiveness < 0.5:
                recommendations.append("Leverage knowledge base and runbooks more effectively")

        if metrics.total_duration_ms > 0:
            duration_min = metrics.total_duration_ms / 60000
            if duration_min > 60:
                recommendations.append("Practice time-boxed investigation - aim for root cause within 30 minutes")

        if metrics.knowledge_base_queries == 0:
            recommendations.append("Always check knowledge base for similar past incidents")

        if metrics.runbook_queries == 0:
            recommendations.append("Consult relevant runbooks for standard mitigation procedures")

        return recommendations

    def generate_comparison_report(self, human_metrics: ExerciseMetrics,
                                    ai_metrics: ExerciseMetrics) -> Dict[str, Any]:
        """Generate side-by-side comparison report for shadow duel"""
        return {
            "comparison_type": "shadow_duel",
            "human": self.generate_exercise_report(human_metrics),
            "ai": self.generate_exercise_report(ai_metrics),
            "summary": {
                "accuracy_winner": "human" if (human_metrics.accuracy_assessment and ai_metrics.accuracy_assessment and
                    human_metrics.accuracy_assessment.similarity_score > ai_metrics.accuracy_assessment.similarity_score) else "ai",
                "speed_winner": "human" if human_metrics.total_duration_ms < ai_metrics.total_duration_ms else "ai",
                "process_winner": "human" if (human_metrics.process_quality and ai_metrics.process_quality and
                    human_metrics.process_quality.overall_score > ai_metrics.process_quality.overall_score) else "ai",
                "time_difference_min": round(abs(human_metrics.total_duration_ms - ai_metrics.total_duration_ms) / 60000, 1),
                "accuracy_difference": round(
                    (human_metrics.accuracy_assessment.similarity_score if human_metrics.accuracy_assessment else 0) -
                    (ai_metrics.accuracy_assessment.similarity_score if ai_metrics.accuracy_assessment else 0), 3)
            }
        }


# ============================================================
# Demo / Test Functions
# ============================================================

async def run_metrics_demo():
    """Demonstrate metrics collection and analysis"""
    print("=" * 60)
    print("METRICS COLLECTOR DEMONSTRATION")
    print("=" * 60)

    # Create collector with in-memory storage
    storage = InMemoryMetricsStorage()
    collector = MetricsCollector(storage)

    # Start an exercise
    exercise_id = "exercise-001"
    metrics = collector.start_exercise(
        exercise_id=exercise_id,
        exercise_type=ExerciseType.SHADOW_DUEL,
        scenario_id="shadow-duel-01",
        participant_id="human-001",
        participant_type="human"
    )

    print(f"\nStarted exercise: {exercise_id}")

    # Simulate investigation steps
    phases = [
        ("evidence_gathering", "query_metrics", 30000),
        ("evidence_gathering", "query_logs", 45000),
        ("evidence_gathering", "query_traces", 20000),
        ("hypothesis_formation", "check_kb", 15000),
        ("hypothesis_formation", "check_runbook", 10000),
        ("hypothesis_formation", "form_hypothesis", 20000),
        ("hypothesis_testing", "test_hypothesis", 25000),
        ("hypothesis_testing", "test_hypothesis", 20000),
        ("root_cause_identification", "form_hypothesis", 15000),
        ("mitigation_planning", "decide_action", 10000),
        ("documentation", "document_finding", 5000)
    ]

    start_time = datetime.now()
    for i, (phase, step_type, duration) in enumerate(phases):
        phase_start = start_time + timedelta(milliseconds=sum(p[2] for p in phases[:i]))
        phase_end = phase_start + timedelta(milliseconds=duration)

        collector.record_step(exercise_id, phase, step_type, duration, True)
        collector.record_phase_timing(exercise_id, phase, phase_start, phase_end)
        collector.record_evidence_collected(exercise_id, 1)

        if "hypothesis" in step_type:
            collector.record_hypothesis(exercise_id, generated="form" in step_type, tested="test" in step_type)
        if step_type == "check_kb":
            collector.record_kb_query(exercise_id)
        if step_type == "check_runbook":
            collector.record_runbook_query(exercise_id)

    # Complete exercise
    final_metrics = collector.complete_exercise(
        exercise_id=exercise_id,
        root_cause="Database connection pool exhaustion in payment-service due to missing connection cleanup",
        expected_root_cause="Database connection pool exhaustion in payment-service due to missing connection cleanup",
        mitigation_actions=["Fix connection leak", "Add pool monitoring", "Deploy fix"],
        deliverables=["incident_report.md", "root_cause_analysis.md", "mitigation_plan.md"],
        required_deliverables=["incident_report.md", "root_cause_analysis.md", "mitigation_plan.md", "timeline.md"],
        required_phases=["evidence_gathering", "hypothesis_formation", "hypothesis_testing",
                        "root_cause_identification", "mitigation_planning", "documentation"],
        learning_objectives=["Practice evidence gathering", "Learn hypothesis testing", "Improve documentation"]
    )

    print(f"\nCompleted exercise: {exercise_id}")
    print(f"Duration: {final_metrics.total_duration_ms/60000:.1f} minutes")
    print(f"Steps: {final_metrics.step_count}")
    print(f"Evidence collected: {final_metrics.evidence_collected_count}")
    print(f"Hypotheses generated: {final_metrics.hypotheses_generated}")
    print(f"Hypotheses tested: {final_metrics.hypotheses_tested}")

    # Generate report
    report_gen = ReportGenerator(collector)
    report = report_gen.generate_exercise_report(final_metrics)

    print("\n" + "=" * 60)
    print("EXERCISE REPORT")
    print("=" * 60)

    print(f"\nTiming Analysis:")
    ta = report["timing_analysis"]
    print(f"  Total: {ta['total_duration_ms']/60000:.1f} min")
    print(f"  Efficiency: {ta['efficiency_score']:.2f}")
    if ta["bottlenecks"]:
        print(f"  Bottlenecks: {[b['phase'] for b in ta['bottlenecks']]}")

    print(f"\nAccuracy Analysis:")
    aa = report["accuracy_analysis"]
    print(f"  Similarity: {aa['similarity_score']:.2f}")
    print(f"  Keyword Match: {aa['keyword_match_score']:.2f}")
    print(f"  Correct: {aa['is_correct']}")
    print(f"  Feedback: {aa['feedback']}")

    print(f"\nProcess Analysis:")
    pa = report["process_analysis"]
    print(f"  Overall Score: {pa['overall_score']:.2f}")
    print(f"  Phase Coverage: {pa['phase_coverage']:.1f}%")
    print(f"  Evidence Thoroughness: {pa['evidence_thoroughness']:.1f}%")
    print(f"  Tool Usage: {pa['tool_usage_effectiveness']:.1f}%")

    print(f"\nRecommendations:")
    for rec in report["recommendations"]:
        print(f"  * {rec}")

    # Test participant dashboard
    print("\n" + "=" * 60)
    print("PARTICIPANT DASHBOARD")
    print("=" * 60)

    tracker = PerformanceTracker(collector)
    dashboard = await tracker.get_participant_dashboard("human-001")
    print(json.dumps(dashboard, indent=2, default=str))

    return report


if __name__ == "__main__":
    asyncio.run(run_metrics_demo())