from .age import parse_birthday
from .occasions import Calendar
from .clock import Clock
from .goals import GoalBook
from .memory import MemoryBook
from .people.book import PeopleBook
from .people.changes import ChangeBook
from .selfstore import SelfStore
from .things.book import ThingBook
from .values import Values

FILES = {
    "values": "values.json",
    "goals": "goals.json",
    "memory": "memory.json",
    "calendar": "calendar.json",
    "people": "people.json",
    "changes": "changes.json",
    "things": "things.json",
}


class Books:
    def __init__(self, store: SelfStore, clock: Clock):
        self.store = store
        self.clock = clock
        core = store.read("core.json")
        self.name = core.get("name", "Pebble")
        self.birthday = parse_birthday((store.read("setup.json", {}) or {}).get("born")) or parse_birthday(core.get("birthday"))
        self.values = Values(store.read("values.json"))
        self.goals = GoalBook(store.read("goals.json"), clock)
        self.memory = MemoryBook(store.read("memory.json"))
        self.calendar = Calendar(store.read("calendar.json"), self.birthday, self.name)
        self.people = PeopleBook(store.read("people.json", {}), clock)
        self.changes = ChangeBook(store.read("changes.json", {}), clock)
        self.things = ThingBook(store.read("things.json", {}), clock)
        self.preferences = store.read("preferences.json", {})

    def save(self, *names: str) -> None:
        for name in names:
            self.store.write(FILES[name], getattr(self, name).to_dict())

    def save_preferences(self) -> None:
        self.store.write("preferences.json", self.preferences)

    def save_all(self) -> None:
        self.save(*FILES)
