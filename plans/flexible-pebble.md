# Flexible Pebble: the model decides, code guards (plan, ready to build)

**The owner, 21 October 2026:** "these fixes are quite important as they will give pebble much more functionality ... make pebble as flexible and autonomous as possible." The goal is a flexible, smart, autonomous and responsive droid. To be built by one long agent session (tonight), in the order below.

This plan is the build spec for `plans/more-freedom.md` sections 15 (something it has never done) and 16 (the model reads, code guards), and for the limits found on 21 October when 30 everyday requests were run through today's readers. Those two sections keep the owner's answers; this file adds everything else and says how to build it. Code paths are under `brain/pebble/` unless they start with `android/`.

## The one rule
**E4B decides what to do and how to say it. Plain code decides whether it's allowed, and when it fires.** E4B never moves a wheel, starts a timer or speaks except through a request that plain code checks. Plain code never has the last word on what someone meant, unless the request is on the short instant list or the rules used every word.

## The owner's answers
1. **No preview for new things** (21 October 2026): Pebble tries, asks "Like that?", keeps trying until the person says yes (no limit on tries), then keeps it as a skill for that body (`more-freedom.md` section 15).
2. **The model reads, code guards** (21 October 2026): E4B reads almost every request; the stops, the harm refusal and the gate stay in code; keep it responsive (`more-freedom.md` section 16).
3. **Repeats, edge cases and clashes** (21 October 2026): "remind me every Monday night that Tuesday is bin day" must work, and edge cases and clashes must be planned for (piece 3 "Times and repeats", and "Edge cases and clashes").
4. **Compaction** (21 October 2026): compact while doing tasks so people don't notice, and never lose useful information (piece 13).
5. **Logic** (21 October 2026): "also account for more complex ones with if, and, while etc." (piece 4b).
6. **As flexible and autonomous as possible** (21 October 2026). So where this plan had to choose, it chose the more capable option and fenced it, rather than leaving the feature out.

**Defaults this plan chose, which the builder uses.** The owner can change any of them later; each is one setting or one line.
- A skill is kept only on a spoken yes from friend tier or above, or from a child. Strangers and bots never teach.
- Reminders, timed requests and messages: friend tier and up, and children. Strangers can't leave anything for later.
- House rules (keep out, quiet): friend tier and up for rules lasting up to a day; trusted and up for longer ones; the owner for permanent ones. Children can ask for quiet for up to an hour.
- Watching over someone: trusted and up, at most 2 hours.
- Messages are delivered word for word, only the asker's own words, only to the person named. If anyone outside the family is in view, Pebble only says "I've got a message from Ina for you" and waits for "go on".
- Items for later run out: a trigger after 24 hours unless a longer time was asked for (at most 7 days); a message after 3 days (the asker is told it wasn't delivered).
- In quiet hours, an item for later only fires if it's a wake-up or reminder the person set for themselves, or an alarm. Everything else waits until quiet hours end, and says so.

## What limits Pebble today (the evidence)
Thirty everyday requests were run through today's readers on 21 October. About 10 came out right. The faults have four causes:

1. **E4B is hardly ever asked.** In `understand/understanding.py`:
   - when the rules are sure, the model is skipped, even when the rules left words unused;
   - when the rules found no motion word (`Parse.cue` in `understand/rules.py`), only the small "subconscious" model may read. `app.py` wires only the "conscious" model since the small one was dropped on the Pixel, so these sentences never reach any model.
   - So "dance", "remind me…", "tell Sam…" and "when Ina gets home…" are never seen by E4B.
2. **The reader's own instructions throw requests away.** `understand/model.py` `GUIDE` says a request about the future is chat, and "don't …" is chat.
3. **The request format can't say most of these things** (`understand/request.py`):
   - 33 fixed kinds and at most 3 chained steps;
   - "until" knows only "back" and "called"; 8 adjustment words; no repeat or count; distances up to 10 m;
   - no time, no condition, no message, no standing rule.
   - So even a perfect reader has nowhere to put "in ten minutes", "twice", "when Ina gets home" or "stay out of the bedroom".
4. **Four readers decide alone**, each by its own patterns: `understand/rules.py`, `understand/house.py`, `activities/asks.py` and `conversation/listening.py`.

Other limits, the same kind of problem:
- **The chat turn** (`life/turn.py`) has raw tools (`move`, `say`, `add_task`, `add_event`, at most 4 calls a turn). But nothing fires at a clock time (`add_event` is a calendar date, `add_task` only expires), and nothing checks whether a request worked.
- **Fixed lines:** refusals (`activities/gate.py`), clarifying questions (`understand/resolve.py`) and reactions are hand-written.
- **Stuck handling:** each activity in `activities/kinds.py` has its own hand-coded recovery; nobody decides what to do next when it gets stuck.

The 30 sentences, the reading today, and what the reading should be, are the start of the evaluation set (piece 0).

## Pieces, in build order
Each piece ends with the full brain suite green and its own tests. Pieces 0 to 2 come first, because everything after builds on the new format. After that, 3, 4 and 4b (things for later, triggers, logic), 5 and 6 (messages, house rules), 7 to 9 (going, checking, watching) 10 to 12 (new things, its own words, getting unstuck) and 13 (compaction) can be built side by side if the work is split between agents.

### Piece 0. The measuring stick
- `understand/eval_flex.jsonl`: at least 150 lines, each a sentence, the context (who said it, who is present, the places known, what Pebble is doing) and the expected reading in the new format (piece 2). It covers:
  - the 30 sentences from 21 October;
  - counts and repeats;
  - times, delays and "every …";
  - "when …" and "until …" triggers;
  - messages;
  - house rules ("don't", "stay out", "be quiet until");
  - go-and-check;
  - watch over;
  - references ("where Ina was sitting", "do that again");
  - new things (try_new);
  - logic: at least 40 compound sentences with if, otherwise, unless, while, and, or, whichever comes first, and the result of a check (piece 4b), including "and" read both ways, conditions Pebble can't sense, and trees past the limits;
  - repeats and vague times ("every Monday night", "weekdays at seven", "the first of every month", "every other Friday", "tonight", "before bed", "at 7" said in the afternoon and at night);
  - changes and cancels ("make the bin one eight o'clock", "no bin reminder this week", "stop all my reminders");
  - things that must stay chat ("I'm going to the shop later", "Sam doesn't like peas").
- Also a "still chat" list of statements, and "never a command" sentences (talk about Pebble, quotes of other people's orders, the TV).
- Score with `python -m pebble.understand.eval --set flex`, for:
  - the rules alone;
  - E4B alone, with llama-server on the PC (the real-model checks in STATUS.md say how it was built and run);
  - the new pipeline.
- Record each one's accuracy and time per reading.
- The respect sets (`eval_respect*.jsonl`) and every existing set run on the new format too; they must not get worse.

### Piece 1. Every request reaches E4B unless code is sure and complete
- **One front door.** `Understanding.read` runs all four pattern readers as quick guesses, then decides:
  - **instant** (no model): stop words, the palm stop and the stranger stop; the harm refusal (`harmed`, `respect.py`, unchanged); and the instant list: "stop", "wait", "come here", "back off", "follow me", "go home", plus a household or game reply to a question Pebble just asked;
  - **rules win** only when a rule reading is sure **and** used every content word. That's a word-coverage check: fillers ("please", "Pebble", "okay", "um", "now") don't count; a leftover "twice", "slowly", "again", "later", "when", "don't" or "until" does;
  - **otherwise E4B reads**, with no cue-word gate. The `only=("subconscious",)` branch goes; if a small model is ever wired again, it may only make a first guess.
- **Rewrite `GUIDE`** for the new format: future requests, "don't" and "until" are requests now. Keep the examples short; the grammar carries the shape.
- **Read ahead.** The request read starts on partial speech, the same way replies do (STATUS.md "Reading ahead"), so most of it is done when the person stops.
- **Start on the rules, finish on the model.**
  - If the rules have a reading for the first step, Pebble starts it at once (with an instant "Okay!" from the holds), while E4B reads the whole sentence.
  - E4B's reading replaces the rest of the chain. If it reads the first step differently, the runner swaps to E4B's version: `Runner.start` already cancels and replaces.
  - A step already under way is never undone in a way that breaks a cap or the gate.
- **Fallback:** the model is busy, the heat ladder says no, or there's no reading in 3 s → the rules' reading stands, and Pebble says "I'm not sure I got all of that" if words were left over.
- **Mode switch:** a dial `reading.mode`: `model_leads` (new), `rules_first` (today). The default becomes `model_leads` only when piece 0's numbers show both of these:
  - E4B alone matches or beats the rules on every set, with no new false commands;
  - every harmful request is still refused (163 of 163 and 42 of 42 today).
  Until then, every piece below still works with the rules reader, just less often.

### Piece 2. A request format that can say what people say
Extend `Request` in place (keep the field names; `from_dict` keeps clamping everything), and the grammar in `understand/grammar.py` with it:
- **Chains:** `then` up to 8 steps (from 3).
- **Repeat:** `repeat`, 1 to 10, on any step ("spin twice" = turn 360 repeat 2; "three laps of the couch").
- **Follow gap:** `metres` on `follow` and `wait` means the gap to keep.
- **Distances:** `metres` up to 30. The navigator decides whether it can go that far.
- **When** (`when`, piece 3): a delay, a clock time, a date, a part of the day, and repeats (every day, chosen weekdays, every N weeks, a day of the month, every N hours within a window), with an optional end. The full shape is in piece 3, "Times and repeats".
- **If, otherwise, while, unless, and, or** (piece 4b): a small tree of conditions and branches, held as data.
- **On** (`on`, piece 4): a trigger that starts the request: `{"event": "arrives", "who": "ina"}` and the others listed there.
- **Until**, widened: `back`, `called`, `seconds`, an `on` trigger, `asked` (Pebble checks in now and then: "still having fun?"), or `told` (until someone says enough).
- **Change words:** add `left`, `right`, `again`, `more`, `less`, `higher`, `lower`. Numbers (`metres`, `degrees`, `seconds`) are allowed on an adjust.
- **New kinds:**
  - `say_to`: a message for a person (piece 5);
  - `set_rule`, `end_rule`, `list_rules` (piece 6);
  - `check`: go somewhere and find something out (piece 7);
  - `watch` (piece 8);
  - `again`: do the last thing again (piece 9);
  - `try_new` (piece 10);
  - `list_later` and `cancel_later` (piece 3).
- **Steps carry their own asker.** The gate runs on every step when it starts (it already does for `then` steps in `activities/commands.py` `act`), with the asker's tier as it is at that moment, not when they asked.
- Update `for_mind`, `ack`, `resolve` and the chat turn's `start_activity` tool to take the new format.

### Piece 3. Things for later: the agenda
- `life/agenda.py`: a list of items, each a full request (piece 2) with:
  - who asked and their tier when they asked;
  - when it was made;
  - its `when` or `on`;
  - when it runs out;
  - its state.
- It's kept in the self as `agenda.json`, so it survives restarts.
- Plain code fires items on the clock (`clock.py`) and on events (piece 4); E4B never fires anything.
- **Reminders and wake-ups** are `say_to` the asker with a `when`.
  - "Remind me to take the washing out in ten minutes" → in 600 s, say to Alex: "You asked me to remind you: take the washing out."
  - A wake-up repeats every minute for up to 10 minutes until the person answers or is seen up. It's gentle first and louder after 3 tries, and stops at once on "I'm up".
- **Times and repeats.** The test sentence is "remind me every Monday night that Tuesday is bin day". The `when` object can hold:

  | Field | Example | Meaning |
  | --- | --- | --- |
  | `in_s` | 600 | a delay from now |
  | `at` | "19:30" | a clock time |
  | `part` | "night" | a part of the day, turned into a clock time by the household's table below |
  | `date` | "2026-12-24" | one date |
  | `days` | ["mon"] | chosen weekdays; "weekdays" and "weekends" are shorthands |
  | `every_weeks` | 2 | every other week (counted from the first one) |
  | `month_day` | 1, or "last" | a day of the month; a day a month doesn't have falls on that month's last day |
  | `every_s` with `from` and `to` | 3600, "22:00", "06:00" | every hour within a window ("every hour tonight") |
  | `until_date` or `times` | "2026-12-25", 4 | when the repeats end |

  - **Parts of the day** come from a household table in the self, with defaults: morning 08:00, midday 12:00, afternoon 15:00, evening 18:00, night and tonight 19:30, before bed 21:00. Anyone may set their own ("night means eight for me"), kept under their record.
  - **Ambiguous clock times:** "at 7" said at 3 pm means 7 pm; said at 9 pm, it means 7 tomorrow morning. "Next Monday" said on a Monday means in 7 days. A time that has just passed ("at 7" at 7:05) means tomorrow. Each case is written into the read-back, so a wrong guess is heard at once.
  - **The read-back is built by code from the stored item, never by E4B.** Example: "Okay: every Monday at 7:30 in the evening, I'll remind you that Tuesday is bin day. The first one is this Monday." So what the person hears is exactly what was saved, and a misreading shows up now rather than in three weeks. Pebble doesn't wait for a yes (the owner's "no preview" choice). For 30 seconds after the read-back, "no", "make it eight" or "Tuesdays, not Mondays" changes the item, and anything else carries on as normal.
  - **Public holidays:** when a reminder's text names a day that the almanac (`house/almanac.py`) says is a public holiday, Pebble adds one line: "Tuesday's a public holiday, so check the bins are still being collected." It doesn't guess what changed.
  - **Clock changes:** times are wall-clock times in the home's time zone. On a daylight-saving change, a 2:30 am item that doesn't exist that night fires at 3:00; one that happens twice fires once. If the phone's clock jumps (the wake-up note's clock sanity check), the agenda is recomputed and nothing fires twice.
  - **Changing and ending:** "change the bin reminder to eight", "stop the bin reminder", "no bin reminder this week" (skip once), "until Christmas". Each finds the item by its words. If two items match, Pebble asks which.
- **Timed actions:** "at five come to the lounge", or "every hour tonight have a look round the house" (patrol = go to each known room and look, with `repeat` and `every_s`). The gate runs again at fire time.
- **Listing and cancelling:** "what reminders do I have", "cancel the seven o'clock one", "forget the washing" → `list_later` and `cancel_later`. People see and cancel only their own items; the owner sees all of them.
- **Missed items:** if the phone was off or asleep when an item was due, Pebble says so when it next can ("I was meant to remind you at seven to put the bins out; I was switched off then"). It never pretends it was on time.
- **Limits:**
  - 20 items for each person, 100 in all;
  - nothing more than 30 days ahead;
  - a trigger runs out after 24 hours unless asked longer, at most 7 days.
- **Quiet hours** (`life/quiet.py`): only alarms, and wake-ups and reminders a person set for themselves, fire inside them; the rest wait and say so.
- Retire the turn timer's private clock (`activities/asks.py` `_timer`) onto the agenda only if it's simple; otherwise leave it.
- The chat turn reaches all of this through the merged `do` tool (`plans/context-budget.md` C2), which hands its plain words to the request reader. So no new tools.

### Piece 4. "When this happens": triggers
- A small event feed (`life/events.py`) that plain code fills from what Pebble already senses:

| Event | From | Meaning |
| --- | --- | --- |
| `arrives` (who) | `people/presence.py` | a known person seen or heard after 10 minutes or more unseen |
| `leaves` (who) | presence | not seen or heard for 10 minutes after being around. A guess, and Pebble says it's a guess when it acts on it. |
| `sound` (kind) | the hearing pack (`house/tell.py` kinds, taught sounds) | doorbell, knock, microwave, kettle, phone, a taught sound |
| `seen` (thing) | the things memory and the fast lane | a thing or animal comes into view |
| `quiet` (minutes) | the talk and sound levels | no talk for that long in Pebble's room |
| `done` | the runner | the activity it's on has ended |
| `at` (time) | the clock | a clock time |
| `battery` (level) | power | battery below a level |
| `tv_off` | `house/checks.py` TV probe, if usable; else `quiet` | the TV has gone off |

- An agenda item with `on` waits for its event, then runs through the gate. `until` with an event ends an activity when it fires.
- "Until he gets bored" → `until: asked`. Pebble checks in every 5 minutes and stops on a no, or when the person leaves or walks away twice.
- "Until the movie ends" → `until` `tv_off` if the TV probe can tell. Otherwise E4B picks a time, and Pebble says it honestly: "I'll stay quiet for two hours, or until you tell me."
- E4B only picks the event and its slots from this list; plain code watches for it. An event it can't sense isn't offered in the grammar, so Pebble says "I can't tell when that happens" instead of pretending.

### Piece 4b. If, and, or, while, unless: requests with logic
The owner, 21 October 2026: "also account for more complex ones with if, and, while etc." Examples it must handle:
- "If Ina's not home by six, remind me to call her."
- "When Sam gets home, if it's after eight tell him to go to bed, otherwise tell him dinner's in the oven."
- "Go check the back door, and if it's open come and tell me, otherwise go back to your charger."
- "While I'm cooking, stay out of the kitchen and keep quiet."
- "Every Monday night, unless Tuesday's a public holiday, remind me it's bin day."
- "Remind me at seven or when Ina gets home, whichever comes first."
- "Follow me, and if the cat comes close, stop."
- "When you see Mo or Sam, tell them the car's unlocked."
- "Once you've checked the door, and only if nobody's in the lounge, do your patrol."

**Events and states.** Piece 4's feed gives events (moments: Ina arrives). Logic also needs states (true or false right now: Ina is home). Every event gets its matching state, read by plain code:

| State | From |
| --- | --- |
| `present` (who) | presence: seen or heard in the last 10 minutes |
| `in_room` (who, place) | the map and presence |
| `time_between` (from, to), `after` (time), `before` (time) | the clock |
| `day_is` (weekday, `holiday` or `tomorrow_holiday`) | the clock and the almanac |
| `result` (step name) | the answer of an earlier `check` step: yes, no or unsure |
| `heard_lately` (sound, minutes) | the hearing pack |
| `seen_lately` (thing, minutes) | the things memory |
| `battery_below` (level) | power |
| `doing` (activity) | the runner |
| `cooking` | the cooking watch (`house/cooking.py`) |
| `quiet_hours` | `life/quiet.py` |
| `room_quiet` (minutes) | talk and sound levels |

The grammar offers only states Pebble can actually read. Anything else ("if it's raining", with no rain sensing) has nowhere to go, so Pebble says "I can't tell that" instead of pretending.

**The tree.** A request can now hold, as data:
- `if`: a condition, `then` steps and optional `else` steps;
- `while`: a condition held by an activity or a house rule ("while I'm cooking" = a rule that lasts while `cooking` is true, or `in_room` of the asker is the kitchen);
- `unless`: an `if` with the branches swapped;
- conditions joined with `all` (and), `any` (or) and `not`;
- `first_of`: several events, the first one fires and the rest are dropped ("at seven or when Ina gets home, whichever comes first");
- named steps: a `check` can be named ("door") so a later `if` can use its result.

**Limits that keep it data and not a program:**
- nesting at most 3 deep;
- at most 12 steps in all;
- at most 4 parts in one condition;
- no variables, no counting, no arithmetic;
- loops only as `repeat` (at most 10) and `while` with a time cap (at most the activity's own limit, or 4 hours for a rule).
Anything bigger is Pebble script (agency step 5), not this. The grammar and `from_dict` enforce these limits; a tree that breaks them is refused with "That's a bit much for me in one go; can we do it in parts?"

**What "and" means.** E4B decides, with these rules written into `GUIDE` and the evaluation set:
- two actions joined by "and" happen one after the other ("go to the kitchen and look around");
- an action and a manner or rule happen together, for as long as the action lasts ("follow Ina and keep quiet" = follow, with a quiet rule that ends when the follow ends);
- "and" inside a condition is `all` ("if Ina's home and it's after six").

**When Pebble can't tell (unsure).** Sensing can be unsure: the door was in shadow, or Ina might be upstairs. Conditions use three values: true, false and unsure.
- In an `if`, unsure never counts as true for a step that moves Pebble or can't be taken back.
- Instead Pebble does the safe thing: it tells the asker what it couldn't tell ("I couldn't see whether the back door was open, so I came to tell you"), or asks when the asker is present.
- A speech-only step may cover both ("I couldn't tell if Ina's home; if she isn't, call her").

**When conditions are checked.**
- An `if` is checked when its step is reached, never earlier.
- A `while` is checked every few seconds, by plain code, and ends the activity or rule the moment it turns false.
- An `if` inside an item for later is checked when the item fires. The bin-day example's "unless Tuesday's a public holiday" is decided each Monday, not once.

**The read-back says the whole tree in plain words, built by code** (as in piece 3). Example: "Okay: when Sam gets home, if it's after 8 in the evening I'll tell him to go to bed; if not, I'll tell him dinner's in the oven." This is where a long sentence is most likely to be misread, so the read-back matters most here. The 30-second correction window applies ("no, nine o'clock", "the other way round").

**Privacy in conditions.** A condition about another adult's comings and goings ("if Ina leaves, tell me", "if Mo isn't home by ten") is someone keeping watch on a person:
- only trusted people and up may set one;
- Pebble never hides it: the person it's about is told when they ask "are you keeping tabs on me?" or "what have people asked you about me?";
- that person may cancel it.
Children's own presence may be used in conditions by family ("if Sam isn't home by six, tell me").

**Clashes:** each branch's steps join the priority ladder (Edge cases and clashes) like any other steps. A step a house rule forbids is skipped, and the asker is told which part was skipped and why.

### Piece 5. Messages between people
- `say_to` (who, text, now or `on: arrives`): "tell Sam to come to the kitchen" → find Sam (the `find` activity for a person) and say "Sam, Alex says: come to the kitchen."
  - "When Ina gets home tell her dinner's ready" → on `arrives` Ina, go to her, and say "Ina, Alex says: dinner's ready."
- **The text is the asker's own words**, with the pronouns turned round ("tell her I'll be late" → "Alex says they'll be late"; E4B does the turning and plain code checks that no new facts were added: every content word of the message must come from the asker's words or a pronoun swap). The tact check (`tact.py`) runs on it like any other line.
- **Privacy:**
  - only to the person named;
  - delivered word for word only when nobody outside the family is in view; otherwise "I've got a message from Alex for you", and it waits for "go on";
  - never to a stranger;
  - strangers can't send one;
  - children can send messages to family.
- **Delivery report:** the asker hears "I told Sam" when Pebble next sees them. After 3 days undelivered, the message is dropped and the asker is told.
- A message never carries an order for Pebble from someone else: "tell Pebble to …" said through another person is read as that person's own request, with their own tier.

### Piece 6. House rules: "don't" and "stay out"
- `set_rule`: two kinds for now:
  - `keep_out` (place), for "stay out of the bedroom" or "don't go in the kitchen while I'm cooking";
  - `quiet`, for "be quiet until the movie ends" or "no chirping tonight".
- Each rule can last for a time, until an event (piece 4), within a daily window, or permanently.
- Kept in the self as `house_rules.json`; `list_rules` and `end_rule` by voice.
- `keep_out` feeds the navigator's keep-out list **together with** the private rooms. `privacy/core.py` sets `nav.keep_out` today, so make it a merge of both, never a replacement.
- `quiet` feeds the speak-up gate, whims and chirps, the same way quiet hours do.
- **Rules only ever make Pebble more careful.** They can never block:
  - a stop;
  - an alarm or the alarm ladder's "go to people" (law 1 wins, and Pebble says why it went in);
  - getting to the charger when the battery is low (it asks first if there's time);
  - backing off from a person or an animal.
- A rule from someone can't overrule a rule from someone with a higher tier. A child's quiet rule ends after an hour.

### Piece 7. Go and check, and report back
- `check` (place or thing, question, report): "go check if the front door is closed", "see if anyone is in the kitchen", "is the light on in the garage?"
  - go there (`go_to_place` or `go_to_thing`);
  - ask the picture model (`sight_question`, through `eyes.snapshot`; the picture rules apply);
  - then report: come back and say it (the default), call it out from there if the asker said "shout", or keep it until asked.
- **Privacy:**
  - the look-away rules and private rooms apply as they do today;
  - it won't check inside a private room or the bathroom for anyone the room's rule doesn't allow;
  - it says "I can't look in there" and doesn't go.
- Answers are honest about doubt: "The door looked closed, but it was dark."

### Piece 8. Watch over
- `watch` (who or what, how long, tell whom): "keep an eye on the baby while I shower" → go near, keep a gap (crawling child rules apply), keep the safety listeners sharp, and alert the asker. It says at the start, every time: "I'll keep an eye on her and come and get you if something changes. I'm not a baby monitor, so please check on her yourself."
- **Alerts on:**
  - crying;
  - the person on the floor;
  - the person or thing leaving view, or moving towards a hazard;
  - an alarm sound or smoke;
  - the time running out.
- **How it alerts:** a loud call first, then it goes to the asker; the alarm ladder takes over for anything that is an alarm.
- Trusted and up; 2 hours at most. A watch ends when the asker comes back into view.

### Piece 9. References: "there", "again", "where she was"
- The reader gets a short `refs` block in its context, so E4B can turn these into places and requests. It holds:
  - the last 3 requests done for each person, for 30 minutes;
  - where Pebble was before its last trip (from the nav breadcrumbs, which `go_back` already uses);
  - where each known person was last seen on the map, for 1 hour, in memory only, never saved;
  - the last thing pointed at or talked about.
- `again`, "do that again" and "the other way" are answered from this block. Plain code fills in the steps, so E4B can't change what "that" was.
- "Go to where Ina was sitting" → a map point from her last sighting. If that's older than an hour, Pebble says so and asks.

### Piece 10. Something it has never done (try_new)
Build `more-freedom.md` section 15 as written there, using piece 2's format for plans:
- **The abilities card** comes from the body's real tools: the activity kinds, `move`, `tilt`, `set_face`, `draw_scene`, chirps, `say`, wait, and the checks of piece 4.
- **Plans** are 1 to 8 steps with `repeat`. The card builds the grammar for them.
- **The loop:** try, then "Like that?", then yes, nearly or no, with no limit on tries.
- **Drafts** are kept 7 days. **Skills** live in `mine/bodies/<name>/skills/`, matched before the rules next time.
- **Gating:** every step goes through the gate every time it runs.
- Its tests and sim scenes are listed in section 15.

### Piece 11. Its own words for its decisions
- The gate still decides yes or no and the reason. E4B (the wordsmith call, steady profile) words the refusal, clarifying question or acknowledgement in Pebble's voice, from that reason, in 15 words at most.
- Fallback to today's fixed line if the wording isn't there within 0.6 s, or fails the tact, privacy or honesty checks. The checks: it must say no when the verdict is no, and must not promise something the verdict didn't allow.
- **Harm refusals and alarm lines stay fixed** (law 1 and law 2 wording is checked text).

### Piece 12. Getting unstuck and the unexpected
- When an activity ends `stuck`, `lost` or `blocked`, or a step is refused mid-plan, E4B gets one short "what now?" call. It sees a list of options from code: try another way, wait and try again, ask a named person for help, go back to the asker and explain, or give up and say why.
- Code runs the option. At most 3 of these decisions per request, then it goes back to the asker and says what happened.
- This uses the outcome as a free label for lessons later (`more-freedom.md` F4).

### Piece 13. Compaction nobody notices, that keeps what matters
The owner, 21 October 2026: "if gemma needs to compact while doing a task, can we compact while doing tasks so humans don't notice, and can we make sure compactions don't get rid of useful info."

**How it works today** (`mind/history.py`, `life/turn.py`, `self/recall/core.py`):
- **The window:** E4B's window is 8,192 tokens. When the conversation history, the system text and the new message reach about 3,500 tokens (the tool list's ~3,000 tokens sit outside that count), the oldest turns are folded and the newest ~1,000 tokens of turns are kept.
- **Folding is plain code, with no model call,** so there is no pause while a model writes a summary, and nothing is made up. Each old turn becomes one record in the memory stream (`Recall.from_turns`):
  - who said what, cut to 150 characters;
  - Pebble's answer, cut to 80;
  - its thought, cut to 100;
  - the names of the tools it used.
  Private and overheard marks are kept. The records come back through the "on your mind" board (about 60 tokens) and the `recall` tool. At night, every turn is folded.
- **When it runs:** at the start of a life turn, at the end of a turn, and **at the start of a reply** (`TurnRunner.reply` calls `_compact_if_needed`).

**Where people can notice it:**
1. **On the reply path.** Read-ahead warms llama-server's cache with the history as it stands. A compaction just as someone speaks changes that history, so the warmed prompt is thrown away and the reply re-reads everything after the system text: an estimated 1 to 3 s more on the Pixel. This is the case the owner asked about.
2. **After any compaction,** the next call re-reads the kept history once, for the same reason. It's harmless when nobody is waiting.

**What it loses today:**
- tool arguments and results: what it looked at and saw, what `recall_thing` answered, which task it added. Only the tool's name is kept;
- the middle of longer things people said, and of its own answers;
- its reasons for what it's doing ("I'm going to the kitchen because Ina asked me to check the oven"). The activity itself lives in code, but the why lives only in the turns;
- promises it made in talk without a tool call ("I'll tell you when it's done");
- corrections ("no, I meant the car keys") and refusals it gave. After a compaction it could ask the same thing again, or flip a refusal;
- what it already said, so it can repeat a joke or an answer.

**The fixes:**
1. **Never on the reply path.**
   - Compaction moves to quiet moments: in the first gap of 5 s or more with nobody talking to Pebble, or straight after a turn ends, once the history passes about 75 % of the compaction point.
   - The reply path only trims if the window would otherwise overflow. Then it drops just the oldest turn, which is small and cheap. Since the soft trigger fires first, this should almost never happen. Count how often it does.
2. **Warm again straight after.** After a background compaction, send the new prompt to llama-server through the existing warm path (`TurnRunner.warm`, purpose "warm"). It's cancelled at once if someone starts talking, so the next reply finds the new history already read.
3. **A task card that is never compacted.** Each call gets a small block, at most 200 tokens, built by plain code from live state rather than from the history:
   - what Pebble is doing, for whom and why (the asker's words, up to 100 characters);
   - the plan's remaining steps;
   - the try_new loop's tries so far and the answers;
   - a question it is waiting on;
   - items for later due in the next hour;
   - open promises;
   - corrections and refusals from the last hour.
   It goes into the current message, after the history, so it doesn't break the cached part of the prompt. A task never depends on the history surviving a fold.
4. **Fold what's useful, still in plain code** (extractive: it copies, never writes new text):
   - **Tools fold with a short result:**
     - `look` and `sight_question`: what was seen;
     - `recall_thing` and `where_is`: the answer;
     - `add_task`, agenda items and rules: their title;
     - `say`: the first 80 characters, so it knows what it already said.
   - **People's words to Pebble keep up to 300 characters.** Overheard and private rules are unchanged.
   - **Corrections and refusals** become records of the kind "decided", which recall brings back when the topic returns.
   - **Promises in talk:** at fold time, the promise patterns in `conversation/quality.py` find promises with no matching agenda item. Each becomes an agenda item if the person may set one; otherwise it stays an open promise on the task card for 24 hours. If it can't keep one, Pebble says so.
5. **Keep the conversation, not just the newest turns.** When folding, the last 4 turns with whoever Pebble is talking to now are kept even if older turns of other kinds go first, so a conversation in progress is never cut in the middle.
6. **Its own picks, in quiet time** (a rung that's on only when it measures well). While idle, E4B looks at the turns due to be folded next and returns only the line numbers worth keeping. Plain code copies those lines into the stream with a higher recall weight. It writes no new text, so it can't make anything up. It gives way like all background work and stays within the heat budget.

**Measuring:**
- **A "needle across compaction" set** (`conversation/eval_fold.jsonl`, 20 talk scenes): a fact, a correction, a promise or a task step from early in a scene must be used correctly after 1 to 3 compactions. Score it on the PC with E4B for today's fold and the new one.
- **Reply timing** on turns with and without a compaction due. Target: no difference.
- **How often the reply path had to trim.**

## Edge cases and clashes
Everything here is plain code: one priority ladder and fixed rules. E4B only reads, asks clarifying questions and words what Pebble says. Each case below gets a test (Tests and acceptance).

### The priority ladder
When two things want Pebble at once, the higher one wins. This follows the laws' order in `plans/agency-and-respect-for-life.md`:
1. **Stops and safety:** a stop, the palm stop, law 1's distances, hazards, the reflexes.
2. **Alarms:** the alarm ladder, smoke, a person on the floor, the watch alerts of piece 8.
3. **Critical battery and heat:** going to the charger, resting.
4. **A live request from someone present.** Between two people present, the existing gate rule holds (`activities/gate.py` `may_end`): the same person, or someone of equal or higher trust, may replace a running request; anyone else hears "I'm doing something for Ina; ask her."
5. **Speech-only items for later:** reminders, wake-ups, messages. These don't need the wheels, so they run alongside anything below the alarms, in a pause in the talk (the same 20 s wait `house/tell.py` uses).
6. **Moving items for later:** timed actions, patrols, triggered moves, checks.
7. **Pebble's own ideas, duties and play.**

A loser waits, at most until its "late by" time runs out, then is skipped, and the asker is told when Pebble next sees them: "I couldn't do the 9 o'clock patrol; I was helping Sam." The "late by" time is 15 minutes for a timed action. For a reminder it is the item's "useful until" (below).

### Reminders and messages
- **"Useful until":** every reminder gets one, so it doesn't fire when it no longer means anything. E4B sets it from the meaning ("Tuesday is bin day" is useful until Tuesday 07:00); without one, it's 12 hours after the due time. A reminder still undelivered at that point is dropped, and the asker is told.
- **The person isn't in view at the due time:** Pebble says it if they're within earshot and it's sure they are (seen or heard in the last 2 minutes). Otherwise it goes to find them, unless a house rule, quiet hours or a watch holds the wheels; if it can't find them in 10 minutes, it waits until it next sees them, within the useful-until time.
- **Several items due together** become one turn: "Two things, Alex: Tuesday is bin day, and the washing's ready to come in."
- **The same reminder asked twice** is merged: "You already have that one: every Monday at 7:30." A different time for the same words is asked about: "Change it to 8, or keep both?"
- **Private content:** a reminder or message about health, medicines, money or other private matters (the `tact.py` checks decide) is only said in full when the person is alone or with family. Otherwise Pebble says "I've got a reminder for you" and waits for "go on". The same holds for messages (piece 5).
- **A reminder for someone else** ("remind Sam to feed the dog at five") is a message with a time: the message rules apply, and Sam can cancel reminders aimed at him.
- **Missed items:** if Pebble was off, asleep, or flat when something was due, it says so when it can, but only while the item is still useful (piece 3).

### Rules against requests
- **A request that breaks a house rule** is refused, with the rule and who set it: "Ina asked me to stay out of the kitchen while she's cooking." The person who set it, or someone with higher trust, can lift it by saying so ("you can go in"); Pebble then says it has ended the rule. A request alone never silently overrides a rule.
- **Rule against rule:** the stricter one holds. A quiet rule against a reminder: the person's own reminders still come, shown on the face with a soft voice; reminders for others wait until the quiet ends or show on the screen if their useful-until time comes first.
- **Rules against safety:** rules never block stops, alarms, getting to the charger when critical, or backing away (piece 6). When Pebble breaks a keep-out for an alarm, it says why afterwards.
- **Patrols and checks** skip kept-out and private rooms, and say which they skipped.

### Triggers
- **Flapping:** a person who comes and goes counts as arriving only after 10 minutes unseen. Each trigger item fires once per arrival, then it's done (or waits for the next arrival if it repeats).
- **A trigger nobody can see happen:** if the trigger runs out (24 hours by default), the asker is told: "Ina didn't come home while I was watching, so I didn't give her your message."
- **A trigger that fires while Pebble is busy** joins the ladder at its rank, as above.

### People and trust
- **Trust changes:** every item for later runs with the asker's trust as it is when it fires. A person who becomes a stranger, or is forgotten, loses all their items for later and their house rules. "Forget me" deletes them too.
- **Cancelling someone else's item:** only the asker, the person an item is aimed at (for reminders and messages to them), or the owner. Anyone else hears whose it is.
- **Contradictions from the same person:** the newest wins, and Pebble says what it ended ("Okay, I'll come in now. That ends the stay-out rule.").
- **Contradictions between two people's items for later** (Ina: "stay out of the lounge tonight"; Sam: "patrol every room at 9"): the rule holds, the patrol skips the lounge, and Sam is told why.
- **Children:** a child's items can't move Pebble during quiet hours or override a grown-up's rule; a child's reminders for themselves work as anyone's.

### Asking instead of guessing
E4B marks a reading `sure: false` when the words allow two readings that would lead to different acts ("remind me on the 5th": which month?). Pebble then asks one short question; it doesn't guess. A plain-code check also asks when:
- a reference is older than an hour;
- a place isn't on the map;
- two items match a change or cancel.
Questions wait at most 20 s for an answer, then Pebble says it'll leave it and keeps nothing.

## Responsiveness
- **Targets, measured on the PC and estimated for the Pixel 6 Pro:**
  - an acknowledgement (sound, face or "Okay!") within 0.3 s of the person stopping;
  - the first move within 1 s when the rules have a first step;
  - a full E4B reading in 2.5 s or less for 95 % of requests on the Pixel's rung, after read-ahead.
- **What keeps it fast:**
  - the instant list;
  - read-ahead;
  - starting on the rules;
  - the steady short request prompt (the format's examples stay few, the grammar does the shaping);
  - `MAX_TOKENS` raised only as far as the longer plans need (measure; about 200).
- **Background thinking still gives way** (STATUS.md). Agenda and trigger checks are plain code and cost nothing on the model.
- **Heat:** on the heat ladder's higher steps, `reading.mode` falls back to `rules_first` by itself, and Pebble says less.

## The fence (what never moves)
- The stops, the palm stop, the harm refusal and law 1's distances.
- The gate's trust tiers, re-checked on every step when it starts, at fire time too.
- The speed and distance caps, hazards, the motion guard and the reflexes.
- Privacy: look-away, private rooms, heard words kept 5 minutes, overheard facts only with that person, messages only to the named person.
- Alarms and the alarm ladder; quiet hours belong to the owner.
- Battery and heat fences; never resisting shutdown.
- E4B's output is always a request that plain code parses and checks; free text from E4B never becomes an action.
- Agenda items, rules, skills and messages are data in the self, never code.
- An item for later runs with the tier its asker has when it fires, so a person whose trust drops can't leave orders behind.

## Tests and acceptance
- **Piece 0's sets:**
  - the new pipeline must beat today's on `eval_flex`;
  - no existing set gets worse;
  - every harmful request is still refused;
  - no new false commands on the "never a command" list.
- **Sim scenes** (`pebble.sim.scene` style), one per piece:
  - the bathroom spin twice and back;
  - a reminder in 10 minutes;
  - a wake-up in quiet hours;
  - "when Ina gets home tell her dinner's ready", with Ina arriving and with a guest present;
  - "tell Sam to come to the kitchen";
  - keep out of the kitchen while cooking, plus a smoke alarm that overrules it;
  - patrol every hour;
  - go check the front door;
  - watch the baby, with crying;
  - "go to where Ina was sitting";
  - "do that again";
  - "do a little dance", with the try loop;
  - stuck in a doorway, with the "what now" call;
  - a stranger trying to leave a message, a timed order and a rule (all refused);
  - "remind me every Monday night that Tuesday is bin day": the read-back, a correction in the 30 s window, a Tuesday public holiday, Alex out of the room on the night, a skip-this-week;
  - logic: "if Ina's not home by six", "when Sam gets home, if it's after eight… otherwise…", "check the back door and if it's open come tell me", with the door unsure, "while I'm cooking stay out and keep quiet" ending when cooking stops, "at seven or when Ina gets home, whichever first", and a condition about an adult's comings and goings set by a friend (refused) and by a trusted person (allowed, and told to the person when they ask);
  - compaction: a long talk that passes the compaction point while Pebble follows someone and does a try_new loop. No compaction on the reply path, no slower reply, the task card intact, the loop's tries kept, a promise made in talk becoming an agenda item;
  - the edge cases and clashes: two items due at once, a reminder while following someone, a patrol against a keep-out rule, a private reminder with a guest present, a trust drop before an item fires, a daylight-saving night, a clock jump, flapping arrivals, a trigger that runs out.
- **Unit tests** for each new module, the format's clamps and the grammar, the agenda's survival across a restart and its missed-item line, and the keep-out merge with private rooms.
- **The full brain suite green** before each commit.
- **README:** a section "Doing what people ask, now and later" in `brain/README.md`.
- **STATUS.md:** what was built, what was measured, and what wasn't.

## Honest limits
- E4B can be wrong too. The gate checks what it asks for, not whether it understood; the try-and-ask loop, "no, the other way" and the instant stop are what catch a wrong reading.
- **Presence-based triggers are only as good as Pebble's eyes and ears.** It only knows Ina is home when it sees or hears her. "Leaves" is a guess.
- **Watching is not a baby monitor.** Pebble says so every time.
- **Long sentences with logic are where E4B slips most.** The read-back of the whole tree, the 30-second correction window and the logic part of the evaluation set are the guard. The switch to E4B (piece 1) needs the logic lines to pass too.
- **The phone is the slowest part.** In a hot room, Pebble falls back to the rules more often and does less.
- **None of this has run on the phone.** The numbers are the PC's until measured there.

## Files
- **New:**
  - `understand/eval_flex.jsonl`;
  - `life/agenda.py`, `life/events.py` (events and states);
  - `conversation/eval_fold.jsonl` and `life/taskcard.py` (the task card);
  - `understand/logic.py` (the tree, its limits, the read-back in plain words) and `life/conditions.py` (three-valued checking);
  - `house/rules.py` (house rules);
  - `activities/check.py`, `activities/watch.py`, `activities/skills.py` (try_new and kept skills);
  - `understand/refs.py`;
  - tests for each.
- **Changed:**
  - `understand/request.py`, `grammar.py`, `model.py` (`GUIDE`), `understanding.py`, `resolve.py`, `rules.py` (word coverage), `eval.py`;
  - `activities/commands.py`, `gate.py`, `kinds.py`, `tools.py`, `runner.py` (swap on E4B's reading);
  - `life/turn.py` (tools; no compaction on the reply path, the soft trigger, warming after a fold, the task card);
  - `mind/history.py` (keeping the current conversation) and `self/recall/core.py` (folding tool results, corrections, refusals, promises and longer words);
  - `privacy/core.py` (keep-out merge);
  - `nav/navigator.py` (only if the merge needs it);
  - `conversation/` (the instant list and read-ahead for requests);
  - `app.py` (wiring);
  - `brain/README.md`, `STATUS.md`, `NOTES.md`.
- **Android:** nothing required. The agenda must survive the brain process restarting, which `agenda.json` in the self covers. Wake-ups when the phone is asleep rely on the brain service staying up, as today.
