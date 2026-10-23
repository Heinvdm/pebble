# Pebble: instructions for agents

Pebble is a personal desk-pet robot: an old Android phone (a Google Pixel 6 Pro with 12 GB of memory) is its brain, face and cameras, on an ESP32-S3 body with two wheels. The project is meant to be publishable, so anyone could build one.

**The Pixel 6 Pro is the floor (owner, 19 October 2026).** Pebble should be as good and as responsive as possible on it, and only get faster and better on a stronger phone, never need one. So:
- every feature must run well on the Pixel 6 Pro, alongside everything else, within its 12 GB and its heat;
- nothing hard-codes a phone: models, context sizes, threads, core masks, backends and rates are chosen from what the phone measures about itself at first start (and again on "measure again"), the way the eyes already pick their fastest backend;
- each choice has a ladder: the Pixel 6 Pro's rung is the tested default, and higher rungs (a bigger model, a longer window, a GPU or NPU path, more scans a second) switch on only when the phone measures fast enough and has the memory;
- a lower rung is the fallback if a higher one is slow, too hot or fails, so a step up can never make Pebble worse.

## Start here
1. `STATUS.md`: where the work stopped, the failing tests, open decisions.
2. `plans/`: the owner's decided plans, not yet built. The owner's answers are recorded in each; don't re-ask them.
3. `interfaces.md`: the single source of truth for body geometry, pins, power, the link protocol and reflexes.
4. `brain/README.md`: how the brain fits together, section by section.
5. `NOTES.md`: the decisions, lessons and open questions from the build sessions so far.

The original spec, parts list and build guide with schematics were drafted in a private document that is not part of this repo; `reference/spec_snapshot_2026-10-15.txt` is a plain-text snapshot of the spec. The repo files win if they disagree.

## Layout
- `brain/`: Python (stdlib and asyncio; numpy only where the phone has it). Runs on the PC against a simulator, and on the phone through Chaquopy.
- `firmware/`: ESP32-S3 (PlatformIO, Arduino). Native unit tests live under `[env:native]`.
- `android/`: the host app (Kotlin). The release signing key is never in the repo; without it the build uses the debug key.
- `cad/`: the printable body (Python and manifold3d). `cad/build.py` makes the STLs and `cad/check.py` checks collisions, tilt, docking and sensor cones.
- `plans/`: designs decided but not yet built.

## Rules
- **No comments or docstrings in code.** Match the surrounding code's style.
- **Plain words in docs and anything Pebble says.**
- **The laws come first** (`brain/pebble/laws.py`). All motion goes through permissions, the motion guard and stop handling. Never weaken a safety limit to pass a test; fix the behaviour.
- **Tests describe the wanted behaviour.** Don't loosen a test to make it pass.
- **No personal data, absolute user paths, keys, or a Pebble "self" folder in the repo.** The sim household names (Ina, Sam, Mo) are made up.
- **Fetched models stay git-ignored.** Only models made here are tracked: `hazards.onnx`, `prints.onnx`, `objects.onnx`, `yamnet.onnx`. Check any staged file over 5 MB before committing.
- **Pebble itself is offline at runtime:** no internet, no cloud model. Development may download models and packages.
- **Licences:** Pebble is never sold (owner, 19 October 2026), so non-commercial models and code may be used; pick the best that's available. List every non-commercial or copyleft part in NOTES.md ("Licences of the parts"), so anyone who builds one knows what they can't sell. Credit lines a licence asks for go there too.

## Setup (Linux)
```
cd brain
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt -r requirements-optional.txt
.venv/bin/python -m pebble.eyes.fetch
.venv/bin/python -m pebble.speech.fetch
.venv/bin/python -m pebble.hearing.fetch
.venv/bin/python -m pebble.self.recall.fetch
```
On Windows, use `.venv\Scripts\python` instead of `.venv/bin/python`.

## Tests
- **Brain:** `cd brain && .venv/bin/python -m pytest -q`. The summary line is hidden by config, so count the dots and failures. At handoff some tests failed or were flaky (see STATUS.md).
- **Firmware:** `cd firmware && pio test -e native`.
- **CAD:** `cd cad && python build.py && python check.py`.
- Run the full brain suite before saying anything is done.

## Work order
**Next, before anything below (owner, 21 October 2026): four plans, in this order.**
1. `plans/flexible-pebble.md` pieces 0 to 2 (the measuring stick, the reader, the format).
2. `plans/context-budget.md` C0 to C2 (the meter, the budget table and guard, the merged tools), so later features add request kinds, not tools.
3. `plans/flexible-pebble.md` pieces 3 to 13 (with 4b): time and repeats, triggers, if/while/unless logic, messages, house rules, go-and-check, watching, references, new things it has never done, its own words, getting unstuck, compaction nobody notices.
4. `plans/context-budget.md` C3 to C6 (naming pulls things in, choosing by score, the shelves, the year-old self test).
5. `plans/pebble-script.md` S1 to S7 (agency step 5, Pebble script).
6. `plans/teach-by-example.md` T1 to T7 (teaching by showing, the how-to book).

Run the year-old self test (context-budget C6) again after steps 5 and 6.

0. Before Pebble goes onto a real phone (owner, 20 October 2026): the privacy look-away and social cues (NOTES.md "Ideas noted for later").
1. ~~Fix the navigation failures~~ (done 19 October 2026; STATUS.md lists what's left). The palm "stop" from `plans/reading-people.md` comes next, because it is law 1 and small.
2. Finish Android round 3 (STATUS.md).
   1. The rest of the speed pass: `reports/Making Pebble quicker to respond.md` (STATUS.md lists the order; per-job slots were measured and dropped), with all three steps of `plans/thinking-out-loud.md` (staged holds while it thinks, and learning its own; the owner asked for the learning now), and `reports/Cutting response time drastically.md` once it exists.
   2. The household pack, as the owner answered it at the top of `reports/More everyday value for the household.md`, then `plans/better-hearing.md` (far calls, the 48 kHz feed and high-pitch listener, sound habits, direction, the clean-up step; several steps need the phone first).
   3. The model upgrades, as the owner answered them in `reports/Model upgrades now non-commercial is allowed.md`: the print models first (face prints on InsightFace, with SFace as the fallback), then the switches, then the try-and-measure rows.
3. Build the plans in the order each one gives:
   1. `agency-and-respect-for-life.md` first, with the pieces of `more-freedom.md` (F1–F8) at the steps its build-order table names, and `reading-people.md` after its first two steps (respect for life, the gatekeeper). `languages.md` comes after the household pack once it is written.
   2. then `workbench.md` and `storage-and-events.md`;
   3. then `everyday-uses.md`;
   4. then `pebble-body-redesign.md`;
   5. and `new-bodies.md` last.
