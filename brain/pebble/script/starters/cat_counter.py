ABOUT = "Counts the cat's trips through the lounge and tells Alex the total at 9 pm."
USES = ["look", "say"]
FOR = "alex"
UNTIL = "21:00"
WANTS = {"seen": ["cat"], "at": ["21:00"]}


def on_start():
    keep("count", 0)


def on_seen(thing, place):
    if place == "lounge":
        keep("count", kept("count", 0) + 1)


def on_at(time):
    n = kept("count", 0)
    say_to("alex", f"The cat came through the lounge {n} times today.")
    finish()
