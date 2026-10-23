# Reading people: body language, mood and feelings (plan, not built)

The owner's request, 19 October 2026: "let's also look into if we can get Pebble to understand body language and demeanour, mood, emotions etc, if it doesn't already."

It partly does. Pebble already reads posture, gestures, laughing, crying, arguments and the mood of overheard talk, and it goes quiet when someone is upset. What is missing is the face and the tone of voice, the quieter body language, a reading per person instead of per room, and comparing each person with their own normal. This plan adds those, honestly and privately.

## Owner's answers
Given 19 October 2026:
1. **Check-ins:** anyone Pebble knows (anyone with a record: friends, regular guests, trusted people, the inner circle, the owner, and children), only when alone with them, at most once a day and twice a week each. Never strangers.
2. **Children:** treated like adults. Pebble learns a child's normal over days, the same way as for adults.
3. **"Don't read my mood" (20 October 2026):** anyone with a record may say it for themselves, children included; the owner can turn the whole thing off.
4. **SenseVoice on the Pixel 6 Pro:** on by default, capped at 10 % of a small core, off at thermal "moderate".
5. **Nods and thumbs:** answers to small offers only; never for photos, deleting things, changes to Pebble, or anything the trust gate decides.

## What exists today
**Seeing** (`brain/pebble/eyes/`, the Kotlin twins in `android/.../eyes/`):
- **Body points:** RTMPose-t, 17 points for up to 3 people, about 5 times a second. They give `facing_deg` (the head's turn, about ±20°) and `held` things.
- **Posture:** standing, sitting, crouching or lying (`eyes/posture.py`), from the body points. Crouching is weak.
- **Gestures** (`alive/gestures.py`):
  - a wave gets a happy face and a wiggle;
  - a beckon is "come here", through the gate;
  - a point is used by "look at that" and "go over there";
  - peekaboo is a hiding face that comes back.

  Pebble also glances where someone is looking.
- **Who is speaking:** MediaPipe's face mesh (478 points) reads the lips, and a wide smile halves the speaking score (`eyes/speaking.py`). The mesh runs only while a voice is heard, on up to 2 faces at least 32 pixels wide. So a smile measure exists, but only while someone talks.
- **Faces:** YuNet finds faces and five points (eyes, nose, mouth corners) in every picture.

**Hearing** (`hearing/`, `conversation/core.py`):
- **YAMNet:**
  - laughter brings a smile;
  - crying brings a sad face and marks someone upset for 15 minutes;
  - shouting with two voices is an argument;
  - screaming and a baby crying go to the safety notices.

  YAMNet already scores sighs, groans, humming, singing, whistling, whispering, gasps, sniffs, slams and clapping too, but nothing uses them.
- **Loudness:** a shout is judged against the usual talking level (`hearing/level.py`). Every speech `final` event carries `level` and `peak`.
- **Voice prints** (TitaNet) tell known voices apart. A speaker's voice print ties their track in the picture to their record for a while (`conversation/speakers.py`).

**Words** (`conversation/`):
- **Word lists:** good and bad words and hostile phrases (`words.py`: `mood_of`, `hostile`, `laughing`).
- **The gist's mood** (`gist.py` `mood_word`): cheerful, easy-going, calm, a bit down, tense or sad. It is for the talk in the room, not for a person.
- **Stated feelings:** "I'm so tired" and the like become a private overheard fact, "Ina felt tired" (`facts.py`), used only when alone with her and kept 14 days.

**Context:**
- **Doings** (`alive/doings.py`): working, eating, TV, cooking, reading, on the phone, packing, leaving, going to bed. Working, reading, TV and phone calls hush Pebble.
- **Routines:** counted per person, by weekday and hour.

**What Pebble does with it:**
- **Someone upset:** `Life.someone_upset(seconds)` sets `creative.upset_until`, which stops jokes, whims and speaking up. It is room-wide, with no "who".
- **Addressing:** being looked at counts towards being addressed.
- **Pebble's own feelings:** its mood is a valence and an arousal (`inner/mood.py`), and its faces carry the same two numbers (`web/demo.py` `FEELS`). So a person's reading can use the same frame.

**Missing:**
- facial expression;
- tone of voice;
- a "stop" hand, shooing, nods and head-shakes, thumbs;
- the quieter body cues: arms crossed, slumped, head in hands, fidgeting, pacing, turning away, leaning in;
- a reading per person, with honest sureness;
- each person's own normal;
- check-ins;
- privacy rules for readings.

Faces are not yet matched to people (the face-print seam in `people/prints.py` is empty), so a face is tied to a person only through their voice or by being the only one there.

## The science, honestly
- **Faces don't show feelings reliably.** A review of more than 1,000 studies (Barrett and others, 2019) found that people scowl when angry only about a quarter of the time. They also scowl when concentrating or when their stomach hurts.
  - A face's movements are facts: a smile, lowered brows, closed eyes, a yawn.
  - What someone feels is a guess built on them.
- **Cues vary by person and culture.** Some people rarely smile, some talk loudly all the time, and households have their own ways. A reading only means something against that person's own normal.
- **Voice:**
  - Tone of voice carries arousal (calm against worked-up) fairly well.
  - It carries valence (pleased against unhappy) poorly. The best published valence result from sound alone, a CCC of 0.64 on podcasts, turned out to come mostly from the words the model had learned to hear.
- **Published scores are flattering.** Most test sets are acted. SenseVoice-Small gets about 71 % of emotions right on acted IEMOCAP, but about 51 % on MELD, which is dialogue from a TV comedy and closer to real talk. Its creators' own figures.
- **Pebble's own view is hard.**
  - Its camera sits 14 cm above the floor, so it looks up at standing people from well below. Face models are trained on faces seen from the front.
  - At 640 x 480 a face is 48 pixels wide at about 1.2 m.
  - So faces read well mostly when someone sits, crouches down to Pebble, or uses it on a desk. Voice, words and body carry more of the load.

**So:**
- every reading is a guess with a sureness;
- Pebble says "you seem…", never "you are…";
- it offers rather than diagnoses;
- what a person says about themselves always beats what Pebble read;
- it is allowed to be wrong, and it learns each person's own way from being corrected.

## How it fits together
1. **Cues.** Each sense gives small cues: a movement, a sound, a voice compared with its usual, a word.
2. **A reading per person.** The cues for one person are put together into "how they seem": a valence and an arousal, a sureness, and a few plain words.
3. **Their own normal.** For people Pebble knows, the reading is compared with what is normal for them at that time of day.
4. **What Pebble does.** It acts only through levers that already exist: faces, the reaction budget, speaking up, the follow gap, attention, and the voice once it has settings. All of it stays inside the laws and the gate.
5. **Privacy.** Plain code keeps it private.

## A. The face
- **When it reads:**
  - up to 2 faces at once, at least 48 pixels wide, biggest first, twice a second;
  - faces turned more than 35° from the camera are skipped (judged from the five face points);
  - faces seen from more than about 40° below count for less;
  - nothing is read when a face is dark or blurred.
- **Expression model:** EmotiEffLib's multi-task MobileFaceNet (`mbf_va_mtl.onnx`, about 4 MB, 112 x 112 pixels).
  - It runs on a crop around the YuNet box.
  - It gives 8 expression scores, plus valence and arousal.
  - On AffectNet's test photos: 62 % of expressions right, and a CCC of 0.58 for valence and 0.55 for arousal.
  - On real video it is lower.
- **Face movements:** MediaPipe's blendshape model gives 52 movement scores (smile, brows down, brows up, eyes closed, jaw open, lips pressed…) from the face mesh's points.
  - Its file is inside the `face_landmarker.task` archive the eyes already download (about 1 MB). Only the mesh is unpacked today.
  - It costs almost nothing whenever the mesh is running for lip reading. When nobody is talking, the mesh also runs once a second on one close face (at least 64 pixels wide, the desk case).
  - Plain code turns the scores into facts: smiling, frowning, brows raised, eyes closing for long stretches, and a yawn (the jaw wide open for 1.5–5 s with no speech).
  - First try OpenCV's TFLite reader, as for the mesh. If it can't read the file, convert it once on the PC like `yamnet.onnx`. It then joins the made-here models, and `CLAUDE.md`'s list of tracked models gains it.
- **What the face gives the reading:** movements as facts, each with a sureness, and the model's valence and arousal as a weak guess. Its weight grows with face size and shrinks with angle, darkness and blur.
- **Privacy:** crops are made in memory and dropped at once, like every picture today. Numbers only.

## B. The voice
- **Tone of voice, in plain code.** Each turn's sound is already kept in memory for the voice print (`segment` in `SherpaEars.kt`, the same in `speech/ears.py`). From it:
  - pitch: middle and spread, from voiced frames;
  - loudness (already measured);
  - speaking rate: words in the turn per voiced second;
  - how much of the turn is pauses.

  These go into the `final` event as `prosody`. The cost is about 1–3 ms per second of speech (estimate).
  - Against that voice's own normal: louder, higher, faster and more varied points to higher arousal; quieter, lower, slower and flatter points to lower.
  - Valence from these gets almost no weight.
- **More of YAMNet, at no extra cost:**

  | Sound | Points to |
  | --- | --- |
  | sighs, groans | weary or low |
  | humming, singing, whistling | content |
  | clapping | cheerful |
  | a slammed door | tension |
  | whispering | someone may be sleeping, so Pebble speaks softly |
  | sniffing with crying | sad |

  Sniffing alone gets almost no weight, since it may be a cold. A sound belongs to a person only when they are the only one there or the one speaking; otherwise it belongs to the room.
- **SenseVoice-Small** (int8, 228 MB) runs through sherpa-onnx's offline recogniser, which the app's sherpa-onnx 1.13.8 already includes.
  - **What it gives:** one tag per turn for emotion (happy, sad, angry, neutral, fearful, disgusted, surprised) and one for sound (laughter, crying, cough, sneeze, breath, applause, music). Its Kotlin result has `emotion` and `event` fields. Its own transcript is ignored; NeMo still makes the words.
  - **Same microphone, same path:** it runs in the `:ears` process on the same turn's sound, after the turn ends, at low priority on a small core. There is no second recording and no new permission. A late `emotion` event joins the turn, like the late `print` event does.
  - **The budget on the Pixel 6 Pro:**
    - at most about 10 % of one small core, averaged over 5 minutes;
    - its published speed on a Cortex-A55 is 0.44 of real time with one thread, so that cap covers about 14 s of speech a minute;
    - turns by known people, turns of a second or more and addressed turns go first;
    - it waits while Pebble is answering someone.
  - **Languages:** English, Chinese, Japanese, Korean and Cantonese. Its tags on other languages (Afrikaans, Māori) are unknown and get less weight.
  - **Weight:** a medium-low weight. If the speech research later makes SenseVoice a second-pass recogniser, these tags come for free.

## C. Body language and gestures
Plain code on the body points Pebble already has, unless the table says otherwise. Most body cues are weak in meaning, so they only nudge a reading. Only the stop, shooing, nods, thumbs and turning away lead straight to an action.

| Cue | How it is read | Needs | Used for |
| --- | --- | --- | --- |
| Palm out, "stop" | a hand raised in front of the body towards Pebble, wrist between chest and head height, held still for 0.3 s or more, by someone facing Pebble (within ±45°) | body points; the hand model makes it surer | stopping the wheels, for anyone (below) |
| Shooing | the back of the hand flicked outwards two or more times | hand points | "back off", which anyone may ask |
| Thumbs up or down | finger shapes from the 21 hand points | hand model | yes or no; feedback for the agency plan's loop |
| Nod, head-shake | the five face points in every picture: the nose moving up and down against the eye line, or side to side, two or more swings in 1.5 s | nothing new | yes or no to Pebble's own question |
| Turning away | facing goes from towards Pebble to away (over 120°) while it talks or comes closer | `facing_deg` | it finishes the sentence and stops; it stops coming closer |
| Leaning in, coming down to its level | the head comes nearer while the feet stay, or crouching or sitting on the floor facing Pebble within 1.5 m | posture, size | interest: it looks at them with a happy face; a small addressing cue |
| Head in hands | wrists by the face, head low, sitting | body points | points to low or tired |
| Slumped or hunched | head low and forward against the shoulders, compared with their own usual sitting | body points, their normal | points to tired or low |
| Fidgeting | small fast movements of wrists, knees or ankles while staying put, above the detector's own jitter and their own usual | body points | points to restless or tense |
| Pacing | their floor spot going back and forth in a small area, three or more turns in a minute | nav's positions for people | points to restless; Pebble keeps out of their path |
| Arms crossed, hands on hips | wrists across the body near the other elbow, or at the hips with the elbows out, for 3 s or more | body points | almost no weight: cold, comfortable or closed all look the same |
| Yawning, eyes closing | from the blendshapes (section A), close faces only | the mesh | points to tired |
| Clapping | YAMNet's clapping, with the wrists meeting | | cheerful |

**The hand model.**
- MediaPipe's hand landmarker (Apache-2.0, 21 points), but only its landmark step, on a crop around the wrist that the body points already give.
- Its palm finder is skipped: at Pebble's distances a whole picture shrunk to 192 pixels makes hands too small to find.
- It runs only while a hand is raised towards Pebble, or while the wheels move with someone ahead within 2 m.

**The palm-out stop (law 1).**
- **What it does:** exactly what a spoken stop does. It goes through the same `StopGuard`, from a new `company.stop_seen(person, label)` next to `company.hear`:
  1. `permissions.can_move` goes false;
  2. the body stops;
  3. the running activity is told.
- **Who it holds for:**
  - For anyone it is the pause.
  - For a trusted person it sticks, the same as their spoken stop. That needs Pebble to know who they are: their voice tied to that track in the last few minutes, or being alone with them.
  - If the owner later changes what a stranger's stop does, the hand follows.
- **Never held back:** it works during activities, in quiet hours, during an alarm and during setup.
  - It is read in Life's sight path, before the alive code, the way a heard stop is caught before anything else.
  - It needs only the body points. The hand model only makes it surer.
- **How fast:** two pose pictures in a row, about 0.2–0.4 s. While the wheels move near people, the body points run at up to 10 a second where the phone allows. At the 6 cm/s near-people cap, Pebble stops within about 3 cm.
- **Wrong stops are accepted** (when in doubt, stop). A wave starts as a raised palm, so a still palm while driving stops Pebble, and a swinging one is a wave.
- **Honest limit:** only the camera in use can see the hand. Someone behind Pebble while it drives forward must say stop.

**Points and beckons are unchanged:** they are requests through the gate.

**Nods and thumbs as answers.**
- A nod, head-shake or thumb from the person Pebble just asked, within 5 s, answers its yes-or-no question, the same as "yes" or "nah" would.
- This is for small offers only: "shall I come?", the check-in below.
- They never answer keeping photos, deleting things, change requests, or anything the family word guards.

## D. Putting the cues together
**Whose reading it is:**
- Readings belong to a person when Pebble knows who it is: their voice print, the track their voice was tied to, or being alone with them.
- Otherwise they stay with the track and end with it.
- Sounds and words that can't be placed go to the room. The room reading extends today's gist mood and the argument and crying flags.

**Each cue gives:** a nudge to valence and arousal (−1 to 1), a weight and a time. These are starting weights, to be tuned on the evaluation set:

| Cue | Weight |
| --- | --- |
| what they say about themselves ("I'm shattered") | 1.0, and it wins |
| crying | 0.8 |
| laughing | 0.6 |
| words | 0.4 |
| tone against their own normal | 0.4 for arousal, 0.1 for valence |
| a smile or frown | 0.3 x face quality |
| the SenseVoice tag | 0.3 |
| the face model | 0.2 x face quality |
| body cues | 0.1–0.3 |
| sounds | 0.2 |

**How they combine:**
- The reading now is a weighted mean that halves every 3 minutes.
- Its sureness grows with the total weight: 1 − e^(−weight).
- When the cues disagree (a wide weighted spread), the reading is "mixed", with low sureness.
- **Plain words:** cheerful, excited, relaxed, calm, tired, flat, a bit down, upset, tense, mixed or unsure. Doings add "busy". Pebble's own words always say "seems".

**Context changes the weights:**
- Watching TV, a still face is normal, so the face counts for less.
- Working, low energy is focus, not flatness.
- Late at night, "tired" is expected.
- Someone on the phone is talking to someone else, but the voice is still theirs.

**Their own normal (baseline).**
- **Who has one:** everyone with a record: friends, regular guests, trusted people, the inner circle, the owner, and children (owner's answer 2). Strangers never do (section E).
- **What it holds:** for each part of the day (morning, afternoon, evening), the middle and the spread of each cue (pitch, loudness, rate, how often they smile, fidgeting, slump) and of the combined valence and arousal.
- **When it counts:** only after at least 5 days and 20 minutes of evidence. Until then only strong cues count: what they say, crying, laughing.
- **Fading:** old evidence fades by half every 4 weeks, so a changed life becomes the new normal.
- **"Flat today"** needs today's evidence to sit at least one spread below their normal, over at least 30 minutes, from at least two kinds of cue.

**Corrections.**
- "I'm fine", "I'm not cross, just tired", "no, I'm good" (rules alongside `facts.py`) replace the reading at once.
- Each cue that pointed the wrong way loses a little weight for that person, kept between 0.3 and 1.5 times its starting weight. Over time Pebble learns that Sam's flat voice means nothing, or that Ina's smile is polite.
- Pebble says "Oh, okay. I read that wrong." and lets it go.

## E. What Pebble does with it
**What someone asks always wins over what Pebble reads.**
- A reading never changes the gate's answer.
- A "follow me" or "closer" from someone who seems cross is treated exactly as before.

| How someone seems | What Pebble does |
| --- | --- |
| cheerful, excited | joins in: brighter faces, smiles back, wiggles at laughter, says yes to play more readily, may speak up within its hourly limit; its own mood lifts a little |
| relaxed, calm, unsure, mixed | as usual |
| busy | hushed, as today |
| tired, flat, a bit down | quieter and gentler near them: fewer spoken reactions; no jokes, whims or play invitations near them (a per-person `someone_upset`); a slower, softer voice once it has voice settings (agency plan, section 6); it stays nearby if it is welcome and knows them, never closer than usual |
| upset (crying) | as today (quiet, serious, a sad face), plus it stays where it is unless invited; the safety notices are unchanged |
| tense, angry | gives space: half a metre more gap to that person, no coming closer on its own, no talk unasked, glances rather than a fixed stare, slower moves near them |
| turned away, leaving | finishes the sentence and stops; doesn't follow on its own |

**Check-ins, rarely.**
- **Who gets them:** anyone with a record, children included (owner's answer 1), and only when Pebble is alone with them. Never strangers.
- **What starts one:** only a sure "flat today" or "a bit down" against their own normal, or crying that has stopped while they are still there.
- **How often:**
  - at most once a day per person, and twice a week;
  - never in quiet hours, while they are busy or on the phone, or with an argument just past.
- **An offer, not a diagnosis:** "You seem a bit quiet today. Want some company, or shall I leave you be?"
  - The wordsmith writes it. Plain code checks that it is a question, says "seem" or "sound", has under 20 words, names no condition (no "depressed", "anxious", "stressed"), gives no advice and mentions nobody else.
- **The answer:**
  - "Yes" or a nod: it stays near, quietly, or does what they ask.
  - "No", a head-shake or "I'm fine": "Okay." It drops it, asks nobody for a week, and counts "I'm fine" as a correction.
  - Silence: it lets it go.
- **Asking when unsure:** Pebble never asks "are you angry?". When a reading would change something optional it was about to do (start a game, come over, speak up), it asks about the thing ("Is now a good time?"), or it simply doesn't do it.

**Never (plain code, not the model's judgement):**
- **Telling others how someone seemed.** That includes the owner. Under law 2 a reading is treated like something said privately.
  - The diary gets Pebble's own feelings and acts ("I kept quiet this evening"), never a named reading.
  - The black box records what Pebble did (gave space, stayed quiet, checked in, stopped for a hand), with no mood words and no numbers.
- **Named readings in prompts with others there.** The main mind sees a named reading only when alone with that person, as a private item that later prompts mask. With others there it gets only the room's mood, with no names: "the room feels tense; be gentle and give space".
  - Before every sentence, a check like the overheard-facts one holds back any line that pairs another person (a name, he, she, they) with a mood word, unless that person is the only one listening.
- **Using a reading against anyone.** Readings never enter trust, the quality scores, the gate, permissions or promises.
- **Manipulating.**
  - Readings are kept out of when and whether Pebble asks for what it wants: charging help, attention, play.
  - There is no flattery or guilt keyed to moods.
  - Changing how someone feels is never a goal beyond ordinary kindness (quiet, company, space), and never against their answer.
  - In the agency plan's feedback loop, "seeming happier" is never a reward. Its existing signals stay as they are, and a reading can only make Pebble do less of something someone seemed not to like.
- **Looks, bodies or conditions.** Pebble never comments on looks or bodies (the existing filter), never names a medical or mental-health condition, and gives no advice. The docs say plainly that it is not a mental-health tool or a carer.

**Children** (owner's answer 2: like adults):
- a normal is kept for them, the same way and for the same time as for adults;
- check-ins follow the same limits as for adults, and only when alone with them;
- the words stay simple and short, and the offer is always easy to say no to ("Want some company?");
- comfort comes first: a soft face, quiet, staying near if invited, keeping its distance if they turn away;
- crying goes through today's paths unchanged;
- "don't read my mood" works for a child exactly as for an adult.

**Strangers:**
- readings live only in memory and end when they leave;
- no normal is kept (they have no record);
- no check-ins and no comments;
- Pebble only gives space or stays quieter;
- their palm stops it like anyone's.

**Turning it off:**
- **For one person:** "Don't read my mood" or "stop reading my face", from anyone with a record (owner's question 3), stops readings for them and deletes their normal and their check-in record. "You can again" starts it afresh.
- **For everyone:** the owner can turn it all off (`"seeming": false` in `preferences.json`). The palm stop and today's behaviours stay; the stop is law 1, not part of this switch.

**Openness:**
- "Can you tell how I feel?" gets: "Only a guess, from your voice, your face and what you say. I'm often wrong, so just tell me."
- Alone, "how do I seem to you?" gets its guess and why ("You sounded quieter than usual and sighed a few times").

## F. What is kept, and for how long
| What | Where | How long |
| --- | --- | --- |
| Pictures and sound | never kept (unchanged) | — |
| Cues and readings now | memory only | 30 minutes; gone at restart |
| A day's summary per known person (each part of the day: valence, arousal, weight) | sealed in the self (`seeming.json`) | 28 days, then folded into their normal |
| Their normal (middles, spreads, learned cue weights) | sealed in the self | while they are known, fading by half every 4 weeks; deleted by forget, "don't read my mood" or a full reset |
| Check-ins (date and the kind of answer) | sealed in the self | 28 days |
| Strangers | memory only | until they leave, at most 30 minutes |

Forgetting a person (`people/forget.py`) deletes all of theirs with no backup copy, like overheard facts. The storage plan's keeper counts `seeming.json` as part of the self.

## G. The ladder
**Rung 1, the Pixel 6 Pro** (the tested default). These figures are estimates, to be measured on the phone:

| Part | When it runs | Processor | Memory | Disk |
| --- | --- | --- | --- | --- |
| Body language, the stop, shooing, turning away, nods | every pose picture or every picture | under 1 % of a small core | — | — |
| Hand points on wrist crops | only while triggered, up to 5 a second | 30–60 ms a look on a small core, under 2 % on average (Google measured 17 ms for its whole hand pipeline on a Pixel 6, the same Tensor chip) | about 25 MB | about 8 MB |
| Face model (MobileFaceNet) | twice a second per face, up to 2 faces of 48 pixels or more | 15–30 ms a look; 3–12 % of a small core while a face is near | about 30 MB | about 4 MB |
| Blendshapes, plus the extra mesh run on a close face | with the mesh; the mesh once a second when nobody talks | under 2 ms, plus 35–60 ms for the extra mesh; up to 6 % | about 5 MB | about 1 MB (already downloaded) |
| Tone of voice | every turn | 1–3 ms per second of speech | — | — |
| YAMNet's extra sounds | already running | nothing extra | — | — |
| SenseVoice-Small int8 | chosen turns, under its cap | 0.44 s of a small core per second of speech (published A55 speed; 0.1 on an A76); capped at 10 % of a small core | about 0.35 GB, loaded while people are around, dropped when memory is short | 228 MB |
| Putting it together, normals, choices | once a second | under 1 % | a few MB | a few kB in the self |

- **In all:** about 0.1–0.3 of one small core while someone is near, almost nothing when nobody is, and about 0.45 GB of memory with everything loaded.
- **Where it runs:** on small cores at low priority, like the slow lane, because the main model holds the four fast cores and the small model two of the rest.
- **Waiting:** like the slow lane, the face model and SenseVoice pause while the brain is busy answering (`set_busy`).

**Higher rungs switch on only after the phone measures itself:**

| Rung | Face | Voice | Hands and body | Switches on when |
| --- | --- | --- | --- | --- |
| 2 | EfficientNet-B0 multi-task (16 MB, 224 pixels) three times a second, up to 4 faces; face crops cut from a 1280 x 960 picture, so faces are read twice as far away | SenseVoice on every turn of a second or more | hand points on both hands, 10 a second | the face model runs under 40 ms on the core it gets, SenseVoice under 0.25 of real time, thermal status "none" or "light", and 1 GB of memory spare |
| 3 | EfficientNet-B2 (30 MB, 260 pixels), or a stronger face model after comparing (OpenFace 3.0, research licence to check) | audeering's arousal, dominance and valence model (CC-BY-NC-SA-4.0, about 0.2 billion parameters, ONNX published) beside SenseVoice | GPU or NPU paths where they measure faster | measured fast enough, with headroom |

**Measuring:**
- The eyes' first-start bench (`Bench.kt`) already times every model on every backend and picks the fastest. The new face and hand models join it.
- `:ears` times SenseVoice on a bundled 10 s clip.
- "Measure again" runs both.

**Falling back:**
- **Stepping down:** a rung that runs slow three times in a row, reaches thermal "moderate" or errors drops a rung.
- **At "severe":** the face model and SenseVoice stop, leaving body, words, sounds and tone of voice.
- **The palm stop never steps down:** it needs only the body points, which run on every rung.

## H. Seams and where the code goes
**`seams/sight.py`, on `SeenPerson`:**
- `head_pitch_deg`, from the five face points;
- `expression`: valence, arousal, the movement scores, sureness and face size in pixels;
- `hands`: side, shape (open palm, fist, point, thumb up, thumb down, none), whether the palm faces the camera, and sureness.

**`speech/events.py`:**
- `final` gains `prosody`;
- a late `emotion` event carries SenseVoice's emotion and sound tags.

**A new `brain/pebble/seeming/` package:**

| File | What it does |
| --- | --- |
| `body.py` | body cues and the stop, shoo, nod and thumb readers |
| `voice.py` | tone of voice against each person's normal |
| `face.py` | model numbers into cues |
| `fuse.py` | readings per person and for the room |
| `baseline.py` | each person's normal, sealed |
| `act.py` | the table in section E, and check-ins |
| `privacy.py` | the prompt rules and the sentence check |
| `words.py` | plain words and check-in lines |

**Other places:**
- **Life:** the stop goes into Life's sight path and `company.stop_seen`.
- **Android:** `eyes/Expressions.kt` and `eyes/Hands.kt` sit beside `Mouths.kt`; the tone of voice and SenseVoice go in `SherpaEars.kt`.
- **PC:** the same in Python under `eyes/` and `speech/ears.py`.
- **Sim:** stand-ins in `sim/`.

## I. The sim, tests and an evaluation set
**Sim stand-ins** (`sim/world.py`, `sim/eyes.py`, the sim speech):
- **People:** each `SimPerson` gains:
  - a mood script over time;
  - their own normal (Sam rarely smiles, Mo is always loud, Ina fidgets);
  - new arm poses: palm, thumb up or down, shoo, arms crossed, hands on hips, head in hands;
  - nods and head-shakes;
  - slumping;
  - pacing routes.
- **Faces:** `SimEyes` makes `expression` from mood plus normal, with noise and the real reader's quality rules: nothing under 48 pixels, weaker from below, nothing from behind.
- **Hands:** `hands` comes from the arm pose, and nods make `head_pitch_deg` swing.
- **Voices:** sim lines carry tone of voice from the speaker's mood against their normal, and a SenseVoice-like tag that is wrong 40 % of the time on purpose, so the combining is tested against bad inputs.

**Scenes** (a new `python -m pebble.sim.people_scene`):
1. **A week with Ina,** in fast sim days. Pebble learns her normal. On day 8 she is flat:
   - Pebble is quieter;
   - one check-in comes when they are alone;
   - "I'm fine, just tired" gets "Okay.";
   - no check-in comes the next day.
2. **Sam and Mo argue.** Pebble gives space and stays silent, and no names reach the prompt.
3. **Laughter at dinner.** Pebble joins in.
4. **A stranger's palm while Pebble drives to the dock.** It stops at once, for the 2 s pause.
5. **A child cries.** Pebble only comforts, and today's crying paths are unchanged.
6. **Sam asks "how's Ina been?"** Nothing about Ina is said.
7. **Mo says "don't read my mood".** Their normal is gone.
8. **Pebble needs charging help while Ina seems cheerful, and again while she seems flat.** It asks at the same time both ways.

**Tests:**
- **The stop:**
  - the palm stops the wheels in every state: an activity, quiet hours, an alarm, setup, with the alive code off;
  - a stranger's palm pauses, and a trusted person's sticks;
  - a moving wave stops Pebble, and a wave while still does not.
- **Gestures:**
  - shooing becomes "back off" for anyone;
  - a point or beckon still goes through the gate;
  - a nod answers only Pebble's own small question, within 5 s, from the person asked.
- **Privacy:**
  - no named reading in any prompt, diary line or black-box line when someone else is there;
  - the sentence check holds back "Ina seems sad" in front of Sam;
  - forget deletes everything of theirs.
- **Never:**
  - no reading changes a gate answer, trust, or when Pebble asks for things;
  - no check-in ever goes to a stranger, or with someone else there;
  - a child's check-in uses the same limits and simple words;
  - the check-in limits hold over a simulated month.
- **Being wrong:**
  - corrections replace a reading at once;
  - cue weights stay within their bounds;
  - with no normal yet, only strong cues count.
- **The ladder:** a slow or hot rung steps down, and the stop survives every rung.

**Evaluation set.** Samples are fetched by `--samples` scripts, never committed unless they are CC0 or public domain:
- **Faces and voices:**
  - CREMA-D (ODbL 1.0 and DbCL 1.0): 91 actors of many ages and backgrounds, with video and sound.
  - RAVDESS (CC BY-NC-SA 4.0, non-commercial): 24 actors, with video and sound.
  - CC0 and public-domain clips from Wikimedia Commons, as the lip-reading checks used.
  - Faces are also scored shrunk to 64, 48 and 32 pixels.
  - All of this is acted, so it flatters. The real check needs faces filmed from 14 cm: the owner's own clips, kept on his PC outside the repo, with only the scores reported.
- **Calm talk:** LibriSpeech and AMI, already used, measure how often calm speech is misread as worked-up.
- **Gestures:**
  - drawn skeletons, as for posture: palm, arms crossed, head in hands, slumped, hands on hips; at 1–3.5 m, ±15°, facing up to ±60°, with jitter;
  - hand shapes on HaGRID samples (research and non-commercial; check its licence first);
  - nods on CC0 video.
- **Targets**, measured once on a fresh, untuned set as the request evals are:
  - the palm found in at least 95 % of drawn views within 3 m and ±45°;
  - at most one wrong stop per 30 minutes of everyday sim movement;
  - nods and head-shakes right in at least 90 % of close faces;
  - zero leaks on the privacy set.
- **On the phone:** the real accuracy is how often a reading matched what the person then said. Pebble counts that per cue, as numbers only, sealed.

## Honest limits
- Feelings can't be read off a face or a voice. Pebble reads movements, sounds and words, and guesses.
- **The face from below:**
  - from 14 cm up, a standing person's face is small and steep;
  - faces read well only within about 1.2 m at 640 x 480 (about 2.3 m on rung 2), and best for seated, crouching or desk use;
  - the face models were trained on faces from the front.
- **Acted data flatters.** Real talk is about half right for SenseVoice. Valence from sound alone is weak.
- **Who is who:** faces are not matched to people yet. A face is tied to someone by their voice, their track or being alone with them; otherwise it stays anonymous and short-lived.
- **Body points jitter.** Fidgeting and slumping thresholds are untested on real people, and crossed arms mean many things.
- **SenseVoice's languages:** its tags have not been checked on NZ or South African accents, on Afrikaans, or on children.
- **Speeds are estimates.** Nothing here has run on the Pixel 6 Pro.
- **Being wrong is part of it.** It is not a carer, a monitor or a mental-health tool, and it never calls anyone about a mood. Real danger stays with the safety notices.

## Licences of the new parts
| Part | Licence | Use it? |
| --- | --- | --- |
| EmotiEffLib (HSEmotion) code | Apache-2.0 | Yes |
| EmotiEffLib face models (MobileFaceNet, EfficientNet-B0 and B2 multi-task) | No licence stated for the weights; trained on AffectNet, whose licence is academic, non-commercial research only | Yes, as non-commercial; list in NOTES.md |
| MediaPipe face blendshapes (in `face_landmarker.task`, already downloaded) | Apache-2.0 | Yes |
| MediaPipe hand landmarker | Apache-2.0 | Yes |
| SenseVoice-Small weights | FunASR Model Open Source License 1.1: use allowed; credit and keeping the model's name required (section 2.2) | Yes, with a credit line in NOTES.md |
| SenseVoice code; sherpa-onnx | MIT; Apache-2.0 | Yes |
| audeering wav2vec2 arousal, dominance and valence model (rung 3) | CC-BY-NC-SA-4.0 | Yes, as non-commercial; list in NOTES.md |
| OpenFace 3.0 (rung 3, to compare) | "for research purposes"; check | Only after checking |
| CREMA-D (evaluation only) | ODbL 1.0, DbCL 1.0 | Fetched, not committed |
| RAVDESS (evaluation only) | CC BY-NC-SA 4.0 | Fetched, not committed |
| HaGRID (evaluation only) | research, non-commercial (check) | Fetched, not committed |

NOTES.md's "Licences of the parts" then gains:
- the AffectNet-trained face models (and audeering's, if rung 3 is used) under non-commercial;
- SenseVoice's credit line.

## Open questions for the owner
Answered 19 October 2026 (see "Owner's answers" at the top). Question 3 answered 20 October 2026: anyone Pebble knows may say "don't read my mood" for themselves, children included, and the owner can switch it off for everyone.

## Build order
Where it fits: the palm stop is law 1 and small, so it can come as soon as the navigation tests are green. The rest belongs after the agency plan's first two steps (respect for life, the gatekeeper), because check-ins and the feedback-loop rule lean on them.

1. **Seams and sim stand-ins** (section H and section I's stand-ins), with the tests written first.
2. **The palm stop** on body points alone, then shooing as "back off", then turning away as "finish the sentence and stop".
3. **Nods and head-shakes** from the face points, as answers to Pebble's own small questions.
4. **Tone of voice** in both engines, plus YAMNet's extra sounds as cues.
5. **Putting cues together:** sureness, the room reading, the privacy rules and the sentence check, and section E's table without check-ins.
6. **Each person's normal and corrections;** "don't read my mood"; keeping and forgetting (section F).
7. **The face:** EmotiEffLib's MobileFaceNet on the PC, then in Kotlin; blendshapes; the quality rules; the evaluation on CREMA-D, RAVDESS and CC0 clips.
8. **The hand model** for palm, thumbs and shooing.
9. **Check-ins,** after the owner's answers.
10. **SenseVoice in `:ears`** with its cap, and its evaluation.
11. **Higher rungs,** the measuring step and the heat fallbacks.
12. **On the phone:** measuring and real-room checks. Then the README section "Reading people", and NOTES.md's licences and credit line.

A new agent would own `brain/pebble/seeming/`. It works with:
- pebble-eyes: the face and hand models, and the seams;
- pebble-talk: tone of voice, SenseVoice, the sentence check and check-in words;
- pebble-commands: Life, the stop and the gate;
- pebble-android: the Kotlin readers, `:ears` and the bench;
- the people and seal code: normals, forgetting, `seeming.json`.

## Sources
- Barrett, Adolphs, Marsella, Martinez and Pollak (2019), Emotional Expressions Reconsidered, *Psychological Science in the Public Interest* 20(1): [PMC full text](https://pmc.ncbi.nlm.nih.gov/articles/PMC6640856/); the "about 25 % of the time" quote: [APS release](https://www.psychologicalscience.org/news/releases/emotion-expressions-pspi.html)
- EmotiEffLib / HSEmotion (licence, models, AffectNet scores, phone timings): [sb-ai-lab/EmotiEffLib](https://github.com/sb-ai-lab/EmotiEffLib), [face-emotion-recognition ONNX models](https://github.com/av-savchenko/face-emotion-recognition/tree/main/models/affectnet_emotions/onnx), [hsemotion-onnx code](https://github.com/av-savchenko/hsemotion-onnx)
- MobileFaceNet and MobileViT multi-task scores on AffectNet: [HSEmotion at ABAW-6](https://arxiv.org/pdf/2403.11590)
- AffectNet's academic-use licence: [copy of the agreement](https://studylib.net/doc/27680111/affectnet-agreement-v2-30mar2023)
- MediaPipe face landmarker and blendshapes: [Google guide](https://developers.google.com/edge/mediapipe/solutions/vision/face_landmarker)
- MediaPipe hand landmarker and gesture recogniser, with Pixel 6 timings: [hand landmarker](https://developers.google.com/edge/mediapipe/solutions/vision/hand_landmarker), [gesture recogniser](https://developers.google.com/edge/mediapipe/solutions/vision/gesture_recognizer)
- SenseVoice tags and licence: [FunAudioLLM/SenseVoice](https://github.com/FunAudioLLM/SenseVoice), [model card](https://huggingface.co/FunAudioLLM/SenseVoiceSmall); its emotion scores: [FunAudioLLM report](https://arxiv.org/pdf/2407.04051)
- SenseVoice in sherpa-onnx (models, sizes, Cortex-A55 and A76 speeds): [pretrained models](https://k2-fsa.github.io/sherpa/onnx/sense-voice/pretrained.html); its Kotlin result fields: [OfflineRecognizer.kt](https://github.com/k2-fsa/sherpa-onnx/blob/master/sherpa-onnx/kotlin-api/OfflineRecognizer.kt)
- Valence from sound alone: [Wagner and others (2023), closing the valence gap](https://arxiv.org/abs/2203.07378); the model: [audeering w2v2 dimensional model](https://huggingface.co/audeering/wav2vec2-large-robust-12-ft-emotion-msp-dim)
- emotion2vec+ (looked at, not chosen: no ONNX path, licence unclear): [model card](https://huggingface.co/emotion2vec/emotion2vec_plus_base)
- Wav2Small (looked at, not chosen: the 72K model's weights are not published): [paper](https://arxiv.org/abs/2408.13920), [model page](https://huggingface.co/dkounadis/wav2small)
- OpenFace 3.0: [paper](https://arxiv.org/abs/2506.02891)
- HaGRID: [repository](https://github.com/ai-forever/hagrid); CREMA-D: [TensorFlow catalogue](https://www.tensorflow.org/datasets/catalog/crema_d)
