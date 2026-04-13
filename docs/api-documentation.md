# InsightGraph API Documentation

## OpenAPI
- FastAPI already exposes OpenAPI JSON at `/openapi.json`.
- Interactive docs: `/docs` (Swagger UI) and `/redoc`.

## Core Endpoints Added
- Real-time:
  - `GET /api/events` (SSE)
  - `GET /ws` (WebSocket)
- Collaboration:
  - `POST /api/collaboration/sessions`
  - `POST /api/collaboration/sessions/join`
  - `POST /api/collaboration/sessions/leave`
  - `POST /api/collaboration/cursor`
  - `POST /api/collaboration/select`
  - `POST /api/collaboration/annotations`
  - `GET /api/collaboration/annotations`
  - `POST /api/collaboration/chat`
  - `GET /api/collaboration/chat/{session_id}`
  - `GET /api/sessions/{session_id}/replay`
- Timeline:
  - `GET /api/graph/history?from=<ts>&to=<ts>`
  - `GET /api/graph/activity-heatmap`
- Auto Healer:
  - `POST /api/auto-healer/patterns`
  - `POST /api/auto-healer/suggest-fix`
  - `POST /api/auto-healer/generate-tests`
  - `POST /api/auto-healer/suggest-refactor`
  - `POST /api/auto-healer/documentation`
- Config:
  - `GET /api/config`
  - `PUT /api/config`

## Response Examples
- Collaboration session:
```json
{
  "session_id": "war-7d9f4f2a1b",
  "created_by": "alice",
  "participants": [{"user_id":"alice","joined_at":1744444444.1,"color":"#60a5fa"}],
  "is_active": true
}
```

- Timeline history:
```json
{
  "items": [{"id":"snap-1","commit_hash":"abc123","diff":{"added":[],"modified":[],"removed":[]}}],
  "count": 1
}
```

- Auto Healer pattern:
```json
{
  "id": "8f0c...",
  "pattern": "null-reference",
  "file_path": "src/service.ts",
  "risk_score": 78.2
}
```

