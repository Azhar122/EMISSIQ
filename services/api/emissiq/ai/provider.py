"""Provider abstraction for tool-calling chat models.

Groq is primary, Ollama is the local fallback, and a scripted provider is the
last resort so a live demonstration never depends on a network. Providers are
interchangeable: they take OpenAI-style messages and tool schemas and return a
normalised response.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

import httpx

from ..config import get_settings

log = logging.getLogger(__name__)


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass
class ProviderResponse:
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    finish_reason: str = "stop"


class Provider:
    name = "base"

    def available(self) -> bool:
        raise NotImplementedError

    def chat(self, messages: list[dict], tools: list[dict] | None = None) -> ProviderResponse:
        raise NotImplementedError


def _parse_openai_style(payload: dict) -> ProviderResponse:
    choice = payload["choices"][0]
    msg = choice.get("message", {})
    calls = []
    for tc in msg.get("tool_calls") or []:
        fn = tc.get("function", {})
        raw = fn.get("arguments") or "{}"
        try:
            args = json.loads(raw) if isinstance(raw, str) else dict(raw)
        except json.JSONDecodeError:
            args = {}
        calls.append(ToolCall(id=tc.get("id", fn.get("name", "call")), name=fn.get("name", ""), arguments=args))
    return ProviderResponse(
        content=msg.get("content") or "",
        tool_calls=calls,
        finish_reason=choice.get("finish_reason", "stop"),
    )


class GroqProvider(Provider):
    name = "groq"
    URL = "https://api.groq.com/openai/v1/chat/completions"

    def __init__(self):
        s = get_settings()
        self.api_key = s.groq_api_key
        self.model = s.groq_model

    def available(self) -> bool:
        return bool(self.api_key)

    def chat(self, messages, tools=None) -> ProviderResponse:
        body = {"model": self.model, "messages": messages, "temperature": 0.1}
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"
        r = httpx.post(
            self.URL,
            headers={"Authorization": f"Bearer {self.api_key}"},
            json=body,
            timeout=45.0,
        )
        r.raise_for_status()
        return _parse_openai_style(r.json())


class OllamaProvider(Provider):
    name = "ollama"

    def __init__(self):
        s = get_settings()
        self.base = s.ollama_base_url.rstrip("/")
        self.model = s.ollama_model

    def available(self) -> bool:
        try:
            r = httpx.get(f"{self.base}/api/tags", timeout=1.5)
            return r.status_code == 200
        except Exception:
            return False

    def chat(self, messages, tools=None) -> ProviderResponse:
        body = {"model": self.model, "messages": messages, "stream": False,
                "options": {"temperature": 0.1}}
        if tools:
            body["tools"] = tools
        r = httpx.post(f"{self.base}/api/chat", json=body, timeout=120.0)
        r.raise_for_status()
        payload = r.json()
        msg = payload.get("message", {})
        calls = [
            ToolCall(
                id=f"call_{i}",
                name=tc.get("function", {}).get("name", ""),
                arguments=tc.get("function", {}).get("arguments") or {},
            )
            for i, tc in enumerate(msg.get("tool_calls") or [])
        ]
        return ProviderResponse(content=msg.get("content") or "", tool_calls=calls)


class ScriptedProvider(Provider):
    """Offline fallback.

    Walks a fixed sequence of read-only tools, then emits the final report. It
    is not an LLM and does not pretend to be — responses that come from it are
    labelled `scripted` in the stored investigation, so nobody mistakes a canned
    run for a model run.
    """

    name = "scripted"

    SEQUENCE = [
        ("get_event", {}),
        ("get_candidate_sources", {}),
        ("get_sensor_window", {}),
        ("get_weather_window", {}),
        ("get_equipment_state", {}),
        ("get_maintenance_history", {}),
        ("get_previous_events", {}),
        ("get_financial_impact", {}),
        ("get_priority_breakdown", {}),
        ("recommend_inspection", {}),
    ]

    def available(self) -> bool:
        return True

    def chat(self, messages, tools=None) -> ProviderResponse:
        allowed = {t["function"]["name"] for t in (tools or [])}
        called = {
            m.get("name")
            for m in messages
            if m.get("role") == "tool"
        }
        for name, args in self.SEQUENCE:
            if name in allowed and name not in called:
                return ProviderResponse(
                    tool_calls=[ToolCall(id=f"scripted_{name}", name=name, arguments=args)],
                    finish_reason="tool_calls",
                )
        # Evidence gathering is complete; the investigator assembles the report
        # from the tool results it already holds.
        return ProviderResponse(content="", finish_reason="stop")


def build_provider() -> Provider:
    """First available provider in the configured order."""
    registry = {"groq": GroqProvider, "ollama": OllamaProvider, "scripted": ScriptedProvider}
    for key in get_settings().provider_order:
        cls = registry.get(key)
        if not cls:
            continue
        try:
            provider = cls()
            if provider.available():
                return provider
        except Exception as exc:  # pragma: no cover - provider construction
            log.warning("provider %s unavailable: %s", key, exc)
    return ScriptedProvider()
