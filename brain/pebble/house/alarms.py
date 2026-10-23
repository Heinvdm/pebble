import math

LOG_CAP = 100
CHIRP_SCORE = 0.9
CHIRP_GAP_S = 6 * 3600.0
SOUNDING = ("smoke_alarm", "co_alarm", "alarm_beeping", "alarm_sound")
WHAT = {"smoke_alarm": "a smoke alarm", "co_alarm": "a carbon monoxide alarm", "alarm_beeping": "steady alarm beeping", "alarm_sound": "an alarm"}
LIMIT = "A test only shows that each alarm can make its sound, not that it can sense smoke."


def counted(n: int) -> str:
    return {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight", 9: "nine", 10: "ten"}.get(n, str(n))


class AlarmCare:
    def __init__(self, house):
        self.house = house
        self.chirps_since = -math.inf
        self.chirp_said = -math.inf
        self.offer_pending = False

    @property
    def ladder(self):
        return getattr(self.house.safety, "ladder", None)

    @property
    def log(self) -> list:
        return self.house.book["alarm_log"]

    def attach(self) -> None:
        ladder = self.ladder
        if ladder is not None and hasattr(ladder, "listeners"):
            ladder.listeners.append(self.ended)

    def start(self, label: str) -> str:
        ladder = self.ladder
        if ladder is None or not hasattr(ladder, "start_test"):
            return "I can't listen for alarms on this body, so I can't help with a test."
        if not ladder.start_test(by=label):
            if ladder.test is not None:
                return "We're already testing. Press the next alarm's test button when you're ready."
            return "Not now. An alarm is going, so I'm treating it as real."
        self.house.diary(f"{label} started a smoke alarm test.")
        self.house.note(f"{label} started an alarm test; for ten minutes, alarm beeping that stops within half a minute counts as a test", True)
        return f"Okay, I'm listening. Press each alarm's test button, one at a time, and I'll count the ones I hear. The test ends by itself in ten minutes. If an alarm keeps going for more than half a minute, or I see smoke, I'll treat it as real. {LIMIT}"

    def stop(self, why: str = "someone said the test was over") -> str:
        ladder = self.ladder
        test = ladder.end_test(why) if ladder is not None and hasattr(ladder, "end_test") else None
        if test is None:
            return "We weren't testing the alarms."
        return self.result(test)

    def result(self, test) -> str:
        house = self.house
        count = len(test.heard)
        stamp = house.hhmm(house.clock.now())
        house.book["asked"]["last_test"] = house.clock.now()
        house.book.touch()
        house.diary(f"The smoke alarm test ended at {stamp}. I heard {count} alarm{'s' if count != 1 else ''}.")
        if count == 0:
            return f"The alarm test is over. I didn't hear any alarms, so they may be too far away for me, or too low in pitch. {LIMIT}"
        pitches = [h.get("freq_hz") for h in test.heard if h.get("freq_hz")]
        tone = ""
        if pitches:
            tone = " Their pitches were " + ", ".join(f"{round(float(p) / 100) / 10:g}" for p in pitches[:6]) + " kHz."
        return f"The alarm test is over. I heard {counted(count)} alarm{'s' if count != 1 else ''} go off.{tone} {LIMIT} I'll remind you again next month."

    def ended(self, incident, how: str) -> None:
        lead = incident.lead() if hasattr(incident, "lead") else None
        names = set(getattr(incident, "evidence", {}) or {})
        if lead is None or not names & set(SOUNDING):
            return
        house = self.house
        now = house.clock.now()
        kind = next((n for n in ("smoke_alarm", "co_alarm", "alarm_beeping", "alarm_sound") if n in names), lead.name)
        entry = {"at": round(now, 1), "kind": kind, "how": how, "test": how == "tested", "freq_hz": incident.details.get("freq_hz"), "level_db": incident.details.get("level_db"), "room": house.where_am_i()}
        self.log.append(entry)
        del self.log[:-LOG_CAP]
        house.book.touch()
        if how == "tested":
            ladder = self.ladder
            heard = len(ladder.test.heard) if ladder is not None and ladder.test is not None else 1
            house.say(f"Heard that one. That's {counted(heard)} so far.", why="alarm test")
        else:
            house.away.add("alarm", f"{WHAT.get(kind, 'an alarm')} went off", now)

    def tick(self, now: float, mono: float, quiet: bool) -> None:
        ladder = self.ladder
        if ladder is not None and getattr(ladder, "last_test", None) is not None:
            test, ladder.last_test = ladder.last_test, None
            self.house.say(self.result(test), why="alarm test over")
        hearing = self.house.hearing
        chirps = getattr(hearing, "chirps", None)
        if chirps is None:
            return
        fresh = chirps(self.chirps_since)
        if not fresh:
            return
        self.chirps_since = fresh[-1].at
        steady = [c for c in fresh if c.score >= CHIRP_SCORE]
        if not steady or now - self.chirp_said < CHIRP_GAP_S:
            return
        period = steady[-1].period_s or 0.0
        self.chirp_said = now
        every = f"about every {int(round(period / 5.0) * 5)} seconds" if period else "every so often"
        self.log.append({"at": round(now, 1), "kind": "chirp", "how": "heard", "test": False, "freq_hz": steady[-1].freq_hz, "level_db": steady[-1].level_db, "room": self.house.where_am_i()})
        del self.log[:-LOG_CAP]
        self.house.away.add("chirp", f"an alarm chirping {every}", now)
        self.house.note(f"you can hear an alarm chirping {every}, which usually means a low battery", True)
        if quiet:
            return
        line = f"I can hear an alarm chirping {every}. That usually means its battery is low. Some alarms chirp like that when they need replacing, so check its label."
        finder = getattr(getattr(self.house.life, "commands", None), "household", None)
        if getattr(finder, "finds_chirps", False):
            line += " Shall I find which one?"
            self.offer_pending = True
        if self.house.teller.to_household(line, "chirp", mono, urgent=False) and self.offer_pending:
            self.house.asks.expect("find_chirp", "", mono)

    def answer(self, now: float) -> str:
        house = self.house
        parts = []
        last_test = house.book["asked"].get("last_test")
        if last_test:
            days = int((now - float(last_test)) // 86400)
            parts.append("The last alarm test was today." if days == 0 else f"The last alarm test was {days} day{'s' if days != 1 else ''} ago.")
        else:
            parts.append("I haven't heard an alarm test yet.")
        real = [e for e in self.log if not e.get("test") and e.get("kind") in SOUNDING and now - float(e["at"]) <= 30 * 86400]
        if real:
            last = real[-1]
            parts.append(f"I last heard {WHAT.get(last['kind'], 'an alarm')} go off on {house.day_words(float(last['at']))} at {house.hhmm(float(last['at']))}.")
        chirp = next((e for e in reversed(self.log) if e.get("kind") == "chirp"), None)
        if chirp is not None and now - float(chirp["at"]) <= 86400:
            parts.append("An alarm has been chirping today, which usually means a low battery.")
        return " ".join(parts)
