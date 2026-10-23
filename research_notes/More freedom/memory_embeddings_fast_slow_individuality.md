# Memory, embeddings, fast and slow thinking, individuality (research notes, 20 October 2026)

Web research done for `plans/more-freedom.md` (pieces F3 and F7 wait on it). Read-only research; nothing measured on the phone. Phone figures use the speed study's rates: prompt reading 25–45 tokens/s, writing 4–7 tokens/s on the Pixel 6 Pro. Anything marked **(est.)** is arithmetic, not a measurement.

**Cost ruler (est.)**
- Each 25 tokens added to the per-turn prompt costs 0.6–1.0 s; 100 tokens cost 2.2–4.0 s.
- Re-reading a 1,500-token stable prefix after an edit takes 33–60 s.
- Writing 100 tokens takes 14–25 s.
- One forced-choice decode step takes 0.14–0.25 s.

Embedding and vector search cost milliseconds. The real cost of memory is the tokens it adds to the prompt.

## 1. Memory designs

### Generative Agents (Park et al., UIST 2023)
- **Stores** a "memory stream" of natural-language observations, each with a creation time, a last-access time and an importance score.
- **Retrieval score** = recency + importance + relevance, each min-max normalised to 0–1 over the candidates, all weighted 1.
  - Recency decays by 0.995 per game-hour since the memory was last retrieved (est.: ×0.89 a day, ×0.43 a week, half-life about 138 h).
  - Importance is a model rating from 1 to 10 at write time ("1 is purely mundane … 10 is extremely poignant").
  - Relevance is the cosine similarity between the memory's embedding and the query's.
- **Reflection** fires when the summed importance of recent events passes 150 (about 2–3 times a game day): take the 100 most recent records, ask for the 3 most salient high-level questions, retrieve for each, ask for 5 insights with cited evidence, store those as new memories.
- **Planning:** the day in 5–8 chunks, then hours, then 5–15-minute chunks; regenerated from the point of any reaction.
- **Results:** TrueSkill μ full 29.89; no reflection 26.88; no reflection or planning 25.64; human crowdworkers 22.95; none of the three 21.21. Knowledge of a party spread 4 % → 52 %, network density 0.167 → 0.74, 5 of 12 invitees came. Cost: thousands of dollars of tokens.
- **Here:** the scoring is pure numpy. Importance can be one decode step from a cached instruction, read through `n_probs` (est. about 1 s a memory). Reflection over 100 records is about 2,000 tokens (est. 45–80 s reading plus 15–25 s writing): a night job.

### MemGPT / Letta, and sleep-time compute
- **MemGPT (Packer et al. 2023):** main context = read-only system instructions + a read/write working context (core memory) + a message queue headed by a recursive summary; outside it, recall storage (every message, searchable) and archival storage (a vector database). Default "human" and "persona" blocks are 2,000 characters each. A warning at about 70 % of the context, a flush at 100 % that evicts about half with a new summary. Deep memory retrieval accuracy: GPT-4 32.1 % → 92.5 %; GPT-4 Turbo 35.3 % → 93.4 %; GPT-3.5 38.7 % → 66.9 %.
- **Letta today:** memory blocks with a label, description, value, character limit and read-only flag, shown in the prompt with current and maximum sizes; tools `memory_insert`, `memory_replace`, `memory_rethink`.
- **Sleep-time agents (Letta, experimental):** the talking agent searches memory but can't edit core blocks; a sleep-time agent rewrites them in the background every N steps or on compaction ("dreaming"), with an optional second review. Letta suggests a fast model for talking and a slower, bigger one for sleep-time work.
- **Sleep-time compute (Lin et al. 2025, arXiv 2504.13171):** reasoning about the context before any question arrives. About 5× less test-time compute for the same accuracy on stateful GSM and AIME; more offline compute adds +13 % (GSM) and +18 % (AIME); shared across 10 related questions, the cost per question falls 2.5×. The gain grows with how predictable the question is. On coding only about 1.5× at low budgets.
- **Here:** the best fit. Core blocks live in the cached stable start of the prompt; an idle or night job edits them and the prompt is re-read once.

### Reflexion (Shinn et al. 2023)
- Verbal self-reflections written after failed trials, 1–3 kept.
- ALFWorld 130/134 (+22 % absolute over 12 trials); HotPotQA +20 %; HumanEval 91.0 % vs 80.1 % for GPT-4. Worse on MBPP (77.1 %), no WebShop gain.
- A small model (starchat-beta) gained nothing (0.26 → 0.26): the authors call self-correction "an emergent quality of stronger, larger models."

### ExpeL (Zhao et al., AAAI 2024)
- Insights from comparing failures with successes; operations ADD, EDIT, UPVOTE, DOWNVOTE; a new insight starts at 2 and is deleted at 0. Also retrieves the 2–6 most similar past successes by embedding.
- HotpotQA 28.0 → 39.0; ALFWorld 40 → 59; FEVER transfer 63 → 70. With GPT-3.5 instead of GPT-4 for insights, HotpotQA fell 39.0 → 32.0.
- **Here:** vote counters suit rules of thumb: auditable and self-pruning.

### Voyager (Wang et al. 2023)
- A library of skill code, added only after self-verification passes, the top 5 retrieved by description embedding. 3.3× more unique items, 2.3× longer distances, milestones up to 15.3× faster. Without self-verification, items found fell 73 %.
- **Here:** procedural memory should be small behaviour scripts kept only after they worked.

### A-MEM (Xu et al. 2025)
- Notes with content, time, keywords, tags, a context line, an embedding and links; a new note links to chosen neighbours among its top 10 and updates them.
- Large gains for small models on LoCoMo multi-hop (Qwen2.5-1.5B F1 4.25 → 24.32; Llama-3.2-1B 7.38 → 17.80); about 1,200 tokens per memory operation. In Mem0's comparison it scored lowest (J 48.38).
- **Here:** about 1,200 tokens a note is est. 27–48 s of reading each, so night batches only.

### Mem0 (Chhikara et al. 2025)
- Extraction from a running summary, the last 10 messages and the newest pair; each candidate fact compared with its 10 most similar memories and the model picks ADD / UPDATE / DELETE / NOOP. The graph variant marks contradicted facts invalid instead of deleting them.
- LoCoMo judge scores: full context 72.90; Mem0g 68.44; Mem0 66.88; Zep 65.99; best RAG 60.97; OpenAI memory 52.90. p95 latency 1.44 s vs 17.1 s for full context; about 1.8k retrieved tokens vs 26k.
- Caveats: self-reported; full context still wins; Letta's plain file-tools agent scored 74.0 % on the same test, and Letta concludes current memory benchmarks "may not be very meaningful." LoCoMo talks are only about 300 turns.

### CoALA (Sumers et al., TMLR 2024)
- Working memory (this decision), episodic (past experiences), semantic (knowledge of the world and of itself), procedural (weights, code, prompts).
- Writing procedural memory is "significantly riskier" than episodic or semantic.
- **For Pebble:** the per-turn prompt is working memory; the diary is episodic; facts and people records are semantic; rules of thumb, the self-description and skills are procedural and need the strictest write rule.

### Consolidation, forgetting and "dreaming"
- **MemoryBank:** retention R = e^(−t/S); S starts at 1 and grows by 1 with each recall, which also resets t. Daily summaries roll up into a global summary and a portrait of the person.
- **Lyfe Agents:** summarise-and-forget; new memories too similar to old ones are dropped (cosine threshold); the model picks a high-level option and cheap plain checks decide when it ends. 10–100× cheaper than Generative Agents.
- **LightMem (ICLR 2026):** sensory filter → topic-grouped short-term → long-term with an offline sleep-time update; accuracy up to +7.7 % / +29.3 % with up to 38× fewer tokens.
- **EM-LLM (ICLR 2025):** a new episode starts when a token's surprise passes the recent mean plus γ standard deviations; the surprise signal comes free from llama.cpp's log-probs.
- **HippoRAG (NeurIPS 2024):** a knowledge graph plus personalised PageRank; up to +20 % on multi-hop questions, 10–30× cheaper than iterative retrieval.
- **Experience-following (Xiong et al. 2025):** storing everything hurt (−3.7 to −12.1 points); strict selective adding gained +3.4 to +21.8; deleting records whose later uses went badly (after 3–5 uses) cut memory about 3× at −1.2 to +4.2 points. Later outcomes are free quality labels.
- **ACE (ICLR 2026), "context collapse":** one whole-context rewrite shrank an 18,282-token context to 122 tokens and accuracy fell 66.7 → 57.1, below the 63.7 baseline. The fix: itemised bullets with an id and helpful/harmful counters, small incremental updates, de-duplication by embedding (+10.6 % on agents, +8.6 % on finance). **A direct warning about Pebble's third-person running summary.**
- **LongMemEval:** store per round, not per session; index by the record plus facts extracted from it (+9.4 % recall, +5.4 % accuracy); time-aware query expansion (+6.8–11.3 % temporal recall). Commercial assistants lose about 30 % accuracy over long interactions.
- **"Language Models Need Sleep" (Behrouz et al. 2026):** sleep as distillation plus RL "dreaming" into the weights. Not feasible on this phone.

### Agents that learn their own prompts and rules
- OPRO +8 % on GSM8K, up to +50 % on BBH; DSPy +25 % (GPT-3.5) and +65 % (llama2-13b-chat) over few-shot; GEPA +6 % on average over GRPO with up to 35× fewer rollouts; Dynamic Cheatsheet took GPT-4o on Game of 24 from 10 % to 99 %; Agent Workflow Memory +24.6 % and +51.1 % relative; ReasoningBank up to 20 % relative with items of a title, a one-line description and content, at most 3 per trajectory; Self-Refine about +20 % with GPT-3.5/4, but Vicuna-13B couldn't give feedback in the required form.
- **Risks:**
  - No outside feedback, no reliable gain: intrinsic self-correction doesn't improve reasoning and sometimes hurts (Huang et al., ICLR 2024).
  - Drift: persona and instruction drift within about 8 rounds (Li et al., COLM 2024); semantic drift through repeated summarising; context collapse (ACE).
  - Poisoning through ordinary conversation: MINJA planted memories through normal queries alone (98.2 % injection success, 76.8 % attack success); AgentPoison over 80 % success at under 0.1 % poisoned records; ChatGPT "SpAIware" (2024), an injected memory that persisted into every later chat.
  - Self-modification gaming: Darwin Gödel Machine went 20.0 % → 50.0 % on SWE-bench, but some variants bypassed the hallucination checker, more often when the checker was visible to the agent.

**Bottom line (section 1)**
- A Letta-style self-description, household rules and people digest in the cached stable start of the prompt, most stable first.
- Edit them only in idle or sleep-time jobs, as itemised ExpeL/ACE bullets (id, helpful/harmful counters, ADD/UPDATE/DELETE/NOOP), never whole rewrites; then re-read once.
- Per turn, 1–3 short notes scored Generative-Agents style in numpy, in the changing tail (at most about 60 tokens ≈ 1.3–2.4 s).
- Lessons only from outside signals (corrections, sensed failures). Tag who said what, keep an unchangeable seed identity, and gate rule writes harder than fact writes.

## 2. Small embedding models, offline on an Android processor

| Model | Params | Dim | Max tokens | Licence | MTEB avg / retrieval | ONNX int8 | GGUF |
|---|---|---|---|---|---|---|---|
| all-MiniLM-L6-v2 | 22.7M | 384 | 256 | Apache-2.0 | 56.26 / 41.95 | 23 MB | community builds |
| snowflake-arctic-embed-xs | 22M | 384 | 512 | Apache-2.0 | – / **50.15** | 23 MB | none official |
| snowflake-arctic-embed-s | 33M | 384 | 512 | Apache-2.0 | – / 51.98 | – | – |
| bge-small-en-v1.5 | 33.4M | 384 | 512 | MIT | 62.17 / **51.68** | 34 MB | Q8_0 36.8 MB |
| gte-small | 33.4M | 384 | 512 | MIT | 61.36 / 49.46 | not checked | none found |
| multilingual-e5-small | ~118M | 384 | 512 | MIT | English 57.9; MIRACL 60.8 | 118 MB | – |
| granite-embedding-small-english-r2 | 47M | 384 | 8192 | Apache-2.0 | retrieval 50.8 / 53.9 (MTEB v2) | – | – |
| nomic-embed-text-v1.5 | ~137M | 768 (Matryoshka) | 8192 | Apache-2.0 | 62.28 | – | Q8_0 140 MiB |
| EmbeddingGemma-300M | 308M | 768 (Matryoshka) | 2048 | Gemma terms | MTEB v2 English 69.67 | q4 197 MB | Q8_0 334 MB |
| potion-base-8M (Model2Vec) | 7.5M static | 256 | n/a | MIT | 51.08 / 31.11 | numpy only | n/a |

- MTEB v1 and v2 scores aren't comparable. Each model needs its own query/passage prefixes. EmbeddingGemma activations don't support fp16. Model2Vec runs in numpy but its package needs the `tokenizers` library (no Chaquopy wheel found); retrieval quality is much lower.
- **Measured phone speeds (none found for the Pixel 6 Pro):** all-MiniLM-L6-v2 on ExecuTorch (about 80 tokens): Galaxy S24 54 ms, OnePlus 12 28 ms. EmbeddingGemma on LiteRT (Galaxy S25 Ultra, 4 threads): 66 ms at 256 tokens, 169 ms at 512; peak memory 110 MB.
- **Pixel 6 Pro estimate:** a 20-token note in about 10–30 ms with MiniLM or arctic-xs, about 50–150 ms with EmbeddingGemma (est.). Don't run the embedder on the big cores while llama.cpp writes.
- **Search without a server:** numpy brute force over 10k × 384 floats is 15.4 MB in fp32 (7.7 MB fp16), est. 1–5 ms a query. sqlite-vec (MIT/Apache, pre-v1) isn't packaged for Android, and Android's own SQLite can't load extensions; not worth it below about 100k vectors.
- **llama-server as a second embedding instance** works (`--embeddings`, its own process and port, `-ub` at least the longest note); it can't share the Gemma instance.

**Bottom line (section 2):** English: snowflake-arctic-embed-xs (Apache-2.0, 23 MB) or bge-small-en-v1.5 (MIT, 34 MB) through ONNX Runtime in Kotlin. Multilingual households: multilingual-e5-small (MIT, 118 MB) or EmbeddingGemma (Gemma terms, about 200 MB, about 10× the compute). fp16 vectors brute-forced in numpy; no index needed. Embed notes when written or at night; at turn time embed only the query.

## 3. When to think deeply, cheaply

- **Talker-Reasoner (DeepMind 2024):** a fast talker replies from the latest belief state while a slower reasoner updates it in the background; the talker waits only when planning. No numbers published.
- **SOFAI / SOFAI-LM (IBM 2025):** take the fast answer when confidence is high enough for the stakes, else run the slow solver if its expected gain beats its cost. SOFAI-LM: 42 % vs 2 % on graph colouring, and faster.
- **SwiftSage (2023):** a small fast model hands over on four triggers: stuck (5 steps without reward), invalid action, critical decision, unexpected observation. ScienceWorld 84.7 vs Reflexion 45.3, with 757 tokens an action vs 1,856–2,983.
- **RouteLLM:** 35–85 % lower cost at 95 % of GPT-4's quality. **FrugalGPT:** up to 98 % lower cost.
- **Self-RAG** retrieves when P(retrieve) > 0.2; **FLARE** when any token in the drafted next sentence falls below 0.4–0.8.
- **Simple uncertainty gates (Moskvoretskii et al. 2025):** matched or beat dedicated pipelines with 1.3–2.0 model calls a question; signals read from the model's logits were the best at "knowing what it knows".
- **KnowNo (CoRL 2023, robots):** make the decision multiple choice and read the letters' next-token probabilities; calibrated on 400 examples; asked for help 14 % less often on hardware.
- **Rational metareasoning (2024):** 23–32 % fewer reasoning tokens for small models at slightly better accuracy.
- **From llama.cpp:** `/completion` with `n_probs` returns each generated token's log-prob and its top alternatives; `post_sampling_probs` gives probabilities after sampling. Minimum token probability, top-N entropy or a forced-choice letter's probability come from these.
- **Do these predict errors in small models?** Top-answer probability predicts correctness about as well as the model is accurate (Plaut et al. 2025: AUROC 52.0–72.9 for 7–8B models; thresholds from only 20 labelled questions helped in every condition). **A small model's stated confidence is near chance** (Gemma3-4B 0.544/0.527; under 2B about 0.5; Shen, Aug 2026). Semantic entropy is better (AUROC 0.790) but needs 10 samples. All uncertainty methods are weak on subtle instruction-following errors.

**Bottom line (section 3):** with one model, "slow" means a bigger token budget (recall, a plan, a self-check, a background job), not a bigger model. Trigger it with SwiftSage-style rules (stakes, surprise, stuck, invalid) plus a free `n_probs` signal on short forced-choice outputs, with thresholds calibrated on the household's own corrections. Never use the model's stated confidence. Answer now from the current belief block, queue deliberation for idle time, and precompute for routines.

## 4. Individuality from the same weights

- **Generative Agents:** 25 agents on one model with different seed memories spread information and formed relationships differently.
- **Takata et al. 2024:** 10 identical Llama-2-7B agents with no persona went from 9 INFJ + 1 INTJ to 5 distinct types in 100 steps; their memories spread widely while their messages clustered (single run).
- **Project Sid (Altera 2024):** 30 agents with the same personality and goal took up persistent, different roles; without the social modules they didn't specialise.
- **Park et al. (June 2026), 1,052 real people:** agents built from 2-hour interviews reproduced each person's survey answers at 83–86 % of the person's own two-week consistency; demographics alone 74 %. Memory individuates the same weights, measurably.
- **Convergence pulls the other way:** populations form shared conventions and biases no single agent had, and a committed minority can flip them (Ashery et al., Science Advances 2025); language aligns with partners (Frisch & Giulianelli 2024); persona drift within about 8 rounds (Li et al. 2024).
- **MicroVerse (Aug 2026):** an unchangeable "soul file" plus a changeable current identity, edited only at importance-gated reflection; thresholds 40 / 80 / 150 → 5 / 2 / 1 of 25 agents changed identity. Drift measured by line diffs (token Jaccard ≥ 0.8, sequence similarity ≥ 0.85), not cosine. Preliminary, one model.
- **How divergence has been measured:** questionnaire probes before and after; embedding spread of memories against messages; entropy and persistence of roles; diffs of the identity against its unchangeable original; network and information-spread measures.

**Bottom line (section 4):** different seeds plus different memories plus different company do diverge measurably, but shared weights pull toward each other and toward the model's default persona. Give each Pebble an unchangeable seed plus a changeable self-description and rules that change only at reflection; track a fixed monthly battery of probes (questionnaire plus forced-choice dilemmas) and diff the self-description against the seed.

## Unverified or flagged
- No Pixel 6 Pro measurements of embedding speed or log-prob overhead were found.
- Chaquopy's numpy BLAS backend is not confirmed.
- Memory-R1's gain numbers were not checked.
- The arXiv HTML page of ReasoningBank (2509.25140) ended with a block of instructions aimed at extraction tools; it was treated as page data and not acted on.

## Sources
Generative Agents https://arxiv.org/abs/2304.03442 · MemGPT https://arxiv.org/abs/2310.08560 · Letta memory blocks https://docs.letta.com/guides/agents/memory-blocks · Letta sleep-time https://docs.letta.com/guides/agents/architectures/sleeptime · Sleep-time compute https://arxiv.org/abs/2504.13171 · Letta memory benchmark https://www.letta.com/blog/benchmarking-ai-agent-memory · Reflexion https://arxiv.org/abs/2303.11366 · ExpeL https://arxiv.org/abs/2308.10144 · Voyager https://arxiv.org/abs/2305.16291 · A-MEM https://arxiv.org/abs/2502.12110 · Mem0 https://arxiv.org/abs/2504.19413 · LoCoMo https://arxiv.org/abs/2402.17753 · CoALA https://arxiv.org/abs/2309.02427 · MemoryBank https://arxiv.org/abs/2305.10250 · Lyfe Agents https://arxiv.org/abs/2310.02172 · LightMem https://arxiv.org/abs/2510.18866 · EM-LLM https://arxiv.org/abs/2407.09450 · HippoRAG https://arxiv.org/abs/2405.14831 · Experience-following https://arxiv.org/abs/2505.16067 · ACE https://arxiv.org/abs/2510.04618 · LongMemEval https://arxiv.org/abs/2410.10813 · Language Models Need Sleep https://arxiv.org/abs/2606.03979 · OPRO https://arxiv.org/abs/2309.03409 · DSPy https://arxiv.org/abs/2310.03714 · GEPA https://arxiv.org/abs/2507.19457 · Dynamic Cheatsheet https://arxiv.org/abs/2504.07952 · Agent Workflow Memory https://arxiv.org/abs/2409.07429 · ReasoningBank https://arxiv.org/abs/2509.25140 · Self-Refine https://arxiv.org/abs/2303.17651 · Huang et al. https://arxiv.org/abs/2310.01798 · Li et al. https://arxiv.org/abs/2402.10962 · MINJA https://arxiv.org/abs/2503.03704 · AgentPoison https://arxiv.org/abs/2407.12784 · Darwin Gödel Machine https://arxiv.org/abs/2505.22954 · all-MiniLM-L6-v2 https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2 · bge-small-en-v1.5 https://huggingface.co/BAAI/bge-small-en-v1.5 · snowflake-arctic-embed-xs https://huggingface.co/Snowflake/snowflake-arctic-embed-xs · multilingual-e5-small https://huggingface.co/intfloat/multilingual-e5-small · EmbeddingGemma https://huggingface.co/google/embeddinggemma-300m · nomic-embed-text-v1.5 https://huggingface.co/nomic-ai/nomic-embed-text-v1.5 · potion-base-8M https://huggingface.co/minishlab/potion-base-8M · ExecuTorch benchmarks https://docs.swmansion.com/react-native-executorch/docs/0.5.x/benchmarks/inference-time · sqlite-vec https://github.com/asg017/sqlite-vec · llama-server README https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md · Talker-Reasoner https://arxiv.org/abs/2410.08328 · SOFAI-LM https://arxiv.org/abs/2508.17959 · SwiftSage https://arxiv.org/abs/2305.17390 · RouteLLM https://arxiv.org/abs/2406.18665 · FrugalGPT https://arxiv.org/abs/2305.05176 · Self-RAG https://arxiv.org/abs/2310.11511 · FLARE https://arxiv.org/abs/2305.06983 · Moskvoretskii et al. https://arxiv.org/abs/2501.12835 · KnowNo https://arxiv.org/abs/2307.01928 · Rational metareasoning https://arxiv.org/abs/2410.05563 · Plaut et al. https://arxiv.org/abs/2402.13213 · Shen https://arxiv.org/abs/2608.05064 · Semantic entropy https://pmc.ncbi.nlm.nih.gov/articles/PMC11186750 · Heo et al. https://arxiv.org/abs/2410.14582 · Takata et al. https://arxiv.org/abs/2411.03252 · Project Sid https://arxiv.org/abs/2411.00114 · Park et al. https://arxiv.org/abs/2411.10109 · Ashery et al. https://arxiv.org/abs/2410.08948 · Frisch & Giulianelli https://arxiv.org/abs/2402.02896 · MicroVerse https://arxiv.org/abs/2608.15844
