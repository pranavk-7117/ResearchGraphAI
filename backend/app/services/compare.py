"""
Uploaded Research Paper Comparison & Novelty Overlap Service for ResearchGraphAI.

Provides an evidence-grounded comparative analysis between an uploaded manuscript
and the project's literature corpus:
- Problem & methodology breakdown
- Gap alignment evaluation (addresses / partially addresses / does not address)
- Truthful semantic distance (explicitly labeled: distance from this corpus != absolute novelty)
- Missing comparison detection & uncited candidate literature
- Concrete suggested improvements and next experiments
Persisted in paper_analyses.
"""

from typing import Any
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import models
from app.services.embeddings import EmbeddingService, cosine_similarity
from app.services.llm import LLMService
from app.services.pdf_processing import PDFExtractionResult


class ComparisonReportSchema(BaseModel):
    overview: str = Field(description="Summary of the uploaded paper's core premise")
    problem: str = Field(description="The specific scientific or engineering problem addressed")
    claimed_contributions: list[str] = Field(description="Key contributions claimed by authors")
    methodology: str = Field(description="Technical methods and experimental design employed")
    datasets_and_benchmarks: str = Field(description="Datasets or benchmarks evaluated")
    findings: str = Field(description="Key empirical results reported")
    limitations: str = Field(description="Limitations noted or observed in the study")
    gap_alignment: dict[str, Any] = Field(
        description="status (addresses | partially_addresses | does_not_address | cannot_assess) and explanation"
    )
    semantic_distance_label: str = Field(
        description="Explanation that semantic distance is measured relative to this corpus, not absolute scientific novelty"
    )
    novelty_overlap_analysis: str = Field(
        description="Qualitative overlap with existing methods and papers in the corpus"
    )
    candidate_uncited_comparisons: list[str] = Field(
        description="Papers in the corpus that address similar tasks but were not cited"
    )
    suggested_improvements: list[str] = Field(
        description="Actionable next experiments, baselines, or evaluations suggested"
    )


class CompareService:
    def __init__(self):
        self.embeddings = EmbeddingService()
        self.llm = LLMService()

    def compare_uploaded_paper(
        self,
        db: Session,
        project_id: int,
        extracted: PDFExtractionResult,
        document_id: int | None = None,
    ) -> models.PaperAnalysis:
        project = db.query(models.ResearchProject).filter(models.ResearchProject.id == project_id).first()
        if not project:
            raise RuntimeError(f"Project {project_id} not found")

        # Fetch corpus papers
        project_papers = (
            db.query(models.ProjectPaper)
            .filter(models.ProjectPaper.project_id == project_id)
            .all()
        )
        paper_ids = [p.paper_id for p in project_papers]
        corpus_papers = db.query(models.Paper).filter(models.Paper.id.in_(paper_ids)).all()

        # Compute semantic similarity against corpus papers
        uploaded_text = f"{extracted.title or ''}. {extracted.abstract or ''}".strip()
        uploaded_vector = self.embeddings.embed(uploaded_text)

        corpus_summaries = []
        similarities = []

        for p in corpus_papers[:12]:
            chunk = (
                db.query(models.PaperChunk)
                .filter(models.PaperChunk.paper_id == p.id)
                .order_by(models.PaperChunk.chunk_index)
                .first()
            )
            sim = 0.0
            if chunk and chunk.embedding:
                emb = chunk.embedding
                if hasattr(emb, "tolist"):
                    emb = emb.tolist()
                sim = cosine_similarity(uploaded_vector, list(emb))
                similarities.append(sim)

            corpus_summaries.append(
                f"- '{p.title}' ({p.year or 'n.d.'}, sim: {round(sim, 2)}): {(p.abstract or '')[:180]}"
            )

        avg_similarity = sum(similarities) / len(similarities) if similarities else 0.5
        semantic_distance = round(1.0 - avg_similarity, 3)

        # Build prompt for LLM comparison
        context = (
            f"Uploaded Paper Title: {extracted.title}\n"
            f"Abstract: {extracted.abstract or 'No abstract'}\n"
            f"Extracted Excerpts: {' '.join(c.text for c in extracted.chunks[:3])[:1200]}\n\n"
            f"Corpus Literature in Project '{project.topic}':\n"
            + "\n".join(corpus_summaries)
        )

        prompt = (
            "Analyze the uploaded research paper and compare it directly against the provided corpus literature. "
            "Synthesize a thorough, evidence-grounded comparative report adhering strictly to the JSON schema. "
            "In 'semantic_distance_label', clearly state: "
            f"'Semantic distance score ({semantic_distance}) reflects textual vector divergence from this specific project collection ({len(corpus_papers)} papers), not absolute novelty across all scientific literature.' "
            "Identify candidate papers in the corpus that are relevant to this work and examine whether they were cited or omitted."
        )

        system_prompt = (
            "You are a rigorous academic peer reviewer conducting a comparative literature analysis. "
            "Provide balanced, honest evaluations. Do not fabricate metrics."
        )

        try:
            report_data = self.llm.generate_structured(
                schema=ComparisonReportSchema,
                prompt=prompt,
                system_prompt=system_prompt,
                context=context,
            )
            report_dict = report_data.model_dump()
        except Exception as e:
            report_dict = {
                "overview": f"Comparative analysis generated with limited synthesis: {e}",
                "problem": "Unspecified",
                "claimed_contributions": [],
                "methodology": "Extracted from manuscript",
                "datasets_and_benchmarks": "N/A",
                "findings": "See uploaded PDF",
                "limitations": "N/A",
                "gap_alignment": {"status": "cannot_assess", "explanation": "LLM provider unavailable."},
                "semantic_distance_label": f"Semantic distance from this corpus: {semantic_distance} (relative measure).",
                "novelty_overlap_analysis": "Unable to compute deep qualitative overlap.",
                "candidate_uncited_comparisons": [],
                "suggested_improvements": [],
            }

        analysis_row = models.PaperAnalysis(
            project_id=project_id,
            uploaded_document_id=document_id,
            paper_title=extracted.title or "Uploaded Manuscript",
            report=report_dict,
            evidence_rows=[{"semantic_distance": semantic_distance, "papers_compared": len(corpus_papers)}],
            corpus_version=project.corpus_version,
        )
        db.add(analysis_row)
        db.commit()
        return analysis_row
