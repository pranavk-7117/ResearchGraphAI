"""
Corpus Completeness Estimation via Inclusion-Exclusion and Capture-Recapture.

Uses hand-built Inclusion-Exclusion (DM-1) to compute multi-source overlap sets
across OpenAlex, Semantic Scholar, and arXiv, and applies the bias-corrected
Chapman estimator with Seber variance for approximate lower-bound corpus size.
"""

import math
from typing import Any
from sqlalchemy.orm import Session

from app import models
from app.dm.inclusion_exclusion import inclusion_exclusion_breakdown


TRACKED_SOURCES = ("openalex", "semantic_scholar", "arxiv")
MIN_RECAPTURE_OVERLAP = 5


def lincoln_petersen(n1: int, n2: int, m: int) -> float | None:
    """Classic two-sample Lincoln-Petersen population estimator: (n1 * n2) / m."""
    if n1 <= 0 or n2 <= 0 or m <= 0:
        return None
    return (n1 * n2) / float(m)


def chapman_estimator(n1: int, n2: int, m: int) -> dict[str, Any]:
    """
    Bias-corrected Chapman capture-recapture estimator with Seber 1970 variance:
      N_hat = ((n1 + 1)(n2 + 1) / (m + 1)) - 1
      Var   = ((n1 + 1)(n2 + 1)(n1 - m)(n2 - m)) / ((m + 1)^2 * (m + 2))
    Refuses unreliable extrapolation when overlap m < MIN_RECAPTURE_OVERLAP.
    """
    observed_union = max(n1 + n2 - m, 0)
    if m < MIN_RECAPTURE_OVERLAP or n1 <= 0 or n2 <= 0:
        return {
            "estimate": None,
            "se": None,
            "ci_95": None,
            "available": False,
            "reason": f"Overlap m={m} is below minimum threshold ({MIN_RECAPTURE_OVERLAP}); estimate suppressed.",
        }

    n_hat = ((n1 + 1) * (n2 + 1) / float(m + 1)) - 1.0
    var = (
        (n1 + 1) * (n2 + 1) * max(n1 - m, 0) * max(n2 - m, 0)
    ) / (float((m + 1) ** 2) * float(m + 2))
    se = math.sqrt(max(0.0, var))
    ci_low = max(float(observed_union), n_hat - 1.96 * se)
    ci_high = max(ci_low, n_hat + 1.96 * se)

    return {
        "estimate": round(n_hat, 1),
        "se": round(se, 2),
        "ci_95": [round(ci_low, 1), round(ci_high, 1)],
        "available": True,
        "reason": None,
    }


class CompletenessService:
    def compute(self, db: Session, project_id: int) -> dict[str, Any]:
        """Compute multi-source Venn overlap and Chapman capture-recapture completeness."""
        rows = (
            db.query(models.ProjectPaper, models.Paper)
            .join(models.Paper, models.ProjectPaper.paper_id == models.Paper.id)
            .filter(models.ProjectPaper.project_id == project_id)
            .all()
        )

        named_sets: dict[str, set[int]] = {src: set() for src in TRACKED_SOURCES}
        all_pids: set[int] = set()

        for pp, paper in rows:
            all_pids.add(paper.id)
            raw_sources = list(getattr(pp, "sources", None) or [])
            if not raw_sources and paper.source_name:
                raw_sources = [paper.source_name]
            for src in raw_sources:
                norm = str(src).strip().lower()
                if norm:
                    named_sets.setdefault(norm, set()).add(paper.id)

        venn = inclusion_exclusion_breakdown(named_sets)

        # Pick pair with highest overlap m among all present source pairs
        source_names = sorted(named_sets.keys())
        best_pair: tuple[str, str] | None = None
        best_m = -1
        for i in range(len(source_names)):
            for j in range(i + 1, len(source_names)):
                s_a, s_b = source_names[i], source_names[j]
                if not named_sets[s_a] or not named_sets[s_b]:
                    continue
                m = len(named_sets[s_a] & named_sets[s_b])
                if m > best_m:
                    best_m = m
                    best_pair = (s_a, s_b)

        total_observed = len(all_pids)
        if best_pair is None:
            return {
                "project_id": project_id,
                "total_observed": total_observed,
                "venn_breakdown": venn,
                "best_pair": None,
                "lincoln_petersen_estimate": None,
                "chapman_estimate": None,
                "ci_95": None,
                "estimated_coverage_pct": None,
                "estimate_available": False,
                "is_lower_bound": True,
                "method": "chapman_best_pair",
                "disclaimer": (
                    "Fewer than two overlapping discovery sources recorded. "
                    "Capture-recapture estimate requires multi-source overlap."
                ),
            }

        s_a, s_b = best_pair
        n1, n2 = len(named_sets[s_a]), len(named_sets[s_b])
        lp = lincoln_petersen(n1, n2, best_m)
        chap = chapman_estimator(n1, n2, best_m)

        coverage_pct = None
        if chap["available"] and chap["estimate"]:
            coverage_pct = round(min(100.0, (total_observed / float(chap["estimate"])) * 100.0), 1)

        if chap["available"]:
            disclaimer = (
                f"Lower-bound estimate via bias-corrected Chapman estimator on best pair ({s_a}, {s_b}) "
                "(statsmodels log-linear 3-source fit not installed). Assumes independent source capture "
                "within the indexed subset; true total relevant literature may be larger."
            )
        else:
            disclaimer = chap["reason"]

        return {
            "project_id": project_id,
            "total_observed": total_observed,
            "venn_breakdown": venn,
            "best_pair": {
                "sources": [s_a, s_b],
                "n1": n1,
                "n2": n2,
                "overlap_m": best_m,
            },
            "lincoln_petersen_estimate": round(lp, 1) if lp is not None else None,
            "chapman_estimate": chap["estimate"],
            "ci_95": chap["ci_95"],
            "estimated_coverage_pct": coverage_pct,
            "estimate_available": chap["available"],
            "is_lower_bound": True,
            "method": "chapman_best_pair",
            "disclaimer": disclaimer,
        }
