# User Guide

## Installation
1. Start services with Docker Compose:
   - `docker compose up -d redis postgres neo4j backend frontend`
2. Open frontend at `http://localhost:5173`.
3. Validate backend health at `http://localhost:8000/api/health`.

## Dashboard de Pulso
- Use **Pulse** in top navigation.
- Metrics auto-refresh every 30 seconds.
- Watch alerts for high risk score and active developers.

## War Rooms (Collaboration)
1. Open **War Room** button in the app.
2. Create or join a session.
3. Chat with participants and add node annotations.
4. Replay a session using `/api/sessions/{id}/replay`.

## Gesture Control
1. Enable gesture flag in runtime config (`feature_flags.enable_gesture_control`).
2. Click **Gesture ON**.
3. Allow webcam permission.
4. Use sensitivity slider to calibrate cursor behavior.
