"""LLM client abstraction — Gemini-first, pluggable provider."""

from __future__ import annotations

import json
import os
from typing import Any

from pydantic import BaseModel, Field


class LLMConfig(BaseModel):
    provider: str = "gemini"
    model: str = Field(default="gemini-2.0-flash")
    api_key: str = Field(default="")
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)

    @classmethod
    def from_env(cls) -> "LLMConfig":
        return cls(
            api_key=os.environ.get("GEMINI_API_KEY", ""),
            model=os.environ.get("GEMINI_MODEL", "gemini-2.0-flash"),
            temperature=float(os.environ.get("GEMINI_TEMPERATURE", "0.2")),
        )

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key.strip())


class LLMClient:
    """Wrapper around the Gemini generative model (google-genai SDK).
    
    Provides simplified access to Gemini's content generation capabilities
    with built-in JSON response parsing and markdown fence stripping.
    """

    def __init__(self, config: LLMConfig) -> None:
        from google import genai
        from google.genai import types

        self._client = genai.Client(api_key=config.api_key)
        self._model = config.model
        self._gen_config = types.GenerateContentConfig(
            temperature=config.temperature,
        )

    def generate(self, prompt: str) -> str:
        """Generate text completion from the LLM.
        
        Args:
            prompt: The input prompt text.
            
        Returns:
            Generated text with leading/trailing whitespace removed.
        """
        response = self._client.models.generate_content(
            model=self._model,
            contents=prompt,
            config=self._gen_config,
        )
        return response.text.strip()

    def generate_json(self, prompt: str) -> dict[str, Any]:
        """Generate and parse JSON response from the LLM.
        
        Automatically strips markdown code fences (```json...```) that some
        models add around JSON responses.
        
        Args:
            prompt: The input prompt text.
            
        Returns:
            Parsed JSON as a Python dictionary.
            
        Raises:
            json.JSONDecodeError: If the response is not valid JSON after
                                   stripping markdown fences.
        """
        raw = self.generate(prompt)
        # Strip markdown code fences that some models wrap JSON responses in
        text = raw
        if text.startswith("```"):
            lines = text.splitlines()
            end = len(lines) - 1 if lines[-1].strip() == "```" else len(lines)
            text = "\n".join(lines[1:end])
        return json.loads(text)
