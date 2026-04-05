from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable

from openai import OpenAI


@dataclass(slots=True)
class LLMResponse:
    text: str
    used_model: str | None
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


ToolExecutor = Callable[[str, dict[str, Any]], dict[str, Any]]


class OpenAIOrchestrator:
    def __init__(
        self,
        api_key: str,
        primary_model: str,
        secondary_model: str,
        fallback_model: str,
        system_prompt: str,
        max_turn_tool_calls: int = 8,
    ) -> None:
        self.system_prompt = system_prompt
        self.max_turn_tool_calls = max_turn_tool_calls
        self.models = [primary_model, secondary_model, fallback_model]
        self.client = OpenAI(api_key=api_key) if api_key else None

    def is_enabled(self) -> bool:
        return self.client is not None

    def respond(
        self,
        chat_context: list[dict[str, str]],
        user_text: str,
        tools: list[dict],
        tool_executor: ToolExecutor,
    ) -> LLMResponse:
        if self.client is None:
            return LLMResponse(
                text="LLM недоступен: OPENAI_API_KEY не задан.",
                used_model=None,
                errors=["OPENAI_API_KEY is missing."],
            )

        errors: list[str] = []
        for model in self._iter_models():
            try:
                return self._respond_single_model(
                    model=model,
                    chat_context=chat_context,
                    user_text=user_text,
                    tools=tools,
                    tool_executor=tool_executor,
                )
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{model}: {exc}")

        return LLMResponse(
            text="Не удалось получить ответ от OpenAI API. Проверьте ключ, модель и сетевое соединение.",
            used_model=None,
            errors=errors,
        )

    def _respond_single_model(
        self,
        model: str,
        chat_context: list[dict[str, str]],
        user_text: str,
        tools: list[dict],
        tool_executor: ToolExecutor,
    ) -> LLMResponse:
        input_items = [{"role": "system", "content": self.system_prompt}]
        input_items.extend(chat_context)
        input_items.append({"role": "user", "content": user_text})

        response = self.client.responses.create(
            model=model,
            input=input_items,
            tools=tools,
        )

        all_tool_calls: list[dict[str, Any]] = []
        for _ in range(self.max_turn_tool_calls):
            function_calls = [item for item in response.output if item.type == "function_call"]
            if not function_calls:
                break

            tool_outputs = []
            for call in function_calls:
                try:
                    parsed_args = json.loads(call.arguments or "{}")
                except json.JSONDecodeError:
                    parsed_args = {}

                result = tool_executor(call.name, parsed_args)
                all_tool_calls.append({"name": call.name, "args": parsed_args, "result": result})
                tool_outputs.append(
                    {
                        "type": "function_call_output",
                        "call_id": call.call_id,
                        "output": json.dumps(result, ensure_ascii=False),
                    }
                )

            response = self.client.responses.create(
                model=model,
                previous_response_id=response.id,
                input=tool_outputs,
                tools=tools,
            )

        text = self._extract_text(response)
        return LLMResponse(text=text, used_model=model, tool_calls=all_tool_calls)

    def _iter_models(self) -> list[str]:
        seen: set[str] = set()
        ordered: list[str] = []
        for model in self.models:
            model = (model or "").strip()
            if not model or model in seen:
                continue
            seen.add(model)
            ordered.append(model)
        return ordered

    @staticmethod
    def _extract_text(response: Any) -> str:
        output_text = getattr(response, "output_text", "")
        if output_text:
            return str(output_text).strip()

        collected: list[str] = []
        for item in getattr(response, "output", []):
            if item.type != "message":
                continue
            for content_item in getattr(item, "content", []):
                text = getattr(content_item, "text", None)
                if text:
                    collected.append(str(text))
        return "\n".join(collected).strip() or "Готово."
