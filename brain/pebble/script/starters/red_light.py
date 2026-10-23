ABOUT = "Red light, green light with Alex, with a twist: sometimes I call a blue light, which means spin around."
USES = ["say", "face"]
FOR = "alex"
UNTIL = "20 minutes"

LIGHTS = ["green", "green", "red", "blue"]


def on_start():
    say("Red light, green light! Green means go, red means freeze, and blue means spin around.")
    wait(3)
    turns = 0
    while turns < 8:
        light = pick(LIGHTS)
        if light == "green":
            face("happy")
            say("Green light!")
        elif light == "red":
            face("surprised")
            say("Red light! Freeze!")
        else:
            face("mischief")
            say("Blue light! Spin around!")
        wait(4)
        turns += 1
    say("Game over! You were brilliant.")
    finish()
