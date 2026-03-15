# CH22 Evaluation Results

## Summary Metrics

| Method | Queries | Hit@3 | Relevant chunks recovered | Missed-but-relevant chunks |
| --- | --- | --- | --- | --- |
| Pure RAG | 6 | 6/6 | 17/18 | 1 |
| CtxFST entity-aware | 6 | 6/6 | 18/18 | 0 |

## Side-by-side Cases

### Q1. 我有哪些後端經驗？

| Method | Top-3 chunks | Notes |
| --- | --- | --- |
| Pure RAG | `about:backend-summary` (0.440), `project:service-platform` (0.073), `principle:retrieval-gap` (0.072) | All top-3 chunks overlap expected entities: about:backend-summary, project:service-platform, principle:retrieval-gap. |
| CtxFST entity-aware | `about:backend-summary` (1.266), `project:service-platform` (0.824), `workflow:deployment-stack` (0.751) | All top-3 chunks overlap expected entities: about:backend-summary, project:service-platform, workflow:deployment-stack. |

Expected difference: Only returns the high-level summary chunk and misses project notes that never say backend explicitly.

### Q2. 我對資料庫其實懂哪些東西？

| Method | Top-3 chunks | Notes |
| --- | --- | --- |
| Pure RAG | `reference:database-tradeoffs` (0.317), `project:embedded-analysis-store` (0.259), `principle:retrieval-gap` (0.154) | All top-3 chunks overlap expected entities: reference:database-tradeoffs, project:embedded-analysis-store, principle:retrieval-gap. |
| CtxFST entity-aware | `reference:database-tradeoffs` (1.297), `project:embedded-analysis-store` (1.100), `principle:retrieval-gap` (0.650) | All top-3 chunks overlap expected entities: reference:database-tradeoffs, project:embedded-analysis-store, principle:retrieval-gap. |

Expected difference: Misses chunks that mention WAL, compaction, or embedded storage without using the word database.

### Q3. 我在哪裡寫過 Docker 和 Kubernetes 的關係？

| Method | Top-3 chunks | Notes |
| --- | --- | --- |
| Pure RAG | `workflow:deployment-stack` (0.620), `about:backend-summary` (0.215), `project:service-platform` (0.162) | All top-3 chunks overlap expected entities: workflow:deployment-stack, about:backend-summary, project:service-platform. |
| CtxFST entity-aware | `workflow:deployment-stack` (1.329), `project:service-platform` (0.738), `about:backend-summary` (0.728) | All top-3 chunks overlap expected entities: workflow:deployment-stack, project:service-platform, about:backend-summary. |

Expected difference: May retrieve only one deployment note and ignore adjacent project chunks linked through shared deployment entities.

### Q4. 我的 Go 經驗有哪些？

| Method | Top-3 chunks | Notes |
| --- | --- | --- |
| Pure RAG | `skill:go-service-runtime` (0.354), `about:backend-summary` (0.301), `project:service-platform` (0.257) | All top-3 chunks overlap expected entities: skill:go-service-runtime, about:backend-summary, project:service-platform. |
| CtxFST entity-aware | `skill:go-service-runtime` (1.222), `about:backend-summary` (1.088), `project:service-platform` (1.076) | All top-3 chunks overlap expected entities: skill:go-service-runtime, about:backend-summary, project:service-platform. |

Expected difference: Retrieves chunks that say Go directly, but may not surface related gRPC service notes or backend summary context.

### Q5. 如果我要把現有服務做得更適合高併發，我以前寫過哪些相關想法？

| Method | Top-3 chunks | Notes |
| --- | --- | --- |
| Pure RAG | `skill:go-service-runtime` (0.347), `project:service-platform` (0.065), `about:backend-summary` (0.047) | All top-3 chunks overlap expected entities: skill:go-service-runtime, project:service-platform, about:backend-summary. |
| CtxFST entity-aware | `skill:go-service-runtime` (1.255), `project:service-platform` (0.870), `about:backend-summary` (0.820) | All top-3 chunks overlap expected entities: skill:go-service-runtime, project:service-platform, about:backend-summary. |

Expected difference: The wording is abstract and may not align strongly with any single chunk even though the idea is present in Go runtime notes.

### Q6. 我在哪裡寫過 retrieval 為什麼需要 entity graph？

| Method | Top-3 chunks | Notes |
| --- | --- | --- |
| Pure RAG | `principle:retrieval-gap` (0.329), `workflow:agent-runtime` (0.134), `about:backend-summary` (0.041) | Relevant support in principle:retrieval-gap, workflow:agent-runtime; weaker fit in about:backend-summary. |
| CtxFST entity-aware | `principle:retrieval-gap` (1.106), `workflow:agent-runtime` (0.783), `reference:database-tradeoffs` (0.367) | All top-3 chunks overlap expected entities: principle:retrieval-gap, workflow:agent-runtime, reference:database-tradeoffs. |

Expected difference: May find the explanation chunk but miss the runtime note that motivates it from planner behavior.

