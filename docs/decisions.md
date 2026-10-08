## Context packing: tested, not enabled in v1

- Setup: 16 scored questions, 6000-character budget, same rerank candidates.
- Production (top 5 chunks, scored at rank 5): hit@5 0.625, MRR 0.466.
- Packing over the top 10 candidates: hit@5 0.875, MRR 0.537.
- Unpacked control over the same top 10 candidates, same budget: hit@5 0.625, MRR 0.503.
- Packed never ranked a golden snippet lower than the control, and gained 4 questions.
- Not enabled. The gain is directional on 16 questions, and no answer-level test was run. Answer errors such as the JPM total-assets figure are not addressed by packing. Scope freeze applied.
- If revisited: run an answer eval with packing on and off (about 120 calls) before enabling.