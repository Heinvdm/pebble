from ..things.words import listing
from ..understand.request import Request
from .base import Activity, Ending
from .kit import Kit
from .motion import Wheels, leave_dock, turn_by
from .rounds import can_drive, find_place, go, private_room, tour, where

LOOK_S = 3.0
LOOK_TURN_DEG = 120.0
KEEP_GOING_BATTERY = 25.0
WHOLE = ("", "house", "home", "the house", "everywhere")


def whole_house(place: str) -> bool:
    return place in WHOLE


class Patrol(Activity):
    kind = "check"
    sight = True

    def describe(self) -> str:
        if whole_house(self.request.place):
            return "having a look round the house"
        return f"having a look round the {self.request.place}"

    def _rooms(self, kit: Kit) -> tuple[list, list]:
        wanted = kit.rooms() if whole_house(self.request.place) else [self.request.place]
        kept_out = dict(kit.kept_out()) if callable(getattr(kit, "kept_out", None)) else {}
        self.kept_by = kept_out
        rooms, skipped = [], []
        for name in wanted:
            place = find_place(kit, name)
            if place is None:
                skipped.append((name, "unknown"))
                continue
            if private_room(kit, place[0], place[1]) is not None:
                skipped.append((name, "private"))
                continue
            if name in kept_out:
                skipped.append((name, "kept out"))
                continue
            rooms.append((name, place[0], place[1], place[2]))
        return tour(rooms, where(kit)), skipped

    def _who_asked(self, rooms: list) -> str:
        found = list(dict.fromkeys((getattr(self, "kept_by", {}) or {}).get(name, "") for name in rooms))
        return found[0] if len(found) == 1 and found[0] else "I was"

    def _why_stop(self, kit: Kit, wheels: Wheels) -> Ending | None:
        if kit.battery_low():
            return Ending("battery", "your battery got low during your look round")
        battery = kit.battery_pct()
        if battery is not None and battery < KEEP_GOING_BATTERY:
            return Ending("battery", f"your battery fell to {round(battery)} percent, so you stopped your look round")
        reason = wheels.why_not()
        if reason:
            return Ending("stopped", f"you stopped your look round ({reason})")
        return None

    async def run(self, kit: Kit) -> Ending:
        own = self.asker.own
        if not can_drive(kit):
            return Ending("failed", "you can't go round the rooms on this body", "" if own else "I can't go round the rooms on this body.")
        if where(kit) is None:
            return Ending("failed", "you have lost track of where you are", "" if own else "I've lost track of where I am. I'll know again after a visit to my charger.")
        rooms, skipped = self._rooms(kit)
        if not rooms:
            if skipped and all(why == "private" for _, why in skipped):
                return Ending("done", "every room you were asked about is private", "" if own else "That's private, so I don't go in there.")
            return Ending("failed", "you don't know your way round the rooms yet", "" if own else "I don't know my way round the rooms yet.")
        docked = kit.body.telemetry.docked
        wheels = Wheels(kit).open()
        looked: list[str] = []
        ending: Ending | None = None
        try:
            if docked and wheels.why_not() is None:
                await leave_dock(kit, wheels)
            for name, x, y, radius in rooms:
                ending = self._why_stop(kit, wheels)
                if ending is not None:
                    break
                trip = await go(kit, x, y, radius)
                if not trip.ok:
                    if trip.how in ("stopped", "battery"):
                        ending = Ending("stopped" if trip.how == "stopped" else "battery", f"your look round stopped on the way to the {name} ({trip.text})")
                        break
                    skipped.append((name, "could not get there"))
                    kit.note(f"you could not get to the {name} on your look round ({trip.text})")
                    continue
                await wheels.halt()
                await turn_by(kit, wheels, LOOK_TURN_DEG)
                await kit.pace.sleep(LOOK_S)
                looked.append(name)
                kit.note(f"you had a look round the {name}")
        finally:
            await wheels.halt()
            wheels.close()
        text = f"you had a look round the {listing(looked)}" if looked else "you could not look round any rooms"
        private = [name for name, why in skipped if why == "private"]
        kept = [name for name, why in skipped if why == "kept out"]
        missed = [name for name, why in skipped if why == "could not get there"]
        if private:
            text += f"; you skipped the {listing(private)}, which {'is' if len(private) == 1 else 'are'} private"
        if kept:
            who = self._who_asked(kept)
            text += f"; you kept out of the {listing(kept)}, as " + ("you were asked" if who == "I was" else f"{who} asked")
        if missed:
            text += f"; you could not get to the {listing(missed)}"
        if ending is not None:
            return Ending(ending.how, f"{ending.text}; {text}", ending.say)
        say = ""
        if not own:
            say = f"I had a look round the {listing(looked)}." if looked else "I couldn't get to any of the rooms."
            if private:
                say += f" I skipped the {listing(private)}, since {'it is' if len(private) == 1 else 'they are'} private."
            if kept:
                say += f" I kept out of the {listing(kept)}, as {self._who_asked(kept)} asked."
        return Ending("done", text, say, Request("go_home") if docked else None)
