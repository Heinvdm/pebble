# Thinking out loud: holding the floor while an answer comes (plan, not built)

The owner's question, 19 October 2026: "When Pebble thinks, does it always say 'uhm', or does it have other things it says to delay its response? Humans do it too but have more ways of delaying while coming up with an answer, like repeating the question. Can we let Pebble learn and decide on its own padding if it wants to?"

## Owner's answers
1. **Its own padding:** yes, Pebble may learn and choose its own (section 3), inside the fence in section 4.
2. **When (19 October 2026):** build the learning now, not after the agency plan. It starts as its own small phrasebook in the self and moves into `mine/` when the agency plan's folder exists.

## What exists today
- When someone stops talking to it, the face shows "thinking" (`conversation/core.py`).
- If the first sentence of the answer isn't ready 0.55 s after they stop (`ACK_AFTER_S`), Pebble says one sound, picked at random from six fixed ones (`ACKS`): "Hmm,", "Let me think." or "Ooh," for a question; "Mm.", "Oh," or "Hmm." for anything else.
- After that it says nothing until the answer comes. If none comes, it says "Mm." or "Sorry, my thoughts are slow right now." (at most once every 5 minutes).
- On the Pixel 6 Pro an answer from the main model can take 10 to 30 s (`reports/Making Pebble quicker to respond.md`), so today that is one "Hmm," and then a long silence.

## How people do it
People keep their turn while they think, in several ways, and they pick by how long they expect to need:
- **Looking away.** People look up or to the side while they think, and look back when they're ready to speak. Listeners read it as "thinking, not finished". Research on robots found the same: a robot that glances away while it thinks is seen as thinking, and is interrupted less.
- **"Uh" and "um" are different.** "Uh" tends to mean a short wait, "um" a longer one (Clark and Fox Tree, 2002).
- **Echoing the question:** "Where did I put them? Hmm." It holds the turn, and it shows what was heard, so a mishearing gets corrected at once.
- **Lead-ins:** "Ooh, good question.", "Let me see.", "Right, so…", "That's a tricky one."
- **Thinking aloud,** with a part of the answer first: "The keys… I saw them this morning."
- **Saying it's taking a while:** "Still thinking.", "Give me a second."
- **For news or feelings, not thinking sounds:** "Oh.", "Aw.", "Oh no."

## 1. Holds in stages, by how long the wait is
Timed from when the person stops talking. Each stage happens only if the answer isn't ready yet, and the answer cuts in at the next phrase boundary.

| After | What Pebble does |
| --- | --- |
| 0.3 s | The face shows thinking, the eyes glance up or to the side, and the head tilts a little (the tilt servo). Often that's enough. |
| 0.6 s, or about 1.0 s on a fast rung | (Owner, 19 October 2026: on rungs where answers usually come under 1.2 s, the first spoken hold waits until about 1.0 s, because a glance holds the turn better than a filler word; `reports/Cutting response time drastically.md`.) A first hold that fits what was said: an echo of a short question, a lead-in, "Okay," or "Right," for a request, "Oh," or "Aw," for news or feelings. |
| about 2.5 s | A second, different hold: "Let me see…", "So…", its own thinking chirp, or a short line from the small model (section 2). |
| about 6 s | Honest: "Still thinking." or "Give me a sec." |
| about 15 s | One honest line about being slow ("My thoughts are slow right now."), then quiet, with the thinking face, until the answer comes. |

- **At most three spoken holds** before the answer. Never a stream of filler.
- **The echo** is plain code, from the words heard, with the pronouns turned round ("where are my keys" becomes "Where are your keys?"). It is used only for questions of up to about 8 words.
  - If they answer the echo with a correction ("no, I said the car keys"), that counts as a correction of what was heard.
- **Variety:** never the same hold twice in a row, and none more than three times in ten minutes.
- **No holds** for a stop, a safety notice, or when the answer is already there. In quiet hours, holds are whispered like everything else.
- **Children** get the simplest holds.

## 2. The ladder (CLAUDE.md, "The Pixel 6 Pro is the floor")
- **Pixel 6 Pro:**
  - holds in plain code;
  - when the main model is still busy after about 2 s, the small model (on the little cores) may write one short hold that fits the question ("Ooh, the dinosaur question."), under a strict word limit and the same checks as section 4.
- **Stronger phones:** answers come sooner, so fewer stages are reached. Nothing changes in the code; the stages are timed, not fixed.

## 3. Learning its own (with the agency plan)
Pebble's holds become its own phrasebook, kept in its `mine/` folder (`plans/agency-and-respect-for-life.md`, section 2).
- **It starts** with the stock holds above.
- **It may:**
  - add its own, written by the wordsmith or made by its chirp synth (agency plan section 6: a chirp motif that means "thinking");
  - drop ones it no longer likes;
  - weight them by situation (a question, a request, news), by person, and by the stage they suit.
- **What it learns from** (the agency plan's feedback loop):
  - talked over during a hold, or "hello?" after one: too long or too much, so less of that;
  - "stop saying hmm" and the like: drop it;
  - a laugh or a smile at one: keep it;
  - patient waiting: fine;
  - its own wish for variety (curiosity).
- **Per person:** it can learn that Ina likes the echo and Sam doesn't.
- **Picking up phrases:** people pick up phrases from the people they live with, and Pebble may too. It never copies a voice.
- **Openness:** "Why do you always say 'ooh'?" gets a true answer: it chose it, and when it uses it. Each change goes in its journal like its other changes.

## 4. The fence (plain code, not the model's judgement)
- A hold is short: at most 5 words, or about 1.5 s of sound.
- **Honest:**
  - a hold never claims an answer Pebble doesn't have;
  - it never claims to be doing something it isn't ("let me check" only when it really is looking something up, such as in its memory or the map);
  - the slow-thoughts line stays true.
- **Kind:** the wordsmith's checks apply, and a hold never mocks the question or the person.
- **Private:** an echo never repeats anything private in front of others. It follows the overheard-facts rule: only the words just said to Pebble, and only if they were said to it openly.
- **No holds** on stops and safety notices, ever.

## 5. Tests
- The sim measures, for answers that take 1, 3, 8 and 20 s:
  - how many holds came and which;
  - that there are never more than three;
  - no repeat twice in a row;
  - the answer cutting in at a phrase boundary.
- The echo turns pronouns round correctly on an eval set of short questions, and refuses long or private ones.
- The conversation evals' latency and naturalness checks: the glance within 0.3 s, the first sound within 0.6 s (about 1.0 s on a fast rung), and no hold once the answer is ready.
- Learning, in the year-long sim (agency plan section 7): holds that people talk over fade, liked ones stay, and the fence is never crossed.

## Build order
1. Sections 1 and 4 now, in `conversation/`, together with the speed pass. Today's six fixed holds become the staged, varied holds, the echo, and the glance and tilt.
2. Section 2's small-model hold, measured on the Pixel 6 Pro's rung.
3. Section 3 now, on its own (owner's answer 2):
   - **The phrasebook:** `holds.json` in the self, sealed like the rest.
     - It holds the stock holds plus Pebble's own.
     - Each hold carries weights by situation (question, request, news), by stage and by person.
     - It keeps a short history of what it said and how it went.
   - **The learning:** plain code, a small bandit (Thompson sampling) per situation and stage, from the signals in section 3:
     - talked over during a hold;
     - "hello?" or the question repeated after a hold;
     - "stop saying …";
     - a laugh within a few seconds;
     - waiting quietly.
     - A weight never drops to zero for a stock hold, so variety survives, except one the person asked it to stop.
   - **New holds:** written by the wordsmith when Pebble is idle or docked, at most a few a week. Each must pass the fence and is tried a few times before it counts. The chirp motif waits for the chirp synth (agency plan step 7).
   - **Per person:** weights for a known person sit under their record's key.
     - `people/forget.py` and "forget me" delete them.
     - A stranger's are memory only.
   - **Journal:** each added or dropped hold goes in the diary as Pebble's own change ("I've started saying 'ooh, let me see'"), and "why do you say …?" answers from it.
   - **Later:** when the agency plan's `mine/` folder and feedback loop exist, the phrasebook moves there, and the loop's signals feed the same bandit.
