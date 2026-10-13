import os
from collections import defaultdict
from pathlib import Path

from app import models
from app.corpus_data import DOMAINS_DATA
from app.database import SessionLocal, init_db
from app.generate_papers_pdf import generate_all_pdfs
from app.services.embeddings import EmbeddingService, cosine_similarity, decode_embedding, encode_embedding


def add_keyword(keyword_cache: dict[str, models.Keyword], text: str) -> models.Keyword:
    clean_text = text.strip()
    keyword = keyword_cache.get(clean_text)
    if keyword is None:
        keyword = models.Keyword(text=clean_text)
        keyword_cache[clean_text] = keyword
    return keyword


def add_edge(db, source: int, target: int, edge_type: str, label: str, confidence: float) -> None:
    db.add(
        models.Edge(
            source_paper_id=source,
            target_paper_id=target,
            edge_type=edge_type,
            relation_label=label,
            confidence=round(confidence, 3),
        )
    )


def seed_database(reset: bool = True) -> None:
    init_db()
    db = SessionLocal()
    embeddings = EmbeddingService()

    # Ensure PDFs are also generated on disk
    try:
        generate_all_pdfs()
    except Exception as e:
        print(f"Warning: PDF generation failed during seed: {e}")

    try:
        if reset:
            db.query(models.ChatHistory).delete()
            db.query(models.PaperChunk).delete()
            db.query(models.Edge).delete()
            db.query(models.PaperKeyword).delete()
            db.query(models.Keyword).delete()
            db.query(models.Paper).delete()
            db.commit()

        keyword_cache: dict[str, models.Keyword] = {}
        paper_key_to_id: dict[str, int] = {}
        domain_papers: dict[str, list[models.Paper]] = defaultdict(list)

        for domain_info in DOMAINS_DATA:
            domain_name = domain_info["domain"]
            for p_data in domain_info["papers"]:
                sections_text = "\n\n".join(
                    f"{sec_title.upper()}:\n{sec_content}"
                    for sec_title, sec_content in p_data["sections"].items()
                )
                full_body = (
                    f"{p_data['title']}\n"
                    f"Authors: {p_data['authors']}\n"
                    f"Domain: {domain_name}\n"
                    f"Year: {p_data['year']}\n\n"
                    f"ABSTRACT:\n{p_data['abstract']}\n\n"
                    f"{sections_text}"
                )

                whole_emb = embeddings.embed(f"{p_data['title']}\n{p_data['abstract']}")

                paper = models.Paper(
                    title=p_data["title"],
                    authors=p_data["authors"],
                    abstract=p_data["abstract"],
                    year=p_data["year"],
                    source_type="indexed",
                    full_text=full_body,
                    whole_embedding=encode_embedding(whole_emb),
                )

                # Attach domain and specific keywords
                all_kws = set(p_data["keywords"]) | {domain_name}
                for kw_text in sorted(all_kws):
                    paper.keywords.append(add_keyword(keyword_cache, kw_text))

                db.add(paper)
                db.flush()

                paper_key_to_id[p_data["id_key"]] = paper.id
                domain_papers[domain_name].append(paper)

                # Store distinct structured chunks for dense RAG retrieval
                chunks_to_index = [
                    f"[Abstract & Overview] {p_data['title']}: {p_data['abstract']}",
                    f"[Methodology & Design] {p_data['title']}: {p_data['sections'].get('Methodology', '')}",
                    f"[Results & Evaluation] {p_data['title']}: {p_data['sections'].get('Results', '')}",
                    f"[Limitations & Trade-offs] {p_data['title']}: {p_data['sections'].get('Limitations', '')}",
                ]

                for chunk_idx, chunk_text in enumerate(chunks_to_index):
                    chunk_emb = embeddings.embed(chunk_text)
                    db.add(
                        models.PaperChunk(
                            paper_id=paper.id,
                            chunk_index=chunk_idx,
                            text=chunk_text,
                            embedding=encode_embedding(chunk_emb),
                        )
                    )

        # Build Intra-Domain graph edges (citations, method extension lineage, similarity)
        for domain_name, papers in domain_papers.items():
            for i in range(len(papers) - 1):
                cur_p = papers[i]
                nxt_p = papers[i + 1]
                # Chronological / method extension edge
                add_edge(db, cur_p.id, nxt_p.id, "semantic_relation", "extends", 0.88 + (i * 0.02))
                # Citation edge: next paper cites previous paper
                add_edge(db, nxt_p.id, cur_p.id, "citation", "cites", 0.92)

            # Intra-domain embedding similarity edges
            for i in range(len(papers)):
                for j in range(i + 1, len(papers)):
                    emb_a = decode_embedding(papers[i].whole_embedding)
                    emb_b = decode_embedding(papers[j].whole_embedding)
                    sim = cosine_similarity(emb_a, emb_b)
                    if sim > 0.65:
                        add_edge(db, papers[i].id, papers[j].id, "similarity", "similar", sim)
                        add_edge(db, papers[j].id, papers[i].id, "similarity", "similar", sim)

        # Cross-Domain Bridge Edges
        cross_bridges = [
            ("ai_1", "iot_5", "semantic_relation", "applies_agent_planning_in_iot", 0.82),
            ("ml_4", "iot_1", "semantic_relation", "quantization_for_edge_sensing", 0.87),
            ("ml_3", "nlp_2", "similarity", "dense_embedding_alignment", 0.79),
            ("nlp_1", "ai_3", "citation", "cites_factuality_verification", 0.89),
            ("ml_2", "sec_5", "citation", "cites_federated_optimization", 0.91),
            ("sec_3", "ai_2", "semantic_relation", "applies_graph_reasoning_in_security", 0.84),
            ("nlp_4", "sec_2", "similarity", "verifiable_retrieval_querying", 0.76),
            ("iot_3", "sec_1", "citation", "cites_robustness_defenses", 0.85),
        ]

        for src_key, tgt_key, etype, elabel, conf in cross_bridges:
            if src_key in paper_key_to_id and tgt_key in paper_key_to_id:
                src_id = paper_key_to_id[src_key]
                tgt_id = paper_key_to_id[tgt_key]
                add_edge(db, src_id, tgt_id, etype, elabel, conf)

        db.commit()
        print(f"Successfully seeded database with {len(paper_key_to_id)} multi-domain papers and {db.query(models.Edge).count()} edges.")
    finally:
        db.close()


def seed_if_empty() -> None:
    init_db()
    db = SessionLocal()
    try:
        if db.query(models.Paper).count() == 0:
            db.close()
            seed_database(reset=False)
    finally:
        if db.is_active:
            db.close()


def main() -> None:
    seed_database(reset=True)


if __name__ == "__main__":
    main()
