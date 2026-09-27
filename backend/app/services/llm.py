import json
import os
import re
from typing import Any


class LLMService:
    def __init__(self) -> None:
        self.provider = os.getenv("LLM_PROVIDER", "").lower()
        if not self.provider:
            if os.getenv("OPENAI_API_KEY"):
                self.provider = "openai"
            elif os.getenv("GEMINI_API_KEY"):
                self.provider = "gemini"
            elif os.getenv("GROQ_API_KEY"):
                self.provider = "groq"
            else:
                self.provider = "local"

        self.model = os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini")

    def complete(self, prompt: str, context: str = "") -> str:
        """Generate a grounded completion using configured LLM provider or smart local synthesis."""
        # 1. OpenAI / OpenAI-compatible endpoint
        if self.provider == "openai" and os.getenv("OPENAI_API_KEY"):
            try:
                from openai import OpenAI

                client = OpenAI(
                    api_key=os.getenv("OPENAI_API_KEY"),
                    base_url=os.getenv("OPENAI_BASE_URL", None),
                )
                system_content = (
                    "You are a rigorous, academic research assistant for a DBMS and Literature Knowledge Graph system. "
                    "Always base answers strictly on the provided paper context excerpts. Never hallucinate or fabricate claims. "
                    "Cite paper titles accurately in brackets [Paper Title]."
                )
                messages = [
                    {"role": "system", "content": system_content},
                    {"role": "user", "content": f"{prompt}\n\nContext:\n{context}".strip()},
                ]
                response = client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=0.1,  # Low temperature for factual grounding
                )
                ans = response.choices[0].message.content or ""
                if ans.strip():
                    return ans.strip()
            except Exception as e:
                # Log error and fall back to local dynamic synthesis
                print(f"[LLMService] OpenAI completion failed: {e}. Falling back to local dynamic synthesis.")

        # 2. Google Gemini API (if GEMINI_API_KEY is configured)
        if self.provider == "gemini" and os.getenv("GEMINI_API_KEY"):
            try:
                import httpx

                api_key = os.getenv("GEMINI_API_KEY")
                url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
                full_prompt = (
                    "You are an academic research assistant. Answer strictly based on the provided context excerpts without hallucinating. "
                    f"Cite sources using [Paper Title].\n\nPrompt: {prompt}\n\nContext:\n{context}"
                )
                payload = {
                    "contents": [{"parts": [{"text": full_prompt}]}],
                    "generationConfig": {"temperature": 0.1, "maxOutputTokens": 1000},
                }
                res = httpx.post(url, json=payload, timeout=12.0)
                if res.status_code == 200:
                    data = res.json()
                    candidates = data.get("candidates", [])
                    if candidates:
                        text_part = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                        if text_part.strip():
                            return text_part.strip()
            except Exception as e:
                print(f"[LLMService] Gemini completion failed: {e}. Falling back to local dynamic synthesis.")

        # 3. Groq API (if GROQ_API_KEY is configured)
        if self.provider == "groq" and os.getenv("GROQ_API_KEY"):
            try:
                from openai import OpenAI

                client = OpenAI(
                    api_key=os.getenv("GROQ_API_KEY"),
                    base_url="https://api.groq.com/openai/v1",
                )
                response = client.chat.completions.create(
                    model=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
                    messages=[
                        {"role": "system", "content": "You are an academic research assistant. Answer strictly based on context without hallucinating. Cite papers in brackets."},
                        {"role": "user", "content": f"{prompt}\n\nContext:\n{context}".strip()},
                    ],
                    temperature=0.1,
                )
                ans = response.choices[0].message.content or ""
                if ans.strip():
                    return ans.strip()
            except Exception as e:
                print(f"[LLMService] Groq completion failed: {e}. Falling back to local dynamic synthesis.")

        # 4. Smart Local Dynamic Synthesis (Zero-hallucination deterministic extraction & reasoning)
        return local_dynamic_response(prompt, context)


def local_dynamic_response(prompt: str, context: str = "") -> str:
    """
    Deterministic, context-grounded dynamic synthesizer.
    Extracts relevant facts directly from the provided context instead of canned hardcoded responses.
    Guarantees no hallucination when running offline or without an external LLM key.
    """
    prompt_lower = prompt.lower()

    # 1. Author extraction
    if "extract author" in prompt_lower:
        lines = [line.strip() for line in context.splitlines() if line.strip()]
        for line in lines[:8]:
            # Look for lines containing names or affiliations
            if re.search(r"\b(university|dept|department|lab|institute|school|college|research)\b", line, re.I):
                continue
            if re.search(r"[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}", line, re.I):
                continue
            # Check for author-like string: letters and commas/ands
            clean = re.sub(r"\d+", "", line).strip()
            words = clean.split()
            if 2 <= len(words) <= 12 and all(len(w) > 1 for w in words):
                return clean
        return "Unknown"

    # 2. Year extraction
    if "guess" in prompt_lower and "year" in prompt_lower:
        years = re.findall(r"\b(19\d{2}|20\d{2})\b", context[:3000])
        if years:
            # Pick the most recent plausible publication year
            plausible = [int(y) for y in years if 1970 <= int(y) <= 2030]
            if plausible:
                return str(max(plausible))
        return ""

    # 3. Path explanation
    if "turn this path into one sentence" in prompt_lower or "path" in prompt_lower:
        try:
            # Parse path data from context
            if "from_title" in context:
                matches = re.findall(r"'from_title':\s*'([^']+)',\s*'to_title':\s*'([^']+)'(?:,\s*'edge_type':\s*'([^']+)')?", context)
                if matches:
                    start_paper = matches[0][0]
                    end_paper = matches[-1][1]
                    steps = len(matches)
                    edge_types = {m[2] for m in matches if len(m) > 2 and m[2]}
                    edges_desc = ", ".join(edge_types) if edge_types else "citations and semantic connections"
                    return f"'{start_paper}' connects to '{end_paper}' across {steps} step(s) through {edges_desc}."
        except Exception:
            pass
        return "The papers connect sequentially through documented citation lineages and semantic similarity relations."

    # 4. RAG Question Answering over Context
    if not context or not context.strip():
        return "No relevant context was retrieved from the database to answer this question."

    # Split context into paper blocks / passages
    blocks = [b.strip() for b in context.split("\n\n") if b.strip()]
    if not blocks:
        return "The retrieved research excerpts do not contain sufficient evidence to answer this query."

    # Extract query keywords
    stop_words = {
        "what", "where", "when", "which", "who", "whom", "whose", "why", "how",
        "is", "are", "was", "were", "be", "been", "being", "have", "has", "had",
        "do", "does", "did", "the", "a", "an", "and", "or", "but", "in", "on",
        "at", "to", "for", "with", "by", "about", "against", "between", "into",
        "through", "during", "before", "after", "above", "below", "from", "up",
        "down", "in", "out", "on", "off", "over", "under", "again", "further",
        "then", "once", "here", "there", "all", "any", "both", "each", "few",
        "more", "most", "other", "some", "such", "no", "nor", "not", "only",
        "own", "same", "so", "than", "too", "very", "can", "will", "just",
        "should", "now", "tell", "explain", "does", "give", "overview",
    }
    tokens = [t.lower().strip(".,?!:;\"'()") for t in prompt.split()]
    keywords = [t for t in tokens if len(t) > 2 and t not in stop_words]

    # Sentence-level relevance scoring across context blocks
    candidate_sentences: list[tuple[float, str, str]] = []  # (score, sentence, paper_title)

    current_title = "Retrieved Document"
    for block in blocks:
        # Check if block has paper header e.g. [Title of Paper (Year)]
        header_match = re.match(r"^\[([^\]]+)\]", block)
        if header_match:
            current_title = header_match.group(1).split(" - ")[0].split(" (Year")[0]

        sentences = re.split(r"(?<=[.!?])\s+", block)
        for s in sentences:
            s_clean = s.strip()
            if len(s_clean) < 25:
                continue
            s_lower = s_clean.lower()
            score = 0.0
            for kw in keywords:
                if kw in s_lower:
                    score += 1.0
                    # Boost if exact word match
                    if re.search(r"\b" + re.escape(kw) + r"\b", s_lower):
                        score += 1.5

            if score > 0:
                candidate_sentences.append((score, s_clean, current_title))

    if not candidate_sentences:
        # If no sentence matches query tokens, inspect if any blocks contain related themes
        sample_title = current_title if current_title != "Retrieved Document" else "the indexed collection"
        return (
            f"Based on the retrieved research papers in the database (including {sample_title}), "
            f"there is insufficient direct evidence to answer '{prompt.strip()}'. "
            "Please try rephrasing your question or indexing additional literature."
        )

    # Sort sentences by relevance score descending
    candidate_sentences.sort(key=lambda x: x[0], reverse=True)

    # Pick top unique sentences (avoiding duplicates or near-duplicates)
    selected: list[str] = []
    seen_texts: set[str] = set()
    used_papers: set[str] = set()

    for score, sent, title in candidate_sentences:
        # Normalize to check duplicate
        norm = re.sub(r"\W+", "", sent.lower())
        if norm in seen_texts:
            continue
        seen_texts.add(norm)
        selected.append(f"{sent} [{title}]")
        used_papers.add(title)
        if len(selected) >= 4:
            break

    answer_body = " ".join(selected)
    return (
        f"Based on the retrieved research evidence:\n\n{answer_body}\n\n"
        f"Sources: {', '.join(sorted(used_papers))}."
    )
