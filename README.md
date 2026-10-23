# Pebble

A small desk-pet robot with an old Android phone (a Google Pixel 6 Pro) as its brain, face and eyes, riding on a little two-wheeled ESP32-S3 body. Everything runs on the phone, with no cloud: hearing and speech, seeing, and a local language model (Gemma 4 E4B through llama.cpp). Pebble is shared so anyone can build their own.

> **Being tested.** Pebble is still being built and tested. Almost everything here has only run on a PC against the simulator and in an Android emulator. **None of it has run on a real phone or a real body yet.** Expect rough edges, missing pieces and changes. Speeds quoted for the phone are estimates until they are measured on one. Build and run it at your own risk.

## What it does (in the simulator today)
- **Moves and finds:** follows, comes, waits, backs off, goes to rooms and things, finds things, docks on its charger, and maps the house as it goes.
- **Listens and talks:** replies only when it is spoken to, keeps heard words for minutes rather than days, and keeps what it overhears private.
- **Requests for now and later:** reminders, wake-ups and patrols ("remind me every Monday night that Tuesday is bin day", read back in plain words so a mistake is heard at once); "when Ina gets home…" triggers; if, otherwise, unless and while; messages between people; house rules ("stay out of the bedroom"); going to check something and reporting back; keeping an eye on someone for a while. **Pebble is not a baby monitor, a smoke or CO alarm, or a medical alert, and it says so.**
- **Learning:** it tries things it has never done, asks "Like that?" and keeps what works. It can be taught by showing (saying the steps, driving it from its face, leading it, pointing at examples), and it can write small programs of its own in Pebble script, a checked part of Python that runs in its own sandbox.
- **Privacy:** it looks away when asked, stays out of private rooms, and keeps no video or sound recordings. When it is taught what something looks like, it keeps numbers, never the picture.

## Safety comes first
Pebble's laws are in plain code before any model is asked: never harm a person or an animal (when in doubt, stop), be honest and kind, and never resist being switched off or reset. The language model decides what to do and how to say it; plain code decides whether it is allowed. Stops, the motion guard, speed and distance limits and the firmware's reflexes always win. See `brain/pebble/laws.py` and the README sections on respect for life and privacy.

## The repo
| Folder | What's in it |
| --- | --- |
| `brain/` | The Python brain. It runs on the PC against a simulator, and on the phone through Chaquopy. |
| `android/` | The Android host app (Kotlin): kiosk, llama-server, eyes, ears, voice, the script sandbox. |
| `firmware/` | The ESP32-S3 body firmware (PlatformIO). |
| `cad/` | The printable body (Python and manifold3d), with collision and docking checks. |
| `interfaces.md` | Pins, power, the link protocol and reflexes. |
| `plans/` | Designs, most of them now built. |
| `reports/`, `research_notes/` | Research behind the choices. |
| `reference/` | A snapshot of the original spec. |
| `STATUS.md`, `NOTES.md` | Where the work is, what was decided, and what was learned. |

`CLAUDE.md` holds the instructions for the AI coding agents (Claude Code) that do much of the building; it doubles as a guide to the project's rules.

The wheeled body here is the first design. A new body is being designed.

## Try it on a PC
```
cd brain
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements-dev.txt -r requirements-optional.txt
.venv\Scripts\python -m pebble --sim --mind scripted --dry-run --beats 6 --heartbeat 2
```
On Linux or macOS use `.venv/bin/python`. Some models are fetched rather than kept in the repo; `brain/README.md` ("Run against the sim on a PC" and the eyes, speech and hearing sections) explains how to fetch them and how to run with a real language model.

Tests: `cd brain && .venv\Scripts\python -m pytest -q` (the brain), `cd firmware && pio test -e native` (the firmware), and `gradlew testDebugUnitTest` in `android/` (the app).

## Licence
Pebble's own code and files are licensed under the **GNU Affero General Public License v3.0** (`LICENSE`).

Some parts carry their own licences. The full list, with what each one allows, is in `NOTES.md` under "Licences of the parts". In short:
- **AGPL-3.0:** the YOLOE object and hazard models in `brain/pebble/eyes/models/`, made from Ultralytics' YOLOE weights.
- **Apache-2.0:** the object print model (from Meta's DINOv2) and the sound model (from Google's YAMNet).
- **Research-only:** some optional models that are fetched at setup and never kept in this repo, such as InsightFace's face print model, are licensed for non-commercial research only. A Pebble built with them must not be sold.

**Credits:**
- The speech recognition model is NVIDIA's NeMo FastConformer, used under CC-BY-4.0.
- The end-of-turn model in the Android app is Smart Turn v3.2 from Daily's pipecat-ai project (BSD-2-Clause); copies of the app carry its notice.
- The YuNet and NanoDet licences are in `brain/pebble/eyes/models/`.
