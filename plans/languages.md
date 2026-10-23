# Languages: Afrikaans, mixed sentences, and learning new ones (plan, not built)

The owner's questions, 19 October 2026:
- "Can it understand more than one language, could it understand Afrikaans for example?"
- Later the same evening: "Can Pebble also learn new languages by itself?"

The owner is South African and lives in New Zealand. In South African homes people often mix English and Afrikaans in one sentence: "Pebble, kom hier asseblief", "stop it, Pebble, los dit". So here a mixed sentence is the normal case, not an odd one. Afrikaans is the worked example; section 12 gives the method for any language.

Nothing here has run on the phone. Every speed, size and score marked "est." is an estimate until the Pixel 6 Pro measures it.

## Owner's answers
**20 October 2026, the three that were open:** household speech is never kept to tune the ears; request lines said to Pebble may be kept sealed for 30 days to learn from; on a stronger phone, overheard Afrikaans is turned into words under English's rules. The Afrikaans wording is checked by the owner later, before anything ships in Afrikaans. Fluister is skipped; the ears are built from public data. The NVIDIA credit line goes in at publishing time.

The owner asked for the recommended answers (19 October 2026). The ones that would loosen a privacy rule stay open at the end ("Open questions for the owner"); until he decides, the stricter rule holds.

1. **Which language first:** Afrikaans, as a full pack (section 12), with mixed Afrikaans and English treated as normal speech. Any other language is its own later decision.
2. **Which language Pebble answers in:** the one it was spoken to in. A mixed line gets the language most of its words were in. A person's record may say otherwise: a parent may ask Pebble to speak Afrikaans to the children, for example.
3. **Mixing:** Pebble may mix the way the household does, one language per sentence, so each sentence goes to a voice that can say it.
4. **"Wag!" and a bare "wait!":** said alone, twice, or with its name while the wheels are moving, each pauses the wheels exactly like "stop". "Wag hier" and "wait here" stay wait requests. This adds stopping; it loosens nothing.
5. **A stop it isn't sure of** counts as a stop (law 1: when in doubt, stop).
6. **Stop and help words never switch off.** Once a language is on, its stop and help words stay on, even if the rest of that language is switched off or its ears are resting.
7. **Who switches a language on or off:** the owner or a trusted person. Pebble offers when it notices a language (section 11); it never switches on more listening by itself.
8. **Overheard Afrikaans on the Pixel 6 Pro:** words only for turns said to Pebble. While the wheels move, every turn is also checked for stop words, and those words are dropped at once. No gist and no overheard facts from Afrikaans talk on this phone.
9. **The voice for now:** Android's own offline Afrikaans voice if the phone has one, otherwise Meta's MMS Afrikaans voice, until Pebble's own Afrikaans voice exists. Its own Afrikaans voice is a voice space built once on the PC from public data; on the phone Pebble moves inside it to sound like itself in English, inside the voice fence (section 8).
10. **Safety lines:** said in the listener's language first, then in English. The flashing screen word shows both. The "not a smoke alarm" notice is in every language Pebble speaks and is said at setup.
11. **Strangers:** language changes nothing about trust or the gate. A stranger's Afrikaans "stop" gets the same short pause as an English one.
12. **Noticing languages:** room-level counts per language per day, kept 30 days, with no words and no sound. A person's languages are kept only in the records of people who talk to Pebble, and forgetting them deletes it.
13. **Taught words:** anyone with a record except strangers may teach Pebble words. A taught word can only make Pebble stop more, help more or keep more private, never less. Words that let it move again come only from trusted people and work only for trusted people.
14. **Its name:** "Pebbletjie" and the other forms people use count as its name.
15. **When:** right after the household pack (see "Build order").

## The short answer
- **Yes, Afrikaans is realistic on the Pixel 6 Pro**, for people talking *to* Pebble, in Afrikaans or mixed with English, and for Pebble answering in Afrikaans. It won't be as good as its English, and it will be slower.
- **How:** today's English ears stay as they are. A second, Afrikaans pair of ears (a small Afrikaans Whisper, tuned to read short lines quickly) reads each turn said to Pebble once the turn ends. Gemma 4 E4B already reads and writes Afrikaans. The voice is a separate small Afrikaans voice.
- **How well (est.):** short household requests should mostly work, because the rules only need a few key words. Free talk will have errors. No small Afrikaans speech model publishes scores worth trusting, and on the only real mixed Afrikaans-English test found (AfriSwitch, 0.68 h), the best large systems still got about a quarter of the words wrong.
- **What it costs (est.):** about 0.5 GB more memory while an Afrikaans speaker is around, about 0.6 GB of disk, and 1.5 to 2 s of two big cores per Afrikaans turn said to Pebble. Replies in Afrikaans start about 1.5 to 2 s later than in English.
- **What it can't do on this phone:** turn overheard Afrikaans talk into words (so no Afrikaans gist or facts), think early on Afrikaans words as they arrive, or speak Afrikaans in Pebble's own voice until that voice is built.
- **Stopping in every language:** "stop" is the same word in Afrikaans, and the raised palm (`plans/reading-people.md`) needs no language at all. The Afrikaans-only stop words ("wag", "hou op", "staan stil") go through the same stop code, but arrive about 1.5 to 2 s later until a fast detector for them is trained and measured.
- **Learning by itself:** partly (section 11). It can notice a language, switch on a pack it carries (after a yes), learn words people teach it, and tune its ears to the household's words. It can't learn a whole new language by listening: that needs recordings it doesn't keep and training a phone can't do.

## What exists today
- **Ears** (`speech/`, `android/.../brain/SherpaEars.kt`): the NeMo FastConformer streaming model is English only. The name spotter spells its keywords in English word pieces and was trained on GigaSpeech (English podcasts and audiobooks). Voice detection (Silero), voice prints (TitaNet), YAMNet and the beep detectors don't depend on language. Android's own recogniser, the fallback when the speech models crash, asks for `Locale.getDefault()`.
- **Rules** (`understand/`): English, with NZ and South African words already in: "voetsek", "ja", "nee", "lekker", "boet", "bru", "ag", "kyk daar", "kyk hier", "Ouma", "Oupa", "aikona", "yebo", "hamba", and "just now" and "now now" read as later.
- **Small model:** LFM2.5-230M. LFM2.5 is listed for nine languages (English, Arabic, Chinese, French, German, Japanese, Korean, Portuguese, Spanish); Afrikaans isn't one of them.
- **Main model:** Gemma 4 E4B, pre-trained on 140+ languages and supported "out of the box" for 35+. Its prompts here are English, and it has never been asked to read or write Afrikaans.
- **Plain-code word checks, all English:**
  - stop and go (`people/stops.py`);
  - help, fire, "it's fine" and quiet (`safety/words.py`);
  - "stop listening" and "start listening" (`conversation/listening.py`);
  - "between us" (`people/company.py`, `SECRET`);
  - addressing cues, hostility and the gist (`conversation/words.py`);
  - overheard-fact templates (`conversation/facts.py`).
- **Pebble's lines:** fixed English sentences across `activities/`, `safety/` and `conversation/` (a quick search found about 170, plus more built from parts).
- **Voice:** `Speech.kt` and `Alarm.kt` set `Locale.getDefault()` (falling back to US English) and pick the best voice of that language that needs no network. The voice seam `Voice.say(text, whisper)` (`seams/voice.py`) takes no language.
- **No language anywhere in the data:** not on speech events, `Heard`, the person record or the voice call.

### A first look (19 October 2026, on the PC)
Seven single Afrikaans words, recorded by two people for Lingua Libre (Wikimedia Commons, CC BY-SA 4.0), were run through Pebble's own NeMo files with the same level step the engine uses. Clean single words are not real talk, so this only shows the shape of the problem. Nothing in the repo was changed.

| Said | Meaning | The English ears wrote |
| --- | --- | --- |
| kom hier (two clips joined) | come here | "come here" |
| kom | come | "come" |
| hier | here | "ere" |
| kyk | look | "cake" |
| nee | no | "near" |
| help | help | "help" |
| wag | wait | nothing |
| brand | fire | nothing |

- Words that sound like English get through. The rest are lost or become other words: "wag" and "brand" vanished, and "nee" became "near", so a "no" to Pebble's question would be missed.
- The name spotter, given English spellings ("wag", "vach", "fach", "brand", "help" and others), found none of the intended words. It took "nee" for "near".
- Today's rules, given the Afrikaans *text* (as if the ears could write it):
  - only lines with the English words "stop" or "help" did anything;
  - "Pebble, follow my asseblief" was read, sure, as chat (Afrikaans "my" means "me"), so no model was even asked;
  - "come here netnou" was read as "come here now", but "netnou" means later.

## 1. The rules for all of it
- **One Pebble.** The same laws, gate, trust tiers and privacy rules in every language. Language never changes who may ask what.
- **Safety words first.** A language counts as "on" only when its stop, help and privacy words work through the same plain code as English, with tests.
- **When in doubt, stop.** A possible stop in any language is a stop.
- **Offline, as always.** Everything runs on the phone. What is built on the PC is built once, from public data, like the made-here models. Nothing Pebble learns at home is trained on a laptop (`plans/workbench.md`, `plans/more-freedom.md` answer 12).
- **Honest.** Pebble says when it can't understand a language, or isn't sure.

## 2. Ears for two languages
### Why not one model
- No streaming Afrikaans speech model was found:
  - none in sherpa-onnx;
  - Moonshine covers English, Spanish, Mandarin, Japanese, Korean, Vietnamese, Ukrainian and Arabic;
  - NVIDIA's multilingual Canary and Parakeet models cover 25 European languages;
  - Vosk has no Afrikaans model;
  - Lelapa AI's Afrikaans model is a paid cloud service.
- The models that do know Afrikaans (Whisper and its fine-tunes, Meta's MMS and Omnilingual ASR) read a whole stretch of speech at once.
- So Pebble keeps its fast English ears for what they do well (its name, "stop", barge-in, words as they arrive) and adds a second pair that reads a finished turn.

### The choices
Word error rate (WER) is the share of words wrong; character error rate (CER) is the share of letters wrong. FLEURS is read sentences; NCHLT is read prompts from about 200 South African speakers.

| Ears | Licence | Afrikaans scores found | Size | A 2.5 s line on the Pixel 6 Pro (est.) | Verdict |
| --- | --- | --- | --- | --- | --- |
| Stock Whisper tiny / base / small / medium | Whisper's (MIT on GitHub, Apache-2.0 on Hugging Face) | FLEURS WER 91 % / 82 % / 61 % / 45 % (OpenAI's paper) | 0.04–0.8 GB | — | No: too many errors without an Afrikaans fine-tune |
| **Fluister small** (DigiPhyte, South Africa): Whisper small fine-tuned on Afrikaans and South African English, keeps English mixed in | MIT; trained on CC-BY-4.0 data | none published | about 0.25 GB; published only as a CTranslate2 file | 13–18 s with Whisper's fixed 30 s window; 1.5–2 s with a trimmed window, which needs ACFT (below) | **The model to build on** |
| Fluister turbo (Whisper large-v3 turbo fine-tune, 0.8B) | MIT; trained on CC-BY-4.0 and CC-BY-3.0 data | NCHLT WER 8.6 % (English 1.7 %), read speech | about 0.8 GB | 8–10 s, even with a trimmed window | The teacher on the PC; stronger phones |
| BuzzASR Afrikaans (Whisper large-v3 fine-tune) | MIT | FLEURS WER 22.4 %, CER 7.7 % (stock large-v3: CER 11.7 %) | about 3 GB | far too slow | A yardstick only |
| Omnilingual ASR CTC 300M (Meta), already in sherpa-onnx | Apache-2.0 | its 7B sibling: CER 4.7 % on Afrikaans; the 300M averages about twice the 7B's errors on FLEURS | 365 MB (int8) | 4.5–6 s | Listen-only packs (section 12); stronger phones |
| MMS-1B-all (Meta) | CC-BY-NC-4.0 | none published for Afrikaans | about 1 GB | too slow | No: Omnilingual replaces it |
| Gemma 4 E4B hearing the sound itself (25 tokens a second of sound, up to 30 s) | Apache-2.0 | multilingual speech recognition claimed; languages not listed | about 0.9 GB more (the E2B sound file's size) | unknown; llama.cpp calls its audio "highly experimental" | Try later, on a stronger phone first |

How the times were estimated: each model's work per second of sound, scaled from today's English model, which the README puts at about 0.4 of one big core. Today's model does about 3 billion sums per second of sound; Whisper small's encoder about 9 billion, plus the words it writes; Omnilingual 300M about 35 billion; Whisper's full 30 s window about 270 billion whatever the length of the speech.

### ACFT: making Whisper quick on short lines
- Whisper always reads a 30 s window, padding short speech with silence, so a 2 s "kom hier" costs as much as 30 s of talk.
- whisper.cpp (MIT; a sibling of the llama.cpp Pebble already builds with the NDK) can read a shorter window (`audio_ctx`), but stock Whisper then tends to loop or drop words.
- FUTO's audio-context fine-tuning (ACFT) teaches Whisper to work with short windows. Its tiny, base and small checkpoints are Apache-2.0, the method is public, and it has already been applied to a Basque fine-tune of Whisper small.
- **So the Afrikaans ears are made once, on the PC, from public data only:**
  - Whisper small fine-tuned for Afrikaans and South African English, then ACFT-tuned (or starting from FUTO's ACFT small);
  - data: NCHLT Afrikaans and English (CC BY 3.0, about 56 h each), the afrikaans-30s church recordings (CC-BY-4.0, about 56 h of unscripted speech), FLEURS (CC-BY-4.0) and Common Voice Afrikaans (CC0);
  - Fluister turbo can act as the teacher, labelling more Afrikaans speech;
  - Fluister small's own weights would save the first step, but they are only published as a CTranslate2 file: ask DigiPhyte for the Transformers weights (they publish them for turbo).
- It needs a GPU for some hours (est.), rented if need be. That is development, not Pebble at run time.
- **Result (est.):** about 0.3 GB, reading a 2.5 s line in 1.5 to 2 s on two big cores. An ACFT base model is the lower rung, at about 0.4 to 0.6 s.

### When the second ears run
Only when they matter, to keep the cost down:
- **A turn said to Pebble** (addressed or maybe) by someone whose record says they use Afrikaans, or by anyone when the English reading looks unsure (few known words, low scores from the English model).
- **Every turn while the wheels move**, to look for stop words. This uses the smaller rung, because a stop check needs only a few words, and the words are dropped straight away.
- **Never** for overheard talk while Pebble is still (answer 8).

### Keeping it quick
- Start reading at the first 0.25 s pause, the way English replies already think early, and throw the reading away if the person carries on.
- The English ears' words for Afrikaans speech are noise, so thinking early on them is off for turns that go to the second ears.
- Load the second ears only while someone who uses Afrikaans is around, and drop them first when memory is short (as the reading-people plan does with SenseVoice).

## 3. Which language was that?
- Spoken language ID is weak on short clips between Afrikaans and South African English: in a study on South African languages, Afrikaans and English formed one overlapping cluster. So Pebble doesn't let a language-ID model make this choice.
- Instead, for each turn, plain code weighs:
  - who spoke: the languages in their record, and what they used in the last minute;
  - both readings: how sure each model was, and how many of each reading's words it knows;
  - Afrikaans-only words in the Afrikaans reading ("nie", "jy", "ek", "wat", "het", "jou", "asseblief", "hierso" and so on).
- A turn can be **mixed**. The rules then read it as one line, with both word tables on.
- The choice goes on the turn as `lang`: "en", "af" or "mixed".
- **When it can't tell,** Pebble asks briefly, in the language it thinks was used: "Ek is nie seker nie. Sê dit weer?"

## 4. Its name
- **Said by an Afrikaans speaker:** Afrikaans p, t and k have no puff of air after them, so "Pebble" can sound more like "Bebble" to a model trained on English. The l is dark, as in English.
- **Inside Afrikaans speech:** "Pebble, kom hier" puts the name first, before a pause, which is where the spotter is strongest.
- Today's spotter already misses 6 of 30 synthetic "Pebble"s (all from the slowest male voice). Afrikaans voices are untested.
- **What to do:**
  - measure "Pebble" said by the household (recordings kept on the owner's PC, outside the repo, with only the scores reported) and by synthetic Afrikaans voices;
  - add the forms people use as extra spotter lines under the same name: "Pebbletjie" (said like "pebble-key"), and "Bebble" if measuring shows it catches more than it fires falsely on the 30 minutes of meetings;
  - train the "Pebble" model planned in the model-upgrades report (livekit-wakeword, row 13) with Afrikaans-accented synthetic voices in the mix;
  - teach the rules and the address code the same forms (today `normalise` removes only "pebble").

## 5. Understanding requests in Afrikaans and mixed sentences
### How
- **Rules first, as for English.** One request reader with both word tables switched on, because people mix inside a sentence ("follow my asseblief", "go to the kombuis"). The Afrikaans grammar rules switch on with the language.
- **The small model:** LFM2.5 has no Afrikaans. Afrikaans lines the rules can't place skip it and go to the main model, unless a measured small model reads them well. Candidates for that test: Gemma 3 270M (trained on 140+ languages; Gemma terms) and Qwen3.5-0.8B (Apache-2.0; Qwen3 lists Afrikaans).
- **The main model:** the same prompt and grammar, plus a few Afrikaans and mixed examples kept in the fixed part of the prompt, so the warm prompt cache survives a change of language.
- The main model is slow on this phone, so the rules must cover the everyday Afrikaans requests, as they do for English.

### The words
| Kind | Afrikaans | Mixed, the way people say it |
| --- | --- | --- |
| follow | "volg my", "kom saam", "loop saam met my", "kom agter my aan" | "follow my asseblief" |
| come | "kom hier", "kom hierso", "kom nader", "kom na my toe", "kom gou", "kom sê hallo vir Ouma" | "Pebble, kom hier asseblief", "come here, toe" |
| wait | "wag hier", "bly hier", "bly daar", "wag vir my", "wag tot ek terug is", "moenie weggaan nie" | "wait hier vir my" |
| look | "kyk na my", "kyk hier", "kyk na Ina", "kyk na die bal", "kyk daar" (with a point) | "kyk hier, look at me" |
| back off | "gaan weg", "staan terug", "skuif terug", "gee my plek", "los my uit", "voetsek" | "back off, man" |
| go home | "gaan slaap", "gaan bed toe", "slaaptyd", "gaan laai", "gaan terug na jou laaier" | "go to bed nou" |
| go to a place | "gaan kombuis toe", "gaan na die sitkamer", "ry stoep toe" | "go to the kombuis" |
| go to a thing | "gaan na die stoel", "ry na die venster", "gaan sê hallo vir die hond" | |
| find a thing | "soek die kat", "soek my bril", "kan jy my sloffie kry?" | "find my sleutels" |
| where is it | "waar is my pantoffel?", "het jy die bal gesien?", "waar het ek my beursie gelos?" | "waar's die remote?" |
| what's that, what can you see | "wat is dit?", "wat is daai?", "wat sien jy?" | |
| turn, small moves | "draai om", "draai links", "draai regs", "'n bietjie links", "ry 'n bietjie vorentoe", "gaan 'n bietjie agteruit" | "turn regs" |
| stop the activity | "hou op om my te volg", "jy kan nou ophou", "genoeg nou", "los dit" | "stop it, Pebble, los dit" |
| change it while it runs | "stadiger", "nie so vinnig nie", "vinniger", "hou by", "nader", "nie so naby nie", "'n bietjie verder", "dis ver genoeg", "mooi, bly daar", "ander kant toe", "hou aan" | "slower, man", "not so naby" |
| carry on | "gaan maar aan", "jy kan maar gaan", "dis al, dankie" | |
| teach | "dis my beker", "dis Sam se koppie", "dis joune", "hy heet Bob" | "dis my mug" |
| play | "kom ons speel", "wil jy speel?", "jaag die bal" | |
| where are you | "waar is jy?", "in watter kamer is jy?" | |
| answers to its questions | "ja", "nee", "nee wat", "reg so", "seker" | |

### Traps
- **"my" means "me" after a verb** ("volg my", "kyk na my") and "my" before a noun ("my pantoffel").
- **The double negative:** "moenie my volg nie", "ek wil nie hê jy moet my volg nie". A negation sits at both ends of the line.
- **Pronouns:** "sy" is she, "hy" he, "hulle" they, "haar" her, "hom" him.
- **Later words:** "netnou" (in a while, the Afrikaans "just now"), "nou-nou" (soon), "later", "môre" (tomorrow), "vanaand" (tonight), "eendag" (one day). "Nou" alone means now.
- **"Bly stil" means keep quiet** (a shush), not keep still; "staan stil" is a stop.
- **"Kom nou"** is "come on!" (fed up) as often as "come now": Pebble asks, "Moet ek na jou toe kom?"
- **"Toe maar"** means "go on then" or "never mind", read by what was asked.
- **"Ja-nee"** is a shrug ("well, yes"), not a clear yes: ask again.
- **Titles:** "Tannie" and "Oom" are polite words for any older woman or man, not only aunts and uncles. "Ma", "Pa", "Ouma", "Oupa", "Boet" and "Sus" are family words.
- **Small forms:** "-tjie" and "-ie" make things little or dear: "balletjie" is a ball, "katjie" a cat, "hondjie" a dog, "Pebbletjie" Pebble.
- **Joined words:** Afrikaans writes compounds as one word ("rookalarm", "afstandbeheer"), so the thing names list them whole.
- **"Toe" after a place** means "to": "kombuis toe".
- **Spelling:** "sê", "môre", "'n". Normalising keeps the accents, but the ears may drop them, so the tables accept both.

### Not requests (must not move it)
- "moenie my volg nie" (don't follow me)
- "kan jy my sien?" (can you see me?)
- "volg jy my?" (are you following me?)
- "Sam volg my heeldag rond" (Sam follows me around all day)
- "ek wag vir die bus" (I'm waiting for the bus)
- "wag, wat?" (wait, what?)
- "kyk, ek is besig" (look, I'm busy)
- "ag, kom nou" (oh, come on)
- "Sam, kom hier" (said to someone else)
- "kom netnou", "kom later" (later)

### Measuring
- New sets, written for this like the English ones: an Afrikaans set (about 150 lines), a mixed set (about 100), a not-a-command set (about 80), and a holdout written afterwards by someone else (the owner), scored once before any tuning.
- The same bar as English: every core line right, at least 95 % right on the main sets, and no command fired on any not-a-command line.
- The owner checks the Afrikaans, including regional words (Kaaps, Namibian Afrikaans) and family words.

## 6. Stop, help and the other words that keep people safe
| What | Afrikaans words (the same handling as English) |
| --- | --- |
| stop (a pause, or sticky from trusted people, as today) | "stop", "stop dit", "hou op", "staan stil", "moenie beweeg nie", "bly staan", "halt", and "wag" alone, twice or with the name ("wag!", "wag wag", "Pebble, wag!") |
| moving again (trusted people only, as today) | "gaan maar aan", "hou aan", "ry maar", "jy kan maar beweeg", "jy kan nou weer ry" |
| a call for help | "help", "help my", "help asseblief", "ek het geval", "ek het neergeval", "ek kan nie opstaan nie", "ek is seer", "ek het my seergemaak", "ek bloei", "ek kan nie asemhaal nie", "bel 'n ambulans" |
| fire | "brand!", "daar's 'n brand", "almal uit!" |
| it's fine (during an alarm) | "dis reg", "alles is reg", "dis okay", "dit was net die toast", "dit was net die roosterbrood", "vals alarm", "ek is okay", "ons is okay", "moenie worry nie", "dis net 'n toets", "sit dit af" |
| quiet | "bly stil", "stilte", "sjuut", "sjt" |
| stop or start listening | "hou op luister", "moenie luister nie", "sit jou ore af"; "luister weer", "jy kan maar luister", "sit jou ore aan" |
| private | "tussen ons", "dis 'n geheim", "moenie vir iemand sê nie", "net vir jou" |
| forget me | "vergeet my", "vergeet van my" |

- **The same code.** `people/stops.py`, `safety/words.py`, `conversation/listening.py` and `people/company.py` get word tables per language. Every reading from every pair of ears goes through `Company.hear` as today, so the stop guard, the sticky stop, the stranger's pause and the release rules don't change.
- **All languages at once.** Each check uses the words of every language that is on, whatever language the turn was judged to be, so a wrong guess about the language can't hide a stop.
- **Clashes with English are checked:** "wag" counts only alone, twice or with the name, so a dog's wagging tail is no stop.
- **Asking for help with something isn't a call for help:** "help my soek my sleutels" (help me find my keys) and "kan jy help?" are treated like "help me find my keys" today.
- **Timing:**
  - English "stop" is caught when the turn's words arrive, about 0.35 s after the speaker stops;
  - Afrikaans-only stop words come from the second ears, about 1.5 to 2 s later (est.);
  - two fast paths work in every language: "stop" itself (the same word, and the English ears hear it), and the raised palm.
- **A fast Afrikaans stop detector (try):** livekit-wakeword (Apache-2.0) trains a tiny model per phrase from synthetic speech. Train "wag", "hou op" and "staan stil" from synthetic Afrikaans voices on the PC, and run the model beside the name spotter (a few % of a small core, est.). It takes over from the slow path only if it holds on the household's recordings: at least 90 % caught within 0.5 s, and at most one false stop an hour of household talk.
- **Tests:**
  - every stop phrase of every language that is on pauses the wheels from every state (an activity, quiet hours, an alarm, setup, the alive code off), like the palm tests;
  - a stranger's Afrikaans stop pauses; a trusted person's sticks;
  - "wag hier" from a trusted person is a wait;
  - "moenie my volg nie" never moves it;
  - switching Afrikaans off leaves its stop and help words working (answer 6).

## 7. Talking back
- **Which language:** answer 2. The last part of the reply prompt (after the cached part) says which language to answer in, and "one language per sentence".
- **Gemma 4 in Afrikaans (est.):**
  - Afrikaans is one of the African languages large models handle best. A 2025 study of models on African languages (Sahara) found Afrikaans among the strongest, helped by how much of it is on the web.
  - Gemma 4 E4B scores 76.6 % on the 14-language MMMLU test (Gemma 3 27B: 70.7 %), but no Afrikaans score is published for it.
  - Known risks when models write Afrikaans: Dutch words and spellings, English sayings translated word for word, and the formal "u" instead of the family "jy". The owner judges a 40-line Afrikaans set of Pebble's replies.
  - Afrikaans usually takes more tokens per word than English (est. 1.2 to 1.5 times), so replies take a little longer to write.
- **Fixed lines** move into a phrasebook by key and language, and safety lines are never written by a model. Examples (the owner checks the Afrikaans):

  | When | English today | Afrikaans |
  | --- | --- | --- |
  | coming | "Coming!" | "Ek kom!" |
  | following | "Okay, I'm right behind you." | "Okay, ek is reg agter jou." |
  | waiting | "Okay, I'll wait here till you're back." | "Okay, ek wag hier tot jy terug is." |
  | ending | "Okay, I'll stop here." | "Okay, ek stop hier." |
  | not sure | — | "Ek is nie seker nie. Sê dit weer?" |
  | who to follow | "Who should I follow: Sam or Mo?" | "Wie moet ek volg: Sam of Mo?" |
  | a child's kind no | "I can come to you instead!" | "Ek kan eerder na jou toe kom!" |
  | its name shouted | "Did you call me?" | "Het jy my geroep?" |
  | someone on the floor | "Are you okay? Do you need help?" | "Is jy okay? Het jy hulp nodig?" |
  | an alarm, asking | "I can hear a smoke alarm going off. Is everything okay?" | "Ek hoor 'n rookalarm wat afgaan. Is alles reg?" |
  | an alarm, loud | "The smoke alarm is going off!" | "Die rookalarm gaan af!" |
  | not trusted to stand down | "Thanks. I'll keep going until someone I know well tells me it's fine." | "Dankie. Ek hou aan tot iemand wat ek goed ken sê dis reg." |
  | "stop listening" from a stranger (anyone it knows, guests included, may since 20 October 2026) | "Only someone I know can switch my ears off. I don't keep what I hear, though." | "Net iemand wat ek ken kan my ore afsit. Ek hou in elk geval nie wat ek hoor nie." |

- **Holds** (`plans/thinking-out-loud.md`): its phrasebook gains Afrikaans ("Hmm,", "Laat ek dink.", "Oe, goeie vraag.").
- **The wordsmith** writes refusals and endings in the reply language.
- **Barge-in and its own voice:**
  - the English ears hear Pebble's own Afrikaans as garbled English, so "two new words" and "ignore my own voice by its words" both fail for Afrikaans;
  - while Pebble speaks Afrikaans, barge-in uses only its name and the voice rule (with the echo canceller on);
  - a turn heard while it speaks is matched against its own words by the second ears before any stop check, so its own "Ek stop hier" doesn't stop it.

## 8. The voice
| Option | Licence | What it sounds like | Size and speed (est.) | Verdict |
| --- | --- | --- | --- | --- |
| Android's own Afrikaans voice (Google), if the Pixel has it offline (unconfirmed) | Google's | a stock voice: somebody else's | already on the phone | Use if present; checked at first start |
| MMS-TTS Afrikaans (Meta), a VITS voice that sherpa-onnx runs | CC-BY-NC-4.0 | one real reader's voice, learnt from Bible recordings: clear, rather formal | about 110 MB (other MMS languages' files are 108.8 MB); faster than real time | The stopgap until its own voice exists |
| espeak-ng Afrikaans | GPL-3.0 (already inside sherpa's Kokoro) | robotic but clear; nobody's voice | tiny, very fast | The floor; also the pronunciation step for the others |
| Kokoro and Kitten (Pebble's planned voices) | Apache-2.0 | its own | — | Not trained on Afrikaans (sherpa's Kokoro: English and Chinese; Kitten: English). Feeding them Afrikaans sounds through espeak-ng is an untested experiment and would likely sound foreign |
| Piper voices | each voice its own licence; the engine is GPL-3.0 | real people's voices | — | None in Afrikaans |
| **Pebble's own Afrikaans voice** (below) | made here | its own | 20–60 MB; faster than real time on a small core (Piper-style voices run on a Raspberry Pi 4) | The goal |

**Pebble's own Afrikaans voice:**
- A small multi-speaker Afrikaans voice (VITS, the kind Piper uses), trained once on the PC with a smooth voice space, like Kokoro's style vectors. It learns from many voices:
  - the SLR32 Afrikaans speakers (Google and North-West University, CC BY-SA 4.0);
  - varied synthetic Afrikaans voices made with OmniVoice (k2-fsa; 646 languages, Afrikaans among them with 4.4 h; weights CC-BY-NC);
  - pronunciation from espeak-ng's Afrikaans.
- On the phone, at night on the dock, Pebble searches that space for the point its own voice-print model rates closest to its English voice. The voice fence holds: its print must score under 0.28 against every known person's print and every speaker the voice was trained on (their prints ship with the voice). It searches again whenever its English voice moves (agency plan, section 6). Nothing is trained on the phone, and nothing on a laptop.
- **"One voice across both" becomes a number Pebble can check:** its English and Afrikaans voices should match each other as one speaker (0.40 or more on today's voice prints) and match nobody else.
- Honest: two engines will never sound identical. The timbre can match; each language keeps its own accent. The owner, a native speaker, judges whether it sounds Afrikaans or like a Dutch tourist.
- **Mixed replies:** one engine per sentence. English words inside an Afrikaans sentence ("okay", "cool") are said the Afrikaans way, which is how South Africans say them anyway.

## 9. People, households and children
- **The record** (`people/person.py`) gains:
  - `languages`: counts of the turns said to Pebble in each language;
  - `reply_in`: empty means "the language they spoke".

  The person can see it ("what do you know about me?") and change it; forgetting them deletes it.
- **How it's set:** by the owner at setup ("Ina speaks Afrikaans and English"), learned from how someone talks to Pebble, or by a parent for a child.
- **Voice prints:** a bilingual person's prints may differ a little between their languages (advice, not measured). Keep a print from each language; the model-upgrades report already suggests several per person.
- **Mixed households and guests:**
  - Pebble answers each person in their own language.
  - Talking to the room (speaking up, a question to the room) uses the language everyone present shares; when unsure, English.
  - Alarms use both (answer 10).
  - **A language is never a privacy shield.** Speaking Afrikaans in front of an English-only guest doesn't make a private thing sayable. The privacy check goes by who is present, never by who would understand.
- **Children:** the same tiers and limits in every language. Children's speech is harder for every speech model, and children mix languages more, so Pebble asks more often.
- **The ears mark** gains a small language tag ("af") while a second language's ears are on, drawn by plain code like the rest of the mark, because those ears turn more talk into words.
- **The honesty line:** when Pebble isn't sure, it asks once. After two misses it says so: "Ek verstaan nog nie alles in Afrikaans nie. Sal jy dit in Engels sê?" (I don't understand everything in Afrikaans yet. Will you say it in English?) A possible stop is never asked about first; it stops.

## 10. Safety notices and the legal lines
- **The notice** (README, "Safety notices"), in every language Pebble speaks, on the admin screen and said once at setup. In Afrikaans (the owner checks it): "Pebble is nie 'n rookalarm, 'n koolstofmonoksied-alarm of 'n mediese alarm nie. Hou die regte alarms, toets hulle, en vervang hul batterye. Pebble bel nooit self nooddienste nie."
- **Alarm lines** are fixed sentences from the phrasebook, never written by a model.
- **The flashing screen word** shows both languages: ROOK / SMOKE, BRAND / FIRE, HELP, CO.
- **Earthquake:** New Zealand's "Drop, cover and hold!" stays in English, because it is what people are taught here, followed by Afrikaans ("Aardbewing! Gaan plat, skuil en hou vas!"; the owner checks the wording).
- **Notices to the owner's phone** are written in the owner's language (a setting).
- **Standing down** in Afrikaans comes from the same people as in English.
- The beep detectors and the alarm sound need no language.

## 11. Can Pebble learn new languages by itself?
The owner's second question. Partly. On its own, offline, it can:
- notice a language it keeps hearing, and offer to switch it on if it carries that language;
- learn words, names and phrases people teach it, in any language;
- tune its ears and voice to the household's words, names and ways of speaking, with no sound kept;
- on a stronger phone, follow almost any language in "listen-only" mode through one big multilingual model and Gemma.

It can't learn a whole new language just by hearing it:
- a speech model for a language is trained on hundreds of hours of recordings with written transcripts, on a GPU, for days;
- Pebble keeps no sound (a privacy rule), is offline, and has no laptop helper;
- and it never downloads a pack itself.

### Noticing a language
- A small language-ID model (VoxLingua107 ECAPA from SpeechBrain, Apache-2.0, 107 languages including Afrikaans and Māori) looks at no more than one stretch of speech a minute while people talk. Est.: under 1 % of a small core, about 0.1 GB while loaded.
- It keeps only counts: the language, the day and the minutes heard, for the room. No words, no sound, no names, for 30 days (answer 12).
- When a language crosses a threshold (for example, heard on 3 of the last 7 days, 10 minutes in all; to tune), Pebble tells the owner or a trusted person:
  - if it carries a pack: "I keep hearing Afrikaans. I can understand it if you like. Shall I switch it on?" Only the owner or a trusted person can say yes (answer 7);
  - if not: "I keep hearing a language I don't know. I think it might be Hindi."
- Language ID guesses on short clips and between close languages, so Pebble says "I think". A language outside its 107 it can't name at all; it only says it doesn't know it.

### Switching on a language it carries
- Packs are built and tested on the PC. They ship at setup, like the storage plan's prebuilt packs, or the owner drops one into the Wi-Fi inbox (his laptop fetches it; Pebble stays offline).
- A pack is data and at most one model, so adding one needs no new app.
- What a pack holds, and its two levels ("full" and "listen-only"): section 12.
- Room: storage isn't the limit (the storage plan). A full Afrikaans pack with its ears and voice is about 0.5 GB (est.); a words-only pack a few MB.

### Words people teach it
- **What people say:** "In Afrikaans we say 'lekker' for nice." "When I say 'kom gou', I mean come here quickly." "A sloffie is a slipper." "We call the lounge the TV room." "Call me Ouma."
- **Checking:** Pebble repeats it back once ("So 'kom gou' means come here quickly?"). A yes keeps it.
- **Where it's kept:** a lexicon in the self (`lexicon.json`, sealed): the phrase, its language, what it means (a request kind, a thing, a place, a person or plain words), who taught it, when, and how often it is used. Up to about 500 entries; one unused for a year fades.
- **What uses it:**
  - the rules, as more words for the same thing;
  - the models' prompts, with only the entries that match the line heard;
  - the name spotter, for names and nicknames (spelled automatically);
  - the ears (below), and the voice, for how to say a name.
- **The fence, in plain code:**
  - a taught word can make Pebble stop more, call for help more or keep more private; it can never remove, change or override a stop, help, privacy or listening word;
  - a word that lets it move again can be taught only by a trusted person, and works only for trusted people, as moving again does today;
  - strangers can't teach; children can teach names for things, as with "teach" today;
  - nothing about the laws, the gate or trust can be taught;
  - nothing is sent anywhere: the lexicon is the household's, sealed like everything else;
  - forgetting a person forgets the words only they taught;
  - "What words have I taught you?" lists that person's words; "forget that word" removes one.

### Ears and a voice that adapt, with no sound kept
- **Biasing the English ears ("hotwords"):** sherpa-onnx can boost chosen words while decoding, with no retraining.
  - It works only for transducer models (NeMo's included) and only with `modified_beam_search`; Pebble uses `greedy_search` today. It needs the model's `bpe.vocab`.
  - Use it for the household's names, places and taught words.
  - Cost: beam search does more work than greedy (est. 10 to 30 % more for the English ears; measure).
  - On the Pixel: on if it fits the ears' budget; otherwise only while Pebble waits for an answer to its own question ("Sam or Mo?"), through per-stream hotwords (in the Kotlin API; check in sherpa-onnx 1.13.8).
- **Biasing the Afrikaans ears:** whisper.cpp takes a short starting prompt. The household's names and taught words go in it.
- **The name spotter** already spells new names and nicknames itself (`speech/tokens.py`).
- **Corrections, as text:** when someone corrects Pebble ("No, I said LOS DIT"), it keeps the pair "loss it" → "los dit" for that person, and uses it once the same correction has happened twice. Text only, in their record.
- **The voice:** a pronunciation list for names and for Afrikaans words inside English sentences (espeak-ng and Kokoro both take one). Pebble can't learn a sound by hearing it without keeping sound, so it asks: "Do I say it like this, or like this?" and keeps the spelling that was liked.
- **Per-person numbers:** how sure each pair of ears tends to be for a voice, and the person's language prior, refitted at night in numpy in seconds, like the learned heads in `plans/more-freedom.md`.

### Training overnight, honestly
- **Fine-tuning the ears on the household's voices: no.** It needs recordings with correct transcripts, and Pebble keeps no sound (open question A). It also needs a way to train on the phone: ONNX Runtime's Android training package stopped at 1.19.2 in September 2024, and nothing Pebble runs can train a speech model.
- **The small model:** as `plans/more-freedom.md` answer 12 already says, a LoRA for the small model is a research rung, trained on the phone only if a trainer measures well, never on a laptop.
  - Today's llama.cpp trainer fine-tunes whole FP32 models only; its README says a 1B model needs 24 GB.
  - LFM2.5-230M in FP32 with its training state would need about 3 to 4 GB (est.), beside a 5 GB main model.
  - And the words it would learn are already in the lexicon and the prompt.
- **What the Pixel 6 Pro trains at night:** only small numbers (per-person language weights, thresholds), in seconds.
- **Stronger phones:** a small-model adapter on taught lines may become possible as trainers mature (16 GB or more). Learning from everyday request lines would need keeping them longer than 5 minutes (open question B).

### The ladder for learning
| Rung | What it adds |
| --- | --- |
| Pixel 6 Pro (the tested default) | noticing (counts only), the packs it carries, taught words, corrections, name forms, nightly numbers; hotwords if the ears' budget allows. Listen-only for a language without a pack works, but slowly (4.5 to 6 s a short line through Omnilingual, est.), so only when someone asks Pebble to listen in that language |
| Stronger phone | hotwords always on with a wider beam; listen-only for any of Omnilingual's 1,600+ languages at a usable speed; perhaps a small-model adapter on taught lines |
| Never, on any phone | downloading a pack by itself; switching on more listening without a yes; training on household sound (unless the owner decides otherwise, open question A) |

## 12. Adding any language: the method
| Part | Where it comes from | What to check |
| --- | --- | --- |
| Ears | a small Whisper fine-tuned for the language, with ACFT (best); Omnilingual ASR CTC 300M (1,600+ languages; slow on the Pixel); stock Whisper (99 languages; weak on most) | WER on FLEURS (102 languages) and on household recordings kept outside the repo |
| Noticing | VoxLingua107 (107 languages) | — |
| Plain-code words | written here, checked by a speaker | stop, moving again, help, fire, "it's fine", quiet, stop and start listening, private, forget me, yes and no, later, negation |
| Request words | written here | the request table, its traps and the evaluation sets |
| Mind | Gemma 4 E4B (140+ languages in training) | the request and reply sets in that language |
| Memory search | if `plans/more-freedom.md`'s recall model is a multilingual one (for example multilingual-e5-small: MIT, 94 languages including Afrikaans), Afrikaans and English memories find each other | recall tests across the two languages |
| Voice | Android's offline voice; MMS-TTS (1,100+ languages; CC-BY-NC; real readers' voices); espeak-ng (about 100; robotic); Pebble's own voice space, built on the PC | how easy it is to understand, judged by a speaker |
| Notices | translated and checked by a speaker | "not a smoke alarm"; never calls emergency services |
| Name | the spotter, measured on speakers of the language | catches and false fires |

**Two levels:**
- **Full:** everything above, checked by a speaker, with the tests passing. Only then do its stop words count.
- **Listen-only:** ears and mind only. Pebble understands, and answers if it has a voice, but tells people once: "I don't know the stop words in this language yet. Say 'stop' or hold up your hand." Its own stop words are added only by a speaker.

**An example:** te reo Māori is the natural next language in New Zealand. Omnilingual's 7B model scores CER 6.7 % on it from only 19 h of training speech; the 300M will do worse. It would start listen-only, checked with Māori speakers, and is a decision of its own.

## The ladder
### Rung 1: the Pixel 6 Pro (the tested default)
| Part | Choice | When it runs | Processor (est.) | Memory (est.) | Disk (est.) |
| --- | --- | --- | --- | --- | --- |
| English ears | today's NeMo (or Moonshine v2 if it wins the upgrades report's trial) | always, as today | as today | as today | as today |
| Afrikaans ears | an Afrikaans Whisper small with ACFT, in whisper.cpp, its window sized to the turn | turns said to Pebble by people who use Afrikaans; unsure English readings | 1.5–2 s of two big cores for a 2.5 s line | about 0.3 GB, only while an Afrikaans speaker is around | about 0.25 GB |
| Stop check while moving | the ACFT base model | every turn while the wheels move | 0.4–0.6 s of two big cores a turn | about 0.1 GB | about 0.06 GB |
| Which language | plain code | each turn | milliseconds | — | — |
| Afrikaans stop, help and privacy words | the same plain code | every reading | milliseconds | — | tables of a few kB |
| Fast Afrikaans stop words (try) | a livekit-wakeword model | always while moving | a few % of a small core | a few MB | a few MB |
| Request reader | Afrikaans rules, then the main model | each Afrikaans request | as today | — | — |
| Afrikaans voice | Android's offline voice, else MMS-TTS, later its own | each Afrikaans sentence | faster than real time on one core | about 0.1–0.15 GB | about 0.1 GB |
| Noticing languages | VoxLingua107 ECAPA | at most one stretch a minute | under 1 % of a small core | about 0.1 GB | about 0.08 GB |

- **In all (est.):** about 0.5 to 0.6 GB of memory while an Afrikaans speaker is around (almost none otherwise), about 0.6 GB of disk, and 1.5 to 2 s of two big cores per Afrikaans turn said to Pebble. The second ears run before the main model starts on the turn, so they don't fight it; the eyes' slow lane pauses while they run (`set_busy`), as it does for the main model.
- **Measured at first start and on "measure again"** (in `:ears`, like the eyes' bench):
  - which languages Android can speak with no network (text-to-speech voices that don't need one) and hear on the phone (`SpeechRecognizer.checkRecognitionSupport`, Android 13 and later);
  - the second ears on a bundled 3 s Afrikaans clip (FLEURS, CC-BY-4.0): the time with the main model idle and while it writes, and the words, which must match the PC's;
  - the Afrikaans voice: how much faster than real time, and the time to its first sound.
- **Choosing:** the small model if a 3 s turn reads in 2 s or less (the slow end, 95th percentile) with the eyes running; the base model otherwise; Afrikaans ears off if even that misses.
- **Stepping down:** three slow turns in a row, thermal "moderate" or an error drops a rung. With the second ears off, Pebble tells Afrikaans speakers once, in both languages, that its Afrikaans ears are resting, that English works, and that "stop" or a raised hand always stops it.

### Higher rungs (switch on only after the phone measures itself)
| Rung | Ears | Voice | Mind | Switches on when |
| --- | --- | --- | --- | --- |
| 2 | Afrikaans ears on every turn, overheard ones too, if the owner allows (open question C); Fluister turbo or Omnilingual 1B on a GPU or NPU; Gemma 4 hearing the sound itself (try) | its own Afrikaans voice at a higher quality | an Afrikaans-capable small model; Gemma 4 12B on a 16 GB phone | a 3 s turn reads in 1 s or less, thermal "none" or "light", 1 GB spare |
| 3 | one streaming model for both languages (research, below) | — | — | — |

**The research rung: one streaming model for both languages.** Fine-tuning NVIDIA's FastConformer (its CC-BY-4.0 licence allows it) or training a zipformer on Afrikaans, South African English and mixed speech would give Afrikaans the live words, early thinking and barge-in that English has, at today's cost. It would then be a Pixel rung too, and would replace the second ears. The problem is data: real mixed Afrikaans-English recordings are scarce (AfriSwitch has 0.68 h, for testing; the Stellenbosch soap-opera corpus has almost none), so it would lean on synthetic mixed speech. Days of GPU time and an uncertain outcome. Later.

## Seams and where the code goes
**A new `brain/pebble/languages/` package:**

| File | What it does |
| --- | --- |
| `packs.py` | loads a pack (word tables, lines, notices, levels) |
| `choose.py` | picks the language of a turn |
| `phrasebook.py` | Pebble's fixed lines by key and language |
| `lexicon.py` | taught words, sealed, with the fence |
| `notice.py` | the language counts and the offer |
| `af/` | the Afrikaans pack: `words.json`, `lines.json`, `notices.md`, its evaluation sets |

**Other places:**
- `speech/events.py`: `final` gains `lang`, and a late `reading` event carries the second ears' words.
- `people/stops.py`, `safety/words.py`, `conversation/listening.py`, `people/company.py`: word tables per language.
- `understand/rules.py` and `understand/words.py`: the Afrikaans tables and grammar rules; `understand/model.py`: the Afrikaans examples.
- `conversation/core.py`: routing turns to the second ears, the echo check, early thinking off for those turns; `conversation/words.py`: Afrikaans addressing cues and hostile words.
- `people/person.py`: `languages`, `reply_in`, corrections.
- `seams/voice.py`: `Voice.say(text, whisper, lang)`.
- **Android:** a `SecondEars.kt` in `:ears` (whisper.cpp, built with the NDK beside llama-server); `Speech.kt` and `Alarm.kt` pick a voice per language.
- **Sim:** sim speech that says Afrikaans and mixed lines, with a stand-in second ears that is wrong now and then on purpose.

## Honest limits
- **No streaming Afrikaans.** Afrikaans is read a turn at a time: replies start later, and there is no early thinking.
- **Mixed speech is hard for everyone.** On AfriSwitch's real Afrikaans-English recordings the best large systems got 26 to 30 % of words wrong. A small phone model will do worse (est.); short requests with key words fare better than free talk.
- **Across the room.** Today's English model gets 46 % of words wrong on meeting talk from across a table. Afrikaans will be worse.
- **Children** are harder for every speech model, in every language.
- **The scores found are for read speech** (NCHLT, FLEURS). Household talk is messier.
- **Overheard Afrikaans on the Pixel** isn't turned into words, so Pebble misses Afrikaans arguments, gists and facts by words (sounds like shouting and crying still count).
- **Afrikaans-only stop words are slower** than English "stop" until the fast detector proves itself. "Stop" and the palm stay the fast paths.
- **The voice:** until its own Afrikaans voice exists, Pebble sounds like somebody else in Afrikaans. Even then, the two voices match in timbre, not exactly.
- **Gemma's Afrikaans** may drift towards Dutch or English sayings; only a native speaker's checks catch that.
- **The word tables** are written here and checked by one native speaker; regional Afrikaans is covered less well.
- **Language ID** can't separate Afrikaans from English reliably on short clips, so the choice leans on who is speaking.
- **Speeds and sizes are estimates.** Nothing here has run on the Pixel 6 Pro.

## Licences of the new parts
| Part | Licence | Use it? |
| --- | --- | --- |
| Our Afrikaans Whisper (from Whisper small, or FUTO's ACFT small) | Apache-2.0 base; trained on NCHLT (CC BY 3.0), afrikaans-30s (CC-BY-4.0), FLEURS (CC-BY-4.0), Common Voice (CC0) | Yes, with credit lines; hosted like the large made-here models, not tracked in git |
| FUTO ACFT checkpoints and method | Apache-2.0 | Yes |
| Fluister (DigiPhyte) | MIT; its data CC-BY-4.0 and CC-BY-3.0 | Yes: turbo as the teacher on the PC; small if its weights are shared |
| whisper.cpp | MIT | Yes |
| Omnilingual ASR CTC 300M (Meta), sherpa-onnx int8 | Apache-2.0 (its corpus CC-BY-4.0) | Yes, for listen-only packs and higher rungs |
| VoxLingua107 ECAPA (SpeechBrain) | Apache-2.0 | Yes |
| livekit-wakeword | Apache-2.0 (its feature models' licences to check, as the upgrades report says) | Try |
| MMS-TTS Afrikaans (Meta) | CC-BY-NC-4.0 | Yes, as the stopgap; non-commercial |
| espeak-ng Afrikaans | GPL-3.0 | Already listed |
| OmniVoice (k2-fsa) | code Apache-2.0; weights CC-BY-NC; its sound tokenizer under Boson AI's Higgs Audio 2 community licence | PC only, to make training voices; non-commercial |
| SLR32 Afrikaans voices (Google and North-West University) | CC BY-SA 4.0 | PC only; a voice trained on it may have to carry the same licence |
| Piper's training code | MIT (the original) or GPL-3.0 (the current one) | PC only |
| Gemma 3 270M | Gemma terms of use | Only if it wins the small-model test |
| Qwen3.5-0.8B | Apache-2.0 | Only if it wins |
| multilingual-e5-small (if chosen for recall) | MIT | The more-freedom plan's choice |
| Evaluation only, fetched and never committed: FLEURS (CC-BY-4.0), NCHLT (CC BY 3.0; terms accepted on SADiLaR), afrikaans-30s (CC-BY-4.0), AfriSwitch (CC BY 4.0), Common Voice (CC0), Lingua Libre words (CC BY-SA 4.0) | as listed | Yes |

NOTES.md's "Licences of the parts" then gains:
- **non-commercial:** MMS-TTS Afrikaans; OmniVoice's weights, if used;
- **extra conditions:** the Higgs Audio 2 licence (if OmniVoice is used); the Gemma terms (if Gemma 3 270M is used);
- **share-alike:** a voice trained on SLR32, if used;
- **credit:** NCHLT (Van Heerden, Barnard, Badenhorst, Davel and De Waal, via SADiLaR), the afrikaans-30s recordings, FLEURS (Google), FUTO, DigiPhyte (if Fluister is used), Meta's Omnilingual ASR.

## Build order
**Where it fits:** right after the household pack (CLAUDE.md, work order 2.2). The step that needs Pebble's own voice waits for the agency plan's voice step 2 (Kokoro measured on the phone).

1. **Seams and tests first:** `lang` on speech events and `Heard`; `languages` and `reply_in` on the person record; `Voice.say` with a language; the phrasebook (the English lines moved to keys, a mechanical sweep); sim speech in Afrikaans.
2. **The words that keep people safe,** in plain code: stop, moving again, help, fire, "it's fine", quiet, listening, private, forget, yes and no, later. With the "wag" rule, the bare "wait!" rule, all-languages-at-once checking, and the tests in every state.
3. **The Afrikaans ears on the PC:** gather the evaluation sets (FLEURS, NCHLT's test speakers, afrikaans-30s, AfriSwitch, the Lingua Libre words, and the household's own recordings kept outside the repo); build our Afrikaans Whisper small with ACFT, and the base model; compare with Omnilingual 300M. Pick on short-request accuracy and speed.
4. **The second ears on the phone:** whisper.cpp in `:ears`, the rules for when they run, the echo check, measuring at first start, stepping down.
5. **Which language:** the per-turn choice, people's languages, the honesty lines.
6. **Afrikaans and mixed requests:** the word tables and grammar rules; the evaluation sets, with the holdout scored once; the owner's review; the main model's examples; the small-model test.
7. **Answering in Afrikaans:** the prompt's last part, the wordsmith, the holds' phrasebook, and the 40-line set the owner judges.
8. **The voice:** the offline-voice check, MMS-TTS through sherpa-onnx, one voice per sentence.
9. **Safety notices and alarm lines in Afrikaans,** the screen words, the line said at setup, the admin screen and the README.
10. **The name:** "Pebbletjie" and the other forms; measuring "Pebble" said by Afrikaans speakers; the trained "Pebble" model with Afrikaans-accented voices in the mix.
11. **The fast Afrikaans stop detector,** trained on the PC from synthetic voices and measured on the household's recordings.
12. **Learning by itself:** noticing languages, the pack format and the inbox path, the lexicon and teaching, hotwords (measure beam search), corrections.
13. **Pebble's own Afrikaans voice:** the voice space on the PC, the nightly search on the phone, the voice-fence checks. After the agency plan's voice step 2.
14. **Higher rungs,** each measured: the bigger ears on a GPU or NPU, Gemma 4 hearing sound, the one-model research rung.
15. **On the phone:** real-room checks with the household; the README section "Languages"; NOTES.md's licences and credit lines.

A new agent would own `brain/pebble/languages/`. It works with:
- pebble-talk: the reply language, the phrasebook, holds, the wordsmith and barge-in;
- pebble-commands: the request rules, the stop words and the gate;
- pebble-android: `:ears`, whisper.cpp, the voices and first-start measuring;
- the safety code: the help, fire and stand-down words and the alarm lines;
- the people and seal code: the record fields, the lexicon and forgetting.

## Open questions for the owner
Each of these would loosen a privacy rule. **All three were answered on 20 October 2026** (see Owner's answers at the top): A no, B yes (request lines said to Pebble kept sealed for 30 days to learn from), C yes. **None of them is built yet:** B and C come with the languages build, and until then the stricter rule below still holds in the code.

**A. Keeping household speech to tune the ears.** Recordings of the family's voices, with correct transcripts, would let the Afrikaans ears learn the household's accents, which helps the most. But it breaks "sound is never stored". Recommended: no. Until decided: no sound is kept; the ears adapt only through hotwords, prompts, taught words and corrections, and the household's recordings for measuring stay on the owner's PC, made on purpose and outside Pebble.

**B. Keeping request lines longer, so Pebble can learn from them at night.** Today words live 5 minutes. Keeping the lines people say *to* Pebble (never overheard talk) for, say, 30 days would let it learn new ways of asking by itself. Recommended: no. Pebble learns only what people teach it on purpose. Until decided: no.

**C. Overheard Afrikaans turned into words on a stronger phone.** On a phone fast enough to read every turn, Afrikaans talk could get the same treatment as English today (the 5-minute window, the gist, overheard facts under the same rules). Recommended: yes, the same rules as English, but it is left open because it turns more of the household's talk into words. Until decided: overheard Afrikaans is never turned into words, on any phone, except the stop check while moving.

## Sources
- Whisper's FLEURS word error rates by language (Table 13): [Radford and others, Robust Speech Recognition via Large-Scale Weak Supervision](https://arxiv.org/abs/2212.04356)
- Fluister models (sizes, licences, data, NCHLT scores, code-switching notes): [fluister-small](https://huggingface.co/digiphyte/fluister-small), [fluister-tiny](https://huggingface.co/digiphyte/fluister-tiny), [fluister-turbo-transformers](https://huggingface.co/digiphyte/fluister-turbo-transformers)
- The afrikaans-30s recordings: [andreoosthuizen/afrikaans-30s](https://huggingface.co/datasets/andreoosthuizen/afrikaans-30s)
- BuzzASR Afrikaans (FLEURS and Common Voice scores, zero-shot large-v3 CER): [BuzzASR/afrikaans](https://huggingface.co/BuzzASR/afrikaans), [BuzzASR paper](https://arxiv.org/pdf/2609.09554)
- Omnilingual ASR (sizes, licence, 40 s limit, per-language CER, model-size averages on FLEURS): [GitHub](https://github.com/facebookresearch/omnilingual-asr), [per-language results](https://github.com/facebookresearch/omnilingual-asr/blob/main/per_language_results_table_7B_llm_asr.csv), [model card](https://huggingface.co/facebook/omniASR-CTC-1B), [paper](https://arxiv.org/abs/2511.09690); in sherpa-onnx: [docs](https://k2-fsa.github.io/sherpa/onnx/omnilingual-asr/index.html), [int8 model files](https://huggingface.co/csukuangfj/sherpa-onnx-omnilingual-asr-1600-languages-300M-ctc-int8-2025-11-12)
- AfriSwitch, real code-switched African speech (Afrikaans 0.68 h, system scores): [arXiv 2608.26434](https://arxiv.org/abs/2608.26434)
- The Stellenbosch soap-opera code-switching corpus: [Jansen van Vuren, De Wet and Niesler, LREC 2024](https://dsp.sun.ac.za/~trn/reports/jansenvanvuren+dewet+niesler_lrec24.pdf)
- CS-FLEURS (synthetic code-switched speech, CC-BY-NC-4.0): [paper](https://arxiv.org/abs/2509.14161), [dataset](https://huggingface.co/datasets/byan/cs-fleurs)
- NCHLT Afrikaans speech corpus (about 56 h, CC BY 3.0): [SADiLaR](https://repo.sadilar.org/handle/20.500.12185/280)
- SLR32, Afrikaans voices from Google and North-West University (CC BY-SA 4.0): [SADiLaR record](https://repo.sadilar.org/items/4357e52c-f8e8-4109-a373-ed6700dcba77/full)
- FUTO's ACFT: [acft-whisper-small](https://huggingface.co/futo-org/acft-whisper-small), [method](https://github.com/futo-org/whisper-acft), [LiteRT conversions and the short-window notes](https://huggingface.co/litert-community/whisper-acft), [a Basque ACFT fine-tune](https://huggingface.co/itzune/whisper-small-eu-acft)
- Whisper's fixed 30 s window and phone timings: [React Native ExecuTorch benchmarks](https://docs.swmansion.com/react-native-executorch/docs/0.3.x/benchmarks/inference-time); sherpa-onnx's Whisper export: [docs](https://k2-fsa.github.io/sherpa/onnx/pretrained_models/whisper/export-onnx.html)
- Moonshine languages: [Moonshine docs](https://www.mintlify.com/moonshine-ai/moonshine/installation); NVIDIA's multilingual models: [NVIDIA blog](https://blogs.nvidia.com/blog/speech-ai-dataset-models); Vosk's models: [model list](https://alphacephei.com/vosk/models); Lelapa AI's Afrikaans model (proprietary): [model card](https://docs.lelapa.ai/transcribe/model/afrikaans)
- Gemma 4 E4B (languages, MMMLU, audio): [model card](https://huggingface.co/google/gemma-4-E4B-it), [audio docs](https://ai.google.dev/gemma/docs/capabilities/audio); llama.cpp audio: [multimodal docs](https://github.com/ggml-org/llama.cpp/blob/master/docs/multimodal.md), [E2B audio file size](https://geniex.aihub.qualcomm.com/en/tutorials/audio-input)
- Afrikaans in large models (Sahara): [Where Are We? Evaluating LLM Performance on African Languages](https://arxiv.org/html/2502.19582v2)
- LFM2.5's languages (a host's listing; check Liquid's card): [Featherless](https://featherless.ai/models/LiquidAI/LFM2.5-350M); Qwen3's languages: [Qwen3 blog](https://qwenlm.github.io/blog/qwen3/); Gemma 3 270M: [model card](https://huggingface.co/google/gemma-3-270m); multilingual-e5-small: [model card](https://huggingface.co/intfloat/multilingual-e5-small)
- Language ID: [VoxLingua107 ECAPA](https://huggingface.co/TalTechNLP/voxlingua107-epaca-tdnn-ce), [VoxLingua107](https://cs.taltech.ee/staff/tanel.alumae/data/voxlingua107/); Afrikaans and English overlapping on short clips: [Triplet entropy loss for short-speech language ID](https://arxiv.org/pdf/2012.03775)
- Afrikaans sounds (unaspirated p, t, k; the g; the dark l): [Afrikaans phonology](https://en.wikipedia.org/wiki/Afrikaans_phonology)
- Voices: [OmniVoice](https://github.com/k2-fsa/OmniVoice) and [its model card](https://huggingface.co/k2-fsa/OmniVoice); [Piper voices](https://huggingface.co/rhasspy/piper-voices/tree/main); [sherpa-onnx Kokoro](https://k2-fsa.github.io/sherpa/onnx/tts/pretrained_models/kokoro.html); MMS-TTS ONNX file sizes: [a community conversion](https://huggingface.co/Axiveri/Renpiper-mms-onnx-V1); [Simba-TTS (MMS-based, includes Afrikaans)](https://huggingface.co/UBC-NLP/Simba-TTS-lin/blob/main/README.md)
- Hotwords in sherpa-onnx: [docs](https://k2-fsa.github.io/sherpa/onnx/hotwords/index.html), [NeMo transducers and beam search in a wrapper's docs](https://www.mintlify.com/xdcobra/react-native-sherpa-onnx/guides/hotwords), [sherpa-onnx changelog](https://pub.dev/packages/sherpa_onnx_linux/changelog)
- Training on the phone: [ONNX Runtime Android training package](https://mvnrepository.com/artifact/com.microsoft.onnxruntime/onnxruntime-training-android), [llama.cpp training example](https://github.com/ggml-org/llama.cpp/blob/master/examples/training/README.md)
- The first look's recordings: Lingua Libre's Afrikaans words on [Wikimedia Commons](https://commons.wikimedia.org/wiki/File:LL-Q14196_(afr)-Oesjaar-wag.wav) (CC BY-SA 4.0), run against Pebble's own speech files on the PC.
