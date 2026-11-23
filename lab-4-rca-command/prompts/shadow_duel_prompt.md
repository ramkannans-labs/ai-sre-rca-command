# Shadow Duel Exercise Prompts

## Overview

Shadow Duel is a signature exercise where a human investigator and an AI investigator work on the SAME incident in PARALLEL, with identical starting information. The goal is to compare investigation methodologies, identify strengths/weaknesses of each approach, and improve both human and AI RCA capabilities.

---

## Shadow Duel System Prompt (AI Investigator)

```
You are the AI Investigator in a Shadow Duel exercise.

EXERCISE CONTEXT:
- Exercise ID: {exercise_id}
- Scenario: {scenario_name}
- Difficulty: {difficulty} (beginner|intermediate|advanced)
- Time Limit: {time_limit_minutes} minutes
- Human Investigator: {human_name} (working in parallel)

YOUR ROLE:
- Investigate the incident using systematic RCA methodology
- Document EVERY step, query, hypothesis, and reasoning
- Your process will be compared against the human investigator's process
- Be explicit about WHY you chose each action and HOW results update your thinking

INCIDENT STARTING INFORMATION:
{incident_brief}

AVAILABLE TOOLS (via MCP):
- mcp.metrics.query: Prometheus queries
- mcp.logs.query: Loki queries
- mcp.traces.query: Tempo queries
- mcp.kb.search: Knowledge base search
- mcp.runbook.search: Runbook search
- mcp.architecture.search: Architecture docs search
- mcp.deployments.query: Recent deployment history

SHADOW DUEL SPECIFIC REQUIREMENTS:
1. Output your investigation as a structured log (see format below)
2. At each decision point, record: action, expected_outcome, actual_outcome, reasoning, confidence_delta
3. When you form/reject hypotheses, explain the evidence chain
4. If you consult knowledge base/runbooks, record what you searched and what you found
5. Flag any point where you would want human input (domain knowledge, business context, approval)

OUTPUT FORMAT - Continuous Investigation Log:
```json
{
  "exercise_id": "{exercise_id}",
  "investigator": "AI",
  "timestamp": "ISO",
  "step": 1,
  "phase": "evidence_gathering|hypothesis_formation|hypothesis_testing|root_cause_identification|mitigation_planning|documentation",
  "action": {
    "type": "query_metrics|query_logs|query_traces|search_kb|search_runbook|search_architecture|query_deployments|form_hypothesis|test_hypothesis|update_confidence|request_human_input",
    "details": {...},
    "expected_outcome": "...",
    "actual_outcome": "...",
    "reasoning": "WHY this action, WHAT I expected, HOW it changes my thinking",
    "confidence_delta": -1.0 to 1.0
  },
  "current_hypotheses": [
    {"id": "hyp-001", "description": "...", "confidence": 0.0-1.0, "status": "active|testing|confirmed|rejected", "evidence": [...]}
  ],
  "evidence_summary": {...},
  "time_elapsed_seconds": 120,
  "stalled": false,
  "request_human_input": {"type": "...", "question": "...", "context": "..."}
}
```

CALIBRATION REQUIREMENTS:
- Be honest about uncertainty; overconfidence is penalized in comparison
- Explicitly record when evidence contradicts your leading hypothesis
- Show your work - the comparison metrics evaluate PROCESS not just outcome
- If stuck > 5 minutes, set stalled=true and request_human_input

SUCCESS CRITERIA (for comparison):
1. Time to root cause identification
2. Hypothesis quality (number, diversity, calibration)
3. Evidence thoroughness (metrics, logs, traces, deployments, KB)
4. Process discipline (structured approach, documentation)
5. Collaboration readiness (appropriate human escalation)
6. Final confidence calibration accuracy
```

---

## Human Investigator Briefing Document

```
SHADOW DUEL EXERCISE - HUMAN INVESTIGATOR BRIEFING

Exercise ID: {exercise_id}
Scenario: {scenario_name}
Difficulty: {difficulty}
Time Limit: {time_limit_minutes} minutes
Date: {date}

INCIDENT BRIEFING:
{incident_brief}

YOUR MISSION:
Investigate this incident and identify the root cause. You have access to all standard observability tools and documentation. An AI investigator is working on the SAME incident in parallel with identical starting information.

TOOLS AVAILABLE:
- Grafana (metrics dashboards, Explore)
- Loki (log queries)
- Tempo (trace queries)
- Knowledge Base (Confluence/Notion/ChromaDB)
- Runbook Repository
- Architecture Documentation
- Deployment History (ArgoCD/Flux/GitHub)
- kubectl (cluster access)

RECORDING REQUIREMENTS:
Please document your investigation using the provided template. Record:
1. Each query you run and why
2. Each hypothesis you form and your confidence (1-10 scale)
3. Evidence that supports/contradicts each hypothesis
4. Decision points and why you chose each path
5. When you consult runbooks/KB/architecture docs
6. Moments of uncertainty or being stuck
7. Final root cause and confidence

TEMPLATE (use this format):
```
STEP 1 - {timestamp} - Phase: Evidence Gathering
ACTION: Queried payment-service latency p99
QUERY: histogram_quantile(0.99, rate(http_request_duration_seconds_bucket{service="payment"}[5m]))
REASONING: Golden signal - latency is the primary symptom
EXPECTED: Confirm latency spike
ACTUAL: p99 = 2.5s (baseline 200ms)
CONFIDENCE IMPACT: +2 on "latency issue confirmed"

STEP 2 - {timestamp} - Phase: Evidence Gathering
ACTION: Checked recent deployments
TOOL: ArgoCD UI
REASONING: Correlation with recent changes
ACTUAL: payment-service v2.3.1 deployed 30 min ago
CONFIDENCE IMPACT: +1 on "deployment-related"
HYPOTHESIS FORMED: "New deployment caused regression" (confidence: 6/10)
```

POST-EXERCISE:
After time expires or you identify root cause, you'll receive the AI's investigation log. You'll then:
1. Compare methodologies
2. Identify where each approach excelled/struggled
3. Discuss calibration differences
4. Extract lessons for both human and AI RCA improvement
```

---

## Exercise Scenarios (Pre-built)

### Scenario 1: Latency Spike (Beginner)
```yaml
exercise_id: "sd-001"
scenario_name: "Payment Service Latency Spike"
difficulty: "beginner"
time_limit_minutes: 20
incident_brief: |
  ALERT: payment-service p99 latency > 2s (threshold: 500ms)
  START: 2024-01-15T10:30:00Z
  SYMPTOMS:
  - Payment API p99 latency: 2.5s (baseline: 200ms)
  - Error rate: 2% (baseline: 0.1%)
  - Throughput: Normal
  - Affected endpoints: /api/v1/payments, /api/v1/refunds
  RECENT CHANGES:
  - payment-service v2.3.1 deployed 25 min ago (feature: new reporting query)
  - No database schema changes
  - No infrastructure changes
  ARCHITECTURE: payment-service (Java Spring Boot) -> PostgreSQL (RDS) -> Redis cache
learning_objectives:
  - Practice golden signals investigation
  - Correlation of deployment timing with symptom onset
  - Connection pool exhaustion pattern recognition
  - Runbook consultation for standard mitigation
expected_root_cause: "Database connection pool exhaustion in payment-service v2.3.1 due to missing connection cleanup in new reporting query code path"
key_evidence:
  - Logs: "HikariPool-1 - Pool exhausted" errors
  - Metrics: DB connection pool active=max, wait queue growing
  - Traces: 95% span time in DB calls
  - Deployment: v2.3.1 changelog shows connection handling refactor
```

### Scenario 2: Pod Crash Cascade (Intermediate)
```yaml
exercise_id: "sd-002"
scenario_name: "Order Service Pod Crash Cascade"
difficulty: "intermediate"
time_limit_minutes: 30
incident_brief: |
  ALERT: order-service pods crashing, 50% replica loss in 5 min
  START: 2024-01-15T14:22:00Z
  SYMPTOMS:
  - order-service: 3/6 pods Running, 3 CrashLoopBackOff
  - Restart count: 12+ per affected pod
  - Downstream: payment-service error rate 15% (calls to order-service failing)
  - Upstream: api-gateway 5xx errors 8%
  RECENT CHANGES:
  - order-service v1.4.0 deployed 40 min ago (memory optimization)
  - Kafka cluster upgraded to 3.6.0 2 hours ago
  - New feature flag "async-processing" enabled 35 min ago
  ARCHITECTURE: api-gateway -> order-service (Kafka consumer) -> payment-service, inventory-service
  - order-service consumes from Kafka topic "orders"
  - Produces to "payment-requests", "inventory-reservations"
learning_objectives:
  - Multi-service blast radius analysis
  - Kafka consumer group rebalance behavior under crashes
  - Feature flag rollout risk assessment
  - Distinguishing cascade cause vs effect
expected_root_cause: "order-service v1.4.0 introduced OOM in async processing path when feature flag enabled; Kafka rebalance storms amplify crashes"
key_evidence:
  - Pod logs: OOMKilled, heap dump shows AsyncProcessor holding references
  - Metrics: order-service memory spike at flag enable time, Kafka consumer lag exponential
  - Traces: payment-service calls timing out waiting for order-service
  - Deployment: v1.4.0 changed AsyncProcessor to use CompletableFuture without proper cleanup
```

### Scenario 3: CPU Exhaustion (Intermediate)
```yaml
exercise_id: "sd-003"
scenario_name: "Recommendation Engine CPU Exhaustion"
difficulty: "intermediate"
time_limit_minutes: 25
incident_brief: |
  ALERT: recommendation-service CPU > 95% sustained, latency degraded
  START: 2024-01-15T09:15:00Z
  SYMPTOMS:
  - recommendation-service: CPU 98% (all cores), p99 latency 5s (baseline: 100ms)
  - Error rate: 0% (requests eventually complete)
  - HPA: scaling but new pods also hit 95% CPU
  - No increase in request volume
  RECENT CHANGES:
  - recommendation-service v3.2.0 deployed 3 hours ago (algorithm update)
  - ML model artifact updated 4 hours ago (v4.1 -> v4.2)
  - Traffic shadowing enabled for v3.2.0 3 hours ago
  ARCHITECTURE: api-gateway -> recommendation-service (Python Flask + ML inference) -> feature-store (Redis) -> model-registry (S3)
learning_objectives:
  - CPU profiling in production
  - ML model performance regression detection
  - Distinguishing code vs model vs config changes
  - Capacity planning vs performance bug
expected_root_cause: "Model v4.2 increased inference complexity 10x (new attention layers); v3.2.0 removed batching optimization that previously masked this"
key_evidence:
  - Metrics: CPU per pod, request latency distribution, model inference time histogram
  - Logs: "Inference time: 450ms" (was 40ms), no errors
  - Deployment: v3.2.0 removed request batching; model v4.2 changelog shows architecture change
  - Profiler: 85% CPU in model.forward(), 10% in feature preprocessing
```

### Scenario 4: Network Partition (Advanced)
```yaml
exercise_id: "sd-004"
scenario_name: "Cross-AZ Network Partition"
difficulty: "advanced"
time_limit_minutes: 35
incident_brief: |
  ALERT: Multiple services degraded in us-east-1a, intermittent 5xx
  START: 2024-01-15T16:45:00Z
  SYMPTOMS:
  - user-service (us-east-1a): 50% requests timeout
  - payment-service (us-east-1a): 30% requests timeout
  - inventory-service (us-east-1b): Normal
  - Cross-service calls between AZs: 40% failure
  - Within same AZ: Normal
  RECENT CHANGES:
  - AWS VPC CNI plugin upgraded 6 hours ago
  - New NetworkPolicy applied to user-service namespace 4 hours ago
  - EKS cluster control plane upgraded to 1.28 12 hours ago
  ARCHITECTURE: 3-AZ EKS cluster, services distributed across AZs, ALB cross-zone load balancing enabled
  - user-service: 2 pods in 1a, 2 in 1b, 2 in 1c
  - payment-service: 3 pods in 1a, 3 in 1b
  - inventory-service: 2 pods in 1b, 2 in 1c
learning_objectives:
  - Network-level failure diagnosis
  - Cross-AZ dependency mapping
  - Kubernetes networking (CNI, NetworkPolicy, Service topology)
  - Partial failure vs complete outage reasoning
expected_root_cause: "NetworkPolicy on user-service namespace blocked inter-AZ traffic; CNI upgrade changed default allow behavior; only user-service affected directly but payment-service calls user-service cross-AZ"
key_evidence:
  - Metrics: Cross-AZ TCP connection failures, ALB target group health checks failing for 1a targets
  - Logs: "connection timeout" from payment-service to user-service (1a pods only)
  - kubectl: NetworkPolicy spec shows ingress only from same namespace
  - AWS: VPC flow logs show SYN packets dropped at ENI level for cross-AZ
  - Deployment: NetworkPolicy applied 4h ago, symptoms match timing
```

### Scenario 5: Black Friday Multi-Failure (Advanced)
```yaml
exercise_id: "sd-005"
scenario_name: "Black Friday Composite Failure"
difficulty: "advanced"
time_limit_minutes: 45
incident_brief: |
  ALERT: SEV-1 - Checkout flow failing, revenue impact critical
  START: 2024-11-29T08:00:00Z (Black Friday)
  SYMPTOMS:
  - Checkout conversion rate dropped 60% in 10 min
  - api-gateway: 25% 5xx errors
  - payment-service: p99 latency 8s, error rate 12%
  - inventory-service: p99 latency 3s, error rate 5%
  - notification-service: 100% queue backlog (50k messages)
  - Database (RDS): CPU 95%, connections 900/1000
  RECENT CHANGES:
  - Black Friday feature flags enabled 07:00 (flash-sales, bundle-offers, guest-checkout)
  - payment-service v4.0.0 deployed 06:30 (new fraud detection)
  - inventory-service v2.1.0 deployed 06:45 (reservation timeout reduction)
  - DB parameter group changed 05:00 (max_connections 1000->500 by mistake)
  - Traffic: 5x normal volume since 07:00
  ARCHITECTURE: Full microservices (15+ services), event-driven via Kafka, PostgreSQL RDS, Redis ElastiCache
  - Checkout flow: api-gateway -> cart -> inventory -> payment -> notification -> order
  - Flash sales create burst traffic patterns
learning_objectives:
  - Multi-root-cause analysis under time pressure
  - Prioritization when multiple failures compound
  - Distinguishing trigger vs amplifier vs independent failures
  - Executive communication during active incident
  - Rollback vs fix-forward decision making
expected_root_causes: (MULTIPLE)
  1. DB max_connections reduced to 500 (config error) - primary bottleneck
  2. payment-service v4.0.0 fraud detection adds 2s synchronous external API call
  3. inventory-service v2.1.0 reduced reservation TTL causing retry storms
  4. Flash sales traffic 5x exceeds capacity even without bugs
key_evidence:
  - Metrics: DB connections at limit, payment latency breakdown shows 2s in fraud API, inventory retries 10x
  - Logs: "connection refused" from payment to DB, "reservation expired" in inventory, fraud API timeouts
  - Deployments: All 3 changes correlate with symptom onset
  - Config: DB parameter group change at 05:00 shows max_connections=500
  - Traffic: 5x baseline confirmed via ALB metrics
```

---

## Comparison Metrics Framework

### Quantitative Metrics

| Metric | Human | AI | Notes |
|--------|-------|-----|-------|
| Time to first hypothesis (min) | | | |
| Time to root cause (min) | | | |
| Number of hypotheses formed | | | Target: 3-5 |
| Hypothesis diversity (categories) | | | Resource, deployment, config, network, code |
| Evidence sources queried | | | Metrics, logs, traces, deployments, KB, runbooks, architecture |
| Queries per evidence source | | | |
| Calibration error (final confidence vs ground truth) | | | Lower is better |
| Contradicting evidence acknowledged | | | Count |
| Human escalation requests | | | Appropriate vs excessive |
| Process steps documented | | | Completeness |

### Qualitative Assessment

**Process Quality (1-5 each):**
- Structure: Followed systematic phases vs ad-hoc
- Documentation: Thoroughness of reasoning capture
- Falsification: Actively sought disconfirming evidence
- Collaboration: Appropriate use of runbooks/KB/team knowledge
- Adaptability: Adjusted approach when stuck

**Outcome Quality:**
- Root cause accuracy: Correct / Partially correct / Incorrect
- Contributing factors identified: Complete / Partial / Missing
- Mitigation appropriateness: Immediate + short + long term
- Communication clarity: Actionable for stakeholders

### Duel Report Template

```
SHADOW DUEL REPORT
Exercise: {exercise_id} - {scenario_name}
Date: {date}
Duration: {actual_duration_minutes} min (limit: {limit} min)

PARTICIPANTS:
- Human: {human_name}, Role: {human_role}, Experience: {years} yrs
- AI: {ai_model_version}

GROUND TRUTH:
- Root Cause: {root_cause}
- Contributing Factors: {list}

RESULTS SUMMARY:
| Metric | Human | AI | Winner |
|--------|-------|-----|--------|
| Time to Root Cause | X min | Y min | Human/AI/Tie |
| Hypothesis Count | N | M | |
| Calibration Error | 0.XX | 0.YY | |
| Evidence Sources | N/7 | M/7 | |

DETAILED COMPARISON:

PHASE 1 - EVIDENCE GATHERING:
Human: {summary of approach, sources, thoroughness}
AI: {summary}
Observations: {key differences}

PHASE 2 - HYPOTHESIS FORMATION:
Human: {hypotheses, confidence, diversity}
AI: {hypotheses, confidence, diversity}
Observations: {key differences}

PHASE 3 - HYPOTHESIS TESTING:
Human: {testing approach, queries, pivots}
AI: {testing approach, queries, pivots}
Observations: {key differences}

PHASE 4 - ROOT CAUSE IDENTIFICATION:
Human: {final RC, confidence, evidence chain}
AI: {final RC, confidence, evidence chain}
Observations: {accuracy, calibration}

PHASE 5 - MITIGATION PLANNING:
Human: {mitigations proposed}
AI: {mitigations proposed}
Observations: {completeness, practicality}

KEY INSIGHTS:
1. {insight about human strength}
2. {insight about AI strength}
3. {insight about complementary capabilities}
4. {insight about process improvement for humans}
5. {insight about AI prompt/architecture improvement}

LESSONS LEARNED:
- For Human Investigators: {actionable takeaways}
- For AI RCA Development: {actionable takeaways}
- For Shadow Duel Design: {format/tool improvements}

RECOMMENDATIONS:
- Next exercise focus: {area}
- Tool/access improvements: {list}
- Training priorities: {list}
```

---

## Facilitator Guide

### Pre-Exercise Setup (15 min before)
1. [ ] Deploy scenario to staging environment
2. [ ] Inject failure (run scenario injection script)
3. [ ] Verify symptoms match expected
4. [ ] Prepare incident briefing document
5. [ ] Set up recording templates for both investigators
6. [ ] Brief human investigator on recording format
7. [ ] Start AI investigator with system prompt
8. [ ] Synchronize start time

### During Exercise
- Monitor both investigators' progress
- Provide time warnings at 50%, 75%, 90%
- If human asks for clarification, provide equally to AI (via prompt injection)
- Do NOT hint or guide investigation
- Note interesting moments for debrief

### Post-Exercise (30 min)
1. Collect investigation logs from both
2. Run automated comparison (metrics_collector.py)
3. Facilitate debrief discussion using report template
4. Capture lessons learned
5. Archive logs for research/improvement

### Scoring Calibration
- Run each scenario 3+ times with different humans to establish baselines
- Track AI performance across model versions
- Use results to improve prompts, tool access, knowledge base