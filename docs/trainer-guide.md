# Week 4 Trainer Guide: Agent RCA & Incident Command

> **Audience:** Lead AI SRE Trainers  
> **Format:** Instructor-led with hands-on labs  
> **Prerequisites:** Weeks 1-3 completed (EKS, Telemetry/MCP, SLO/Budgets)  
> **Environment:** AWS EKS only — no GCP/Azure references

---

## 🎯 Session Overview

| Phase | Duration | Activity |
|-------|----------|----------|
| **Phase 1** | 30 min | RCA Agent Architecture & Deployment |
| **Phase 2** | 45 min | Knowledge Base Construction |
| **Phase 3** | 30 min | Incident Command System (ICS) Setup |
| **Phase 4** | 90 min | **Shadow Duel Exercise** (Signature Lab) |
| **Phase 5** | 30 min | Post-Incident Review Automation |
| **Phase 6** | 60 min | Capstone: Full Incident Response |

**Total:** ~4.5 hours (can be split across 2 sessions)

---

## 📋 Phase 1: RCA Agent Architecture & Deployment (30 min)

### Learning Objectives
- Understand the RCA agent architecture: evidence collection → hypothesis generation → confidence scoring
- Deploy the RCA agent to EKS with proper RBAC and MCP integration
- Configure telemetry access (Prometheus, Loki, Tempo via MCP)

### Instructor Demo (15 min)

```bash
# 1. Show the agent architecture
cat lab-4-rca-command/rca-agent/agent.py | head -80

# 2. Deploy via GitHub Actions (manual trigger)
gh workflow run rca-agent-deploy.yml \
  -f environment=staging \
  -f mcp-url=http://mcp-server:8082

# 3. Verify deployment
kubectl get pods -n ai-sre-rca -l app=rca-agent
kubectl logs -n ai-sre-rca -l app=rca-agent --tail=50
```

### Key Talking Points

| Concept | Explanation |
|---------|-------------|
| **Evidence Collection** | Agent queries MCP for metrics (Prometheus), logs (Loki), traces (Tempo) — unified interface |
| **Hypothesis Generation** | Uses service topology (from Week 2 knowledge graph) to generate ranked causes |
| **Confidence Scoring** | Weights: metrics (0.3), logs (0.25), traces (0.2), topology (0.15), history (0.1) |
| **MCP Integration** | Single interface for all telemetry — agent doesn't need to know PromQL/LogQL/TraceQL |

### Hands-On (15 min)

Learners deploy RCA agent to their namespace and verify it can query MCP.

```bash
# Learner exercise
cd lab-4-rca-command/scripts
./setup_rca_stack.sh development  # deploys to their namespace
```

### Common Issues & Fixes

| Issue | Resolution |
|-------|------------|
| Agent can't reach MCP | Check MCP service name/port in values.yaml; verify network policies |
| Prometheus queries timeout | Increase MCP query timeout; check Prometheus resource limits |
| RBAC errors | Ensure ServiceAccount has `prometheus`, `loki`, `tempo` ClusterRole bindings |

---

## 📋 Phase 2: Knowledge Base Construction (45 min)

### Learning Objectives
- Build a vector database of past incidents for similarity search
- Parse and index runbooks with symptom-action mappings
- Index Architecture Decision Records (ADRs) for contextual awareness

### Instructor Demo (20 min)

```bash
# 1. Show knowledge base structure
ls lab-4-rca-command/knowledge-base/

# 2. Ingest sample incidents
./lab-4-rca-command/scripts/ingest_incidents.py \
  --source ./sample-incidents \
  --vector-db chroma \
  --namespace development

# 3. Query the knowledge base
python -c "
from knowledge_base.vector_store import VectorStore
vs = VectorStore('chroma', namespace='development')
results = vs.search('java-service latency spike after deployment', k=3)
for r in results:
    print(f'Score: {r.score:.3f} | {r.metadata[\"incident_id\"]} | {r.text[:100]}')
"
```

### Key Talking Points

| Component | Purpose |
|-----------|---------|
| **Vector Store** | ChromaDB for embeddings — similarity search on incident narratives |
| **Incident Ingestion** | Parses markdown/JSON incidents, extracts: symptoms, root cause, timeline, resolution |
| **Runbook Parser** | Extracts "if symptom X then action Y" rules from markdown runbooks |
| **ADR Index** | Links architectural decisions to services for context during RCA |

### Hands-On (25 min)

Learners create their own incident entries and add to knowledge base.

```bash
# Create sample incident
cat > my-incident.md << 'EOF'
---
incident_id: INC-2024-042
service: java-service
severity: SEV-2
date: 2024-03-15
root_cause: Connection pool exhaustion due to missing timeout config
---
## Symptoms
- 500 errors on /api/orders endpoint
- Latency p99 > 30s
- Thread pool queue full alerts

## Timeline
- 14:00: Deploy v2.3.1
- 14:05: Error rate spikes
- 14:12: Paged on-call
- 14:18: Root cause identified
- 14:25: Config fix deployed
- 14:30: Recovery confirmed

## Resolution
Added connection timeout=5s and max-pool-size=50 to HikariCP config
EOF

# Ingest it
./lab-4-rca-command/scripts/ingest_incidents.py \
  --source ./my-incident.md \
  --vector-db chroma
```

### Common Issues & Fixes

| Issue | Resolution |
|-------|------------|
| ChromaDB OOM | Limit batch size in ingestion; use persistent volume |
| Embedding model not found | Install `sentence-transformers`; download model on first run |
| Namespace isolation | Use separate Chroma collections per learner namespace |

---

## 📋 Phase 3: Incident Command System (ICS) Setup (30 min)

### Learning Objectives
- Understand software-adapted ICS roles and responsibilities
- Configure automated timeline reconstruction
- Set up escalation policies and communication channels

### Instructor Demo (15 min)

```bash
# 1. Show ICS role definitions
cat lab-4-rca-command/incident-command/ics_roles.py

# 2. Show escalation policy
cat lab-4-rca-command/incident-command/escalation_policy.py

# 3. Trigger test incident with ICS
gh workflow run incident-simulation.yml \
  -f scenario=single-service-degradation \
  -f severity=SEV-2 \
  -f namespace=development
```

### Key Talking Points

| ICS Role | Software Adaptation | Responsibilities |
|----------|---------------------|------------------|
| **Incident Commander** | Lead SRE / On-call | Owns incident, makes decisions, coordinates |
| **Operations Lead** | Service owner | Executes mitigation, runs runbooks |
| **Communications Lead** | SRE/EM | Stakeholder updates, status page, Slack |
| **Scribe** | Automated (timeline bot) | Records all events, decisions, actions |
| **SME** | Domain experts | Database, network, security specialists |

### Hands-On (15 min)

Learners configure their escalation policy and test timeline reconstruction.

```bash
# Configure escalation for their team
cat > my-escalation.yaml << 'EOF'
escalation:
  sev1:
    - delay: 0m
      role: incident_commander
      notify: ["oncall-primary", "oncall-secondary", "manager"]
    - delay: 15m
      role: operations_lead
      notify: ["service-owner", "tech-lead"]
    - delay: 30m
      notify: ["director", "vp-engineering"]
  sev2:
    - delay: 0m
      role: incident_commander
      notify: ["oncall-primary"]
    - delay: 30m
      notify: ["service-owner", "manager"]
EOF
```

---

## 📋 Phase 4: Shadow Duel Exercise (90 min) ⭐ SIGNATURE LAB

### Learning Objectives
- Experience parallel human vs AI investigation of the same incident
- Identify strengths/weaknesses of each approach
- Learn to combine human intuition with AI evidence gathering

### Exercise Structure

```
┌────────────────────────────────────────────────────────────────┐
│                    SHADOW DUEL FLOW                            │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  1. SETUP (10 min)                                            │
│     - Deploy incident scenario via chaos mesh                 │
│     - Assign: Human Investigator + AI RCA Agent               │
│     - Both start with SAME information: alert + dashboard     │
│                                                                │
│  2. INVESTIGATION (45 min)                                    │
│     ┌─────────────────────┐     ┌─────────────────────┐       │
│     │ HUMAN INVESTIGATOR  │     │    AI RCA AGENT     │       │
│     │ • Grafana dashboards│     │ • MCP tool access   │       │
│     │ • Runbook library   │     │ • Knowledge base    │       │
│     │ • Team Slack        │     │ • Hypothesis engine │       │
│     │ • kubectl access    │     │ • Evidence scorer   │       │
│     └──────────┬──────────┘     └──────────┬──────────┘       │
│                │                           │                   │
│                ▼                           ▼                   │
│     ┌─────────────────────────────────────────────────┐       │
│     │           SAME INCIDENT (hidden)                │       │
│     │  java-service: connection pool exhaustion       │       │
│     │  Triggered by: missing timeout config in v2.3.1 │       │
│     └─────────────────────────────────────────────────┘       │
│                                                                │
│  3. FINDINGS SUBMISSION (15 min)                              │
│     - Human: fills investigation form                         │
│     - AI: generates structured RCA report                     │
│                                                                │
│  4. COMPARISON & DEBRIEF (20 min)                             │
│     - Side-by-side comparison                                 │
│     - What did each miss?                                     │
│     - Combined approach discussion                            │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

### Instructor Setup (Before Session)

```bash
# 1. Prepare incident scenario
gh workflow run incident-simulation.yml \
  -f scenario=connection-pool-exhaustion \
  -f severity=SEV-2 \
  -f namespace=shadow-duel \
  -f inject-at=$(date -d '+2 minutes' -Iseconds)

# 2. Verify both investigators have access
# Human: Grafana dashboard URL, runbook links, Slack channel
# AI: RCA agent endpoint, MCP URL, knowledge base namespace
```

### Running the Shadow Duel

```bash
# Start the duel (run in separate terminals)
# Terminal 1: Human investigator works manually
# Terminal 2: AI agent runs investigation
./lab-4-rca-command/scripts/run_shadow_duel.sh \
  --incident-id INC-SHADOW-001 \
  --mode parallel \
  --human-investigator "$(whoami)" \
  --ai-agent rca-agent

# After completion, generate comparison
./lab-4-rca-command/scripts/run_shadow_duel.sh \
  --incident-id INC-SHADOW-001 \
  --mode compare
```

### Comparison Metrics

| Metric | Human | AI | Notes |
|--------|-------|-----|-------|
| Time to first hypothesis | __ min | __ min | |
| Time to root cause | __ min | __ min | |
| Hypothesis accuracy (top-1) | ✓/✗ | ✓/✗ | |
| Evidence cited | __ items | __ items | |
| Actions taken | __ | __ | |
| False leads pursued | __ | __ | |

### Debrief Questions

1. **What did the AI find that the human missed?** (e.g., correlated trace from 3 hops away)
2. **What did the human find that the AI missed?** (e.g., recent config change not in telemetry)
3. **Where did the AI hallucinate or chase false leads?**
4. **Where did human intuition accelerate the investigation?**
5. **What would the ideal combined workflow look like?**

### Expected Outcomes

- AI excels at: broad evidence gathering, correlation across services, historical pattern matching
- Human excels at: contextual reasoning, recent changes not in telemetry, stakeholder communication
- Combined: AI gathers evidence → Human synthesizes → AI validates hypotheses

---

## 📋 Phase 5: Post-Incident Review Automation (30 min)

### Learning Objectives
- Automate post-incident report generation
- Extract action items and track them to completion
- Feed lessons back into knowledge base

### Instructor Demo

```bash
# Generate post-incident report
./lab-4-rca-command/scripts/export_incident_report.py \
  --incident-id INC-2024-042 \
  --format markdown \
  --include-timeline \
  --include-action-items \
  --output ./post-incident-INC-2024-042.md

# View generated report
cat ./post-incident-INC-2024-042.md
```

### Report Sections

1. **Executive Summary** — One-paragraph for leadership
2. **Timeline** — Reconstructed from logs, alerts, comms, deployments
3. **Root Cause Analysis** — 5 Whys format
4. **Impact Assessment** — Customer impact, revenue, SLO breach
5. **What Went Well** — Detection, response, collaboration
6. **What Could Improve** — Gaps in monitoring, runbooks, process
7. **Action Items** — Owner, due date, tracking link

---

## 📋 Phase 6: Capstone — Full Incident Response (60 min)

### Scenario: "Black Friday Cascade"

```
┌─────────────────────────────────────────────────────────────────┐
│  SCENARIO: Multi-service cascade during peak traffic            │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  1. java-service: CPU saturation (bad query in v3.1.0)         │
│     │                                                           │
│     ▼ (downstream calls timeout)                               │
│  2. python-service: Thread pool exhaustion                      │
│     │                                                           │
│     ▼ (circuit breaker opens)                                  │
│  3. mcp-server: Query queue backup                              │
│     │                                                           │
│     ▼ (knowledge graph queries fail)                           │
│  4. correlation-engine: Alert storm                             │
│                                                                 │
│  LEARNER TASKS:                                                 │
│  1. Assume Incident Commander role                             │
│  2. Delegate to Operations/Comms/Scribe                        │
│  3. Use RCA agent for hypothesis generation                    │
│  4. Query knowledge base for similar incidents                 │
│  5. Execute runbooks, communicate status                       │
│  6. Resolve root cause, verify recovery                        │
│  7. Generate post-incident report                              │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Capstone Evaluation Rubric

| Criteria | Excellent (4) | Good (3) | Needs Work (2) | Missing (1) |
|----------|---------------|----------|----------------|-------------|
| **ICS Role Adoption** | Clear roles, smooth handoffs | Roles assigned, minor confusion | Roles unclear, overlaps | No role structure |
| **RCA Agent Usage** | Effective queries, validated hypotheses | Used agent, some validation | Ran agent, ignored output | Didn't use agent |
| **Knowledge Base** | Queried history, applied lessons | Queried history | Aware of KB, didn't use | Unaware of KB |
| **Communication** | Structured updates, stakeholder aware | Regular updates | Sporadic updates | No comms |
| **Resolution Time** | < 45 min | < 60 min | < 90 min | > 90 min or unresolved |
| **Post-Incident Report** | Complete, actionable, tracked | Good coverage | Partial | Missing |

---

## 🛠️ Troubleshooting Quick Reference

| Symptom | Likely Cause | Fix |
|---------|--------------|-----|
| RCA agent returns "no evidence" | MCP not reachable | Check MCP service, network policies, auth |
| Knowledge base search empty | No incidents ingested | Run ingestion script with sample data |
| Timeline missing events | Loki/LogQL query wrong | Check log labels, time range |
| Escalation not firing | Webhook URL wrong | Verify Slack/PagerDuty webhook in config |
| Shadow duel times out | Scenario not injecting | Check chaos mesh CRD, namespace |
| Vector DB OOM | Too many embeddings | Limit batch size, use persistent storage |

---

## 📦 Required Secrets (GitHub Actions)

| Secret | Description | Required For |
|--------|-------------|--------------|
| `AWS_ACCESS_KEY_ID` | AWS credentials for EKS | All workflows |
| `AWS_SECRET_ACCESS_KEY` | AWS credentials for EKS | All workflows |
| `EKS_CLUSTER_NAME` | Target EKS cluster | Deploy workflows |
| `MCP_URL` | MCP server endpoint | RCA agent, workflows |
| `PROMETHEUS_URL` | Prometheus endpoint | RCA agent, validation |
| `LOKI_URL` | Loki endpoint | RCA agent |
| `TEMPO_URL` | Tempo endpoint | RCA agent |
| `SLACK_WEBHOOK_URL` | Slack notifications | Incident comms, alerts |
| `PAGERDUTY_KEY` | PagerDuty integration | Escalation |
| `ANTHROPIC_API_KEY` | Claude API for RCA agent | RCA agent (if using API) |

---

## 🎓 Teaching Tips

### For Learners New to AI-Assisted RCA

1. **Start with the "why"** — Show a real incident where human investigation took 2 hours vs AI-assisted 15 min
2. **Demystify the agent** — Walk through the code: it's just structured PromQL/LogQL + LLM prompting
3. **Emphasize human-in-the-loop** — AI proposes, human decides; never auto-execute remediation
4. **Practice Shadow Duel multiple times** — First run is chaotic; second run shows improvement

### Common Learner Misconceptions

| Misconception | Reality |
|---------------|---------|
| "AI will replace incident response" | AI augments; human judgment essential for context, comms, decisions |
| "More data = better RCA" | Relevant data > volume; agent filters noise via correlation |
| "Runbooks are obsolete with AI" | Runbooks codify proven procedures; AI helps select right one |
| "Shadow Duel is a competition" | It's a collaboration exercise; find the best combined workflow |

---

## 📚 Additional Resources

- [Incident Response Runbook Template](https://github.com/google/sre-workbook/blob/main/chapters/incident-response.md)
- [Netflix Incident Management](https://netflixtechblog.com/incident-management-at-netflix-velocity-2019-7b8e8c8c8c8c)
- [PagerDuty Incident Response Docs](https://response.pagerduty.com/)
- [ChromaDB Documentation](https://docs.trychroma.com/)
- [Sentence Transformers Models](https://www.sbert.net/docs/pretrained_models.html)

---

*Last updated for AWS EKS-only deployment. No GCP/Azure references.*