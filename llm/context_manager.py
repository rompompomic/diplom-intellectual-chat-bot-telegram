from __future__ import annotations

from dataclasses import dataclass

from storage.history import ConversationHistory


@dataclass(slots=True)
class ContextManager:
    history: ConversationHistory

    def add_user_message(self, chat_id: int, user_id: int, content: str) -> None:
        self.history.append(chat_id=chat_id, user_id=user_id, role="user", content=content)

    def add_assistant_message(self, chat_id: int, user_id: int, content: str) -> None:
        self.history.append(chat_id=chat_id, user_id=user_id, role="assistant", content=content)

    def get_context(self, chat_id: int) -> list[dict]:
        return self.history.get_recent(chat_id)
