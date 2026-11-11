# Discrete Mathematics Proofs & Derivations (DM-1)

This document summarizes the formal correctness arguments behind the discrete mathematics algorithms implemented in `backend/app/dm/` and `backend/app/dsa/`.

---

## 1. Correctness of Kahn's Topological Sort

**Theorem:** Let $G = (V, E)$ be a finite directed graph. Kahn's algorithm emits all $|V|$ vertices in topological order if and only if $G$ is a Directed Acyclic Graph (DAG). Otherwise, the unvisited subgraph contains at least one directed cycle.

**Proof:**
1. *($\implies$) Soundness:* Whenever vertex $u$ is popped from the zero-in-degree queue, all incoming edges $(p, u) \in E$ have already had their source $p$ popped and placed earlier in `order`. Hence for every $(u, v) \in E$ emitted completely, $\text{pos}(u) < \text{pos}(v)$. Thus `order` is a valid topological sort, which implies $G$ has no cycle (a cycle $c_1 \to \dots \to c_k \to c_1$ would require $\text{pos}(c_1) < \text{pos}(c_1)$).
2. *($\impliedby$) Completeness:* Suppose $G$ is a finite DAG and Kahn's algorithm halts with $|R| > 0$ unvisited vertices, where $R = V \setminus \text{order}$. Every vertex $v \in R$ still has positive remaining in-degree from vertices in $R$ (otherwise it would have entered the queue). Starting at any $v_0 \in R$ and repeatedly stepping backward to an unvisited predecessor $v_{i+1} \in R$ generates an infinite sequence inside the finite set $R$. By the Pigeonhole Principle, some vertex repeats, yielding a directed cycle in $G$ — contradicting that $G$ is a DAG. $\blacksquare$

---

## 2. Why $\text{SPC}(u, v) = N(u) \cdot M(v)$ Counts Source-to-Sink Paths

**Setup:** Let $G = (V, E)$ be a DAG with source set $S = \{x \in V : \text{deg}^-(x) = 0\}$ and sink set $T = \{y \in V : \text{deg}^+(y) = 0\}$.

- **Forward Recurrence:** Define $N(v)$ as:
  $$N(v) = \begin{cases} 1 & \text{if } v \in S, \\ \sum_{(u, v) \in E} N(u) & \text{otherwise.} \end{cases}$$
  By structural induction along the topological order, every path from any source $s \in S$ to $v$ decomposes uniquely into a path from $s$ to an immediate predecessor $u$ followed by edge $(u, v)$. Since subpaths to distinct predecessors are disjoint, $N(v)$ equals the exact number of $S$-to-$v$ paths.

- **Backward Recurrence:** Symmetrically, along reverse topological order:
  $$M(u) = \begin{cases} 1 & \text{if } u \in T, \\ \sum_{(u, v) \in E} M(v) & \text{otherwise.} \end{cases}$$
  By induction on reverse topological order, $M(u)$ equals the exact number of $u$-to-$T$ paths.

- **Product Rule for Edge $(u, v)$:** Because $G$ is acyclic, any prefix path $P_1: s \rightsquigarrow u$ and suffix path $P_2: v \rightsquigarrow t$ cannot share vertices (otherwise $G$ would contain a cycle). Concatenating $P_1 \cdot (u, v) \cdot P_2$ establishes a bijection between $\mathcal{P}(S, u) \times \mathcal{P}(v, T)$ and the set of all source-to-sink paths traversing edge $(u, v)$. By the Multiplication Principle:
  $$\text{SPC}(u, v) = N(u) \cdot M(v). \quad \blacksquare$$

---

## 3. Unique Topological Order $\iff$ Hamiltonian Path in a DAG

**Theorem:** A finite DAG $G = (V, E)$ has a unique topological ordering $(v_1, v_2, \dots, v_n)$ if and only if $(v_1, v_2, \dots, v_n)$ is a directed Hamiltonian path (i.e., $(v_i, v_{i+1}) \in E$ for all $1 \le i < n$).

**Proof:**
1. *($\impliedby$):* Suppose $(v_1, v_2, \dots, v_n)$ is a Hamiltonian path in $G$. In *any* topological sort $\pi$, each edge $(v_i, v_{i+1}) \in E$ forces $\pi(v_i) < \pi(v_{i+1})$. Chaining inequalities yields $\pi(v_1) < \pi(v_2) < \dots < \pi(v_n)$, uniquely determining $\pi$.
2. *($\implies$):* Suppose $(v_1, \dots, v_n)$ is a topological ordering of $G$, and assume for contradiction that $(v_i, v_{i+1}) \notin E$ for some $i$. Because $(v_1, \dots, v_n)$ is already a valid topological sort, there can be no edge $(v_{i+1}, v_i)$ either. Therefore swapping $v_i$ and $v_{i+1}$ produces $(v_1, \dots, v_{i+1}, v_i, \dots, v_n)$, which still preserves every edge $(u, w) \in E$! Thus there are at least two distinct topological orderings, contradicting uniqueness. Hence $(v_i, v_{i+1}) \in E$ for every consecutive pair. $\blacksquare$

---

## 4. Inclusion–Exclusion Principle for 3 Sets

**Theorem:** For any finite sets $A, B, C$:
$$|A \cup B \cup C| = |A| + |B| + |C| - |A \cap B| - |A \cap C| - |B \cap C| + |A \cap B \cap C|.$$

**Indicator Proof:** Let $\mathbf{1}_X(x) \in \{0, 1\}$ denote the indicator function of $x \in X$. For any element $x \in A \cup B \cup C$, consider the polynomial identity:
$$1 - (1 - \mathbf{1}_A(x))(1 - \mathbf{1}_B(x))(1 - \mathbf{1}_C(x)) = \mathbf{1}_{A \cup B \cup C}(x).$$
Notice if $x \in A \cup B \cup C$, at least one factor $(1 - \mathbf{1}_X(x)) = 0$, so the LHS evaluates to $1$; if $x \notin A \cup B \cup C$, all three indicators are $0$, so the LHS is $1 - 1 = 0$. Expanding the product:
$$\mathbf{1}_{A \cup B \cup C} = \mathbf{1}_A + \mathbf{1}_B + \mathbf{1}_C - \mathbf{1}_A\mathbf{1}_B - \mathbf{1}_A\mathbf{1}_C - \mathbf{1}_B\mathbf{1}_C + \mathbf{1}_A\mathbf{1}_B\mathbf{1}_C.$$
Using $\mathbf{1}_X \mathbf{1}_Y = \mathbf{1}_{X \cap Y}$ and summing over all elements $x$ in the universe immediately yields the cardinality formula. $\blacksquare$

---

## 5. Lincoln–Petersen Capture–Recapture Estimator & Chapman Correction

**Setup:** Suppose a closed population of true size $N$ relevant papers is sampled independently by Source 1 (yielding $n_1$ marked papers) and Source 2 (yielding $n_2$ papers), with $m = |S_1 \cap S_2|$ overlapping papers.

1. **Lincoln–Petersen Derivation:** Under independence, the fraction of Source 2 papers present in Source 1 equals the true population proportion sampled by Source 1:
   $$\frac{m}{n_2} \approx \frac{n_1}{N} \implies \hat{N}_{\text{LP}} = \frac{n_1 n_2}{m}.$$
   Since scholarly search engines are *positively correlated* (both index high-citation / OpenAlex-linked papers more frequently), $m$ is inflated relative to independent sampling, making $\hat{N}$ a **conservative lower-bound estimate** of the total literature.
2. **Chapman Correction (Unbiased for Small Overlaps):** $\hat{N}_{\text{LP}}$ is undefined when $m=0$ and slightly upward-biased for small $m$. Chapman's nearly unbiased estimator adds $1$ to each count:
   $$\hat{N}_C = \frac{(n_1 + 1)(n_2 + 1)}{m + 1} - 1,$$
   with approximate variance:
   $$\widehat{\text{Var}}(\hat{N}_C) = \frac{(n_1 + 1)(n_2 + 1)(n_1 - m)(n_2 - m)}{(m + 1)^2 (m + 2)}, \qquad \text{CI}_{95\%} = \hat{N}_C \pm 1.96\sqrt{\widehat{\text{Var}}(\hat{N}_C)}. \quad \blacksquare$$
