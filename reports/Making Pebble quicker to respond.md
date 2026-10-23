# Making Pebble quicker to respond

19 October 2026. Research on the code as it stands, the llama.cpp build the project pins (`android/llama/build.sh`: tag `v0.6.0`, build b11429), and a replay of real prompts from the scripted sim. Nothing here has run on the Pixel 6 Pro yet. Every phone speed below is an estimate and is marked so.

"gzip" would not help: it shrinks data crossing a network, and Pebble's calls never leave the phone. The time goes into the model reading its prompt and writing its answer.

## The short version

Three things make Pebble slow or silent today, and all three are cheap to fix:

1. **Gemma 4 thinks before every answer.** The pinned llama-server turns Gemma 4's thinking on by default, and nothing in Pebble turns it off. Each answer starts with a hidden thought, at about 5 words a second. A reply only has room for 90 tokens, so the thought can use them all and Pebble says "Sorry, my thoughts are slow right now."
2. **A turn does not fit in its window.** A turn sends 20 to 23 tool descriptions (2,650 to 3,050 tokens) plus about 1,100 tokens of system text before any history. That is more than the 4,096-token window, so llama-server refuses the turn, the brain marks the mind as not ready, and replies stop until it checks again. The brain's compaction never counts the tools, and its token estimate runs 12 to 19 % low.
3. **The model rereads too much.** The phone reads a prompt at an estimated 20 to 40 tokens a second. A reply that misses the cache rereads 1,000 to 2,000 tokens: 30 to 70 seconds. Small windows force a summary every few turns, and each one throws the cache away.

Giving each job its own slot was measured and is not worth it on this llama.cpp: the server already keeps each job's prompt in a RAM cache, and pinned slots changed the work by under 1 %. What pays is a bigger window, compaction that counts the tools, a bounded cache, and `--swa-full`.

## Ranked fixes (Pixel 6 Pro first)

Seconds assume the estimated 30 tokens a second for reading a prompt and 5 for writing (see "Phone speeds"). "Built" means it is in the code now (see "What was built").

| # | Fix | Where in the code | Estimated saving | Effort | Risk | How to test |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | **Thinking off** for Gemma 4 | `android/.../llm/LlamaPlan.kt` `args()`: `--reasoning off` when `--jinja`; `brain/pebble/profiles/model_gemma4_e4b.json` `extra_body.chat_template_kwargs.enable_thinking = false` (for PC servers started by hand). **Built.** | 10 to 60 s on every main-model call (a 50 to 300 token thought), and replies stop coming back empty | 2 lines | Low | `LlamaPlanTest`; `test_mind.py` checks the payload. On the phone: a reply has no `reasoning_content`, and the server log shows no `<|think|>` |
| 2 | **Make a turn fit:** a window of 8,192, and compaction that leaves room for the tools and fits the window the server really has | `KeeperService.tickModels` → `LlamaPlan.pick` (window per rung); `brain/pebble/mind/profile.py` `limits()`; `mind/history.py`; `mind/llama.py` reads `/props`; gemma profile `context_tokens 8192`, `compact_at_tokens 3500`, `keep 1000`. **Built.** | Turns stop failing on the phone. In the replay, a third less reading (32,200 → 21,300 tokens; with fix 3 as well, 18,300, 43 % less: about 8 minutes of phone time saved over a 3-minute scene) because summaries become rarer | Small | Low; about +280 MB of KV cache | `test_mind.py` (limits fit the served window; a smaller window compacts sooner). On the phone: no "exceeds the available context size" in `llama-main.log` |
| 3 | **Each job keeps its memory, safely:** bound and count llama-server's own prompt cache (`--cache-ram`), and `--swa-full` | `LlamaPlan` rungs, `Gguf.kt` (KV cost read from the model file), `LlamaChoice.kt` (the step down after a failure), `LlamaServer` status. **Built.** | Keeps the reuse the cache already gives (50,000 → 32,000 tokens read in the replay) without the default 8 GiB cap growing into Android's low-memory killer; `--swa-full` saves another 14 % with the new window (replies 1,267 → 795 tokens on average, 42 s → 27 s) and makes the shared start of turn and reply prompts reusable | Medium | Medium: memory on the phone is unmeasured | `LlamaPlanTest` (rungs, memory, KV cost from a made-up model file). On the phone: admin status shows the rung; RSS of llama-server stays under the plan |
| 4 | **Let a reply jump the queue.** A turn starts 20 s after every exchange (`BEAT_AFTER_S`), and llama-server serves one request at a time, so the next thing someone says waits for that turn | `brain/pebble/conversation/core.py` (the beat after an exchange), `brain/pebble/life/loop.py` `beat()`: skip or delay the beat while the person is still talking to Pebble, or cancel a running turn when someone addresses Pebble | 10 to 40 s whenever someone answers within about a minute | Small to medium | Low to medium (a cancelled turn must not mark the mind as down) | A scene where Ina answers 25 s after a reply: the reply's start time should not depend on the turn |
| 5 | **Make the reply share the turn's prompt start:** the same system text and tools, with the reply's guide moved into the reply's own message. Or, without changing the prompt, warm the reply's cache in idle time after each turn | `brain/pebble/life/turn.py` `reply()` | Replay, 8,192 window: replies read 1,065 tokens on average today (35 s), 263 shared (9 s). The first reply after some turns: 2,106 → 333 | Small | Changes what the model is told for replies (it would see the tool list). Owner's call; check with `conversation/eval.py` and a real model | Replay; `test_activities`-style scene timing |
| 6 | **Smaller, steadier tool list.** 20 to 23 tools cost 2,650 to 3,050 tokens a turn; `start_activity` alone is 450. The list changes when someone arrives, when an activity starts and in quiet hours, and each change makes the whole history be read again | Tool descriptions (`tools/`, `activities/`, `screen/tools.py`, `people/tools.py`); `life/loop.py` `tool_names` (changing tools last, or always the same list with the gate refusing) | 1,000 to 2,000 tokens less per miss (30 to 60 s); far fewer misses on arrivals | Medium | Tool-use quality; measure with the evals | Token count per turn in the replay; the evals |
| 7 | **Speculative decoding with Gemma 4's own drafter**: `mtp-gemma-4-E4B-it` (Q8_0, 99 MB, published by ggml-org), `--spec-type draft-mtp -md <file>` | `LlamaPlan.args`, a model fetch | Estimate 1.3 to 1.8 × faster writing on a phone CPU: a 30-token answer from 6 s to about 4 s | Small | Medium: untested with `--swa-full` and the picture projector; acceptance is lower at temperature 0.7 | Self-bench rung: keep it only if writing is at least 15 % faster |
| 8 | **Stream the Wordsmith.** The `say` tool and every "no" or ending wait for the whole rephrase (up to 70 tokens, about 14 s) before a word is spoken | `brain/pebble/mind/wordsmith.py`, `tools/builtin.py` `say` | 3 to 10 s to the first sound for those lines | Medium | Low (the number check can run per sentence) | A test that the first sentence is spoken before the call ends |
| 9 | **Threads and cores rung**: reading wants 4 cores (2 × X1 + 2 × A76); writing is limited by memory speed and may be as fast on the 2 X1s, leaving the A76s to the eyes | `LlamaPlan.plan` (`-t` and `-tb`, `-C` and `-Cb`) | Estimate 0 to 15 %, plus less heat | Small with a self-bench | Low | Self-bench |
| 10 | **Model and projector format.** In this llama.cpp both Q4_0 and Q4_K_M are repacked for dot-product ARM (`q4_0_4x4`, `q4_K_8x4`), so Q4_K_M is not penalised the way older advice says. Q4_0 (4.59 GB) is 8 % smaller than Q4_K_M (4.98 GB). The projector at Q8_0 is 560 MB instead of 990 MB | Model files; the admin screen | Q4_0: estimate 5 to 8 % faster writing, maybe 10 to 30 % faster reading. Projector Q8_0: 430 MB back, enough to lift the Pixel 6 Pro to the bigger cache rung | Download and measure | Quality (Q4_0); picture answers (projector) | Self-bench and the understand eval |
| 11 | **Heat.** The Tensor G1 slows its big cores within minutes of full load | `LlamaServer` / keeper: read `PowerManager.getThermalHeadroom`, step down threads or the eyes' rate | Keeps speeds from halving in a long chat (unmeasured) | Medium | Low | Ten minutes of chat on the phone with speeds logged |
| 12 | Little ones: the reply waits up to 0.6 s for the request reader (`CONSIDER_WAIT_S`) unless thinking started early; the small model's request prompt is about 1,300 tokens against a 6 s timeout on two A55 cores (fine when cached, too slow cold); KleidiAI kernels are off in the build | `conversation/core.py`, `understand/model.py`, `android/llama/build.sh` | Under 1 s each, or only on cold starts | Small | Low | — |

**Not worth it (measured):** pinned per-job slots (`-np N` with `id_slot`): under 1 % less reading in the replay, because the RAM prompt cache already does the job, and each slot costs its own KV memory; on a phone CPU two requests at once also slow each other. Moving the "people here now" block after the history: 22 % less reading with today's 4,096 window but 23 % more with 8,192, because the stored history no longer matches what was sent. `--cache-reuse`: not usable here (the server switches it off when the picture projector is loaded, and Gemma 4's cache can only shift with `--swa-full`). Saving slots to disk (`--slot-save-path`): the RAM cache does the same in memory.

**The two or three changes to make first:** 1 (thinking off), 2 (a window the turn fits, with honest compaction) and 4 (a reply never waits for a background turn). 1 and 2 are built. 5 is the biggest single saving for replies, but it changes the prompt, so it is the owner's decision.

## Where the time goes, from someone speaking

| Step | Today | Notes |
| --- | --- | --- |
| Pebble's name to its eyes turning | about 0.12 s after the name | `alive.face_speaker`; no model involved |
| End of speech to the turn closing | about 0.3 s | 0.25 s of quiet after a complete question |
| "Mm." or "Hmm," | 0.55 s, when no sentence is ready | Already built; about 0.6 s |
| Waiting for the request reader | up to 0.6 s | Skipped when thinking started at the first pause |
| Waiting for a running turn | 0 to 40 s | A turn starts 20 s after each exchange; one request at a time |
| Reading the reply's prompt | 4 to 70 s | 130 tokens when the cache holds the rest; 1,000 to 2,100 when it misses (replay average 1,270, or 1,065 with the 8,192 window) |
| Thinking | 10 to 60 s, or the whole budget | Fix 1 |
| The first sentence | 2 to 3 s | 10 to 15 tokens at about 5 a second; streamed to speech sentence by sentence (already) |

So the first real words come 15 s to more than a minute after someone stops, or not at all. With fixes 1 to 3, a reply that follows another is about 5 to 7 s, and the average reply in the replay reads 795 tokens (about 27 s); the first reply after some turns is still 30 to 40 s. With 4 and 5 as well, most replies are about 5 to 10 s.

**First wheel movement.** Confident requests ("follow me", "come here", "go to bed") are read by plain-code rules and start at once with a few plain words; no model is involved. Unsure wording goes to the small model (about 1 to 2 s when its cache is warm; up to its 6 s timeout when cold), then to the main model (up to 25 s, and behind any running turn). So the wheels are already quick for most requests; fix 4 also helps the rare slow ones.

## Evidence

### Phone speeds (estimates)

No published llama.cpp numbers were found for Gemma 4 E4B on a Tensor G1. These are estimates from:

- someone reporting Gemma 3n E4B on a Pixel 6 Pro in Google's own app at about 4.4 tokens a second with a picture and over 6 on text;
- Google's LiteRT-LM figures for Gemma 3n E4B on a Galaxy S24 Ultra's CPU: 73.5 tokens a second reading, 9.2 writing (the Tensor G1 has older cores and no int8 matrix instructions, so roughly 2 to 3 times slower at reading);
- arithmetic: writing reads about 2.7 GB of weights per token (about 3.9 billion weights in the layers plus the 671-million-weight output table, at about 0.6 bytes each), and the phone can stream roughly 20 GB a second to four cores.

| | Estimate on 2 × X1 + 2 × A76, cool phone |
| --- | --- |
| Reading a prompt | 20 to 40 tokens a second (30 used above) |
| Writing | 4 to 7 tokens a second (5 used above) |
| Small model (LFM2.5-230M, 2 × A55) | reading about 140, writing about 25 (rough) |

The phone must measure these itself (see "How the phone picks its settings").

### Thinking is on

- `tools/server/server-context.cpp`: `enable_thinking = params_base.enable_reasoning != 0 && template_supports_thinking`. `enable_reasoning` defaults to `-1` ("auto", `common/common.h`).
- `common/parsers/gemma4.cpp` sets `supports_thinking = true` for Gemma 4.
- Gemma 4's template puts `<|think|>` at the top of the system turn when thinking is on, and an empty thought when it is off.
- Pebble never sends `enable_thinking`, `reasoning_effort` or `--reasoning`. `stream_piece` reads only `delta.content`, so a thought shows as silence, and its tokens count against `max_tokens` (90 for a reply, 70 for the Wordsmith, 120 for understanding).

### How big the prompts are

The scripted conversation scene was replayed with every main-model call kept, turned into Gemma 4's chat format, and counted with Gemma 4's own tokenizer (the vocabulary file in the llama.cpp tree; a scratch BPE outside the repo). Other jobs were built with their real builders.

| Job | Tokens |
| --- | --- |
| Turn | 3,129 at the start, up to 4,209 with the scene's 13 to 14 tools; up to 6,249 with a bigger window |
| of which system text | 1,077 (safety rules 234, the people block 114, laws 106, personality 104, tool rules 102) |
| of which tool descriptions | 1,648 in the scene; **2,650 to 3,050 with the phone's 20 to 23 tools** (all 25: 3,257) |
| Reply | 2,106 to 2,768 (up to 3,929 with a bigger window) |
| Understanding a request | 1,213 |
| Drawing | 1,056 |
| Summary | 360 to 567, plus up to 350 written |
| Picture question | about 480 with the picture |
| Wordsmith | about 310 |
| Expression pick | about 200 |

- The turn and the reply share only their first 907 tokens: the system text differs at the guide line, and the reply sends no tools.
- The brain counts about 4 characters a token, which matches the system text (4.1), but the whole prompt runs 7 to 19 % over its estimate (tool calls, template marks), and the tool descriptions are not counted at all (`TurnRunner._fixed_tokens`).
- llama-server refuses a prompt that reaches its window ("exceeds the available context size"), and `ctx_shift` is off by default.

### What the cache does today

Replay of 32 calls (16 turns with their tool rounds, 4 replies, 4 summaries, and Wordsmith, understanding, drawing and picture calls slotted in), simulating the pinned server's rules: the longest shared start is reused, Gemma 4's sliding-window layers keep only the last 1,024 positions so a reuse further back needs a saved checkpoint (made at the last user message and near the end of each prompt), and the RAM cache saves and restores whole prompt states by the server's similarity rules.

| Setting | Tokens read | At 30 a second |
| --- | --- | --- |
| No reuse at all | 78,767 | 44 min |
| One slot, RAM cache off | 49,822 | 28 min |
| **Today: one slot, RAM cache on (default)** | **32,219** | **18 min** |
| One slot per job group | 32,043 | 18 min |
| `--swa-full` | 28,338 | 16 min |
| 8,192 window, compaction at 3,500 / 1,000 (built) | 21,314 | 12 min |
| **the same with `--swa-full` (built)** | **18,266** | **10 min** |
| the same with slots per job | 21,239 | 12 min |
| the same with `--swa-full` and the reply sharing the turn's start | 16,720 | 9 min |
| 8,192 window, compaction at 5,000 / 2,000 (too close to the window with the phone's tools) | 16,389 | 9 min |
| that, with `--swa-full` | 15,229 | 8.5 min |
| that, with `--swa-full` and the reply sharing the turn's start | 12,605 | 7 min |

Per call, with the built settings: turns read about 695 tokens on average (23 s) and replies about 795 (27 s). With compaction at 5,000 / 2,000, replies that share the turn's start read 263 (9 s). Compaction stops at 3,500 because the estimate runs up to 19 % low and the phone's tools add about 3,050 tokens: 1.19 × 3,500 + 3,050 + up to 300 for tool rounds + 200 for the answer is about 7,700, inside 8,192.

The reasons it misses:

- **Compaction.** Each summary changes the system text and cuts the history, so the next turn and the next reply read everything again, and the summary itself writes up to 350 tokens (about 70 s) while nothing else can run. With the 4,096 window it happened 4 times in 16 turns.
- **The reply's prompt is different from the turn's** after 907 tokens, so the first reply after some turns reads its whole history again.
- **Private lines are masked after the fact.** The last observation is stored with "[something said in private]" in place of room talk, so every next prompt differs from the cached one at that observation. The server's checkpoint at the last user message covers this, but only while that checkpoint survives (see below).
- **The people block and the tool list change** when someone arrives or leaves, when an activity starts or stops, and in quiet hours. Both sit before the history.

### Slots and the server's cache in the pinned build

- `--cache-ram` (default 8,192 MiB) keeps whole prompt states in RAM and restores the best match when a new request comes in (`server_prompt_cache` in `server-task.cpp`). That is already "each job its own memory" with one slot.
- With `id_slot` pinned, the same rules run per slot; idle slots are also copied into the RAM cache on every new request (`--cache-idle-slots`, default on).
- The default cap is the risk: states pile up (every turn leaves one that later prompts no longer start with), and for Gemma 4 a turn's state with its checkpoints can be 100 to 900 MB. Unbounded, it can grow until Android kills llama-server or the brain.
- Checkpoints: default 32 per slot, each about 40 MB for Gemma 4 E4B (the sliding-window part). They pile up between summaries, and when the list is full the server keeps the oldest and the current request's, dropping the one Pebble needs next time. `--swa-full` keeps the sliding-window layers whole (+280 MB at 8,192 tokens), so no checkpoints are needed and any shared start is reusable.
- `--cache-reuse` is switched off by the server when a picture projector is loaded, and Gemma 4's cache cannot shift.
- Speculative decoding: the build has `draft-mtp`, `draft-simple`, `draft-eagle3`, `draft-dflash` and several n-gram kinds. Gemma 4 has its own drafter architecture (`gemma4-assistant`), which shares the main model's cache.

### Gemma 4 E4B's cache cost

From the model's config: 42 layers; the last 18 reuse earlier layers' cache, so 24 keep their own; of those, 4 are full-attention (2 heads of 512) and 20 are sliding-window (2 heads of 256, window 512).

| | f16 | q8_0 |
| --- | --- | --- |
| Full-attention layers, per token | 16 KB | 8.5 KB |
| Sliding-window layers, per token | 40 KB | 21 KB |
| 8,192 tokens, `--swa-full` | 448 MiB | 238 MiB |
| 8,192 tokens, window only (+ checkpoints of about 40 MB each) | 168 MiB | 89 MiB |

### Kernels and memory settings

- Repacking: Q4_0, Q4_K, Q5_K, Q6_K and Q8_0 are all repacked for dot-product ARM in this build (`ggml-cpu/repack.cpp`); the Tensor G1 gets the `android_armv8.2_2` variant (dot product and half precision, no int8 matrix multiply).
- Flash attention defaults to auto; a quantised V cache needs it.
- Repacked weights are copied into ordinary memory at load, so they no longer come from the mapped file; Android can still push them into compressed swap when memory is short. `mlock` is not available to an app. The warm-up run at start is on by default.
- The per-layer embedding table (about 1.7 GB of the 5 GB file) is read one row per token and stays in the mapped file, so most of it never needs to be in memory.
- GPU: the Mali-G78 has no llama.cpp path worth using (OpenCL is for Adreno, the server build is CPU only).

### Outputs, grammar and the rules-first path

- Replies stream into speech sentence by sentence, with "Mm." first when nothing is ready at 0.55 s. Already built.
- Reply budgets: 90 tokens (reply), 70 (Wordsmith), 120 (understanding), 140 (drawing), 60 (picture), 32 (jobs), 350 (summary). Fine once thinking is off; the summary is the long one.
- Grammars are used for understanding and drawing, both short. Sampling cost from a grammar is small next to a phone's reading speed.
- The rules catch every confident request with no model; the evals require every core line right.

### Brain waits

- `conversation/core.py`: 10 to 50 ms polling loops (fine); `CONSIDER_WAIT_S` 0.6 s; a beat 20 s after each exchange (fix 4).
- `understand/model.py`: small model 6 s, main model 25 s, tried in turn.
- `mind/wordsmith.py`: a whole non-streamed call before speaking (fix 8).

## How the phone picks its settings

Following "The Pixel 6 Pro is the floor": each setting has rungs, the phone measures itself at first start, keeps its choice, and steps down when a rung fails.

**Built now (memory rungs).**

1. The keeper reads the model file's header (`Gguf.kt`): layers, cache heads and head sizes, sliding window, shared-cache layers. From that it works out the cache's bytes per token (`KvCost`).
2. For the main model it walks the rungs from the top and takes the first whose memory (model + projector + 400 MB of working room + KV cache + RAM prompt cache) fits, leaving room for the small model at its lowest rung, under the existing rules (main + small under 70 % of the phone's memory; each under free memory + 2 GB).

   | Rung | Window | Sliding layers | Cache type | RAM prompt cache |
   | --- | --- | --- | --- | --- |
   | 0 | 8,192 | whole | f16 | 1,536 MiB |
   | 1 | 8,192 | whole | f16 | 768 MiB |
   | 2 | 8,192 | whole | q8_0 | 384 MiB |
   | 3 | 6,144 | whole | f16 | 192 MiB |

   The small model: 2,048 tokens with 128 MiB, then 32 MiB. One slot each (`-np 1`) throughout.
3. The rung comes from the phone's total memory and the files, not from the memory free at that moment, so it never flaps; free memory only decides whether to start now or wait. While a server runs, its plan is kept.
4. If llama-server dies before it is ready, or within 5 minutes of being ready, or takes over 15 minutes to load, the next lower rung is saved (`llama-main.json` and `llama-sub.json` in the app's no-backup folder, keyed by app version, phone model and model file) and used from then on. A new app version or model file starts from the top again. "Measure the eyes again" does not reset it yet (one line in `AdminActivity` would).
5. The brain asks the server for its real window (`/props`) and fits its compaction to it, so a lower rung can never overflow.

**Expected on the Pixel 6 Pro** (not yet run): rung 1 (8,192 tokens, f16 cache, 768 MiB RAM cache, about 7.1 GiB for the main server) if Android reports at least about 11.2 GiB of memory in all; otherwise rung 2 (q8_0 cache, 384 MiB, about 6.6 GiB). The Q8_0 projector makes rung 1 certain. A phone with more memory climbs to rung 0; the brain's compaction stays at the tuned values, so a bigger phone gets more room, never a slower prompt.

**To build next (speed rungs).** Start the server, send a fixed 512-token prompt with `cache_prompt: false` and ask for 32 tokens; read `timings.prompt_per_second` and `timings.predicted_per_second` from the answer. Do it once cool and once after two minutes of load. Use it to choose:

- threads and cores (`-t`/`-C` for writing, `-tb`/`-Cb` for reading): 2 × X1 against 2 × X1 + 2 × A76;
- the drafter (`draft-mtp`): keep only at 15 % faster writing or better;
- cache type: q8_0 against f16 when memory allows both;
- the model format (Q4_0 against Q4_K_M) when both files are there.

Fall back a rung when it measures slower than the floor's by more than 10 %, when the phone's thermal headroom (`PowerManager.getThermalHeadroom`) drops below 0.2, or when it fails. On stronger phones the higher rungs are a GPU path (OpenCL on Adreno 750 and newer), the Hexagon NPU backend, more threads, and a bigger model, each switched on only when it measures faster.

## What was built

- `android/app/src/main/java/nz/pebble/robot/llm/Gguf.kt` (new): reads a GGUF file's header without loading the model, and `KvCost` works out the KV cache's bytes per token from it (full-attention and sliding-window layers, shared-cache layers, f16 or q8_0, with or without `--swa-full`).
- `llm/LlamaPlan.kt`: the rungs, `need` (model + projector + working room + KV cache + RAM prompt cache), `pick` (the highest rung within the 70 % rule, leaving room for the small model; waits when free memory is short), and the new arguments `--reasoning off`, `--swa-full`, `-ctk`/`-ctv`, `--cache-ram`. Still `-np 1`.
- `llm/LlamaChoice.kt` (new): keeps the step down after a failure, per app version, phone and model file.
- `llm/LlamaServer.kt`: steps down when the server dies while loading or soon after, reads and caches the KV cost, keeps the running plan, and shows window, rung, cache type and cache size in its status.
- `keeper/KeeperService.kt` (`tickModels` only): plans both servers through the rungs; the small model counts the main one's real need.
- `brain/pebble/mind/profile.py`: `served` (what the server reports) and `limits()`, which fits compaction to the real window while keeping room for the tools.
- `brain/pebble/mind/history.py`: compaction uses `limits()`.
- `brain/pebble/mind/llama.py`: reads `/props` when the server is ready (window and pictures).
- `brain/pebble/profiles/model_gemma4_e4b.json`: window 8,192, compaction 3,500 / 1,000, thinking off.
- Tests: `brain/tests/test_mind.py` (3 new, 1 updated), `android/app/src/test/.../llm/LlamaPlanTest.kt` (6 new, 1 updated).
- Notes: `brain/README.md` (running a model on a PC), `android/README.md` (the settings the phone picks).

Slots per job were not built, because the replay says they do not pay.

## Only the phone can tell

- Real reading and writing speeds, and how much heat takes off them.
- Whether thinking really was on (it should show as `reasoning_content` before the fix).
- llama-server's real memory with the projector, the cache and the eyes running, and which rung the Pixel 6 Pro lands on.
- Whether `--swa-full` and a q8_0 cache start and run correctly with the projector.
- The end-to-end time from someone's last word to Pebble's first.
