# CH22 Evaluation Results

## Summary Metrics

| Method | Queries | Hit@3 | Relevant chunks recovered | Missed-but-relevant chunks |
| --- | --- | --- | --- | --- |
| Pure RAG | 6 | 3/6 | 7/18 | 11 |
| CtxFST entity-aware | 6 | 6/6 | 16/18 | 2 |

## Side-by-side Cases

### Q1. 我有哪些跟「用 AI 做語意搜尋」相關的筆記？

| Method | Top-3 chunks | Notes |
| --- | --- | --- |
| Pure RAG | `doc_43931a796cf75674` (0.196), `doc_98a7e45e0bf652a4` (0.192), `doc_7ef4df22bb7d5ce2` (0.135) | Top-3 did not overlap the expected entity set. |
| CtxFST entity-aware | `doc_9b60bf368b7a579a` (0.980), `doc_470f1eb51cba58a2` (0.901), `doc_5117fe624dac5b25` (0.884) | All top-3 chunks overlap expected entities: doc_9b60bf368b7a579a, doc_470f1eb51cba58a2, doc_5117fe624dac5b25. |

Expected difference: Many RAG/Vector DB/Embeddings/LanceDB chunks do not contain the phrase「語意搜尋」or「AI 搜尋」. TF-IDF will rank chunks that happen to say those exact words above the conceptually related ones. Entity-aware retrieval can traverse entity:semantic-search → entity:embeddings → entity:vector-db → entity:rag and recover the full ecosystem.

### Q2. 我想做一個聊天機器人，需要先學哪些基礎？

| Method | Top-3 chunks | Notes |
| --- | --- | --- |
| Pure RAG | `doc_01d95f723929525d` (0.000), `doc_02cc0f74352054ab` (0.000), `doc_054ebed5c2de5086` (0.000) | Relevant support in doc_01d95f723929525d; weaker fit in doc_02cc0f74352054ab, doc_054ebed5c2de5086. |
| CtxFST entity-aware | `doc_449ded6bfc995e35` (0.826), `doc_77dd0bf6997b5d74` (0.826), `doc_a80b1c0c667d553d` (0.826) | All top-3 chunks overlap expected entities: doc_449ded6bfc995e35, doc_77dd0bf6997b5d74, doc_a80b1c0c667d553d. |

Expected difference: No chunk is titled「聊天機器人基礎」. Baseline finds chunks about HTTP/Node.js but misses that they are prerequisites for Telegram Bot and Discord Bot. Entity-aware retrieval traverses entity:telegram-bot / entity:discord-bot → requires entity:nodejs, entity:http, entity:webhooks.

### Q3. 要理解一個完整的 AI agent runtime，我需要哪些底層知識？

| Method | Top-3 chunks | Notes |
| --- | --- | --- |
| Pure RAG | `doc_50612e609bd05175` (0.546), `doc_41d2434d28525f22` (0.515), `doc_4839fc8f779e5165` (0.512) | All top-3 chunks overlap expected entities: doc_50612e609bd05175, doc_41d2434d28525f22, doc_4839fc8f779e5165. |
| CtxFST entity-aware | `doc_41d2434d28525f22` (1.366), `doc_4839fc8f779e5165` (1.364), `doc_e28f69c1f4825bfe` (1.290) | All top-3 chunks overlap expected entities: doc_41d2434d28525f22, doc_4839fc8f779e5165, doc_e28f69c1f4825bfe. |

Expected difference: "AI agent runtime 底層知識" does not appear verbatim in most chunks. Baseline finds chunks that happen to say "agent" or "runtime" but misses the graph-encoded prerequisite cluster: LLM API, Tool Calling, Prompt Engineering, LangChain. Entity-aware retrieval fans out from entity:agent-architecture through its requires edges.

### Q4. 前端工程師想接觸 LLM 開發，有什麼入門路徑？

| Method | Top-3 chunks | Notes |
| --- | --- | --- |
| Pure RAG | `doc_16d0403dc9b056f6` (0.520), `doc_09b8d07e19955863` (0.416), `doc_b1cf217922525431` (0.393) | All top-3 chunks overlap expected entities: doc_16d0403dc9b056f6, doc_09b8d07e19955863, doc_b1cf217922525431. |
| CtxFST entity-aware | `doc_16d0403dc9b056f6` (1.064), `doc_b1cf217922525431` (0.978), `doc_f81c962ed0a75516` (0.974) | All top-3 chunks overlap expected entities: doc_16d0403dc9b056f6, doc_b1cf217922525431, doc_f81c962ed0a75516. |

Expected difference: "前端工程師" is not a keyword in any chunk. Baseline anchors on "LLM" and returns LLM API / OpenAI chunks that do not mention JavaScript or frontend context. Entity-aware retrieval traverses entity:javascript → entity:nodejs → entity:openclaw / entity:llm-api and surfaces the JS-native path to LLM development.

### Q5. 我對 Python Web 框架懂多少？

| Method | Top-3 chunks | Notes |
| --- | --- | --- |
| Pure RAG | `doc_515ee377094c5a32` (0.530), `doc_7a25af349fa35142` (0.500), `doc_bf19ea16b6b05e07` (0.334) | Top-3 did not overlap the expected entity set. |
| CtxFST entity-aware | `doc_515ee377094c5a32` (0.933), `doc_7a25af349fa35142` (0.913), `doc_66422274129957d5` (0.801) | Relevant support in doc_66422274129957d5; weaker fit in doc_515ee377094c5a32, doc_7a25af349fa35142. |

Expected difference: Chunks on FastAPI, Flask, Django, Pydantic each focus on the specific framework without repeating「Python Web 框架」as a category phrase. Baseline ranks by lexical overlap with「Web」and surfaces Web Standards / Edge Runtime chunks instead.

### Q6. 學了網頁操作自動化之後，還能拿來做哪些不只是爬蟲的事？

| Method | Top-3 chunks | Notes |
| --- | --- | --- |
| Pure RAG | `doc_01d95f723929525d` (0.000), `doc_02cc0f74352054ab` (0.000), `doc_054ebed5c2de5086` (0.000) | Top-3 did not overlap the expected entity set. |
| CtxFST entity-aware | `doc_c5743fa7e1465f7e` (0.965), `doc_c61c9f2dd8325b7d` (0.965), `doc_d2bbb5d2441050af` (0.965) | All top-3 chunks overlap expected entities: doc_c5743fa7e1465f7e, doc_c61c9f2dd8325b7d, doc_d2bbb5d2441050af. |

Expected difference: "網頁操作自動化"「爬蟲」do not appear as keywords in OpenClaw or E2E-testing chunks. Baseline returns only crawling/scraping-labeled chunks. Entity-aware retrieval goes from entity:browser-automation → relatedTo entity:puppeteer / entity:playwright and entity:openclaw (which requires browser-automation) to surface agent-runtime and testing use cases.

