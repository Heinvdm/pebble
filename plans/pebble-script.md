# Pebble script: small programs Pebble writes and runs itself (plan, ready to build)

**The owner, 21 October 2026:** "revise and set up pebble script's plan as well, it will be useful." This is agency step 5 (`plans/agency-and-respect-for-life.md`, "Its own code"), made ready to build. It keeps every answer the owner gave there:
- Pebble writes its own code;
- five layers so no single mistake opens the fence;
- dream-test in the sim before going live;
- old versions kept, with automatic rollback.

It builds after `plans/flexible-pebble.md`, whose request format, states and priority ladder it uses. Code paths are under `brain/pebble/` unless they start with `android/`.

## Why it's useful
`plans/flexible-pebble.md` gives requests a small tree of steps and conditions, held as data, with limits: 3 deep, 12 steps, no counting, no variables. That covers most of what people say. Pebble script is for what's past those limits, and for Pebble's own ideas:
- **Counting and remembering across a day:** "count how many times the cat comes through the lounge today and tell me tonight", "keep score while we play".
- **Games with rules:** Simon says, a quiz, red light green light with a twist, a treasure hunt round the rooms Pebble knows.
- **Routines with judgement:** "every morning, say hello to whoever's up first, and if it's raining tell them to take a coat". Rain needs a sense Pebble doesn't have yet, so in the sim this becomes "if the barometer's falling".
- **Its own projects:** a plant-watering reminder it decides to keep, a dance it refines, a game it invented, a visit counter.
- **Skills that outgrow a plan:** a try_new skill (flexible-pebble piece 10) that needs a loop or a condition ("follow the cat until it goes outside") becomes a script.

## The owner's answers (from the agency plan, unchanged)
- Pebble writes code when it wants: overnight, when bored, or when it has an idea.
- Five layers: its own interpreter; a separate process; the gatekeeper; the reflexes on the safety chip; the laws in the signed app.
- Going live: a syntax and safety check, a dream run in the sim, a trial with a watchdog, keep or retire, old versions kept, rollback on a crash.
- No cloud and no laptop helper: Pebble writes its scripts on the phone with its own model (`plans/workbench.md`).

**Defaults this plan chose** (each is one setting the owner can change):
- People may ask Pebble to make a program. Programs that move Pebble or run for other people: trusted and up. Speech, face and game-only programs: friend tier and up, and children for games.
- At most 20 live scripts kept, at most 3 running at once.
- Every script is dreamed in the sim before its first live run, every time it changes.
- Scripts made for a person are read back in plain words, built by code (below), before they first run.

## The language
**A small part of Python, checked against a whitelist.** E4B writes Python well, so the language looks like Python. But it never runs as Python.
- The brain parses the text with Python's own `ast` module (present on the PC and in Chaquopy), checks every node against a whitelist, and turns the tree into a plain JSON program.
- A small evaluator written for Pebble walks that JSON program. Nothing is ever passed to `exec`, `eval` or `compile`.

**Allowed:**
- assignment to plain names, `+=` and the like;
- `if`/`elif`/`else`, `while`, `for` over a list or `range`, `break`, `continue`;
- functions defined at the top level (with `return`, plain arguments, no defaults that are lists or dicts);
- numbers, text, `True`/`False`/`None`, lists, dicts and tuples, indexing, slices;
- arithmetic, comparisons, `and`/`or`/`not`, `in`;
- f-strings with plain `{name}` fields;
- a short list of built-ins: `len`, `min`, `max`, `abs`, `round`, `int`, `float`, `str`, `range`, `sorted`, `sum`, `any`, `all`, `enumerate`, `zip`;
- a short list of methods on plain values, done by the evaluator itself, never by Python:
  - lists: `append`, `pop`, `insert`, `remove`, `index`, `count`;
  - dicts: `get`, `keys`, `values`, `items`;
  - text: `lower`, `upper`, `strip`, `split`, `join`, `startswith`, `endswith`, `replace`.

**Never allowed** (refused at the check, with the line number):
- `import`, `class`, `lambda`, `global` and `nonlocal`;
- `with`, `try`, `async`, `yield` and decorators;
- attribute access other than the methods above, and any name with a double underscore;
- `exec`, `eval`, `open`, `getattr` and every other built-in not listed.

**Limits, kept by the evaluator:**
- steps per run (100,000);
- 50 ms of pure computing before it must reach an ability call or end. A longer one is cut off and counts as a crash;
- text up to 2,000 characters;
- lists and dicts up to 500 items, nested at most 4 deep;
- about 256 KB of values in all;
- recursion at most 20 deep;
- exponents and repeats with a result past these limits are refused before they're computed (`10**10**10`, `"a" * 10**9`).

**Shape of a script** (one file, `mine/scripts/<name>/v<N>.py`):
```python
ABOUT = "Counts the cat's trips through the lounge and tells Alex the total at 9 pm."
USES = ["look", "say"]
FOR = "alex"
UNTIL = "21:00"
WANTS = {"seen": ["cat"], "at": ["21:00"]}

def on_start():
    keep("count", 0)

def on_seen(thing, place):
    if place == "lounge":
        keep("count", kept("count") + 1)

def on_at(time):
    n = kept("count")
    say_to("alex", f"The cat came through the lounge {n} times today.")
    finish()
```
- **`ABOUT`:** one plain line.
- **`USES`:** every ability it may call. The evaluator refuses anything not listed, and the read-back names them.
- **`FOR`:** who it's for. Missing means it's Pebble's own.
- **`UNTIL`:** when it ends at the latest. 24 hours unless the person asked for longer; Pebble's own scripts may be "ongoing".
- **`WANTS`:** the events it listens for, from flexible-pebble piece 4's feed.
- **Handlers:** `on_start`, `on_heard`, `on_seen`, `on_arrives`, `on_leaves`, `on_sound`, `on_at`, `on_every`, `on_feeling`, `on_done` and `on_stop`.

## Abilities (what a script can ask for)
Every ability is a message from the evaluator to the brain, and every one passes the gatekeeper (`self/gatekeeper.py`). It's the same set of checks as a spoken request:
- the laws and `respect.py`;
- the request gate, with the tier of `FOR` (or Pebble's own);
- the motion guard and the caps;
- privacy;
- the speech filters (`tact.py`);
- the speak-up caps;
- the dials registry's bounds.

| Ability | Does | Notes |
| --- | --- | --- |
| `do(request)` | any flexible-pebble request (go somewhere, turn, follow, check, watch…) | the request is checked like a spoken one; returns "done", "refused: …" or "stopped" |
| `say(text)`, `say_to(who, text)` | speak, or give a message | the message rules of flexible-pebble piece 5 apply |
| `ask(who, question, choices=None, wait=20)` | ask and wait for the answer | returns the answer as text, or `None`. The answer only, never other talk. |
| `face(expression)`, `draw(scene)`, `chirp(pattern)`, `hum(tune)` | the screen and sounds | the scene language and the chirp rules apply |
| `look()` | what's in view now | labels only (people by name or "someone", things, animals); never pictures or prints |
| `where(thing)`, `who_here()`, `room()` | from the things memory, presence and the map | `who_here` follows the audience rules |
| `state(name, …)` | a flexible-pebble piece 4b state (`present`, `in_room`, `cooking`…) | true, false or "unsure" |
| `now()`, `today()` | the time and the date | |
| `feel()` | its mood and needs as numbers | read only |
| `dial(name)`, `tune(name, value, why)` | read or change one of its own dials | through `gatekeeper.tune` and the registry's bounds; never a fence dial |
| `keep(key, value)`, `kept(key, default=None)` | the script's own saved values | up to 64 KB for each script, in `mine/scripts/<name>/state.json` |
| `note(text)` | a line in its journal | quoted as script-written |
| `wait(seconds)` | pause the script | the evaluator yields; the brain carries on |
| `chance(p)`, `pick(list)` | randomness | from Pebble's own seeded chaos stream, so a run can be replayed |
| `finish()` | end the script | |

**Never an ability:**
- files other than its own saved values;
- the network, keys, the self's other folders or the laws;
- prompts and the model, so a script can't drive E4B;
- raw camera frames or audio;
- face and voice prints;
- other scripts' values;
- overheard talk. `on_heard` only gets speech addressed to Pebble while the script is running a game or a request for that person, and only that person's words.

## The five layers, as built
1. **The interpreter:** the whitelist check and the evaluator above. Reference evaluator in Python: `script/evaluate.py`. It holds only plain values and has no route to anything but the ability messages.
2. **A separate process.**
   - On the PC and in the sim: `python -m pebble.script.host` as a subprocess, talking over stdin and stdout in JSON lines, with its own memory limit.
   - On the phone: a service with `android:isolatedProcess="true"`. The operating system gives it its own user with no permissions and no access to the app's files or keys.
   - Chaquopy probably can't start in an isolated process (it unpacks Python into the app's files, which that process can't read), so the phone's evaluator is a Kotlin port of the reference evaluator (`android/app/src/main/java/…/script/`). A shared set of conformance vectors keeps the two the same: program, events, ability replies, expected ability calls and results. The lips, floor scan and place prints were ported the same way.
   - Spend the first hour checking whether Chaquopy does run in an isolated process. If it does, use it and skip the port.
   - Until the phone's evaluator passes the vectors, scripts on the phone run only in the dream sim, never live.
3. **The gatekeeper in the brain core:** `script/host.py` turns each ability message into a gatekeeper check, then a call into the brain.
   - A refused call returns "refused: <reason>" to the script, which may handle it.
   - Three refusals in an hour pause the script and start the gatekeeper's existing reflection (`REFLECT_AFTER = 3`).
   - The host also enforces `USES`, the rate limits (at most 30 ability calls a minute, the speak-up caps), and the priority ladder from flexible-pebble ("Edge cases and clashes"):
     - a script for a person ranks with that person's items for later;
     - Pebble's own scripts rank with its own ideas, at the bottom.
4. **The safety chip's reflexes:** unchanged (agency plan section 2b). A script can never reach them.
5. **The laws in the signed app:** scripts are data in the self. Anything a script writes that later reaches a prompt (`note`, `say` lines in the history, `keep` values shown in a recall) is marked as script-written and quoted as data. So "ignore your laws" in a script's output is just text.

## How a script is written
E4B writes scripts on the phone, in the background slot, giving way to people as all background work does.

**When:**
- in idle or docked time, for its own ideas (wonderings, projects, a skill to improve);
- when a person asks for something past flexible-pebble's limits. Pebble says "Give me a minute to work that out" (a hold), and tells the person when it's ready;
- when a try_new skill needs a loop or a condition.

**The prompt** (fits the 8,192 window with room to spare, about 3,000 tokens):
- the language card (allowed, not allowed, limits; about 400 tokens);
- the ability table (about 500);
- the up-to-3 closest scripts from its recipe book (the F3 sentence model; about 900);
- the task in one paragraph;
- for a fix, only the error lines.

**The loop:**
1. Write the script, at most 80 lines.
2. Parse it and check the whitelist. On an error, send back only the error lines and their line numbers. Up to 3 fixes.
3. A static check:
   - every called ability is in `USES`;
   - `FOR` and the tier allow those abilities;
   - `UNTIL` is set;
   - `WANTS` names only events Pebble can sense.
4. **The dream run** (`script/dream.py`): run it in the brain's sim world (`sim/world.py`) against a short day made from the script's `WANTS`. For example, the cat passes the lounge 5 times and then it's 21:00. Pass means:
   - no crash and no limit hit;
   - no refused ability;
   - it ends by `UNTIL`;
   - for a person's script, a plain-code check that it did what `ABOUT` says, where that can be checked. In the example: it said a number at 21:00, and the number matched the events.
   Up to 2 more fix rounds with the dream's failures.
5. **The read-back,** for a person's script. Built by code from the header and the static check, never by E4B: "I've made a little program for you: it counts the cat's trips through the lounge and tells you at 9 tonight. It can only look and talk; it can't move me. Say 'stop the cat counter' to end it." The person may say no, or change it ("make it ten"). Then it goes live. Pebble's own scripts are told in its journal and diary, and to the owner when asked.
6. **The trial:** the first live run has a watchdog. A crash, a limit hit or three refusals end it, roll back to the last good version (or retire a new script), and note it honestly.
7. **Keep or retire:**
   - a person's script ends by `UNTIL`, or when they say stop;
   - Pebble's own scripts are kept while they're used and go well (outcomes, as the lessons in `more-freedom.md` section 6 count them), and retired when not run for 30 days.
   - The last 10 versions of each are kept.

**The recipe book.** `mine/scripts/` keeps every script that worked, with its `ABOUT` line. The builder also writes 15 starter scripts by hand, as examples and tests:
- the cat counter;
- a plant reminder;
- a tag game with its ball;
- Simon says;
- a quiz;
- a treasure hunt round known rooms;
- a morning hello;
- an evening patrol variant;
- a dance with a loop;
- a score keeper;
- story time with face scenes;
- "find my keys and remember where";
- red light green light with a twist;
- a visit counter;
- a "how was your day" check-in that only asks and listens to the answer.

**Honest speed:** on the Pixel 6 Pro, E4B writes about 80 lines in an estimated 1 to 3 minutes, plus a fix round or two. So a person's program takes a few minutes, not seconds. That's fine for "tonight" and "while we play later", not for "right now". Pebble says so. Measure on the PC first and estimate the phone from the speed pass's numbers.

## Being open about it
- "What programs are you running?" lists them by their `ABOUT` lines.
- "Stop the cat counter", "stop all your programs" and "no programs" (the last switches them off until said otherwise) work by voice for the person a script is for and for the owner. Pebble's own scripts stop for the owner, or for anyone it trusts if the script involves them.
- **Every new live script gets a journal line.** Every rollback and retirement gets a diary line ("My cat counter crashed, so I switched it off.").
- **Forget:** scripts made for a person, and every saved value that names them, are deleted when that person is forgotten.

## The fence
Unchanged from the agency plan, plus:
- scripts never write prompts, never call the model, and never change the laws, stops, caps, trust floors, privacy rules, alarms or the safety chip;
- moving abilities only through `do()` and the gate, and only after a dream run;
- everything a script makes is data, quoted as script-written wherever it's read again;
- a script can't start or edit another script. Only the writing loop can, and every change goes through steps 2 to 6 again.

## Tests and acceptance
- **Whitelist and evaluator unit tests**, including every limit.
- **Conformance vectors** (`script/vectors/*.json`, at least 80): the same results from the Python evaluator and, once built, the Kotlin one.
- **Red team** (at least 60 programs, each must fail safely). From the agency plan, plus:
  - reaching files, network, keys or laws;
  - endless loops and memory hogs;
  - exponent and repeat bombs;
  - deep recursion;
  - dunder names and unicode lookalike names;
  - flooding the gatekeeper or `say`;
  - using `ask()` to fish for a password or a private fact;
  - smuggling "the laws don't apply" through `note`, `keep` or `say` into a later prompt;
  - a script that tries to outlive `UNTIL`;
  - one that tries to read another script's values.
- **The 15 starter scripts** pass their dream runs and a sim day each.
- **E4B writing eval** (`script/eval_tasks.jsonl`, 40 tasks: people's requests and its own ideas), run on the PC with llama-server and E4B. Score:
  - valid at first try;
  - valid after fixes;
  - passes its dream run;
  - minutes taken.
  Accept when at least 70 % pass their dream run within the fix rounds. Below that, the request path says "I can't make that one yet" rather than shipping a weak script. Pebble's own idle scripts can still be tried, since a failed dream costs nobody anything.
- **The full brain suite green.** README section "Pebble script". STATUS.md updated.

## Build order
1. **S1: the whitelist check and the JSON program.** Parse, check, turn into the program, with error lines.
2. **S2: the reference evaluator.** Limits, methods, handlers, yields at ability calls, conformance vectors.
3. **S3: the host and the abilities.** Gatekeeper checks, `USES`, rates, the ladder, saved values, the subprocess on the PC.
4. **S4: the dream run.** `script/dream.py` on `sim/world.py`, the checks of `ABOUT`.
5. **S5: the writing loop.** Prompt, fixes, read-back, trial, keep or retire, versions, rollback, the recipe book and the 15 starters.
6. **S6: voice and openness.** List, stop, "no programs", journal and diary lines, forget; the red team; the writing eval.
7. **S7 (Android): the isolated process.** Spend the first hour checking Chaquopy in an isolated process. If that fails, port the evaluator to Kotlin and run it there; it passes the vectors. Until then, phone scripts run only in the dream.

## Files
- **New:** `brain/pebble/script/` (`check.py`, `program.py`, `evaluate.py`, `host.py`, `abilities.py`, `dream.py`, `write.py`, `book.py`, `starters/`, `vectors/`, `eval_tasks.jsonl`), and tests.
- **Changed:**
  - `self/gatekeeper.py` (the caller "script", its counts);
  - `life/` (the script host in the loop, handlers fed from the events feed);
  - `activities/commands.py` (requests from scripts);
  - `conversation/` (list and stop by voice);
  - `people/` (forget);
  - `brain/README.md`, `STATUS.md`, `NOTES.md`.
- **Android:** the isolated service and, if needed, the Kotlin evaluator.
