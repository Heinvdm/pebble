ABOUT = "Looks for Alex's keys, remembers where it saw them, and tells Alex when asked where they are."
USES = ["do", "say", "look"]
FOR = "alex"
UNTIL = "2 hours"
WANTS = {"heard": ["me"]}


def on_start():
    found = do("find the keys")
    spot = where("keys")
    if found == "done":
        here = room()
        if here is None:
            here = "room I'm in"
        keep("spot", here)
        say(f"Found your keys! They're in the {here}.")
    elif spot is not None:
        keep("spot", spot)
        say(f"I can't see them right here, but I last saw your keys in the {spot}.")
    else:
        say("I couldn't find your keys. I'll keep an eye out.")


def on_heard(who, words):
    said = words.lower()
    if "where" in said and "keys" in said:
        spot = kept("spot")
        if spot is None:
            say("I haven't found them yet.")
        else:
            say(f"Your keys were in the {spot}.")
