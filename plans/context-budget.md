# What goes into each prompt: a budget that holds for years (plan, ready to build)

**The owner, 21 October 2026:** "look into how we can properly handle all the info that gets fed into each prompt, so that after a year, we don't end up with 10% of context for everything on each prompt."

The aim: a year-old Pebble's prompts are the same size as a new one's, and just as quick, while it can still reach everything it knows. Growth goes into its stores and lookups, never into the prompt. Code paths are under `brain/pebble/`.

## The ruler: why every token matters on the phone
From `plans/more-freedom.md` section 13 (estimates for the Pixel 6 Pro; measure on the phone):
- **Reading fresh text is slow:** each 25 tokens a call must read fresh costs about 0.6 to 1.0 s.
- **A changed start is very slow:** re-reading a 1,500-token stable start after it changes costs 33 to 60 s.
- **Cached text is nearly free:** text llama-server already holds from the last call costs almost nothing, and so does text read ahead while the person was still talking.

So three rules follow:
1. **The start of the prompt never changes during the day.** Changes are swapped in only after being read ahead in quiet time, never while someone is talking (already the rule in `more-freedom.md` section 13).
2. **Text that changes per call** is either read ahead or tiny.
3. **Everything that grows** is chosen per call, under a cap, never listed whole.

## What goes in today, and what grows
| Part | Where | Today's limit | Grows over a year? |
| --- | --- | --- | --- |
| Core, laws, safety and tool rules, low battery | system text (`mind/prompt.py` `core_text`) | fixed | no |
| Own words, personality, stage, values, faces, turn guide | system text | fixed sizes | no |
| Itemised notes | system text | 1,200 characters (`self/notes.py`) | no (capped) |
| People you know | system text (`household_text`) | 12 names, **the first 12 met**, not the most relevant | the choice goes stale |
| People here now | the message (`people/prompt.py`) | per person: last 3 nicknames, last 5 likes, dislikes, wishes and promises, private notes; **no limit on how many people** | yes, with visitors |
| The tool list | every life turn | **all 28 tools, about 3,000 tokens**, every turn (`steady_tools`) | **yes**: every feature adds tools |
| "On your mind" board | before the person's words | about 60 tokens | no (capped) |
| History | messages | compacts at about 3,500 tokens | no (capped) |
| The request reader's context | `understand/context.py` `lines()` | **every known place**, every name present | **yes**: places, spots and rooms pile up |
| Coming with `plans/flexible-pebble.md` and `plans/pebble-script.md` | task card, references, abilities card, kept skills, house rules, agenda, lessons, recipe book | each planned with a cap | yes, unless chosen per call |

Two parts already grow without a cap, the tool list and the reader's place list, and the plans in progress would add more. Most of the self is already capped well. The fix is a budget system that every part has to pass through.

## The design
### 1. One budget table, for each kind of call
`mind/budget.py` holds a table of token budgets for each kind of call (a reply, a life turn, the request reader, a background job, the script writer, the teaching session), section by section. The Pixel 6 Pro's numbers, for the 8,192 window:

| Section | Reply | Life turn | Reader | Kind |
| --- | --- | --- | --- | --- |
| Core and laws | 900 | 900 | (its own guide) 700 | frozen |
| Tools | 0 | 1,200 | 0 | frozen |
| Self (own words, personality, stage, values) | 350 | 350 | 0 | changes at night |
| Notes | 300 | 300 | 0 | changes at night |
| Household names | 60 | 60 | 0 | changes at night |
| **Stable start, total** | **1,610** | **2,810** | **700** | cached |
| History | what's left, at least 2,000 | what's left, at least 2,000 | 0 | rolling |
| People here now | 250 | 250 | 40 | per call, read ahead |
| Task card | 200 | 200 | 60 | per call |
| Board and recall | 60 | 60 | 0 | per call, read ahead |
| Matched items (skills, rules, agenda, lessons, places, references) | 150 | 300 | 150 | per call |
| The new words or observation | 200 | 300 | 100 | per call |
| Reply room | 250 | 400 | 200 | output |

- The table scales with the window on stronger phones (the ladder in CLAUDE.md): a bigger window gives more history and more matched items, never less than the Pixel's.
- `compact_at_tokens` and `keep_tokens_after_compaction` are worked out from the table, not set by hand.
- **The promise to the owner:** on the Pixel, history and the task keep at least 45 % of every life turn's window after a year, the same as on day one.

### 2. Push little, pull the rest
Only what's relevant now is pushed into the prompt. Everything else stays in the stores, and E4B pulls it with a lookup when it needs it. The lookup tools already exist or come with the plans: `recall`, `recall_thing`, `where_is`, plus `how_to` (taught skills and scripts, `plans/teach-by-example.md`), `who_is` (a person's record, within the privacy rules), `places` (the map) and `later` (the agenda).
- A lookup returns at most 5 short lines. That is a small per-call cost, paid only when needed.
- The turn guide tells E4B that it knows more than it sees, and how to look it up.

### 3. Naming pulls things in, at no cost
Before every reply and reader call, plain code scans the words (and the activity's target) for every name and alias of every stored item: people, places, spots, things, skills, scripts, sounds, rules and lists. It uses a cheap string and spelling-tolerant match against all of them, so a year of growth costs only microseconds. Exactly the named items come into the prompt, so "do the evening round" brings that skill and "where Mo's bag is" brings Mo and the bag.
- The request reader's "Places known" becomes: the places named in the words, then the current room, then the most-used places, up to 15. No place is lost; it just isn't listed when nobody mentions it.

### 4. Choosing the rest by meaning, recency and who's here
What isn't named is chosen by score, under the section's budget:
- **Meaning:** the sentence model, F3 in `more-freedom.md`.
- **Recency.**
- **Importance.**
- **How often it's used.**
- **Who's here** (their items first).
- **Where Pebble is** (this room's rules and things first).

Each item has a short form (one line) and a long form. The long form is used only when there's room.
- **People here now:** at most 4 described in full, chosen by who's talking and who was talked about. Others are named only. Each person's description is capped at 60 tokens, and their likes, wishes and promises are chosen by relevance to the talk, not just the last 5.
- **Household names:** family first, then whoever was seen or mentioned most in the last month, up to 12. It changes only at night.
- **Matched items:** at most 3 skills, 3 house rules (only those for this room or activity), 3 agenda items (the next hour), 3 lessons and the references block.

### 5. A few broad tools instead of many narrow ones
The tool list is the biggest part of a life turn, and every feature would add to it. So the tools are merged into a fixed set of about 10, with short descriptions:
- **`do`** takes, in plain words, what Pebble wants to do: "go and check the back door", "remind Alex at 7 to call Mo". The request reader (`plans/flexible-pebble.md` piece 1) turns those words into a request, with the grammar and the gate. So new request kinds, items for later, rules, checks and watches add nothing to the tool list.
  - It replaces `start_activity`, `change_activity`, `end_activity`, `move`, `look`, `add_task` and `add_event`.
  - It costs one reader call. A life turn is background, so that's fine.
- **`say`** (and `say_to`).
- **`face`** (faces, scenes, drawing).
- **`remember`** (facts, people's notes, promises, impressions).
- **`recall`** (memories, things, places, people, how-tos, the agenda: one lookup with a `about` field).
- **`self`** (its dials, `mine/`, wonderings, its standing, change and forget requests).
- **`stop`.**
- **`status`** (battery, sensors, tasks).

Target: about 1,200 tokens, the same whatever is added later. The existing tool evals (`conversation/quality.py`) must pass with the merged set before the old tools go.

### 6. A stable order, so the cache works
Every prompt is laid out in the same order:
1. frozen (core, laws, tools);
2. nightly (own words, personality, values, notes, household names);
3. history;
4. per call (people here, task card, board, matched items, the words).

- Nothing in parts 1 and 2 changes during the day. New notes, words and household names are written at night and swapped in after a background read-ahead.
- Per-call parts are read ahead while the person talks, as replies already are.
- Today the household names and people sit in the system text. They move into the message (`people_in_message` already does this for people) so a visitor arriving doesn't break the cache.

### 7. Three shelves: hot, warm and cold
Every store sorts its items onto shelves, at night, by use and importance:
- **Hot:** may be pushed into prompts by the rules above.
- **Warm:** only by naming or a lookup.
- **Cold:** archived on disk, found only by a lookup that asks for old things ("do you remember last summer…"). Never pushed.

Rules for the shelves:
- An item moves up when it's used, and down after months without use.
- **Nothing is deleted by the shelves.** Deleting is for forget, privacy limits and the storage plan (`plans/storage-and-events.md`).
- **Night consolidation:**
  - merge duplicates ("dance" and "little dance");
  - fold many small memories about one person or place into one line, copied from the memories it came from, with a pointer to them;
  - drop expired items.
- Summaries written by E4B (more-freedom F5) must point at the memories they came from, and plain code checks that every name in them exists.

### 8. A meter and a guard
- **The meter:** every call records how many tokens each section used (numbers only, never text) in `logs/budget.jsonl`. A daily line goes in the journal ("prompts stayed in budget; the biggest was the people section at 230 of 250").
- **The guard:** if a section is over its budget, plain code trims it in a fixed order: the lowest-scoring matched items first, then long forms to short forms, then fewer people described. It records that it did.
  - **Never trimmed:** the laws, the safety rules, the stop and alarm state, the task card's first line, or the words just said.
  - A call can never go out over the window: the guard is the last step before every call.

### 9. Test it on a year-old Pebble
`sim/year_self.py` builds a made-up self as full as a busy year:
- 60 people (15 seen often);
- 80 places and spots;
- 800 things;
- 200 skills;
- 40 scripts;
- 400 lessons;
- 30 house rules;
- 20 taught sounds;
- 150 agenda items;
- 100,000 memory records;
- full notes.

Every kind of call is run against it in the sim. Pass means:
- **Size:** every section is within budget, and the total within the window.
- **Room:** history and the task keep at least 45 % of a life turn.
- **Finding:** on a 100-question set, the right item is still found at least 95 % of the time. Examples: a skill taught 11 months ago, asked for by name and by a description; a person's like; a rule for this room; a place mentioned once.
- **Speed:** the estimated fresh-read time on the Pixel ruler for a reply after read-ahead is the same as on a new self, within 10 %.

## Build order
1. **C0: measure today.** The meter on every call, and a report of each kind of call's real sizes on the PC.
2. **C1: the budget table and the guard,** in front of every call; `compact_at` worked out from the table.
3. **C2: the merged tools,** with the tool evals passing. This must land before `plans/flexible-pebble.md` piece 3, so the new features add request kinds, not tools.
4. **C3: naming pulls things in,** with the reader's place list chosen this way.
5. **C4: choosing by score;** people here and household names by relevance; the stable order (people out of the system text).
6. **C5: the shelves** and night consolidation.
7. **C6: the year-old self test,** run again after every later plan lands.

## Files
- **New:** `mind/budget.py`, `mind/select.py` (naming, scores, shelves), `sim/year_self.py`, `logs/budget.jsonl` (in the self), and tests.
- **Changed:**
  - `mind/prompt.py`;
  - `people/prompt.py`;
  - `life/turn.py`;
  - `tools/builtin.py`, `activities/tools.py` and `people/tools.py` (the merged set);
  - `understand/context.py`;
  - `mind/profile.py`;
  - `self/notes.py` and `self/recall/` (shelves);
  - `brain/README.md`, `STATUS.md`, `NOTES.md`.
