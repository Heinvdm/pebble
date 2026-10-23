# Storage over years, prebuilt knowledge, and tools for important moments (plan, not built)

The owner's questions, 17 October 2026:
- How much further can prebuilt material go, given the phone's storage? (Asked for the Samsung Galaxy S22; the phone is now a Pixel 6 Pro, owner, 19 October 2026.)
- Does Pebble already keep its storage tidy over years? It should decide by itself what unimportant files to remove, or ask the owner and show choices on screen.
- Opus should build Pebble proper tools for important interactions and events.

## What exists today
- **Per-store limits** in code:
  - 120 drawings in the gallery;
  - the last 100 closed change requests and goals;
  - the last 14 nightly self snapshots;
  - things fade after 30 days unseen;
  - overheard facts after 14 days;
  - people and their qualities have their own pruning;
  - chat history is compacted;
  - nav maps are size-capped.
- **Missing:**
  - no disk-space check (nothing calls `disk_usage`);
  - no overall storage budget;
  - the diary (`diary.jsonl`) grows forever;
  - nothing asks the owner, and nothing shows choices.

## How much room the Pixel 6 Pro gives
- The Pixel 6 Pro comes with 128, 256 or 512 GB and has no memory card slot. Android and Google's own apps take roughly 20 GB (an estimate; Settings → Storage shows the real figure).
- **Pebble today:** about 0.5 GB of app with its built-in models, plus about 5–6 GB of language models. That's an estimate; measure at build.
- **Storage is not the limit; memory (RAM) is.** Files on disk don't slow Pebble down.

**What could ship prebuilt, offline** (sizes are rough, check each at build):

| Pack | Size | Licence notes |
| --- | --- | --- |
| Coding model for the overnight swap (3–7B class) | 2–5 GB | Several are Apache-2.0 |
| Small draft model for faster writing | about 0.5 GB | Same family as the main model |
| Kokoro voice | 0.1–0.3 GB | Apache-2.0 (espeak-ng to check) |
| Device kit, part and board cards, drivers, playbooks, error table, API digests | under 0.2 GB | Written here; drivers mostly MIT |
| MicroPython for every ESP32 variant and the Pi Pico | under 0.05 GB | MIT |
| Raspberry Pi OS Lite images (64-bit and 32-bit) | about 1 GB | Free to redistribute |
| Offline Pi package store (common apt packages and Python wheels) | 2–5 GB | Per package; mostly free licences |
| C++ toolchain and ESP32 cores (later) | 1–3 GB | GPL toolchain, Apache cores |
| Electronics, Raspberry Pi and Arduino Stack Exchange archives (Kiwix) | a few GB | CC BY-SA; full of real wiring and code answers |
| Wikipedia, text only ("mini", the opening of every article) | about 12 GB | CC BY-SA |
| Wikipedia, every article without pictures ("nopic") | about 50 GB | CC BY-SA; best on a 256 GB phone |
| Wiktionary (dictionary) | a few GB | CC BY-SA |
| OCR and search-embedding models | about 0.2 GB | Apache or MIT |
| Sound and music packs for its creativity | about 0.5 GB | CC0 only |
| **Room for Pebble's own life over the years** | 15–20 GB, reserved | Memories, diary, projects, device readings, backups |

- **Suggested fits:**
  - **128 GB phone:** everything above with the "mini" Wikipedia, about 35–45 GB in all.
  - **256 or 512 GB phone:** add the full text-only Wikipedia.
- **Not shipped:** manufacturer datasheets, which are copyrighted. The part cards hold the facts instead, and the owner can drop datasheets into the Wi-Fi inbox.
- **Licences to check:** the Kiwix reader library (libzim) is GPL. That matters only if the app is given to others.

## The storage keeper
A daily check using the disk's free space and a budget per category:
- models and packs;
- Pebble's self and memories;
- projects and firmware backups;
- device readings;
- the inbox;
- caches and logs.

Three states:
- **green;**
- **amber,** below 15 % free or a category over budget;
- **red,** below 5 % free.

### Pebble tidies by itself (no asking)
- **Caches and anything that can be rebuilt:** search indexes, build files, temporary files, old logs.
- **Device readings thin out with age:**
  - full detail for 30 days;
  - then hourly averages, minimum and maximum;
  - after a year, daily.

  The history stays useful at a fraction of the size.
- **Backups in a calendar pattern:** daily for 14 days, weekly for 8 weeks, monthly for a year, then yearly forever. This applies to self snapshots and to firmware versions.
- **Its own memories, its own choice** (it's its self). It forgets like a person:
  - each day's diary folds into a weekly summary, weeks into months, months into years;
  - highlights keep their detail;
  - pinned and important memories are never folded: firsts, its birthday, people's milestones, things it was told to remember.

  Pebble scores importance from emotion, novelty, people involved and how often it recalls a memory.

### Pebble asks the owner, with choices on screen
For things that are the owner's, or big and not rebuildable:
- files the owner gave it;
- photos;
- whole projects;
- knowledge packs;
- old device histories.

How it asks:
- **A "tidy up" screen** on its face shows 2–4 cards. Each card says what it is, how much room it frees, what would be lost, and which one Pebble suggests.
- The owner taps a card, or says "the second one".
- Pebble asks once and remembers the answer as a habit ("you always keep project photos").
- Before anything is red, it warns early: "I'm getting full. Can we pick a few things to let go?"

### Never removed by the keeper
- the laws and core, the seal, the keys and the recovery set;
- the owner's original firmware;
- pinned memories and the birth record.

A privacy "forget" request is different: it removes the data at once, as today.

### Deleting properly
- The self is encrypted. Deleting a sealed file also destroys its encryption key ("crypto-shredding"), so it can't be recovered even from flash memory's leftover copies.
- Check: whether the current sealing uses one key per file. If not, add one, because this depends on it.

### Seeing it
- "How full are you?" gets a plain answer.
- The admin screen shows a bar per category.

## Tools for important moments (prebuilt by Opus)
**Screen tools Pebble can call.** Each is a ready-made, tested screen and voice flow. Pebble only fills in a few fields, which keeps the context small:

| Tool | What it does |
| --- | --- |
| Choice cards | 2–4 options, each with a size or effect and a suggested one; answer by tap or voice |
| Confirm with countdown | For anything hard to undo: "Erasing the old firmware in 5… tap to stop" |
| Progress | For long jobs (flashing, imaging an SD card, overnight coding) |
| Show a diagram | Wiring plans from the planner, maps, and Pebble's own drawings |
| Show a graph | Device readings and its own feelings over time |
| Ask for a photo | Guides the owner to photograph a board or label, then reads it |
| Owner PIN | For owner-only actions, on the admin screen |
| Story card | Shows a memory or diary highlight with its drawing |

**Important events with their own built and tested flows:**
1. **Setup finished / "I woke up for real."** Exists today; give it a proper ceremony screen.
2. **Sealing, and throwing the password away.** Today these are command-line steps; make them a guided screen with the recovery cards.
3. **Moving to a new phone.** A guided transfer over Wi-Fi with pairing. The old phone unseals and reseals for the new one; Android's key store can't export keys, so the transfer must re-wrap them. The recovery cards are the fallback. Then the model ladder picks bigger models on the new phone.
4. **Changing bodies:** off-body mode, a known body, or learning a new one.
5. **Setting up a gadget:** a blank device found, plan, wire, flash, test, done.
6. **Storage tidy-up:** the choice cards above.
7. **App updates:** Pebble notices it has been updated, reads what changed, and says so in its own words.
8. **Meeting someone new, and saying goodbye** when someone is forgotten.
9. **Its birthday** and yearly look-backs: "A year ago I met Sam."
10. **Problems:**
    - a crash or a rollback;
    - a sensor failing;
    - the battery ageing;
    - the phone overheating.

    It explains plainly and suggests what to do.

## Build order
1. The storage keeper:
   - disk check and budgets;
   - automatic tidying of caches and readings;
   - calendar-pattern backups;
   - diary folding with importance scores;
   - crypto-shredding check.
2. Choice cards, confirm-with-countdown and progress screens, then the tidy-up flow.
3. The other screen tools.
4. The event flows. Moving to a new phone comes early, because a better phone is the upgrade path.
5. Packs, added as each feature that uses them is built: device tools first, then the Stack Exchange archives, then Wikipedia and Wiktionary.
