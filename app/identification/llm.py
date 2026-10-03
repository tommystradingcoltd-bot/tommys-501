"""LLM client abstraction: real Anthropic SDK client + deterministic mock.

Prompts live in /prompts/*_vN.md (versioned). Variables are {{name}} placeholders.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Protocol

from app.config import get_settings

log = logging.getLogger(__name__)
PROMPT_DIR = Path(__file__).resolve().parent.parent.parent / "prompts"


def load_prompt(name: str, version: int = 1) -> str:
    text = (PROMPT_DIR / f"{name}_v{version}.md").read_text()
    # strip the "# name vN" header line
    return re.sub(r"^#.*\n", "", text, count=1).strip()


def render(template: str, variables: dict[str, Any]) -> str:
    out = template
    for k, v in variables.items():
        out = out.replace("{{" + k + "}}", v if isinstance(v, str) else json.dumps(v, default=str))
    return out


def extract_json(text: str) -> dict:
    """Tolerant JSON extraction (handles code fences / leading prose)."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.S)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        if m:
            return json.loads(m.group(0))
        raise


class LLMClient(Protocol):
    name: str

    def complete_json(self, prompt_name: str, variables: dict[str, Any], max_tokens: int = 2000) -> dict: ...

    def complete_text(self, prompt_name: str, variables: dict[str, Any], max_tokens: int = 2000) -> str: ...


class AnthropicLLMClient:
    """Real client using the official Anthropic Python SDK."""

    def __init__(self, api_key: str, model: str):
        import anthropic
        self._anthropic = anthropic
        self.client = anthropic.Anthropic(api_key=api_key, max_retries=3)
        self.model = model
        self.name = model

    def _call(self, prompt_name: str, variables: dict[str, Any], max_tokens: int, system: str) -> str:
        prompt = render(load_prompt(prompt_name), variables)
        try:
            resp = self.client.messages.create(
                model=self.model, max_tokens=max_tokens, system=system,
                messages=[{"role": "user", "content": prompt}],
            )
        except self._anthropic.RateLimitError as e:
            raise RuntimeError(f"Claude rate limited: {e}") from e
        except self._anthropic.APIStatusError as e:
            raise RuntimeError(f"Claude API error {e.status_code}") from e
        except self._anthropic.APIConnectionError as e:
            raise RuntimeError(f"Claude connection error: {e}") from e
        if resp.stop_reason == "refusal":
            raise RuntimeError("Claude declined the request")
        return "".join(b.text for b in resp.content if b.type == "text")

    def complete_json(self, prompt_name: str, variables: dict[str, Any], max_tokens: int = 2000) -> dict:
        text = self._call(prompt_name, variables, max_tokens, "Respond with a single JSON object and nothing else.")
        return extract_json(text)

    def complete_text(self, prompt_name: str, variables: dict[str, Any], max_tokens: int = 2000) -> str:
        return self._call(prompt_name, variables, max_tokens, "You are a concise, practical analyst. Respond in Markdown.")


class MockLLMClient:
    """Rule-based stand-in so the whole pipeline and tests run without an API key."""
    name = "mock"

    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    def complete_json(self, prompt_name: str, variables: dict[str, Any], max_tokens: int = 2000) -> dict:
        self.calls.append((prompt_name, variables))
        if prompt_name == "normalise":
            from app.identification.normaliser import rule_based_normalise
            return rule_based_normalise(variables["title"], variables.get("description", ""), variables.get("niche_config", {}))
        if prompt_name == "risk_flags":
            from app.identification.risk import rule_based_flags
            return {"flags": rule_based_flags(variables)}
        if prompt_name == "listing_copy":
            from app.inventory.listing_gen import rule_based_copy
            return rule_based_copy(variables["item"], variables.get("tests", []))
        return {}

    def complete_text(self, prompt_name: str, variables: dict[str, Any], max_tokens: int = 2000) -> str:
        self.calls.append((prompt_name, variables))
        if prompt_name == "insights":
            from app.analytics.insights import rule_based_insights
            return rule_based_insights(variables["data"])
        return ""


_client: LLMClient | None = None


def get_llm() -> LLMClient:
    global _client
    if _client is None:
        s = get_settings()
        _client = MockLLMClient() if s.llm_is_mock else AnthropicLLMClient(s.anthropic_api_key, s.claude_model)
    return _client


def set_llm(client: LLMClient | None) -> None:
    global _client
    _client = client
