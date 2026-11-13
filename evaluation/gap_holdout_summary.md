# T12b Temporal Holdout Gap Validation Summary

- **Cutoff Year (T)**: `2023` | **Validation Window**: `2024`–`2026` (`H = 3` years)
- **Overall Matrix Gap Precision@3**: **0.643** (9/14) vs **Random Empty Cell Baseline**: **0.357** (5/14) (Fisher's exact test two-sided p = **0.257**, not statistically significant at alpha = 0.05 due to small sample size N=14 per condition)

| Topic | Domain | Pre-T Papers | Pairs Extracted | Matrix Void Precision@K | Random Baseline |
|---|---|---|---|---|---|
| perovskite solar cell degradation mechanisms | Materials Science & Energy | 19 | 18 | 0.667 | 0.000 |
| retrieval augmented generation attribution benchmarks | Computer Science & NLP | 25 | 16 | 0.000 | 0.000 |
| crispr cas9 off target cleavage detection | Biomedical & Genetics | 19 | 18 | 1.000 | 0.333 |
| graph neural networks molecular property prediction | Graph Machine Learning & Chemistry | 21 | 18 | 0.667 | 0.667 |
| urban heat island remote sensing deep learning | Climate & Earth Observation | 23 | 18 | 1.000 | 1.000 |

## Honest Caveats
- Small evaluation scale (5 benchmark topics; pre-T extraction from abstracts rather than full PDFs).
- Post-T check measures OpenAlex keyword + embedding matches (`cosine >= 0.45`), which captures topical follow-up but does not guarantee methodological rigor.
- The difference (9/14 vs 5/14, Fisher exact p = 0.257) is directional but not statistically significant; a larger sample size (>=15 topics) would be required to establish formal statistical significance.
