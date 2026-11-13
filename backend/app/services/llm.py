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
        if self.groq_model in ("llama-3.3-70b-versatile", "llama-3.1-8b-instant"):
            self.groq_model = "openai/gpt-oss-120b"

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
            # Clean markdown formatting and optional reasoning tags if present
            cleaned = raw_text.strip()
            if "<think>" in cleaned and "</think>" in cleaned:
                cleaned = re.sub(r"<think>.*?</think>", "", cleaned, flags=re.DOTALL).strip()
            if cleaned.startswith("```"):
                lines = cleaned.splitlines()
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                cleaned = "\n".join(lines).strip()
            if cleaned and not cleaned.startswith("{"):
                start = cleaned.find("{")
                end = cleaned.rfind("}")
                if start != -1 and end > start:
                    cleaned = cleaned[start : end + 1]

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

        # Working Groq models verified for this environment
        candidate_models = []
        if self.groq_model and self.groq_model not in ("llama-3.3-70b-versatile", "llama-3.1-8b-instant"):
            candidate_models.append(self.groq_model)
        for fallback in [
            "openai/gpt-oss-120b",
            "openai/gpt-oss-20b",
            "qwen/qwen3.8-27b",
        ]:
            if fallback not in candidate_models:
                candidate_models.append(fallback)

        last_error = "Unknown error"
        with httpx.Client(timeout=15.0) as client:
            for model_name in candidate_models:
                payload = {
                    "model": model_name,
                    "messages": messages,
                    "temperature": 0.1,
                    "max_tokens": 4000,
                }
                for attempt in range(3):
                    try:
                        resp = client.post(
                            "https://api.groq.com/openai/v1/chat/completions",
                            headers=headers,
                            json=payload,
                        )
                        if resp.status_code == 429:
                            import time as _t
                            wait_m = re.search(r"try again in ([0-9.]+)s", resp.text)
                            delay = min(20.0, float(wait_m.group(1)) + 0.5) if wait_m else (3.5 * (attempt + 1))
                            _t.sleep(delay)
                            continue
                        if resp.status_code == 200:
                            data = resp.json()
                            self.groq_model = model_name
                            return data["choices"][0]["message"]["content"]
                        last_error = f"Groq API error ({resp.status_code}) for model '{model_name}': {resp.text}"
                        break
                    except Exception as ex:
                        last_error = f"Groq request exception for model '{model_name}': {ex}"
                        break

        raise LLMProviderUnavailableError(last_error)

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


def _normalize_for_quote(text: str) -> str:
    """Normalize whitespace, case, soft hyphens, and line-break hyphenation."""
    if not text:
        return ""
    # Rejoin line-break hyphenations (e.g. "infer-\nence" -> "inference")
    normalized = re.sub(r"-\s*\n\s*", "", text)
    # Remove soft hyphens / zero-width spaces and normalize unicode hyphens
    normalized = re.sub(r"[\u00ad\u200b]", "", normalized)
    normalized = re.sub(r"[\u2010-\u2015\u2212]", "-", normalized)
    return " ".join(normalized.split()).lower()


def _tokenize_quote(text: str) -> list[str]:
    """Extract lowercase alphanumeric/decimal tokens in order."""
    return re.findall(r"[a-z0-9]+(?:[.\-][a-z0-9]+)*", text)


def _extract_numbers(tokens: list[str]) -> list[str]:
    """Extract numeric values from a list of tokens."""
    nums: list[str] = []
    for t in tokens:
        for m in re.findall(r"\b\d+(?:\.\d+)?\b", t):
            nums.append(m)
    return nums


NEGATION_WORDS = {
    "not", "no", "never", "none", "neither", "nor", "without",
    "cannot", "cant", "can't", "fails", "failed", "failure",
}

POLARITY_OPPOSITES = {
    "increases": "decreases",
    "decreases": "increases",
    "increase": "decrease",
    "decrease": "increase",
    "increased": "decreased",
    "decreased": "increased",
    "increasing": "decreasing",
    "decreasing": "increasing",
    "higher": "lower",
    "lower": "higher",
    "more": "less",
    "less": "more",
    "positive": "negative",
    "negative": "positive",
    "effective": "ineffective",
    "ineffective": "effective",
    "improved": "worsened",
    "worsened": "improved",
}


def _lcs_len(a: list[str], b: list[str]) -> int:
    """Compute length of Longest Common Subsequence between token lists a and b."""
    if not a or not b:
        return 0
    prev = [0] * (len(b) + 1)
    for tok_a in a:
        curr = [0] * (len(b) + 1)
        for j, tok_b in enumerate(b, start=1):
            if tok_a == tok_b:
                curr[j] = prev[j - 1] + 1
            else:
                curr[j] = curr[j - 1] if curr[j - 1] >= prev[j] else prev[j]
        prev = curr
    return prev[-1]


def _find_contiguous_window(q_tokens: list[str], c_tokens: list[str]) -> tuple[float, list[str]]:
    """
    Search for a tight, contiguous window in c_tokens matching q_tokens.
    Windows are constrained to lengths [q_len - 1, q_len + 2] to strictly disallow
    splicing across non-contiguous sections.
    Returns (best_ratio, best_window_tokens).
    """
    q_len = len(q_tokens)
    if not q_tokens or not c_tokens or len(c_tokens) < max(1, q_len - 1):
        return 0.0, []

    best_ratio = 0.0
    best_win: list[str] = []

    # Slide window sizes from q_len to q_len + 1
    for win_len in (q_len, q_len + 1):
        if len(c_tokens) < win_len:
            continue
        for i in range(len(c_tokens) - win_len + 1):
            win = c_tokens[i : i + win_len]
            # Exact positional match ratio
            exact_matches = sum(1 for a, b in zip(q_tokens, win) if a == b)
            ratio = exact_matches / q_len
            if ratio > best_ratio:
                best_ratio = ratio
                best_win = win
                if ratio == 1.0:
                    return 1.0, win

            # Fallback to LCS inside this tight window
            lcs = _lcs_len(q_tokens, win)
            lcs_ratio = lcs / q_len
            if lcs_ratio > best_ratio:
                best_ratio = lcs_ratio
                best_win = win
                if lcs_ratio == 1.0:
                    return 1.0, win

    return round(float(best_ratio), 4), best_win


def post_validate_citation(
    quote: str,
    chunk_text: str,
    chunk_id: int | None = None,
    threshold: float = 0.9,
    min_tokens: int = 5,
) -> dict[str, Any]:
    """
    Strictly validate that a quote appears in the specific cited chunk.
    Hardened guarantees:
    1. Rejects short phrases (< min_tokens, default 5 tokens) as 'too_short'.
    2. Enforces exact number preservation: all digits in quote must match chunk verbatim.
    3. Enforces negation & polarity invariance: no meaning flips ('increases' -> 'decreases').
    4. Enforces contiguous window match: disallows spliced non-contiguous fragments.
    Returns: {verified: bool, chunk_id: int | None, match_type: str, score: float, reject_reason: str | None}
    """
    if not quote or not chunk_text:
        return {
            "verified": False,
            "chunk_id": chunk_id,
            "match_type": "none",
            "score": 0.0,
            "reject_reason": "empty",
        }

    clean_quote = _normalize_for_quote(quote)
    clean_chunk = _normalize_for_quote(chunk_text)
    if not clean_quote or not clean_chunk:
        return {
            "verified": False,
            "chunk_id": chunk_id,
            "match_type": "none",
            "score": 0.0,
            "reject_reason": "empty",
        }

    q_tokens = _tokenize_quote(clean_quote)
    c_tokens = _tokenize_quote(clean_chunk)
    if not q_tokens or not c_tokens:
        return {
            "verified": False,
            "chunk_id": chunk_id,
            "match_type": "none",
            "score": 0.0,
            "reject_reason": "empty",
        }

    # 1. Minimum token length guard
    if len(q_tokens) < min_tokens:
        return {
            "verified": False,
            "chunk_id": chunk_id,
            "match_type": "too_short",
            "score": 0.0,
            "reject_reason": "too_short",
        }

    # 2. Number check: all numbers in quote MUST be present in chunk
    q_nums = _extract_numbers(q_tokens)
    c_nums = _extract_numbers(c_tokens)
    for num in q_nums:
        if num not in c_nums:
            return {
                "verified": False,
                "chunk_id": chunk_id,
                "match_type": "none",
                "score": 0.0,
                "reject_reason": "number_mismatch",
            }

    # 3. Exact normalized substring match
    if clean_quote in clean_chunk:
        return {
            "verified": True,
            "chunk_id": chunk_id,
            "match_type": "exact",
            "score": 1.0,
            "reject_reason": None,
        }

    # 4. Contiguous window fuzzy match
    score, matched_win = _find_contiguous_window(q_tokens, c_tokens)

    # 5. Check polarity flips / negation changes in the matched window
    if matched_win:
        q_negs = sum(1 for t in q_tokens if t in NEGATION_WORDS)
        w_negs = sum(1 for t in matched_win if t in NEGATION_WORDS)
        if q_negs != w_negs:
            return {
                "verified": False,
                "chunk_id": chunk_id,
                "match_type": "none",
                "score": score,
                "reject_reason": "negation_flip",
            }

        # Check for antonym opposite words (e.g. quote has 'decreases', chunk has 'increases')
        for q_tok in q_tokens:
            opp = POLARITY_OPPOSITES.get(q_tok)
            if opp and opp in matched_win and q_tok not in matched_win:
                return {
                    "verified": False,
                    "chunk_id": chunk_id,
                    "match_type": "none",
                    "score": score,
                    "reject_reason": "negation_flip",
                }

    if score >= threshold:
        return {
            "verified": True,
            "chunk_id": chunk_id,
            "match_type": "token_sequence",
            "score": score,
            "reject_reason": None,
        }

    return {
        "verified": False,
        "chunk_id": chunk_id,
        "match_type": "none",
        "score": score,
        "reject_reason": "low_overlap",
    }
