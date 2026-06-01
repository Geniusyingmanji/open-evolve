"""Minimal Azure OpenAI Responses client for local managed-identity runs."""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class AzureOpenAIConfig:
    """Configuration matching the local Codex Azure provider shape."""

    base_url: str = "https://t2vgoaigpt4o3.openai.azure.com/openai/v1"
    model: str = "gpt-5.5"
    api_version: str = "preview"
    timeout_seconds: float = 60.0
    token_env: str = "AZURE_OPENAI_AD_TOKEN"

    @classmethod
    def from_env(cls) -> "AzureOpenAIConfig":
        endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT", "").rstrip("/")
        base_url = (
            os.environ.get("OPEN_EVOLVE_AZURE_BASE_URL")
            or os.environ.get("AZURE_OPENAI_BASE_URL")
            or ("%s/openai/v1" % endpoint if endpoint else cls.base_url)
        )
        return cls(
            base_url=base_url.rstrip("/"),
            model=os.environ.get("OPEN_EVOLVE_AZURE_MODEL") or os.environ.get("AZURE_OPENAI_MODEL") or cls.model,
            api_version=os.environ.get("OPEN_EVOLVE_AZURE_API_VERSION") or cls.api_version,
            timeout_seconds=float(os.environ.get("OPEN_EVOLVE_AZURE_TIMEOUT_SECONDS", cls.timeout_seconds)),
            token_env=os.environ.get("OPEN_EVOLVE_AZURE_TOKEN_ENV") or cls.token_env,
        )


class AzureOpenAIResponsesClient:
    """Small stdlib-only client for Azure OpenAI's OpenAI-compatible Responses API."""

    def __init__(self, config: Optional[AzureOpenAIConfig] = None, token: Optional[str] = None) -> None:
        self.config = config or AzureOpenAIConfig.from_env()
        self._token = self._normalize_token(token) if token else None

    @classmethod
    def from_env(cls) -> "AzureOpenAIResponsesClient":
        return cls(config=AzureOpenAIConfig.from_env())

    def complete_text(
        self,
        prompt: str,
        system: Optional[str] = None,
        max_output_tokens: int = 512,
        temperature: Optional[float] = None,
    ) -> str:
        response = self.create_response(
            prompt=prompt,
            system=system,
            max_output_tokens=max_output_tokens,
            temperature=temperature,
        )
        return self.extract_text(response)

    def create_response(
        self,
        prompt: str,
        system: Optional[str] = None,
        max_output_tokens: int = 512,
        temperature: Optional[float] = None,
    ) -> Dict[str, Any]:
        payload = self.build_response_payload(
            prompt=prompt,
            system=system,
            max_output_tokens=max_output_tokens,
            temperature=temperature,
        )
        req = urllib.request.Request(
            self.responses_url(),
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": "Bearer %s" % self.token(),
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self.config.timeout_seconds) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def build_response_payload(
        self,
        prompt: str,
        system: Optional[str] = None,
        max_output_tokens: int = 512,
        temperature: Optional[float] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "model": self.config.model,
            "input": prompt,
            "max_output_tokens": int(max_output_tokens),
        }
        if system:
            payload["instructions"] = system
        if temperature is not None:
            payload["temperature"] = float(temperature)
        return payload

    def responses_url(self) -> str:
        query = urllib.parse.urlencode({"api-version": self.config.api_version})
        return "%s/responses?%s" % (self.config.base_url.rstrip("/"), query)

    def token(self) -> str:
        if self._token:
            return self._token
        raw = os.environ.get(self.config.token_env) or os.environ.get("AZURE_OPENAI_AD_TOKEN")
        if not raw:
            raw = os.environ.get("AZURE_OPENAI_AUTHORIZATION")
        token = self._normalize_token(raw)
        if not token:
            raise RuntimeError(
                "Missing Azure OpenAI bearer token. Expected %s or AZURE_OPENAI_AUTHORIZATION."
                % self.config.token_env
            )
        self._token = token
        return token

    @staticmethod
    def _normalize_token(raw: Optional[str]) -> str:
        if not raw:
            return ""
        token = raw.strip()
        if token.lower().startswith("bearer "):
            return token[7:].strip()
        return token

    @staticmethod
    def extract_text(response: Dict[str, Any]) -> str:
        direct = response.get("output_text")
        if isinstance(direct, str):
            return direct

        chunks = []
        output = response.get("output")
        if isinstance(output, list):
            for item in output:
                if not isinstance(item, dict):
                    continue
                content = item.get("content")
                if not isinstance(content, list):
                    continue
                for part in content:
                    if not isinstance(part, dict):
                        continue
                    text = part.get("text")
                    if isinstance(text, str):
                        chunks.append(text)
        if chunks:
            return "".join(chunks)

        choices = response.get("choices")
        if isinstance(choices, list) and choices:
            first = choices[0]
            if isinstance(first, dict):
                message = first.get("message")
                if isinstance(message, dict) and isinstance(message.get("content"), str):
                    return message["content"]
                if isinstance(first.get("text"), str):
                    return first["text"]
        return ""
