from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class HistoryRecord:
    chat_id: int
    user_id: int
    role: str
    content: str
    created_at: datetime


@dataclass(slots=True)
class ToolCallRecord:
    chat_id: int
    user_id: int
    tool_name: str
    args_json: str
    status: str
    result_json: str
    created_at: datetime
