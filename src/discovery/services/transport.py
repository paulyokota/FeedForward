"""Conversation transport protocol and implementations.

Defines the interface that ConversationService uses to interact with
conversation storage. The Agenterminal transport wraps MCP tool calls;
the in-memory transport is for testing.
"""

import json
import logging
import os
import random
import string
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Protocol

logger = logging.getLogger(__name__)


class ConversationTransport(Protocol):
    """Protocol for conversation storage backends.

    ConversationService depends on this, not on any specific implementation.
    """

    def create_conversation(self, conversation_id: str) -> None:
        """Create a new conversation. Idempotent if it already exists."""
        ...

    def post_turn(
        self,
        conversation_id: str,
        role: str,
        text: str,
        mode: Optional[str] = None,
    ) -> str:
        """Post a turn to a conversation. Returns the turn ID."""
        ...

    def read_turns(
        self,
        conversation_id: str,
        since_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Read turns from a conversation. Returns list of turn dicts."""
        ...

    def generate_conversation_id(self) -> str:
        """Generate a new conversation ID."""
        ...


class InMemoryTransport:
    """In-memory conversation transport for testing.

    Stores conversations as lists of turn dicts in memory.
    """

    def __init__(self):
        self.conversations: Dict[str, List[Dict[str, Any]]] = {}
        self._next_id = 1

    def create_conversation(self, conversation_id: str) -> None:
        if conversation_id not in self.conversations:
            self.conversations[conversation_id] = []

    def post_turn(
        self,
        conversation_id: str,
        role: str,
        text: str,
        mode: Optional[str] = None,
    ) -> str:
        if conversation_id not in self.conversations:
            self.conversations[conversation_id] = []

        turn_id = f"turn-{self._next_id}"
        self._next_id += 1

        turn = {
            "id": turn_id,
            "role": role,
            "text": text,
            "createdAt": datetime.now(timezone.utc).isoformat(),
        }
        if mode:
            turn["mode"] = mode

        self.conversations[conversation_id].append(turn)
        return turn_id

    def read_turns(
        self,
        conversation_id: str,
        since_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        turns = self.conversations.get(conversation_id, [])

        if since_id:
            start_idx = 0
            for i, turn in enumerate(turns):
                if turn.get("id") == since_id:
                    start_idx = i + 1
                    break
            turns = turns[start_idx:]

        return turns

    def generate_conversation_id(self) -> str:
        cid = f"test-{self._next_id:04d}"
        self._next_id += 1
        return cid


class AgenterminalTransport:
    """Agenterminal-backed conversation transport.

    Reads and writes conversations via the Agenterminal NDJSON file protocol.
    This is the same format the Agenterminal MCP tools use, so conversations
    created here are visible in the Agenterminal UI.

    Does NOT depend on MCP — directly reads/writes the NDJSON files for
    use from Python services. MCP is for Claude Code agents; this is for
    the orchestration layer.
    """

    def __init__(self, conversations_dir: Optional[str] = None):
        self.conversations_dir = conversations_dir or os.path.join(
            os.path.expanduser("~"), ".agenterminal", "conversations"
        )

    def _file_path(self, conversation_id: str) -> str:
        safe_id = "".join(c for c in conversation_id if c.isalnum() or c in "_-")
        return os.path.join(self.conversations_dir, f"conversation-{safe_id}.ndjson")

    def create_conversation(self, conversation_id: str) -> None:
        os.makedirs(self.conversations_dir, exist_ok=True)
        path = self._file_path(conversation_id)
        if not os.path.exists(path):
            with open(path, "w") as f:
                pass  # Create empty file

    def post_turn(
        self,
        conversation_id: str,
        role: str,
        text: str,
        mode: Optional[str] = None,
    ) -> str:
        os.makedirs(self.conversations_dir, exist_ok=True)
        turn_id = f"conv-{int(datetime.now(timezone.utc).timestamp() * 1000)}-{''.join(random.choices(string.ascii_lowercase + string.digits, k=6))}"

        turn = {
            "id": turn_id,
            "role": role,
            "text": text,
            "createdAt": datetime.now(timezone.utc).isoformat(),
        }
        if mode:
            turn["mode"] = mode

        path = self._file_path(conversation_id)
        with open(path, "a") as f:
            f.write(json.dumps(turn) + "\n")

        return turn_id

    def read_turns(
        self,
        conversation_id: str,
        since_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        path = self._file_path(conversation_id)
        if not os.path.exists(path):
            return []

        turns = []
        with open(path, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    turns.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

        if since_id:
            start_idx = 0
            for i, turn in enumerate(turns):
                if turn.get("id") == since_id:
                    start_idx = i + 1
                    break
            turns = turns[start_idx:]

        return turns

    def generate_conversation_id(self) -> str:
        """Generate a 7-char alphanumeric ID matching Agenterminal convention."""
        chars = string.ascii_uppercase + string.digits
        return "".join(random.choices(chars, k=7))
