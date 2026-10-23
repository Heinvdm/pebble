from .base import Activity, Ending
from .kit import Kit
from .motion import Wheels, leave_dock
from .rounds import can_drive, find_place, go, known_places, tour, where

SCORE_MIN = 0.3
RECENT_S = 600.0
LISTEN_S = 70.0
LISTEN_MIN_S = 35.0
LISTEN_MAX_S = 130.0
CHIRPS_WANTED = 2
STILL_FIRST_S = 1.0
CHECK_S = 0.5
SURE_DB = 3.0
MAX_PLACES = 8
STOP_BATTERY = 25.0
LOW_BATTERY_LINE = "That usually means its battery is low."


def middle(levels: list[float]) -> float | None:
    if not levels:
        return None
    ordered = sorted(levels)
    half = len(ordered) // 2
    return ordered[half] if len(ordered) % 2 else (ordered[half - 1] + ordered[half]) / 2.0


def loudest(results: list[tuple[str, list[float]]]) -> list[tuple[str, float]]:
    return sorted(((name, middle(levels)) for name, levels in results if levels), key=lambda item: item[1], reverse=True)


def verdict(results: list[tuple[str, list[float]]]) -> tuple[str, str, str | None]:
    heard = loudest(results)
    if not results:
        return "you could not get to any room or spot to listen", "I couldn't get to any of the rooms to listen, so I can't tell which one it is.", None
    if not heard:
        return "you heard no chirp anywhere you listened", "I didn't hear it chirp while I went round, so I can't tell which one it is. It may have stopped.", None
    best, level = heard[0]
    if len(results) == 1:
        return f"you only got to listen in the {best}", f"I only got to listen in the {best}, where I heard it, so I can't compare. {LOW_BATTERY_LINE}", None
    if len(heard) == 1:
        return f"you only heard it in the {best}", f"I think it's the one in the {best}. I only heard it there. {LOW_BATTERY_LINE}", best
    second, other = heard[1]
    if level - other < SURE_DB:
        return f"the {best} and the {second} sounded about the same", f"It's the one in the {best} or the {second}. They sounded about the same, and chirps echo, so I can't be sure. {LOW_BATTERY_LINE}", None
    return f"it was loudest in the {best}", f"I think it's the one in the {best}. It was loudest there. {LOW_BATTERY_LINE}", best


class FindChirp(Activity):
    kind = "find_chirp"

    def describe(self) -> str:
        return "looking for the chirping alarm"

    def _heard(self, kit: Kit, since: float) -> list:
        return [chirp for chirp in kit.chirps(since) if chirp.score >= SCORE_MIN]

    def _listen_for(self, recent: list) -> float:
        periods = sorted(chirp.period_s for chirp in recent if chirp.period_s)
        if not periods:
            return LISTEN_S
        period = periods[len(periods) // 2]
        return max(LISTEN_MIN_S, min(LISTEN_MAX_S, CHIRPS_WANTED * period + 5.0))

    def _why_stop(self, kit: Kit, wheels: Wheels) -> Ending | None:
        if kit.battery_low():
            return Ending("battery", "your battery got low while you were looking for the chirping alarm", "My battery's low, so I have to stop looking.")
        battery = kit.battery_pct()
        if battery is not None and battery < STOP_BATTERY:
            return Ending("battery", f"your battery fell to {round(battery)} percent while you were looking for the chirping alarm", "My battery's getting low, so I have to stop looking.")
        reason = wheels.why_not()
        if reason:
            return Ending("stopped", f"you stopped looking for the chirping alarm ({reason})")
        return None

    async def _listen(self, kit: Kit, wheels: Wheels, seconds: float) -> tuple[list[float], Ending | None]:
        await kit.pace.sleep(STILL_FIRST_S)
        since = kit.body.clock.now()
        start = kit.pace.now()
        levels: list[float] = []
        while kit.pace.now() - start < seconds:
            stop = self._why_stop(kit, wheels)
            if stop is not None:
                return levels, stop
            levels = [chirp.level_db for chirp in self._heard(kit, since)]
            if len(levels) > CHIRPS_WANTED:
                break
            await kit.pace.sleep(CHECK_S)
        return levels, None

    async def run(self, kit: Kit) -> Ending:
        if kit.chirps is None:
            return Ending("failed", "you have no way to pick out chirps on this body", "I can't pick out chirps on this body yet.")
        if not can_drive(kit):
            return Ending("failed", "you can't drive round the rooms on this body", "I can't drive round the rooms on this body.")
        if where(kit) is None:
            return Ending("failed", "you have lost track of where you are", "I've lost track of where I am. I'll know again after a visit to my charger.")
        places = known_places(kit)
        if len(places) < 2:
            return Ending("failed", "you do not know enough rooms or spots to compare", "I don't know my way round the rooms well enough yet, so I can't tell which one it is.")
        recent = self._heard(kit, kit.body.clock.now() - RECENT_S)
        listen_s = self._listen_for(recent)
        wheels = Wheels(kit).open()
        results: list[tuple[str, list[float]]] = []
        skipped: list[str] = []
        try:
            if not recent:
                kit.say("I haven't heard it lately, so I'll listen here for a minute first.")
                levels, stop = await self._listen(kit, wheels, listen_s)
                if stop is not None:
                    return stop
                if not levels:
                    return Ending("done", "you listened for a chirp and heard none", "I listened for a minute and didn't hear any chirping. Tell me when you hear it again.")
            if kit.body.telemetry.docked and wheels.why_not() is None:
                await leave_dock(kit, wheels)
            for name, x, y, radius in tour(places, where(kit))[:MAX_PLACES]:
                stop = self._why_stop(kit, wheels)
                if stop is not None:
                    return Ending(stop.how, f"{stop.text}; you had listened in {len(results)} places", stop.say)
                trip = await go(kit, x, y, radius, door=True)
                if not trip.ok:
                    if trip.how in ("stopped", "battery"):
                        return Ending(trip.how, f"you stopped looking for the chirping alarm on the way to the {name} ({trip.text})")
                    skipped.append(name)
                    kit.note(f"you could not get to the {name} to listen for the chirp ({trip.text})")
                    continue
                await wheels.halt()
                levels, stop = await self._listen(kit, wheels, listen_s)
                results.append((name, levels))
                kit.note(f"you listened in the {name}: " + (f"{len(levels)} chirps, about {round(middle(levels))} dB" if levels else "no chirp"))
                if stop is not None:
                    return Ending(stop.how, f"{stop.text}; you had listened in {len(results)} places", stop.say)
            heard = loudest(results)
            if len(heard) >= 2 and heard[0][1] - heard[1][1] < SURE_DB:
                results = await self._again(kit, wheels, results, [heard[0][0], heard[1][0]], listen_s)
            text, say, winner = verdict(results)
            place = find_place(kit, winner) if winner else None
            if place is not None and self._why_stop(kit, wheels) is None:
                await go(kit, place[0], place[1], place[2], door=True)
        finally:
            await wheels.halt()
            wheels.close()
        if skipped:
            text += f"; you could not get to {', '.join(skipped)}"
        return Ending("done", text, say)

    async def _again(self, kit: Kit, wheels: Wheels, results: list, names: list[str], listen_s: float) -> list:
        merged = {name: list(levels) for name, levels in results}
        for name in names:
            if self._why_stop(kit, wheels) is not None:
                break
            place = find_place(kit, name)
            if place is None:
                continue
            trip = await go(kit, place[0], place[1], place[2], door=True)
            if not trip.ok:
                break
            await wheels.halt()
            levels, stop = await self._listen(kit, wheels, listen_s)
            merged[name] = merged.get(name, []) + levels
            kit.note(f"you listened again in the {name}: " + (f"{len(levels)} chirps" if levels else "no chirp"))
            if stop is not None:
                break
        return [(name, merged[name]) for name, _ in results]
