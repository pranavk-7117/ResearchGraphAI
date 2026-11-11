# Course Mapping — DBMS, Data Structures & Discrete Mathematics

Maps every syllabus concept implemented in **ResearchGraphAI** directly to its source module, API endpoint, documentation, and verification test. All `backend/app/dsa/` and `backend/app/dm/` algorithms are hand-built in pure Python with zero `networkx` or `scikit-learn` runtime imports (`networkx` is used solely inside `tests/` as an external oracle).

---

## 1. Database Management Systems (DBMS)

| Syllabus Concept | Implementation & Migration / File | API / Call Site | Verification Test / Evidence |
|---|---|---|---|
| **ER Modeling & Normalization (3NF/BCNF, M:N Junctions)** | [`models.py`](../backend/app/models.py), [`5d4d80a9f2aa`](../backend/alembic/versions/5d4d80a9f2aa_initial_schema_clean.py), [`docs/DBMS_NOTES.md`](DBMS_NOTES.md) | All project & corpus endpoints | Schema constraints & cascade tests |
| **PostgreSQL + `pgvector` HNSW Index & Hybrid GIN `tsvector`** | [`a1b2c3d4e501_t1_hybrid_fts_gin.py`](../backend/alembic/versions/a1b2c3d4e501_t1_hybrid_fts_gin.py), [`chat.py`](../backend/app/services/chat.py) | `POST /projects/{id}/chat` | `test_hybrid_db_isolation_and_gin_explain` (`test_rag_chat.py`) |
| **Relational Views (`v_project_paper_stats`) & Materialized Views (`mv_field_growth`)** | [`f60708091006_t15_dbms_views_trigger.py`](../backend/alembic/versions/f60708091006_t15_dbms_views_trigger.py), [`dbms_queries.py`](../backend/app/services/dbms_queries.py) | `GET /projects`, `GET /projects/{id}/stats`, `POST /projects/{id}/stats/refresh` | `test_dbms_features.py` |
| **PL/pgSQL Triggers (`AFTER INSERT OR DELETE` `corpus_version` bump)** | [`f60708091006_t15_dbms_views_trigger.py`](../backend/alembic/versions/f60708091006_t15_dbms_views_trigger.py) | Automatic on `project_papers` writes | `test_dbms_features.py` (INSERT & DELETE trigger assertions) |
| **Recursive CTEs (`WITH RECURSIVE` + cycle guard)** | [`dbms_queries.py`](../backend/app/services/dbms_queries.py) (`get_citation_ancestors_recursive`) | `GET /projects/{id}/ancestors?paper_id=` | `test_dbms_features.py` (verified against DSA `bfs` oracle) |
| **SQL Window Functions (`RANK() OVER (PARTITION BY cluster_id ...)`)** | [`dbms_queries.py`](../backend/app/services/dbms_queries.py) (`get_cluster_representatives_window`) | `GET /projects/{id}/cluster-representatives` | `test_dbms_features.py` |
| **Transaction Isolation & Concurrency (`FOR UPDATE SKIP LOCKED`)** | [`jobs.py`](../backend/app/services/jobs.py), [`docs/DBMS_NOTES.md`](DBMS_NOTES.md) | `POST /projects/{id}/gaps/detect`, worker polling | Worker claim tests & `EXPLAIN ANALYZE` notes |
| **Constraints (`UNIQUE`, Deduplication Hashes) & Read-Only GETs** | [`b2c3d4e5f602`](../backend/alembic/versions/b2c3d4e5f602_t4_directed_and_graph_cache.py), [`c3d4e5f60703`](../backend/alembic/versions/c3d4e5f60703_t5_gap_statement_hash_unique.py) | `GET /projects/{id}/gaps`, `POST /projects/{id}/gaps/detect` | `test_gaps_endpoint_and_dedup.py` |
| **Query Execution Plans (`EXPLAIN (ANALYZE, BUFFERS)`) & RLS** | [`docs/DBMS_NOTES.md`](DBMS_NOTES.md) | GIN, HNSW, Recursive CTE plans | Live Supabase Postgres captures |

---

## 2. Data Structures (DS)

| Syllabus Concept | Hand-Built Pure-Python Module | Integrated Production Caller | Oracle / Unit Verification |
|---|---|---|---|
| **Graph Representation (Adjacency List), BFS & DFS** | [`backend/app/dsa/graph.py`](../backend/app/dsa/graph.py) | [`research_graph.py`](../backend/app/services/research_graph.py), [`evolution.py`](../backend/app/services/evolution.py), `routes.py` | 200+ randomized oracle trials vs `networkx` (`test_dsa.py`) |
| **Disjoint-Set / Union-Find (Path Compression + Union by Rank)** | [`backend/app/dsa/union_find.py`](../backend/app/dsa/union_find.py) | [`gap_matrix.py`](../backend/app/services/gap_matrix.py) (signal clustering), `mst.py` | Connected-component & cycle equivalence oracle (`test_dsa.py`) |
| **Topological Sort (Kahn's Algorithm) & Cycle Extraction** | [`backend/app/dsa/topo.py`](../backend/app/dsa/topo.py) | [`dm/path_counting.py`](../backend/app/dm/path_counting.py), [`dm/reading_path.py`](../backend/app/dm/reading_path.py) | Topological ordering & witness cycle check vs `networkx` (`test_dsa.py`) |
| **Binary Min-Heap & `O(N log K)` `top_k` Selection** | [`backend/app/dsa/heap.py`](../backend/app/dsa/heap.py) | [`discovery.py`](../backend/app/services/discovery.py), [`relations.py`](../backend/app/services/relations.py), [`dm/main_path.py`](../backend/app/dm/main_path.py) | Heap sort & `heapq.nlargest` oracle (`test_dsa.py`) + [`bench_dsa.py`](../backend/scripts/bench_dsa.py) |
| **Shortest Path (Dijkstra with Semantic Distance Cost)** | [`backend/app/dsa/shortest_path.py`](../backend/app/dsa/shortest_path.py) | [`research_graph.py`](../backend/app/services/research_graph.py) (`GET /projects/{id}/graph` pathfinder) | 200 random weighted graphs vs `nx.dijkstra_path` (`test_dsa.py`) |
| **Minimum / Maximum Spanning Tree (Kruskal's Algorithm)** | [`backend/app/dsa/mst.py`](../backend/app/dsa/mst.py) | [`research_graph.py`](../backend/app/services/research_graph.py) | MST weight parity vs `nx.minimum_spanning_tree` (`test_dsa.py`) |
| **Prefix Trie (`insert` / `search_prefix`)** | [`backend/app/dsa/trie.py`](../backend/app/dsa/trie.py) | `GET /projects/{id}/autocomplete` ([`routes.py`](../backend/app/api/routes.py)) | Prefix matching oracle (`test_dsa.py`) |
| **Open-Addressing Linear-Probing Hash Table** | [`backend/app/dsa/hashtable.py`](../backend/app/dsa/hashtable.py) | [`discovery.py`](../backend/app/services/discovery.py) (`_deduplicate_candidates`), [`relations.py`](../backend/app/services/relations.py) | Insert/resize/collision/delete oracle vs Python `dict` (`test_dsa.py`) |

---

## 3. Discrete Mathematics (DM)

| Syllabus Concept | Hand-Built Module & Proof Reference | Endpoint / Analytics Caller | Verification Test |
|---|---|---|---|
| **Partial Orders, Hasse Diagram (Transitive Reduction) & Transitive Closure** | [`backend/app/dm/partial_order.py`](../backend/app/dm/partial_order.py), [`docs/DM_PROOFS.md`](DM_PROOFS.md) | `GET /projects/{id}/hasse` | 100 random DAG checks vs `nx.transitive_reduction` & `closure` (`test_dm.py`) |
| **DAG Dynamic Programming & Path Counting (Search Path Count / SPC)** | [`backend/app/dm/path_counting.py`](../backend/app/dm/path_counting.py), [`backend/app/dm/main_path.py`](../backend/app/dm/main_path.py) | [`evolution.py`](../backend/app/services/evolution.py) (`citation_backbone`) | Hand-calculated diamond DAG & `test_evolution.py`, `test_dm.py` |
| **Inclusion-Exclusion Principle & Multi-Source Overlaps** | [`backend/app/dm/inclusion_exclusion.py`](../backend/app/dm/inclusion_exclusion.py) | [`completeness.py`](../backend/app/services/completeness.py) (`GET /projects/{id}/completeness`) | Set-union equality & exact Venn breakdown (`test_dm.py`, `test_completeness.py`) |
| **Capture-Recapture Combinatorics (Lincoln-Petersen & Chapman Estimator)** | [`completeness.py`](../backend/app/services/completeness.py) | `GET /projects/{id}/completeness`, [`DiscoverPage.tsx`](../frontend/src/pages/DiscoverPage.tsx) | 500-trial 95% CI coverage >= 90% & `m < 5` suppression (`test_completeness.py`) |
| **Topological Prerequisite Ordering & Citation-DAG PageRank** | [`backend/app/dm/reading_path.py`](../backend/app/dm/reading_path.py), [`research_graph.py`](../backend/app/services/research_graph.py) | `GET /projects/{id}/reading-path` | Prerequisite ordering & invariance tests (`test_dm.py`, `test_embeddings_and_relations.py`) |
| **Bipartite Co-occurrence, PMI & Exact Hypergeometric Test** | [`gap_matrix.py`](../backend/app/services/gap_matrix.py) | `GET /projects/{id}/gap-matrix`, [`gaps.py`](../backend/app/services/gaps.py) | Known bipartite empty-cell CDF `C(5,3)/C(8,3)` (`test_gaps_matrix_and_grounding.py`) |
| **Graph Community Modularity, k-Core, Betweenness & Burt Constraint** | [`research_graph.py`](../backend/app/services/research_graph.py), [`clustering.py`](../backend/app/services/clustering.py) | `GET /projects/{id}/graph`, `POST /projects/{id}/clusters/recompute` | Connected-subgraph & NMI tests (`test_clustering.py`, `test_multilayer_graph.py`) |
