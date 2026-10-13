import os
import re
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import HRFlowable, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.corpus_data import DOMAINS_DATA


def sanitize_filename(title: str) -> str:
    # Keep alphanumeric and dashes, clean up
    clean = re.sub(r"[^\w\s-]", "", title)
    clean = re.sub(r"[\s]+", "_", clean).strip("_")
    return clean[:70] + ".pdf"


def generate_all_pdfs(base_dir: Path | None = None) -> list[Path]:
    if base_dir is None:
        base_dir = Path(__file__).resolve().parents[2] / "research_papers"

    base_dir.mkdir(parents=True, exist_ok=True)
    generated_files: list[Path] = []

    styles = getSampleStyleSheet()

    # Custom academic styles
    title_style = ParagraphStyle(
        "AcademicTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=15,
        leading=19,
        alignment=1,  # Centered
        textColor=colors.HexColor("#0f172a"),
        spaceAfter=8,
    )

    authors_style = ParagraphStyle(
        "AcademicAuthors",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9.5,
        leading=13,
        alignment=1,  # Centered
        textColor=colors.HexColor("#334155"),
        spaceAfter=4,
    )

    journal_header_style = ParagraphStyle(
        "JournalHeader",
        parent=styles["Normal"],
        fontName="Helvetica-Oblique",
        fontSize=8,
        leading=10,
        alignment=1,
        textColor=colors.HexColor("#64748b"),
        spaceAfter=12,
    )

    abstract_heading = ParagraphStyle(
        "AbstractHeading",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=9.5,
        leading=12,
        textColor=colors.HexColor("#0f172a"),
        spaceAfter=4,
    )

    abstract_text_style = ParagraphStyle(
        "AbstractText",
        parent=styles["Normal"],
        fontName="Times-Italic",
        fontSize=8.5,
        leading=11.5,
        textColor=colors.HexColor("#1e293b"),
        spaceAfter=4,
    )

    keywords_style = ParagraphStyle(
        "KeywordsText",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8,
        leading=10.5,
        textColor=colors.HexColor("#334155"),
    )

    section_heading_style = ParagraphStyle(
        "SectionHeading",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=10.5,
        leading=13,
        textColor=colors.HexColor("#1e3a8a"),
        spaceBefore=10,
        spaceAfter=4,
    )

    body_text_style = ParagraphStyle(
        "AcademicBody",
        parent=styles["Normal"],
        fontName="Times-Roman",
        fontSize=8.5,
        leading=11.5,
        textColor=colors.HexColor("#0f172a"),
        spaceAfter=6,
    )

    ref_style = ParagraphStyle(
        "AcademicRef",
        parent=styles["Normal"],
        fontName="Times-Roman",
        fontSize=7.5,
        leading=9.5,
        textColor=colors.HexColor("#334155"),
        leftIndent=14,
        firstLineIndent=-14,
        spaceAfter=3,
    )

    # Build reference lookup by id_key
    all_papers_map = {}
    for d in DOMAINS_DATA:
        for p in d["papers"]:
            all_papers_map[p["id_key"]] = p

    for domain_info in DOMAINS_DATA:
        domain_name = domain_info["domain"]
        folder_name = domain_name.replace(" ", "_") + "_Domain"
        domain_dir = base_dir / folder_name
        domain_dir.mkdir(parents=True, exist_ok=True)

        for paper in domain_info["papers"]:
            filename = sanitize_filename(paper["title"])
            pdf_path = domain_dir / filename

            doc = SimpleDocTemplate(
                str(pdf_path),
                pagesize=letter,
                leftMargin=40,
                rightMargin=40,
                topMargin=36,
                bottomMargin=36,
            )

            story = []

            # 1. Journal / Conference Banner
            banner_text = f"Proceedings of the International Conference on {domain_name} & Engineering · Published {paper['year']}"
            story.append(Paragraph(banner_text, journal_header_style))
            story.append(HRFlowable(width="100%", thickness=0.8, color=colors.HexColor("#cbd5e1"), spaceAfter=10))

            # 2. Title & Authors
            story.append(Paragraph(paper["title"], title_style))
            story.append(Paragraph(paper["authors"], authors_style))
            story.append(Paragraph(f"Department of Computer Science & Intelligent Systems · Publication Year: {paper['year']}", journal_header_style))
            story.append(Spacer(1, 8))

            # 3. Abstract Box
            abstract_flowables = [
                Paragraph("<b>ABSTRACT</b>", abstract_heading),
                Paragraph(paper["abstract"], abstract_text_style),
                Spacer(1, 4),
                Paragraph(f"<b>Keywords—</b> {', '.join(paper['keywords'])}", keywords_style),
            ]
            box_table = Table([[abstract_flowables]], colWidths=[letter[0] - 80])
            box_table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
                        ("BOX", (0, 0), (-1, -1), 0.75, colors.HexColor("#94a3b8")),
                        ("TOPPADDING", (0, 0), (-1, -1), 8),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                        ("LEFTPADDING", (0, 0), (-1, -1), 10),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                    ]
                )
            )
            story.append(box_table)
            story.append(Spacer(1, 12))

            # 4. Body Sections
            for sec_title, sec_content in paper["sections"].items():
                story.append(Paragraph(f"{sec_title.upper()}", section_heading_style))
                story.append(Paragraph(sec_content, body_text_style))

            # 5. References Section
            story.append(Spacer(1, 6))
            story.append(Paragraph("REFERENCES", section_heading_style))

            citations_list = []
            for cited_key in paper.get("cites", []):
                if cited_key in all_papers_map:
                    cp = all_papers_map[cited_key]
                    citations_list.append(f"{cp['authors']} ({cp['year']}). \"{cp['title']}\". In Proc. Int. Conf. on Advanced Computing Systems.")

            # Add default foundational references
            citations_list.append(f"Vaswani, A., et al. (2017). \"Attention Is All You Need\". Advances in Neural Information Processing Systems, 30.")
            citations_list.append(f"Kipf, T. N., & Welling, M. (2016). \"Semi-Supervised Classification with Graph Convolutional Networks\". arXiv:1609.02907.")
            citations_list.append(f"Lewis, P., et al. (2020). \"Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks\". NeurIPS.")

            for idx, ref in enumerate(citations_list, start=1):
                story.append(Paragraph(f"[{idx}] {ref}", ref_style))

            doc.build(story)
            generated_files.append(pdf_path)

    return generated_files


if __name__ == "__main__":
    files = generate_all_pdfs()
    print(f"Generated {len(files)} research paper PDFs successfully in research_papers/ folder.")
