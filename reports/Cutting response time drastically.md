# Cutting response time drastically

19 October 2026. The owner: "10–30 seconds is way too long for a response, let's figure out how we can cut that drastically, do some research."

**Owner's answers (19 October 2026):**
1. **No E2B talker.** E4B does everything, sped up with Gemma 4's drafter: the "fallback" column of the time budget is the plan (first words about 1.1–1.9 s, a short answer about 2.6–4.9 s on the Pixel 6 Pro). A stronger phone gets there faster on the same model.
2. **Read early:** yes. What someone says to Pebble is read before they finish, in memory on the phone only, only for speech that looks addressed to Pebble, and thrown away otherwise.
3. **Background turns:** they give way as soon as someone starts talking to Pebble, and none run during a live conversation, until **30 s** of quiet (not 60). A dropped thought comes back later.
4. **Pre-written social lines:** yes.
5. **Reorder the reply prompt:** yes, checked on the evals.
6. **Spoken hold later on fast rungs:** yes. The glance and tilt stay at 0.3 s. A hold is spoken only if nothing is ready by about 1.0 s, on rungs where answers usually come under 1.2 s. `plans/thinking-out-loud.md` follows this.

This is research, not code. Nothing here has run on the Pixel 6 Pro. Phone speeds are estimates unless they are marked as measured, and each source says what kind of number it is. It builds on `reports/Making Pebble quicker to respond.md` (the first study) and does not repeat it. The tweaks from that study (thinking off, the 8,192 window, the cache ladder, the reply sharing the turn's prompt) are assumed built.

## The plan in short

Today the wait is mostly the model **reading**. A reply that misses the cache rereads 800 to 1,300 tokens at an estimated 20 to 40 a second: 25 to 45 s. A reply can also queue behind a background turn. Writing is the smaller part: about 1 s for the first few words.

The step change: **do the reading before the person stops talking, and make sure nothing else is using the model when they do.** Then only about a dozen tokens are left to read, and what remains is writing the first few words.

In build order:

1. **Never wait for background work.** When someone starts talking to Pebble, any background turn gives way at once. Today a cancel cannot cut into a batch of prompt reading, and the batch is 2,048 tokens, so a reply can wait over a minute even after a cancel. A batch of 64 to 128 fixes that.
2. **Keep the next reply read ahead, and read the person's words while they talk.** The reply's prompt is put in order: everything known before they speak first, their words last. Whenever the prompt's start changes (an exchange, a turn, a summary, someone arriving), the phone reads it in idle time. While they talk, each new chunk of words is read as it comes. When they stop, about 12 tokens are left.
3. **A talker that writes faster than Pebble speaks.** On the Pixel 6 Pro, Gemma 4 E2B does everyday talk and E4B keeps the background turns, tools, pictures and deeper questions. If both don't fit in memory, E4B does both with Gemma 4's drafter. The phone measures which.
4. **Instant lines for social talk:** hello, thanks, good night, "how are you", the name alone. They are written ahead in Pebble's own words by its own model, in idle time, and picked by rules. A greeting can be written while a known face walks in.
5. **Smaller cuts:** the drafter (`draft-mtp`); a start at the pause for every turn, not only questions; an end-of-turn model so statements don't wait 0.65 s or get cut off; a prompt start that doesn't change when someone arrives; heat handling.
6. **Later rungs:** Google's LiteRT-LM on the CPU (2 to 3 times faster prompt reading on these cores) and its GPU path (3 to 10 times faster reading, no faster writing) for cold starts and pictures, switched on only where they measure faster and give correct output.

## Time budget

From the moment they stop talking. "A short answer" is about 20 tokens (about 15 words, 5 to 6 s of speech). "First real words" are the start of the answer itself, not a hold.

| Step | Today (first speed pass built) | Pixel 6 Pro: E2B talks, E4B thinks | Pixel 6 Pro fallback: E4B does both, with the drafter | Stronger phone: E4B talks |
| --- | --- | --- | --- | --- |
| The turn closes | 0.25 s for a complete question or command; 0.65 s for anything else | Writing starts at the pause, 0.25 s; the sound waits for the close | Same | Same |
| Waiting for a background turn | 0 to 40 s; over 60 s at worst | 0; at most about 2 s | 0; at most 2 to 4 s | 0 |
| Reading what is left of the prompt | About 4 s with a warm cache (about 130 tokens); 25 to 45 s on a miss (800 to 1,300) | 0.15 to 0.3 s (about 12 tokens) | 0.3 to 0.5 s | Under 0.1 s |
| Writing the first spoken part (about 5 tokens) | About 1 s | 0.4 to 0.6 s | 0.5 to 1.0 s | 0.2 to 0.3 s |
| Voice to first sound | About 0.05 s (measured on the emulator) | About 0.05 to 0.1 s | Same | Same |
| **First real words** | **About 5 s at best, about 28 s on average, over a minute behind a turn** | **0.9 to 1.3 s** | **1.1 to 1.9 s** | **0.6 to 0.8 s** |
| Writing the rest of a 20-token answer | 3 to 4 s | 1.2 to 1.9 s | 1.5 to 3.0 s | 0.5 to 1.0 s |
| **Short answer written** | **About 8 s at best, about 32 s on average** | **2.1 to 3.2 s** | **2.6 to 4.9 s** | **1.1 to 1.8 s** |
| The same on a hot phone (25 % slower) | | First words 1.0 to 1.5 s; answer 2.6 to 4 s | First words 1.4 to 2.3 s; answer 3.3 to 6 s | |
| A cold miss (after a restart, or no time to read ahead) | 30 to 120 s | 13 to 24 s (a compact talk prompt of about 1,200 tokens) | 45 to 120 s | 5 to 10 s on the CPU, 1 to 3 s on a GPU |

All Pixel 6 Pro and stronger-phone figures are estimates (see "Phone speeds" in the evidence). They assume llama.cpp on the CPU, 2 × X1 + 2 × A76. On a cool phone the writing runs ahead of the speaking once it starts: Pebble speaks about 3.5 tokens a second, and every plan column writes faster than that. So a 20-token answer is fully spoken about 6 to 7 s after they stop, with no gaps. On a hot phone the fallback column writes at about speaking speed, so short gaps between sentences can appear there.

A hold (a glance and tilt at 0.3 s, a spoken hold when the answer is late) still covers the first second, as `plans/thinking-out-loud.md` plans.

## The three changes that give the most

1. **Reading ahead and reading while they talk** (plan steps 2 and part of 5). It takes the 25 to 45 s of reading on a miss, and the 4 s even on a hit, down to 0.15 to 0.5 s. That is most of today's wait. It works with today's llama-server: checked on the PC with the pinned build (see "Checked on the PC").
2. **Never waiting for background work** (plan step 1). It removes the 0 to 40 s queue, and the worst case of over a minute. It is a small change: a smaller batch, a cancel at voice start, and no turn while a conversation is live.
3. **A faster talker** (plan step 3). With the reading gone, writing sets the time. Gemma 4 E2B writes about twice as fast as E4B on these cores: first words from about 1.5 s to about 1 s, a short answer from about 4 s to about 2.5 s, with margin left for heat. The drafter is the fallback when both models don't fit.

## What it costs

| Change | Memory | Heat and power | Quality | Effort | Risk |
| --- | --- | --- | --- | --- | --- |
| 1. Never wait for background work | None | Less (fewer turns during talk) | A background thought is dropped and comes again later | Small: `-b`/`-ub` in `LlamaPlan.args`; a cancellable turn call in `mind/llama.py`; the beat in `life/loop.py` and `conversation/core.py` holds off while someone talks | Low. A cancelled turn must not mark the mind as down |
| 2. Read ahead and read while they talk | A few prompt states more in the RAM cache, which is already bounded | About half of the big cores while someone talks to Pebble (E4B), a quarter (E2B); short bursts after each exchange | None: the same words reach the model, in a different order | Medium: the reply prompt's order (`conversation/core.py` `_observation`, `life/turn.py` `reply`), a warm call, warming on partials and after each change | Low to medium: reading ahead for speech that turns out not to be for Pebble wastes a little work |
| 3. E2B talks, E4B thinks | About 2 GB more resident (E2B QAT 2.62 GB file; its per-layer table mostly stays on disk), so it may not fit with everything else. Only the phone can tell | More cores busy only while talking | E2B is weaker: MMLU-Pro 60.0 against 69.4, tool use (Tau2) 24.5 against 42.2, instruction following (IFEval) 94.6 against 96.7. For short warm talk the gap should be small, but nobody has measured persona at this size | Medium: a third server and profile, routing, the memory rung, evals | Medium. Needs the conversation evals and a memory measurement |
| The drafter (fallback, or on top) | About 100 MB | Slightly more work per word | None: it never changes what is written | Small | Medium: untested with `--swa-full` and the projector; less gain at temperature 0.7 |
| 4. Instant social lines | None | A few idle-time writes | Must not sound canned. Needs variety rules | Small to medium | Low |
| 5. End-of-turn model | 7 to 8 MB | One small model run per pause | Fewer cut-offs | Small to medium | Low (it can only wait longer or confirm) |
| 6. LiteRT-LM (later) | E2B 1.7 to 2.6 GB | GPU: unknown, Mali throttles hard | Mali GPU: wrong digits in about 6 to 9 % of tool calls without float32 activations | Large: a second runtime in Kotlin, no GBNF in the Kotlin API | High on Mali, medium on the CPU |

## How the phone picks its rung

This follows "The Pixel 6 Pro is the floor" in CLAUDE.md. At first start, and on "measure again" (which should also call `LlamaChoice.forget()`), the keeper runs a talk bench against each candidate model with the eyes and ears running:

1. **Tail read:** read a fixed 2,500-token reply prompt, then send 12 new tokens plus the template tail. Time to the first written token.
2. **First part and answer:** time to the 5th and the 20th written token.
3. **Hot:** repeat after 3 minutes of a talk-like duty cycle (bursts of reading and writing). Log `PowerManager.getThermalHeadroom`. Use the hot numbers.
4. **Drafter:** on and off. Keep it only if the hot 20-token time is at least 15 % better.
5. **Batch:** prompt-reading speed at `-b`/`-ub` 64, 128 and 512. Take the smallest within 5 % of the best.
6. **Cancel:** start a 1,500-token read, cancel after 1 s, time a one-token request. It must answer within 2.5 s.
7. **Memory:** the resident memory of each server (`VmRSS` in `/proc/<pid>/status`) with the eyes running. At least 1.5 GB must stay free with both.

Then the talk rungs, from the top:

| Rung | Talk | Turns, tools, pictures, deep questions | Taken when |
| --- | --- | --- | --- |
| GPU (stronger phones, later) | E4B or E2B on LiteRT-LM GPU | E4B | It measures faster and passes a fixed check of numbers and JSON |
| A | E4B (with the drafter if it pays) | E4B | Hot: first words within 1.5 s and a short answer within 5 s |
| B | **E2B** (with its drafter if it pays) | E4B | Both fit in memory and A fails. **Expected on the Pixel 6 Pro** |
| C | E4B with the drafter | E4B | B doesn't fit in memory |
| D | E2B | E2B | Hot or slow; a step down for the day |

"First words" here is 0.25 s for the close + the tail read + the first part + 0.1 s for the voice. In daily use the brain logs, for each reply, the tokens read after the person stopped, the time to the first token and the time to first words. If the 10-minute median runs 30 % over the bench, it steps down a rung until the phone is cool. A step down can never make Pebble slower than the rung below it, because the rung below is what it falls back to.

## Decisions for the owner

1. **Let Gemma 4 E2B do everyday talk on the Pixel 6 Pro**, with E4B for turns, tools, pictures and deeper questions. *Recommended: yes*, if it passes the conversation evals (`conversation/eval.py` plus a persona and honesty set) within a margin the owner sets, and as a measured rung, never forced.
2. **Read what someone says to Pebble before they finish.** It stays in memory on the phone, as today. It only happens for speech that looks addressed to Pebble (its name, looking at it, alone with it), and it is thrown away if the speech was not for Pebble. *Recommended: yes.*
3. **A background turn gives way whenever someone starts talking to Pebble, and no turn runs during a live conversation** (until, say, 60 s of quiet). The dropped thought comes again later. *Recommended: yes.*
4. **Social lines written ahead, in Pebble's own words.** Its own model writes them in idle time. Plain code picks them with variety rules: never the same twice running, refreshed often. They count as its own words, like the phrasebook in `plans/thinking-out-loud.md`. *Recommended: yes.*
5. **The reply prompt's order changes. The model sees the same content.** The person's words come last. "Who is here now" moves from the system text into the message, and the system text lists the household instead, so an arrival doesn't force a reread. The first study treated prompt changes as the owner's call. *Recommended: yes, checked on the evals.*
6. **The first spoken hold.** With answers at about 1 s, a spoken hold at 0.6 s comes just before most answers. The studies found that a gesture works better than a filler word, and filler words wear thin. *Recommended:* keep the glance and tilt at 0.3 s, and say the first spoken hold only if nothing is ready by about 1.0 s on rungs where first words usually come under 1.2 s. The plan's stages are timed, so this is a timing change, not a new design.

## Evidence

### Where the time goes today (new findings)

- **A cancel waits for the current batch.** The pinned llama-server reads a prompt in one `llama_process` call per logical batch and sets no abort callback (`tools/server/server-context.cpp`). A cancel or a new request is handled only between batches. `LlamaPlan.args` sets no `-b`/`-ub`, so the batch is the default 2,048 tokens. At 20 to 40 tokens a second that is 50 to 100 s. A turn's whole prompt (about 700 tokens on average) is therefore one call that nothing can interrupt. Measured on the PC (below): cancelling 3 s into a long read, the next request waited 3.19 s at batch 2,048 and 0.13 s at 512 and 64.
- **A turn closes later for statements.** `conversation/turns.py` closes a turn 0.25 s after the speech ends when the words look complete (a question of 3 or more words, a command, a short "done" word), and 0.65 s otherwise, waiting up to 1.5 s for the final words. `core._changed` starts an early reply at a pause only for complete words. So "I had a long day" gets no head start and waits 0.65 s.
- **`n_predict: 0` still writes one token** in the pinned build, although its README says it writes none (the stop check runs only after the first token, `server-context.cpp` near "stopped by limit"). Measured on the PC: `predicted_n` 1. So each read-ahead request costs one written token (about 0.1 s on E2B, 0.2 s on E4B).
- **Rules already take commands off the model's path.** Confident requests run from `understand/rules.py` with no model. An action the request reader found ends the reply early (`_considered`). The name alone and "stop listening" get fixed lines. What reaches the main model is talk: chat, questions, jokes, feelings. That is the path this plan speeds up.

### Checked on the PC with the pinned llama.cpp

The pinned commit (`android/llama/src`, built outside the repo for x86-64 Windows) was run with a 15-million-parameter test model (stories15M Q4_0, chatml template, `-np 1`, `--cache-ram 256`). This shows how the cache behaves, not how fast the phone is. Gemma 4 needs `--swa-full` (built) for the same behaviour.

| Request (chat endpoint, `cache_prompt` on) | Tokens reused | Tokens read |
| --- | --- | --- |
| Cold reply (system 2,300 tokens + 6 exchanges + "hello") | 0 | 2,360 |
| Read ahead: the prompt up to the opening quote, 1 token written | 2,339 | 18 |
| The words so far, 2 / 5 / 8 / 11 words | 2,339 to 2,350 | 21 to 23 (new words + the template tail) |
| The final reply, all 12 words | 2,353 | 27 |
| A background turn with a different system text | 15 | 2,415 |
| The next reply after that turn | 2,379 | **1** (restored from the RAM cache) |
| The following reply, history one exchange longer | 2,355 | 77 |

- So reading the words as they come works through the ordinary chat endpoint: each request rereads only the new words and the template tail. For Gemma 4 the tail is `<turn|>`, a newline, `<|turn>model`, and the empty thought, about 9 tokens.
- The RAM prompt cache gives the reply its warm state back after a turn ran in between.
- Gemma 4's template trims the message, so a partial ending in a space does no harm. A word the recognizer revises only costs a reread from that word.

Cancel test (1 thread, a 12,718-token prompt at about 290 tokens a second, cancelled 3 s in, then a 4-token request):

| `-b` = `-ub` | Prompt speed | The next request answered after |
| --- | --- | --- |
| 2,048 | 290 tokens/s | 3.19 s |
| 512 | 276 tokens/s | 0.13 s |
| 64 | 288 tokens/s | 0.13 s |

On this tiny model a small batch cost no reading speed. On the phone that must be measured (bench step 5): a small batch rereads the weights more often.

### Reading while they talk

- **How it works with llama-server:** keep the stable part first, with the person's words at the end. Send a request with `max_tokens: 1` when at least 4 new stable tokens have arrived, with at most one in flight. Leave out the last word, which may still change. At a pause, send the real request. Each read-ahead request costs about one forward pass plus one written token: about 0.3 to 0.5 s on E4B and 0.15 to 0.25 s on E2B (estimate). Partials come every 480 ms, and people say about 3 tokens a second, so the model is busy about half the time while someone talks (E4B) or a quarter (E2B).
- **Reading ahead between exchanges:** the next reply's prompt start changes after every exchange (masked private lines, the answer), every turn, every summary and every arrival. Each change is read in idle time with the same one-token request, so the next reply starts warm. Today, the first reply after some turns rereads 2,106 tokens (first study).
- **Literature:**
  - LiveMind (2024; text, not speech; Llama-3-70B) cut latency by 84 % on average on MMLU (5.39 s → 0.86 s) by reading the input sentence by sentence as it came in. Word-level splitting cost much more work.
  - Meta's "Can speech LLMs think while listening?" (2025) reported 70 % lower latency with no accuracy loss.
  - An Amazon patent describes an early endpoint at about 200 ms, with the result held until the final transcript confirms it.
  - GLaDOS (a hobby voice assistant on llama.cpp, now on Gemma 4 E4B) ends a turn after 416 ms of silence and drafts speculative replies in a spare slot. It publishes no read-ahead numbers.
- **How often the words change:**
  - Google's on-device recognizer (2020): 0.15 to 1.19 revised segments per utterance. About half are only case, punctuation or numerals. Longer partial intervals cut instability by about 70 %.
  - Google's streaming prefetch: 1.29 to 1.90 prefetches per query (0.3 to 0.9 wasted calls), arriving 140 to 370 ms before the endpointer.
  - Guessing words not yet spoken does not work: over 80 % of predicted future words are wrong beyond 300 ms. Speculate only on words already heard.

### Runtimes, the GPU and the TPU on this phone

- **The Tensor G1 TPU is out of reach.** LiteRT's NPU path covers Tensor G5 and G6 only. NNAPI is deprecated since Android 15 and never ran an LLM. ML Kit's Gemini Nano starts at the Pixel 9. Nobody has run an LLM on the G1's TPU.
- **The Mali-G78 GPU:** only LiteRT-LM is a real option, and it is fragile.
  - Gemma 4 E2B ran on its GPU path on a Galaxy S21 (Exynos 2100, also a Mali-G78), but no speed was posted.
  - 2026 bugs on Mali: a crash at start on "Pixel 6 to 9" (patched 27 September 2026); multi-turn GPU decode failing on Tensor G3 and G4 (a fix landed 12 September 2026); float16 errors that mangle digits in 6 to 9 % of tool-call arguments and degrade long prompts (an opt-in float32 setting fixes it, at an unmeasured cost).
  - In Google's own Gallery app, GPU writing is often slower than CPU on Pixel and Mali phones.
- **Measured GPU against CPU on Mali** (LiteRT-LM):
  - Pixel 8 (Mali-G715), one user, E2B: reading 53 → 427 tokens/s, writing 10.6 → 11.9.
  - RK3588 board (Mali-G610, 4 × A76), E2B: reading 124 → 374, writing 12.3 → 8.7; E4B: 53 → 75, writing 5.6 → 4.5. The author calls the Mali GPU "a prefill/TTFT accelerator here, not a decode accelerator".
  - Google's ML Drift paper, Pixel 9 (Mali-G715): Gemma 2 2B at 729 reading and 18.4 writing.
- **Pixel 6 Pro estimate on the LiteRT-LM GPU:** E2B reading 300 to 700, writing 8 to 14; E4B reading 120 to 280, writing 4 to 8. Writing is no faster than on the CPU, because both are limited by the same memory (51.2 GB/s in theory).
- **LiteRT-LM on the CPU (XNNPACK)** reads 2 to 3 times faster than llama.cpp on A76 cores. On a Raspberry Pi 5 (4 × A76, dot-product, no int8 matrix maths, the closest match to the G1): Google gives E2B 133 reading / 7.6 writing and E4B 51 / 3.2. A measured llama.cpp run on a Pi 5 gave E2B 45.4 / 7.0 and E4B 22.5 / 3.7 (quantization not stated). Writing is about the same.
- **LiteRT-LM features:** a Kotlin API with streaming, tool calls, MTP, a conversation that keeps its KV cache between turns, and checkpoints and rewinds in C++ (not exposed in Kotlin). Apache-2.0, v0.18.0. Constrained decoding is claimed in Google's blog but not in the Kotlin documentation. Pebble's request reader and drawing need GBNF, so those jobs would stay on llama.cpp.
- **The rest:**
  - MNN: OpenCL aborts on a Pixel 6a's Mali, "pixel not support opencl"; its CPU gains rely on int8 matrix maths, which the G1 lacks.
  - MLC-LLM: the slowest reading of any GPU in one study, on a Mali-G78.
  - ExecuTorch: good on Mali-G715 for Llama 3.2, but no Gemma 4 E-models.
  - ONNX Runtime GenAI: CPU only on a Pixel.
  - llama.cpp's OpenCL backend is for Adreno (about 5 times slower than the CPU on a Mali).
  - llama.cpp's Vulkan backend asserts, crashes or crawls on Mali phones (24 s against 1.6 s on the CPU in one report).
  - KleidiAI's big gains need int8 matrix maths.
  - None of these is worth it on this phone.
- **llama.cpp tuning that still pays:** Q4_0 against Q4_K_M (first study, fix 10), threads on 2 × X1 + 2 × A76, and E2B. A Pixel 8 reading only 53 on the CPU, below a Pi 5's 133, suggests bad thread placement on Pixels, so keep pinning the threads.

### Smaller and split models

| Model | Size at 4 bits | Licence | Scores (vendor) | Pixel 6 Pro, llama.cpp CPU (estimate) |
| --- | --- | --- | --- | --- |
| Gemma 4 E4B (today) | QAT 4.22 GB, Q4_0 4.84 GB | Apache-2.0 | IFEval 96.7, MMLU-Pro 69.4, Tau2 42.2 | Reading 25 to 45, writing 4 to 7 |
| **Gemma 4 E2B** | QAT 2.62 GB, Q4_0 3.04 GB | Apache-2.0 | IFEval 94.6, MMLU-Pro 60.0, Tau2 24.5, GPQA 43.4 against 58.6 | Reading 50 to 90, writing 8 to 13 |
| LFM2.5-1.2B-Instruct | Q4_0 about 670 MB | LFM Open License | IFEval 86.2, MMLU-Pro 44.4 | Reading 80 to 150, writing 16 to 28 |
| Qwen3.5-2B | Q4_0 1.21 GB | Apache-2.0 | IFEval 61.2 (no thinking); prone to thinking loops | — |
| Gemma 3 1B | about 0.8 GB | Gemma terms | Weak at keeping to facts it is given (FACTS 36.4) | — |

- **E2B is the talker to try first.** It is the same family as E4B: the same voice, template and tool format, which keeps a hand-over between them smooth. It also has a drafter (the MTP head is 78 million parameters).
- **LFM2.5-1.2B is the fast fallback** if E2B's first words are too slow. It is weaker, and Liquid does not recommend it for knowledge.
- **Persona at this size:** the evidence is thin.
  - CharacterEval: 1 to 3B models score 2.05 to 2.45, against 2.77 for 7B.
  - Small models know almost no facts: Gemma 3 SimpleQA is 2.2 % at 1B and 4.0 % at 4B.
  - So the talker must not state facts, numbers, dates or memories it wasn't given.
- **Fast and slow:**
  - Google DeepMind's Talker-Reasoner: the talker reads beliefs the reasoner writes to memory. Its failure modes are stale beliefs and answering an easier question.
  - ConvFill (2025): a small on-device talker with a big model behind it was rated faster (4.24 against 3.46) but less natural (3.83 against 4.41), and its fillers sometimes contradicted the answer.
  - The lesson: **a quick line must carry no content.** It is a gesture, a sound, or an honest "let me think". Gestures beat filler words in user studies (66.7 % preferred a behavioural filler, n = 24), and spoken fillers lowered perceived intelligence.
- **Routing for Pebble:**
  - Plain-code rules come first:
    - deep: needs a tool, a memory lookup, the camera, a date sum, a fact, a number or a name; "why", "how", "explain", "what do you think"; over about 20 words;
    - talker: greetings, feelings, reactions, yes or no, small talk.
  - Anything unclear goes to the existing small model as a one-line JSON choice (talk or deep), on the partial words while they are still talking.
  - The talker can hand over with a first token that means "deep". Pebble then gives an honest hold and E4B answers.
  - Log the route, the time and any "what?" or repeated question, and tune the rules from that.
- **Later:** a LoRA on 2,000 to 5,000 of E4B's own Pebble replies could carry the persona into E2B. That would shrink the talker's system text to about 200 tokens. Ditto (on a 1.8B model) raised persona consistency from 0.60 to 0.78 this way; knowledge stays at the small model's level. About an hour on a consumer GPU (estimate).
- **The talker's history:** E2B gets a talk-only view: the summary, recent exchanges and "on your mind". Not the turns' tool calls, which it has no tools to read.

### Knowing sooner that they've finished

- Pebble's 0.25 s for a complete question is already as fast as any detector. The problem with a fixed silence is cutting people off:
  - eot-bench, real turns: a silence-only rule cuts off 55.6 % of turns at a 300 ms budget and 21.7 % at 600 ms, and needs 1,600 ms to get down to 5 %;
  - the best small open models still misfire on 20 to 35 % at 300 ms.
- **Options that run offline:**
  - **Smart Turn v3.1 / v3.2** (Pipecat): audio, 8 MB int8, BSD-2-Clause, 23 languages. 57 ms on one Graviton core; about 40 to 120 ms on one X1 (estimate).
  - **turn-1-mini** (p99lab, October 2026): 7 MB, Apache-2.0, English only, very new, self-reported.
  - **NVIDIA parakeet_realtime_eou_120m**: the same streaming family as Pebble's recognizer, with an end-of-turn token. Detection p50 160 ms on clean test audio. NVIDIA Open Model License, English only, not in sherpa-onnx yet.
  - Not usable: LiveKit's turn detector (only with LiveKit Agents), VAP (academic use only) and TEN (7B).
  - **A free option (untested):** Gemma already holds the words in its cache during read-ahead. One raw `/completion` request ending at the words, with `n_probs`, gives the chance that the next token ends the turn (`<turn|>`). LiveKit's old text detector worked this way.
- **Use:** start writing at every pause of speech addressed to Pebble, and hold the sound until the detector says done, or until 0.65 s, capped at 1.5 s. Drop the draft if they go on. A confident "done" lets a statement answer at about 0.3 s instead of 0.65 s, and an unsure one waits longer instead of cutting in.

### Faster writing

- **Gemma 4's drafter.** In the pinned build: `--spec-type draft-mtp -md <file>` (architecture `gemma4-assistant`). Google claims up to 1.5 times faster writing on a phone CPU, and its own LiteRT-LM figures for a Galaxy S26 Ultra CPU show E4B going from 17 to between 21 and 29.5 tokens a second. On a data-centre GPU (31B, 3 drafted tokens): 74 % accepted, 2.3 times faster. On the G1, expect 1.2 to 1.8 times (estimate), less at temperature 0.7.
- **The first spoken part is already short:** `conversation/mouth.py` speaks the first sentence, or the first clause of 4 or more words, as soon as it is written. The voice starts within about 0.05 s (emulator). The reply guide can ask for a short opening, which Pebble's style ("Short sentences") already suits.
- **Writing must outrun speaking** (about 3.5 tokens a second), or gaps appear between sentences. E4B on a hot phone (3 to 5 tokens a second) is close to that line. E2B and the drafter leave room.
- **Shorter answers:** the reply budget is 90 tokens, and "one to three short sentences" usually gives 15 to 30. Fine as it is.

### Less to read

- With read-ahead, the size of the prompt matters mainly for cold misses and memory, not for every reply.
- The prompt start should change as little as possible:
  - the household list goes in the system text, and "who is here now" goes in the message;
  - the tool list stays the same and the gate refuses what isn't allowed (first study, fix 6). This matters more now that replies share the turns' tools;
  - summaries happen in idle time, followed by an immediate read-ahead.
- **The talker's prompt** needs no tool list. Who Pebble is, its personality, the reply guide, the privacy rules and the safety rules that bear on speech come to about 400 to 600 tokens, against 1,077 for the turn's system text today.

### Other cuts

- **Social lines written ahead:**
  - for greetings, thanks, good night, "how are you", "good boy", the name alone;
  - per person and time of day, written by Pebble's model when idle, inside the wordsmith's checks;
  - a greeting for someone just recognised can be written while they walk in;
  - picked in about 0.1 s.
  - How much talk this covers is unknown. The blackbox's "talk" records can count it on the phone.
- **Running ahead between turns:**
  - the read-ahead itself;
  - E4B writes "on your mind" notes the talker reads (Talker-Reasoner), which Pebble's monologue already does;
  - the small model sorts talk from deep on the partial words.
- **Warm-up:**
  - the first read-ahead at voice start also wakes the big cores;
  - the server's start-up warm-up is on by default;
  - after a long idle, Android may have compressed the model's memory, and the read-ahead pays that cost while the person is still talking.
- **Heat:**
  - a Pixel 6 Pro running llama.cpp lost 25 to 27 % of reading and writing speed after heat soak (measured, an 8B model at an unusual quant);
  - the G1's GPU throttles hard (AnandTech);
  - background turns are the steady heat source: about 23 s of four-core reading for each turn, every 20 s after an exchange;
  - holding them off during talk and reading only new words cuts that;
  - step down a rung when thermal headroom falls below 0.2 (first study, fix 11).
- **The big cores and the eyes:**
  - the eyes' fast lane is not pinned, so Android can put its threads on the X1 and A76 cores that llama-server spins on;
  - `set_busy` pauses only the slow lane;
  - while Pebble listens or answers, pin the eyes' ONNX Runtime threads to the little cores (its intra-op thread affinity setting; to check) and slow the fast lane;
  - one study saw over 90 % of writing speed lost to contention with a camera app.

### How people judge the wait

- People leave gaps of about 200 ms between turns and plan their reply while the other is still talking (Stivers et al. 2009; Levinson and Torreira 2015).
- A robot is preferred at about 1 s, and a filler helps (Shiwa et al. 2008).
- In LLM-driven agents, the experience degrades above about 4 s (2025).
- **Targets:** a signal within 1 s, real words within 2 s, never 4 s of silence. The plan's Pixel 6 Pro columns meet these on a cool phone; on a hot phone the fallback column is at the edge.

### Licences of new parts

| Part | Licence | Note |
| --- | --- | --- |
| Gemma 4 E2B and its drafter | Apache-2.0 | |
| LiteRT-LM | Apache-2.0 | |
| Smart Turn v3.x | BSD-2-Clause | |
| turn-1-mini | Apache-2.0 | |
| NVIDIA parakeet_realtime_eou_120m | NVIDIA Open Model License | List in NOTES.md if used |
| LFM2.5-1.2B | LFM Open License | Already listed for LFM2.5 |
| LiveKit turn detector | LiveKit Model License | Not usable outside LiveKit Agents |
| VAP | Academic use only | Not used |

### Phone speeds (all estimates unless marked)

| | E4B, llama.cpp | E2B, llama.cpp | E2B, LiteRT-LM CPU | E2B, LiteRT-LM GPU |
| --- | --- | --- | --- | --- |
| Reading, tokens/s | 25 to 45 | 50 to 90 | 120 to 200 | 300 to 700 |
| Writing, tokens/s | 4 to 7 | 8 to 13 | 9 to 14 | 8 to 14 |
| Anchors | Pi 5: 22.5 / 3.7 (measured); Pixel 9 Pro XL, Gemma 3n E4B: 35 / 5.7 (user report) | Pi 5: 45.4 / 7.0 (measured) | Pi 5: 133 / 7.6 (Google); RK3588: 124 / 12.3 (measured) | Pixel 8: 427 / 11.9 (user); RK3588: 374 / 8.7 (measured) |

- The Pixel 6 Pro has two X1 cores in place of two of the Pi 5's A76s, and about three times the memory bandwidth. Reading should be 1.1 to 1.8 times a Pi 5's, and writing up to twice.
- A hot phone is about 25 % slower.
- A short read of about 12 tokens costs about one forward pass however few tokens it holds: about 0.3 to 0.5 s on E4B and 0.15 to 0.3 s on E2B.
- **Stronger phone** (for example Snapdragon 8 Gen 3 or 8 Elite, with int8 matrix maths): E4B reads 100 to 200 and writes 12 to 18 on the CPU (Google: 195 / 18 on an S26 Ultra), and reads about 1,300 on its GPU.

### Only the phone can tell

- Real reading and writing speeds for E2B and E4B, cool and hot, with the eyes and ears running.
- Whether E2B and E4B fit together, by resident memory, beside everything else. How much of each per-layer table stays on disk.
- The cost of a short read and of `-b 64`.
- Whether the drafter works with `--swa-full` and the projector, and what it gains.
- How often read-ahead is wasted on speech that wasn't for Pebble.
- Whether LiteRT-LM's GPU path runs on this phone's Mali-G78 at all, and with correct digits.
- The end-to-end time from someone's last word to Pebble's first, which the brain already logs (`stats.latencies`, `answer_latencies`).

### Sources

- Pinned llama.cpp: `android/llama/src` (`tools/server/server-context.cpp`, `server-queue.cpp`, `tools/server/README.md`, `docs/speculative.md`, the Gemma 4 vocabulary file's chat template); the brain's `conversation/turns.py`, `conversation/core.py`, `conversation/mouth.py`, `life/turn.py`, `life/loop.py`, `understand/model.py`; `android/.../llm/LlamaPlan.kt`.
- LiteRT-LM Gemma 4 speeds: https://developers.google.com/edge/litert-lm/models/gemma-4 ; model cards https://huggingface.co/litert-community/gemma-4-E2B-it-litert-lm , https://huggingface.co/litert-community/gemma-4-E4B-it-litert-lm ; repo https://github.com/google-ai-edge/LiteRT-LM ; Android API https://developers.google.com/edge/litert-lm/android ; blog https://developers.googleblog.com/en/blazing-fast-on-device-genai-with-litert-lm/
- LiteRT-LM on Mali: https://github.com/google-ai-edge/LiteRT-LM/issues/3507 , /issues/1850 , /issues/2421 , /issues/2202 , /issues/3986 ; https://github.com/DenisovAV/flutter_gemma/pull/550 ; https://github.com/google-ai-edge/gallery/issues/35 ; RK3588 measurements https://blog.armbian.com/mali-gpu-with-litert-lm/ ; ML Drift https://arxiv.org/html/2505.00232v1
- TPU and NPU: https://developers.google.com/edge/litert/next/tensor-sdk , https://developer.android.com/ndk/guides/neuralnetworks/migration-guide , https://developers.google.com/ml-kit/genai , https://github.com/google-ai-edge/gallery/issues/64
- Other runtimes: MLC on Mali https://arxiv.org/html/2410.03613 ; MNN on Pixel https://github.com/alibaba/MNN/issues/3571 ; ExecuTorch on Pixel 9 https://arxiv.org/html/2605.08195v1 ; llama.cpp OpenCL https://github.com/ggml-org/llama.cpp/blob/master/docs/backend/OPENCL.md ; Vulkan on Mali https://github.com/ggml-org/llama.cpp/issues/21483 , https://github.com/ggml-org/llama.cpp/issues/17226 ; Q4_K dot-product repack https://github.com/ggml-org/llama.cpp/pull/17494 ; Gemma 4 MTP in llama.cpp https://github.com/ggml-org/llama.cpp/pull/23398 ; ONNX Runtime GenAI https://github.com/microsoft/onnxruntime-genai/releases
- Pi 5 llama.cpp measurements: https://github.com/leemailto2008/pi5-llm-arena ; Pixel 6 Pro heat soak: https://github.com/Osmantic/ODS/pull/1878 ; G1 memory: https://en.wikipedia.org/wiki/Google_Tensor
- Gemma 4: https://huggingface.co/google/gemma-4-E2B-it , https://ai.google.dev/gemma/docs/core/model_card_4 , https://unsloth.ai/docs/models/gemma-4/qat ; MTP https://ai.google.dev/gemma/docs/mtp/overview , https://point.free/blog/gemma-4-mtp/
- Small models: https://huggingface.co/LiquidAI/LFM2.5-1.2B-Instruct , https://huggingface.co/Qwen/Qwen3.5-2B , https://ai.google.dev/gemma/docs/core/model_card_3
- Fast and slow, persona: Talker-Reasoner https://arxiv.org/html/2410.08328v1 ; ConvFill https://arxiv.org/html/2511.07397 ; fillers https://arxiv.org/html/2508.11781v1 , https://arxiv.org/abs/2507.22352 , https://arxiv.org/abs/2607.23204 ; routing https://lmsys.org/blog/2024-07-01-routellm/ , https://arxiv.org/abs/2404.14618 ; Ditto https://arxiv.org/html/2401.12474 ; AbstentionBench https://arxiv.org/abs/2506.09038 ; contention https://arxiv.org/html/2410.03613v3
- Reading while they talk: LiveMind https://arxiv.org/html/2406.14319v2 ; thinking while listening https://arxiv.org/abs/2510.07497 ; Amazon patent https://patents.google.com/patent/US9437186 ; GLaDOS https://github.com/dnhkng/GlaDOS ; partial stability https://ar5iv.labs.arxiv.org/html/2006.01416 ; streaming prefetch https://ar5iv.labs.arxiv.org/html/2011.10798 ; predicting the end https://arxiv.org/html/2409.19990v1
- End of turn: Smart Turn https://github.com/pipecat-ai/smart-turn , https://www.daily.co/blog/improved-accuracy-in-smart-turn-v3-1/ ; turn-1-mini https://huggingface.co/p99lab/turn-1-mini ; eot-bench figures via https://huggingface.co/Nikhil-09/turnwave ; NVIDIA EOU https://huggingface.co/nvidia/parakeet_realtime_eou_120m-v1 ; LiveKit licence https://docs.livekit.io/agents/logic/turns/turn-detector ; VAP https://github.com/inokoj/VAP-Realtime
- Human timing: Levinson and Torreira https://pmc.ncbi.nlm.nih.gov/articles/PMC4464110 ; Shiwa et al. https://unpaywall.org/10.1007%2FS12369-009-0012-8
