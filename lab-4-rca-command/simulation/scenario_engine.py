"""
Chaos Scenario Engine
=====================
Defines and orchestrates chaos engineering scenarios for training.
Supports failure injection, blast radius analysis, and scenario replay.
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime, timedelta
from abc import ABC, abstractmethod
import json
import uuid
import logging
import threading
import time

logger = logging.getLogger(__name__)


class FailureType(Enum):
    """Types of failures that can be injected."""
    LATENCY_SPIKE = "latency_spike"           # Add latency to service calls
    POD_CRASH = "pod_crash"                   # Kill/kill pods
    CPU_EXHAUSTION = "cpu_exhaustion"         # Consume CPU resources
    MEMORY_LEAK = "memory_leak"               # Consume memory
    NETWORK_PARTITION = "network_partition"   # Block network between services
    DNS_FAILURE = "dns_failure"               # Break service discovery
    DEPENDENCY_FAILURE = "dependency_failure" # Fail upstream dependency
    CONFIG_ERROR = "config_error"             # Inject bad configuration
    DISK_FULL = "disk_full"                   # Fill disk space
    THREAD_EXHAUSTION = "thread_exhaustion"   # Exhaust thread pools
    DATABASE_CONNECTION_EXHAUSTION = "db_connection_exhaustion"  # Exhaust DB connections
    CACHE_EVICTION = "cache_eviction"         # Evict cache entries
    CERTIFICATE_EXPIRY = "certificate_expiry" # Expire TLS certificates
    RATE_LIMIT = "rate_limit"                 # Apply aggressive rate limiting
    CLOCK_DRIFT = "clock_drift"               # Drift system clock


class InjectionTarget(Enum):
    """Target for failure injection."""
    SERVICE = "service"               # Specific service
    NAMESPACE = "namespace"           # Kubernetes namespace
    NODE = "node"                     # Kubernetes node
    POD = "pod"                       # Specific pod
    DEPLOYMENT = "deployment"         # Deployment
    SERVICE_MESH = "service_mesh"     # Istio/Linkerd
    INFRASTRUCTURE = "infrastructure" # Cloud infrastructure


class ScenarioStatus(Enum):
    """Scenario execution status."""
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    ABORTED = "aborted"


class Severity(Enum):
    """Scenario severity."""
    LOW = "low"           # Minor impact, single service
    MEDIUM = "medium"     # Multiple services, degraded performance
    HIGH = "high"         # Major outage, customer impact
    CRITICAL = "critical" # Full system outage


@dataclass
class FailureInjection:
    """A single failure injection action."""
    id: str
    failure_type: FailureType
    target: InjectionTarget
    target_selector: str  # Label selector, service name, etc.

    # Parameters
    parameters: Dict[str, Any] = field(default_factory=dict)

    # Timing
    start_delay_seconds: int = 0
    duration_seconds: int = 300
    ramp_up_seconds: int = 0
    ramp_down_seconds: int = 0

    # Conditions
    preconditions: List[str] = field(default_factory=list)  # Conditions that must be true
    postconditions: List[str] = field(default_factory=list)  # Expected effects

    # Metadata
    description: str = ""
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "failure_type": self.failure_type.value,
            "target": self.target.value,
            "target_selector": self.target_selector,
            "parameters": self.parameters,
            "start_delay_seconds": self.start_delay_seconds,
            "duration_seconds": self.duration_seconds,
            "ramp_up_seconds": self.ramp_up_seconds,
            "ramp_down_seconds": self.ramp_down_seconds,
            "preconditions": self.preconditions,
            "postconditions": self.postconditions,
            "description": self.description,
            "tags": self.tags
        }


@dataclass
class ChaosScenario:
    """A complete chaos engineering scenario."""
    id: str
    name: str
    description: str
    severity: Severity

    # Injections
    injections: List[FailureInjection] = field(default_factory=list)

    # Scenario flow
    phases: List[Dict[str, Any]] = field(default_factory=list)  # Sequential phases

    # Expected outcomes
    expected_blast_radius: List[str] = field(default_factory=list)  # Services expected to be affected
    expected_symptoms: List[str] = field(default_factory=list)
    expected_root_cause: str = ""

    # Learning objectives
    learning_objectives: List[str] = field(default_factory=list)
    skills_tested: List[str] = field(default_factory=list)

    # Constraints
    max_duration_minutes: int = 60
    requires_approval: bool = False
    allowed_environments: List[str] = field(default_factory=lambda: ["staging", "training"])

    # Metadata
    created_at: datetime = field(default_factory=datetime.utcnow)
    created_by: str = ""
    tags: List[str] = field(default_factory=list)
    version: str = "1.0"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "severity": self.severity.value,
            "injections": [inj.to_dict() for inj in self.injections],
            "phases": self.phases,
            "expected_blast_radius": self.expected_blast_radius,
            "expected_symptoms": self.expected_symptoms,
            "expected_root_cause": self.expected_root_cause,
            "learning_objectives": self.learning_objectives,
            "skills_tested": self.skills_tested,
            "max_duration_minutes": self.max_duration_minutes,
            "requires_approval": self.requires_approval,
            "allowed_environments": self.allowed_environments,
            "created_at": self.created_at.isoformat(),
            "created_by": self.created_by,
            "tags": self.tags,
            "version": self.version
        }


@dataclass
class ScenarioExecution:
    """Runtime execution of a scenario."""
    id: str
    scenario_id: str
    scenario_name: str
    status: ScenarioStatus = ScenarioStatus.PENDING

    # Timing
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    current_phase: int = 0

    # Injection tracking
    active_injections: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    completed_injections: List[Dict[str, Any]] = field(default_factory=list)
    failed_injections: List[Dict[str, Any]] = field(default_factory=list)

    # Observations
    observations: List[Dict[str, Any]] = field(default_factory=list)
    metrics_snapshots: List[Dict[str, Any]] = field(default_factory=list)

    # Results
    actual_blast_radius: List[str] = field(default_factory=list)
    actual_symptoms: List[str] = field(default_factory=list)
    root_cause_identified: bool = False
    identified_root_cause: str = ""
    time_to_detection_minutes: float = 0
    time_to_resolution_minutes: float = 0

    # Metadata
    executed_by: str = ""
    environment: str = "training"
    notes: str = ""

    def get_duration_seconds(self) -> float:
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        elif self.started_at:
            return (datetime.utcnow() - self.started_at).total_seconds()
        return 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "scenario_id": self.scenario_id,
            "scenario_name": self.scenario_name,
            "status": self.status.value,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "current_phase": self.current_phase,
            "active_injections": self.active_injections,
            "completed_injections": self.completed_injections,
            "failed_injections": self.failed_injections,
            "observations": self.observations,
            "metrics_snapshots": self.metrics_snapshots,
            "actual_blast_radius": self.actual_blast_radius,
            "actual_symptoms": self.actual_symptoms,
            "root_cause_identified": self.root_cause_identified,
            "identified_root_cause": self.identified_root_cause,
            "time_to_detection_minutes": self.time_to_detection_minutes,
            "time_to_resolution_minutes": self.time_to_resolution_minutes,
            "executed_by": self.executed_by,
            "environment": self.environment,
            "notes": self.notes,
            "duration_seconds": self.get_duration_seconds()
        }


class FailureInjector(ABC):
    """Abstract base class for failure injectors."""

    @abstractmethod
    def inject(self, injection: FailureInjection) -> Dict[str, Any]:
        """Inject a failure. Returns result with success status and details."""
        pass

    @abstractmethod
    def revert(self, injection: FailureInjection, injection_result: Dict[str, Any]) -> bool:
        """Revert a failure injection."""
        pass

    @abstractmethod
    def verify(self, injection: FailureInjection) -> Dict[str, Any]:
        """Verify injection is active and working."""
        pass


class KubernetesFailureInjector(FailureInjector):
    """Kubernetes-based failure injector using kubectl/helm."""

    def __init__(self, kubeconfig: str = "", namespace: str = "default"):
        self.kubeconfig = kubeconfig
        self.namespace = namespace
        self.active_injections: Dict[str, Dict] = {}

    def inject(self, injection: FailureInjection) -> Dict[str, Any]:
        """Inject failure via Kubernetes."""
        result = {
            "success": False,
            "injection_id": injection.id,
            "method": "kubernetes",
            "details": {},
            "error": None
        }

        try:
            if injection.failure_type == FailureType.POD_CRASH:
                result = self._inject_pod_crash(injection)
            elif injection.failure_type == FailureType.CPU_EXHAUSTION:
                result = self._inject_cpu_exhaustion(injection)
            elif injection.failure_type == FailureType.MEMORY_LEAK:
                result = self._inject_memory_leak(injection)
            elif injection.failure_type == FailureType.LATENCY_SPIKE:
                result = self._inject_latency_spike(injection)
            elif injection.failure_type == FailureType.NETWORK_PARTITION:
                result = self._inject_network_partition(injection)
            elif injection.failure_type == FailureType.DNS_FAILURE:
                result = self._inject_dns_failure(injection)
            elif injection.failure_type == FailureType.CONFIG_ERROR:
                result = self._inject_config_error(injection)
            else:
                result["error"] = f"Unsupported failure type: {injection.failure_type.value}"

            if result["success"]:
                self.active_injections[injection.id] = {
                    "injection": injection,
                    "result": result,
                    "started_at": datetime.utcnow()
                }

        except Exception as e:
            result["error"] = str(e)
            logger.error(f"Injection failed: {e}")

        return result

    def _inject_pod_crash(self, injection: FailureInjection) -> Dict[str, Any]:
        """Kill pods matching selector."""
        selector = injection.target_selector
        grace_period = injection.parameters.get("grace_period", 0)

        # In production: kubectl delete pods -l <selector> --grace-period=<grace_period>
        pods_affected = injection.parameters.get("mock_pods", [f"{selector}-pod-1", f"{selector}-pod-2"])

        return {
            "success": True,
            "method": "kubectl delete pods",
            "details": {
                "selector": selector,
                "pods_killed": pods_affected,
                "grace_period": grace_period
            }
        }

    def _inject_cpu_exhaustion(self, injection: FailureInjection) -> Dict[str, Any]:
        """Inject CPU exhaustion via stress container."""
        selector = injection.target_selector
        cpu_cores = injection.parameters.get("cpu_cores", 2)
        duration = injection.duration_seconds

        # In production: kubectl run stress --image=progrium/stress -- -c <cpu_cores> -t <duration>

        return {
            "success": True,
            "method": "stress-ng container",
            "details": {
                "selector": selector,
                "cpu_cores": cpu_cores,
                "duration_seconds": duration
            }
        }

    def _inject_memory_leak(self, injection: FailureInjection) -> Dict[str, Any]:
        """Inject memory leak."""
        selector = injection.target_selector
        memory_mb = injection.parameters.get("memory_mb", 512)
        growth_rate_mb = injection.parameters.get("growth_rate_mb_per_sec", 10)

        return {
            "success": True,
            "method": "memory leak sidecar",
            "details": {
                "selector": selector,
                "initial_memory_mb": memory_mb,
                "growth_rate_mb_per_sec": growth_rate_mb
            }
        }

    def _inject_latency_spike(self, injection: FailureInjection) -> Dict[str, Any]:
        """Inject latency via service mesh or sidecar."""
        selector = injection.target_selector
        latency_ms = injection.parameters.get("latency_ms", 5000)
        jitter_ms = injection.parameters.get("jitter_ms", 1000)

        # In production: Istio fault injection, or sidecar proxy

        return {
            "success": True,
            "method": "istio fault injection / tc netem",
            "details": {
                "selector": selector,
                "latency_ms": latency_ms,
                "jitter_ms": jitter_ms
            }
        }

    def _inject_network_partition(self, injection: FailureInjection) -> Dict[str, Any]:
        """Inject network partition."""
        selector = injection.target_selector
        target_selector = injection.parameters.get("target_selector", "")
        direction = injection.parameters.get("direction", "both")  # both, ingress, egress

        return {
            "success": True,
            "method": "calico network policy / istio authorization policy",
            "details": {
                "source_selector": selector,
                "target_selector": target_selector,
                "direction": direction
            }
        }

    def _inject_dns_failure(self, injection: FailureInjection) -> Dict[str, Any]:
        """Inject DNS failure."""
        selector = injection.target_selector
        failure_mode = injection.parameters.get("mode", "block")  # block, corrupt, slow

        return {
            "success": True,
            "method": "coredns configmap modification / iptables",
            "details": {
                "selector": selector,
                "mode": failure_mode
            }
        }

    def _inject_config_error(self, injection: FailureInjection) -> Dict[str, Any]:
        """Inject configuration error."""
        selector = injection.target_selector
        config_map = injection.parameters.get("config_map", "")
        bad_key = injection.parameters.get("bad_key", "")
        bad_value = injection.parameters.get("bad_value", "")

        return {
            "success": True,
            "method": "kubectl patch configmap",
            "details": {
                "selector": selector,
                "config_map": config_map,
                "bad_key": bad_key,
                "bad_value": bad_value
            }
        }

    def revert(self, injection: FailureInjection, injection_result: Dict[str, Any]) -> bool:
        """Revert a Kubernetes injection."""
        try:
            if injection.failure_type == FailureType.POD_CRASH:
                # Pods will be recreated by deployment/replicaset
                logger.info(f"Pod crash reverted - deployment will recreate pods for {injection.target_selector}")
            elif injection.failure_type in [FailureType.CPU_EXHAUSTION, FailureType.MEMORY_LEAK]:
                # Stress containers will complete
                logger.info(f"Resource exhaustion reverted for {injection.target_selector}")
            elif injection.failure_type == FailureType.LATENCY_SPIKE:
                # Remove fault injection rule
                logger.info(f"Latency injection reverted for {injection.target_selector}")
            elif injection.failure_type == FailureType.NETWORK_PARTITION:
                # Remove network policy
                logger.info(f"Network partition reverted for {injection.target_selector}")
            elif injection.failure_type == FailureType.DNS_FAILURE:
                # Restore CoreDNS config
                logger.info(f"DNS failure reverted for {injection.target_selector}")
            elif injection.failure_type == FailureType.CONFIG_ERROR:
                # Restore configmap
                logger.info(f"Config error reverted for {injection.target_selector}")

            if injection.id in self.active_injections:
                del self.active_injections[injection.id]

            return True
        except Exception as e:
            logger.error(f"Revert failed: {e}")
            return False

    def verify(self, injection: FailureInjection) -> Dict[str, Any]:
        """Verify injection is active."""
        active = injection.id in self.active_injections
        return {
            "active": active,
            "injection_id": injection.id,
            "details": self.active_injections.get(injection.id, {})
        }


class ScenarioEngine:
    """Orchestrates chaos scenario execution."""

    def __init__(self, injector: FailureInjector = None):
        self.injector = injector or KubernetesFailureInjector()
        self.scenarios: Dict[str, ChaosScenario] = {}
        self.executions: Dict[str, ScenarioExecution] = {}
        self.observers: List[Callable[[ScenarioExecution, str, Dict], None]] = []
        self._execution_threads: Dict[str, threading.Thread] = {}
        self._stop_flags: Dict[str, threading.Event] = {}

    def register_scenario(self, scenario: ChaosScenario) -> None:
        """Register a scenario."""
        self.scenarios[scenario.id] = scenario
        logger.info(f"Registered scenario: {scenario.id} - {scenario.name}")

    def get_scenario(self, scenario_id: str) -> Optional[ChaosScenario]:
        """Get scenario by ID."""
        return self.scenarios.get(scenario_id)

    def list_scenarios(self, severity: Severity = None, tag: str = None) -> List[ChaosScenario]:
        """List scenarios with optional filters."""
        scenarios = list(self.scenarios.values())

        if severity:
            scenarios = [s for s in scenarios if s.severity == severity]
        if tag:
            scenarios = [s for s in scenarios if tag in s.tags]

        return sorted(scenarios, key=lambda s: (s.severity.value, s.name))

    def add_observer(self, observer: Callable[[ScenarioExecution, str, Dict], None]) -> None:
        """Add an execution observer."""
        self.observers.append(observer)

    def _notify_observers(self, execution: ScenarioExecution, event: str, data: Dict) -> None:
        """Notify all observers."""
        for observer in self.observers:
            try:
                observer(execution, event, data)
            except Exception as e:
                logger.error(f"Observer notification failed: {e}")

    def execute_scenario(
        self,
        scenario_id: str,
        executed_by: str = "",
        environment: str = "training",
        dry_run: bool = False
    ) -> ScenarioExecution:
        """Execute a scenario."""
        scenario = self.scenarios.get(scenario_id)
        if not scenario:
            raise ValueError(f"Scenario not found: {scenario_id}")

        if environment not in scenario.allowed_environments:
            raise ValueError(f"Environment {environment} not allowed for this scenario")

        execution = ScenarioExecution(
            id=f"exec-{uuid.uuid4().hex[:8]}",
            scenario_id=scenario.id,
            scenario_name=scenario.name,
            status=ScenarioStatus.RUNNING,
            started_at=datetime.utcnow(),
            executed_by=executed_by,
            environment=environment
        )

        self.executions[execution.id] = execution

        if dry_run:
            logger.info(f"DRY RUN: Would execute scenario {scenario.name}")
            execution.status = ScenarioStatus.COMPLETED
            execution.completed_at = datetime.utcnow()
            return execution

        # Start execution in background thread
        stop_flag = threading.Event()
        self._stop_flags[execution.id] = stop_flag

        thread = threading.Thread(
            target=self._run_scenario,
            args=(execution, scenario, stop_flag),
            daemon=True
        )
        self._execution_threads[execution.id] = thread
        thread.start()

        return execution

    def _run_scenario(
        self,
        execution: ScenarioExecution,
        scenario: ChaosScenario,
        stop_flag: threading.Event
    ) -> None:
        """Run scenario in background thread."""
        try:
            self._notify_observers(execution, "scenario_started", {"scenario": scenario.to_dict()})

            # Execute phases sequentially
            for phase_idx, phase in enumerate(scenario.phases):
                if stop_flag.is_set():
                    execution.status = ScenarioStatus.ABORTED
                    break

                execution.current_phase = phase_idx
                phase_name = phase.get("name", f"Phase {phase_idx + 1}")
                logger.info(f"Executing phase: {phase_name}")

                self._notify_observers(execution, "phase_started", {"phase": phase_name, "index": phase_idx})

                # Execute injections in this phase
                injections = phase.get("injections", [])
                for inj_config in injections:
                    if stop_flag.is_set():
                        break

                    injection = self._create_injection_from_config(inj_config)
                    if not injection:
                        continue

                    # Wait for start delay
                    if injection.start_delay_seconds > 0:
                        time.sleep(injection.start_delay_seconds)
                        if stop_flag.is_set():
                            break

                    # Execute injection
                    result = self.injector.inject(injection)

                    if result["success"]:
                        execution.active_injections[injection.id] = {
                            "injection": injection.to_dict(),
                            "result": result,
                            "started_at": datetime.utcnow().isoformat()
                        }
                        execution.completed_injections.append({
                            "injection": injection.to_dict(),
                            "result": result,
                            "completed_at": datetime.utcnow().isoformat()
                        })
                    else:
                        execution.failed_injections.append({
                            "injection": injection.to_dict(),
                            "result": result,
                            "failed_at": datetime.utcnow().isoformat()
                        })

                    self._notify_observers(execution, "injection_completed", {
                        "injection_id": injection.id,
                        "result": result
                    })

                # Wait for phase duration
                phase_duration = phase.get("duration_seconds", 60)
                time.sleep(phase_duration)

                self._notify_observers(execution, "phase_completed", {"phase": phase_name})

            # Revert all active injections
            self._revert_all_injections(execution)

            execution.status = ScenarioStatus.COMPLETED
            execution.completed_at = datetime.utcnow()

            self._notify_observers(execution, "scenario_completed", execution.to_dict())

        except Exception as e:
            logger.error(f"Scenario execution failed: {e}")
            execution.status = ScenarioStatus.FAILED
            execution.completed_at = datetime.utcnow()
            execution.notes = f"Error: {str(e)}"
            self._notify_observers(execution, "scenario_failed", {"error": str(e)})

    def _create_injection_from_config(self, config: Dict[str, Any]) -> Optional[FailureInjection]:
        """Create FailureInjection from config dict."""
        try:
            return FailureInjection(
                id=config.get("id", f"inj-{uuid.uuid4().hex[:8]}"),
                failure_type=FailureType(config["failure_type"]),
                target=InjectionTarget(config["target"]),
                target_selector=config["target_selector"],
                parameters=config.get("parameters", {}),
                start_delay_seconds=config.get("start_delay_seconds", 0),
                duration_seconds=config.get("duration_seconds", 300),
                ramp_up_seconds=config.get("ramp_up_seconds", 0),
                ramp_down_seconds=config.get("ramp_down_seconds", 0),
                preconditions=config.get("preconditions", []),
                postconditions=config.get("postconditions", []),
                description=config.get("description", ""),
                tags=config.get("tags", [])
            )
        except Exception as e:
            logger.error(f"Failed to create injection from config: {e}")
            return None

    def _revert_all_injections(self, execution: ScenarioExecution) -> None:
        """Revert all active injections."""
        for inj_id, inj_data in execution.active_injections.items():
            injection = FailureInjection(**inj_data["injection"])
            result = inj_data["result"]
            self.injector.revert(injection, result)

    def pause_execution(self, execution_id: str) -> bool:
        """Pause a running execution."""
        execution = self.executions.get(execution_id)
        if not execution or execution.status != ScenarioStatus.RUNNING:
            return False

        execution.status = ScenarioStatus.PAUSED
        # In a real implementation, would pause the thread
        return True

    def resume_execution(self, execution_id: str) -> bool:
        """Resume a paused execution."""
        execution = self.executions.get(execution_id)
        if not execution or execution.status != ScenarioStatus.PAUSED:
            return False

        execution.status = ScenarioStatus.RUNNING
        return True

    def abort_execution(self, execution_id: str) -> bool:
        """Abort a running execution."""
        execution = self.executions.get(execution_id)
        if not execution or execution.status not in [ScenarioStatus.RUNNING, ScenarioStatus.PAUSED]:
            return False

        stop_flag = self._stop_flags.get(execution_id)
        if stop_flag:
            stop_flag.set()

        # Revert active injections
        self._revert_all_injections(execution)

        execution.status = ScenarioStatus.ABORTED
        execution.completed_at = datetime.utcnow()

        self._notify_observers(execution, "scenario_aborted", {})
        return True

    def get_execution(self, execution_id: str) -> Optional[ScenarioExecution]:
        """Get execution by ID."""
        return self.executions.get(execution_id)

    def record_observation(self, execution_id: str, observation: Dict[str, Any]) -> bool:
        """Record an observation during execution."""
        execution = self.executions.get(execution_id)
        if not execution:
            return False

        observation["timestamp"] = datetime.utcnow().isoformat()
        execution.observations.append(observation)
        return True

    def record_metrics_snapshot(self, execution_id: str, metrics: Dict[str, Any]) -> bool:
        """Record a metrics snapshot during execution."""
        execution = self.executions.get(execution_id)
        if not execution:
            return False

        snapshot = {
            "timestamp": datetime.utcnow().isoformat(),
            "metrics": metrics
        }
        execution.metrics_snapshots.append(snapshot)
        return True

    def submit_findings(
        self,
        execution_id: str,
        blast_radius: List[str],
        symptoms: List[str],
        root_cause: str,
        time_to_detection: float,
        time_to_resolution: float = 0
    ) -> bool:
        """Submit findings from the exercise."""
        execution = self.executions.get(execution_id)
        if not execution:
            return False

        execution.actual_blast_radius = blast_radius
        execution.actual_symptoms = symptoms
        execution.root_cause_identified = True
        execution.identified_root_cause = root_cause
        execution.time_to_detection_minutes = time_to_detection
        execution.time_to_resolution_minutes = time_to_resolution

        return True


# Pre-defined scenarios
def create_training_scenarios() -> List[ChaosScenario]:
    """Create a set of training scenarios."""
    scenarios = []

    # Scenario 1: Simple latency spike
    scenarios.append(ChaosScenario(
        id="scenario-latency-spike",
        name="Payment API Latency Spike",
        description="Inject latency into payment-api to simulate downstream dependency slowdown",
        severity=Severity.LOW,
        injections=[
            FailureInjection(
                id="inj-latency-1",
                failure_type=FailureType.LATENCY_SPIKE,
                target=InjectionTarget.SERVICE,
                target_selector="app=payment-api",
                parameters={"latency_ms": 5000, "jitter_ms": 1000},
                duration_seconds=300,
                description="Add 5s latency to payment-api calls"
            )
        ],
        phases=[
            {
                "name": "Inject Latency",
                "duration_seconds": 300,
                "injections": [
                    {
                        "id": "inj-latency-1",
                        "failure_type": "latency_spike",
                        "target": "service",
                        "target_selector": "app=payment-api",
                        "parameters": {"latency_ms": 5000, "jitter_ms": 1000},
                        "duration_seconds": 300
                    }
                ]
            },
            {
                "name": "Observe & Diagnose",
                "duration_seconds": 600,
                "injections": []
            }
        ],
        expected_blast_radius=["payment-api", "checkout-service", "order-service"],
        expected_symptoms=["increased p99 latency", "timeout errors", "checkout failures"],
        expected_root_cause="Downstream dependency (payment-gateway) latency",
        learning_objectives=[
            "Identify latency propagation through service mesh",
            "Use distributed tracing to find bottleneck",
            "Apply circuit breaker pattern"
        ],
        skills_tested=["distributed tracing", "service mesh observability", "circuit breaker"],
        max_duration_minutes=20,
        tags=["latency", "payment", "beginner"]
    ))

    # Scenario 2: Pod crash cascade
    scenarios.append(ChaosScenario(
        id="scenario-pod-crash-cascade",
        name="Inventory Service Pod Crash Cascade",
        description="Crash inventory pods and observe cascade to dependent services",
        severity=Severity.MEDIUM,
        injections=[
            FailureInjection(
                id="inj-crash-1",
                failure_type=FailureType.POD_CRASH,
                target=InjectionTarget.SERVICE,
                target_selector="app=inventory-service",
                parameters={"grace_period": 0, "mock_pods": ["inventory-pod-1", "inventory-pod-2", "inventory-pod-3"]},
                duration_seconds=180,
                description="Kill all inventory-service pods"
            )
        ],
        phases=[
            {
                "name": "Crash Pods",
                "duration_seconds": 60,
                "injections": [
                    {
                        "id": "inj-crash-1",
                        "failure_type": "pod_crash",
                        "target": "service",
                        "target_selector": "app=inventory-service",
                        "parameters": {"grace_period": 0},
                        "duration_seconds": 180
                    }
                ]
            },
            {
                "name": "Cascade Observation",
                "duration_seconds": 300,
                "injections": []
            }
        ],
        expected_blast_radius=["inventory-service", "product-service", "search-service", "recommendation-engine"],
        expected_symptoms=["503 errors", "circuit breaker open", "fallback responses", "increased error rates"],
        expected_root_cause="Inventory service pods OOMKilled due to memory leak",
        learning_objectives=[
            "Understand blast radius through service dependencies",
            "Identify cascade failure patterns",
            "Implement proper health checks and circuit breakers"
        ],
        skills_tested=["blast radius analysis", "cascade detection", "resilience patterns"],
        max_duration_minutes=15,
        tags=["pod-crash", "cascade", "intermediate"]
    ))

    # Scenario 3: CPU exhaustion
    scenarios.append(ChaosScenario(
        id="scenario-cpu-exhaustion",
        name="Recommendation Engine CPU Exhaustion",
        description="Exhaust CPU on recommendation engine causing timeout cascade",
        severity=Severity.HIGH,
        injections=[
            FailureInjection(
                id="inj-cpu-1",
                failure_type=FailureType.CPU_EXHAUSTION,
                target=InjectionTarget.SERVICE,
                target_selector="app=recommendation-engine",
                parameters={"cpu_cores": 4, "mock_pods": ["rec-pod-1", "rec-pod-2"]},
                duration_seconds=300,
                description="Consume 4 CPU cores on recommendation pods"
            )
        ],
        phases=[
            {
                "name": "CPU Exhaustion",
                "duration_seconds": 300,
                "injections": [
                    {
                        "id": "inj-cpu-1",
                        "failure_type": "cpu_exhaustion",
                        "target": "service",
                        "target_selector": "app=recommendation-engine",
                        "parameters": {"cpu_cores": 4},
                        "duration_seconds": 300
                    }
                ]
            }
        ],
        expected_blast_radius=["recommendation-engine", "homepage-service", "personalization-api"],
        expected_symptoms=["high CPU usage", "request timeouts", "thread pool exhaustion", "504 gateway timeout"],
        expected_root_cause="Inefficient ML model inference consuming all CPU",
        learning_objectives=[
            "Detect resource exhaustion via metrics",
            "Understand timeout propagation",
            "Implement resource limits and autoscaling"
        ],
        skills_tested=["resource monitoring", "autoscaling", "performance profiling"],
        max_duration_minutes=15,
        tags=["cpu", "resource-exhaustion", "ml", "advanced"]
    ))

    # Scenario 4: Network partition
    scenarios.append(ChaosScenario(
        id="scenario-network-partition",
        name="Database Network Partition",
        description="Partition network between services and database",
        severity=Severity.CRITICAL,
        injections=[
            FailureInjection(
                id="inj-net-1",
                failure_type=FailureType.NETWORK_PARTITION,
                target=InjectionTarget.SERVICE,
                target_selector="app=order-service",
                parameters={"target_selector": "app=postgres", "direction": "egress"},
                duration_seconds=240,
                description="Block egress from order-service to database"
            )
        ],
        phases=[
            {
                "name": "Network Partition",
                "duration_seconds": 240,
                "injections": [
                    {
                        "id": "inj-net-1",
                        "failure_type": "network_partition",
                        "target": "service",
                        "target_selector": "app=order-service",
                        "parameters": {"target_selector": "app=postgres", "direction": "egress"},
                        "duration_seconds": 240
                    }
                ]
            }
        ],
        expected_blast_radius=["order-service", "payment-service", "inventory-service", "notification-service"],
        expected_symptoms=["database connection errors", "transaction failures", "dead letter queue growth", "data inconsistency"],
        expected_root_cause="Network policy misconfiguration blocking database access",
        learning_objectives=[
            "Diagnose network-level failures",
            "Understand database connection pool behavior",
            "Implement graceful degradation"
        ],
        skills_tested=["network debugging", "database connectivity", "graceful degradation"],
        max_duration_minutes=15,
        tags=["network", "database", "critical", "advanced"]
    ))

    # Scenario 5: Multi-failure complex scenario
    scenarios.append(ChaosScenario(
        id="scenario-complex-multi",
        name="Black Friday Multi-Failure",
        description="Complex scenario with multiple simultaneous failures during peak traffic",
        severity=Severity.CRITICAL,
        injections=[
            FailureInjection(
                id="inj-multi-1",
                failure_type=FailureType.LATENCY_SPIKE,
                target=InjectionTarget.SERVICE,
                target_selector="app=payment-gateway",
                parameters={"latency_ms": 10000, "jitter_ms": 5000},
                duration_seconds=600,
                description="Payment gateway extreme latency"
            ),
            FailureInjection(
                id="inj-multi-2",
                failure_type=FailureType.CPU_EXHAUSTION,
                target=InjectionTarget.SERVICE,
                target_selector="app=checkout-service",
                parameters={"cpu_cores": 8},
                duration_seconds=600,
                description="Checkout service CPU saturation"
            ),
            FailureInjection(
                id="inj-multi-3",
                failure_type=FailureType.POD_CRASH,
                target=InjectionTarget.SERVICE,
                target_selector="app=notification-service",
                parameters={"grace_period": 0},
                duration_seconds=600,
                description="Notification service pods crash"
            )
        ],
        phases=[
            {
                "name": "Simultaneous Failures",
                "duration_seconds": 600,
                "injections": [
                    {
                        "id": "inj-multi-1",
                        "failure_type": "latency_spike",
                        "target": "service",
                        "target_selector": "app=payment-gateway",
                        "parameters": {"latency_ms": 10000, "jitter_ms": 5000},
                        "duration_seconds": 600
                    },
                    {
                        "id": "inj-multi-2",
                        "failure_type": "cpu_exhaustion",
                        "target": "service",
                        "target_selector": "app=checkout-service",
                        "parameters": {"cpu_cores": 8},
                        "duration_seconds": 600
                    },
                    {
                        "id": "inj-multi-3",
                        "failure_type": "pod_crash",
                        "target": "service",
                        "target_selector": "app=notification-service",
                        "parameters": {"grace_period": 0},
                        "duration_seconds": 600
                    }
                ]
            }
        ],
        expected_blast_radius=["payment-gateway", "checkout-service", "notification-service", "order-service", "email-service", "sms-service"],
        expected_symptoms=["payment timeouts", "checkout failures", "notification delays", "order processing backlog", "customer complaints"],
        expected_root_cause="Combined: payment gateway degradation + checkout resource exhaustion + notification outage",
        learning_objectives=[
            "Prioritize multiple simultaneous incidents",
            "Coordinate across teams during major outage",
            "Communicate effectively with stakeholders"
        ],
        skills_tested=["incident command", "multi-team coordination", "stakeholder communication", "triage"],
        max_duration_minutes=30,
        tags=["multi-failure", "black-friday", "war-room", "expert"]
    ))

    return scenarios


if __name__ == "__main__":
    # Demo
    logging.basicConfig(level=logging.INFO)

    # Create engine
    injector = KubernetesFailureInjector()
    engine = ScenarioEngine(injector)

    # Register scenarios
    for scenario in create_training_scenarios():
        engine.register_scenario(scenario)

    # List scenarios
    print("=== Available Scenarios ===")
    for scenario in engine.list_scenarios():
        print(f"  {scenario.id}: {scenario.name} ({scenario.severity.value})")
        print(f"    {scenario.description}")
        print(f"    Objectives: {scenario.learning_objectives}")
        print()

    # Execute a scenario (dry run)
    print("=== Dry Run Execution ===")
    execution = engine.execute_scenario("scenario-latency-spike", executed_by="trainer", dry_run=True)
    print(f"Execution: {execution.id}")
    print(f"Status: {execution.status.value}")

    # Show scenario details
    scenario = engine.get_scenario("scenario-pod-crash-cascade")
    print(f"\n=== Scenario Details: {scenario.name} ===")
    print(json.dumps(scenario.to_dict(), indent=2, default=str))