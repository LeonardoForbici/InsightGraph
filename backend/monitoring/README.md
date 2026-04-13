# Monitoring and Observability

## Prometheus
- Endpoint: `GET /metrics`
- Config file: `prometheus.yml`
- Alert rules: `backend/monitoring/alert_rules.yml`

## Grafana Dashboards
- WebSocket connections
- Event propagation latency
- Prediction engine traffic
- Redis throughput

## Logging
- Structured JSON logging enabled by default (`LOG_FORMAT=json`).
- Correlation IDs are injected via `CorrelationIdMiddleware`.
- Environment controls:
  - `LOG_LEVEL` (default: `INFO`)
  - `LOG_FORMAT` (`json` or `text`)
