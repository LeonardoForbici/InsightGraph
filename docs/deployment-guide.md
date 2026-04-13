# Deployment Guide

## Docker Compose (Dev)
- Use root `docker-compose.yml`.
- Services: `backend`, `frontend`, `redis`, `postgres`, `neo4j`.
- Start: `docker compose up -d`.

## Kubernetes (Prod)
- Apply manifests in `k8s/` (backend deployment/service and dependencies).
- Recommended backend replicas: `3`.
- Configure readiness/liveness probes for `/api/health`.

## Monitoring Setup
- Prometheus config: `prometheus.yml`.
- Alert rules: `backend/monitoring/alert_rules.yml`.
- Grafana dashboards:
  - `backend/grafana/websocket-connections.json`
  - `backend/grafana/event-propagation-latency.json`
  - `backend/grafana/prediction-engine-accuracy.json`
  - `backend/grafana/redis-throughput.json`

## Troubleshooting
- WebSocket auth fails:
  - verify JWT secret and token expiration.
- Missing realtime updates:
  - check `/metrics` and Redis connectivity.
- Config update not applied:
  - validate payload with `/api/config` before `PUT`.
- Timeline empty:
  - ensure snapshots exist by running at least one scan.
