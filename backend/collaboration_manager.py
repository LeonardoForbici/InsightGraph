"""Collaboration manager for war rooms, cursors, and shared annotations."""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, asdict
from typing import Any, Optional

from redis_client import RedisClient
from state_store import LocalStateStore

logger = logging.getLogger("insightgraph.collaboration")


@dataclass
class SessionParticipant:
    user_id: str
    joined_at: float
    color: str


@dataclass
class WarRoomSession:
    session_id: str
    created_at: float
    created_by: str
    participants: list[SessionParticipant]
    active_node: Optional[str] = None
    is_active: bool = True


class CollaborationManager:
    """Manages collaboration sessions with Redis + SQLite persistence."""

    def __init__(self, state_store: LocalStateStore, redis_client: Optional[RedisClient] = None):
        self.state_store = state_store
        self.redis_client = redis_client
        self._local_sessions: dict[str, WarRoomSession] = {}
        self._cursor_palette = [
            "#60a5fa",
            "#f59e0b",
            "#a78bfa",
            "#34d399",
            "#fb7185",
            "#22d3ee",
            "#f97316",
        ]

    def create_war_room(self, session_id: str, created_by: str) -> dict[str, Any]:
        now = time.time()
        seed_color = self._cursor_palette[hash(created_by) % len(self._cursor_palette)]
        session = WarRoomSession(
            session_id=session_id,
            created_at=now,
            created_by=created_by,
            participants=[SessionParticipant(user_id=created_by, joined_at=now, color=seed_color)],
        )
        self._local_sessions[session_id] = session
        stored = self.state_store.create_collab_session(
            {
                "session_id": session_id,
                "created_by": created_by,
                "created_at": now,
                "active_node": None,
                "is_active": True,
                "participants": [asdict(p) for p in session.participants],
            }
        )
        return stored

    async def join_session(self, user_id: str, session_id: str) -> dict[str, Any]:
        session = self._local_sessions.get(session_id)
        if session is None:
            loaded = self.state_store.get_collab_session(session_id)
            if not loaded:
                raise ValueError(f"session '{session_id}' not found")
            session = WarRoomSession(
                session_id=loaded["session_id"],
                created_at=loaded["created_at"],
                created_by=loaded["created_by"],
                participants=[
                    SessionParticipant(
                        user_id=p["user_id"],
                        joined_at=float(p.get("joined_at", time.time())),
                        color=str(p.get("color") or self._cursor_palette[0]),
                    )
                    for p in loaded.get("participants", [])
                ],
                active_node=loaded.get("active_node"),
                is_active=bool(loaded.get("is_active", True)),
            )
            self._local_sessions[session_id] = session

        if not any(p.user_id == user_id for p in session.participants):
            color = self._cursor_palette[len(session.participants) % len(self._cursor_palette)]
            session.participants.append(SessionParticipant(user_id=user_id, joined_at=time.time(), color=color))
            self.state_store.update_collab_participants(session_id, [asdict(p) for p in session.participants])

        await self._persist_session_state(session)
        return self._serialize_session(session)

    async def leave_session(self, user_id: str, session_id: str) -> dict[str, Any]:
        session = self._local_sessions.get(session_id)
        if session is None:
            loaded = self.state_store.get_collab_session(session_id)
            if not loaded:
                raise ValueError(f"session '{session_id}' not found")
            session = WarRoomSession(
                session_id=loaded["session_id"],
                created_at=loaded["created_at"],
                created_by=loaded["created_by"],
                participants=[
                    SessionParticipant(
                        user_id=p["user_id"],
                        joined_at=float(p.get("joined_at", time.time())),
                        color=str(p.get("color") or self._cursor_palette[0]),
                    )
                    for p in loaded.get("participants", [])
                ],
                active_node=loaded.get("active_node"),
                is_active=bool(loaded.get("is_active", True)),
            )
            self._local_sessions[session_id] = session
        session.participants = [p for p in session.participants if p.user_id != user_id]
        if not session.participants:
            session.is_active = False
            self.state_store.close_collab_session(session_id)
        else:
            self.state_store.update_collab_participants(session_id, [asdict(p) for p in session.participants])
        await self._persist_session_state(session)
        return self._serialize_session(session)

    async def broadcast_cursor(
        self,
        session_id: str,
        user_id: str,
        position: dict[str, Any],
        selected_node: Optional[str] = None,
    ) -> dict[str, Any]:
        payload = {
            "event": "cursor_move",
            "session_id": session_id,
            "user_id": user_id,
            "position": position,
            "selected_node": selected_node,
            "timestamp": time.time(),
        }
        self.state_store.save_session_event(
            session_id=session_id,
            event_type="cursor_move",
            payload=payload,
        )
        await self._publish_collaboration_event(payload)
        return payload

    async def broadcast_selection(self, session_id: str, user_id: str, node_key: str) -> dict[str, Any]:
        payload = {
            "event": "node_selection",
            "session_id": session_id,
            "user_id": user_id,
            "node_key": node_key,
            "timestamp": time.time(),
        }
        self.state_store.update_collab_active_node(session_id, node_key)
        self.state_store.save_session_event(
            session_id=session_id,
            event_type="node_selection",
            payload=payload,
        )
        await self._publish_collaboration_event(payload)
        return payload

    async def add_annotation(
        self,
        session_id: str,
        node_key: str,
        text: str,
        user_id: str,
        visibility: str = "public",
    ) -> dict[str, Any]:
        record = self.state_store.create_collab_annotation(
            {
                "session_id": session_id,
                "node_key": node_key,
                "text": text,
                "user_id": user_id,
                "visibility": visibility,
            }
        )
        await self._publish_collaboration_event(
            {
                "event": "annotation_added",
                "session_id": session_id,
                "annotation": record,
                "timestamp": time.time(),
            }
        )
        self.state_store.save_session_event(
            session_id=session_id,
            event_type="annotation_added",
            payload=record,
        )
        return record

    def get_annotations(self, node_key: str, user_id: Optional[str] = None) -> list[dict[str, Any]]:
        return self.state_store.list_collab_annotations(node_key=node_key, user_id=user_id)

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        session = self._local_sessions.get(session_id)
        if session:
            return self._serialize_session(session)
        return self.state_store.get_collab_session(session_id)

    def list_sessions(self, active_only: bool = True) -> list[dict[str, Any]]:
        return self.state_store.list_collab_sessions(active_only=active_only)

    def get_session_replay(self, session_id: str, limit: int = 1000) -> dict[str, Any]:
        session = self.get_session(session_id)
        if not session:
            raise ValueError(f"session '{session_id}' not found")
        events = self.state_store.list_session_events(session_id, limit=limit)
        return {"session": session, "events": events}

    async def _persist_session_state(self, session: WarRoomSession) -> None:
        await self._store_redis_state(
            f"collab:session:{session.session_id}",
            json.dumps(self._serialize_session(session), ensure_ascii=False),
            ttl=24 * 3600,
        )

    async def _publish_collaboration_event(self, payload: dict[str, Any]) -> None:
        if not self.redis_client or not self.redis_client.is_available:
            return
        try:
            await self.redis_client.publish_collaboration(json.dumps(payload, ensure_ascii=False))
        except Exception as exc:
            logger.debug("Failed to publish collaboration event to Redis: %s", exc)

    async def _store_redis_state(self, key: str, value: str, ttl: int) -> None:
        if not self.redis_client or not self.redis_client.is_available:
            return
        try:
            await self.redis_client.set(key, value, ex=ttl)
        except Exception as exc:
            logger.debug("Failed to persist collaboration state in Redis: %s", exc)

    def _serialize_session(self, session: WarRoomSession) -> dict[str, Any]:
        return {
            "session_id": session.session_id,
            "created_at": session.created_at,
            "created_by": session.created_by,
            "participants": [asdict(p) for p in session.participants],
            "active_node": session.active_node,
            "is_active": session.is_active,
        }

    @staticmethod
    def new_session_id() -> str:
        return f"war-{uuid.uuid4().hex[:10]}"
