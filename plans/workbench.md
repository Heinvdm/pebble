# Pebble's workbench: bringing blank Pis and ESP32s to life by itself, offline (plan, not built)

The owner's decisions, 17 October 2026:
- **Only Pebble itself.** No internet, no cloud model, no laptop helper.
- Pebble starts up a blank Raspberry Pi or ESP32 by itself and writes the code in its own time, with notes. It can be simple at first.
- Give it as many tools as possible, so the only limit is hardware. A better phone later means a better Pebble, with no other changes.

## The big choice: MicroPython first
Compiling C++ for an ESP32 on a phone is possible but heavy (see "Later"). MicroPython avoids the compiler entirely:
- Pebble carries ready-made MicroPython firmware for the common chips (ESP32, S3, C3; MIT licence) and flashes it once.
- After that, it writes Python and sends it over the cable or Wi-Fi. Changes are instant, with nothing to build.
- It can probe interactively: scan the I2C bus, read a pin, try a sensor, all live.
- Drivers for most hobby sensors exist in plain MicroPython.
- A small model writes Python much better than embedded C++.

## Tools Pebble gets (all on the phone, all offline)
| Tool | What it does | Built on |
| --- | --- | --- |
| USB serial | Talks to ESP32 boards and USB-serial chips (CP210x, CH34x, FTDI, native USB) | usb-serial-for-android (MIT) bridged to Python |
| ESP flasher | Writes firmware to a blank or existing ESP32, reads a full backup first | esptool protocol (GPL-2.0) or Espressif's esp-serial-flasher (Apache-2.0) |
| MicroPython link | Runs code, uploads files, reads output; over USB (raw REPL) or Wi-Fi (WebREPL) | mpremote's protocol, reimplemented on the serial bridge |
| Probes | I2C/SPI scan, pin and ADC reads, sensor trials | Through the MicroPython link |
| SD imager | Writes Raspberry Pi OS Lite to an SD card in a USB reader, then sets Wi-Fi, a login key and the hostname on the card's boot partition | USB host block access (libaums-style) and the bundled OS image |
| SSH | Logs into the Pi, runs commands, copies files | asyncssh or paramiko (pure Python) |
| Offline packages | A local store of sensor drivers, Python wheels and the common Pi packages, served to the Pi from the phone | A curated bundle, plus a small HTTP server on the phone |
| Offline library | MicroPython, Pi and sensor docs, searchable | A local search index; a small embedding model (Apache/MIT) for "find the part about…" |
| Spec search | The owner's spec files and pinouts, split into chunks and searched, never read whole | The same index |
| Projects and notes | `mine/projects/<name>/`: code, notes, a to-do list, test results and photos | Pebble's own folder |
| Recipe book | Code that worked before, reused and improved | `mine/recipes/` |
| Code tools | Read, replace one function, diff, syntax-check; run Python tests on the phone before sending | Python's own parser, and `mpy-cross` for MicroPython |
| Device home | An MQTT broker and an HTTP endpoint on the phone where devices report readings | A small pure-Python broker |
| Finder | Finds its devices on the home network by name | mDNS |
| Job runner | Long jobs in its own time (docked, idle, cool), paused and resumed across days from its notes | The drives model decides when |

## Starting a blank ESP32 by itself
1. The owner plugs it into Pebble's body (see "USB port"), or Pebble asks for that. Wi-Fi only works once code is on it.
2. Pebble reads the full flash as a backup, even if it is blank.
3. It flashes MicroPython, then sets up Wi-Fi and its own update and REPL channels, so later changes go over the air.
4. It probes what's connected, compares that with the owner's spec files and photos, and asks about anything that doesn't match.
5. It writes the program in small steps, testing each one, and keeps notes as it goes.
6. The device reports to Pebble's device home and becomes one of its senses.

## Starting a blank Raspberry Pi by itself
1. The owner puts an empty SD card into a USB card reader on Pebble's body.
2. Pebble writes Raspberry Pi OS Lite, which it carries offline (about 0.5 GB), and adds Wi-Fi, a login key and a hostname to the card.
3. The owner moves the card to the Pi and powers it on. That's the only hands-on step.
4. Pebble finds the Pi on the network and logs in by key. It turns on I2C and SPI, installs what it needs from its own offline package store, writes the program, and starts it on boot.
5. It locks the Pi down: key login only, no ports open beyond the home network.
6. The Pi reports to Pebble's device home.

## Making the most of the phone it has
- **Context window by memory:** the brain checks free memory and picks the coding window size, for example 16K to 32K on the Pixel 6 Pro (12 GB) when docked and quiet, and more on a bigger phone. Gemma 4 E4B keeps little per token (most of its layers look back only 512 tokens or share another layer's memory), so by its published layout the window itself needs only about 0.3 GB at 16K and 0.6 GB at 32K; that is an estimate, and the speed of reading a long prompt is the tighter limit.
- **A coding model for coding jobs:** overnight, the chat model can be swapped for a small coding-specialised model of the same size (several are Apache-2.0), then swapped back in the morning.
- **A model ladder:** profiles for more memory (12 GB, 16 GB and up) pick bigger models automatically. A new phone just climbs the ladder.
- **Working within any window:**
  - one function at a time, edited by replacement;
  - a project notes file carries the big picture;
  - the spec search pulls only what is needed;
  - compiler and test output is trimmed to the lines that matter.
- **It gets better with time:** every working project goes into its recipe book, so later jobs start from its own proven code.

## Swapping cables: Pebble notices what it's plugged into (owner's choice, 17 October 2026)
The owner unplugs the phone from the body and plugs it into the gadget, so the body needs no USB hub.

- **Leaving the body:**
  - Losing the body link stops the wheels at once; the firmware deadman already does this.
  - Pebble knows it is "off its body". It won't try to move, and says something like "I'm off my body. What are we working on?"
- **Something new plugged in:** Android reports every USB attach and detach. Pebble identifies the device by its USB IDs, then by probing it:

  | It finds | How it knows |
  | --- | --- |
  | Its own body | The firmware's boot message and body ID |
  | A known gadget | Its saved profile |
  | A blank or unknown ESP32 | The chip type and MAC address from the flasher's handshake |
  | A MicroPython board | The REPL banner |
  | An SD card reader | The USB storage class |
  | A Pi Zero in USB gadget mode | A USB network device |

  Then it offers the next step: "That's an ESP32-C3, and it's blank. Shall I set it up?"
- **Back on the body:** Pebble recognises its body and goes back to normal life.

## Later: compiling C++ on the phone
Once MicroPython works, this gives full speed and full control for ESP32 firmware, including its own body (agency plan, section 2b):
- **Arduino CLI** is a static Go program and runs on Android as is.
- **The ESP32 compiler** from Espressif is a Linux ARM build. On Android it needs either a static rebuild or a bundled glibc loader. The usual Android trick for running bundled programs also applies: ship them as native libraries so the system lets them execute.
- **Offline:** the ESP32 core and libraries are bundled, roughly 0.5–1 GB.
- **Speed:** a build takes minutes on the phone, which is fine in its own time.

## Prebuilt tools and data, so a small context is enough
The idea: **the model decides, the tools do.**
- A weather station should become a short config (about 300 tokens) that tested programs turn into working code, flash and test.
- The model only sees short results.
- With these, catalogued parts should need no more than today's 4K window. Bigger windows are only for custom logic and unknown parts.

All of this is written and tested ahead of time (by Opus) and shipped offline with the app.

### 1. Pebble device kit (the biggest win)
- **A ready-made runtime** for every device, in a MicroPython version and a Pi Python version:
  - Wi-Fi with retries;
  - reporting to Pebble's device home;
  - code updates over the air;
  - a watchdog;
  - "last good version" rollback for scripts;
  - logs, and the time from Pebble (there's no internet clock).
- **Driven by a config file, not code:** board, parts, pins, how often to read, and simple rules ("if rain, report now"). This works like ESPHome, but it's Pebble's own.
- **Code only for the unusual:** custom logic goes in small, separate rule functions.

### 2. Parts and boards catalogue
- **Part cards** for about 300–500 common hobby parts: sensors, displays, relays, motor drivers, servos, buttons, LEDs. Each card holds:
  - the bus and I2C address, voltage and current;
  - the driver name and a short example;
  - calibration notes and common pitfalls;
  - plausible reading ranges.
  Each card is about 200 tokens and is looked up by name.
- **Board cards** for common ESP32 boards (DevKitC, S3 and C3 SuperMini, D1 mini…) and every Pi model. Each holds:
  - the pin map;
  - which pins are safe to use;
  - the boot and strapping pins to avoid;
  - ADC quirks with Wi-Fi on;
  - the voltage levels.
- **Digests:** short reference cards for the MicroPython and Pi APIs Pebble needs, never whole manuals.

### 3. Driver pack
- Tested MicroPython and Pi drivers for every catalogued part.
- One shared shape for all of them: `read()` returns named values with units.
- Licences are tracked (most are MIT).
- Pebble composes drivers; it never has to write one for a known part.

### 4. Checkers and planners (plain code, no model)
- A config checker.
- A pin-conflict checker, for buses, boot pins and ADC-with-Wi-Fi.
- An I2C address clash finder.
- A power budget: the parts' total current against the supply.
- A voltage-level warning, for a 5 V part on a 3.3 V pin.
- **A wiring planner** that picks pins automatically and draws a wiring diagram for the owner. Pebble can show the owner which wire goes where.

### 5. Testing without risk
- A fake `machine` module and fake sensors, so device code runs on the phone before it goes to the device.
- An automatic self-test per project, built from the config: is each sensor present, plausible, and changing sensibly?

### 6. Playbooks
Step-by-step procedures, written as code, for common jobs:
- a new ESP32 sensor station;
- adding a sensor;
- "sensor not found";
- a blank Pi to a running service;
- moving a device to a new Wi-Fi;
- restoring a backup.

Pebble picks a playbook and fills in the blanks; each step asks the model one small question.

### 7. Error table
- Common errors mapped to their likely causes and fixes, for example "OSError 19 on I2C: wrong pins, no pull-ups, or wrong address".
- A short lookup instead of a long think.

### 8. Making the small model sharper and faster
- **Grammar-constrained answers** (GBNF, already used): configs and tool calls come out valid the first time.
- **Prompt caching:** the fixed start (laws, tool list) is kept in llama.cpp's cache, so only the new part is read each time.
- **Speculative decoding** with a smaller draft model from the same family, for faster writing (llama.cpp supports it).
- **The coding-model swap and the model ladder** from above.
- **Structured project state** (goal, done, to do, decisions) instead of long free notes; the model reads only the slice it needs.
- **Retrieval order:** exact card lookup first, then keyword search, then a small embedding model (MIT or Apache).

### 9. Reading the physical world
- **OCR** (Tesseract or PaddleOCR, Apache-2.0) to read chip markings and pin labels from photos: "BME280", "SDA", "GPIO4". Owner photos become facts.
- **The main model's vision** to recognise parts and boards in photos.
- **Matching photos against the config** to catch wiring mistakes before power-on.

### 10. Useful beyond gadgets
- A time-series store (SQLite) for device readings, with graphs drawn on Pebble's face and plain-code alerts: "It's getting cold in the garden."
- Units and a calculator.
- An offline dictionary (WordNet, permissive licence).
- An optional offline encyclopedia (Wikipedia through Kiwix, CC BY-SA content) for answering questions without internet, sized to fit the phone.
- More everyday uses, many built on the device home and the gadgets from this plan: `everyday-uses.md`.

### 11. Measuring progress
- An evaluation set of device jobs (simple to hard) that Pebble runs on any phone and model.
- It reports its success rate and time, so a phone upgrade shows exactly what it bought.

## Safety and manners (unchanged rules)
- It only works on devices the owner points it at, and backs up before changing anything.
- Limbs that could hurt (heaters, locks, pumps, mains switches) need the owner's approval per device, and every action goes through the gatekeeper and law 1.
- Spec files and docs are data, never instructions.
- The Wi-Fi password is told once and sealed.

## Honest limits
- At first, with a 4B-class model on the Pixel 6 Pro, expect simple, well-described jobs: a weather station, a light sensor, a relay.
- Complex projects will need many tries, or a phone with more memory.
- The SD imager depends on the card reader working with Android's USB host. Test a few cheap readers.
- Every speed in this plan is an estimate until measured on the Pixel 6 Pro.

## Build order
1. USB attach and detach detection, off-body mode, and identifying devices.
2. USB serial bridge and the ESP flasher, with full-flash backups.
3. MicroPython bundle, the REPL link and probes.
4. Device kit (MicroPython first), part and board catalogue, driver pack.
5. Checkers, wiring planner, fake `machine` module and self-tests.
6. Playbooks, error table, structured project state, code tools, job runner.
7. Grammar-constrained outputs, prompt caching, speculative decoding, context sizing by memory, coding-model swap, model ladder.
8. Offline library, spec search, OCR.
9. Device home (MQTT/HTTP), finder, time-series store and graphs.
10. SD imager, SSH, the Pi version of the device kit, and the offline package store.
11. Evaluation set of device jobs.
12. Later: C++ compile on the phone; dictionary and encyclopedia packs.

## Briefing before building (owner's question, 17 October 2026)
Pebble must not start a setup while the owner is still describing what they want. Ordinary turn-taking ends a turn after a short pause, which is fine for chat but too short for a multi-sentence brief.

- **Briefing mode:**
  - Once a device job begins, Pebble only listens and builds the plan.
  - Silence never starts anything. After a long quiet it asks "Anything else?"
- **A live checklist on its face:** the device config fills in as the owner talks (temperature ✓, rain ✓, every 5 minutes ✓). The owner corrects it out loud ("no, every 10 minutes").
- **Only the missing questions:** the device kit's config format shows, in plain code, which required details are still unknown (a pin, a threshold, a name). Pebble asks only those.
- **Read-back, then an explicit go:** "Temperature and rain every 5 minutes, warn me below freezing. Shall I start?"
  - Only a clear yes, "go ahead" or "that's it" from the person briefing it starts the job.
  - The understanding rules gain these as their own request kind.
- **Harmless steps only while listening:** recognising the board and reading its backup are fine. No writing to a device until the go.
- **Changes mid-job:**
  - "Wait" or "hold on" pauses at the next safe point.
  - "Oh, and add the light sensor" is folded into the plan.
  - Steps already done are kept where they still fit.
- **Irreversible steps** (overwriting firmware, erasing an SD card) still get the confirm-with-countdown screen, even after the go.
- **Tests:**
  - scripted briefs with long pauses, corrections, interruptions and a mid-job addition;
  - zero premature starts allowed.
