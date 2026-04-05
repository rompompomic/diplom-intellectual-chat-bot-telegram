from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field

from storage.db import StorageDB


@dataclass(slots=True)
class ConversationHistory:
    max_messages: int
    db: StorageDB | None = None
    _memory: dict[int, deque[dict]] = field(init=False)

    def __post_init__(self) -> None:
        self._memory: dict[int, deque[dict]] = defaultdict(lambda: deque(maxlen=self.max_messages))

    def append(self, chat_id: int, user_id: int, role: str, content: str) -> None:
        self._memory[chat_id].append({"role": role, "content": content})
        if self.db is not None:
            self.db.add_history(chat_id=chat_id, user_id=user_id, role=role, content=content)

    def get_recent(self, chat_id: int) -> list[dict]:
        memory_items = list(self._memory.get(chat_id, []))
        if memory_items:
            return memory_items
        if self.db is None:
            return []
        rows = self.db.get_recent_history(chat_id=chat_id, limit=self.max_messages)
        return [{"role": row["role"], "content": row["content"]} for row in rows]
