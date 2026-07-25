import os


class LLMService:
    def __init__(self) -> None:
        self.provider = os.getenv("LLM_PROVIDER", "local").lower()
        self.model = os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini")

    def complete(self, prompt: str, context: str = "") -> str:
        if self.provider == "openai" and os.getenv("OPENAI_API_KEY"):
            from openai import OpenAI

            client = OpenAI()
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "Be concise and cite paper titles when useful."},
                    {"role": "user", "content": f"{prompt}\n\n{context}".strip()},
                ],
                temperature=0.2,
            )
            return response.choices[0].message.content or ""
        return local_response(prompt, context)


def local_response(prompt: str, context: str = "") -> str:
    prompt_lower = prompt.lower()
    if "open problem" in prompt_lower:
        return (
            "Potential gap: this cluster has strong methods and evaluation work, "
            "but fewer papers connect the findings to reproducible deployment workflows."
        )
    if "turn this path into one sentence" in prompt_lower:
        return "These papers connect through a chain of citations, similarity, and method extensions."
    if "what did paper 1 solve" in prompt_lower:
        return "Solved: a narrower technical step. Left open: broader validation. Next paper: extends the idea with a more complete setting."
    if "literature review" in prompt_lower:
        return "The topic evolves from foundational retrieval methods toward graph-aware assistants that combine structure, citations, and grounded generation."
    if "extract author" in prompt_lower:
        return "Unknown"
    if "guess the year" in prompt_lower:
        return ""
    return (
        "Based on the retrieved papers, the collection points to graph-based organization, "
        "semantic retrieval, and citation-aware reasoning as the main themes."
    )
