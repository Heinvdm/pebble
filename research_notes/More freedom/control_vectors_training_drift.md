# Per-Pebble "neurons": control vectors, training on the phone, and measuring how different two Pebbles are (research notes, 20 October 2026)

Web research done for `plans/more-freedom.md` (pieces F6, F7 and F8). Read-only research; nothing measured on the phone. Tags: **(m)** measured by the cited source, **(v)** vendor claim, spec or official config, **(e)** estimate with the reasoning given. llama.cpp code was checked against master on 20 October 2026; the pinned build may use different names.

## 1. Control vectors (activation steering)

### How llama.cpp does it
- **History:** repeng (Theia Vogel, MIT) was the origin. PR #5970 added `--control-vector`, `--control-vector-scaled` and `--control-vector-layer-range`; PR #8060 added `build_cvec` to every model builder; PR #7514 added `cvector-generator` (its first output "outputs gibberish"); PR #8069 added `--method mean`.
- **Mechanism:** at the output of each layer in the range, one fixed vector is added to the residual stream for every token, prompt and generated. It's a constant bias that doesn't depend on the input. Several files are summed with their scales into one vector per layer.
- **File:** a GGUF with `general.architecture="controlvector"`, a model hint and a layer count, and one F32 tensor per layer (`direction.<layer>`, length = the model's width).
- **cvector-generator:** captures every layer's output at every token; pads positive and negative prompts to the same length; works on pos − neg. PCA is power iteration (defaults 1,000 iterations, batch 100). **The PCA output's sign is random per layer** (a TODO in the source; nothing fixes it). `--method mean` has no sign problem and normalises each layer to unit length, so the scale is in absolute residual-stream units. The default prompt files hold only 4 pairs.
- **C API:** on master `llama_set_adapter_cvec(ctx, data, len, n_embd, il_start, il_end)`; `data=NULL` clears it. Earlier names: `llama_control_vector_apply`, then `llama_apply_adapter_cvec`. Check the pinned build.
- **The cache:** changing the vector does **not** clear the KV cache; tokens already cached keep values computed under the old vector. Clear the memory and re-read for exact results. A llama-server restart empties the cache anyway; never restore saved slots across a vector change. (The server does clear a slot's cache when its LoRA set changes.)
- **Hot swap:** not upstream. Issue #10685 open since December 2024; PR #24740 (`/cvectors` endpoints) open with no review as of 11 October 2026. The ucvg.cpp fork (MIT) has per-request coefficients.

### Sizes
- **Gemma 4 E4B (v):** width 2,560, 42 layers, FFN 10,240, 8 attention heads, 2 KV heads, 18 KV-shared layers, sliding window 512 (5 sliding to 1 full), GELU-tanh, final logit softcap 30, vocabulary 262,144. Apache 2.0.
- **Gemma 4 E2B (v):** width 1,536, 35 layers, 1 KV head, 20 KV-shared layers.
- **A vector file:** E4B 41 × 2,560 × 4 B ≈ 410 KiB; E2B ≈ 204 KiB. Runtime cost: one add per layer.

### Does it work, and how well
- **CAA** (Rimsky et al., ACL 2024; Llama-2-Chat 7B/13B) (m): best around a third of the depth; multipliers ±1 for multiple choice, ±2 for open text; larger multipliers degraded the text; MMLU 0.63 → 0.57–0.65 at ±1.
- **Tan et al.** (NeurIPS 2024; 40 datasets) (m): "many of these datasets have almost half of the inputs being anti-steerable"; steerability is mostly a property of the dataset, not the model.
- **RepE** (Zou et al. 2023) (m): TruthfulQA MC1 on Llama-2-Chat-7B 31.0 → 47.9 with a contrast vector.
- **repeng** (Mistral-7B) (m): coefficient 2 is "middle-of-the-road"; at 3 the output fell into repetition loops; honesty at −2 produced absurd lies.
- **Scaling by the layer's own size:** Rogue Scalpel scales by c × the mean activation norm at that layer; on Llama-3.1-8B MMLU's sweet spot was c ≤ 0.75 (m). jukofyork's guidance: when n vectors are stacked, scale each between 1/n and √(1/n); leave out the last layer.
- **SteerScope** (October 2026; 23 methods, 15 measures) (m): "No evaluated activation steering method achieves higher efficacy without incurring greater composite side effects." None beat plain prompting on the balance of effect and side effects; fluency and relevance get worse on unfamiliar prompts.
- **Gemma 4:** no published layer or scale study found. Starting point (e): steer layers about 12–28, measure each layer's activation size and pre-scale each layer's direction inside the file (llama.cpp applies one scale per file). Layers 25–42 reuse K/V from earlier layers, so steering there acts only through queries and the residual path (unverified reading).

### Persona vectors (Chen et al. 2025)
- A trait vector is the difference in mean activation over response tokens from contrasting system prompts (5 pairs × 20 questions × 10 rollouts, with a judge model).
- Projection at the last prompt token predicts how strongly the trait shows (r = 0.75–0.83) (m); the activation shift from fine-tuning predicts the trait after it (r = 0.76–0.97) (m).
- Steering toward a trait during fine-tuning prevents it better than steering against it afterwards (m). Code Apache-2.0; needs a GPU and a judge model.

### Safety (the important part)
- **The refusal direction** (Arditi et al., NeurIPS 2024; 13 models from 1.8B to 72B incl. Gemma) (m): removing one direction removes refusal; adding it makes the model refuse harmless requests.
- **Rogue Scalpel** (ICLR 2026) (m): random unit vectors at mid depth raised harmful compliance from 0 % to 1–13 %; averaging 20 single-prompt jailbreak vectors gave a universal attack (50.4 % on Llama-3.1-70B; Falcon3-7B 5.7 % → 63.4 %). Harmless-looking features behaved similarly.
- **Steering-vector safety pitfalls** (TUM, 2026) (m): CAA vectors moved attack success by up to +57 % or −50 %; the shift tracks the vector's cosine with the refusal direction (R² ≥ 0.85 above 3B); projecting out the refusal component cut the shift by only about 15–25 %.
- **Steering externalities** (2026) (m): steering toward harmless goals like "comply strictly" or "answer in JSON" raised jailbreak success above 80 %.
- **Honesty:** the same vectors can steer toward lying (repeng −2; RepE).
- **Fine-tuning drift is a bigger risk than steering:** a narrow fine-tune on 6,000 insecure-code examples made GPT-4o give misaligned answers to unrelated questions about 20 % of the time (Betley et al., ICML 2025 / Nature 2026) (m); a "toxic persona" feature controls it, and a few hundred harmless samples restore alignment (OpenAI, ICLR 2026) (m).
- **Memories drift behaviour too:** stored memories act like implicit steering vectors, moving behaviour by up to +3.6 on a 1–5 scale (2026).
- **Guard practices (none is a guarantee):**
  1. Scale caps relative to each layer's activation size, a cap on the summed vector's size, and the 1/n–√(1/n) rule for stacked vectors.
  2. Geometry checks: cosine of each vector with the refusal direction and with persona directions (harm, flattery, made-up facts); project out the refusal component, knowing it only partly helps.
  3. An evaluation gate before adopting any vector or adapter: refusal rate on a fixed harmful-request set, an over-refusal set, coherence (perplexity or KL on fixed text, plus a repetition check), and the persona checks.
  4. Runtime monitoring of projections onto those directions.
  5. Rollback history. Harmful vectors generalise poorly across prompts, so a few test prompts won't catch them.

### Per-user and evolving precedents
- Closest match: "After Talking with 1,000 Personas" (arXiv 2602.04000, 2026): per-user, per-category vectors as running means of preferred minus rejected activations; strength rises on negative feedback, is clipped, and decays without recent feedback; a 4-bit Llama-3.2-3B "on a modern smartphone" (runtime not named).
- No write-up was found of control vectors running on a phone, or of a personality evolving over a long time.

### Building vectors on this phone (E4B, at 25–45 tokens/s reading) (e)
- Pairs used elsewhere: llama.cpp demo 4; Arditi 128 + 128; CAA 290–1,000; persona vectors up to 1,000 rollouts a side.
- Each pair is two forward passes of about 40–60 tokens: about 2–5 s a pair. 50 pairs ≈ 2–4 min; 500 ≈ 17–40 min; 1,000 ≈ 35–80 min, before loading and heat.
- Memory: the tool keeps every token row for every layer twice, about 0.84 MB a token row. 50 pairs × 40 tokens ≈ 1.7 GB fits; 200 × 60 ≈ 10 GB doesn't. A small patch keeping only a per-pair mean row brings 1,000 pairs under 1 GB.
- PCA about 0.5–2 min on the processor; the mean method takes seconds. Run with llama-server stopped.

**Bottom line (section 1)**
- **Feasible now:** nightly vectors built on the phone with `--method mean` from Pebble's own logged contrasts, blended slowly into the stored one (a moving average), with a capped size, the safety gates, then a server restart to apply it. Or several PC-built trait vectors whose per-Pebble weights drift, summed with `--control-vector-scaled`.
- **Needs a stronger phone:** PCA over hundreds of long pairs; generating hundreds of responses a night.
- **Unsound:** per-request vectors in upstream llama-server; treating steering as safe by construction; expecting reliable per-input effects.

## 2. Training on the phone (LoRA)

### llama.cpp / ggml, October 2026
- The 2023 LoRA fine-tune was removed (PR #8669, July 2024). PR #10544 (May 2025) added `llama_opt_*` and `finetune.cpp`: full fine-tuning only, F32 KV cache, "24 GB" for LLaMA 3.2 1B, no LoRA options.
- Community QLoRA PRs were all closed unmerged in 2026. An open bug: gradient accumulators aren't cleared between steps (issue #30083).
- **Upstream ggml's backward pass can't train Gemma 4 at all** (no GELU/tanh/GEGLU backward, and the logit softcap), **nor LFM2/LFM2.5** (the short-conv block's `ssm_conv` and `concat`) (code reading).
- **QVAC Fabric fork (Tether):** `llama-finetune-lora` (rank 8, alpha 16, attention by default), quantised bases, CPU/Vulkan/Metal; lists Gemma 4; context 512 recommended on mobile. Vendor numbers for Qwen3-1.7B Q8 LoRA per epoch (v): 1 h 40 m on Adreno 830, 7 h 40 m on Mali-G715 (Pixel 9). Its README warns "Qwen3-4B causes OOM on most mobile devices." Not upstream; Mali-G78 untested.

### Phone fine-tuning research
- **MeBP** (Apple, EMNLP 2025; iPhone 15 Pro Max; INT4 base, LoRA, sequence 256) (m): Qwen2.5-0.5B 3.85 s a step, 320 MB; Qwen2.5-1.5B 9.09 s, 460 MB; Gemma3-1B 9.48 s, 569 MB; Gemma3-4B 28.58 s, 1,029 MB. Zeroth-order is faster per step but needs 10–100× more steps. iOS only.
- **MobiZO** (OnePlus 12 NPU, TinyLlama-1.1B) (m): 5.76 s a step; no licence file (all rights reserved).
- **MobileFineTuner** (C++, Apache-2.0; Pixel 7 Pro and 8) (m): Qwen2.5-0.5B LoRA about 6.1 GB peak, about 3.5 tokens/s; some Gemma 3 270M runs failed on 12 GB Pixels.
- **ExecuTorch training:** "experimental … technical preview"; can't yet save trained weights natively.
- **Termux** has a `python-torch` package; LoRA with transformers and PEFT would run, untested on phones.

### An overnight (8 h) estimate for the Pixel 6 Pro (e)
| | 230–350M (LFM2.5-230M, Gemma 3 270M, Qwen3-0.6B) | Gemma 4 E2B | Gemma 4 E4B |
|---|---|---|---|
| Runtime today | PyTorch with PEFT (LFM2 needs this path); MobileFineTuner (not LFM2); QVAC for Qwen3/Gemma 3 | QVAC fork, processor, untested on Tensor G1 | QVAC fork, processor |
| Training speed | 5–30 tokens/s | 1–5 tokens/s | 0.5–2 tokens/s |
| Tokens a night | 0.15–0.85 M | 30k–150k | 15k–60k |
| Peak memory | 1.5–4 GB | 6–8 GB, llama-server stopped | 9–12+ GB |
| Verdict | **Feasible now** | Marginal; an E2B adapter can't be used on E4B | **Infeasible with today's tools** |
- Heat and power (e): about 50–60 % of peak speed after 15–30 minutes of sustained load; 8 h at 3–5 W is 25–40 Wh, more than the 19 Wh battery, so training must run on the charger, which wears the battery. Duty-cycle it, gate it on battery temperature, and use only the big cores.

### Gemma 4 and LoRA in llama.cpp (code reading)
- Inference is LoRA-aware for q/k/v, the per-layer input gate and projection, attention output and the FFN; `per_layer_model_proj` uses a plain matrix multiply, so a LoRA there would be silently ignored.
- Conversion should handle the text tower's linear layers; embedding LoRA is rejected. No working Gemma 4 LoRA GGUF report was found; test early.
- Adapter sizes (e): E4B rank 8 attention-only ≈ 9–10 MB F16; rank 16 all linear ≈ 72 MB.

**Bottom line (section 2)**
- **Feasible now:** an overnight LoRA or full fine-tune of a ≤350M model; per-Pebble drift of the mixing scales of PC-trained E4B adapters (each change clears the cache and forces a full re-read, so rarely); forward-only tuning of a handful of scalars (vector or adapter weights) by calling the vector setter from a small tool, a few thousand steps a night (untested idea).
- **Needs a stronger phone or another engine:** E2B or E4B LoRA overnight (16–24 GB, an Adreno 8-series GPU, or a MeBP-style Android engine).
- **Infeasible on the Pixel 6 Pro:** E4B LoRA; any LoRA training in upstream llama.cpp; any training of Gemma 4 or LFM2 in upstream ggml; training on the Mali-G78.

## 3. Persona drift and measuring how different two Pebbles are
- **Li et al. (COLM 2024):** two instructed chatbots talk for 8 rounds and are probed each round, scored by deterministic Python checks; large models drift significantly within 8 rounds, and drift toward the other bot's persona; attention to the system prompt drops at turn boundaries. This protocol (two Pebbles talking, deterministic persona checks) can be reused directly.
- **Questionnaires are unreliable on small models:** base models "unacceptable", 7B chat models "neutral to good" (Serapio-García et al., Nature Machine Intelligence 2025); equivalent wordings and option order change scores (Gupta et al. 2024); low negation consistency (Shu et al., NAACL 2024). TRAIT (8K scenario questions) is more reliable than self-report. **The Chameleon's Limit (2026): personas collapse into a few clusters across all 8 models tested, and persona fine-tuning narrows them further.** No reliability study for ~4B models; measure Cronbach's α directly.
- **Practical measures and their cost on the phone (E4B, estimates):**
  1. A trait-projection fingerprint: mean projection onto K trait directions over a fixed probe set; distance between Pebbles. Forward passes only, about 3,000 tokens, 1–2 minutes.
  2. Output-distribution distance: `llama-perplexity --kl-divergence-base` on one Pebble, `--kl-divergence` on the other, over a fixed transcript (mean KL, same-top-token %); 1.5–3 minutes per 4k tokens; about 1 GB of logits per 2k scored tokens.
  3. Response-embedding distance: at least 3 samples per probe per Pebble; the ratio of between-Pebble to within-Pebble distance (above 1 = the persona is detectable).
  4. Questionnaires scored by log-probability, averaged over option orders and 2–3 wordings, with Cronbach's α; a shift smaller than the spread across wordings is noise.
  5. Instruction-stability checks, Li et al. style.
- **Bottom line (section 3):** measures 1, 2 and 5 nightly, 3 and 4 weekly on this phone. Unreliable: self-report questionnaires as ground truth for a 4B model, and any single-sample comparison.

## Not verified
- The vector API's name in the pinned build; whether a Gemma 4 LoRA converts and loads; QVAC on Tensor G1; the 54 % sustained-speed figure; the embedding-ratio measure in The Chameleon's Limit (summary only); PockEngine code; MNN LLM LoRA training; how much memory weight repacking duplicates.

## Licences
llama.cpp MIT; QVAC fabric-llm.cpp MIT (its fine-tune repo Apache-2.0); MobileFineTuner Apache-2.0; apple/ml-mebp Apple's permissive licence; MobiZO no licence (all rights reserved); ExecuTorch BSD; MNN Apache-2.0; PyTorch BSD-3; transformers and PEFT Apache-2.0; repeng MIT; jukofyork control-vectors Apache-2.0; persona_vectors Apache-2.0; ucvg.cpp MIT. Gemma 4 Apache 2.0; LFM2.5 LFM Open License v1.0.

## Sources
llama.cpp: https://github.com/ggml-org/llama.cpp/pull/5970 · https://github.com/ggml-org/llama.cpp/pull/7514 · https://github.com/ggml-org/llama.cpp/pull/8069 · https://github.com/ggml-org/llama.cpp/pull/11110 · https://github.com/ggml-org/llama.cpp/blob/master/include/llama.h · https://github.com/ggml-org/llama.cpp/blob/master/src/llama-context.cpp · https://github.com/ggml-org/llama.cpp/tree/master/tools/cvector-generator · https://github.com/ggml-org/llama.cpp/blob/master/tools/server/server-context.cpp · https://github.com/ggml-org/llama.cpp/issues/10685 · https://github.com/ggml-org/llama.cpp/pull/24740 · https://github.com/ggml-org/llama.cpp/blob/master/examples/training/README.md · https://github.com/ggml-org/llama.cpp/pull/10544 · https://github.com/ggml-org/llama.cpp/pull/8669 · https://github.com/ggml-org/llama.cpp/pull/22705 · https://github.com/ggml-org/llama.cpp/issues/30083 · https://github.com/ggml-org/llama.cpp/blob/master/ggml/src/ggml.c · https://github.com/ggml-org/llama.cpp/blob/master/src/models/gemma4.cpp · https://github.com/ggml-org/llama.cpp/blob/master/src/models/lfm2.cpp · https://github.com/ggml-org/llama.cpp/blob/master/convert_lora_to_gguf.py · https://github.com/ggml-org/llama.cpp/blob/master/tools/perplexity/README.md
Models: https://huggingface.co/google/gemma-4-E4B-it · https://huggingface.co/google/gemma-4-E2B-it/blob/main/config.json · https://docs.liquid.ai/lfm/models/lfm25-230m
Steering: https://github.com/vgel/repeng · https://vgel.me/posts/representation-engineering/ · https://arxiv.org/abs/2407.12404 · https://neurips.cc/virtual/2024/poster/93224 · https://aclanthology.org/2024.acl-long.828/ · https://arxiv.org/abs/2310.01405 · https://arxiv.org/abs/2507.21509 · https://www.anthropic.com/research/persona-vectors · https://github.com/safety-research/persona_vectors · https://arxiv.org/abs/2406.11717 · https://arxiv.org/abs/2509.22067 · https://arxiv.org/abs/2603.24543 · https://arxiv.org/abs/2602.04896 · https://arxiv.org/abs/2406.15518 · https://arxiv.org/abs/2610.07722 · https://arxiv.org/abs/2604.04064 · https://arxiv.org/abs/2502.17424 · https://arxiv.org/abs/2506.19823
Per-user and hobby steering: https://arxiv.org/abs/2602.04000 · https://arxiv.org/abs/2505.04260 · https://arxiv.org/abs/2408.11779 · https://arxiv.org/abs/2510.22256 · https://arxiv.org/abs/2510.27206 · https://arxiv.org/abs/2605.24941 · https://huggingface.co/jukofyork/creative-writing-control-vectors-v3.0 · https://github.com/jukofyork/control-vectors · https://github.com/Egor4More/ucvg.cpp · https://github.com/Siddhesh2377/llama.cpp-android
On-device training: https://arxiv.org/abs/2510.03425 · https://github.com/apple/ml-mebp · https://arxiv.org/abs/2409.15520 · https://github.com/leigao97/MobiZO · https://arxiv.org/abs/2310.17752 · https://arxiv.org/abs/2407.01031 · https://arxiv.org/abs/2512.08211 · https://github.com/AndyLu666/MobileFineTuner · https://huggingface.co/blog/qvac/fabric-llm-finetune · https://huggingface.co/blog/qvac/fabric-llm-finetune-bitnet · https://github.com/tetherto/qvac-fabric-llm.cpp · https://github.com/tetherto/qvac-rnd-fabric-llm-finetune · https://github.com/pytorch/executorch/tree/main/extension/training · https://github.com/alibaba/MNN
Hardware: https://en.wikipedia.org/wiki/Google_Tensor · https://www.anandtech.com/show/17032/tensor-soc-performance-efficiency · https://www.91mobiles.com/hub/?p=471239 (unverified)
Persona measurement: https://arxiv.org/abs/2402.10962 · https://arxiv.org/abs/2307.00184 · https://doi.org/10.1038/s42256-025-01115-6 · https://arxiv.org/abs/2309.08163 · https://arxiv.org/abs/2311.09718 · https://arxiv.org/abs/2406.14703 · https://arxiv.org/abs/2407.18416 · https://arxiv.org/abs/2604.24698
