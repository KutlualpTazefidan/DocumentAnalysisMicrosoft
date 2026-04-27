# Evaluation Metrics — Rationale

This is a reasoning document, not a spec. It explains *why* the eval pipeline uses the metrics it uses. Read this when you want to understand the trade-offs, not the implementation.

## Setting

Goal: evaluate retrieval quality for the `query-index` feature. Given a query, the system returns a ranked list of chunks. We want to know how good that ranking is.

To compute any retrieval metric we need labeled data: for each query, the set of chunks that *should* appear in the result.

## Important context: chunk relevance is multi-valued in this corpus

Earlier rounds of design assumed single-chunk relevance ("for this query, chunk X is the answer"). That was wrong for our corpus. In practice:

- A query about a topic may legitimately match **several** chunks — for example, the chunk where the topic is introduced plus a chunk in an attachment, a table, or a bibliography reference.
- Some of these chunks should rank **higher** than others, either because they are more on-topic or because there is a natural reading order in the source document.

This shape — multiple relevant chunks per query, with rank order mattering — fundamentally changes which metrics are appropriate. It rules out metrics that assume a single "correct" answer (or treat all relevant items equally), and it favours metrics that reward both completeness and good ordering.

## The candidate metrics, ranked by usefulness for this case

### Recall@k — primary metric

> Of all the chunks that should have been returned, what fraction did we find in the top-k?

For k ∈ {5, 10, 20}. This is the most direct answer to "did the system find everything relevant?" It is the right primary metric when there are multiple expected chunks per query.

### MAP (Mean Average Precision) — primary metric for ranking quality

> Did the system not just find relevant chunks, but rank them high?

MAP penalises both missing relevant chunks AND putting them late in the list. It works with binary labels — you do not need to grade chunks as "highly relevant" vs. "somewhat relevant". It is the standard metric for ranked multi-document retrieval and produces a single number that captures both recall and ranking quality. A good default when graded labels are not available.

### nDCG@k — only meaningful with graded relevance labels

> If chunks have ranks like "most relevant", "supporting", "tangential", how well does the system order them?

nDCG (normalized Discounted Cumulative Gain) requires graded relevance labels — e.g., 3 = primary chunk, 2 = supporting chunk, 1 = tangentially relevant, 0 = irrelevant. With binary labels (relevant / not), nDCG collapses to a less interpretable variant of MAP and adds no signal.

**Trade-off:** graded labels mean every curated example takes 2-3x as long because the curator has to assign weights instead of just listing chunk IDs. For a small team starting from zero, this is expensive. Recommendation: start binary, adopt graded later only if MAP proves insufficient.

### Hit Rate@k — secondary metric

> Did at least one relevant chunk appear in the top-k?

For multi-chunk relevance this is too coarse — a system that finds 1 of 5 relevant chunks scores the same as one that finds all 5. But it remains useful as a cheap "is the system at least partially working" signal at small k. Hit Rate@1 in particular answers "does the top result match the topic at all?"

### MRR (Mean Reciprocal Rank) — secondary metric

> How far down is the first relevant chunk?

MRR captures top-result quality but ignores everything after the first hit. In multi-chunk cases it is narrow. Useful when you care about "how quickly does the user see something useful", less useful when you care about "did they see all relevant content".

## What was almost wrong

Before the corpus shape was clarified, the design proposed dropping Recall@k and nDCG and keeping Hit Rate@k + MRR. That would have been correct for single-chunk relevance but is wrong for the actual multi-chunk case. The clarification reactivated Recall@k as the primary metric and brought MAP in as a strong fit it was not before.

The lesson: the appropriate metric set is a function of corpus shape and label shape, not of "what looks rigorous". Picking metrics before understanding the data leads to expensive-looking dashboards that miss the point.

## The synthetic-data ceiling

Synthetic generation creates one labeled chunk per question — the source chunk that the LLM was given. In a corpus with attachments, bibliographies, tables, and cross-references, *other* chunks often legitimately answer the same question. When the search returns one of those instead of the source chunk, synthetic eval scores it as a miss — even though the answer was correct.

**Practical consequence:** synthetic Recall@k systematically understates true retrieval quality, by an amount that depends on corpus redundancy (typically 5-15 percentage points for technical-document corpora).

**Therefore:**

- Synthetic metrics are valid for **regression detection** — "did the number drop since yesterday?"
- Synthetic metrics are **not valid for absolute statements** — "the system is 73% good".
- Absolute statements come from the hand-curated golden set, where curators can label *all* legitimate chunks per query, not just the source.

This is a hard rule. Reports must label which metrics came from which dataset, and any cross-team communication of an absolute number must come from the golden set.

## Sample-size thresholds — where the numbers come from

Reports flag datasets below certain sizes as "indicative" or "preliminary". Those thresholds are not magic — they come from one formula plus one convention.

### The formula (binary outcomes per query, e.g. Hit Rate@k)

For a metric that is binary per query (hit / no hit), the result is a sample proportion. The 95% confidence interval around it is approximately:

```
CI half-width  ≈  1.96 × sqrt( p(1 − p) / n )
```

The variance term `p(1 − p)` is maximised at `p = 0.5`, so the worst-case CI half-width is:

```
CI half-width (worst case)  ≈  1 / sqrt(n)
```

This gives the following table:

| n   | CI half-width (worst case) | What it means |
|-----|---|---|
| 8   | ±35 percentage points | A measured 50% could be anywhere from 15% to 85%. Useless for decisions. |
| 20  | ±22 pp | Trend visible only if very large. |
| 30  | ±18 pp | Threshold below which the normal approximation itself becomes unreliable; below this you would use t-distribution or exact (Clopper-Pearson) methods. Convention since the early 20th century. |
| 50  | ±14 pp | Preliminary signal — coarse trends but not precise levels. |
| 100 | ±10 pp | The threshold above which percentage-level results "feel" interpretable. **Pure convention, not a natural law.** |
| 200 | ±7 pp | Reasonably precise. |
| 400 | ±5 pp | Solid. |
| 1000 | ±3 pp | Research-grade. |

### What is convention vs. what is derivation

| Number | Origin |
|---|---|
| `n < 30 → indicative` | Mathematically grounded: below 30 the normal approximation is unreliable; you should switch to exact methods. |
| `30 ≤ n < 100 → preliminary` | Convention. The 100-cutoff is not derived from a principle — it corresponds to roughly ±10pp CI at p=0.5, which is a folk-science threshold for "interpretable percentage". |
| `n ≥ 100 → reportable` | Convention, same caveat. Could equally be 50, 200, 400 depending on the precision the project actually needs. |

### Decision-driven alternative

A more rigorous approach: pick the precision the project needs first, then back-solve for n.

```
required n  ≈  ( 1 / target CI half-width )²        (worst case, p = 0.5)
```

- Want ±5 pp? → n ≥ 400.
- Want ±10 pp? → n ≥ 100.
- Want ±15 pp? → n ≥ 45.

This is the more honest framing. The project should pick an acceptable CI width based on what decisions the metric will drive, not adopt 100 because it is round.

### Caveat for multi-chunk Recall@k

The formula above assumes binary per-query outcomes. Recall@k with multiple expected chunks per query is continuous in [0,1], with variance that depends on the per-query distribution. The same scaling law (`precision ∝ 1/sqrt(n)`) applies, with similar magnitudes, but the exact CI is best computed via bootstrap from the actual per-query distribution. The eval pipeline can produce bootstrap CIs as a follow-up if precise statements are needed.

### Sources

- Standard error of a proportion / Wald confidence interval: any introductory statistics textbook (e.g., Hogg & Tanis, *Probability and Statistical Inference*; Casella & Berger, *Statistical Inference*).
- More accurate intervals for small n / extreme p: Wilson score interval (Wilson, 1927); Clopper-Pearson exact interval.
- Bootstrap confidence intervals for arbitrary statistics: Efron, *Bootstrap Methods: Another Look at the Jackknife* (1979).
- IR evaluation specifically — Sanderson & Zobel and Voorhees both report empirical results on how query-set size affects metric stability; TREC tracks have historically used 50 queries as a working minimum.

## Operational metrics (not quality, but tracked anyway)

- Mean / p95 latency per query
- Count of queries, embedding calls, failures
- Estimated cost per run

These cost almost nothing extra to compute — the data falls out of the eval run — but they flag operational regressions early. A run that suddenly takes 10x longer signals something worth investigating, even if quality numbers stay flat.

## Open decision (to be resolved before the spec is finalised)

**Binary labels** (each chunk: relevant or not) **or graded labels** (each chunk: a relevance rank)?

Affects whether nDCG@k is in the metric set or not. The user has indicated rank order matters in their corpus, which leans toward graded — but graded curation is meaningfully more expensive. Default if undecided: binary, with MAP as the ranking-quality metric. If graded is adopted, nDCG@k joins the primary set and MAP becomes secondary.

## Final candidate set (pending the open decision above)

If binary:
- Primary: Recall@k for k ∈ {5, 10, 20}, MAP
- Secondary: Hit Rate@1, MRR
- Operational: latency p50/p95, query count, failure count

If graded:
- Primary: Recall@k for k ∈ {5, 10, 20}, nDCG@k for k ∈ {5, 10}
- Secondary: Hit Rate@1, MAP, MRR
- Operational: same as above
