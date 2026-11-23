# Week 4 Learner Lab Guide: Agent RCA & Incident Command

> **Audience:** AI SRE Practitioner Program Participants  
> **Format:** Hands-on labs with instructor guidance  
> **Prerequisites:** Weeks 1-3 completed (EKS cluster, telemetry stack, SLO/budget stack)  
> **Environment:** AWS EKS only

---

## 🎯 Lab Overview

| Lab | Title | Duration | Difficulty |
|-----|-------|----------|------------|
| 4.1 | Deploy RCA Agent | 45 min | ⭐⭐ |
| 4.2 | Build Knowledge Base | 60 min | ⭐⭐⭐ |
| 4.3 | Incident Command System | 45 min | ⭐⭐ |
| 4.4 | Shadow Duel: Human vs AI | 90 min | ⭐⭐⭐⭐ |
| 4.5 | Post-Incident Review Automation | 45 min | ⭐⭐ |
| 4.6 | Capstone: Full Incident Response | 120 min | ⭐⭐⭐⭐⭐ |

---

## 🔧 Lab 4.1: Deploy RCA Agent

### Objective
Deploy the AI RCA agent to your namespace with MCP integration for telemetry access.

### Prerequisites
- EKS cluster access (`kubectl` configured)
- MCP server running (from Week 2)
- GitHub CLI (`gh`) authenticated

### Steps

#### 1. Review the RCA Agent Code

```bash
cd lab-4-rca-command/rca-agent

# Main agent orchestration
cat agent.py | head -100

# Evidence collector (queries MCP for metrics/logs/traces)
cat evidence_collector.py | head -80

# Hypothesis engine (generates root cause hypotheses)
cat hypothesis_engine.py | head -80
```

#### 2. Configure Deployment Values

```bash
# Copy and customize values for your namespace
cp values.yaml.template values.yaml.$(whoami)

# Edit key settings:
# - namespace: your namespace (e.g., development-ram)
# - mcp.url: http://mcp-server.ai-sre-telemetry.svc.cluster.local:8082
# - agent.model: claude-3-5-sonnet (or your preferred model)
# - rbac.create: true
```

#### 3. Deploy via GitHub Actions (Manual Trigger)

```bash
# Trigger the deployment workflow
gh workflow run rca-agent-deploy.yml \
  -f environment=development \
  -f namespace=development-$(whoami) \
  -f mcp-url=http://mcp-server.ai-sre-telemetry.svc.cluster.local:8082
```

#### 4. Verify Deployment

```bash
# Check pod status
kubectl get pods -n development-$(whoami) -l app=rca-agent

# Check logs
kubectl logs -n development-$(whoami) -l app=rca-agent --tail=50

# Test agent health endpoint
kubectl port-forward -n development-$(whoami) svc/rca-agent 8080:8080 &
curl http://localhost:8080/health
```

#### 5. Test RCA Agent Query

```bash
# Send a test investigation request
curl -X POST http://localhost:8080/investigate \
  -H "Content-Type: application/json" \
  -d '{
    "incident_id": "TEST-001",
    "alert": "High error rate on java-service",
    "service": "java-service",
    "severity": "SEV-2"
  }' | jq .
```

### Expected Outcome
- RCA agent pod running and healthy
- Agent can query MCP for telemetry
- Test investigation returns structured hypotheses

### Troubleshooting

| Issue | Fix |
|-------|-----|
| Pod stuck in Pending | Check PVC for ChromaDB; verify resource quotas |
| MCP connection refused | Verify MCP service name and port; check network policies |
| RBAC permission denied | Ensure ServiceAccount bound to required ClusterRoles |
| Model API errors | Check ANTHROPIC_API_KEY secret in namespace |

---

## 🔧 Lab 4.2: Build Knowledge Base

### Objective
Create a vector database of historical incidents, runbooks, and architecture decisions for AI-assisted RCA.

### Prerequisites
- RCA agent deployed (Lab 4.1)
- ChromaDB or pgvector available
- Sample incident data (provided in `sample-incidents/`)

### Steps

#### 1. Review Knowledge Base Components

```bash
cd lab-4-rca-command/knowledge-base

# Vector store with embeddings
cat vector_store.py | head -100

# Incident ingestion pipeline
cat incident_ingest.py | head -100

# Runbook parser
cat runbook_parser.py | head -80
```

#### 2. Deploy ChromaDB (if not already running)

```bash
# Deploy via Helm
helm repo add chroma https://chromadb.github.io/charts
helm install chroma chroma/chroma \
  --namespace development-$(whoami) \
  --set persistence.enabled=true \
  --set persistence.size=5Gi
```

#### 3. Ingest Sample Incidents

```bash
# View sample incidents
ls sample-incidents/
cat sample-incidents/INC-2024-001.md

# Run ingestion
cd lab-4-rca-command/scripts
./ingest_incidents.py \
  --source ../sample-incidents \
  --vector-db chroma \
  --namespace development-$(whoami) \
  --embedding-model all-MiniLM-L6-v2
```

#### 4. Ingest Runbooks

```bash
# View sample runbooks
ls sample-runbooks/
cat sample-runbooks/java-service-high-latency.md

# Parse and index runbooks
./ingest_incidents.py \
  --source ../sample-runbooks \
  --vector-db chroma \
  --namespace development-$(whoami) \
  --type runbook
```

#### 5. Ingest Architecture Decision Records

```bash
# View sample ADRs
ls sample-adrs/
cat sample-adrs/ADR-001-connection-pooling.md

# Index ADRs
./ingest_incidents.py \
  --source ../sample-adrs \
  --vector-db chroma \
  --namespace development-$(whoami) \
  --type adr
```

#### 6. Query the Knowledge Base

```bash
# Test similarity search
python -c "
from knowledge_base.vector_store import VectorStore
vs = VectorStore('chroma', namespace='development-$(whoami)')

# Search for similar incidents
results = vs.search('java-service latency spike after deployment', k=5)
print('=== SIMILAR INCIDENTS ===')
for r in results:
    print(f'Score: {r.score:.3f} | {r.metadata[\"incident_id\"]} | {r.text[:150]}')

# Search for relevant runbooks
results = vs.search('connection pool exhaustion timeout', k=3)
print('\n=== RELEVANT RUNBOOKS ===')
for r in results:
    print(f'Score: {r.score:.3f} | {r.metadata[\"title\"]} | {r.text[:150]}')
"
```

### Expected Outcome
- ChromaDB running with incident, runbook, and ADR collections
- Similarity search returns relevant historical context
- RCA agent can query knowledge base during investigations

### Create Your Own Incident Entry

```bash
# Create a personal incident entry
cat > my-incident.md << 'EOF'
---
incident_id: INC-2024-$(date +%s)
service: python-service
severity: SEV-3
date: $(date -I)
root_cause: Memory leak in request handler due to unclosed DB connections
tags: [memory-leak, database, python]
---
## Symptoms
- Memory usage growing 10%/hour
- OOM kills after 6 hours
- Increased GC pause times

## Timeline
- $(date -d '-2 hours' -Iseconds): Deploy v1.4.2
- $(date -d '-1 hour' -Iseconds): Memory alert fires
- $(date -Iseconds): Root cause identified via heap dump
- $(date -d '+30 minutes' -Iseconds): Fix deployed (v1.4.3)

## Resolution
Added connection.close() in finally block; upgraded DB pool library

## Lessons Learned
- Always use context managers for DB connections
- Add memory profiling to CI pipeline
- Set memory limits on all containers
EOF

# Ingest your incident
./ingest_incidents.py \
  --source ./my-incident.md \
  --vector-db chroma \
  --namespace development-$(whoami)
```

---

## 🔧 Lab 4.3: Incident Command System

### Objective
Configure and practice the software-adapted Incident Command System (ICS) for structured incident response.

### Prerequisites
- Knowledge base deployed (Lab 4.2)
- Slack webhook configured for notifications

### Steps

#### 1. Review ICS Components

```bash
cd lab-4-rca-command/incident-command

# Role definitions
cat ics_roles.py

# Timeline reconstruction
cat incident_timeline.py

# Escalation policies
cat escalation_policy.py

# Communication channels
cat communication_channels.py
```

#### 2. Configure Your Team's Escalation Policy

```bash
# Create escalation config for your team
cat > my-escalation.yaml << 'EOF'
team: "platform-team-$(whoami)"
timezone: "UTC"

escalation:
  sev1:
    - delay: 0m
      role: incident_commander
      notify: ["oncall-primary"]
      action: "page"
    - delay: 5m
      role: operations_lead
      notify: ["service-owner"]
      action: "page"
    - delay: 15m
      notify: ["team-lead", "manager"]
      action: "page"
    - delay: 30m
      notify: ["director"]
      action: "page"
  
  sev2:
    - delay: 0m
      role: incident_commander
      notify: ["oncall-primary"]
      action: "slack"
    - delay: 15m
      role: operations_lead
      notify: ["service-owner"]
      action: "slack"
    - delay: 30m
      notify: ["team-lead"]
      action: "slack"
  
  sev3:
    - delay: 0m
      role: incident_commander
      notify: ["oncall-primary"]
      action: "slack"
    - delay: 60m
      notify: ["service-owner"]
      action: "slack"

communication:
  slack_channel: "#incidents-$(whoami)"
  status_page: "https://status.example.com"
  update_cadence:
    sev1: 10m
    sev2: 15m
    sev3: 30m
EOF
```

#### 3. Test Timeline Reconstruction

```bash
# Deploy test incident scenario
gh workflow run incident-simulation.yml \
  -f scenario=single-service-degradation \
  -f severity=SEV-2 \
  -f namespace=development-$(whoami)

# Wait for incident to develop (2-3 minutes)
sleep 180

# Reconstruct timeline
python -c "
from incident_command.incident_timeline import TimelineReconstructor
tr = TimelineReconstructor(
    namespace='development-$(whoami)',
    loki_url='http://loki:3100',
    prometheus_url='http://prometheus:9090'
)
timeline = tr.reconstruct('INC-TEST-001')
for event in timeline:
    print(f'{event.timestamp} | {event.source:15} | {event.description}')
"
```

#### 4. Practice ICS Role Assignment

```bash
# Simulate incident with role assignment
gh workflow run incident-simulation.yml \
  -f scenario=cascade-failure \
  -f severity=SEV-1 \
  -f namespace=development-$(whoami) \
  -f assign-roles=true

# In Slack, practice:
# 1. /incident start SEV-1 "Cascade failure in java-service" --assign-ic @you
# 2. /incident assign ops @teammate1
# 3. /incident assign comms @teammate2
# 4. /incident assign scribe @teammate3 (or use bot)
# 5. /incident update "Investigating java-service CPU spike"
```

### Expected Outcome
- Escalation policy configured for your team
- Timeline reconstruction working from Loki/Prometheus
- ICS roles understood and practiced

---

## 🔧 Lab 4.4: Shadow Duel — Human vs AI Investigation ⭐

### Objective
Run parallel investigations of the same incident — one by human, one by AI — and compare results.

### Prerequisites
- All previous labs completed
- RCA agent deployed and healthy
- Knowledge base populated with incidents
- Incident simulation framework ready

### Exercise Setup (Instructor-Led)

The instructor will:
1. Deploy a **hidden incident scenario** to a shared namespace
2. Provide both investigators with the **same initial alert**
3. Start a **45-minute timer**

### Your Role: Human Investigator

```bash
# 1. Join the incident channel
# Slack: #shadow-duel-<session-id>

# 2. Receive initial alert
# Alert: "java-service error rate > 5% (SEV-2)"

# 3. Begin investigation - use your standard tools:
# - Grafana dashboards
# - kubectl logs / describe
# - Runbook library
# - Team knowledge

# 4. Document your findings in the investigation form:
cat > my-investigation.md << 'EOF'
# Investigation: INC-SHADOW-<ID>
## Investigator: <your-name>
## Start Time: <timestamp>

### Initial Hypothesis
<what you think is wrong>

### Evidence Gathered
| Time | Source | Query/Command | Finding |
|------|--------|---------------|---------|
|      |        |               |         |

### Root Cause Conclusion
<your final root cause>

### Confidence: <1-10>
### Time to Root Cause: <minutes>
EOF
```

### AI Investigator (Runs in Parallel)

The instructor runs the AI agent:

```bash
# AI investigation (instructor runs this)
./lab-4-rca-command/scripts/run_shadow_duel.sh \
  --incident-id INC-SHADOW-<ID> \
  --mode ai-only \
  --output ai-findings.json
```

### Comparison & Debrief (20 min)

After both investigations complete:

```bash
# Generate comparison report
./lab-4-rca-command/scripts/run_shadow_duel.sh \
  --incident-id INC-SHADOW-<ID> \
  --mode compare \
  --human-findings my-investigation.md \
  --ai-findings ai-findings.json \
  --output comparison-report.md

# View comparison
cat comparison-report.md
```

### Comparison Report Structure

```markdown
# Shadow Duel Comparison: INC-SHADOW-<ID>

## Summary
| Metric | Human | AI | Delta |
|--------|-------|-----|-------|
| Time to First Hypothesis | X min | Y min | ±Z min |
| Time to Root Cause | X min | Y min | ±Z min |
| Root Cause Accuracy | ✓/✗ | ✓/✗ | |
| Evidence Items Cited | N | M | |
| False Leads Pursued | N | M | |

## Human Strengths
- Contextual reasoning about recent changes
- Stakeholder communication
- Intuition from past experience

## AI Strengths
- Exhaustive evidence gathering across all telemetry
- Historical pattern matching from knowledge base
- Multi-service correlation via topology graph

## Missed by Human, Found by AI
- [ ] Correlated trace span 3 hops upstream
- [ ] Similar incident from 6 months ago
- [ ] Configuration drift detected

## Missed by AI, Found by Human
- [ ] Recent unreleased config change
- [ ] Business context (marketing campaign)
- [ ] Tribal knowledge about legacy code

## Combined Workflow Recommendation
1. AI gathers evidence + generates hypotheses (0-5 min)
2. Human reviews top 3 hypotheses + adds context (5-10 min)
3. AI validates/refutes with targeted queries (10-15 min)
4. Human makes decision + executes runbook (15+ min)
```

### Reflection Questions

1. What would you change about your investigation process after seeing the AI's approach?
2. What telemetry queries did the AI run that you wouldn't have thought of?
3. Where did the AI waste time on irrelevant evidence?
4. How would you integrate this into your real on-call workflow?

---

## 🔧 Lab 4.5: Post-Incident Review Automation

### Objective
Automate generation of post-incident reports with timeline, root cause, action items, and knowledge base updates.

### Prerequisites
- Completed incident (from Lab 4.4 or previous real incident)
- Access to Loki, Prometheus, GitHub, Slack APIs

### Steps

#### 1. Review Report Generator

```bash
cd lab-4-rca-command/scripts
cat export_incident_report.py | head -150
```

#### 2. Generate Report for Shadow Duel Incident

```bash
./export_incident_report.py \
  --incident-id INC-SHADOW-<ID> \
  --namespace development-$(whoami) \
  --format markdown \
  --include-timeline \
  --include-action-items \
  --include-knowledge-base-update \
  --output ./post-incident-INC-SHADOW-<ID>.md
```

#### 3. Review Generated Report

```bash
cat ./post-incident-INC-SHADOW-<ID>.md
```

#### 4. Generate HTML Version for Sharing

```bash
./export_incident_report.py \
  --incident-id INC-SHADOW-<ID> \
  --namespace development-$(whoami) \
  --format html \
  --output ./post-incident-INC-SHADOW-<ID>.html
```

#### 5. Create GitHub Issue for Action Items

```bash
# Extract action items and create issues
python -c "
import yaml
with open('./post-incident-INC-SHADOW-<ID>.md') as f:
    content = f.read()

# Parse action items section (simplified)
import re
items = re.findall(r'- \[ \] (.+)', content)
for i, item in enumerate(items):
    print(f'Action Item {i+1}: {item}')
"
```

### Expected Outcome
- Comprehensive post-incident report in Markdown/HTML
- Action items extracted and tracked
- Lessons learned fed back to knowledge base

---

## 🔧 Lab 4.6: Capstone — Full Incident Response

### Objective
Execute a complete incident response for a multi-service cascade scenario using all Week 4 tools.

### Scenario: "Black Friday Cascade"

```
Timeline:
T+0min:  java-service CPU spike (bad query in v3.1.0)
T+2min:  python-service thread pool exhaustion (downstream timeouts)
T+4min:  mcp-server query queue backup
T+6min:  correlation-engine alert storm
T+8min:  SLO burn rate alerts fire (Week 3)
```

### Your Tasks

#### 1. Assume Incident Commander Role (0-5 min)

```bash
# Start incident
gh workflow run incident-simulation.yml \
  -f scenario=black-friday-cascade \
  -f severity=SEV-1 \
  -f namespace=development-$(whoami)

# Announce in Slack
# /incident start SEV-1 "Black Friday Cascade - multi-service degradation" --assign-ic @you
```

#### 2. Delegate Roles (5-10 min)

```bash
# Assign roles via Slack bot or manually
# /incident assign ops @teammate1
# /incident assign comms @teammate2
# /incident assign scribe @teammate3 (or use auto-scribe)
```

#### 3. Use RCA Agent for Hypothesis Generation (10-20 min)

```bash
# Query RCA agent
curl -X POST http://rca-agent:8080/investigate \
  -H "Content-Type: application/json" \
  -d '{
    "incident_id": "INC-BF-001",
    "alert": "Multi-service degradation: java-service, python-service, mcp-server",
    "services": ["java-service", "python-service", "mcp-server"],
    "severity": "SEV-1"
  }' | jq .

# Review hypotheses with team
# "AI suggests: 1) java-service bad query (85%), 2) python-service config (10%), 3) infra (5%)"
```

#### 4. Query Knowledge Base for Similar Incidents (15-25 min)

```bash
python -c "
from knowledge_base.vector_store import VectorStore
vs = VectorStore('chroma', namespace='development-$(whoami)')
results = vs.search('multi-service cascade cpu spike downstream timeout', k=3)
for r in results:
    print(f'{r.score:.3f} | {r.metadata[\"incident_id\"]} | {r.text[:200]}')
"
```

#### 5. Execute Mitigation (20-40 min)

Based on RCA findings:
- **If java-service bad query**: Rollback java-service to v3.0.9
- **If config issue**: Apply connection pool fix
- **If infra**: Scale nodes, check network

```bash
# Example: Rollback java-service
kubectl rollout undo deployment/java-service -n development-$(whoami)
kubectl rollout status deployment/java-service -n development-$(whoami)
```

#### 6. Verify Recovery (40-50 min)

```bash
# Check SLO compliance (Week 3 integration)
curl -X POST http://rca-agent:8080/verify-recovery \
  -H "Content-Type: application/json" \
  -d '{"incident_id": "INC-BF-001", "services": ["java-service", "python-service", "mcp-server"]}' | jq .

# Monitor dashboards
# - SLO Compliance Dashboard (Week 3)
# - Error Budget Burndown
# - Service health panels
```

#### 7. Close Incident & Generate Report (50-60 min)

```bash
# Close incident
# /incident close INC-BF-001 "Rolled back java-service v3.1.0 → v3.0.9; all services recovered"

# Generate final report
./export_incident_report.py \
  --incident-id INC-BF-001 \
  --namespace development-$(whoami) \
  --format markdown \
  --output ./capstone-INC-BF-001.md
```

### Capstone Success Criteria

| Criteria | Target |
|----------|--------|
| Incident acknowledged | < 2 min |
| ICS roles assigned | < 5 min |
| First RCA hypothesis | < 10 min |
| Root cause identified | < 25 min |
| Mitigation executed | < 40 min |
| Full recovery verified | < 50 min |
| Post-incident report | < 60 min |
| Action items created | All tracked |

---

## 📝 Lab Completion Checklist

- [ ] Lab 4.1: RCA Agent deployed and responding to queries
- [ ] Lab 4.2: Knowledge base populated with incidents, runbooks, ADRs
- [ ] Lab 4.3: ICS escalation policy configured; timeline reconstruction working
- [ ] Lab 4.4: Shadow Duel completed; comparison report generated
- [ ] Lab 4.5: Post-incident report generated for Shadow Duel incident
- [ ] Lab 4.6: Capstone completed within 60 minutes; all success criteria met

---

## 🆘 Getting Help

| Resource | Access |
|----------|--------|
| Instructor Slack | #ai-sre-week4-help |
| RCA Agent Logs | `kubectl logs -n <ns> -l app=rca-agent` |
| MCP Health | `curl http://mcp-server:8082/health` |
| Knowledge Base Query | `python -c "from knowledge_base.vector_store import VectorStore; vs=VectorStore(...); print(vs.search('query', k=3))"` |
| Incident Timeline | `python -c "from incident_command.incident_timeline import TimelineReconstructor; tr=TimelineReconstructor(...); print(tr.reconstruct('INC-ID'))"` |

---

*Remember: The goal is not to replace human judgment with AI, but to augment human investigation with exhaustive evidence gathering and historical pattern matching. The best incident response combines both.*