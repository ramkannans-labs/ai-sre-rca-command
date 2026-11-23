# Incident Command System (ICS) Reference for Software Incidents

> **Adapted from:** FEMA ICS-100/200 for software engineering teams  
> **Purpose:** Quick reference for Week 4 labs and real incidents

---

## 🎯 ICS Core Principles

| Principle | Software Adaptation |
|-----------|---------------------|
| **Unified Command** | Single Incident Commander owns the incident |
| **Span of Control** | 1 IC manages 3-7 direct reports (Ops, Comms, Scribe, SMEs) |
| **Common Terminology** | SEV-1/2/3, not "critical/high/medium" |
| **Modular Organization** | Activate only needed roles |
| **Manageable Span** | Delegate when >7 people involved |
| **Incident Action Plan** | Living document: timeline + objectives + assignments |

---

## 👥 ICS Roles & Responsibilities

### Incident Commander (IC) — **Required for every incident**
```
┌─────────────────────────────────────────────────────────────┐
│  INCIDENT COMMANDER                                         │
├─────────────────────────────────────────────────────────────┤
│  Authority: Final decision maker for the incident           │
│  Reports to: Stakeholders (director, VP)                    │
│  Direct Reports: Ops Lead, Comms Lead, Scribe, Safety       │
│                                                             │
│  RESPONSIBILITIES:                                          │
│  □ Declare incident severity (SEV-1/2/3)                   │
│  □ Assign roles and delegate tasks                          │
│  □ Set incident objectives (e.g., "Restore checkout API")  │
│  □ Approve mitigation actions (rollback, scale, config)    │
│  □ Authorize communications (internal + external)           │
│  □ Manage escalation                                        │
│  □ Declare resolution and close incident                    │
│  □ Initiate post-incident review                            │
│                                                             │
│  DECISION RIGHTS:                                           │
│  ✓ Rollback deployment?        ✓ Page additional engineers? │
│  ✓ Disable feature flag?       ✓ Engage vendor support?     │
│  ✗ Approve code changes        ✗ Change architecture        │
└─────────────────────────────────────────────────────────────┘
```

### Operations Lead — **Required for SEV-1/2**
```
┌─────────────────────────────────────────────────────────────┐
│  OPERATIONS LEAD                                            │
├─────────────────────────────────────────────────────────────┤
│  Authority: Executes technical mitigation                   │
│  Reports to: Incident Commander                             │
│  Direct Reports: Service owners, SMEs as needed             │
│                                                             │
│  RESPONSIBILITIES:                                          │
│  □ Investigate technical root cause                         │
│  □ Execute runbooks and playbooks                           │
│  □ Deploy fixes (rollback, config, scale)                   │
│  □ Verify recovery (health checks, SLOs)                    │
│  □ Coordinate with service owners                           │
│  □ Report technical status to IC                            │
│                                                             │
│  TOOLS:                                                     │
│  • kubectl / helm                                           │
│  • RCA Agent (hypotheses)                                   │
│  • MCP (metrics, logs, traces)                              │
│  • Knowledge Base (similar incidents)                       │
│  • Runbook library                                          │
└─────────────────────────────────────────────────────────────┘
```

### Communications Lead — **Required for SEV-1; recommended for SEV-2**
```
┌─────────────────────────────────────────────────────────────┐
│  COMMUNICATIONS LEAD                                        │
├─────────────────────────────────────────────────────────────┤
│  Authority: Owns all incident communications                │
│  Reports to: Incident Commander                             │
│                                                             │
│  RESPONSIBILITIES:                                          │
│  □ Internal updates (Slack, every cadence)                  │
│  □ Stakeholder notifications (execs, customers, support)    │
│  □ Status page updates                                      │
│  □ Customer-facing communications (if applicable)           │
│  □ Media/legal coordination (if needed)                     │
│  □ Document all communications in timeline                  │
│                                                             │
│  CADENCE:                                                   │
│  SEV-1: Every 10 minutes                                    │
│  SEV-2: Every 15 minutes                                    │
│  SEV-3: Every 30 minutes                                    │
│                                                             │
│  TEMPLATE:                                                  │
│  "[SEV-X] <Title> - <Current Status> - <Next Update in Xm>" │
│  Impact: <customer-facing impact>                           │
│  Root Cause: <known/unknown>                                │
│  ETA: <estimated resolution>                                │
│  Actions: <what we're doing>                                │
└─────────────────────────────────────────────────────────────┘
```

### Scribe — **Automated (Timeline Bot)**
```
┌─────────────────────────────────────────────────────────────┐
│  SCRIBE (Automated)                                         │
├─────────────────────────────────────────────────────────────┤
│  Authority: Records everything; no decision authority       │
│  Reports to: Incident Commander                             │
│                                                             │
│  RESPONSIBILITIES (Automated):                              │
│  □ Ingest alerts (Prometheus Alertmanager)                  │
│  □ Ingest logs (Loki) with incident labels                  │
│  □ Ingest deployments (GitHub/ArgoCD)                       │
│  □ Ingest Slack messages in incident channel                │
│  □ Ingest RCA agent findings                                │
│  □ Ingest manual timeline entries                           │
│  □ Reconstruct chronological timeline                       │
│  □ Export timeline for post-incident report                 │
│                                                             │
│  DATA SOURCES:                                              │
│  • Loki: {incident_id="INC-XXX"}                            │
│  • Prometheus: ALERTS{incident_id="INC-XXX"}                │
│  • GitHub: Deployments during incident window               │
│  • Slack: #incident-XXX channel messages                    │
│  • Manual: /timeline add "14:23 - IC assigned ops to @jane" │
└─────────────────────────────────────────────────────────────┘
```

### Subject Matter Experts (SMEs) — **As needed**
| SME Type | When to Engage | Typical Actions |
|----------|----------------|-----------------|
| **Database** | Connection pool, query perf, locks | Analyze slow queries, check locks, scale read replicas |
| **Network** | DNS, latency, connectivity | Check VPC, security groups, service mesh, CDN |
| **Security** | Suspected breach, auth issues | Review audit logs, check IAM, rotate credentials |
| **Platform/K8s** | Node issues, scheduler, CNI | Check node health, pod scheduling, resource quotas |
| **Vendor** | Cloud provider outage, 3rd party API | Open support ticket, check status page, implement fallback |

---

## 🚨 Severity Definitions

| Severity | Customer Impact | Response Time | Examples |
|----------|-----------------|---------------|----------|
| **SEV-1** | Critical: Core workflow down, revenue loss, data loss | **Immediate** (page) | Checkout failing, payment processing down, data corruption |
| **SEV-2** | Major: Degraded experience, partial outage, SLO breach risk | **15 min** (page/slack) | High latency p99, elevated error rate, single feature broken |
| **SEV-3** | Minor: Limited impact, workaround exists, no SLO breach | **1 hour** (slack) | Non-critical feature degraded, cosmetic bug, internal tool issue |

### Severity Escalation Triggers
```
SEV-3 → SEV-2:  • SLO burn rate > 2x (Week 3)
                • Duration > 1 hour without progress
                • Customer escalation

SEV-2 → SEV-1:  • Revenue impact confirmed
                • Data loss/corruption detected
                • Security breach suspected
                • Duration > 30 min without mitigation
                • Multiple services affected (cascade)
```

---

## 📋 Incident Lifecycle

### 1. DETECTION → ACKNOWLEDGMENT (0-5 min)
```
Alert fires
    │
    ▼
On-call receives page
    │
    ▼
/incident start SEV-X "Description" --assign-ic @me
    │
    ▼
IC acknowledges in Slack: "IC acknowledged. Investigating."
    │
    ▼
Timeline starts (auto-scribe begins)
```

### 2. ROLE ASSIGNMENT (5-10 min)
```
/incident assign ops @service-owner
/incident assign comms @sre-comms
/incident assign scribe auto
/incident assign sme-db @dba (if needed)
```

### 3. INVESTIGATION (10-30 min)
```
IC: "Ops, what's your top hypothesis?"
Ops: Queries RCA Agent → Gets ranked hypotheses
Ops: Validates top hypothesis with targeted MCP queries
Ops: Reports to IC: "Root cause: connection pool exhaustion (85% confidence)"
IC: "Comms, notify stakeholders. Ops, execute runbook."
```

### 4. MITIGATION (20-45 min)
```
Ops: Executes runbook (rollback / config change / scale)
Ops: Monitors health checks + SLO dashboards
IC: Receives recovery confirmation
IC: "Comms, send resolution notification."
```

### 5. RECOVERY VERIFICATION (30-60 min)
```
Ops: Verifies SLO compliance (Week 3 dashboards)
Ops: Confirms error budget not critically burning
IC: Declares "Incident resolved"
/incident close INC-XXX "Rolled back v2.3.1 → v2.3.0; all services healthy"
```

### 6. POST-INCIDENT (Within 24-48 hours)
```
IC: Initiates post-incident review
Scribe: Exports full timeline
RCA Agent: Contributes findings
Report Gen: Creates report with action items
IC: Reviews + approves report
Action items → GitHub Issues with owners + due dates
Lessons → Knowledge Base ingestion
```

---

## 💬 Communication Templates

### Initial Notification (SEV-1/2)
```
:rotating_light: **INCIDENT DECLARED** :rotating_light:
**Incident:** INC-2024-042
**Severity:** SEV-2
**Title:** java-service elevated error rate (12%)
**Impact:** Orders API returning 500s for ~15% of requests
**IC:** @jane.doe
**Ops:** @john.smith
**Comms:** @sarah.wilson
**Started:** 2024-03-15 14:22 UTC
**Next Update:** 14:37 UTC (15 min)

**Status:** Investigating root cause
**Suspected:** Recent deployment v2.3.1
**Actions:** RCA agent analyzing; Ops checking connection pools
```

### Status Update (Every Cadence)
```
:arrows_counterclockwise: **INCIDENT UPDATE** - INC-2024-042
**Severity:** SEV-2 (unchanged)
**Status:** Mitigating - rolling back deployment
**Root Cause:** CONFIRMED - Connection pool exhaustion in java-service (HikariCP max-pool-size=10, no timeout)
**Impact:** Orders API 500s reduced to 3% (improving)
**Actions Taken:** 
  ✓ RCA agent identified connection pool exhaustion (14:28)
  ✓ Ops validated via MCP metrics (14:30)
  ✓ Rollback initiated: v2.3.1 → v2.3.0 (14:32)
  ⏳ Rollout in progress (ETA 14:37)
**Next Update:** 14:37 UTC
```

### Resolution Notification
```
:white_check_mark: **INCIDENT RESOLVED** - INC-2024-042
**Severity:** SEV-2 → RESOLVED
**Duration:** 18 minutes (14:22 - 14:40)
**Root Cause:** Connection pool exhaustion after v2.3.1 deployment
  - Missing `connectionTimeout` and `idleTimeout` in HikariCP config
  - Connection leak in new order processing code path
**Resolution:** Rolled back to v2.3.0; fix deployed in v2.3.2
**Impact:** ~2,400 failed orders; $12K estimated revenue impact
**SLO Impact:** Availability SLO burned 0.8% of monthly budget
**Action Items:**
  1. Add connection pool config validation to CI (Owner: @jane, Due: 3/22)
  2. Add connection leak detection to integration tests (Owner: @john, Due: 3/29)
  3. Update java-service runbook with pool exhaustion steps (Owner: @sarah, Due: 3/20)
**Post-Incident Review:** Scheduled 2024-03-18 10:00 UTC
**Report:** https://github.com/ramkannans-labs/ai-sre-rca-command/issues/142
```

---

## ⚡ Quick Commands (Slack Bot)

| Command | Description | Example |
|---------|-------------|---------|
| `/incident start SEV-1 "title" --assign-ic @me` | Declare incident | `/incident start SEV-1 "Payment API down" --assign-ic @jane` |
| `/incident assign ops @user` | Assign Operations Lead | `/incident assign ops @john` |
| `/incident assign comms @user` | Assign Communications Lead | `/incident assign comms @sarah` |
| `/incident assign scribe auto` | Enable auto-scribe | `/incident assign scribe auto` |
| `/incident assign sme-db @user` | Assign DB SME | `/incident assign sme-db @dba` |
| `/incident update "message"` | Add timeline entry | `/incident update "Root cause confirmed: pool exhaustion"` |
| `/incident severity SEV-1` | Change severity | `/incident severity SEV-1` |
| `/incident close "resolution summary"` | Close incident | `/incident close "Rolled back v2.3.1; all healthy"` |
| `/incident timeline` | Show current timeline | `/incident timeline` |
| `/incident status` | Show current status | `/incident status` |

---

## 🎯 Runbook Integration

### Runbook Structure (Markdown)
```markdown
---
title: "java-service: Connection Pool Exhaustion"
service: java-service
symptoms:
  - "High error rate on /api/* endpoints"
  - "Thread pool queue full in logs"
  - "Latency p99 > 30s"
severity: SEV-2
estimated_resolution: 15 min
---

## Diagnosis
1. Check HikariCP metrics: `hikaricp_connections_active`, `hikaricp_connections_idle`, `hikaricp_connections_pending`
2. Check application logs for "Connection not available" or "Pool exhausted"
3. Verify recent deployment changed pool config

## Mitigation
1. **Immediate**: Rollback deployment
   ```bash
   kubectl rollout undo deployment/java-service -n production
   ```
2. **If rollback not possible**: Scale replicas
   ```bash
   kubectl scale deployment java-service --replicas=20 -n production
   ```
3. **Config fix** (requires deploy):
   - Add `connectionTimeout: 5000`
   - Add `idleTimeout: 300000`
   - Set `maximumPoolSize: 50`

## Verification
- Error rate < 0.1%
- Latency p99 < 500ms
- Active connections < 80% of pool
- No "pool exhausted" logs for 5 min

## Prevention
- CI check for connection pool config
- Integration test with load to verify pool sizing
- Runbook review quarterly
```

---

## 📊 Metrics to Track During Incident

| Metric | Target | Source |
|--------|--------|--------|
| **Time to Acknowledge** | < 5 min | PagerDuty |
| **Time to IC Assignment** | < 2 min | Slack bot |
| **Time to First Hypothesis** | < 10 min | RCA Agent / Ops |
| **Time to Root Cause** | < 20 min | RCA Agent / Ops |
| **Time to Mitigation Start** | < 30 min | Ops |
| **Time to Resolution** | < 60 min (SEV-2) | IC |
| **Communication Cadence Met** | 100% | Comms Lead |
| **Timeline Completeness** | > 90% events captured | Scribe |

---

## 🔄 Escalation Policy Template

```yaml
# lab-4-rca-command/incident-command/escalation_policy.yaml
team: platform-team
timezone: UTC

escalation:
  sev1:
    - delay: 0
      role: incident_commander
      notify: [oncall-primary]
      action: page
      message: "SEV-1 declared: {title}. You are IC."
    - delay: 300        # 5 min
      role: operations_lead
      notify: [service-owner]
      action: page
      message: "SEV-1: {title}. Ops lead needed for {service}."
    - delay: 900        # 15 min
      notify: [team-lead, engineering-manager]
      action: page
      message: "SEV-1 ongoing >15 min: {title}. Leadership awareness."
    - delay: 1800       # 30 min
      notify: [director, vp-engineering]
      action: page
      message: "SEV-1 ongoing >30 min: {title}. Executive escalation."
  
  sev2:
    - delay: 0
      role: incident_commander
      notify: [oncall-primary]
      action: slack
    - delay: 900        # 15 min
      role: operations_lead
      notify: [service-owner]
      action: slack
    - delay: 1800       # 30 min
      notify: [team-lead]
      action: slack
    - delay: 3600       # 60 min
      notify: [engineering-manager]
      action: slack
  
  sev3:
    - delay: 0
      role: incident_commander
      notify: [oncall-primary]
      action: slack
    - delay: 3600       # 60 min
      notify: [service-owner]
      action: slack

# Auto-escalation triggers
auto_escalate:
  - condition: "slo_burn_rate_24h > 10"
    action: "escalate_to_sev1"
  - condition: "duration > 3600 and no_mitigation"
    action: "escalate_severity"
  - condition: "affected_services > 2"
    action: "escalate_to_sev1"
```

---

## ✅ Incident Commander Checklist

### On Declaration
- [ ] Declare severity (SEV-1/2/3)
- [ ] Assign self as IC in Slack bot
- [ ] Assign Operations Lead
- [ ] Assign Communications Lead (SEV-1/2)
- [ ] Enable auto-scribe
- [ ] Set incident objectives (e.g., "Restore Orders API to <1% error rate")

### During Investigation
- [ ] Get hypothesis from Ops + RCA Agent
- [ ] Validate hypothesis makes sense
- [ ] Authorize mitigation action
- [ ] Ensure Comms updates on cadence
- [ ] Monitor for escalation triggers

### During Mitigation
- [ ] Track mitigation progress
- [ ] Verify recovery with Ops (health checks + SLOs)
- [ ] Approve "all clear" for resolution

### On Resolution
- [ ] Declare incident resolved
- [ ] Close incident in Slack bot
- [ ] Ensure Comms sends resolution notification
- [ ] Initiate post-incident review (within 24h)
- [ ] Assign action item owners

### Post-Incident
- [ ] Review generated report
- [ ] Approve action items with owners + due dates
- [ ] Schedule review meeting
- [ ] Ensure lessons ingested to Knowledge Base

---

## 🆘 Common Anti-Patterns to Avoid

| Anti-Pattern | Why It's Bad | Better Approach |
|--------------|--------------|-----------------|
| **No IC assigned** | Confusion, duplicated work, no decisions | Always assign IC immediately |
| **IC doing technical work** | IC loses situational awareness | IC delegates; Ops does technical work |
| **No Comms Lead** | Stakeholders learn from Twitter | Assign Comms for SEV-1/2 |
| **Skipping timeline** | Post-incident review impossible | Auto-scribe + manual entries |
| **Fixing without hypothesis** | Random changes, longer MTTR | RCA Agent → Hypothesis → Validate → Fix |
| **No runbook reference** | Re-inventing wheel every time | Check runbook library first |
| **Closing without verification** | Recurrence within hours | SLO verification + 10 min observation |
| **No post-incident review** | Same incident repeats | Mandatory review within 48h |

---

*This reference is used in Week 4 labs. Keep it handy during Shadow Duel and Capstone exercises.*