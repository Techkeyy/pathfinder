"""Optional LLM narration.

The LLM never *decides* anything (rules do that in :mod:`pathfinder.classifier`);
it only turns a structured verdict into a fluent sentence and can polish a drafted
fix. Every method degrades to ``None`` if no provider/key is configured or the
call fails, so Pathfinder always runs — the deterministic text is used instead.
"""

from __future__ import annotations

from typing import Optional


class LLM:
    def __init__(self, provider: str = "none", model: str = "", api_key: Optional[str] = None):
        self.provider = provider
        self.model = model
        self.api_key = api_key

    @property
    def available(self) -> bool:
        return self.provider in {"anthropic", "openai"} and bool(self.api_key)

    def complete(self, system: str, prompt: str, max_tokens: int = 700) -> Optional[str]:
        if not self.available:
            return None
        try:
            if self.provider == "anthropic":
                return self._anthropic(system, prompt, max_tokens)
            if self.provider == "openai":
                return self._openai(system, prompt, max_tokens)
        except Exception:
            # Any SDK/network/quota problem: fall back to deterministic text.
            return None
        return None

    def _anthropic(self, system: str, prompt: str, max_tokens: int) -> str:
        import anthropic

        client = anthropic.Anthropic(api_key=self.api_key)
        msg = client.messages.create(
            model=self.model or "claude-sonnet-5",
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(block.text for block in msg.content if getattr(block, "type", "") == "text").strip()

    def _openai(self, system: str, prompt: str, max_tokens: int) -> str:
        from openai import OpenAI

        client = OpenAI(api_key=self.api_key)
        resp = client.chat.completions.create(
            model=self.model or "gpt-4o",
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
        )
        return (resp.choices[0].message.content or "").strip()
