ABOUT = "Reminds whoever is home to water the plants on Monday and Thursday mornings."
USES = ["say", "look"]
UNTIL = "ongoing"
WANTS = {"at": ["09:00"], "arrives": ["anyone"]}


def on_at(time):
    if state("day_is", "monday") == True or state("day_is", "thursday") == True:
        keep("due", today())
        tell()


def on_arrives(who):
    if kept("due", "") == today():
        tell()


def tell():
    people = who_here()
    if len(people) > 0:
        first = people[0]
        say(f"It's plant day, {first}. The plants would love some water.")
        keep("due", "")
