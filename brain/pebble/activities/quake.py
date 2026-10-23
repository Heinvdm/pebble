from ..things.words import listing
from .base import Activity, Ending
from .kit import Kit
from .motion import Wheels, leave_dock
from .rounds import can_drive, find_place, go, known_places, tour, where

HOME_S = 8 * 3600.0
TOP = 0.3
ANSWER_S = 8.0
CHECK_S = 0.5
PERSON_SCORE = 0.5
MAX_ROOMS = 6


class QuakeRound(Activity):
    kind = "quake_round"
    urgent = True
    sight = True

    def __init__(self, request, asker, target=None, battery: bool = False, why: str = "", report=None):
        super().__init__(request, asker, target, battery)
        self.why = why
        self.report = report
        self.done = self._finished
        self.people: dict[str, str] = {}
        self.found: dict[str, str] = {}
        self.missing: dict[str, str] = {}
        self.someone = False
        self.how = "stopped"

    def describe(self) -> str:
        return "checking on everyone after the earthquake"

    def _finished(self, result: str, detail: str) -> None:
        if self.report is None:
            return
        self.missing = {pid: label for pid, label in self.missing.items() if pid not in self.found}
        unchecked = {pid: label for pid, label in self.people.items() if pid not in self.found and pid not in self.missing}
        self.report({
            "how": self.how,
            "found": sorted(self.found.items(), key=lambda item: item[1]),
            "missing": sorted(self.missing.items(), key=lambda item: item[1]),
            "unchecked": sorted(unchecked.items(), key=lambda item: item[1]),
            "someone": self.someone,
        })

    def _by_label(self) -> dict[str, str]:
        return {label.lower(): pid for pid, label in self.people.items()}

    def _look(self, kit: Kit, since: float, expected: list[str]) -> bool:
        for pid in list(self.people):
            if pid not in self.found and kit.last_present(pid) >= since:
                self.found[pid] = self.people[pid]
        sight = kit.eyes.latest(1.0)
        seen = [p for p in (sight.people if sight is not None else ()) if p.score >= PERSON_SCORE]
        if not seen:
            return False
        self.someone = True
        labels = self._by_label()
        unnamed = 0
        for person in seen:
            name = kit.name_of(person.track)
            pid = labels.get(name.lower()) if name else None
            if pid is not None:
                self.found[pid] = self.people[pid]
            else:
                unnamed += 1
        left = [pid for pid in expected if pid not in self.found]
        if unnamed and len(left) == 1 and unnamed == 1:
            self.found[left[0]] = self.people[left[0]]
        return True

    async def _ask(self, kit: Kit, expected: list[str], start: float, door: bool = False) -> None:
        names = [self.people[pid] for pid in expected if pid not in self.found]
        if door:
            kit.say_loud(f"{listing(names)}, are you okay in there?" if names else "Is anyone in there? Are you okay?")
        else:
            kit.say(f"{listing(names)}, are you okay?" if names else "Is anyone here? Are you okay?")
        asked = kit.body.clock.now()
        until = kit.pace.now() + ANSWER_S
        while kit.pace.now() < until:
            self._look(kit, min(start, asked), expected)
            if expected and all(pid in self.found for pid in expected):
                return
            await kit.pace.sleep(CHECK_S)

    def _visits(self, kit: Kit) -> list[tuple[str, float, float, float, list[str]]]:
        rooms: dict[str, list[str]] = {}
        for pid in self.people:
            if pid in self.found:
                continue
            room = kit.usual_room(pid)
            if room and find_place(kit, room) is not None:
                rooms.setdefault(room, []).append(pid)
        places = []
        for name, x, y, radius in known_places(kit, spots=False):
            if name in rooms or len(places) < MAX_ROOMS:
                places.append((name, x, y, radius, rooms.get(name, [])))
        for room, pids in rooms.items():
            if room not in [p[0] for p in places]:
                x, y, radius = find_place(kit, room)
                places.append((room, x, y, radius, pids))
        ordered = tour([(name, x, y, radius) for name, x, y, radius, _ in places], where(kit))
        wanted = {name: pids for name, _, _, _, pids in places}
        return [(name, x, y, radius, wanted[name]) for name, x, y, radius in ordered]

    async def run(self, kit: Kit) -> Ending:
        start = kit.body.clock.now()
        self.people = {pid: label for pid, label in kit.here(HOME_S)}
        if not self.people:
            self.how = "done"
            return Ending("done", "you knew of nobody at home to check on")
        here_now = [pid for pid in self.people if kit.last_present(pid) >= start - 30.0]
        wheels = Wheels(kit).open()
        try:
            self._look(kit, start, [])
            if here_now or self.someone:
                await self._ask(kit, here_now, start)
            if all(pid in self.found for pid in self.people):
                self.how = "done"
                return Ending("done", "everyone you knew was home was right there")
            if not can_drive(kit) or where(kit) is None:
                self.how = "no_drive"
                return Ending("failed", "you can't drive round the rooms just now, so you only asked the people right here")
            visits = self._visits(kit)
            if visits and kit.body.telemetry.docked and wheels.why_not() is None:
                await leave_dock(kit, wheels)
            for name, x, y, radius, pids in visits:
                if all(pid in self.found for pid in self.people):
                    break
                waiting = [pid for pid in pids if pid not in self.found]
                if pids and not waiting:
                    continue
                reason = wheels.why_not()
                if reason:
                    return Ending("stopped", f"you stopped checking on everyone ({reason})")
                trip = await go(kit, x, y, radius, top=TOP, door=True)
                if not trip.ok:
                    if trip.how in ("stopped", "battery"):
                        return Ending("stopped", f"you stopped checking on everyone on the way to the {name} ({trip.text})")
                    kit.note(f"you could not get to the {name} to check on people ({trip.text})")
                    continue
                await wheels.halt()
                if trip.how == "door":
                    kit.note(f"you did not go into the {name}, which is private, so you called through the door")
                await self._ask(kit, waiting, start, door=trip.how == "door")
                for pid in waiting:
                    if pid not in self.found:
                        self.missing[pid] = self.people[pid]
        finally:
            await wheels.halt()
            wheels.close()
        self.how = "done"
        for pid, label in self.people.items():
            if pid not in self.found and pid not in self.missing and kit.usual_room(pid) is None:
                self.missing[pid] = label
        self.missing = {pid: label for pid, label in self.missing.items() if pid not in self.found}
        found = [label for pid, label in self.people.items() if pid in self.found]
        missing = [label for pid, label in self.people.items() if pid in self.missing]
        text = f"you found {listing(found)}" if found else "you found nobody"
        if missing:
            text += f"; you could not find {listing(missing)}"
        return Ending("done", text)
