ABOUT = "Counts how many times each person comes home each day, and notes the day's visits in my journal at night."
USES = []
UNTIL = "ongoing"
WANTS = {"arrives": ["anyone"], "at": ["22:00"]}


def on_arrives(who):
    visits = kept("visits", {})
    visits[who] = visits.get(who, 0) + 1
    keep("visits", visits)


def on_at(time):
    visits = kept("visits", {})
    if len(visits) == 0:
        note("Nobody came home today.")
    else:
        parts = []
        for name in sorted(visits.keys()):
            count = visits[name]
            parts.append(f"{name} {count}")
        text = ", ".join(parts)
        note(f"Comings home today: {text}.")
    keep("visits", {})
