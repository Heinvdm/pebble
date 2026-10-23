ABOUT = "A little dance of my own when I feel happy: turns left and right in a loop, three times over, with happy faces."
USES = ["do", "face"]
UNTIL = "ongoing"
WANTS = {"feeling": ["happy"]}


def on_feeling(feeling, level):
    if kept("danced", "") == today():
        return
    keep("danced", today())
    face("happy")
    for step in range(3):
        do("turn left 45 degrees")
        do("turn right 90 degrees")
        do("turn left 45 degrees")
    face("love")
