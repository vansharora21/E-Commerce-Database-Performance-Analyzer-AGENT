"""
agent/conversation_manager.py
──────────────────────────────
In-memory conversation session manager.

Each browser tab gets a unique session_id (generated client-side).
The manager stores the last N turns per session so the LLM has context
for follow-up questions like "explain that" or "compare with last week".

Architecture:
  - Pure in-memory (no DB) — fast, simple, resets on server restart
  - Max 20 sessions × 20 turns each (very small memory footprint)
  - Sessions expire after 30 minutes of inactivity
"""
from __future__ import annotations
import time
import logging
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

_MAX_SESSIONS = 20       # max concurrent sessions kept in memory
_MAX_TURNS    = 20       # turns per session (user + assistant pairs)
_SESSION_TTL  = 30 * 60  # 30 minutes inactivity timeout (seconds)


@dataclass
class Turn:
    role: str        # "user" | "assistant"
    content: str
    intent: Optional[str] = None   # the analytics intent if applicable


@dataclass
class Session:
    session_id: str
    turns: list[Turn] = field(default_factory=list)
    last_active: float = field(default_factory=time.time)

    def add(self, role: str, content: str, intent: str | None = None) -> None:
        self.turns.append(Turn(role=role, content=content, intent=intent))
        if len(self.turns) > _MAX_TURNS * 2:
            self.turns = self.turns[-_MAX_TURNS * 2:]
        self.last_active = time.time()

    def to_llm_messages(self, max_turns: int = 6) -> list[dict]:
        """Return the last N turns formatted for the LLM prompt."""
        recent = self.turns[-max_turns * 2:]
        return [{"role": t.role, "content": t.content} for t in recent]

    def last_assistant_insight(self) -> str:
        """Find the most recent assistant response (for follow-up context)."""
        for turn in reversed(self.turns):
            if turn.role == "assistant":
                return turn.content[:800]
        return ""


class ConversationManager:
    """Thread-safe (asyncio single-threaded) session store."""

    def __init__(self) -> None:
        # OrderedDict acts as an LRU cache (oldest session dropped when full)
        self._sessions: OrderedDict[str, Session] = OrderedDict()

    def get_or_create(self, session_id: str) -> Session:
        """Get existing session or create a new one. Evicts expired sessions."""
        self._evict_expired()

        if session_id in self._sessions:
            session = self._sessions[session_id]
            self._sessions.move_to_end(session_id)   # mark as recently used
            return session

        # Evict oldest if at capacity
        if len(self._sessions) >= _MAX_SESSIONS:
            oldest_id, _ = next(iter(self._sessions.items()))
            del self._sessions[oldest_id]
            logger.debug(f"Evicted oldest session: {oldest_id}")

        session = Session(session_id=session_id)
        self._sessions[session_id] = session
        logger.debug(f"Created new session: {session_id} (total: {len(self._sessions)})")
        return session

    def _evict_expired(self) -> None:
        now = time.time()
        expired = [sid for sid, s in self._sessions.items()
                   if now - s.last_active > _SESSION_TTL]
        for sid in expired:
            del self._sessions[sid]
            logger.debug(f"Session expired: {sid}")

    def clear(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)

    @property
    def active_sessions(self) -> int:
        return len(self._sessions)


# Global singleton — shared across all requests
conversation_manager = ConversationManager()
