# Week 4 Architectural Flow: Agent RCA & Incident Command

> **Repository:** `ai-sre-rca-command`  
> **Focus:** Data flows, component interactions, and sequence diagrams for RCA agent and ICS

---

## 🏗️ System Architecture Overview

```mermaid
graph TB
    subgraph "INCIDENT COMMAND PLANE"
        IC[Incident Commander<br/>Human]
        RCA[RCA Agent<br/>Claude Code]
        KB[Knowledge Base<br/>ChromaDB]
        ICS[ICS Engine<br/>Timeline/Escalation/Comms]
        RB[Runbook Executor]
    end

    subgraph "MCP OBSERVABILITY LAYER"
        MCP[MCP Server<br/>Unified Telemetry API]
        PM[Prometheus<br/>Metrics]
        LG[Loki<br/>Logs]
        TP[Tempo<br/>Traces]
        KG[Knowledge Graph<br/>Service Topology]
        CE[Correlation Engine<br/>Alert Groups]
    end

    subgraph "PRODUCTION WORKLOADS (EKS)"
        JS[java-service]
        PS[python-service]
        MS[mcp-server]
        KG_SVC[knowledge-graph]
        CE_SVC[correlation-engine]
        KF[Kafka]
        RD[Redis]
        PG[PostgreSQL]
    end

    subgraph "EXTERNAL INTEGRATIONS"
        SL[Slack/Teams]
        PD[PagerDuty]
        GH[GitHub Issues]
        SP[Status Page]
    end

    IC -->|Commands/Decisions| ICS
    IC -->|Reviews| RCA
    RCA -->|Queries| MCP
    RCA -->|Searches| KB
    RCA -->|Generates| Hypotheses
    KB -->|Ingests| Incidents
    KB -->|Indexes| Runbooks
    KB -->|Indexes| ADRs
    ICS -->|Timeline| LG
    ICS -->|Metrics| PM
    ICS -->|Escalates| SL
    ICS -->|Escalates| PD
    ICS -->|Creates Issues| GH
    ICS -->|Updates| SP
    RB -->|Executes| Runbooks
    MCP -->|Queries| PM
    MCP -->|Queries| LG
    MCP -->|Queries| TP
    MCP -->|Queries| KG
    MCP -->|Queries| CE
    PM -->|Scrapes| JS
    PM -->|Scrapes| PS
    PM -->|Scrapes| MS
    PM -->|Scrapes| KG_SVC
    PM -->|Scrapes| CE_SVC
    LG -->|Collects| JS
    LG -->|Collects| PS
    LG -->|Collects| MS
    TP -->|Traces| JS
    TP -->|Traces| PS
    KG -->|Builds from| JS
    KG -->|Builds from| PS
    CE -->|Correlates| Alerts

    style IC fill:#e1f5fe
    style RCA fill:#f3e5f5
    style KB fill:#fff3e0
    style ICS fill:#e8f5e9
    style MCP fill:#fce4ec
```

---

## 🔄 RCA Agent Investigation Flow

```mermaid
sequenceDiagram
    participant Alert as Alert Manager
    participant IC as Incident Commander
    participant RCA as RCA Agent
    participant MCP as MCP Server
    participant PM as Prometheus
    participant LG as Loki
    participant TP as Tempo
    participant KG as Knowledge Graph
    participant KB as Knowledge Base
    participant CE as Correlation Engine

    Alert->>IC: Alert: java-service error rate > 5%
    IC->>RCA: Start investigation(incident_id, alert, services)
    RCA->>MCP: Get correlated alerts(incident_id)
    MCP->>CE: Query correlated alert groups
    CE-->>MCP: Alert group with related alerts
    MCP-->>RCA: Correlated alert context
    
    par Evidence Collection
        RCA->>MCP: Query metrics(service, time_range)
        MCP->>PM: PromQL: error_rate, latency, cpu, memory
        PM-->>MCP: Time series data
        MCP-->>RCA: Metrics evidence
        
        RCA->>MCP: Query logs(service, time_range, severity)
        MCP->>LG: LogQL: {service="java-service"} |= "error"
        LG-->>MCP: Log entries
        MCP-->>RCA: Log evidence
        
        RCA->>MCP: Query traces(service, time_range)
        MCP->>TP: TraceQL: {service="java-service"} duration>1s
        TP-->>MCP: Trace spans
        MCP-->>RCA: Trace evidence
        
        RCA->>MCP: Get topology(service)
        MCP->>KG: Get upstream/downstream services
        KG-->>MCP: Service dependency graph
        MCP-->>RCA: Topology evidence
    end
    
    RCA->>KB: Search similar incidents(symptoms)
    KB-->>RCA: Historical incidents with root causes
    
    RCA->>RCA: Generate hypotheses(evidence, topology, history)
    Note over RCA: 1. Score each hypothesis<br/>2. Weight evidence types<br/>3. Rank by confidence
    
    RCA->>MCP: Validate top hypotheses(targeted queries)
    MCP->>PM: Specific PromQL for hypothesis
    PM-->>MCP: Validation data
    MCP-->>RCA: Hypothesis validation results
    
    RCA-->>IC: Structured RCA Report
    Note over IC,RCA: {hypotheses, evidence, timeline, recommended_actions, confidence}
    
    IC->>IC: Review + Decide
    IC->>ICS: Execute runbook / Delegate
```

---

## 📊 Knowledge Base Ingestion & Query Flow

```mermaid
flowchart TD
    subgraph "INGESTION PIPELINE"
        SRC[Source Documents<br/>Incidents/Runbooks/ADRs]
        PARSE[Parser<br/>Markdown/JSON/YAML]
        EXTRACT[Metadata Extraction<br/>ID, Service, Severity, Tags]
        CHUNK[Text Chunking<br/>Semantic sections]
        EMBED[Embedding Generation<br/>sentence-transformers]
        STORE[Vector Store<br/>ChromaDB/pgvector]
    end
    
    subgraph "QUERY PIPELINE"
        QUERY[Natural Language Query]
        EMBED_Q[Query Embedding]
        SEARCH[Similarity Search<br/>cosine/ANN]
        RERANK[Re-ranking<br/>Cross-encoder]
        FILTER[Metadata Filter<br/>Service, Severity, Date]
        RESULTS[Ranked Results<br/>with citations]
    end
    
    SRC --> PARSE --> EXTRACT --> CHUNK --> EMBED --> STORE
    QUERY --> EMBED_Q --> SEARCH --> RERANK --> FILTER --> RESULTS
    STORE -.->|Index| SEARCH
```

---

## 🚨 Incident Command System Flow

```mermaid
stateDiagram-v2
    [*] --> DETECTED: Alert fires
    DETECTED --> ACKNOWLEDGED: IC acknowledges
    ACKNOWLEDGED --> INVESTIGATING: IC assigns roles
    INVESTIGATING --> MITIGATING: Root cause found
    MITIGATING --> RECOVERING: Fix deployed
    RECOVERING --> RESOLVED: Health verified
    RESOLVED --> POST_INCIDENT: Report generated
    POST_INCIDENT --> CLOSED: Action items tracked
    CLOSED --> [*]
    
    INVESTIGATING --> ESCALATED: SLA breach / severity increase
    ESCALATED --> INVESTIGATING: Additional resources
    MITIGATING --> ROLLED_BACK: Fix fails
    ROLLED_BACK --> INVESTIGATING: Re-assess
```

### ICS Role Interaction Flow

```mermaid
sequenceDiagram
    participant Alert as Alert/Page
    participant IC as Incident Commander
    participant Ops as Operations Lead
    participant Comms as Communications Lead
    participant Scribe as Scribe (Auto)
    participant RCA as RCA Agent
    participant KB as Knowledge Base
    participant Stake as Stakeholders
    participant Slack as Slack Channel

    Alert->>IC: Page: SEV-1 java-service down
    IC->>Slack: /incident start SEV-1 "java-service down"
    IC->>Ops: Assign: Investigate java-service
    IC->>Comms: Assign: Stakeholder updates
    IC->>Scribe: Auto-assign: Timeline tracking
    
    par Parallel Investigation
        Ops->>RCA: Request hypotheses
        RCA->>KB: Search similar incidents
        KB-->>RCA: Historical matches
        RCA-->>Ops: Ranked hypotheses
        Ops->>MCP: Targeted queries for validation
        MCP-->>Ops: Evidence
        Ops->>IC: Root cause: Connection pool exhaustion
    and
        Scribe->>LG: Query logs for timeline
        Scribe->>PM: Query alerts for timeline
        Scribe->>GH: Query deployments for timeline
        Scribe->>Slack: Auto-record all messages
        Scribe->>Timeline: Reconstructed timeline
    and
        Comms->>Stake: Initial notification (5 min)
        Comms->>Slack: Status updates (every 15 min)
        Comms->>StatusPage: Update status page
    end
    
    IC->>Ops: Execute runbook: Increase pool size
    Ops->>K8s: Patch deployment
    K8s-->>Ops: Rollout complete
    Ops->>IC: Recovery verified
    IC->>Comms: Resolution notification
    IC->>Scribe: Finalize timeline
    IC->>PostIncident: Generate report
```

---

## 🥊 Shadow Duel Flow

```mermaid
flowchart TD
    subgraph "SETUP"
        DEPLOY[Deploy Hidden Scenario\nChaos Mesh]
        ASSIGN[Assign Investigators\nHuman + AI]
        BRIEF[Same Initial Brief\nAlert + Dashboard]
    end
    
    subgraph "INVESTIGATION (45 min)"
        H_START[Human Starts\nGrafana/kubectl/Runbooks]
        A_START[AI Starts\nMCP/KB/Hypothesis Engine]
        
        H_EVIDENCE[Human: Gather Evidence\nQueries, Logs, Traces]
        H_HYPOTHESIS[Human: Form Hypothesis\nIntuition + Experience]
        H_VALIDATE[Human: Validate\nTargeted queries]
        H_CONCLUDE[Human: Conclusion\nRoot cause + Confidence]
        
        A_EVIDENCE[AI: Exhaustive Evidence\nAll telemetry + Topology]
        A_HYPOTHESIS[AI: Generate Hypotheses\nPattern matching + KB]
        A_VALIDATE[AI: Validate Top-N\nTargeted MCP queries]
        A_CONCLUDE[AI: Conclusion\nRanked hypotheses + Evidence]
    end
    
    subgraph "COMPARISON"
        SUBMIT[Submit Findings\nStructured forms]
        COMPARE[Side-by-side Comparison\nMetrics table]
        DEBRIEF[Facilitated Debrief\nWhat missed? What combined?]
        DOCUMENT[Document Combined Workflow\nBest of both]
    end
    
    DEPLOY --> ASSIGN --> BRIEF
    BRIEF --> H_START & A_START
    H_START --> H_EVIDENCE --> H_HYPOTHESIS --> H_VALIDATE --> H_CONCLUDE
    A_START --> A_EVIDENCE --> A_HYPOTHESIS --> A_VALIDATE --> A_CONCLUDE
    H_CONCLUDE & A_CONCLUDE --> SUBMIT --> COMPARE --> DEBRIEF --> DOCUMENT
```

### Shadow Duel Comparison Metrics

```mermaid
graph LR
    subgraph "TIME METRICS"
        T1[Time to First\nHypothesis]
        T2[Time to Root\nCause]
        T3[Total\nInvestigation Time]
    end
    
    subgraph "QUALITY METRICS"
        Q1[Root Cause\nAccuracy Top-1]
        Q2[Evidence\nCoverage %]
        Q3[False Leads\nCount]
    end
    
    subgraph "PROCESS METRICS"
        P1[Tools Used\nCount/Type]
        P2[Queries Run\nCount]
        P3[Collaboration\nEvents]
    end
    
    HUMAN[Human Investigator] --> T1 & T2 & T3 & Q1 & Q2 & Q3 & P1 & P2 & P3
    AI[AI RCA Agent] --> T1 & T2 & T3 & Q1 & Q2 & Q3 & P1 & P2 & P3
```

---

## 📈 Post-Incident Report Generation Flow

```mermaid
sequenceDiagram
    participant IC as Incident Commander
    participant Scribe as Scribe/Timeline
    participant RCA as RCA Agent
    participant KB as Knowledge Base
    participant Report as Report Generator
    participant GH as GitHub Issues
    participant KB2 as Knowledge Base Update

    IC->>Report: Generate report(incident_id)
    Report->>Scribe: Get timeline(events, decisions, actions)
    Scribe-->>Report: Structured timeline
    Report->>RCA: Get RCA findings(hypotheses, evidence)
    RCA-->>Report: RCA report
    Report->>KB: Get similar incidents(lessons)
    KB-->>Report: Historical context
    Report->>Report: Synthesize report
    Note over Report: Executive Summary, Timeline, RCA,\nImpact, What Went Well, Improvements, Action Items
    Report-->>IC: Markdown/HTML/PDF report
    IC->>Report: Review + Approve
    Report->>KB2: Extract lessons → Update KB
    Report->>GH: Create action item issues
    GH-->>Report: Issue URLs
    Report-->>IC: Final report with tracking links
```

---

## 🔗 Week-to-Week Integration Points

```mermaid
graph LR
    subgraph "WEEK 1: Foundations"
        W1[EKS Cluster\nJava/Python Services\nHelm Charts]
    end
    
    subgraph "WEEK 2: Telemetry/MCP"
        W2[MCP Server\nPrometheus/Loki/Tempo\nKnowledge Graph\nCorrelation Engine]
    end
    
    subgraph "WEEK 3: SLO/Budgets"
        W3[SLO Definitions\nError Budget Engine\nBurn Rate Alerts\nRelease Gates\nBlast Radius SLOs]
    end
    
    subgraph "WEEK 4: RCA/ICS"
        W4[RCA Agent\nKnowledge Base\nICS Engine\nShadow Duel\nPost-Incident Reports]
    end
    
    W1 -->|Workloads| W2
    W1 -->|Services| W3
    W2 -->|Telemetry API| W4
    W2 -->|Topology/Graph| W4
    W2 -->|Correlated Alerts| W4
    W3 -->|Budget Metrics| W4
    W3 -->|Deployment History| W4
    W3 -->|SLO Breach Context| W4
    W4 -->|Incidents| W2
    W4 -->|Lessons| W3
```

---

## 🌐 Network & Security Architecture

```mermaid
graph TB
    subgraph "VPC: ai-sre-vpc"
        subgraph "Public Subnets"
            ALB[ALB\nIngress Controller]
            BASTION[Bastion Host]
        end
        
        subgraph "Private Subnets - Control Plane"
            EKS_CP[EKS Control Plane]
        end
        
        subgraph "Private Subnets - Workloads"
            subgraph "NS: ai-sre-foundations"
                JS1[java-service]
                PS1[python-service]
            end
            
            subgraph "NS: ai-sre-telemetry"
                MCP[MCP Server]
                PM[Prometheus]
                LG[Loki]
                TP[Tempo]
                KG[Knowledge Graph]
                CE[Correlation Engine]
            end
            
            subgraph "NS: ai-sre-slo-budgets"
                EB[Error Budget Engine]
                RG[Release Gates]
                GRAF[Grafana]
            end
            
            subgraph "NS: ai-sre-rca-command"
                RCA[RCA Agent]
                CHROMA[ChromaDB]
                ICS[ICS Engine]
            end
        end
        
        subgraph "Private Subnets - Data"
            KAFKA[Kafka/MSK]
            REDIS[ElastiCache Redis]
            PG[RDS PostgreSQL]
        end
    end
    
    subgraph "External"
        GH[GitHub Actions]
        SLACK[Slack]
        PD[PagerDuty]
        ANTHROPIC[Anthropic API]
    end
    
    GH -.->|OIDC| EKS_CP
    GH -.->|Deploy| ALB
    ALB --> JS1
    ALB --> PS1
    JS1 --> KAFKA
    JS1 --> REDIS
    JS1 --> PG
    PS1 --> KAFKA
    PS1 --> REDIS
    PS1 --> PG
    RCA --> ANTHROPIC
    ICS --> SLACK
    ICS --> PD
    MCP --> PM
    MCP --> LG
    MCP --> TP
    MCP --> KG
    MCP --> CE
    PM --> JS1
    PM --> PS1
    LG --> JS1
    LG --> PS1
    TP --> JS1
    TP --> PS1
    RCA --> MCP
    RCA --> CHROMA
    EB --> PM
    RG --> EB
    GRAF --> PM
    GRAF --> EB
```

---

## 📋 Component Specifications

### RCA Agent Deployment

```yaml
# lab-4-rca-command/rca-agent/values.yaml
replicaCount: 1
namespace: ai-sre-rca-command

image:
  repository: ai-sre/rca-agent
  tag: latest
  pullPolicy: IfNotPresent

resources:
  limits:
    cpu: 2000m
    memory: 2Gi
  requests:
    cpu: 500m
    memory: 1Gi

mcp:
  url: http://mcp-server.ai-sre-telemetry.svc.cluster.local:8082
  timeout: 30s

knowledgeBase:
  type: chroma
  url: http://chroma.ai-sre-rca-command.svc.cluster.local:8000
  collection: incidents

model:
  provider: anthropic
  name: claude-3-5-sonnet-20241022
  apiKeySecret: anthropic-api-key

rbac:
  create: true
  clusterRoles:
    - prometheus-query
    - loki-query
    - tempo-query

service:
  type: ClusterIP
  port: 8080
  healthPath: /health
  investigatePath: /investigate
```

### Knowledge Base (ChromaDB) Deployment

```yaml
# lab-4-rca-command/knowledge-base/chroma-values.yaml
persistence:
  enabled: true
  size: 10Gi
  storageClass: gp3

resources:
  limits:
    cpu: 1000m
    memory: 4Gi
  requests:
    cpu: 250m
    memory: 1Gi

service:
  type: ClusterIP
  port: 8000

env:
  - name: CHROMA_SERVER_HOST
    value: "0.0.0.0"
  - name: CHROMA_SERVER_PORT
    value: "8000"
  - name: ANONYMIZED_TELEMETRY
    value: "False"
```

### ICS Engine Configuration

```yaml
# lab-4-rca-command/incident-command/config.yaml
team: platform-team
timezone: UTC

escalation:
  sev1:
    - delay: 0
      role: incident_commander
      notify: [oncall-primary]
      action: page
    - delay: 300
      role: operations_lead
      notify: [service-owner]
      action: page
    - delay: 900
      notify: [team-lead, manager]
      action: page
  
  sev2:
    - delay: 0
      role: incident_commander
      notify: [oncall-primary]
      action: slack
    - delay: 900
      role: operations_lead
      notify: [service-owner]
      action: slack
    - delay: 1800
      notify: [team-lead]
      action: slack

communication:
  slack:
    webhook_secret: slack-webhook-url
    channel_template: "#incidents-{namespace}"
    update_cadence:
      sev1: 600
      sev2: 900
      sev3: 1800
  status_page:
    url: https://status.example.com/api
    api_key_secret: statuspage-api-key
  github:
    repo: ramkannans-labs/ai-sre-rca-command
    token_secret: github-token
    labels: [incident, auto-generated]

timeline:
  sources:
    - loki
    - prometheus_alerts
    - github_deployments
    - slack_messages
  loki_url: http://loki.ai-sre-telemetry.svc.cluster.local:3100
  prometheus_url: http://prometheus.ai-sre-telemetry.svc.cluster.local:9090
```

---

## 🎯 Data Flow Summary

| Flow | Source | Destination | Protocol | Frequency |
|------|--------|-------------|----------|-----------|
| Metrics scrape | Services | Prometheus | HTTP/PromQL | 15s |
| Log collection | Services | Loki | HTTP/LogQL | Continuous |
| Trace export | Services | Tempo | OTLP/gRPC | Continuous |
| MCP queries | RCA Agent | MCP Server | HTTP/REST | On-demand |
| MCP → Prometheus | MCP Server | Prometheus | HTTP/PromQL | On-demand |
| MCP → Loki | MCP Server | Loki | HTTP/LogQL | On-demand |
| MCP → Tempo | MCP Server | Tempo | HTTP/TraceQL | On-demand |
| MCP → Knowledge Graph | MCP Server | KG Service | HTTP/REST | On-demand |
| Knowledge Base ingest | Scripts | ChromaDB | HTTP/REST | Batch/On-demand |
| Knowledge Base query | RCA Agent | ChromaDB | HTTP/REST | On-demand |
| Timeline reconstruction | ICS Engine | Loki/Prometheus/GitHub | HTTP/REST | On incident |
| Escalation notifications | ICS Engine | Slack/PagerDuty | Webhook | On trigger |
| Post-incident report | Report Gen | GitHub Issues/Knowledge Base | HTTP/REST | On close |
| Shadow Duel metrics | Simulation | Prometheus | Pushgateway | Per exercise |

---

*All components deploy to AWS EKS. No GCP/Azure dependencies. All GitHub Actions use `workflow_dispatch` manual triggers only.*