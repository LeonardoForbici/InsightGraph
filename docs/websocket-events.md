# WebSocket & SSE Events

## Event Types
- `graph_updated`
- `impact_detected`
- `audit_alert`
- `scan_complete`
- `cicd_build_update`
- `collaboration_event`
- `chat_message`
- `session_replay_ready`
- `auto_healer_suggestion`

## Payload Patterns
- `collaboration_event`
  - `session_created`
  - `participant_joined`
  - `participant_left`
  - `cursor_move`
  - `node_selection`
  - `annotation_added`
- `chat_message`
  - `id`, `session_id`, `user_id`, `text`, `context`, `created_at`
- `auto_healer_suggestion`
  - `pattern_id`, `file_path`, `suggestion`

## Notes
- WebSocket endpoint uses JWT auth (`/ws?token=<jwt>` or `Authorization` header).
- Heartbeat is ping/pong with 30s default interval (hot-reloadable via `/api/config`).
