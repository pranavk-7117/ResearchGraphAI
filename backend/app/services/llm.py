"""
Multi-provider LLM Layer for ResearchGraphAI.

Supports Groq, OpenAI, Anthropic, and Google Gemini with:
- Model names and settings loaded from environment
- JSON-schema-validated structured outputs with Pydantic
- Post-validation of citations against actual retrieved passage chunks
- Transparent failure reporting (zero silent heuristic fallbacks)
"""

import json
import os
import re
from typing import Any, TypeVar
import httpx
from pydantic import BaseModel, ValidationError
from rapidfuzz import fuzz

T = TypeVar("T", bound=BaseModel)


class LLMProviderUnavailableError(RuntimeError):
    """Raised when the configured LLM provider cannot be reached or is unconfigured."""
    pass


class LLMService:
    def __init__(self) -> None:
        self.provider = os.getenv("LLM_PROVIDER", "").lower()
        if not self.provider:
            if os.getenv("GROQ_API_KEY"):
                self.provider = "groq"
            elif os.getenv("OPENAI_API_KEY"):
                self.provider = "openai"
            elif os.getenv("ANTHROPIC_API_KEY"):
                self.provider = "anthropic"
            elif os.getenv("GEMINI_API_KEY"):
                self.provider = "gemini"
            else:
                self.provider = "none"

        self.groq_api_key = os.getenv("GROQ_API_KEY")
        self.groq_model = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")

        self.openai_api_key = os.getenv("OPENAI_API_KEY")
        self.openai_model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

        self.anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
        self.anthropic_model = os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022")

        self.gemini_api_key = os.getenv("GEMINI_API_KEY")
        self.gemini_model = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")

    def is_available(self) -> bool:
        if self.provider == "groq" and self.groq_api_key:
            return True
        if self.provider == "openai" and self.openai_api_key:
            return True
        if self.provider == "anthropic" and self.anthropic_api_key:
            return True
        if self.provider == "gemini" and self.gemini_api_key:
            return True
        return False

    def complete(self, prompt: str, system_prompt: str = "", context: str = "") -> str:
        """Execute a text completion across the configured LLM provider."""
        if not self.is_available():
            raise LLMProviderUnavailableError(
                f"LLM provider '{self.provider}' is not configured with a valid API key. "
                "Please configure GROQ_API_KEY, OPENAI_API_KEY, ANTHROPIC_API_KEY, or GEMINI_API_KEY in backend/.env"
            )

        full_prompt = f"{prompt}\n\nContext:\n{context}".strip() if context else prompt

        # 1. Groq
        if self.provider == "groq":
            return self._call_groq(full_prompt, system_prompt)

        # 2. OpenAI
        if self.provider == "openai":
            return self._call_openai(full_prompt, system_prompt)

        # 3. Anthropic
        if self.provider == "anthropic":
            return self._call_anthropic(full_prompt, system_prompt)

        # 4. Gemini
        if self.provider == "gemini":
            return self._call_gemini(full_prompt, system_prompt)

        raise LLMProviderUnavailableError(f"Unsupported LLM provider: {self.provider}")

    def generate_structured(
        self,
        schema: type[T],
        prompt: str,
        system_prompt: str = "",
        context: str = "",
        retries: int = 2,
    ) -> T:
        """
        Generate JSON output validated strictly against a Pydantic schema.
        Retries on validation failure with error feedback.
        """
        json_schema_str = json.dumps(schema.model_json_schema(), indent=2)
        instructions = (
            f"{system_prompt}\n\n"
            "CRITICAL: You must reply strictly with a valid JSON object conforming to the following JSON Schema. "
            "Do NOT include any markdown code blocks (```json), preamble, or commentary outside the JSON:\n"
            f"{json_schema_str}"
        )

        last_error = None
        current_prompt = prompt

        for attempt in range(retries + 1):
            raw_text = self.complete(current_prompt, system_prompt=instructions, context=context)
            # Clean markdown formatting if present
            cleaned = raw_text.strip()
            if cleaned.startswith("```"):
                lines = cleaned.splitlines()
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                cleaned = "\n".join(lines).strip()

            try:
                data = json.loads(cleaned)
                return schema.model_validate(data)
            except (json.JSONDecodeError, ValidationError) as e:
                last_error = e
                current_prompt = (
                    f"{prompt}\n\n"
                    f"PREVIOUS ATTEMPT FAILED VALIDATION: {e}\n"
                    f"Please output strictly valid JSON conforming to the schema."
                )

        raise RuntimeError(f"Failed to produce valid structured output for {schema.__name__}: {last_error}")

    # ==========================================================================
    # Provider Implementations
    # ==========================================================================

    def _call_groq(self, prompt: str, system_prompt: str) -> str:
        headers = {
            "Authorization": f"Bearer {self.groq_api_key}",
            "Content-Type": "application/json",
        }
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.groq_model,
            "messages": messages,
            "temperature": 0.1,
            "max_tokens": 1500,
        }

        with httpx.Client(timeout=45.0) as client:
            resp = client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers=headers,
                json=payload,
            )
            # If rate limit on gpt-oss-120b, fall back to gpt-oss-20b
            if resp.status_code == 429 and self.groq_model != "openai/gpt-oss-20b":
                payload["model"] = "openai/gpt-oss-20b"
                payload["max_tokens"] = 1200
                resp = client.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers=headers,
                    json=payload,
                )

            if resp.status_code != 200:
                raise LLMProviderUnavailableError(
                    f"Groq API error ({resp.status_code}): {resp.text}"
                )
            data = resp.json()
            return data["choices"][0]["message"]["content"]

    def _call_openai(self, prompt: str, system_prompt: str) -> str:
        headers = {
            "Authorization": f"Bearer {self.openai_api_key}",
            "Content-Type": "application/json",
        }
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.openai_model,
            "messages": messages,
            "temperature": 0.1,
        }

        with httpx.Client(timeout=45.0) as client:
            resp = client.post(
                "https://api.openai.com/v1/chat/completions",
                headers=headers,
                json=payload,
            )
            if resp.status_code != 200:
                raise LLMProviderUnavailableError(
                    f"OpenAI API error ({resp.status_code}): {resp.text}"
                )
            data = resp.json()
            return data["choices"][0]["message"]["content"]

    def _call_anthropic(self, prompt: str, system_prompt: str) -> str:
        headers = {
            "x-api-key": self.anthropic_api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.anthropic_model,
            "max_tokens": 4096,
            "temperature": 0.1,
            "system": system_prompt,
            "messages": [{"role": "user", "content": prompt}],
        }
        with httpx.Client(timeout=45.0) as client:
            resp = client.post(
                "https://api.anthropic.com/v1/messages",
                headers=headers,
                json=payload,
            )
            if resp.status_code != 200:
                raise LLMProviderUnavailableError(
                    f"Anthropic API error ({resp.status_code}): {resp.text}"
                )
            data = resp.json()
            return data["content"][0]["text"]

    def _call_gemini(self, prompt: str, system_prompt: str) -> str:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.gemini_model}:generateContent?key={self.gemini_api_key}"
        full_text = f"{system_prompt}\n\n{prompt}".strip() if system_prompt else prompt
        payload = {
            "contents": [{"parts": [{"text": full_text}]}],
            "generationConfig": {"temperature": 0.1, "maxOutputTokens": 4096},
        }
        with httpx.Client(timeout=45.0) as client:
            resp = client.post(url, json=payload)
            if resp.status_code != 200:
                raise LLMProviderUnavailableError(
                    f"Gemini API error ({resp.status_code}): {resp.text}"
                )
            data = resp.json()
            return data["candidates"][0]["content"]["parts"][0]["text"]


def post_validate_citation(quote: str, chunk_text: str, threshold: float = 75.0) -> bool:
    """
    Validate that an extracted quote actually appears in the retrieved passage chunk.
    Uses exact substring matching or fuzzy token similarity.
    """
    if not quote or not chunk_text:
        return False
    clean_quote = " ".join(quote.split()).lower()
    clean_chunk = " ".join(chunk_text.split()).lower()
    if clean_quote in clean_chunk:
        return True
    return fuzz.partial_ratio(clean_quote, clean_chunk) >= threshold
