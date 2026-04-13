"""Chat manager for collaboration war rooms."""

from __future__ import annotations

import time
import uuid
from typing import Any, Optional

from state_store import LocalStateStore


class ChatManager:
    def __init__(self, state_store: LocalStateStore):
        self.state_store = state_store

    def send_message(
        self,
        session_id: str,
        user_id: str,
        text: str,
        context: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        payload = {
            "id": str(uuid.uuid4()),
            "session_id": session_id,
            "user_id": user_id,
            "text": text,
            "context": context or {},
            "created_at": time.time(),
        }
        self.state_store.save_chat_message(payload)
        self.state_store.save_session_event(
            session_id=session_id,
            event_type="chat_message",
            payload=payload,
        )
        return payload

    def list_messages(self, session_id: str, limit: int = 200) -> list[dict[str, Any]]:
        return self.state_store.list_chat_messages(session_id=session_id, limit=limit)
