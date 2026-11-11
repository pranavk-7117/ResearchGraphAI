"""
Bipartite Method x Task/Dataset Matrix and Union-Find Signal Clustering for T12 Auditable Gaps.

Implements:
- Step 1: Canonical normalization (lowercase, light lemmatization, fuzz.ratio >= 92),
  bipartite paper <-> (method, task_or_dataset) matrix, PMI, and exact hypergeometric p-values.
- Step 2: Embedding clustering of all limitation & future-work signals (zero [:15] cap)
  using hand-built UnionFind over cosine similarity >= 0.75.
"""

from collections import Counter
import math
import re
from typing import Any, Callable

import numpy as np
from rapidfuzz import fuzz
from scipy.stats import hypergeom

from app.dsa.union_find import UnionFind


_PLURAL_KEEP = {"loss", "bias", "analysis", "corpus", "series", "diagnosis", "class", "cross"}


def normalize_entity_label(raw: str) -> str:
    """Lowercase, normalize separators, and lightly lemmatize trailing plural suffixes."""
    cleaned = re.sub(r"[^a-z0-9\s\-/+]", " ", (raw or "").strip().lower())
    tokens = []
    for tok in cleaned.split():
        if len(tok) > 4 and tok not in _PLURAL_KEEP:
            if tok.endswith("ies") and len(tok) > 5:
                tok = tok[:-3] + "y"
            elif tok.endswith("s") and not tok.endswith(("ss", "us", "is")):
                tok = tok[:-1]
        tokens.append(tok)
    return " ".join(tokens)


def canonicalize_labels(raw_labels: list[str], ratio_threshold: float = 92.0) -> dict[str, str]:
    """
    Map each normalized label string to a canonical representative string using
    greedy merging at `fuzz.ratio >= ratio_threshold`, preferring most frequent variant.
    """
    normed = [normalize_entity_label(x) for x in raw_labels if normalize_entity_label(x)]
    counts = Counter(normed)
    canonicals: list[str] = []
    mapping: dict[str, str] = {}

    for label, _cnt in counts.most_common():
        matched = None
        for c in canonicals:
            if fuzz.ratio(label, c) >= ratio_threshold:
                matched = c
                break
        if matched is None:
            canonicals.append(label)
            mapping[label] = label
        else:
            mapping[label] = matched
    return mapping


def _extract_fact_val(field_obj: Any) -> str:
    if isinstance(field_obj, dict):
        return str(field_obj.get("value") or "").strip()
    if isinstance(field_obj, str):
        return field_obj.strip()
    return ""


def build_method_task_matrix(
    paper_facts: list[tuple[int, str, Any]],
    min_support: int = 2,
) -> dict[str, Any]:
    """
    Construct the bipartite Method x Task/Dataset co-occurrence matrix.

    Args:
        paper_facts: list of `(paper_id, title, PaperFact-like object)` tuples.
        min_support: minimum marginal count required in both row & column to nominate an empty/sparse cell.
    """
    raw_pairs: list[tuple[int, str, str, str]] = []
    for pid, title, fact in paper_facts:
        m_val = _extract_fact_val(getattr(fact, "method", None)) or _extract_fact_val(
            getattr(fact, "algorithm_or_model", None)
        )
        t_val = _extract_fact_val(getattr(fact, "dataset", None)) or _extract_fact_val(
            getattr(fact, "problem", None)
        )
        m_norm = normalize_entity_label(m_val)
        t_norm = normalize_entity_label(t_val)
        if m_norm and t_norm:
            raw_pairs.append((pid, title or f"Paper {pid}", m_norm, t_norm))

    if not raw_pairs:
        return {
            "methods": [],
            "tasks": [],
            "cells": [],
            "candidates": [],
            "total_papers": 0,
            "min_support": min_support,
        }

    m_canon_map = canonicalize_labels([x[2] for x in raw_pairs])
    t_canon_map = canonicalize_labels([x[3] for x in raw_pairs])

    papers_by_method: dict[str, set[int]] = {}
    papers_by_task: dict[str, set[int]] = {}
    cell_papers: dict[tuple[str, str], list[dict[str, Any]]] = {}
    all_bipartite_pids: set[int] = set()

    seen_pair_pid: set[tuple[int, str, str]] = set()
    for pid, title, m_norm, t_norm in raw_pairs:
        cm = m_canon_map[m_norm]
        ct = t_canon_map[t_norm]
        if (pid, cm, ct) in seen_pair_pid:
            continue
        seen_pair_pid.add((pid, cm, ct))
        all_bipartite_pids.add(pid)
        papers_by_method.setdefault(cm, set()).add(pid)
        papers_by_task.setdefault(ct, set()).add(pid)
        cell_papers.setdefault((cm, ct), []).append({"paper_id": pid, "title": title})

    total_n = len(all_bipartite_pids)
    methods_sorted = sorted(papers_by_method.keys(), key=lambda m: (-len(papers_by_method[m]), m))
    tasks_sorted = sorted(papers_by_task.keys(), key=lambda t: (-len(papers_by_task[t]), t))

    cells: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []

    for m in methods_sorted:
        row_sup = len(papers_by_method[m])
        for t in tasks_sorted:
            col_sup = len(papers_by_task[t])
            p_list = cell_papers.get((m, t), [])
            obs = len(p_list)
            expected = (row_sup * col_sup) / float(total_n) if total_n > 0 else 0.0
            pmi = (
                math.log2(((obs + 0.5) * total_n) / float(row_sup * col_sup))
                if (row_sup > 0 and col_sup > 0 and total_n > 0)
                else 0.0
            )
            # Lower-tail hypergeometric p-value: P(X <= obs) under independence
            hg_p = float(hypergeom.cdf(obs, total_n, row_sup, col_sup)) if total_n > 0 else 1.0
            is_void_candidate = (row_sup >= min_support and col_sup >= min_support) and (
                obs == 0 or (obs == 1 and expected >= 1.5)
            )
            cell = {
                "method": m,
                "task": t,
                "count": obs,
                "row_support": row_sup,
                "col_support": col_sup,
                "expected": round(expected, 3),
                "pmi": round(pmi, 3),
                "hypergeom_p": round(hg_p, 4),
                "is_candidate_void": is_void_candidate,
                "papers": p_list,
            }
            cells.append(cell)
            if is_void_candidate:
                candidates.append(cell)

    candidates.sort(key=lambda c: (c["count"], c["hypergeom_p"], -c["expected"], c["method"], c["task"]))
    return {
        "methods": methods_sorted,
        "tasks": tasks_sorted,
        "cells": cells,
        "candidates": candidates,
        "total_papers": total_n,
        "min_support": min_support,
    }


def cluster_limitation_signals(
    signals: list[dict[str, Any]],
    embed_batch_fn: Callable[[list[str]], list[list[float]]],
    sim_threshold: float = 0.75,
) -> list[dict[str, Any]]:
    """
    Cluster ALL limitation and future-work signals by embedding cosine similarity >= sim_threshold
    using hand-built UnionFind (no arbitrary [:15] cap).
    """
    if not signals:
        return []

    texts = [f"{s.get('type', 'limitation')}: {s.get('text', '')}".strip() for s in signals]
    vecs = np.asarray(embed_batch_fn(texts), dtype=float)
    if vecs.ndim != 2 or vecs.shape[0] != len(signals):
        return [{"representative": s["text"], "signals": [s], "paper_count": 1, "verified_count": int(bool(s.get("verified")))} for s in signals]

    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    normed = vecs / norms
    sim_matrix = normed @ normed.T

    uf = UnionFind(list(range(len(signals))))
    n = len(signals)
    for i in range(n):
        for j in range(i + 1, n):
            if float(sim_matrix[i, j]) >= sim_threshold:
                uf.union(i, j)

    groups: dict[int, list[dict[str, Any]]] = {}
    for idx in range(n):
        root = uf.find(idx)
        groups.setdefault(root, []).append(signals[idx])

    clusters: list[dict[str, Any]] = []
    for members in groups.values():
        distinct_pids = {m["paper_id"] for m in members if m.get("paper_id") is not None}
        verified_cnt = sum(1 for m in members if m.get("verified"))
        rep = sorted(members, key=lambda m: (not m.get("verified", False), -len(m.get("text", ""))))[0]["text"]
        clusters.append({
            "representative": rep,
            "signals": members,
            "paper_count": len(distinct_pids),
            "verified_count": verified_cnt,
        })

    clusters.sort(key=lambda c: (-c["paper_count"], -c["verified_count"], -len(c["signals"])))
    return clusters
