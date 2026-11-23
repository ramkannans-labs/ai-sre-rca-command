# AI SRE Practitioner Program — Week 4: Agent RCA & Incident Command

> **Repository:** `ai-sre-rca-command`  
> **Week:** 4 of 7  
> **Focus:** Automated Root Cause Analysis using AI agents, Incident Command System (ICS) integration, and knowledge-base-driven investigations

---

## 🎯 Learning Objectives

By the end of this week, learners will be able to:

1. **Design and deploy an AI-powered RCA agent** that correlates telemetry, logs, and topology to propose root causes
2. **Implement Incident Command System (ICS) workflows** adapted for software incidents with role assignments and escalation paths
3. **Build a queryable knowledge base** of past incidents, runbooks, and architectural decisions for AI-assisted triage
4. **Conduct Shadow Duel exercises** where human and AI investigators work the same incident in parallel
5. **Measure and improve MTTD/MTTR** through structured post-incident reviews

---

## 🏗️ Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         INCIDENT COMMAND PLANE                          │
├─────────────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌────────────┐  │
│  │  Incident    │  │   RCA Agent  │  │  Knowledge   │  │  Runbook   │  │
│  │  Commander   │──│  (Claude)    │──│  Base        │──│  Executor  │  │
│  │  (Human)     │  │              │  │  (Vector DB) │  │            │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  └────────────┘  │
│         │                │                │                │            │
│         ▼                ▼                ▼                ▼            │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │                    MCP OBSERVABILITY LAYER                        │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐              │  │
│  │  │  Metrics    │  │  Logs       │  │  Traces     │              │  │
│  │  │  (Prometheus)    │  (Loki)     │  │  (Tempo)    │              │  │
│  │  └─────────────┘  └─────────────┘  └─────────────┘              │  │
│  └──────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      PRODUCTION WORKLOADS (EKS)                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌────────────┐  │
│  │ java-service │  │ python-svc   │  │ mcp-server   │  │  kafka/    │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │  redis     │  │
│                                                       └────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 📁 Repository Structure

```
ai-sre-rca-command/
├── README.md                          # This file
├── docs/
│   ├── trainer-guide.md               # Instructor notes, demo scripts, timing
│   ├── learner-lab-guide.md           # Step-by-step learner instructions
│   ├── architectural-flow.md          # Mermaid diagrams for all components
│   └── ics-reference.md               # Incident Command System cheat sheet
├── lab-4-rca-command/
│   ├── rca-agent/                     # AI RCA agent implementation
│   │   ├── agent.py                   # Main RCA agent orchestration
│   │   ├── evidence_collector.py      # Telemetry/log/trace gathering
│   │   ├── hypothesis_engine.py       # Root cause hypothesis generation
│   │   ├── confidence_scorer.py       # Evidence weighting & scoring
│   │   └── requirements.txt
│   ├── incident-command/              # ICS workflow engine
│   │   ├── ics_roles.py               # Role definitions (IC, Ops, Comms, Scribe)
│   │   ├── incident_timeline.py       # Timeline tracking & reconstruction
│   │   ├── escalation_policy.py       # Automated escalation rules
│   │   ├── communication_channels.py  # Slack/Teams/PagerDuty integration
│   │   └── requirements.txt
│   ├── knowledge-base/                # Incident knowledge store
│   │   ├── vector_store.py            # Embeddings + similarity search
│   │   ├── incident_ingest.py         # Past incident ingestion pipeline
│   │   ├── runbook_parser.py          # Runbook extraction & indexing
│   │   ├── architecture_docs.py       # Architecture decision records
│   │   └── requirements.txt
│   ├── simulation/                    # Incident simulation framework
│   │   ├── scenario_engine.py         # Multi-stage incident scenarios
│   │   ├── shadow_duel.py             # Human vs AI parallel investigation
│   │   ├── metrics_collector.py       # MTTD/MTTR measurement
│   │   └── requirements.txt
│   ├── prompts/                       # Claude Code prompts
│   │   ├── rca-investigation-prompt.md
│   │   ├── hypothesis-generation-prompt.md
│   │   ├── timeline-reconstruction-prompt.md
│   │   └── post-incident-review-prompt.md
│   └── scripts/
│       ├── setup_rca_stack.sh         # Deploy RCA agent + knowledge base
│       ├── run_shadow_duel.sh         # Execute Shadow Duel exercise
│       ├── ingest_incidents.py        # Load historical incidents
│       └── export_incident_report.py  # Generate post-incident report
├── .github/workflows/
│   ├── rca-agent-deploy.yml           # Deploy RCA agent (manual)
│   ├── incident-simulation.yml        # Run incident scenarios (manual)
│   ├── shadow-duel.yml                # Shadow Duel execution (manual)
│   └── knowledge-base-sync.yml        # Sync knowledge base (manual)
```

---

## 🚀 Quick Start

### Prerequisites

- AWS CLI configured with EKS permissions
- kubectl configured for target cluster
- Python 3.11+
- GitHub CLI (`gh`) for workflow triggers
- Access to LLM API (Anthropic Claude, OpenAI, or local model)

### 1. Clone & Configure

```bash
git clone https://github.com/ramkannans-labs/ai-sre-rca-command.git
cd ai-sre-rca-command
```

### 2. Deploy RCA Stack

```bash
# Manual trigger via GitHub Actions
gh workflow run rca-agent-deploy.yml -f environment=staging

# Or run locally
./lab-4-rca-command/scripts/setup_rca_stack.sh staging
```

### 3. Ingest Historical Incidents

```bash
./lab-4-rca-command/scripts/ingest_incidents.py \
  --source ./sample-incidents \
  --vector-db chroma
```

### 4. Run Shadow Duel Exercise

```bash
# Trigger incident scenario
gh workflow run incident-simulation.yml \
  -f scenario=cascade-failure \
  -f severity=SEV-2

# Run Shadow Duel (human + AI in parallel)
./lab-4-rca-command/scripts/run_shadow_duel.sh \
  --incident-id INC-2024-001 \
  --mode parallel
```

---

## 🧪 Lab Exercises

| Lab | Title | Duration | Pattern |
|-----|-------|----------|---------|
| 4.1 | **Deploy RCA Agent** | 45 min | Learn → Do |
| 4.2 | **Build Knowledge Base** | 60 min | Learn → Do |
| 4.3 | **Incident Command System** | 45 min | Learn → Do |
| 4.4 | **Shadow Duel: Human vs AI** | 90 min | Do → Relearn |
| 4.5 | **Post-Incident Review Automation** | 45 min | Learn → Do |
| 4.6 | **Capstone: Full Incident Response** | 120 min | Do → Relearn |

### Lab 4.4: Shadow Duel (Signature Exercise)

> **Concept:** Run the same incident scenario twice in parallel — once investigated by a human SRE, once by the AI RCA agent. Compare findings, speed, and completeness.

```
┌─────────────────────┐     ┌─────────────────────┐
│   HUMAN INVESTIGATOR │     │    AI RCA AGENT     │
│   (Lead SRE)        │     │    (Claude Code)    │
├─────────────────────┤     ├─────────────────────┤
│ • Dashboard access  │     │ • MCP tool access   │
│ • Runbook library   │     │ • Knowledge base    │
│ • Team comms        │     │ • Hypothesis engine │
│ • Intuition         │     │ • Evidence scoring  │
└─────────┬───────────┘     └─────────┬───────────┘
          │                           │
          ▼                           ▼
    ┌───────────────────────────────────────┐
    │         SAME INCIDENT SCENARIO        │
    │    (injected via chaos mesh)          │
    └───────────────────────────────────────┘
          │                           │
          ▼                           ▼
    ┌─────────────────────┐     ┌─────────────────────┐
    │  HUMAN FINDINGS     │     │   AI FINDINGS       │
    │  - Root cause       │     │  - Root cause       │
    │  - Timeline         │     │  - Timeline         │
    │  - Confidence       │     │  - Confidence       │
    │  - Actions taken    │     │  - Evidence trail   │
    └─────────┬───────────┘     └─────────┬───────────┘
              │                           │
              └───────────┬───────────────┘
                          ▼
              ┌───────────────────────┐
              │   COMPARISON & DEBRIEF │
              │  - What did AI miss?   │
              │  - What did human miss?│
              │  - Combined approach?  │
              └───────────────────────┘
```

---

## 🔧 Key Components

### RCA Agent (`lab-4-rca-command/rca-agent/`)

The AI agent that performs automated root cause analysis:

- **Evidence Collector** — Queries Prometheus, Loki, Tempo via MCP for relevant telemetry
- **Hypothesis Engine** — Generates ranked root cause hypotheses using service topology
- **Confidence Scorer** — Weights evidence (metrics, logs, traces, topology, history) to score hypotheses
- **Output** — Structured RCA report with timeline, root cause, contributing factors, recommended actions

### Incident Command (`lab-4-rca-command/incident-command/`)

Software-adapted Incident Command System:

- **Roles**: Incident Commander, Operations Lead, Communications Lead, Scribe, Subject Matter Experts
- **Timeline**: Automated incident timeline reconstruction from logs, alerts, deployments, communications
- **Escalation**: Time-based and severity-based escalation with on-call rotation integration
- **Communication**: Structured update cadence (every 15 min for SEV-1, 30 min for SEV-2)

### Knowledge Base (`lab-4-rca-command/knowledge-base/`)

Vector-based incident memory:

- **Incident Embeddings** — Past incidents stored as vectors for similarity search
- **Runbook Index** — Parsed runbooks with step-by-step actions linked to symptoms
- **Architecture Decisions** — ADRs indexed for context during investigations
- **Query Interface** — Natural language queries: *"Show me incidents where java-service had latency spikes after deployments"*

### Simulation Framework (`lab-4-rca-command/simulation/`)

- **Scenario Engine** — Multi-stage failure injection with configurable blast radius
- **Shadow Duel** — Parallel human/AI investigation with automated comparison
- **Metrics Collection** — MTTD, MTTR, hypothesis accuracy, action effectiveness tracking

---

## 📊 Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| **MTTD (Mean Time to Detect)** | < 5 min | Alert fire → Incident acknowledged |
| **MTTI (Mean Time to Investigate)** | < 15 min | Acknowledged → Root cause hypothesized |
| **MTTR (Mean Time to Resolve)** | < 60 min | Acknowledged → Resolution confirmed |
| **AI Hypothesis Accuracy** | > 80% | Top-1 hypothesis matches human RC |
| **AI Evidence Coverage** | > 90% | AI cites all evidence human used |
| **Shadow Duel Parity** | ±20% | Human vs AI time-to-hypothesis |

---

## 🎓 Trainer Notes

### Demo Scripts

See [`docs/trainer-guide.md`](docs/trainer-guide.md) for:
- Live demo flow for each lab
- Failure injection commands for realistic incidents
- Expected learner questions and answers
- Troubleshooting common issues

### Prerequisites for Training Session

1. EKS cluster running (from Week 1)
2. Telemetry stack deployed (from Week 2)
3. SLO/Budget stack deployed (from Week 3)
4. Sample incidents pre-loaded in knowledge base
5. Slack/PagerDuty webhooks configured for comms testing

---

## 🔗 Integration Points

| Week | Component | Integration |
|------|-----------|-------------|
| 1 | EKS Cluster | Target environment for incidents |
| 2 | MCP Server | Telemetry query interface for RCA agent |
| 2 | Knowledge Graph | Service topology for blast radius & hypothesis generation |
| 2 | Correlation Engine | Pre-correlated alerts as RCA starting points |
| 3 | SLO/Budget Metrics | Error budget consumption as incident severity indicator |
| 3 | Release Gates | Recent deployments as potential root causes |

---

## 📚 References

- [Incident Command System (ICS) - FEMA](https://training.fema.gov/ics/)
- [Google SRE Workbook - Incident Response](https://sre.google/workbook/incident-response/)
- [Howie et al. - "Incident Response at Google"](https://sre.google/workbook/incident-response/)
- [Netflix Chaos Engineering](https://netflixtechblog.com/chaos-engineering/)
- [OpenTelemetry Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/)

---

## 🤝 Contributing

This is a training repository. Issues and PRs welcome for:
- Additional incident scenarios
- Improved RCA agent prompts
- New knowledge base sources
- Enhanced Shadow Duel metrics

---

## 📄 License

MIT License — See LICENSE file for details.

---

*Part of the AI SRE Practitioner Program — Week 4 of 7*