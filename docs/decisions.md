# Decisions and failed experiments

**Summary**

1. An enterprise RAG platform that answers questions about 13 SEC 10-K filings from 7 companies, with numbered citations, or an explicit refusal when the filings do not contain the answer.
2. Retrieval is hybrid search (dense + BM25, fused) with a cross-encoder reranker. Reference run (20261008_211316_recheck.json): hit@1 0.375, hit@5 0.625, MRR 0.503 on 16 scored questions.
3. Answers (one 10-question run, 20261008_113829): all 3 answerable questions gave the correct figure; all 4 out-of-scope questions and both known retrieval misses were refused. JPM total assets is wrong in some runs.
4. Status: runs locally in Docker, 21 unit tests pass, not deployed. Live answers depended on CraftX, which returned 502 errors during testing.
5. Context packing improved retrieval hits in a test and is disabled. It has not been tested at the answer level.

## Decision log

Date = date of the saved run that holds the evidence. "Not recorded" means no saved run is attached.

| ID | Decision | Status | Date |
|---|---|---|---|
| D1 | Section splitter merges all spans per Item | Accepted | Not recorded |
| D2 | Filing selection by fiscal year in the question, newest if none | Accepted | Not recorded |
| D3 | Context headers without filing dates | Accepted | 2026-10-03 |
| D4 | Eval fix: widened JPM snippet (eval correction) | Accepted | 2026-10-04 |
| D5 | Hybrid retrieval (RRF) and reranking | Accepted, with caveat | 2026-10-08 |
| D6 | Reranker score as a "not found" threshold | Rejected | 2026-10-03 |
| D7 | LLM verifier pass | Disabled | Not recorded |
| D8 | Prompt rules 8 to 11 (line items, measure labels, subset tables, balance-sheet identity) | Accepted, limitation stated | 2026-10-08 |
| D9 | Citation normalization | Accepted | Not recorded |
| D10 | Context packing | Proposed | 2026-10-08 |
| D11 | Answer cache | Proposed | Not measured |
| D12 | Single-turn /query for this release | Accepted | n/a |
| D13 | Request logging to Postgres | Accepted | Not recorded |
| D14 | Docker packaging | Accepted | Not recorded |

---

## D1. Section splitter merges all spans per Item

**Status:** Accepted

**Context:** The splitter divides filings by Item heading. When an Item appeared in several spans, the splitter kept only part of the text, so some filings were under-indexed.

**Options considered:**
- Keep the first span only
- Merge all spans for each Item (chosen)

**Decision:** Merge all spans for each Item before chunking.

**Evidence:** MSFT chunks went from 96 to 619 after the fix (handoff notes; no ingest log attached).

**Consequences:** Fixed silent data loss. Any future ingest change should be checked by chunk count per filing.

---

## D2. Filing selection by fiscal year

**Status:** Accepted

**Context:** Each company has several years of filings with the same line-item labels. Without a rule, a question about one year could return another year's figure.

**Options considered:**
- Always use the newest filing
- Use the fiscal year in the question, newest filing if none (chosen)
- No filter

**Decision:** Pick the filing by the fiscal year in the question. If the question names no year, use the newest filing.

**Evidence:** Rerank hit@5 rose from 0.50 to 0.62 and MRR from 0.364 to 0.395 (handoff notes; the before and after runs are not attached).

**Consequences:** The rule depends on detecting the year and ticker. A question without either gets no filing filter.

---

## D3. Context headers without filing dates

**Status:** Accepted

**Context:** Chunks did not say which company or section they came from, so the reranker and the LLM could not tell filings apart.

**Options considered:**
- No header
- Header with company, ticker, form type and cleaned section (chosen)
- Header that includes the filing date

**Decision:** Prepend company, ticker, form type and cleaned section to each chunk. The filing date is left out on purpose, so year questions do not favour the wrong filing.

**Evidence:** Headers run (20261003_231318_headers.json): rerank hit@1 0.375, hit@5 0.5625 (9/16), MRR 0.472. BM25 hit@5 0.625. The rerank MRR before headers was 0.395 (handoff notes; that run is not attached).

**Consequences:** The header appears twice in each prompt (source label and chunk text). This wastes some tokens. It was left in place to keep production stable.

---

## D4. Eval fix: widened JPM snippet

**Status:** Accepted. This is an eval correction, not a system improvement.

**Context:** The golden snippet for JPM did not match the text the system correctly retrieved, so a correct retrieval was scored as a miss.

**Options considered:**
- Keep the original snippet
- Widen the snippet to match the correct text (chosen)

**Decision:** Widen the JPM snippet. The system is unchanged.

**Evidence:** Rerank hit@5 went from 9/16 (0.5625, headers run 20261003) to 10/16 (0.625, snippets run 20261004). Hit@1 stayed at 0.375. MRR went from 0.472 to 0.503.

**Consequences:** The gain comes from correcting the measurement. Scores before and after this fix are not directly comparable.

---

## D5. Hybrid retrieval (RRF) and reranking

**Status:** Accepted, with caveat

**Context:** Dense search missed exact figures and table labels. BM25 finds exact terms but misses paraphrases.

**Options considered:**
- Dense only
- BM25 only
- Hybrid with reciprocal rank fusion, then reranking (chosen)

**Decision:** Fuse dense and BM25 results with reciprocal rank fusion (k=60), rerank 100 candidates with a cross-encoder, and return the top 5.

**Evidence:** Reference run (20261008_211316_recheck.json): hit@1 0.375, hit@5 0.625, MRR 0.503. BM25 alone reached hit@5 0.6875 in the snippets run (20261004_223232_snippets.json), above the reranked 0.625. The headers run shows the same pattern (BM25 0.625, rerank 0.5625).

**Consequences:** Reranking is best on hit@1 and MRR in these runs. BM25 is better on hit@5. The design was kept for hit@1 and MRR. Sixteen questions cannot settle this.

---

## D6. Reranker score as a "not found" threshold

**Status:** Rejected

**Context:** The system must refuse when the filings do not contain the answer. The reranker score seemed a natural cut-off.

**Options considered:**
- Threshold on the reranker score
- Refusal through the answer prompt (chosen)

**Decision:** Do not use a reranker threshold. Refusal is handled in the prompt.

**Evidence:** Headers run, not_found block: tsla-cybertruck-revenue scored 7.943, above the other three not-found questions (xom-revenue-2024 1.431, aapl-vision-pro-sales 2.242, nvda-ai-chip-share 3.558). Handoff notes record that some correct answers score below 7.9.

**Consequences:** Refusal depends on the LLM following the prompt. One out-of-scope question (Cybertruck) was refused in the answer run, so the prompt works for this case, but no score-based guard exists.

---

## D7. LLM verifier pass

**Status:** Disabled

**Context:** A second LLM call was meant to check that each answer is supported by its cited sources.

**Options considered:**
- Enable the verifier
- Disable the verifier (chosen)

**Decision:** Keep the code and set `verify_answers = false`.

**Evidence:** Verifier test output (handoff notes; output file not attached): SUPPORTED on 12 of 12 calls, including the known wrong JPM total-assets answer.

**Consequences:** Wrong answers that cite real sources pass unchecked. The verifier must be replaced by a better check before it is turned back on.

---

## D8. Prompt rules 8 to 11

**Status:** Accepted, limitation stated

**Context:** Early answers used a number with the wrong line-item name, or a total from a subset table such as variable interest entities (VIEs).

**Options considered:**
- No extra rules
- Rules for line-item names, measure labels, subset tables and the balance-sheet identity (chosen)

**Decision:** Include rules 8 to 11 in prompt v4.

**Evidence:** Answer run (20261008_113829): Microsoft net income and Apple revenue refused (2 of 2, the known misses). Tesla revenue, Autopilot verdict and Walmart segments correct (3 of 3). JPM total assets 43,295 million, the VIE total, in this run. Handoff notes: correct 4,424,900 million in about 3 of 5 runs.

**Consequences:** The rules reduce wrong figures but do not stop them. Rule 10 (subset tables) did not prevent the JPM answer. See Known limitations for the citation issue.

---

## D9. Citation normalization

**Status:** Accepted

**Context:** The model sometimes wrote lenticular brackets and special dashes, so citation numbers were not parsed and answers showed no citations.

**Options considered:**
- No normalization
- Normalize brackets, hyphens and invisible spaces before parsing (chosen)

**Decision:** Normalize model output before citations are parsed.

**Evidence:** The v1 answer run (answers_20261004_134947) had empty citation lists (handoff notes; file not attached). In the answer run 20261008_113829, all 3 answerable answers have parsed citations.

**Consequences:** Normalization fixes formatting only. Whether each citation supports its figure is a separate question (see Known limitations).

---

## D10. Context packing

**Status:** Proposed. Tested at the retrieval level. Not in `/query`.

**Context:** Overlapping and split chunks use up the prompt budget. Golden snippets that sit at ranks 6 to 10 never reach the LLM.

**Options considered:**
- No packing (current)
- Pack the top 5 candidates
- Pack the top 10 candidates under a 6,000-character budget (chosen for the test)

**Decision:** Keep packing out of `/query`. Propose it for an answer-level test before enabling.

**Evidence:**
- Packing the top 5 (20261008_211732_packed.json): hit@5 0.625 (unchanged), MRR 0.466.
- Packing the top 10 (20261008_213510_packed_top10_fixed.json): hit@1 0.375, hit@5 0.875 (14/16), MRR 0.5375.
- Unpacked control at top 10 (20261008_213822_control_top10.json): hit@5 0.625, MRR 0.503.
- Average context: 5,510 characters packed, 5,703 characters control.

**Consequences:** Packing gained four questions in the top 5 (tsla-rev-2025, nvda-rev-fy2026, aapl-supply-risk, wmt-segments) and never ranked a snippet lower than the control. Hit@1 did not change. Sixteen questions is a small sample. **Generation has not been tested with packed context.** Whether the LLM answers better is unknown.

---

## D11. Answer cache

**Status:** Proposed. Implemented in code. Behaviour not measured.

**Context:** Repeated questions cost an LLM call and several seconds of latency.

**Options considered:**
- No cache
- In-process cache with TTL, keyed on question, ticker, prompt version, model and corpus version (chosen)
- Redis, deferred to deployment

**Decision:** Use an in-process cache for a single process now. Move to Redis when the service runs with more than one process or restarts often.

**Evidence:** Not measured.

**Consequences:** The cache is lost on restart and is per process. Errors and truncated answers are never stored. `CORPUS_VERSION` must be bumped on every re-ingest.

---

## D12. Single-turn `/query` for this release

**Status:** Accepted for this release

**Context:** Follow-up questions need rewriting into standalone questions. This was deferred to keep the scope fixed.

**Options considered:**
- Conversation history with a rewrite step
- Single-turn `/query` (chosen)

**Decision:** Each request is answered on its own.

**Evidence:** Not measured.

**Consequences:** Follow-ups such as "and in 2024?" are not supported. The README says so.

---

## D13. Request logging to Postgres

**Status:** Accepted

**Context:** Failures had to be diagnosed, and retrieval had to be checked for consistency.

**Options considered:**
- Console logs only
- A `query_logs` table with question, chunk IDs, rerank scores, answer, cost, latency and error (chosen)

**Decision:** Log every request that reaches `/query`.

**Evidence:** During the CraftX 502 outage, failed requests were logged with chunk IDs and rerank scores (handoff notes). Repeated requests returned identical chunks and scores (handoff notes).

**Consequences:** Requests rejected before the endpoint (401, 422, and 429 from rate limits) are not logged. There is no retention policy yet.

---

## D14. Docker packaging

**Status:** Accepted

**Context:** The API and Postgres with pgvector needed a reproducible setup.

**Options considered:**
- Local install only
- Docker Compose with the API and database services (chosen)

**Decision:** CPU-only PyTorch, models downloaded at build time, offline mode at runtime, non-root user, health check, and an external data volume.

**Evidence:** Container healthy. Idle memory 472 MiB. 10,628 chunks intact after rebuild (handoff notes).

**Consequences:** The external volume survives `docker compose down -v`. The database password must match the one the volume was created with. The database port must be removed before any server deployment. Image size and peak memory were not measured.

---

## What failed

- **Section splitter dropped text.** MSFT had 96 chunks instead of about 600 (handoff notes). Fixed by D1.
- **A rule was imported but never called.** Its metrics matched the baseline exactly. Checking that the run actually changed caught it.
- **The first packing comparison had a scorer bug.** Run 210245 (not included here) compared top-5 results against a top-10 baseline, and its scorer check failed. The DROP verdict from that run was an artifact. The corrected comparison is 213510, which reports `scorer_matches_baseline: true`.
- **The verifier approved a known wrong answer** on all 12 calls (D7).
- **Invented golden snippets and fabricated terminal output** from another model were caught by checking against the database (handoff notes).
- **JPM total assets gave a confident, cited, wrong answer.** The question asks for the consolidated total, but the retrieved table was a VIE subset (43,295 million, "Total assets" in the variable interest entity table). The consolidated figure is 4,424,900 million. The same question gave the correct figure in about 3 of 5 runs (handoff notes).

---

## Known limitations

- **Two questions are never retrieved.** AAPL FY2025 revenue (aapl-rev-fy2025) and MSFT FY2026 net income (msft-ni-fy2026) are misses in the reference run, and the system refuses them. This is correct behaviour, but it cannot answer them. The data sits in table rows the retriever does not return.
- **Answers vary between runs at temperature 0.** JPM total assets: correct in about 3 of 5 runs (handoff notes).
- **Citations are not always correct.** In the answer run, the Autopilot answer cites [1] and [2], and [1] supports the figures. [2] is a shareholder class-action passage that does not contain them.
- **The citation preview for the Tesla answer did not show 94,827** in that run (20261008_113829). The preview fix was made after that run. It has not been rerun.
- **The eval gives the correct company ticker.** Real users may not. Ticker detection uses company names or symbols only.
- **HTML cleaning leaves glued words** (for example "ofour", "2025and") and messy section labels. JPM's financial statement content sits under "Item 15. Exhibits, Financial Statement Schedules" (visible in the snippets and headers run files).
- **Provider dependency.** A CraftX 502 outage lasted several minutes (handoff notes). Service stats also show 502 errors on 2026-10-06 to 2026-10-08.
- **Small sample.** There are 16 scored questions and 10 answer-suite questions. One question changes hit@5 by 0.0625. Differences of one to four questions are directional.

---

## Open items

- **Answer-level eval** (3 runs per question, citation correctness, latency p50 and p95). Not run. Accuracy claims in the README rest on one 10-question run until it is done.
- **Packing in the production path**, and a generation test with packed context. Not started.
- **Rerun the answer suite** after the preview fix, and check the Autopilot citation.
- **Deployment.** Remove the database port, trim `env_file`, and move to a host with at least 1 GB of RAM and hosted Postgres with pgvector. Peak memory and image size are not measured.
- **Caching.** Measure hit behaviour. Decide on Redis at deployment.
- **Tests and CI.** 21 unit tests cover packing, the tokenizer and generation helpers. Tests for chunking, cleaning, the API and the rate limit are not written. The CI workflow is written but not confirmed to pass on GitHub.
- **Frontend.** The static page is written. A manual browser test is not recorded.