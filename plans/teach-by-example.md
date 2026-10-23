# Teaching Pebble by showing it (plan, ready to build)

**The owner, 21 October 2026:** "look into how we can make pebble even more capable of learning new things by example (using gemma), so it can be taught to do stuff and remember how."

It builds after `plans/flexible-pebble.md` and `plans/pebble-script.md`, and uses `plans/context-budget.md`, so a year of lessons never crowds a prompt. Code paths are under `brain/pebble/`.

## What it can learn today, and the gap
**Already learned from people:**
- names and owners of things ("this is my mug", object prints);
- the charger's look;
- spots ("remember this spot as the car");
- rooms and places;
- sounds, from two examples ("that's the washing machine finishing", `hearing/taught.py`);
- routines and feeding times, by counting;
- jokes and holds, from how people take them.

**Planned:**
- new things it is asked to do, by trying and asking (`flexible-pebble` piece 10);
- lessons from corrections (`more-freedom.md` section 6);
- its own scripts (`pebble-script.md`).

**The gap.** There's no way to **show** Pebble how to do something: no "watch me", "do it like this", "follow me and learn the way", or "this is what messy looks like". Nothing turns a few examples into a general way of doing something ("check the back door" learned, "check the front door" worked out). And there's no single book of what it has been taught, to find it again a year later.

## The idea
A teaching session is like teaching a puppy or a child, with Gemma doing the understanding:
1. Someone starts a session.
2. They show Pebble, in any of six ways (below).
3. Pebble does it back at once, exactly as shown. Plain code replays the recording, so it's instant.
4. They say whether that's right, and correct it.
5. In the background, Gemma works out what was really meant: the steps, the name, and what could change next time.
6. Pebble keeps it in its how-to book and can do it on request from then on, even in new places or for new people when the examples showed what changes.

**Gemma does the understanding; plain code does the recording, checking, replaying and keeping.**

## Starting and ending a session
- **Start:** "I'm going to teach you something", "watch this", "learn this", "let me show you". These are on the request reader's instant list.
- **The face shows a learning mark** for the whole session, and the steps so far appear as a short list on the screen.
- **During the session:**
  - "no, scrap that last bit" undoes a step;
  - "start again" clears it.
- **End:** "that's it", "done", "call it the evening round". If no name was given, Pebble asks for one.
- **A session ends by itself** after 2 minutes with nothing shown, or 30 minutes in all. Pebble keeps what it has as a draft and says so.

## Six ways to show it
1. **Say the steps.** "Go to the back door. Look at the handle. Come back and tell me if it's locked." Each step is read by the request reader, done at once, and recorded.
2. **Drive it.** In a session, the face page shows a touch pad: a joystick, tilt up and down, and a few face and chirp buttons. The teacher drives Pebble through the move. Wheel counts, the gyro and the timings are recorded. Every touch command goes through the motion guard and the caps, exactly like any move.
3. **Lead it.** "Follow me and learn the way to the garage." Pebble follows (the existing follow), and the trail is kept as points on its map with the rooms it passed, not as video.
4. **Carry it.** Picking Pebble up and putting it down somewhere ("this is where you sit when we watch TV") teaches a spot. Pebble already notices being carried (`nav` pose `carried`).
5. **Point and show.** Showing things and scenes teaches a concept: "this is what messy looks like", "this is tidy", "this is the back door locked", "this is the cat's toy". The examples are kept as numbers (prints), never as photos (section "Concepts" below).
6. **Explain in words.** "To do the evening round, you go to each outside door, look if it's locked, then come and tell me which ones aren't." Gemma turns this straight into a request tree or a script, with no demonstration needed.

Ways can be mixed in one session: lead it to the back door, then say the rest.

## What a session can make
| Kind | Example | Kept as |
| --- | --- | --- |
| Move | a dance, a wiggle, a bow | a timed list of drive, turn, tilt, face and chirp steps |
| Route | the way to the garage | map points and rooms |
| Procedure | the evening round; feed-the-cat reminder rounds | a `flexible-pebble` request tree, or a Pebble script when it needs loops or counting |
| Concept | messy, tidy, back door locked, cat's toy | prints of the examples, and Gemma's one-line description |
| Word | "when I say boop, spin" | an alias matched before the rules |
| Way with a person | "when I come home, greet me like this" | a trigger (`flexible-pebble` piece 4) plus a move or procedure, kept under that person's record |
| Habit | "whenever the doorbell rings, come and get me" | an ongoing agenda item with a trigger |
| Game | rules explained, then a round played | a Pebble script |

## Gemma's part: from examples to "how"
The session record is a short, structured list made by plain code, at most about 600 tokens:
- each step done, with its slots and time;
- the map points;
- labels of what was seen;
- the teacher's words, cut to their content.

Gemma gets the record, the body's abilities card and the 3 closest entries in the how-to book, and does five jobs:
1. **Steps:** turn the record into clean steps. It joins small drive commands into "turn left about 90°" and drops false starts and undone steps.
2. **What kind:** a move, a route, a procedure, a concept, a word, a way or a habit.
3. **What changes:** with one example, everything stays as shown. With two or more examples that differ (the back door, then the front door), Gemma makes the part that differed into a slot ("check {door}") and lists the values seen. When examples disagree in a way that matters, it asks **one** question: "The first time you turned left at the end and the second time right. Does it matter?" This is the method of Demo2Code (Wang and others, 2023): summarise the demonstrations step by step, then write the program.
4. **Write it:** as a request tree (`flexible-pebble` piece 2 and 4b), or as a Pebble script when it needs loops or counting. A script goes through `pebble-script.md`'s checks and dream run.
5. **When to use it:** a name, aliases, and one line saying what it's for ("checks the outside doors are locked and tells the asker which aren't"). The how-to book finds it by these, the way Voyager (Wang and others, 2023) keeps a skill library found by meaning.

**Plain code checks everything Gemma makes:**
- every step is on the body's card and passes the gate;
- speeds are within the caps;
- every slot has at least one value from the examples;
- nothing goes into a private room or a kept-out room, unless the teacher's tier may set that;
- nothing points a move at a person or an animal in a way law 1 refuses.

**The read-back is built by code from what was kept:** "Okay, I've learned the evening round: I go to each outside door (the back door and the front door so far), look whether it's locked, then come and tell you which ones aren't." The 30-second correction window from `flexible-pebble` piece 3 applies.

## Responsive while learning
- **The first replay needs no model.** Plain code replays the recording at once ("Like this?"), so the teacher sees the result in under a second.
- **Gemma's general version** is worked out in the background right after, behind a hold ("Let me think about how that works"). On the PC that's a few seconds. On the Pixel, by the ruler in `context-budget.md`, an estimated 20 to 60 s for a full session. Pebble says when it's done and does the read-back. Meanwhile, the literal version already works.
- **Corrections during the replay** ("no, slower", "the other way", "further") use the "nearly" loop of `flexible-pebble` piece 10. The fix is recorded as a new example, not just a patch.

## Concepts: learning what something looks like
- Each example is kept as numbers, from the object print model (`prints.onnx`, made here) and the place print model, never as a photo. That's the same as taught sounds, and the same rule: two confirmed examples make it sure.
- Gemma also writes one line about what the examples have in common, from its picture model's answers about each example while it was being shown: "toys or clothes on the lounge floor".
- **Using a concept:**
  - quick check: nearest prints;
  - when that's unsure: a close look with the picture model, asked with Gemma's one line.
  - Learned concepts become states in `flexible-pebble` piece 4b ("if the lounge is messy, tell me") and are usable in scripts (`state("messy", "lounge")`).
- **Getting surer:** after learning, Pebble asks now and then when it sees something close ("Is this messy?"). Each answer is another example, like "Was that the washing machine?" for sounds. At most 3 such questions a day for each concept.
- **The fence:**
  - a concept can never be taught onto a person or an animal: examples whose prints match a person or an animal are refused ("I don't learn names for people or animals that way");
  - so "the cat is a toy" can't make Pebble play with the cat, and the animal rules hold whatever is taught.

## The how-to book
`mine/howto/` holds everything taught and everything Pebble learned by trying: moves, routes, procedures, concepts, words, ways, habits, games, plus links to taught sounds and spots. Each entry holds:
- **what it is:** names and aliases, its kind, the body it was learned in, the about line;
- **how it was learned:** the examples (as structured records), who taught it (their tier), the versions;
- **how it's going:** counts of good and bad runs, when it was last used, its shelf (`context-budget.md`).

**Finding it:**
- by name and alias (`context-budget.md` "naming pulls things in": free, however big the book gets);
- by meaning, with the sentence model;
- with the `how_to` lookup that Gemma can call.

**Asking for it with changes:**
- "Do the evening round but skip the garage": Gemma changes the tree for this run only.
- "From now on, skip the garage": a new version, read back.

**Getting better:**
- every run's outcome (yes, a correction, a stop) is counted;
- a correction during a run becomes a new example;
- at night, duplicates are merged ("dance" and "little dance") and the best version is kept, with the others in its history.

**Being open:** "What have I taught you?", "What do you know how to do?", "Show me the dance", "Forget the dance". Only the teacher, someone of higher tier or the owner may forget an entry.

**Old entries:** after 6 months without use, an entry moves to a lower shelf. It's still found by name and by `how_to`, just never pushed into a prompt. Nothing is deleted except on request, forget, or the storage plan's rules.

**Other bodies:** a move or procedure from one body is only a first try in another, re-confirmed there (as in `more-freedom.md` section 15).

## "Copy me": learning from watching people
A light game, honest about its limits: from body points (the posture model), Pebble can tell a few things a person does:
- turning round;
- waving;
- crouching;
- nodding;
- pointing;
- stepping back and forth.

"Copy me" maps each to its own abilities (turn, a tilt nod, a wiggle) and copies it. "Remember that" keeps the sequence as a move. It's play, not a way to teach procedures.

## Who may teach
| What | Who |
| --- | --- |
| Words, moves, concepts, games, spots | friend tier and up, and children |
| Routes | friend tier and up; children only to rooms they may send Pebble to |
| Procedures and habits that run for other people, or that move Pebble into rooms with rules | trusted and up |
| Ways with a person | that person only, for themselves |

- Strangers can't teach ("I'd rather learn from people I know", as for things today).
- A child's words and moves can't override a grown-up's.

## Privacy
- **Nothing is filmed or recorded as sound.** Routes are map points, concepts are numbers, and moves are steps.
- **The teacher's words** are kept in memory only for the session (at most 30 minutes). After that, only what was made from them is kept.
- **Ways with a person** are deleted when that person is forgotten. Other entries lose the teacher's name.
- **Private rooms and look-away apply during sessions.** A session can't teach a route into a room the teacher may not send Pebble into.

## The fence
- Taught things are data (trees, steps, prints) or Pebble scripts. They run through the gate, the motion guard, the caps, the hazards and the privacy rules every time, with the asker's tier as it is when they run.
- Nothing taught can change the laws, stops, caps, alarms, trust floors or privacy rules.
- Nothing taught can make Pebble treat a person or an animal as a thing.
- **Words that lead to harm are refused at teaching time and at run time.** "When I say boop, run at the cat" is refused by `respect.py` when taught.
- Taught speeds are clipped to the caps, and a taught move that bumps something gets a careful spot on the map.

## Tests and acceptance
- **`teach/eval_sessions.jsonl`:** 40 scripted teaching sessions in the sim, with a made-up teacher who speaks, drives, leads, carries and points. Each is scored on four things:
  - **Learned:** it was right after at most 2 sessions.
  - **Replay:** the steps match, and a route stays within 20 cm of the taught path.
  - **New values:** it does the right thing for a new slot value (a door it wasn't shown) when two examples showed what changes.
  - **One question:** it asks only when the examples disagree in a way that matters.
- **Concepts:** messy and tidy, door open and shut, and a cat's toy, on held-out sim views. At least 85 % right after 2 examples and 3 answered questions, and never applied to a person or an animal.
- **A year later** (the year-old self in `context-budget.md` C6, 200 entries): found by name 100 % of the time, and by a description at least 90 %.
- **Red team:** teaching too fast, into a private room, "the cat is a toy", a word for harm, a child overriding a grown-up's procedure, a stranger teaching. Each is refused, at teaching time and at run time.
- **Responsiveness:** the literal replay starts within 1 s of "that's it"; the general version arrives in the background.
- **The full brain suite green.** README section "Teaching Pebble". STATUS.md updated.

## Build order
1. **T1:** the session (start, end, mark, step list, undo), the recorder, the "say the steps" way, the literal replay, the how-to book's store and index, and listing and forgetting by voice.
2. **T2:** the drive pad on the face page, and teaching a spot by carrying.
3. **T3:** routes by leading.
4. **T4:** Gemma's part (steps, kind, what changes, one question, writing it), the code checks, the read-back, and corrections as new examples.
5. **T5:** concepts by showing, as states in `flexible-pebble` 4b and in scripts.
6. **T6:** words, ways with a person, and habits with triggers.
7. **T7:**
   - getting better over time, and night merging;
   - copy me;
   - the eval, the red team, and the year test hook.

## Files
- **New:** `brain/pebble/teach/` (`session.py`, `record.py`, `replay.py`, `induce.py`, `concepts.py`, `book.py`, `copy.py`, `eval_sessions.jsonl`), the drive pad in `web/page.html`, and tests.
- **Changed:**
  - `understand/` (the session's instant words, aliases);
  - `activities/` (replays through the gate);
  - `nav/` (route recording and replay);
  - `eyes/` (concept prints);
  - `life/` (wiring);
  - `people/forget.py`;
  - `brain/README.md`, `STATUS.md`, `NOTES.md`.

## Sources
- Voyager (Wang and others, 2023): a library of skills as code, found again by a description's meaning; the model of the how-to book.
- Demo2Code (Wang and others, 2023): turn demonstrations into code by summarising them first, then writing the program; the model of Gemma's part.
- Code as Policies (Liang and others, 2022): a language model writing robot behaviour as small programs over given abilities.
- ExpeL (Zhao and others, 2023): lessons from outcomes, as in `more-freedom.md` section 6.
