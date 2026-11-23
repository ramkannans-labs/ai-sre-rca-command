#!/bin/bash
# Setup script for Week 4 RCA Command Stack
# Provisions all infrastructure needed for RCA agent, knowledge base, incident command, and shadow duel exercises

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
NAMESPACE_RCA="rca-system"
NAMESPACE_MONITORING="monitoring"
NAMESPACE_KB="knowledge-base"
CHROMADB_PVC_SIZE="10Gi"
GRAFANA_PVC_SIZE="5Gi"

echo -e "${BLUE}================================================${NC}"
echo -e "${BLUE}  AI SRE Week 4 - RCA Command Stack Setup${NC}"
echo -e "${BLUE}================================================${NC}"
echo ""

# Function to print status
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check prerequisites
check_prerequisites() {
    print_status "Checking prerequisites..."

    local missing=0

    for cmd in kubectl helm docker python3 pip3; do
        if ! command -v $cmd &> /dev/null; then
            print_error "$cmd is not installed"
            missing=1
        fi
    done

    if [ $missing -eq 1 ]; then
        print_error "Please install missing prerequisites"
        exit 1
    fi

    # Check kubectl context
    local context=$(kubectl config current-context 2>/dev/null || echo "none")
    print_status "Kubernetes context: $context"

    if [[ "$context" == "none" ]]; then
        print_error "No kubectl context set. Please configure kubectl for your EKS cluster."
        exit 1
    fi

    print_status "Prerequisites check passed"
}

# Create namespaces
create_namespaces() {
    print_status "Creating namespaces..."

    for ns in "$NAMESPACE_RCA" "$NAMESPACE_MONITORING" "$NAMESPACE_KB"; do
        if kubectl get namespace "$ns" &>/dev/null; then
            print_warning "Namespace $ns already exists"
        else
            kubectl create namespace "$ns"
            print_status "Created namespace: $ns"
        fi
    done
}

# Install ChromaDB for vector knowledge base
install_chromadb() {
    print_status "Installing ChromaDB vector database..."

    # Add Helm repo if needed
    helm repo add chromadb https://chromadb.github.io/helm-charts 2>/dev/null || true
    helm repo update

    # Create values file
    cat > /tmp/chromadb-values.yaml <<EOF
persistence:
  enabled: true
  size: ${CHROMADB_PVC_SIZE}
  storageClass: gp3

resources:
  limits:
    cpu: 2000m
    memory: 4Gi
  requests:
    cpu: 500m
    memory: 2Gi

service:
  type: ClusterIP
  port: 8000

ingress:
  enabled: false

env:
  - name: CHROMA_SERVER_HOST
    value: "0.0.0.0"
  - name: CHROMA_SERVER_HTTP_PORT
    value: "8000"
  - name: ALLOW_RESET
    value: "TRUE"
  - name: ANONYMIZED_TELEMETRY
    value: "FALSE"

# Enable authentication for production
auth:
  enabled: false
  # credentials:
  #   - username: admin
  #     password: changeme
EOF

    helm upgrade --install chromadb chromadb/chromadb \
        --namespace "$NAMESPACE_KB" \
        --values /tmp/chromadb-values.yaml \
        --wait --timeout 5m

    print_status "ChromaDB installed"
}

# Install Grafana for dashboards
install_grafana() {
    print_status "Installing Grafana..."

    helm repo add grafana https://grafana.github.io/helm-charts 2>/dev/null || true
    helm repo update

    cat > /tmp/grafana-values.yaml <<EOF
persistence:
  enabled: true
  size: ${GRAFANA_PVC_SIZE}
  storageClass: gp3

adminUser: admin
adminPassword: "admin123"  # Change in production!

service:
  type: ClusterIP
  port: 3000

ingress:
  enabled: false

datasources:
  datasources.yaml:
    apiVersion: 1
    datasources:
      - name: Prometheus
        type: prometheus
        url: http://prometheus-operated.monitoring:9090
        access: proxy
        isDefault: true
      - name: Loki
        type: loki
        url: http://loki.monitoring:3100
        access: proxy
      - name: Tempo
        type: tempo
        url: http://tempo.monitoring:3200
        access: proxy

dashboardProviders:
  dashboardproviders.yaml:
    apiVersion: 1
    providers:
      - name: 'RCA Dashboards'
        orgId: 1
        folder: 'RCA Command'
        type: file
        disableDeletion: false
        updateIntervalSeconds: 10
        allowUiUpdates: true
        options:
          path: /var/lib/grafana/dashboards/rca

sidecar:
  dashboards:
    enabled: true
    label: grafana_dashboard
    folder: /tmp/dashboards
    provider:
      foldersFromFilesStructure: true

resources:
  limits:
    cpu: 1000m
    memory: 1Gi
  requests:
    cpu: 250m
    memory: 512Mi
EOF

    helm upgrade --install grafana grafana/grafana \
        --namespace "$NAMESPACE_MONITORING" \
        --values /tmp/grafana-values.yaml \
        --wait --timeout 5m

    print_status "Grafana installed"
}

# Deploy RCA Agent
deploy_rca_agent() {
    print_status "Deploying RCA Agent..."

    # Build and push Docker image (assumes local Docker and registry access)
    # In CI/CD, this would be a separate build step
    cat > /tmp/rca-agent-deployment.yaml <<EOF
apiVersion: apps/v1
kind: Deployment
metadata:
  name: rca-agent
  namespace: ${NAMESPACE_RCA}
  labels:
    app: rca-agent
    component: ai-rca
spec:
  replicas: 1
  selector:
    matchLabels:
      app: rca-agent
  template:
    metadata:
      labels:
        app: rca-agent
        component: ai-rca
      annotations:
        prometheus.io/scrape: "true"
        prometheus.io/port: "8080"
        prometheus.io/path: "/metrics"
    spec:
      serviceAccountName: rca-agent
      containers:
        - name: rca-agent
          image: ghcr.io/ramkannans-labs/ai-sre-rca-command/rca-agent:latest
          imagePullPolicy: Always
          ports:
            - containerPort: 8080
              name: http
          env:
            - name: CHROMADB_HOST
              value: "chromadb.${NAMESPACE_KB}.svc.cluster.local"
            - name: CHROMADB_PORT
              value: "8000"
            - name: PROMETHEUS_URL
              value: "http://prometheus-operated.monitoring:9090"
            - name: LOKI_URL
              value: "http://loki.monitoring:3100"
            - name: TEMPO_URL
              value: "http://tempo.monitoring:3200"
            - name: MCP_SERVER_URL
              value: "http://mcp-server.${NAMESPACE_MONITORING}.svc.cluster.local:8000"
            - name: KNOWLEDGE_BASE_COLLECTION
              value: "incidents"
            - name: LOG_LEVEL
              value: "INFO"
          resources:
            limits:
              cpu: "2000m"
              memory: "4Gi"
            requests:
              cpu: "500m"
              memory: "1Gi"
          livenessProbe:
            httpGet:
              path: /health
              port: 8080
            initialDelaySeconds: 30
            periodSeconds: 10
          readinessProbe:
            httpGet:
              path: /ready
              port: 8080
            initialDelaySeconds: 10
            periodSeconds: 5
---
apiVersion: v1
kind: Service
metadata:
  name: rca-agent
  namespace: ${NAMESPACE_RCA}
spec:
  selector:
    app: rca-agent
  ports:
    - port: 8080
      targetPort: 8080
      name: http
  type: ClusterIP
---
apiVersion: v1
kind: ServiceAccount
metadata:
  name: rca-agent
  namespace: ${NAMESPACE_RCA}
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: rca-agent
  namespace: ${NAMESPACE_RCA}
rules:
  - apiGroups: [""]
    resources: ["pods", "services", "configmaps", "events"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["apps"]
    resources: ["deployments", "replicasets", "statefulsets"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["networking.k8s.io"]
    resources: ["networkpolicies", "ingresses"]
    verbs: ["get", "list", "watch"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: rca-agent
  namespace: ${NAMESPACE_RCA}
subjects:
  - kind: ServiceAccount
    name: rca-agent
    namespace: ${NAMESPACE_RCA}
roleRef:
  kind: Role
  name: rca-agent
  apiGroup: rbac.authorization.k8s.io
EOF

    kubectl apply -f /tmp/rca-agent-deployment.yaml
    print_status "RCA Agent deployed"
}

# Deploy Incident Command components
deploy_incident_command() {
    print_status "Deploying Incident Command components..."

    cat > /tmp/incident-command-deployment.yaml <<EOF
apiVersion: apps/v1
kind: Deployment
metadata:
  name: incident-command-api
  namespace: ${NAMESPACE_RCA}
  labels:
    app: incident-command-api
    component: ics
spec:
  replicas: 1
  selector:
    matchLabels:
      app: incident-command-api
  template:
    metadata:
      labels:
        app: incident-command-api
        component: ics
      annotations:
        prometheus.io/scrape: "true"
        prometheus.io/port: "8081"
        prometheus.io/path: "/metrics"
    spec:
      serviceAccountName: incident-command
      containers:
        - name: incident-command-api
          image: ghcr.io/ramkannans-labs/ai-sre-rca-command/incident-command:latest
          imagePullPolicy: Always
          ports:
            - containerPort: 8081
              name: http
          env:
            - name: CHROMADB_HOST
              value: "chromadb.${NAMESPACE_KB}.svc.cluster.local"
            - name: CHROMADB_PORT
              value: "8000"
            - name: RCA_AGENT_URL
              value: "http://rca-agent.${NAMESPACE_RCA}.svc.cluster.local:8080"
            - name: SLACK_WEBHOOK_URL
              valueFrom:
                secretKeyRef:
                  name: ics-secrets
                  key: slack-webhook
                  optional: true
            - name: PAGERDUTY_KEY
              valueFrom:
                secretKeyRef:
                  name: ics-secrets
                  key: pagerduty-key
                  optional: true
            - name: ZOOM_API_KEY
              valueFrom:
                secretKeyRef:
                  name: ics-secrets
                  key: zoom-api-key
                  optional: true
            - name: ZOOM_API_SECRET
              valueFrom:
                secretKeyRef:
                  name: ics-secrets
                  key: zoom-api-secret
                  optional: true
            - name: STATUSPAGE_API_KEY
              valueFrom:
                secretKeyRef:
                  name: ics-secrets
                  key: statuspage-api-key
                  optional: true
            - name: STATUSPAGE_PAGE_ID
              valueFrom:
                secretKeyRef:
                  name: ics-secrets
                  key: statuspage-page-id
                  optional: true
          resources:
            limits:
              cpu: "1000m"
              memory: "2Gi"
            requests:
              cpu: "250m"
              memory: "512Mi"
          livenessProbe:
            httpGet:
              path: /health
              port: 8081
            initialDelaySeconds: 20
            periodSeconds: 10
          readinessProbe:
            httpGet:
              path: /ready
              port: 8081
            initialDelaySeconds: 10
            periodSeconds: 5
---
apiVersion: v1
kind: Service
metadata:
  name: incident-command-api
  namespace: ${NAMESPACE_RCA}
spec:
  selector:
    app: incident-command-api
  ports:
    - port: 8081
      targetPort: 8081
      name: http
  type: ClusterIP
---
apiVersion: v1
kind: ServiceAccount
metadata:
  name: incident-command
  namespace: ${NAMESPACE_RCA}
---
apiVersion: v1
kind: Secret
metadata:
  name: ics-secrets
  namespace: ${NAMESPACE_RCA}
type: Opaque
stringData:
  # Fill these in with actual values
  slack-webhook: ""
  pagerduty-key: ""
  zoom-api-key: ""
  zoom-api-secret: ""
  statuspage-api-key: ""
  statuspage-page-id: ""
EOF

    kubectl apply -f /tmp/incident-command-deployment.yaml
    print_status "Incident Command API deployed"
}

# Deploy Shadow Duel Orchestrator
deploy_shadow_duel() {
    print_status "Deploying Shadow Duel Orchestrator..."

    cat > /tmp/shadow-duel-deployment.yaml <<EOF
apiVersion: apps/v1
kind: Deployment
metadata:
  name: shadow-duel-orchestrator
  namespace: ${NAMESPACE_RCA}
  labels:
    app: shadow-duel-orchestrator
    component: training
spec:
  replicas: 1
  selector:
    matchLabels:
      app: shadow-duel-orchestrator
  template:
    metadata:
      labels:
        app: shadow-duel-orchestrator
        component: training
      annotations:
        prometheus.io/scrape: "true"
        prometheus.io/port: "8082"
        prometheus.io/path: "/metrics"
    spec:
      serviceAccountName: shadow-duel
      containers:
        - name: shadow-duel-orchestrator
          image: ghcr.io/ramkannans-labs/ai-sre-rca-command/shadow-duel:latest
          imagePullPolicy: Always
          ports:
            - containerPort: 8082
              name: http
          env:
            - name: CHROMADB_HOST
              value: "chromadb.${NAMESPACE_KB}.svc.cluster.local"
            - name: CHROMADB_PORT
              value: "8000"
            - name: SCENARIO_ENGINE_URL
              value: "http://scenario-engine.${NAMESPACE_RCA}.svc.cluster.local:8083"
            - name: METRICS_COLLECTOR_URL
              value: "http://metrics-collector.${NAMESPACE_RCA}.svc.cluster.local:8084"
            - name: RCA_AGENT_URL
              value: "http://rca-agent.${NAMESPACE_RCA}.svc.cluster.local:8080"
          resources:
            limits:
              cpu: "1000m"
              memory: "2Gi"
            requests:
              cpu: "250m"
              memory: "512Mi"
---
apiVersion: v1
kind: Service
metadata:
  name: shadow-duel-orchestrator
  namespace: ${NAMESPACE_RCA}
spec:
  selector:
    app: shadow-duel-orchestrator
  ports:
    - port: 8082
      targetPort: 8082
      name: http
  type: ClusterIP
---
apiVersion: v1
kind: ServiceAccount
metadata:
  name: shadow-duel
  namespace: ${NAMESPACE_RCA}
EOF

    kubectl apply -f /tmp/shadow-duel-deployment.yaml
    print_status "Shadow Duel Orchestrator deployed"
}

# Deploy Scenario Engine
deploy_scenario_engine() {
    print_status "Deploying Scenario Engine..."

    cat > /tmp/scenario-engine-deployment.yaml <<EOF
apiVersion: apps/v1
kind: Deployment
metadata:
  name: scenario-engine
  namespace: ${NAMESPACE_RCA}
  labels:
    app: scenario-engine
    component: simulation
spec:
  replicas: 1
  selector:
    matchLabels:
      app: scenario-engine
  template:
    metadata:
      labels:
        app: scenario-engine
        component: simulation
      annotations:
        prometheus.io/scrape: "true"
        prometheus.io/port: "8083"
        prometheus.io/path: "/metrics"
    spec:
      serviceAccountName: scenario-engine
      containers:
        - name: scenario-engine
          image: ghcr.io/ramkannans-labs/ai-sre-rca-command/scenario-engine:latest
          imagePullPolicy: Always
          ports:
            - containerPort: 8083
              name: http
          env:
            - name: KUBECONFIG
              value: "/etc/kubeconfig/kubeconfig"
          volumeMounts:
            - name: kubeconfig
              mountPath: /etc/kubeconfig
              readOnly: true
          resources:
            limits:
              cpu: "2000m"
              memory: "2Gi"
            requests:
              cpu: "500m"
              memory: "1Gi"
      volumes:
        - name: kubeconfig
          secret:
            secretName: scenario-engine-kubeconfig
---
apiVersion: v1
kind: Service
metadata:
  name: scenario-engine
  namespace: ${NAMESPACE_RCA}
spec:
  selector:
    app: scenario-engine
  ports:
    - port: 8083
      targetPort: 8083
      name: http
  type: ClusterIP
---
apiVersion: v1
kind: ServiceAccount
metadata:
  name: scenario-engine
  namespace: ${NAMESPACE_RCA}
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: scenario-engine
rules:
  - apiGroups: [""]
    resources: ["pods", "pods/exec", "services", "configmaps", "namespaces"]
    verbs: ["get", "list", "watch", "create", "delete", "patch"]
  - apiGroups: ["apps"]
    resources: ["deployments", "replicasets", "statefulsets", "daemonsets"]
    verbs: ["get", "list", "watch", "create", "delete", "patch", "update"]
  - apiGroups: ["batch"]
    resources: ["jobs", "cronjobs"]
    verbs: ["get", "list", "watch", "create", "delete"]
  - apiGroups: ["networking.k8s.io"]
    resources: ["networkpolicies", "ingresses"]
    verbs: ["get", "list", "watch", "create", "delete", "patch"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: scenario-engine
subjects:
  - kind: ServiceAccount
    name: scenario-engine
    namespace: ${NAMESPACE_RCA}
roleRef:
  kind: ClusterRole
  name: scenario-engine
  apiGroup: rbac.authorization.k8s.io
EOF

    kubectl apply -f /tmp/scenario-engine-deployment.yaml
    print_status "Scenario Engine deployed"
}

# Deploy Metrics Collector
deploy_metrics_collector() {
    print_status "Deploying Metrics Collector..."

    cat > /tmp/metrics-collector-deployment.yaml <<EOF
apiVersion: apps/v1
kind: Deployment
metadata:
  name: metrics-collector
  namespace: ${NAMESPACE_RCA}
  labels:
    app: metrics-collector
    component: training
spec:
  replicas: 1
  selector:
    matchLabels:
      app: metrics-collector
  template:
    metadata:
      labels:
        app: metrics-collector
        component: training
      annotations:
        prometheus.io/scrape: "true"
        prometheus.io/port: "8084"
        prometheus.io/path: "/metrics"
    spec:
      serviceAccountName: metrics-collector
      containers:
        - name: metrics-collector
          image: ghcr.io/ramkannans-labs/ai-sre-rca-command/metrics-collector:latest
          imagePullPolicy: Always
          ports:
            - containerPort: 8084
              name: http
          env:
            - name: CHROMADB_HOST
              value: "chromadb.${NAMESPACE_KB}.svc.cluster.local"
            - name: CHROMADB_PORT
              value: "8000"
            - name: PROMETHEUS_URL
              value: "http://prometheus-operated.monitoring:9090"
          resources:
            limits:
              cpu: "1000m"
              memory: "2Gi"
            requests:
              cpu: "250m"
              memory: "512Mi"
---
apiVersion: v1
kind: Service
metadata:
  name: metrics-collector
  namespace: ${NAMESPACE_RCA}
spec:
  selector:
    app: metrics-collector
  ports:
    - port: 8084
      targetPort: 8084
      name: http
  type: ClusterIP
---
apiVersion: v1
kind: ServiceAccount
metadata:
  name: metrics-collector
  namespace: ${NAMESPACE_RCA}
EOF

    kubectl apply -f /tmp/metrics-collector-deployment.yaml
    print_status "Metrics Collector deployed"
}

# Install Grafana dashboards
install_dashboards() {
    print_status "Installing RCA Grafana dashboards..."

    # Create ConfigMaps for dashboards
    local dashboard_dir="$(dirname "$0")/../dashboards"

    if [ -d "$dashboard_dir" ]; then
        for dashboard in "$dashboard_dir"/*.json; do
            if [ -f "$dashboard" ]; then
                local name=$(basename "$dashboard" .json)
                kubectl create configmap "grafana-dashboard-$name" \
                    --from-file="$dashboard" \
                    --namespace "$NAMESPACE_MONITORING" \
                    --dry-run=client -o yaml | kubectl apply -f -
                kubectl label configmap "grafana-dashboard-$name" \
                    grafana_dashboard=1 \
                    --namespace "$NAMESPACE_MONITORING" \
                    --overwrite
            fi
        done
        print_status "Grafana dashboards installed"
    else
        print_warning "Dashboard directory not found: $dashboard_dir"
    fi
}

# Load knowledge base with initial data
load_knowledge_base() {
    print_status "Loading initial knowledge base data..."

    # Wait for ChromaDB to be ready
    kubectl wait --for=condition=ready pod -l app=chromadb -n "$NAMESPACE_KB" --timeout=120s

    # Port forward to ChromaDB
    kubectl port-forward -n "$NAMESPACE_KB" svc/chromadb 8000:8000 &
    local pf_pid=$!
    sleep 5

    # Run ingestion scripts
    python3 "$(dirname "$0")/../knowledge-base/incident_ingest.py" \
        --source "$(dirname "$0")/../../sample-incidents" \
        --chromadb-host localhost \
        --chromadb-port 8000 \
        --batch-size 50 || print_warning "Incident ingestion had issues"

    python3 "$(dirname "$0")/../knowledge-base/runbook_parser.py" \
        --source "$(dirname "$0")/../../sample-runbooks" \
        --chromadb-host localhost \
        --chromadb-port 8000 || print_warning "Runbook ingestion had issues"

    python3 "$(dirname "$0")/../knowledge-base/architecture_docs.py" \
        --source "$(dirname "$0")/../../sample-architecture" \
        --chromadb-host localhost \
        --chromadb-port 8000 || print_warning "Architecture doc ingestion had issues"

    kill $pf_pid 2>/dev/null || true

    print_status "Knowledge base loading initiated"
}

# Verify deployment
verify_deployment() {
    print_status "Verifying deployment..."

    local all_ready=true

    for deployment in rca-agent incident-command-api shadow-duel-orchestrator scenario-engine metrics-collector; do
        if kubectl get deployment "$deployment" -n "$NAMESPACE_RCA" &>/dev/null; then
            local ready=$(kubectl get deployment "$deployment" -n "$NAMESPACE_RCA" -o jsonpath='{.status.readyReplicas}')
            local desired=$(kubectl get deployment "$deployment" -n "$NAMESPACE_RCA" -o jsonpath='{.spec.replicas}')
            if [ "$ready" = "$desired" ] && [ "$ready" != "" ]; then
                print_status "$deployment: READY ($ready/$desired)"
            else
                print_warning "$deployment: NOT READY ($ready/$desired)"
                all_ready=false
            fi
        else
            print_warning "$deployment: NOT FOUND"
            all_ready=false
        fi
    done

    # Check ChromaDB
    if kubectl get deployment chromadb -n "$NAMESPACE_KB" &>/dev/null; then
        local ready=$(kubectl get deployment chromadb -n "$NAMESPACE_KB" -o jsonpath='{.status.readyReplicas}')
        if [ "$ready" = "1" ]; then
            print_status "ChromaDB: READY"
        else
            print_warning "ChromaDB: NOT READY"
            all_ready=false
        fi
    fi

    # Check Grafana
    if kubectl get deployment grafana -n "$NAMESPACE_MONITORING" &>/dev/null; then
        local ready=$(kubectl get deployment grafana -n "$NAMESPACE_MONITORING" -o jsonpath='{.status.readyReplicas}')
        if [ "$ready" = "1" ]; then
            print_status "Grafana: READY"
        else
            print_warning "Grafana: NOT READY"
            all_ready=false
        fi
    fi

    if [ "$all_ready" = true ]; then
        print_status "All components deployed successfully!"
    else
        print_warning "Some components not ready. Check pod logs for details."
    fi
}

# Print access information
print_access_info() {
    echo ""
    echo -e "${BLUE}================================================${NC}"
    echo -e "${BLUE}  Access Information${NC}"
    echo -e "${BLUE}================================================${NC}"
    echo ""
    echo "To access services, use kubectl port-forward:"
    echo ""
    echo "  # RCA Agent API"
    echo "  kubectl port-forward -n $NAMESPACE_RCA svc/rca-agent 8080:8080"
    echo ""
    echo "  # Incident Command API"
    echo "  kubectl port-forward -n $NAMESPACE_RCA svc/incident-command-api 8081:8081"
    echo ""
    echo "  # Shadow Duel Orchestrator"
    echo "  kubectl port-forward -n $NAMESPACE_RCA svc/shadow-duel-orchestrator 8082:8082"
    echo ""
    echo "  # Scenario Engine"
    echo "  kubectl port-forward -n $NAMESPACE_RCA svc/scenario-engine 8083:8083"
    echo ""
    echo "  # Metrics Collector"
    echo "  kubectl port-forward -n $NAMESPACE_RCA svc/metrics-collector 8084:8084"
    echo ""
    echo "  # ChromaDB"
    echo "  kubectl port-forward -n $NAMESPACE_KB svc/chromadb 8000:8000"
    echo ""
    echo "  # Grafana (admin/admin123)"
    echo "  kubectl port-forward -n $NAMESPACE_MONITORING svc/grafana 3000:3000"
    echo ""
    echo -e "${YELLOW}Note:${NC} Update secrets in namespace $NAMESPACE_RCA (ics-secrets) with actual credentials for Slack, PagerDuty, Zoom, StatusPage"
}

# Main execution
main() {
    echo -e "${BLUE}Starting RCA Command Stack Setup${NC}"
    echo ""

    check_prerequisites
    create_namespaces
    install_chromadb
    install_grafana
    deploy_rca_agent
    deploy_incident_command
    deploy_shadow_duel
    deploy_scenario_engine
    deploy_metrics_collector
    install_dashboards
    load_knowledge_base
    verify_deployment
    print_access_info

    echo ""
    echo -e "${GREEN}Setup complete!${NC}"
    echo ""
    echo "Next steps:"
    echo "1. Update ics-secrets with real credentials"
    echo "2. Build and push Docker images to ghcr.io/ramkannans-labs/ai-sre-rca-command/"
    echo "3. Run a Shadow Duel exercise: kubectl exec -n $NAMESPACE_RCA deploy/shadow-duel-orchestrator -- python -m simulation.shadow_duel --scenario latency-spike"
    echo "4. Access Grafana at http://localhost:3000 (after port-forward)"
}

# Run main
main "$@"