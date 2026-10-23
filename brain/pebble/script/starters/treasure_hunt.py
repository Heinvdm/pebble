ABOUT = "A treasure hunt with Alex: Alex hides my ball, then I search the rooms I know until I find it."
USES = ["do", "say", "look"]
FOR = "alex"
UNTIL = "1 hour"

ROOMS = ["lounge", "kitchen", "study", "hall"]


def on_start():
    say("Hide my ball somewhere, and I'll find it! I'll count to thirty.")
    wait(30)
    say("Ready or not, here I come!")
    places = []
    first = where("ball")
    if first is not None:
        places.append(first)
    for place in ROOMS:
        if place not in places:
            places.append(place)
    for place in places:
        went = do(f"go to the {place}")
        if went != "done":
            continue
        found = do("find the ball")
        if found == "done":
            say(f"Found it in the {place}! Treasure!")
            finish()
            return
    say("I couldn't find the ball anywhere. You win!")
    finish()
